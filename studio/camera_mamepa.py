"""Camera mamepa: a small Mamba-style state-space model over the live stream's frame embeddings, JEPA-trained to
predict the latent of the next frames (never pixels), and a compact "what happened recently" for the video prompt.

It follows the carrying-state conventions of his inner models (latent_stream_model.py, the persistence candidates),
so his eyes and his inner state keep one memory scheme:
  * a versioned schema; a checkpoint is one .npz with a JSON ``meta`` and is identified by its sha256; a dumped
    state names the checkpoint it belongs to and is refused by any other;
  * carried state = the last latent plus continuous-time EMA levels over a ladder of time constants
    (w = exp(-dt/tau)), each elapsed step clamped to 0..300 s, so a gap never invents carry;
  * several forecasters of the next latent, mixed per axis with online weights from each one's recently realized
    error (inverse-MSE weights, decayed in continuous time; only outcomes already seen are used);
  * ``advance`` scores the preceding state once before ingesting, ingests each event once (``seen``), and returns
    raw errors, never probabilities or claims about what was seen.

Inputs are the sensory tap's frame vectors (mean of the projected soft tokens, ``aeon-12b/vision-proj``) and tag
events. Audio is a different vector space and is never mixed into this state. Nothing is written to disk by the
model; a state lives in memory unless a caller dumps it. AprilTag ids are keys: a seen tag retrieves the records a
pluggable store links to that key (a direct lookup, never a guess).
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = 'camera-mamepa-v1'
SPACE = 'aeon-12b/vision-proj'
TAUS = (0.5, 2., 8., 30., 120.)    # seconds: frame-to-frame, a gesture, a moment, a scene, a few minutes
MAX_STEP = 300.                    # one elapsed step never carries more than five minutes
MIX_TAU = 10.                      # seconds over which a forecaster's realized error is remembered
ETA = 1.                           # inverse-MSE weight exponent (the persistence candidates' m08 choice)
BOUNDARY = 10.                     # surprise (error / calibrated scale) that opens a new segment
MIN_VIEW_FRAMES = 2                # an adaptive view never shows fewer frames than this
MAX_SEGMENTS = 64
MAX_EPISODES = 16                  # remembered sightings per tag key
KEEP_PER_SEGMENT = 8               # frames' projected tokens kept per scene for recall (memory only)
MAX_KEPT = 32                      # across scenes; the oldest scene's frames go first
MAX_SEEN = 8192
NOTE_CHARS = 900                   # the summary line budget (well inside the answer reserve)
RECORD_CHARS = 240


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def softplus(x):
    return np.logaddexp(0., x)


def stamp(seconds):
    minutes, rest = divmod(max(0, int(seconds)), 60)
    return '%02d:%02d' % (minutes, rest)


# ---------------------------------------------------------------- pixel motion per scene (camera_motion.py)

WHOLE_VIEW_CUT = .6     # a step that changed more of the view than this with no consistent shift is a cut


def _add_motion(seg, move):
    """Add one camera_motion step to a scene's record: reliable object steps and whole-view moves separately."""
    m = seg.setdefault('motion', {'dx': 0., 'dy': 0., 'moving': 0, 'pan_dx': 0., 'pan_dy': 0., 'pans': 0, 'steps': 0})
    m['steps'] += 1
    if not move['reliable']:
        return
    if move['changed'] > WHOLE_VIEW_CUT:
        m['pan_dx'] = round(m['pan_dx'] + move['dx'], 5); m['pan_dy'] = round(m['pan_dy'] + move['dy'], 5); m['pans'] += 1
    else:
        m['dx'] = round(m['dx'] + move['dx'], 5); m['dy'] = round(m['dy'] + move['dy'], 5); m['moving'] += 1


def _merge_motion(segs):
    out = {'motion': {'dx': 0., 'dy': 0., 'moving': 0, 'pan_dx': 0., 'pan_dy': 0., 'pans': 0, 'steps': 0}}
    for s in segs:
        for k, v in (s.get('motion') or {}).items():
            out['motion'][k] += v
    return out


