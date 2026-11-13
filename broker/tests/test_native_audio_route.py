#!/usr/bin/env python3
"""Waveforms reach the mind; transcript bookkeeping cannot replace them."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import hashlib

repo = Path(__file__).resolve().parents[2]
scratch = tempfile.TemporaryDirectory()
os.environ['HOME'] = scratch.name
os.environ['SPARK_WORKSPACE'] = str(Path(scratch.name) / 'workspace')
assert Path(os.environ['SPARK_WORKSPACE']).is_relative_to(scratch.name)
sys.path.insert(0, str(repo / 'scripts'))
import native_audio as na
import voice_local as voice
for relative in ['scripts/native_audio.py', 'scripts/voice_local.py', 'scripts/auditory_memory.py',
                 'scripts/record_gaps.py', 'bin/mac_stage_service.py', 'studio/native_audio_runtime.py',
                 'studio/native_audio_server.py']:
    print('SOURCE_SHA256', relative, hashlib.sha256((repo / relative).read_bytes()).hexdigest())


def check(label, condition):
    assert condition, label
    print('ok - ' + label)


os.environ.pop('VINTOS_NATIVE_AUDIO_BASE', None)
check('route is disabled by default', not na.enabled())
for url in ['https://example.invalid:8844', 'http://192.0.2.1:8844', 'http://127.0.0.1:8840',
            'http://name:secret@localhost:8844', 'http://localhost:8844/path']:
    os.environ['VINTOS_NATIVE_AUDIO_BASE'] = url
    try:
        na.base_url()
        raise AssertionError('unsafe route accepted')
    except ValueError:
        pass
check('nonlocal, household and credential-bearing routes are refused', True)
os.environ['VINTOS_NATIVE_AUDIO_BASE'] = 'http://127.0.0.1:8844'
audio = base64.b64encode(b'\x00\x01' * 3200).decode()
parts = na.content(audio, 16000)
check('original bytes are preserved as an audio part', parts[1]['input_audio']['data'] == audio)
for invalid, rate in [('bad!', 16000), (audio, 44100), (base64.b64encode(b'x').decode(), 16000),
                      (base64.b64encode(b'\0\0' * 128001).decode(), 16000)]:
    try:
        na.content(invalid, rate)
        raise AssertionError('invalid audio accepted')
    except ValueError:
        pass
check('invalid and over-budget recordings fail explicitly', True)

calls = []
def post(url, body, timeout):
    calls.append((url, body))
    if url.endswith('/listen'):
        return json.dumps({'ok': True, 'transcript': 'index words', 'native_audio': True,
                           'checkpoint_sha256': na.ANCHOR_SHA256}).encode(), {}
    if url.endswith('/v1/chat/completions'):
        return json.dumps({'choices': [{'message': {'content': 'I heard the recording.'}}]}).encode(), {}
    if url.endswith('/tts'):
        return b'RIFF' + b'x' * 80, {'X-Vintos-Voice': 'fixture'}
    raise AssertionError('unexpected external call')
voice._post = post
na.verify = lambda: na.base_url()
check('all audio senders are stubbed', voice._post is post)

class Interaction:
    def __init__(self, *args):
        self.turn = types.SimpleNamespace(duplicate_event=False, test_mode=True, turn_id='fixture-turn')
    def prompt(self): return ''
    def admitted(self, text): pass
    def complete(self, text): return text

sys.modules['stratagem_turn'] = types.SimpleNamespace(Interaction=Interaction, control=lambda text: None,
                                                     guard_reply=lambda *args: True)
sys.modules['intent_engine'] = types.SimpleNamespace(note_response=lambda text: None)
sys.modules['intent_context'] = types.SimpleNamespace(admit_voice_lead=lambda turn: (None, ''))
voice._hold_audio = lambda *args, **kwargs: None
voice._remember_how_it_sounded = lambda *args, **kwargs: None
assert voice._hold_audio.__name__ == '<lambda>'
result = voice.turn(audio, 16000, 'fixture instructions')
brain = [body for url, body in calls if url.endswith('/v1/chat/completions')][0]
check('complete voice turn reaches the native route', result['ok'] and calls[0][0].endswith(':8844/listen'))
check('mind receives waveform instead of narrator text', brain['messages'][1]['content'][1]['input_audio']['data'] == audio
      and 'index words' not in json.dumps(brain['messages'][1]['content']))
check('transcript remains the literal interaction index', result['transcript'] == 'index words')
heard = voice._hear_input(audio, 16000)
check('short record carries a source reference and gap rule', heard['capture_ref'].startswith('sha256:') and 'not captured' in heard['record_gap'])
stream_calls = []
def stream_post(url, body):
    stream_calls.append(url)
    if url.endswith('/start'):
        return {'session_id': 'synthetic-session'}
    if url.endswith('/finish'):
        return {'checkpoint_sha256': na.ANCHOR_SHA256, 'native_audio': True, 'text': 'fixture'}
    return {'ok': True}
stream = na.Stream(post=stream_post)
stream.push(base64.b64decode(audio))
stream.finish()
check('stream client finishes without aborting an already closed session', stream.closed and not stream_calls[-1].endswith('/abort'))
check('stream client sends only to its verified loopback base', all(url.startswith('http://127.0.0.1:8844/audio/') for url in stream_calls))
import auditory_memory as memory
assert str(memory.STORE).startswith(scratch.name)
assert str(memory.TEST_MODE_FLAG).startswith(scratch.name)
record = memory.build(audio, 16000, heard)
check('native records do not fabricate an acoustic reading', record['observation']['reading'] == '' and not record['audio_kept'])
check('native record retains its source and omission rule', record['audio_ref'] == record['source_hash']
      and 'not captured' in memory.render(record))

spec = importlib.util.spec_from_file_location('native_stage_fixture', repo / 'bin/mac_stage_service.py')
stage = importlib.util.module_from_spec(spec); spec.loader.exec_module(stage)
loaders = []
stage._chatterbox_load = lambda: loaders.append('voice')
stage._chatterbox_unload = lambda: loaders.append('voice-unload')
stage._ears_load = lambda: loaders.append('ears')
assert stage._ears_load.__name__ == '<lambda>'
receipt = stage.voice_models(True, external_ears=True)
check('native call warms the existing voice without loading other ears', loaders == ['voice'] and receipt['external_ears'])
stage.voice_models(False, external_ears=True)
check('native call still releases its voice on end', loaders == ['voice', 'voice-unload'])

def fail(*args):
    raise RuntimeError('fixture service unavailable')
voice._post = fail
try:
    voice._hear_input(audio, 16000)
    raise AssertionError('failed native service silently fell back')
except RuntimeError:
    pass
check('native failure does not use a narrator or hosted fallback', voice._post is fail)

os.environ.pop('VINTOS_NATIVE_AUDIO_BASE')
legacy = voice._heard_content({'transcript': 'fixture words', 'audio_reading': 'fixture tone'}, audio, 16000)
check('disabled lane retains existing transcript and acoustic context', isinstance(legacy, str) and 'fixture tone' in legacy)
