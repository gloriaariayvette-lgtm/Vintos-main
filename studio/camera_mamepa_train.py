#!/usr/bin/env python3
"""Train the camera mamepa's selective SSM forecaster, JEPA-style: from the carried state, predict the latent of the
next frames (horizons 1, 2 and 4) in a fixed whitened projection of the mind's own frame embeddings. No pixels are
predicted and no labels exist. Training data is synthetic only (this file's own generator, seeds far from every
registered evaluation seed); no live frame, recording or downloaded video is used.

Runs on Apple MLX. ``--encoder toy`` (a fixed random projection of tiny frames) needs no model and is the CPU check;
``--encoder aeon`` encodes through the checkpoint's own vision projection and is a GPU job that must hold
~/physics-lab/train.lock. The projection is PCA-whitened (fixed, so the target cannot collapse); only the
forecaster learns. The SSM forecaster is kept only if it beats persistence on held-out synthetic sequences by the
margin in ``--keep-margin``; otherwise the checkpoint carries no SSM and the mixture runs on its fixed forecasters.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camera_mamepa as cm

SEED_BASE = 7_300_000_000      # far from the registered motion seeds (2026111xxx) and the stills seeds (<2e6)
SIZE = 192


# ---------------------------------------------------------------- synthetic video (own generator)

def _shape_mask(kind, h, w, cy, cx, r):
    yy, xx = np.ogrid[:h, :w]
    if kind == 'square':
        return (np.abs(yy - cy) < r) & (np.abs(xx - cx) < r)
    d = np.hypot(yy - cy, xx - cx)
    if kind == 'disc':
        return d < r
    if kind == 'ring':
        return (d < r) & (d > r * .55)
    return (yy - cy > -r) & (yy - cy < r) & (np.abs(xx - cx) < (yy - cy + r) / 2)   # triangle


def _background(rng, h, w):
    kind = rng.integers(3)
    a, b = rng.integers(0, 256, 3), rng.integers(0, 256, 3)
    if kind == 0:
        return np.broadcast_to(a, (h, w, 3)).astype(np.float32)
    if kind == 1:
        g = np.linspace(0, 1, h if rng.integers(2) else w)
        g = g[:, None, None] if len(g) == h else g[None, :, None]
        return np.broadcast_to(a * (1 - g) + b * g, (h, w, 3)).astype(np.float32)
    small = rng.integers(0, 256, (6, 6, 3)).astype(np.float32)
    return np.kron(small, np.ones((h // 6 + 1, w // 6 + 1, 1)))[:h, :w].astype(np.float32)


def synthetic_clip(seed, frames=32, size=SIZE):
    """One clip of ``frames`` frames at ~2 fps: scenes of 2-12 frames joined by cuts. Each scene has 0-3 shapes
    with their own velocities (some still), an optional slow pan and a little brightness flicker."""
    rng = np.random.default_rng(seed)
    out = np.empty((frames, size, size, 3), np.uint8)
    cut = np.zeros(frames, bool)
    at = np.cumsum(np.r_[0., .5 + rng.uniform(-.05, .05, frames - 1)])
    i = 0
    while i < frames:
        n = int(rng.integers(2, 13))
        cut[i] = i > 0
        bg = _background(rng, size, size)
        shapes = [(rng.choice(['square', 'disc', 'ring', 'triangle']), rng.uniform(30, size - 30, 2),
                   rng.uniform(-14, 14, 2) * (rng.random() > .25), rng.uniform(5, 18), rng.integers(0, 256, 3))
                  for _ in range(int(rng.integers(0, 4)))]
        pan = rng.uniform(-4, 4, 2) * (rng.random() < .3)
        for j in range(min(n, frames - i)):
            f = np.roll(bg, (int(pan[0] * j), int(pan[1] * j)), (0, 1)).copy()
            for kind, c, v, r, col in shapes:
                cy, cx = c + v * j
                f[_shape_mask(kind, size, size, cy, cx, r)] = col
            out[i + j] = np.clip(f * rng.uniform(.96, 1.04), 0, 255)
        i += n
    return out, at, cut


# ---------------------------------------------------------------- encoders

def toy_encoder(dim=256, seed=1):
    """CPU check only: block-mean 12x12 thumbnails through a fixed random projection."""
    W = np.random.default_rng(seed).standard_normal((12 * 12 * 3, dim)).astype(np.float32) / math.sqrt(432)

    def encode(rgb):
        x = np.asarray(rgb, np.float32) / 255.
        h = x.shape[0] // 12 * 12
        x = x[:h, :h].reshape(12, h // 12, 12, h // 12, 3).mean((1, 3)).reshape(-1)
        return np.tanh((x - .5) @ W * 3)
    encode.space = 'toy'
    return encode


def aeon_encoder(stream):
    """The mind's own frame path: the mean of the projected soft tokens, as the sensory tap carries it."""
    def encode(rgb):
        e = stream.numpy(stream.image(rgb))
        return e.reshape(-1, e.shape[-1]).mean(0)
    encode.space = cm.SPACE
    return encode