def motion_phrase(seg):
    """'something in view moved left' (and/or 'the whole view shifted up'), or None when nothing moved clearly."""
    from camera_motion import direction
    m = seg.get('motion') or {}
    parts = []
    if m.get('moving'):
        way = direction(m['dx'], m['dy'])
        parts.append('something in view moved %s' % way if way else 'something in view moved, in no single clear direction')
    if m.get('pans'):
        way = direction(m['pan_dx'], m['pan_dy'])
        if way:
            parts.append('the whole view shifted %s' % way)
    return ' and '.join(parts) or None


# ---------------------------------------------------------------- checkpoint

def save(path, arrays, metadata):
    """Write a checkpoint; returns its id (sha256 of the file)."""
    meta = dict(metadata, schema=SCHEMA, space=metadata.get('space', SPACE))
    np.savez_compressed(path, meta=json.dumps(meta, sort_keys=True), **arrays)
    return _digest(path)


def untrained(dim=3840, dz=64, seed=0):
    """Arrays for a checkpoint with no learned forecaster: a fixed orthonormal projection and no SSM."""
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.standard_normal((dim, dz)))
    return {'mu': np.zeros(dim, np.float32), 'P': (q * math.sqrt(dim / dz)).astype(np.float32)}, \
        {'trained': False, 'seed': int(seed), 'err_scale': None, 'horizons': [1]}


class Model:
    """Frozen parameters: projection (mu, P) and, when trained, the selective SSM forecaster."""
    SSM = ('Wd', 'bd', 'A_log', 'WB', 'WC', 'Dskip', 'Wo')

    def __init__(self, path, space=SPACE):
        with np.load(path, allow_pickle=False) as z:
            self.meta = json.loads(str(z['meta']))
            self.a = {k: z[k].astype(np.float32) for k in z.files if k != 'meta'}
        m, a = self.meta, self.a
        if m.get('schema') != SCHEMA or m.get('space') != space:
            raise ValueError('incompatible camera-mamepa schema')
        if a['P'].ndim != 2 or a['mu'].shape != (a['P'].shape[0],):
            raise ValueError('invalid projection')
        self.dim, self.dz = a['P'].shape
        self.trained = all(k in a for k in self.SSM)
        if self.trained:
            S = a['A_log'].shape[1]
            shapes = {'Wd': (self.dz, self.dz), 'bd': (self.dz,), 'A_log': (self.dz, S), 'WB': (self.dz, S),
                      'WC': (self.dz, S), 'Dskip': (self.dz,), 'Wo': (len(m.get('horizons', [1])), self.dz, self.dz)}
            for k, shape in shapes.items():
                if a[k].shape != shape:
                    raise ValueError('invalid parameter ' + k)
            self.A = -np.exp(a['A_log'])
            self.S = S
        for k, v in a.items():
            if not np.isfinite(v).all():
                raise ValueError('invalid parameter ' + k)
        self.err_scale = m.get('err_scale')
        self.dt_ref = float(m.get('dt_ref', .5))
        self.checkpoint_id = _digest(path)

    def project(self, vec):
        v = np.asarray(vec, np.float32).reshape(-1)
        if v.shape != (self.dim,) or not np.isfinite(v).all():
            raise ValueError('invalid frame vector')
        v = v / (np.linalg.norm(v) or 1.)
        return ((v - self.a['mu']) @ self.a['P']).astype(np.float32)

    def ssm_step(self, h, x, dt):
        """One selective (Mamba-style) step in continuous time: the input sets its own step size, scaled by the
        real elapsed seconds; returns the new hidden state and the next-latent forecast for each horizon."""
        a = self.a
        delta = softplus(x @ a['Wd'] + a['bd']) * (min(max(dt, 0.), MAX_STEP) / self.dt_ref if dt else 1.)
        delta = np.minimum(delta, 50.)
        Bt, Ct = x @ a['WB'], x @ a['WC']
        h = np.exp(delta[:, None] * self.A) * h + (delta * x)[:, None] * Bt[None, :]
        y = h @ Ct + a['Dskip'] * x
        return h.astype(np.float32), x[None, :] + np.einsum('d,kde->ke', y, a['Wo'])


