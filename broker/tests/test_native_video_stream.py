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
try:
    pcm16(base64.b64encode(b'\0').decode()); raise AssertionError('odd PCM accepted')
except ValueError:
    pass
check('malformed audio packets are refused', True)

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
check('nothing but the test fixtures was written', not any(memory_dir.iterdir()))