def encode_clips(seeds, encoder, frames=32):
    V, DT, CUT = [], [], []
    for s in seeds:
        clip, at, cut = synthetic_clip(s, frames)
        V.append(np.stack([encoder(f) for f in clip]))
        DT.append(np.r_[0., np.diff(at)])
        CUT.append(cut)
    return np.stack(V).astype(np.float32), np.stack(DT).astype(np.float32), np.stack(CUT)


def fit_projection(V, dz):
    """Unit-normalise, centre, PCA-whiten to ``dz`` axes (each unit variance on the training frames)."""
    X = V.reshape(-1, V.shape[-1])
    X = X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    mu = X.mean(0)
    _, s, vt = np.linalg.svd(X - mu, full_matrices=False)
    sd = s[:dz] / math.sqrt(len(X))
    return mu.astype(np.float32), (vt[:dz].T / np.maximum(sd, 1e-6)).astype(np.float32)


def project(V, mu, P):
    X = V / np.maximum(np.linalg.norm(V, axis=-1, keepdims=True), 1e-12)
    return ((X - mu) @ P).astype(np.float32)


# ---------------------------------------------------------------- the SSM in MLX (same math as Model.ssm_step)

def init_params(dz, S, horizons, seed):
    rng = np.random.default_rng(seed)
    dt0 = np.exp(rng.uniform(np.log(.05), np.log(.5), dz))
    return {'Wd': rng.normal(0, .01, (dz, dz)), 'bd': np.log(np.expm1(dt0)),
            'A_log': np.log(np.tile(np.arange(1, S + 1, dtype=np.float64), (dz, 1))),
            'WB': rng.normal(0, 1 / math.sqrt(dz), (dz, S)), 'WC': rng.normal(0, 1 / math.sqrt(dz), (dz, S)),
            'Dskip': np.ones(dz), 'Wo': np.zeros((len(horizons), dz, dz))}


def mlx_forward(mx, p, Z, DTN):
    """Z [B,T,dz], DTN [B,T] (elapsed/dt_ref, 1 where unknown) -> predictions [K,B,T,dz]."""
    B, T, dz = Z.shape
    A = -mx.exp(p['A_log'])
    h = mx.zeros((B, dz, A.shape[1]))
    ys = []
    for t in range(T):
        x = Z[:, t]
        delta = mx.minimum(mx.logaddexp(mx.zeros_like(x), x @ p['Wd'] + p['bd']) * DTN[:, t:t + 1], 50.)
        Bt, Ct = x @ p['WB'], x @ p['WC']
        h = mx.exp(delta[..., None] * A) * h + (delta * x)[..., None] * Bt[:, None, :]
        ys.append((h * Ct[:, None, :]).sum(-1) + p['Dskip'] * x)
    Y = mx.stack(ys, 1)
    return Z[None] + mx.einsum('btd,kde->kbte', Y, p['Wo'])


def valid_masks(CUT, horizons):
    """[K,B,T] 1 where the target k frames ahead is in the same scene (a cut is not forecastable)."""
    B, T = CUT.shape
    out = np.zeros((len(horizons), B, T), np.float32)
    for i, k in enumerate(horizons):
        for t in range(T - k):
            out[i, :, t] = ~CUT[:, t + 1:t + k + 1].any(1)
    return out