# ---------------------------------------------------------------- pluggable tag store

class TagStore:
    """Interface: ``lookup(key)`` returns the records linked to a tag key ('<family>:<id>'), [] when none."""
    def lookup(self, key):
        return []


class DictTagStore(TagStore):
    """In-memory store (tests and synthetic records only)."""
    def __init__(self, records):
        self.records = {str(k): [dict(r) for r in (v if isinstance(v, list) else [v])] for k, v in records.items()}

    def lookup(self, key):
        return [dict(r) for r in self.records.get(key, [])]


class CallableTagStore(TagStore):
    """Adapter for an existing lookup, e.g. ``lambda key: ...`` over the workspace tag map. Faults read as empty."""
    def __init__(self, fn):
        self.fn = fn

    def lookup(self, key):
        try:
            out = self.fn(key)
        except Exception:
            return []
        if out is None:
            return []
        return [r for r in (out if isinstance(out, list) else [out]) if isinstance(r, dict)]


class TagMapStore(TagStore):
    """Read-only view of a resolved tag-map copy (written by scripts/apriltag_map_sync.py): {key: {'label', 'text'}
    or {'label', 'record'}}. The file must be private (no group or other access); it is re-read when it changes and
    a missing or unreadable file reads as no records. Nothing is ever written back."""
    def __init__(self, path):
        self.path = Path(path)
        self.stamp, self.map = None, {}

    def _load(self):
        import os
        import stat
        try:
            st = self.path.stat()
        except OSError:
            self.stamp, self.map = None, {}
            return
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError('the tag map copy must be private (mode 600)')
        if (st.st_mtime_ns, st.st_size) == self.stamp:
            return
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            data = {}
        self.map = {k: v for k, v in data.items() if isinstance(v, dict) and not k.startswith('_')} \
            if isinstance(data, dict) else {}
        self.stamp = (st.st_mtime_ns, st.st_size)

    def lookup(self, key):
        self._load()
        entry = self.map.get(key)
        if not entry:
            return []
        if entry.get('text'):
            return [{'text': str(entry['text'])[:1200], 'label': entry.get('label')}]
        if isinstance(entry.get('record'), dict):
            return [dict(entry['record'], label=entry.get('label'))]
        return []


# ---------------------------------------------------------------- state

