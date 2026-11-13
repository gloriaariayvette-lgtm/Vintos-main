"""Camera mamepa acceptance helpers (Studio only, not in the repository). Copied from the native video run's
common.py (registered generator byte for byte), with this work dir's source tree."""
import hashlib
import pathlib
import sys
import time

import numpy as np

HOME = pathlib.Path.home()
WORK = HOME / 'camera-mamepa-20261113'
SRC = WORK / 'src'
sys.path[:0] = [str(SRC / 'studio'), str(SRC / 'scripts'), str(HOME / 'native-video-20261113' / 'vendor')]
MIND = HOME / 'physics-lab/models/AEON-7__Gemma-4-12B-it-AEON-Abliterated-K4-BF16'
SHA = '989526926b49de244b87dc69ce23949652062a699925c9bdf9dc249116c4079d'
LABELS = ['left', 'right', 'up', 'down']
QUESTION = 'Watch this video. In which direction does the square move? Answer with exactly one word: left, right, up, or down.'
SETS = {'projector-development': (2026111312, 64, [10]), 'projector-final': (2026111313, 128, [14, 16]),
        'resampler-development': (2026111322, 128, [10]), 'resampler-final': (2026111323, 256, [14, 16])}


def clips(name):
    """The Codex's registered generator, byte for byte."""
    seed, count, speeds = SETS[name]
    rng = np.random.default_rng(seed)
    for i in range(count):
        label = i % 4; center = rng.integers(70, 122, size=2); half = int(rng.integers(6, 15))
        foreground = rng.integers(0, 256, size=3, dtype=np.uint8)
        background = rng.integers(0, 256, size=3, dtype=np.uint8)
        speed = int(rng.choice(speeds)); direction = np.array([[-1, 0], [1, 0], [0, -1], [0, 1]][label])
        frames = np.empty((4, 192, 192, 3), dtype=np.uint8)
        for j, at in enumerate([-1.5, -.5, .5, 1.5]):
            x, y = (center + direction * speed * at).astype(int)
            frames[j] = background; frames[j, y-half:y+half, x-half:x+half] = foreground
        yield frames, label


def still_frames(seed, count):
    """Public synthetic distractors: static coloured rectangles, no motion."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(count):
        f = np.empty((192, 192, 3), dtype=np.uint8); f[:] = rng.integers(0, 256, 3, dtype=np.uint8)
        x, y = rng.integers(20, 150, 2); w = int(rng.integers(10, 40))
        f[y:y+w, x:x+w] = rng.integers(0, 256, 3, dtype=np.uint8)
        out.append(f)
    return out


def word(text):
    import re
    m = re.match(r'^(left|right|up|down)\b', text.strip().lower())
    return m.group(1) if m else None


def load():
    from native_audio_runtime import NativeMind
    from native_video_runtime import AppleStream
    mind = NativeMind(MIND, SHA, 'apple')
    return mind, AppleStream(mind.backend)


class Tracer:
    """Records every chunk the stream forwards (embeddings stay in memory) and its logits."""
    def __init__(self, stream):
        self.stream, self.calls = stream, []
        self.original = stream.forward
        def forward(embeds, cache, vision=False):
            out = self.original(embeds, cache, vision)
            self.calls.append((embeds, vision, out))
            return out
        stream.forward = forward

    def reset(self):
        self.calls = []


def bulk_logits(stream, calls):
    """The stock MLX path: the same chunks prefilled at once with stock caches and the stock vision masks."""
    import mlx.core as mx
    embeds = mx.concatenate([c[0] for c in calls], axis=1)
    types = mx.concatenate([mx.full((1, int(c[0].shape[1])), 2 if c[1] else 0, dtype=mx.int32) for c in calls], axis=1)
    model = stream.model
    out = model.language_model(None, inputs_embeds=embeds, cache=model.make_cache(), logits_to_keep=1,
                               mm_token_type_ids=types)
    mx.eval(out.logits)
    return np.array(out.logits[0, -1].astype(mx.float32))


def pct(xs, q):
    return float(np.percentile(np.array(xs, dtype=np.float64), q)) if xs else None


def plain_stills(seed, count):
    """Shape-free stills: a flat colour with a soft vertical gradient."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(count):
        top, bottom = rng.integers(0, 256, 3), rng.integers(0, 256, 3)
        g = np.linspace(0, 1, 192)[:, None, None]
        out.append(np.broadcast_to(top * (1 - g) + bottom * g, (192, 192, 3)).astype(np.uint8).copy())
    return out


def bulk_reference(stream, mind, calls):
    import mlx.core as mx
    model = stream.model
    embeds = mx.concatenate([c[0] for c in calls], axis=1)
    types = mx.concatenate([mx.full((1, int(c[0].shape[1])), 2 if c[1] else 0, dtype=mx.int32) for c in calls], axis=1)
    cache = model.make_cache()
    out = model.language_model(None, inputs_embeds=embeds, cache=cache, logits_to_keep=1, mm_token_type_ids=types)
    tokens = []
    for _ in range(8):
        s = np.array(out.logits[0, -1].astype(mx.float32)); s[mind.suppress] = -np.inf
        t = int(np.argmax(s))
        if t in mind.eos:
            break
        tokens.append(t)
        out = model.language_model(None, inputs_embeds=mind.backend.text([t]), cache=cache, logits_to_keep=1)
    return mind.tokenizer.decode(tokens, skip_special_tokens=True)


def mamepa_hook(mamepa_list, stream, timings, keep=False):
    """on_embedding for LiveSession: each frame's pooled projection goes to every mamepa; time per frame kept."""
    def hook(kind, at, embeds, ref):
        if kind != 'frame':
            return
        started = time.perf_counter()
        x = stream.numpy(embeds)
        vec = x.reshape(-1, x.shape[-1]).mean(0)
        for m in mamepa_list:
            m.frame(vec, at, tokens=embeds if keep else None)
        timings.append(time.perf_counter() - started)
    return hook
