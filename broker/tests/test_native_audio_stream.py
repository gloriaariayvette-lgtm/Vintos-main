#!/usr/bin/env python3
"""Bounded waveform framing and cache lifetime, with a synthetic backend only."""
import base64
import os
from pathlib import Path
import sys
import tempfile
import time
import types

import numpy as np

repo = Path(__file__).resolve().parents[2]
scratch = tempfile.TemporaryDirectory()
os.environ['HOME'] = scratch.name
os.environ['SPARK_WORKSPACE'] = str(Path(scratch.name) / 'workspace')
assert Path(os.environ['SPARK_WORKSPACE']).is_relative_to(scratch.name)
sys.path.insert(0, str(repo / 'studio'))
from native_audio_runtime import AudioSession, MARKER
from native_audio_server import Service, waveform


def check(label, condition):
    assert condition, label
    print('ok - ' + label)


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return '<user>' + messages[0]['content'] + '<end>'
    def encode(self, text, **kwargs):
        return [ord(c) % 50 for c in text]
    def decode(self, tokens, **kwargs):
        return 'a' * len(tokens)


class Backend:
    def new_cache(self): return []
    def text(self, ids): return np.array(ids, dtype=np.float32).reshape(1, -1, 1)
    def audio(self, frames): return frames.mean(-1).reshape(1, -1, 1)
    def forward(self, embeds, cache, length):
        cache.extend(embeds[0, :, 0].tolist())
        assert length == len(cache)
        return np.array([0., 1.]), cache


class Mind:
    sha = 'synthetic-checkpoint'
    eos = {0}
    suppress = []
    tokenizer = Tokenizer()
    backend = Backend()
    def session(self, messages, max_tokens=2, temperature=0, **kwargs):
        return AudioSession(self, messages, max_tokens, temperature, **kwargs)


mind = Mind()
check('no model loader or network sender is used', isinstance(mind.backend, Backend))
messages = [{'role': 'user', 'content': '<|audio>' + MARKER + '<audio|>'}]
x = np.linspace(-.5, .5, 6381, dtype=np.float32)
caches = []
for chunk in [len(x), 3200, 997, 1]:
    session = mind.session(messages)
    for i in range(0, len(x), chunk):
        receipt = session.push(x[i:i + chunk])
        assert receipt['pending_samples'] < 640
    cache = session.cache
    result = session.finish()
    caches.append(list(cache))
    check('frame count and bounded cache are exact for chunk %d' % chunk,
          result['audio_tokens'] == 10 and session.cache is None and not len(session.pending))
    try:
        session.push(x[:1]); raise AssertionError('closed stream accepted input')
    except ValueError:
        pass
check('arbitrary packet boundaries preserve the same frames and token order', all(c == caches[0] for c in caches))
session = mind.session(messages)
for bad in [np.array([np.nan]), np.ones((1, 2)), np.array([1.1]), np.array([]), np.zeros(128001)]:
    try:
        session.push(bad); raise AssertionError('invalid stream accepted')
    except ValueError:
        assert session.samples == 0
check('invalid and over-budget chunks never mutate the stream', session.samples == 0)
session.push(np.zeros(128000, dtype=np.float32))
check('eight-second audio uses exactly 200 tokens', session.audio_tokens == 200)
session.abort()
check('abort releases waveform tail and cache', session.cache is None and not len(session.pending))
voice_session = mind.session(messages, sample_limit=480000)
voice_session.push(np.zeros(480000, dtype=np.float32))
check('complete thirty-second voice recording keeps every frame', voice_session.finish()['audio_tokens'] == 750)
try:
    mind.session([{'role': 'user', 'content': 'x' * 7600 + MARKER}], sample_limit=480000)
    raise AssertionError('long audio exceeded the shared context budget')
except ValueError:
    pass
check('long voice reserves its actual audio context budget', True)
text = mind.session([{'role': 'user', 'content': 'ready'}]).finish()
check('text warmup needs no fake waveform', not text['native_audio'] and text['audio_tokens'] == 0)

service = Service(mind)
start = service.dispatch('/audio/start', {'max_tokens': 2})
try:
    service.dispatch('/audio/start', {}); raise AssertionError('overlapping session accepted')
except BlockingIOError:
    pass
check('one stream owns the inference cache', service.active[0] == start['session_id'])
packet = base64.b64encode(b'\0\0' * 997).decode()
service.dispatch('/audio/push', {'session_id': start['session_id'], 'audio': packet})
result = service.dispatch('/audio/finish', {'session_id': start['session_id']})
check('finish clears session and returns an evidence reference', service.active is None and result['audio_ref'].startswith('sha256:')
      and not result['raw_audio_retained'])
service.dispatch('/audio/start', {})
old = service.active[1]
service.expires = time.monotonic() - 1
service.expire()
check('idle expiry aborts the cache', service.active is None and old.closed and old.cache is None)
check('idle expiry cancels its cleanup timer', service._expiry_timer is None)
complete = service.dispatch('/listen', {'audio': base64.b64encode(b'\0\0' * 480000).decode(), 'sample_rate': 16000})
check('complete voice endpoint retains all thirty seconds', complete['audio_tokens'] == 750 and service.active is None)
for invalid in ['bad!', base64.b64encode(b'x').decode()]:
    try:
        waveform(invalid); raise AssertionError('invalid PCM accepted')
    except ValueError:
        pass
check('malformed PCM is refused before inference', True)