def loss_fn(mx, p, Z, DTN, horizons, W):
    pred = mlx_forward(mx, p, Z, DTN)
    total = 0.
    for i, k in enumerate(horizons):
        w = W[i, :, :-k]
        total = total + (((pred[i, :, :-k] - Z[:, k:]) ** 2).mean(-1) * w).sum() / mx.maximum(w.sum(), 1.)
    return total / len(horizons)


def dtn(DT, dt_ref=.5):
    return np.where(DT > 0, np.minimum(DT, cm.MAX_STEP) / dt_ref, 1.).astype(np.float32)


def train(Z, DT, CUT, Zv, DTv, CUTv, horizons=(1, 2, 4), S=16, epochs=30, batch=16, lr=1e-3, wd=.05, seed=0, log=print):
    import mlx.core as mx
    import mlx.optimizers as optim
    from mlx.utils import tree_map
    p = tree_map(lambda v: mx.array(np.asarray(v, np.float32)), init_params(Z.shape[-1], S, horizons, seed))
    opt = optim.AdamW(learning_rate=lr, weight_decay=wd)
    grad = mx.value_and_grad(lambda q, z, d, w: loss_fn(mx, q, z, d, horizons, w))
    W, Wv = valid_masks(CUT, horizons), mx.array(valid_masks(CUTv, horizons))
    rng = np.random.default_rng(seed)
    Dn, Dvn = dtn(DT), dtn(DTv)
    zv, dv = mx.array(Zv), mx.array(Dvn)
    history, best = [], (float('inf'), None)
    for ep in range(epochs):
        order = rng.permutation(len(Z))
        for b in range(0, len(Z), batch):
            idx = order[b:b + batch]
            loss, g = grad(p, mx.array(Z[idx]), mx.array(Dn[idx]), mx.array(W[:, idx]))
            opt.update(p, g)
            mx.eval(p, opt.state)
        val = float(loss_fn(mx, p, zv, dv, horizons, Wv))
        history.append(val)
        if val < best[0]:   # early stopping on the selection split; the keep decision uses a separate test split
            best = (val, {k: np.array(v) for k, v in p.items()})
        log('epoch %d val %.5f' % (ep + 1, val))
    return best[1], history


def _masked(err, w):
    return float((err * w).sum() / max(w.sum(), 1.))


def persistence_loss(Z, CUT, horizons=(1, 2, 4)):
    W = valid_masks(CUT, horizons)
    return float(np.mean([_masked(((Z[:, :-k] - Z[:, k:]) ** 2).mean(-1), W[i, :, :-k]) for i, k in enumerate(horizons)]))


def ssm_loss_numpy(model, Z, DT, CUT, horizons=(1, 2, 4)):
    """Held-out loss (within-scene targets) through the numpy inference path (what the service runs)."""
    W = valid_masks(CUT, horizons)
    tot = []
    for b, (z, d) in enumerate(zip(Z, DT)):
        h = np.zeros((model.dz, model.S), np.float32)
        preds = []
        for t in range(len(z)):
            h, pk = model.ssm_step(h, z[t], float(d[t]))
            preds.append(pk)
        preds = np.stack(preds, 1)   # [K,T,dz]
        tot.append([(((preds[i, :-k] - z[k:]) ** 2).mean(-1), W[i, b, :-k]) for i, k in enumerate(horizons)])
    return float(np.mean([_masked(np.concatenate([t[i][0] for t in tot]), np.concatenate([t[i][1] for t in tot]))
                          for i in range(len(horizons))]))