class Mamepa:
    """Carried state for one camera: forecasters, their online weights, segments and tag episodes."""
    EXPERTS = ('persist', 'drift') + tuple('ema%g' % t for t in TAUS[1:]) + ('ssm',)

    def __init__(self, model, store=None, boundary=BOUNDARY, payload=None):
        self.model, self.store, self.boundary = model, store or TagStore(), float(boundary)
        dz = model.dz
        self.experts = [e for e in self.EXPERTS if e != 'ssm' or model.trained]
        k = len(self.experts)
        self.last = None
        self.levels = np.zeros((len(TAUS), dz), np.float32)
        self.h = np.zeros((dz, model.S), np.float32) if model.trained else None
        self.forecast = None                       # (k, dz): each expert's forecast of the next latent
        self.L = np.full((k, dz), .3, np.float32)  # decayed realized squared error per expert and axis
        self.M = 1.
        self.err_level = None                      # running error, the scale when the checkpoint has none
        self.at = None
        self.t = None
        self.stream = None
        self.frames = 0
        self.seen = []
        self._seen = set()
        self.segments = []
        self.episodes = {}
        self.records = {}
        self.kept = []                             # [{'sid', 'at', 'tokens'}]: opaque embeddings, never dumped
        self.thumb = None                          # the previous frame's 96-px thumbnail (camera_motion), memory only
        self.next_sid = 0
        if payload:
            self.load(payload)

    # -- persistence of the state (in memory unless the caller writes it)
    def dump(self):
        return {'schema': SCHEMA, 'checkpoint_id': self.model.checkpoint_id, 'experts': self.experts,
                'last': None if self.last is None else self.last.tolist(), 'levels': self.levels.tolist(),
                'h': None if self.h is None else self.h.tolist(),
                'forecast': None if self.forecast is None else self.forecast.tolist(),
                'L': self.L.tolist(), 'M': self.M, 'err_level': self.err_level, 'at': self.at, 't': self.t,
                'stream': self.stream, 'frames': self.frames, 'seen': list(self.seen),
                'segments': [{k: v for k, v in s.items() if k != 'zsum'} for s in self.segments],
                'episodes': self.episodes}

    def load(self, p):
        if p.get('schema') != SCHEMA or p.get('checkpoint_id') != self.model.checkpoint_id:
            raise ValueError('state checkpoint mismatch')
        if p.get('experts') != self.experts:
            raise ValueError('state forecaster mismatch')
        arr = lambda v, shape: None if v is None else np.asarray(v, np.float32).reshape(shape)
        dz = self.model.dz
        self.last = arr(p['last'], (dz,))
        self.levels = arr(p['levels'], (len(TAUS), dz))
        self.h = arr(p['h'], (dz, self.model.S)) if self.model.trained else None
        self.forecast = arr(p['forecast'], (len(self.experts), dz))
        self.L, self.M = arr(p['L'], (len(self.experts), dz)), float(p['M'])
        self.err_level, self.at, self.t = p['err_level'], p['at'], p['t']
        self.stream, self.frames = p['stream'], int(p['frames'])
        self.seen = [tuple(s) if isinstance(s, list) else s for s in p['seen']][-MAX_SEEN:]
        self._seen = set(self.seen)
        self.segments = [dict(s) for s in p['segments']][-MAX_SEGMENTS:]
        self.next_sid = max([int(s.get('sid') or 0) for s in self.segments] + [0])
        self.episodes = {k: list(v)[-MAX_EPISODES:] for k, v in p['episodes'].items()}

    def _mark_seen(self, key):
        if key is None:
            return False
        if key in self._seen:
            return True
        self.seen.append(key)
        self._seen.add(key)
        if len(self.seen) > MAX_SEEN:
            self._seen.discard(self.seen.pop(0))
        return False

    # -- the forecasters
    def _forecasts(self, x, dt):
        out = []
        for e in self.experts:
            if e == 'persist':
                out.append(x)
            elif e == 'drift':   # continue the last step's change away from the fast level
                out.append(x + (x - self.levels[0]))
            elif e == 'ssm':
                self.h, pred = self.model.ssm_step(self.h, x, dt)
                out.append(pred[0])
            else:
                out.append(self.levels[TAUS.index(float(e[3:]))].copy())
        return np.stack(out).astype(np.float32)

    def weights(self):
        """Per-axis inverse-MSE weights from each forecaster's recently realized error."""
        w = 1. / np.maximum(self.L / max(self.M, 1e-6), 1e-3) ** ETA
        return w / w.sum(0, keepdims=True)

    def prediction(self):
        return None if self.forecast is None else (self.weights() * self.forecast).sum(0)

    # -- ingestion
    def new_stream(self, stream, at=0., t=None):
        """A fresh live session: the carry continues (decayed by real time), segments start again."""
        self.stream = stream
        self.at = None
        self.thumb = None
        self.segments.append({'start': float(at), 'end': float(at), 'frames': 0, 'stream': stream, 'tags': [],
                              'change': 0., 'peak': None, 'opened_by': 'stream', 'sid': self._sid()})
        del self.segments[:-MAX_SEGMENTS]
        self.records = {}
        if t is not None and self.t is not None:
            self._decay(min(max(float(t) - self.t, 0.), MAX_STEP))
        self.t = t if t is not None else self.t

    def _sid(self):
        self.next_sid += 1
        return self.next_sid

    def _keep(self, sid, at, tokens):
        mine = [k for k in self.kept if k['sid'] == sid]
        if len(mine) >= KEEP_PER_SEGMENT:   # thin a long scene evenly: drop every second kept frame, keep the first
            drop = {id(k) for k in mine[1::2]}
            self.kept = [k for k in self.kept if id(k) not in drop]
        self.kept.append({'sid': sid, 'at': float(at), 'tokens': tokens})
        while len(self.kept) > MAX_KEPT:
            oldest = self.kept[0]['sid']
            self.kept = [k for k in self.kept if k['sid'] != oldest] or self.kept[1:]

    def recall(self, max_frames=4, min_frames=2):
        """The most recent earlier scene of this stream (not the current one) with at least ``min_frames``
        frames and kept tokens: up to ``max_frames`` of its frames (evenly spaced) and a note saying what they
        are. None when there is no such scene."""
        segs = self.current()
        for seg in reversed(segs[:-1]):
            frames = [(k['at'], k['tokens']) for k in self.kept if k['sid'] == seg.get('sid')]
            if seg['frames'] >= min_frames and len(frames) >= min_frames:
                pick = np.unique(np.linspace(0, len(frames) - 1, min(max_frames, len(frames))).round().astype(int))
                moved = motion_phrase(seg)
                note = ('[CAMERA MEMORY RECALL: the frames stamped %s-%s just above are from an earlier scene '
                        '(%d frames), shown again from memory%s; the current scene began at %s.]' % (
                            stamp(seg['start']), stamp(seg['end']), seg['frames'],
                            '; in that earlier scene ' + moved if moved else '', stamp(segs[-1]['start'])))
                return {'frames': [frames[i] for i in pick], 'note': note,
                        'segment': {k: seg[k] for k in ('start', 'end', 'frames')}}
        return None


    def _decay(self, dt):
        """Pure passage of time with nothing seen: levels hold, the realized-error memory fades."""
        w = math.exp(-dt / MIX_TAU)
        self.L *= w
        self.M *= w

    def frame(self, vec, at, t=None, key=None, tokens=None, thumb=None):
        """Ingest one frame vector at stream time ``at`` (seconds). Returns raw errors of the preceding state's
        forecast (``None`` for a duplicate). ``tokens`` (optional, opaque) are the frame's projected soft tokens,
        kept in memory per scene so an earlier scene can be shown again after it has left the window. ``thumb``
        (optional, camera_motion.thumb of the same frame) adds the pixel motion organ: the step from the previous
        frame is added to the scene's motion, and a whole-view change with no consistent shift opens a new scene."""
        if self._mark_seen(key):
            return None
        at = float(at)
        x = self.model.project(vec)
        dt = 0. if self.at is None else min(max(at - self.at, 0.), MAX_STEP)
        if self.at is None and self.t is not None and t is not None:
            dt = min(max(float(t) - self.t, 0.), MAX_STEP)
        result = {'at': round(at, 3), 'kind': 'frame', 'checkpoint_id': self.model.checkpoint_id}
        surprise = None
        if self.forecast is not None:
            err = (self.forecast - x[None, :]) ** 2                    # (k, dz) realized now
            mix = self.prediction()
            norm = max(float(np.mean(x ** 2)), 1e-6)
            e = float(np.mean((mix - x) ** 2) / norm)
            # Surprise asks whether ANY forecaster foresaw this frame: right after a cut the mixture weights still
            # reflect the old scene, but a continuing scene is foreseen at least by persistence.
            best = float(err.mean(1).min() / norm)
            scale = self.model.err_scale or self.err_level or best
            surprise = best / max(scale, 1e-9)
            w = math.exp(-dt / MIX_TAU)
            self.L = w * self.L + err
            self.M = w * self.M + 1.
            self.err_level = best if self.err_level is None else .9 * self.err_level + .1 * best
            result.update(error=e, best_error=best, persist_error=float(np.mean(err[0]) / norm),
                          surprise=surprise, weights=dict(zip(self.experts, self.weights().mean(1).round(4).tolist())))
        # carry: continuous-time EMA levels of the latent
        if self.last is None:
            self.levels[:] = x
        else:
            w = np.exp(-max(dt, 1e-3) / np.asarray(TAUS, np.float32))[:, None]
            self.levels = (w * self.levels + (1 - w) * x[None, :]).astype(np.float32)
        self.forecast = self._forecasts(x, dt)
        self.last, self.at, self.frames = x, at, self.frames + 1
        if t is not None:
            self.t = float(t)
        move = None
        if thumb is not None:
            from camera_motion import step
            move = step(self.thumb, thumb) if self.thumb is not None else None
            self.thumb = thumb
        cut = bool(move and move['changed'] > WHOLE_VIEW_CUT and not move['reliable'])
        self._segment(at, x, surprise, cut)
        if move and not cut:
            _add_motion(self.segments[-1], move)
        if move is not None:
            result['motion'] = {k: move[k] for k in ('dx', 'dy', 'reliable', 'changed')}
        if tokens is not None:
            self._keep(self.segments[-1]['sid'], at, tokens)
        result['segment_start'] = self.segments[-1]['start']
        result['boundary'] = self.segments[-1]['frames'] == 1 and self.segments[-1]['opened_by'] in ('surprise', 'cut')
        return result

    def _segment(self, at, x, surprise, cut=False):
        cur = self.segments[-1] if self.segments and self.segments[-1]['stream'] == self.stream else None
        if cur is None or (cur['frames'] and ((surprise is not None and surprise >= self.boundary) or cut)):
            cur = {'start': at, 'end': at, 'frames': 0, 'stream': self.stream, 'tags': [], 'change': 0.,
                   'sid': self._sid(), 'peak': None if surprise is None else round(surprise, 3),
                   'opened_by': 'cut' if cur is not None and cut and (surprise is None or surprise < self.boundary)
                   else 'surprise' if surprise is not None else 'stream'}
            self.segments.append(cur)
            del self.segments[:-MAX_SEGMENTS]
        elif surprise is not None and cur['frames']:
            cur['change'] = round(cur['change'] + (min(surprise, self.boundary) - cur['change']) / cur['frames'], 4)
        if not cur['frames']:
            cur['start'] = at
        cur['frames'] += 1
        cur['end'] = at

    def tag(self, at, detection, key=None):
        """A seen AprilTag: its key retrieves linked records from the store (cached per stream) and the sighting
        is bound to the current segment, so a later sighting recalls when it was last seen."""
        if self._mark_seen(key):
            return None
        tag_key = '%s:%s' % (detection.get('family'), detection.get('tag_id'))
        if tag_key not in self.records:
            self.records[tag_key] = self.store.lookup(tag_key)
        before = list(self.episodes.get(tag_key, []))
        seg = self.segments[-1] if self.segments else None
        if seg is not None and tag_key not in seg['tags']:
            seg['tags'].append(tag_key)
        episode = {'at': round(float(at), 3), 'stream': self.stream, 'segment_start': seg['start'] if seg else None}
        if not before or before[-1]['stream'] != episode['stream'] or before[-1]['segment_start'] != episode['segment_start']:
            self.episodes[tag_key] = (before + [episode])[-MAX_EPISODES:]
        return {'tag': tag_key, 'records': self.records[tag_key], 'previous': before}

    def feed(self, events):
        """Consume sensory-tap events (schema v1). Frames in another vector space are refused, never mixed."""
        out = []
        for ev in events:
            if ev.get('v') != 1:
                raise ValueError('unknown tap schema')
            if ev.get('stream') != self.stream:
                self.new_stream(ev.get('stream'), ev.get('at') or 0., ev.get('t'))
            key = (ev.get('stream'), ev.get('seq'))
            if ev['kind'] == 'frame':
                if ev.get('space') != SPACE:
                    raise ValueError('frame vector from another space')
                from native_sensory_tap import decode_vector
                out.append(self.frame(decode_vector(ev), ev['at'], ev.get('t'), key))
            elif ev['kind'] == 'tag':
                out.append(self.tag(ev['at'], ev, key))
        return out

    # -- what the prompt sees
    def current(self):
        return [s for s in self.segments if s['stream'] == self.stream and s['frames']]

    def onset(self, min_frames=MIN_VIEW_FRAMES):
        """Stream time where the present happening began: the start of the current segment, extended back over
        earlier segments until at least ``min_frames`` frames are in view. None before any frame."""
        segs = self.current()
        if not segs:
            return None
        n, start = 0, None
        for s in reversed(segs):
            n += s['frames']
            start = s['start']
            if n >= min_frames:
                break
        return start

    def summary(self, now=None, tags_text=True):
        """Compact, factual: segment timing and how much changed, plus each tag seen and its linked records.
        It names no objects and guesses nothing."""
        segs = self.current()
        if not segs:
            return {'lines': [], 'onset': None, 'segments': 0}
        cur = segs[-1]
        lines = []
        steady = 'little change' if cur['change'] < .5 else 'steady change' if cur['change'] < 1.2 else 'much change'
        lines.append('[CAMERA MEMORY: the current scene began at %s and has lasted %d frame(s), with %s.' % (
            stamp(cur['start']), cur['frames'], steady))
        onset = self.onset()
        present = [s for s in segs if s['start'] >= onset - 1e-6]
        moved = motion_phrase(_merge_motion(present))
        if moved:
            lines.append('Since %s, %s.' % (stamp(onset), moved))
        earlier = segs[:-1]
        if earlier:
            back = next((s for s in reversed([s for s in segs if s['start'] < onset - 1e-6])
                         if s['frames'] >= 2 and motion_phrase(s)), None)
            if back is not None:
                lines.append('In the earlier scene %s-%s, %s.' % (stamp(back['start']), stamp(back['end']),
                                                                motion_phrase(back)))
            short = [s for s in earlier if s['frames'] <= 2]
            span = '%s-%s' % (stamp(earlier[0]['start']), stamp(earlier[-1]['end']))
            if len(short) == len(earlier):
                lines.append('Before it, %s: %d brief scene(s), each a different view.' % (span, len(earlier)))
            else:
                longest = max(earlier, key=lambda s: s['frames'])
                lines.append('Before it, %s: %d scene(s); the longest from %s, %d frame(s).' % (
                    span, len(earlier), stamp(longest['start']), longest['frames']))
        lines[-1] += ']'
        if tags_text:
            for key in sorted({k for s in segs for k in s['tags']}):
                recs = self.records.get(key) or []
                eps = self.episodes.get(key, [])
                prior = [e for e in eps if e['stream'] != self.stream]
                seen = ' (seen before, in an earlier stream)' if prior else ''
                if recs:
                    text = '; '.join(str(r.get('text') or json.dumps(r, ensure_ascii=False, sort_keys=True))[:RECORD_CHARS]
                                     for r in recs[:3])
                    lines.append('[TAG %s in view%s - linked record(s): %s]' % (key, seen, text))
                else:
                    lines.append('[TAG %s in view%s - no record is linked to it. Do not guess what it stands for.]' % (key, seen))
        text = ' '.join(lines)
        if len(text) > NOTE_CHARS:
            text = text[:NOTE_CHARS - 2].rsplit(' ', 1)[0] + ' …]'
        return {'lines': lines, 'text': text, 'onset': self.onset(), 'segments': len(segs),
                'current': {k: cur[k] for k in ('start', 'end', 'frames', 'change')}}
