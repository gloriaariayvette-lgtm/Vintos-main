#!/usr/bin/env python3
"""Camera mamepa: carried state, forecaster mixture, segments, the adaptive view, the summary and tag lookup.
Synthetic vectors and synthetic tag records only; no camera, frame, memory or model is used."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

repo = Path(__file__).resolve().parents[2]
scratch = tempfile.TemporaryDirectory()
os.environ['HOME'] = scratch.name
os.environ['SPARK_WORKSPACE'] = str(Path(scratch.name) / 'workspace')
sys.path.insert(0, str(repo / 'studio'))
sys.path.insert(0, str(repo / 'scripts'))
import camera_mamepa as cm
from camera_mamepa import CallableTagStore, DictTagStore, Mamepa, Model
from native_sensory_tap import SensoryTap
from native_video_runtime import LiveSession
from native_video_server import VideoService


def check(label, condition):
    assert condition, label
    print('ok - ' + label)


tmp = Path(scratch.name)
DIM, DZ = 48, 16
rng = np.random.default_rng(5)


def ckpt(name, err_scale=.05, trained=False, mu=None, **extra):
    arrays, meta = cm.untrained(DIM, DZ, seed=3)
    if mu is not None:
        arrays['mu'] = mu.astype(np.float32)
    meta.update(err_scale=err_scale, **extra.pop('meta', {}))
    if trained:
        S = 4
        arrays.update(Wd=rng.normal(0, .05, (DZ, DZ)), bd=np.full(DZ, -1.), A_log=np.log(np.tile(np.arange(1, S + 1.), (DZ, 1))),
                      WB=rng.normal(0, .2, (DZ, S)), WC=rng.normal(0, .2, (DZ, S)), Dskip=np.ones(DZ),
                      Wo=rng.normal(0, .01, (3, DZ, DZ)))
        meta.update(trained=True, horizons=[1, 2, 4])
    arrays.update(extra)
    path = tmp / name
    return path, cm.save(path, {k: np.asarray(v, np.float32) for k, v in arrays.items()}, meta)


# ---- checkpoint conventions (versioned schema, sha256 identity, refusal of anything else)
path, cid = ckpt('plain.npz')
model = Model(path)
check('a checkpoint is identified by the sha256 of its file', model.checkpoint_id == cid and len(cid) == 64)
check('without learned weights there is no SSM forecaster', not model.trained
      and 'ssm' not in Mamepa(model).experts and Mamepa(model).experts[0] == 'persist')
np.savez(tmp / 'bad-schema.npz', meta=json.dumps({'schema': 'present-moment-v1', 'space': cm.SPACE}),
         mu=np.zeros(DIM), P=np.zeros((DIM, DZ)))
np.savez(tmp / 'bad-space.npz', meta=json.dumps({'schema': cm.SCHEMA, 'space': 'aeon-12b/audio-proj'}),
         mu=np.zeros(DIM), P=np.zeros((DIM, DZ)))
bad_p = np.zeros((DIM, DZ)); bad_p[0, 0] = np.nan
np.savez(tmp / 'bad-value.npz', meta=json.dumps({'schema': cm.SCHEMA, 'space': cm.SPACE}), mu=np.zeros(DIM), P=bad_p)
for bad in ['bad-schema.npz', 'bad-space.npz', 'bad-value.npz']:
    try:
        Model(tmp / bad); raise AssertionError(bad + ' accepted')
    except ValueError:
        pass
check('another schema, another vector space (audio) or a non-finite weight is refused', True)

tpath, _ = ckpt('trained.npz', trained=True)
tm = Model(tpath)
h, pred = tm.ssm_step(np.zeros((DZ, tm.S), np.float32), np.ones(DZ, np.float32), .5)
h2, _ = tm.ssm_step(np.zeros((DZ, tm.S), np.float32), np.ones(DZ, np.float32), 1e9)
check('the selective step forecasts every horizon and stays finite for any elapsed time',
      pred.shape == (3, DZ) and np.isfinite(pred).all() and np.isfinite(h2).all() and 'ssm' in Mamepa(tm).experts)


# ---- forecaster mixture: online weights follow each forecaster's recently realized error
def vec(z):
    """A frame vector whose projection is (close to) ``z``; unit-norm handled by the model."""
    return np.asarray(z, np.float32) @ np.linalg.pinv(model.a['P'])


m = Mamepa(model)
m.new_stream('s1', 0.)
base = rng.normal(size=DIM).astype(np.float32); base /= np.linalg.norm(base)
step = rng.normal(size=DIM).astype(np.float32); step *= .01 / np.linalg.norm(step)
for k in range(12):   # a steady drift: continuing the last change beats holding still
    r = m.frame(base + k * step, at=k * .5)
w = dict(zip(m.experts, m.weights().mean(1)))
check('weights move to the forecaster that has been right (drift beats persistence on a steady change)',
      w['drift'] > w['persist'] and abs(sum(w.values()) - 1) < 1e-5 and 'weights' in r and r['error'] >= 0)

# ---- segments: a run of different stills, then one continuous scene; the onset is where it began
seg = Mamepa(model)
seg.new_stream('s2', 0.)
stills = [rng.normal(size=DIM).astype(np.float32) for _ in range(20)]
for k, v in enumerate(stills):
    seg.frame(v, at=k * .5)
clip = rng.normal(size=DIM).astype(np.float32)
for k in range(4):
    out = seg.frame(clip + k * step * 3, at=10 + k * .5)
summary = seg.summary()
check('the present happening is found: the view starts where the continuous scene began',
      seg.onset() == 10.0 and summary['current']['frames'] == 4 and summary['onset'] == 10.0)
check('the summary is compact and factual about timing, names nothing',
      'began at 00:10' in summary['text'] and '20 brief scene(s)' in summary['text']
      and len(summary['text']) <= cm.NOTE_CHARS and 'square' not in summary['text'])
one = Mamepa(model); one.new_stream('s3', 0.)
for k, v in enumerate(stills[:3]):
    one.frame(v, at=k)
check('an adaptive view never shows fewer than two frames', one.onset() == 1.0 and one.onset(min_frames=1) == 2.0)
check('before any frame there is no onset and no summary', Mamepa(model).onset() is None and Mamepa(model).summary()['lines'] == [])

# ---- time: a long gap never invents carry; duplicates are ingested once
gap = Mamepa(model); gap.new_stream('g', 0.)
gap.frame(base, at=0.)
far = gap.frame(base, at=1e9)
check('an elapsed step is clamped (no overflow, no invented carry)', far is not None and np.isfinite(gap.levels).all()
      and np.isfinite(gap.L).all())
check('an event key is ingested once', gap.frame(base, at=2., key=('g', 1)) is not None and gap.frame(base, at=3., key=('g', 1)) is None)
for i in range(cm.MAX_SEEN + 5):
    gap._mark_seen(('x', i))
check('the ingestion record is bounded', len(gap.seen) == cm.MAX_SEEN == len(gap._seen))

# ---- state dump: bound to its checkpoint, and resumes exactly
a = Mamepa(tm); a.new_stream('d', 0.)
for k in range(5):
    a.frame(stills[k], at=k * .5)
payload = json.loads(json.dumps(a.dump()))
b = Mamepa(tm, payload=payload)
ra, rb = a.frame(clip, at=3.), b.frame(clip, at=3.)
check('a dumped state resumes to the same forecast, weights and segment',
      abs(ra['error'] - rb['error']) < 1e-6 and ra['weights'] == rb['weights'] and ra['segment_start'] == rb['segment_start'])
try:
    Mamepa(model, payload=payload); raise AssertionError('state loaded into another checkpoint')
except ValueError:
    pass
check('a state is refused by any other checkpoint', True)

# ---- tags are keys: direct lookup in a pluggable store (synthetic records only)
store = DictTagStore({'tag36h11:7': [{'id': 'syn-1', 'text': 'synthetic record: the blue test card'}],
                      'tag36h11:3': {'id': 'syn-2', 'text': 'synthetic record two'}})
tg = Mamepa(model, store); tg.new_stream('t1', 0.)
tg.frame(clip, at=0.)
hit = tg.tag(0., {'family': 'tag36h11', 'tag_id': 7})
miss = tg.tag(.5, {'family': 'tag36h11', 'tag_id': 11})
text = tg.summary()['text']
check('a seen tag retrieves exactly its linked records', hit['records'] == [{'id': 'syn-1', 'text': 'synthetic record: the blue test card'}]
      and hit['previous'] == [])
check('an unlinked tag is said plainly, never guessed', miss['records'] == [] and 'tag36h11:11 in view - no record is linked' in text
      and 'the blue test card' in text)
tg.new_stream('t2', 30.)
tg.frame(clip, at=0.)
again = tg.tag(1., {'family': 'tag36h11', 'tag_id': 7})
check('a later sighting recalls when the tag was seen before', len(again['previous']) == 1 and again['previous'][0]['stream'] == 't1'
      and 'seen before, in an earlier stream' in tg.summary()['text'])
calls = []
flaky = Mamepa(model, CallableTagStore(lambda key: calls.append(key) or 1 / 0)); flaky.new_stream('f', 0.)
flaky.frame(clip, at=0.)
check('a failing store reads as no record, and is asked once per key per stream',
      flaky.tag(0, {'family': 'tag36h11', 'tag_id': 1})['records'] == [] and flaky.tag(1, {'family': 'tag36h11', 'tag_id': 1}) is not None
      and calls == ['tag36h11:1'])
check('records are never written back to the store', store.lookup('tag36h11:7') == [{'id': 'syn-1', 'text': 'synthetic record: the blue test card'}])

# ---- sensory tap events: frames in the vision space, audio never mixed in
tap = SensoryTap(clock=lambda: 100.)
tap.start('replay')
tap.embedding('frame', 0., stills[0][None, None, :], 'r0')
tap.embedding('audio', .2, np.ones((1, 3, DIM)), 'a0')
tap.embedding('frame', .5, stills[1][None, None, :], 'r1')
tap.tag(.5, {'tag_id': 3, 'family': 'tag36h11', 'decision_margin': 50.})
fed = Mamepa(model, store)
out = fed.feed(tap.since(0)['events'])
check('tap frames and tags are consumed; audio stays out of this state', fed.frames == 2 and len(out) == 3
      and out[-1]['records'][0]['id'] == 'syn-2' and fed.stream == tap.stream)
check('re-reading the same tap page ingests nothing twice', fed.feed(tap.since(0)['events']) == [None, None, None] and fed.frames == 2)
bad = dict(tap.since(0)['events'][0], space='aeon-12b/audio-proj', seq=99)
try:
    fed.feed([bad]); raise AssertionError('foreign space mixed')
except ValueError:
    pass
check('a frame vector from another space is refused', True)


# ---- the video prompt: the summary as a note and the onset as the view, rolled back with the answer
class Tok:
    boi_token, eoi_token, boa_token, eoa_token = '<I', 'I>', '<A', 'A>'
    def apply_chat_template(self, messages, **kwargs): return '<user>' + messages[0]['content'] + '<end>'
    def encode(self, text, **kwargs): return [ord(c) % 50 + 1 for c in text]
    def decode(self, tokens, **kwargs): return 'a' * len(tokens)


class Mind:
    sha = 'test'
    eos = {0}
    suppress = []
    tokenizer = Tok()


OFFSET = 1000.
DIR = rng.normal(size=DIM).astype(np.float32)


class Backend:
    """Images carry a DIM-wide vector that depends on the frame colour (vision values stay >= 1000)."""
    def __init__(self): self.calls, self.hidden = [], None
    def new_cache(self): return []
    def numpy(self, x): return np.asarray(x, np.float32)
    def text(self, ids): return np.array(ids, dtype=np.float32).reshape(1, -1, 1).repeat(DIM, 2)
    def image(self, rgb, soft_tokens=70):
        v = OFFSET + np.cos(DIR * (1 + float(rgb.mean()))) * 5
        return np.tile(v[None, None, :], (1, 4, 1)).astype(np.float32)
    def forward(self, embeds, cache, vision=False):
        self.calls.append((embeds[0, :, 0].tolist(), vision, self.hidden))
        cache.extend(embeds[0, :, 0].tolist())
        return np.array([1., 0.]) if len([c for c in self.calls[-3:] if len(c[0]) == 1]) >= 2 else np.array([0., 1.])
    def length(self, cache): return len(cache)
    def keep(self, cache, index): cache[:] = [cache[i] for i in index]
    def truncate(self, cache, length): del cache[length:]


def qcall(calls):
    """The question chunk (the closing tag of the last frame, two tokens, may be committed first)."""
    return next(c for c in calls if len(c[0]) > 2)


mind, be = Mind(), Backend()
s = LiveSession(mind, be, clock=lambda: 0.)
for k in range(6):
    s.frame(np.full((48, 64, 3), k * 20, np.uint8), at=k)
s.ask('warm', max_tokens=1)   # commits the pending close of the last frame
be.calls = []
before = list(s.cache)
ans = s.ask('which way?', max_tokens=3, view_from=3.5, note='[CAMERA MEMORY: test note]')
q_tokens = qcall(be.calls)[0]
hidden_old = set(int(p) for p in s.positions[np.isin(s.owner, [0, 1, 2, 3])])
check('the note is placed before the question', q_tokens[:len(Tok().encode(' [CAMERA MEMORY: test note]'))]
      == [float(t) for t in Tok().encode(' [CAMERA MEMORY: test note]')])
check('frames before the onset are masked for the answer only, and everything is rolled back',
      all(c[2] == hidden_old for c in be.calls) and s.cache == before
      and len(s.window()) == 6 and be.hidden is None)
be.calls = []
s.ask('which way?', max_tokens=2, view_from=99.)
newest = [i for i, x in s.segments.items() if x['kind'] == 'frame'][-1]
check('the view never hides the newest frame', not (qcall(be.calls)[2] & set(int(p) for p in s.positions[s.owner == newest])))
be.calls = []
s.ask('which way?', max_tokens=2)
check('without a view or note the answer path is unchanged', qcall(be.calls)[2] is None
      and qcall(be.calls)[0] == [float(t) for t in Tok().encode(' which way?<end>')])
try:
    s.ask('q', note='x' * 700); raise AssertionError('oversized note accepted')
except ValueError:
    pass
check('the note counts against the reserved answer budget', True)

# ---- the service feeds the mamepa in process and uses it only when asked
from PIL import Image
mu = np.full(DIM, OFFSET, np.float32); mu /= np.linalg.norm(mu)
spath, _ = ckpt('service.npz', err_scale=1e-4, mu=mu)
mam = Mamepa(Model(spath), DictTagStore({}))
svc = VideoService(mind, Backend(), SensoryTap(), None, mam)
sid = svc.dispatch('/video/start', {'feed': 'replay'})['session_id']


def png(v):
    buf = io.BytesIO(); Image.fromarray(np.full((48, 64, 3), v, np.uint8)).save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


receipts = [svc.dispatch('/video/frame', {'session_id': sid, 'at': k * .5, 'image': png(40 * k)}) for k in range(5)]
check('every frame reaches the mamepa on the inference thread, with its cost on the receipt',
      mam.frames == 5 and all('mamepa_seconds' in r for r in receipts) and mam.stream == svc.tap.stream)
svc.stream.calls = []
svc.dispatch('/video/ask', {'session_id': sid, 'question': 'q', 'max_tokens': 2})
check('by default the answer path is untouched', qcall(svc.stream.calls)[2] is None
      and qcall(svc.stream.calls)[0] == [float(t) for t in Tok().encode(' q<end>')])
svc.stream.calls = []
svc.dispatch('/video/ask', {'session_id': sid, 'question': 'q', 'max_tokens': 2, 'recall': True})
note = mam.summary()['text']
check('with recall the summary is the note and the onset is the view',
      qcall(svc.stream.calls)[0][:len(note)] == [float(t) for t in Tok().encode(' ' + note)][:len(note)]
      and (qcall(svc.stream.calls)[2] is not None) == (mam.onset() > 0))
check('the summary is readable on the inference thread', svc.dispatch_read(mam.summary)['segments'] >= 1)
svc.dispatch('/video/abort', {'session_id': sid})
check('nothing was written outside the scratch checkpoints', sorted(p.name for p in tmp.iterdir() if p.is_file())
      == sorted(['plain.npz', 'trained.npz', 'service.npz', 'bad-schema.npz', 'bad-space.npz', 'bad-value.npz']))

# ---- earlier-scene recall: kept tokens of a scene that has left the window are shown again for the question
rc = Mamepa(model); rc.new_stream('r', 0.)
for k in range(4):
    rc.frame(clip + k * step * 3, at=k * .5, tokens=('A', k))
other = rng.normal(size=DIM).astype(np.float32)
for k in range(16):
    rc.frame(other + k * step * 3, at=2 + k * .5, tokens=('B', k))
got = rc.recall()
check('recall returns the most recent earlier scene, not the current one, with a note saying so',
      [f[1] for f in got['frames']] == [('A', 0), ('A', 1), ('A', 2), ('A', 3)] and got['segment']['frames'] == 4
      and 'earlier scene' in got['note'] and 'current scene began at 00:02' in got['note'])
check('kept frames are thinned per scene and bounded overall', len([k for k in rc.kept if k['tokens'][0] == 'B']) <= cm.KEEP_PER_SEGMENT
      and len(rc.kept) <= cm.MAX_KEPT and ('B', 0) in [k['tokens'] for k in rc.kept])
check('kept tokens are never dumped', 'kept' not in rc.dump() and 'tokens' not in json.dumps(rc.dump()))
lone = Mamepa(model); lone.new_stream('l', 0.)
for k in range(3):
    lone.frame(clip + k * step * 3, at=k, tokens=k)
check('with no earlier scene there is nothing to recall', lone.recall() is None)

be.calls = []
before = list(s.cache)
emb = be.image(np.full((48, 64, 3), 7, np.uint8))
s.ask('which way?', max_tokens=2, note='[RECALL]', recall_frames=[(0., emb), (.5, emb)])
vis = [c for c in be.calls if c[1]]
check('recalled frames are shown as stamped image spans before the note, then rolled back',
      len(vis) == 2 and max(i for i, c in enumerate(be.calls) if c[1]) < next(i for i, c in enumerate(be.calls)
      if c[0][:3] == [float(t) for t in Tok().encode(" [R")])
      and s.cache == before and len(s.window()) == 6)
try:
    s.ask('q', recall_frames=[(0., np.zeros((1, 9000, DIM), np.float32))]); raise AssertionError('oversized recall accepted')
except ValueError:
    pass
check('recalled frames count against the 8192 context budget', True)

mam2 = Mamepa(Model(spath)); svc2 = VideoService(mind, Backend(), None, None, mam2)
sid2 = svc2.dispatch('/video/start', {})['session_id']
for k in range(4):
    svc2.dispatch('/video/frame', {'session_id': sid2, 'at': k * .5, 'image': png(200)})
for k in range(4):
    svc2.dispatch('/video/frame', {'session_id': sid2, 'at': 2 + k * .5, 'image': png(10 + 30 * k)})
check('the service keeps each frame\'s projected tokens for recall', len(mam2.kept) == 8)
svc2.stream.calls = []
svc2.dispatch('/video/ask', {'session_id': sid2, 'question': 'q', 'max_tokens': 2, 'recall_earlier': True})
earlier = mam2.recall()
check('recall_earlier shows the earlier scene again when there is one',
      earlier is None or sum(1 for c in svc2.stream.calls if c[1]) == len(earlier['frames']))
svc2.dispatch('/video/abort', {'session_id': sid2})
print('all camera mamepa checks passed')
