#!/usr/bin/env python3
"""Live frame timeline, cross-window eviction, rollback, sampling and provenance, with a synthetic backend only."""
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
os.environ.pop('VINTOS_NATIVE_VIDEO_BASE', None)
sys.path.insert(0, str(repo / 'studio'))
sys.path.insert(0, str(repo / 'scripts'))
import native_video_runtime as runtime
from native_video_runtime import LiveSession, PositionedKV, stamp, stream_masks
from native_video_server import VideoService, pcm16
import native_video as client
import native_video_sources as sources
from record_gaps import VIDEO_GAP_RULE


def check(label, condition):
    assert condition, label
    print('ok - ' + label)


class Tokenizer:
    boi_token, eoi_token, boa_token, eoa_token = '<I', 'I>', '<A', 'A>'
    def apply_chat_template(self, messages, **kwargs):
        return '<user>' + messages[0]['content'] + '<end>'
    def encode(self, text, **kwargs):
        return [ord(c) % 50 + 1 for c in text]
    def decode(self, tokens, **kwargs):
        return 'a' * len(tokens)


class Backend:
    """Cache = list of token values; logits favour token 1, then EOS (0) after two generated tokens."""
    def new_cache(self): return []
    def text(self, ids): return np.array(ids, dtype=np.float32).reshape(1, -1, 1)
    def audio(self, frames): return np.full((1, len(frames), 1), 500., dtype=np.float32)
    def image(self, rgb, soft_tokens=70): return np.full((1, 4 * soft_tokens // 70, 1), 1000. + rgb.mean(), dtype=np.float32)
    def forward(self, embeds, cache, vision=False):
        values = embeds[0, :, 0].tolist()
        if vision:
            assert all(v >= 1000 for v in values)
        cache.extend(values)
        self.threads = getattr(self, 'threads', set()) | {__import__('threading').current_thread().name}
        self.generated = getattr(self, 'generated', 0) + 1 if len(values) == 1 else 0
        return np.array([0., 1.]) if self.generated < 2 else np.array([1., 0.])
    def length(self, cache): return len(cache)
    def keep(self, cache, index): cache[:] = [cache[i] for i in index]
    def truncate(self, cache, length): del cache[length:]


class Mind:
    sha = client.ANCHOR_SHA256
    eos = {0}
    suppress = []
    tokenizer = Tokenizer()


mind, backend = Mind(), Backend()
frame = lambda v: np.full((48, 64, 3), v, dtype=np.uint8)
session = LiveSession(mind, backend, retain_frames=3, clock=lambda: 0.)
prefix = list(session.cache)
receipts = [session.frame(frame(i * 10), at=i * .5) for i in range(5)]
check('frames enter as stamped native image spans', receipts[0]['visual_tokens'] == 4
      and session.segments[receipts[-1]['segment']]['stamp'] == stamp(2.0))
check('the open-turn prefix is never evicted', session.cache[:len(prefix)] == prefix)
check('only the newest frames stay in the window', [s['segment'] for s in session.window()] == [2, 3, 4]
      and receipts[3]['evicted_segments'] == [0] and session.evicted_frames == 2)
check('evicted frame tokens leave the cache and owners stay aligned',
      len(session.owner) == len(session.cache) and sum(1 for v in session.cache if v >= 1000) == 12)
before = list(session.cache)
answer = session.ask('what moved?', max_tokens=4)
check('a question is answered from the window', answer['text'] == 'aa' and answer['finish_reason'] == 'stop'
      and answer['frames_seen'] == 5 and len(answer['window']) == 3)
check('question and answer are rolled back so the stream continues', session.cache == before + Tokenizer().encode('I>')
      and len(session.owner) == len(session.cache))
check('the closing image boundary stays with its own frame', session.owner[len(before)] == 4)
session.frame(frame(99), at=3.0)
check('the stream continues after an answer', [s['segment'] for s in session.window()] == [3, 4, 5]
      and 4 in session.owner and 2 not in session.owner)

audio = LiveSession(mind, backend, retain_frames=2, retain_audio_tokens=100, clock=lambda: 0.)
audio.frame(frame(1), at=0)
r = audio.audio(np.zeros(16000 * 3, dtype=np.float32), at=.5)
check('audio shares the timeline in two-second spans', r['audio_tokens'] == 75 and
      [s['kind'] for s in audio.window()] == ['frame', 'audio', 'audio'])
audio.audio(np.zeros(16000 * 4, dtype=np.float32), at=3.5)
audio.frame(frame(2), at=8)
kinds = [s['kind'] for s in audio.window()]
spans = [s for s in audio.window() if s['kind'] == 'audio']
check('audio beyond its window is evicted oldest first', sum(s['audio_tokens'] for s in spans) <= 100 + runtime.AUDIO_SPAN_TOKENS
      and kinds.count('frame') == 2 and all(s['audio_ref'].startswith('sha256:') for s in spans))
for bad in [np.full((10, 10, 3), 1, np.uint8), np.zeros((40, 40), np.uint8), np.zeros((40, 40, 3), np.float32)]:
    try:
        audio.frame(bad); raise AssertionError('invalid frame accepted')
    except ValueError:
        pass
try:
    audio.frame(frame(3), soft_tokens=99); raise AssertionError('unsupported visual budget accepted')
except ValueError:
    pass
check('invalid frames never touch the cache', len(audio.owner) == len(audio.cache))
try:
    LiveSession(mind, backend, instruction=runtime.STREAM_MARKER); raise AssertionError('marker accepted')
except ValueError:
    pass
check('the stream placeholder is reserved', True)
big = LiveSession(mind, backend, retain_frames=64, clock=lambda: 0.)
try:
    big._forward(np.zeros((1, runtime.CONTEXT, 1), np.float32), 0); raise AssertionError('context overflow accepted')
except ValueError:
    pass
check('the answer reserve keeps the 8192 context bound', True)


class FakeMx:
    array = staticmethod(np.asarray)
    concatenate = staticmethod(np.concatenate)
    @staticmethod
    def take(x, i, axis): return np.take(x, i, axis=axis)


def layer(kind):
    return type('L', (), {'layer_type': kind})()


kv = PositionedKV(FakeMx())
kv.update_and_fetch(np.zeros((1, 1, 5, 2)), np.zeros((1, 1, 5, 2)))
kv.keep([0, 1, 4])
check('eviction keeps absolute positions and the RoPE offset', list(kv.positions) == [0, 1, 4] and kv.offset == 5)
full, local = stream_masks([layer('full_attention'), layer('sliding_attention')], [kv, kv], 3, 3, False, mx=FakeMx())
check('masks are causal over absolute positions', full.shape == (3, 6) and full[0].tolist() == [1, 1, 1, 1, 0, 0])
check('sliding layers keep their window over positions, not storage', local[2].tolist() == [0, 0, 0, 1, 1, 1]
      and local[0].tolist() == [0, 0, 1, 1, 0, 0])
full, _ = stream_masks([layer('full_attention'), layer('sliding_attention')], [kv, kv], 3, 3, True, mx=FakeMx())
check('one image chunk attends bidirectionally inside itself only', full.all())
masked, _ = stream_masks([layer('full_attention'), layer('sliding_attention')], [kv, kv], 2, 99, False, {4}, FakeMx())
check('the masking reference hides exactly the requested positions', masked[:, 2].sum() == 0 and masked[:, :2].all())
kv.truncate(2)
check('rollback restores the next position after the kept tail', kv.offset == 2 and list(kv.positions) == [0, 1])

backend.threads = set()
service = VideoService(mind, backend)
start = service.dispatch('/video/start', {'retain_frames': 2})
try:
    service.dispatch('/video/start', {}); raise AssertionError('overlapping session accepted')
except BlockingIOError:
    pass
check('one stream owns the inference cache', service.active[0] == start['session_id'])
from PIL import Image
png = io.BytesIO(); Image.fromarray(frame(7)).save(png, format='PNG')
receipt = service.dispatch('/video/frame', {'session_id': start['session_id'], 'at': 0,
                                            'image': base64.b64encode(png.getvalue()).decode()})
check('frames are decoded in memory and never retained', receipt['raw_frames_retained'] is False
      and receipt['frame_ref'].startswith('sha256:') and not any(Path(scratch.name).iterdir()))
for bad in [{'image': base64.b64encode(b'GIF89a').decode()}, {'image': 'bad!'}]:
    try:
        service.dispatch('/video/frame', dict(bad, session_id=start['session_id'])); raise AssertionError('bad frame')
    except ValueError:
        pass
check('non-JPEG/PNG and malformed frames are refused', True)
service.dispatch('/video/audio', {'session_id': start['session_id'], 'audio': base64.b64encode(b'\0\0' * 3200).decode()})
asked = service.dispatch('/video/ask', {'session_id': start['session_id'], 'question': 'what?', 'max_tokens': 4})
check('the service answers with checkpoint and window provenance', asked['native_video'] and asked['window'])
done = service.dispatch('/video/finish', {'session_id': start['session_id']})
check('finish clears the session', service.active is None and done['raw_frames_retained'] is False)
import threading
errors = []
def request(path, body):
    try:
        service.dispatch(path, body)
    except Exception as exc:
        errors.append(exc)
again = service.dispatch('/video/start', {})
for path, body in [('/video/frame', {'image': base64.b64encode(png.getvalue()).decode()}),
                   ('/video/audio', {'audio': base64.b64encode(b'\0\0' * 3200).decode()}),
                   ('/video/ask', {'question': 'now?', 'max_tokens': 2}), ('/video/abort', {})]:
    t = threading.Thread(target=request, args=(path, dict(body, session_id=again['session_id']))); t.start(); t.join()
check('every model call runs on the one inference thread, whatever thread the request came on',
      not errors and backend.threads == {'native-video-inference'})
try:
    service.dispatch('/video/frame', {'session_id': 'nope', 'image': ''}); raise AssertionError('unknown session')
except ValueError:
    pass
check('errors raised on the inference thread reach the caller unchanged', True)

from native_video_runtime import resize_like_hf
const = np.full((192, 192, 3), 77, np.uint8)
same = frame(5)
check('the reference resize keeps a flat image flat and leaves same-size frames untouched',
      (resize_like_hf(const, 384, 384) == 77).all() and resize_like_hf(same, 48, 64) is same)
ramp = np.tile(np.linspace(0, 255, 192).astype(np.uint8)[None, :, None], (192, 1, 3))
check('the reference resize is the antialiased bicubic kernel (PIL native code)',
      (resize_like_hf(ramp, 384, 432) == np.asarray(Image.fromarray(ramp).resize((432, 384), Image.BICUBIC))).all())

# Window-boundary eviction: a frame outside the local window leaves the global layers too.
class Narrow(Backend):
    window = 40
narrow = LiveSession(mind, Narrow(), retain_frames=64, clock=lambda: 0.)
for i in range(12):
    narrow.frame(frame(i * 9), at=i)
kept = [s for s in narrow.window() if s['kind'] == 'frame']
check('frames that slid out of the local window are evicted even under a large frame cap',
      len(kept) < 12 and all(s['end_pos'] >= narrow.next_pos - 40 for s in kept) and narrow.evicted_frames == 12 - len(kept))
q_before = narrow.next_pos
narrow.ask('still there?', max_tokens=2)
check('a rolled-back question does not move the window', narrow.next_pos == q_before + len(Tokenizer().encode('I>')))

# Audio enters in 400 ms steps; a frame or question flushes what is waiting.
held = LiveSession(mind, Backend(), clock=lambda: 0.)
r = held.audio(np.zeros(3200, np.float32), at=0)
check('a 200 ms packet waits for the 400 ms step', r['audio_tokens'] == 0 and r['pending_samples'] == 3200)
held.audio(np.zeros(3200, np.float32), at=.2)
check('two packets enter the mind together', held.audio_tokens == 10 and held.audio_tail.size == 0)
held.audio(np.zeros(1000, np.float32), at=.4)
held.frame(frame(3), at=.5)
check('a frame flushes the waiting audio first, padded to whole tokens', held.audio_tokens == 12)

# The sampler triggers on the largest block change, so a small moving object counts.
t = [0.]
small = client.AdaptiveSampler(idle_fps=.5, burst_fps=2, change=.04, clock=lambda: t[0])
scene_a = np.full((480, 640, 3), 60, np.uint8)
scene_b = scene_a.copy(); scene_b[100:140, 300:340] = (230, 40, 40)
small.offer(scene_a); t[0] = .6
check('a 40-pixel object moving on a 640x480 scene triggers a burst', small.offer(scene_b) == 'change')
try:
    pcm16(base64.b64encode(b'\0').decode()); raise AssertionError('odd PCM accepted')
except ValueError:
    pass
check('malformed audio packets are refused', True)

# Interleaving: an answer is decoded token by token; arrivals in between are taken in, held, then committed.
import threading as _threading
import time as _time


class Slow(Backend):
    """Never reaches EOS, and each single-token step takes a moment, like a real decode. Each step favours a
    different token, so the answer never trips the repetition guard."""
    def forward(self, embeds, cache, vision=False):
        self.hidden_seen = getattr(self, 'hidden_seen', []) + [getattr(self, 'hidden', None)]
        out = Backend.forward(self, embeds, cache, vision)
        if embeds.shape[1] == 1:
            _time.sleep(.01)
        scores = np.zeros(4096)
        scores[1 + len(cache) % 4000] = 1.
        return scores


slow = Slow()
svc = VideoService(mind, slow)
sid = svc.dispatch('/video/start', {})['session_id']
svc.dispatch('/video/frame', {'session_id': sid, 'at': 0, 'image': base64.b64encode(png.getvalue()).decode()})
answer, receipts_during = {}, []
asker = _threading.Thread(target=lambda: answer.update(svc.dispatch('/video/ask', {'session_id': sid, 'question': 'q', 'max_tokens': 500})))
asker.start(); _time.sleep(.05)
for k in range(3):
    started = _time.perf_counter()
    r = svc.dispatch('/video/frame', {'session_id': sid, 'at': 1 + k, 'image': base64.b64encode(png.getvalue()).decode()})
    receipts_during.append((r, _time.perf_counter() - started))
r = svc.dispatch('/video/audio', {'session_id': sid, 'at': 4, 'audio': base64.b64encode(b'\0\0' * 6400).decode()})
asker.join()
check('frames and audio that arrive mid-answer are taken in between tokens, not after the answer',
      all(x[0].get('deferred') for x in receipts_during) and r.get('deferred') and all(x[1] < .2 for x in receipts_during))
check('the live answer is capped and everything that arrived is committed after it',
      len(answer['tokens']) == runtime.LIVE_ANSWER_TOKENS and answer['deferred_committed'] == 4
      and [s['kind'] for s in svc.active[1].window()].count('frame') == 4)
try:
    svc.dispatch('/video/ask', {'session_id': sid, 'question': 'again', 'max_tokens': 2})
    check('a second question after the first is answered normally', True)
finally:
    svc.dispatch('/video/abort', {'session_id': sid})

# Recent-seconds: older frames are masked for the question and answer only.
rs = LiveSession(mind, Slow(), clock=lambda: 0.)
for k in range(6):
    rs.frame(frame(k * 30), at=k)
rs.stream.hidden_seen = []
rs.ask('which way?', max_tokens=2, recent_seconds=1.5)
old_positions = set(int(p) for p in rs.positions[np.isin(rs.owner, [0, 1, 2, 3])])
check('only frames from the last N seconds are visible to the answer',
      rs.stream.hidden_seen[0] is None and all(h == old_positions for h in rs.stream.hidden_seen[1:])
      and rs.stream.hidden is None and len(rs.window()) == 6)

# Scene markers: a frame that differs from the last on most of the image is marked.
sm = LiveSession(mind, Backend(), scene_markers=True, clock=lambda: 0.)
r1 = sm.frame(frame(10), at=0); r2 = sm.frame(frame(12), at=.5); r3 = sm.frame(frame(200), at=1)
check('a new scene is marked in the timeline, a small change is not', not r1['scene_change'] and not r2['scene_change']
      and r3['scene_change'] and sm.segments[r3['segment']].get('scene_change'))

t = [0.]
sampler = client.AdaptiveSampler(idle_fps=.5, burst_fps=2, change=.04, tokens_per_second=144, clock=lambda: t[0])
still, moved = frame(50), frame(200)
decisions = []
for i in range(40):
    t[0] = i * .1
    decisions.append(sampler.offer(moved if (i // 5) % 2 and i >= 20 else still))
check('still scenes are sampled at the idle rate', decisions[:20].count('first') == 1 and decisions[:20].count('idle') == 0
      and decisions[:20].count(None) == 19)
check('changes trigger bursts within the burst rate', decisions[20:].count('change') >= 3
      and all(d is None for d in decisions[21:25]))
greedy = client.AdaptiveSampler(idle_fps=8, burst_fps=8, change=.5, tokens_per_second=72, clock=lambda: t[0])
sent = 0
for i in range(100):
    t[0] = 10 + i * .125
    sent += greedy.offer(still) is not None
check('the token budget per second caps the frame rate', sent <= 2 + 13)

record = client.window_record(asked['window'], [dict(receipt, source_hash='sha256:abc', source='door')])
check('provenance carries keyframe ref, source hash and the gap rule', record['keyframe_ref'] == receipt['frame_ref']
      and record['source_hash'] == 'sha256:abc' and record['record_gap'] == VIDEO_GAP_RULE and not record['frames_kept'])
parts = client.senses_block(record, [b'\xff\xd8x\xff\xd9'])
check('the Senses block carries the frames themselves and one provenance line',
      parts[0]['type'] == 'image_url' and 'not captured' in parts[-1]['text'] and 'were not kept' in parts[-1]['text'])
for bad in ['http://10.0.0.2:8876', 'http://127.0.0.1:8840', 'https://127.0.0.1:8876', 'http://127.0.0.1:8876/x']:
    os.environ['VINTOS_NATIVE_VIDEO_BASE'] = bad
    try:
        client.base_url(); raise AssertionError('non-loopback route accepted')
    except ValueError:
        pass
os.environ.pop('VINTOS_NATIVE_VIDEO_BASE')
check('the route is loopback-only, explicit and disabled by default', not client.enabled())

jpeg = io.BytesIO(); Image.fromarray(frame(9)).save(jpeg, format='JPEG')
found, rest = sources.split_jpegs(b'--b\r\n' + jpeg.getvalue() + b'\r\n--b\r\n' + jpeg.getvalue()[:100])
check('MJPEG boundaries split complete JPEGs and keep the tail', len(found) == 1 and rest == jpeg.getvalue()[:100])
reads = iter([None, png.getvalue()])
door = list(sources.door_png_source(read=lambda: next(reads), sleep=lambda s: None, limit=2))
check('the door PNG adapter skips missing frames and never substitutes one', len(door) == 1 and door[0][0].shape == (48, 64, 3))
feed = sources.SnapshotFeed(maxsize=1)
feed.push_jpeg(jpeg.getvalue()); feed.push_jpeg(jpeg.getvalue())
check('snapshot feed keeps the newest frame when full', feed.dropped == 1 and len(list(feed.frames(timeout=.01))) == 1)
check('stream inputs cover RTSP, HTTP and local webcams through ffmpeg',
      '-rtsp_transport' in sources.ffmpeg_command('rtsp://cam/x') and 'avfoundation' in sources.ffmpeg_command('avfoundation:0'))
paced = list(sources.replay_source([frame(1)] * 3, 2, clock=lambda: 0., sleep=lambda s: None))
check('public replay yields frames with capture times', len(paced) == 3)

# Live latency: what arrived during an answer is committed one item per step, and later arrivals queue behind it.
held = LiveSession(mind, Slow(), clock=lambda: 0.)
held.frame(frame(1), at=0)
steps = held.ask_steps('q', max_tokens=3)
next(steps)
held.frame(frame(2), at=1); held.audio(np.zeros(6400, np.float32), at=1.2); held.frame(frame(3), at=1.4)
order = []
try:
    while True:
        next(steps)
        if held.deferred and not order:
            order.append('mid-flush')
            r = held.frame(frame(4), at=1.6)
            check('a frame arriving while held items are committed is encoded now and queued behind them',
                  r.get('deferred') and held.deferred[-1][0] == 'frame')
except StopIteration as done:
    flushed = done.value
check('held arrivals are committed one per step, in arrival order',
      order == ['mid-flush'] and flushed['deferred_committed'] == 4 and not held.deferred
      and [s['at'] for s in held.window() if s['kind'] == 'frame'] == [0., 1., 1.4, 1.6])
check('a direct ask still commits everything before it returns',
      LiveSession(mind, backend, clock=lambda: 0.).ask('q', max_tokens=2)['deferred_committed'] == 0)


class FakePost:
    """A loopback stand-in: an ask takes a moment, frames and audio return at once."""
    def __init__(self):
        self.paths, self.lock = [], threading.Lock()
    def __call__(self, url, body):
        path = url.split(':0', 1)[1]
        with self.lock:
            self.paths.append(path)
        if path == '/video/start':
            return {'session_id': 's'}
        if path == '/video/ask':
            _time.sleep(.2)
            return {'text': 'ok', 'checkpoint_sha256': client.ANCHOR_SHA256, 'native_video': True}
        return {'ingest_seconds': 0., 'frame_ref': 'sha256:x', 'at': body.get('at')}


now = [100.]
post = FakePost()
live = client.Stream(post=post, clock=lambda: now[0],
                     sampler=client.AdaptiveSampler(idle_fps=8, burst_fps=8, change=.5, tokens_per_second=2000))
pending = live.ask('what moved?', 8, wait=False)
sent_during = 0
for k in range(3):
    now[0] += .2
    sent_during += live.offer(frame(k), captured=now[0]) is not None
check('frames keep flowing while a question is being answered', sent_during == 3 and not pending.done())
try:
    live.ask('again?', wait=False); raise AssertionError('overlapping question accepted')
except BlockingIOError:
    pass
check('one question at a time on a stream', pending.result(5)['text'] == 'ok')
now[0] += 1
check('a frame that is already stale is dropped before the sampler, not queued',
      live.offer(frame(9), captured=now[0] - .5) is None and live.stale_dropped == 1 and live.sampler.skipped == 0)
check('a fresh frame after a stale one is sent', live.offer(frame(10), captured=now[0]) is not None)
check('a stream can keep every frame', client.Stream(post=FakePost(), max_lag=None).max_lag is None)
answers = []
src = [(frame(i), 200. + i * .1) for i in range(12)]
now[0] = 200.
def paced():
    for rgb, at in src:
        now[0] = at
        yield rgb, at
paths_before = len(post.paths)
sources.run(live, paced(), ask_every=.5, question='q', on_answer=answers.append)
check('the run loop asks on its own thread and still delivers every answer',
      answers and all(a['text'] == 'ok' for a in answers) and post.paths[paths_before:].count('/video/frame') >= 5)
live.finish()
check('no file was written during the stream', not any(Path(scratch.name).iterdir()))

# Sensory tap and AprilTags (fake detector; no frames or tags from any camera).
from native_sensory_tap import SensoryTap, decode_vector
from native_apriltags import TagDetector


class Det:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeTags:
    def detect(self, image, **kwargs):
        assert image.dtype == np.uint8 and image.ndim == 2
        good = Det(tag_id=7, tag_family=b'tag36h11', decision_margin=60., hamming=0, center=[10, 12],
                   corners=[[0, 0], [1, 0], [1, 1], [0, 1]])
        weak = Det(tag_id=8, tag_family=b'tag36h11', decision_margin=3., hamming=0, center=[1, 1], corners=[[0, 0]] * 4)
        flipped = Det(tag_id=9, tag_family=b'tag36h11', decision_margin=80., hamming=1, center=[1, 1], corners=[[0, 0]] * 4)
        return [good, weak, flipped]


clock = [100.]
tap = SensoryTap(max_events=5, clock=lambda: clock[0])
service = VideoService(mind, backend, tap, TagDetector(backend=FakeTags()))
start = service.dispatch('/video/start', {'feed': 'replay'})
clock[0] = 101.5
r = service.dispatch('/video/frame', {'session_id': start['session_id'], 'at': 1.0,
                                      'image': base64.b64encode(png.getvalue()).decode()})
check('tags are detected on the sampled frame; weak or bit-corrected reads are dropped',
      [t['tag_id'] for t in r['tags']] == [7] and r['tags'][0]['family'] == 'tag36h11' and r['tags'][0]['pose'] is None)
events = tap.since(0)['events']
check('the tap holds the projected frame embedding and the tag event, timestamped',
      [e['kind'] for e in events] == ['frame', 'tag'] and events[0]['space'] == 'aeon-12b/vision-proj'
      and events[0]['feed'] == 'replay' and events[0]['ref'] == r['frame_ref'] and events[1]['tag_id'] == 7
      and events[1]['ref'] == r['frame_ref'] and events[0]['dt'] is None and events[1]['dt'] == 0)
check('tap vectors decode to the pooled embedding width', decode_vector(events[0]).shape == (1,))
service.dispatch('/video/audio', {'session_id': start['session_id'], 'audio': base64.b64encode(b'\0\0' * 6400).decode()})
check('audio embeddings join the same tap in their own space',
      any(e['kind'] == 'audio' and e['space'] == 'aeon-12b/audio-proj' for e in tap.since(0)['events']))
for _ in range(4):
    service.dispatch('/video/frame', {'session_id': start['session_id'], 'image': base64.b64encode(png.getvalue()).decode()})
page = tap.since(0)
check('the ring is bounded and says how much it dropped', len(page['events']) == 5 and page['dropped'] > 0
      and page['oldest'] == page['events'][0]['seq'] and tap.since(page['next'])['events'] == [])
service.dispatch('/video/abort', {'session_id': start['session_id']})
absent = TagDetector()
absent.backend = None
check('detection is off, not faked, when the library is absent', not absent.available and absent.detect(frame(1)) == [])
try:
    TagDetector(backend=FakeTags(), intrinsics=(500, 500, 320, 240)); raise AssertionError('pose without tag size')
except ValueError:
    pass
check('pose needs intrinsics and the printed tag size', True)

memory_dir = Path(scratch.name) / 'workspace' / 'memory'
client.WORKSPACE = str(Path(scratch.name) / 'workspace')
client.TAG_MAP = str(memory_dir / 'apriltag-memories.json')
check('the tag map is created once with its how-to and never overwritten',
      client.init_tag_map() and not client.init_tag_map() and client.load_tag_map() == {})
(memory_dir / 'moments.jsonl').write_text(json.dumps({'id': 'm1', 'text': 'the first lantern'}) + '\n')
tag_map = {'tag36h11:7': {'store': 'moments.jsonl', 'id': 'm1', 'label': 'lantern'},
           'tag36h11:8': {'text': 'her words for this one'},
           'tag36h11:9': {'store': 'moments.jsonl', 'id': 'missing'},
           'tag36h11:10': {'store': '../../outside.json', 'id': 'x'}}
hits = {t: client.tag_memory({'family': 'tag36h11', 'tag_id': t}, tag_map) for t in (7, 8, 9, 10, 11)}
check('a tag returns exactly the memory record it is linked to', hits[7]['found'] and hits[7]['memory']['text'] == 'the first lantern'
      and hits[8]['memory'] == {'text': 'her words for this one'})
check('missing links and missing records are said plainly, never guessed', not hits[9]['found'] and 'not found' in hits[9]['note']
      and not hits[11]['found'] and 'no memory' in hits[11]['note'])
check('a store outside his memory folder is never read', not hits[10]['found'])
tags = client.window_tags([dict(r, at=1.0)])
parts = client.senses_block(record, [b'\xff\xd8x\xff\xd9'], tags, tag_map)
check('the Senses block puts the linked memory beside the frames',
      parts[0]['type'] == 'image_url' and 'the first lantern' in parts[1]['text'] and '(lantern)' in parts[1]['text']
      and 'were not kept' in parts[-1]['text'])
(memory_dir / 'moments.jsonl').unlink(); Path(client.TAG_MAP).unlink()

# The repetition guard: answers cannot loop on themselves; the first token (every one-word answer) is untouched.
from native_video_runtime import guard_repeats
base_scores = np.array([0., 3., 2., 1., -1.])
check('the first token of an answer is never changed', np.array_equal(guard_repeats(base_scores.copy(), []), base_scores))
g = guard_repeats(base_scores.copy(), [1, 4])
check('tokens already in the answer are penalised (positive divided, negative multiplied)',
      g[1] == 3. / runtime.REPEAT_PENALTY and g[4] == -1. * runtime.REPEAT_PENALTY and g[2] == 2.)
g = guard_repeats(base_scores.copy(), [1, 2, 3, 4, 1, 2, 3])
check('a token that would repeat a four-token run is ruled out', g[4] == -np.inf and np.isfinite(g[1]))


class Looper(Backend):
    """Greedy logits that would loop forever on tokens 1, 2, 3 ("the oration of the oration of ...")."""
    def forward(self, embeds, cache, vision=False):
        Backend.forward(self, embeds, cache, vision)
        last = int(embeds[0, -1, 0])
        scores = np.full(64, -5.)
        scores[{1: 2, 2: 3, 3: 1}.get(last, 1)] = 4.
        scores[10 + len(cache) % 40] = 3.
        return scores


loop = LiveSession(mind, Looper(), clock=lambda: 0.)
loop.frame(frame(10), at=0.)
toks = loop.ask('what is moving?', max_tokens=24)['tokens']
runs = [tuple(toks[i:i + 4]) for i in range(len(toks) - 3)]
check('a greedy answer that would loop does not repeat any four-token run', len(runs) == len(set(runs)) and len(toks) == 24)
g = guard_repeats(np.zeros(12), [1, 2, 3, 4, 9, 2, 3], keys=['the', 'blue', 'square', 'is', 'the', 'blue', 'square'])
check('runs are compared by their keys, so a case or space variant cannot restart a loop', g[4] == -np.inf)


class Channeler(Backend):
    """Would open a second thinking channel first (token 7 stands for <|channel>)."""
    def forward(self, embeds, cache, vision=False):
        Backend.forward(self, embeds, cache, vision)
        scores = np.full(16, -5.); scores[7] = 9.; scores[0] = 1. if len(cache) % 2 else -9.; scores[3] = 2.
        return scores


class ChannelTok(Tokenizer):
    unk_token_id = 99
    def convert_tokens_to_ids(self, tokens):
        return [{'<|channel>': 7, '<channel|>': 8}.get(t, 99) for t in tokens]


class ChannelMind(Mind):
    tokenizer = ChannelTok()


ch = LiveSession(ChannelMind(), Channeler(), clock=lambda: 0.)
ch.frame(frame(10), at=0.)
check('an answer never opens another thinking channel', ch.blocked == [7, 8] and 7 not in ch.ask('q', max_tokens=3)['tokens'])

check('nothing but the test fixtures was written', not any(memory_dir.iterdir()))