def calibrate(ckpt, space, V, DT, CUT, report):
    """err_scale = median of the best forecaster's relative error on within-scene transitions (the unit of
    surprise); boundary diagnostics at the candidate thresholds."""
    model = cm.Model(ckpt, space)
    errs, labels = [], []
    for v, d, c in zip(V, DT, CUT):
        m = cm.Mamepa(model)
        m.new_stream('cal', 0.)
        at = np.cumsum(d)
        for t in range(len(v)):
            r = m.frame(v[t], float(at[t]))
            if 'best_error' in r:
                errs.append(r['best_error'])
                labels.append(bool(c[t]))
    errs, labels = np.array(errs), np.array(labels)
    scale = float(np.median(errs[~labels]))
    ratio = errs / scale
    diag = {}
    for b in (2.5, 5., 10., 20., 40.):
        hit = ratio >= b
        tp = int((hit & labels).sum())
        diag[str(b)] = {'recall_cuts': tp / max(1, labels.sum()), 'precision': tp / max(1, hit.sum())}
    report.update(err_scale=scale, boundary_diagnostics=diag, within_scene_median=scale,
                  cut_median=float(np.median(errs[labels])) if labels.any() else None)
    return scale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--encoder', choices=['toy', 'aeon'], default='toy')
    ap.add_argument('--clips', type=int, default=64)
    ap.add_argument('--val-clips', type=int, default=16, help='selection split; the test split has the same size')
    ap.add_argument('--frames', type=int, default=32)
    ap.add_argument('--dz', type=int, default=64)
    ap.add_argument('--state', type=int, default=16)
    ap.add_argument('--epochs', type=int, default=30)
    ap.add_argument('--keep-margin', type=float, default=.05, help='SSM must beat persistence held-out loss by this')
    ap.add_argument('--cpu', action='store_true')
    ap.add_argument('--mind', help='checkpoint directory (aeon encoder)')
    ap.add_argument('--expected-sha256')
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    import mlx.core as mx
    if args.cpu:
        mx.set_default_device(mx.cpu)
    started = time.time()
    if args.encoder == 'aeon':
        from native_audio_runtime import NativeMind
        from native_video_runtime import AppleStream
        mind = NativeMind(args.mind, args.expected_sha256, 'apple')
        encoder = aeon_encoder(AppleStream(mind.backend))
    else:
        encoder = toy_encoder()
    train_seeds = [SEED_BASE + i for i in range(args.clips)]
    val_seeds = [SEED_BASE + 500_000 + i for i in range(args.val_clips)]
    V, DT, CUT = encode_clips(train_seeds, encoder, args.frames)
    Vv, DTv, CUTv = encode_clips(val_seeds, encoder, args.frames)
    Vt, DTt, CUTt = encode_clips([SEED_BASE + 900_000 + i for i in range(args.val_clips)], encoder, args.frames)
    mu, P = fit_projection(V, args.dz)
    Z, Zv, Zt = project(V, mu, P), project(Vv, mu, P), project(Vt, mu, P)
    horizons = (1, 2, 4)
    params, history = train(Z, DT, CUT, Zv, DTv, CUTv, horizons, args.state, args.epochs)
    space = cm.SPACE if args.encoder == 'aeon' else 'toy'
    meta = {'trained': True, 'horizons': list(horizons), 'dt_ref': .5, 'space': space,
            'data': 'synthetic-v1 (own generator, seeds %d+)' % SEED_BASE,
            'train_clips': args.clips, 'val_clips': args.val_clips, 'frames': args.frames, 'err_scale': None}
    arrays = dict(mu=mu, P=P, **{k: v.astype(np.float32) for k, v in params.items()})
    out = Path(args.out)
    tmp = out.with_name(out.stem + '.tmp.npz')
    cm.save(tmp, arrays, meta)
    report = {'encoder': args.encoder, 'history': history, 'persistence_test': persistence_loss(Zt, CUTt, horizons),
              'ssm_test_numpy': ssm_loss_numpy(cm.Model(tmp, space), Zt, DTt, CUTt, horizons)}
    report['ssm_gain'] = 1 - report['ssm_test_numpy'] / report['persistence_test']
    report['ssm_kept'] = report['ssm_gain'] >= args.keep_margin
    if not report['ssm_kept']:
        arrays = {'mu': mu, 'P': P}
        meta.update(trained=False, horizons=[1])
        cm.save(tmp, arrays, meta)
    meta['err_scale'] = calibrate(tmp, space, Vt, DTt, CUTt, report)
    report.update(checkpoint=str(out), checkpoint_id=cm.save(out, arrays, meta), seconds=time.time() - started)
    tmp.unlink()
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'history'}))


if __name__ == '__main__':
    main()
