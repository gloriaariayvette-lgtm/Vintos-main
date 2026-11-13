"""Camera mamepa run, copied from the native video run's vision_battery.py with its own output folder and the
stream-path diagnostic asked with recall on. Existing sight stays at 19/22: the original grader and cases on the unchanged GGUF mind and its native
projection, served by an owned loopback process (port 8877) that is stopped afterwards. Then the same 22
cases through the new stream path (one 280-token frame, then the question) as a diagnostic."""
import base64
import hashlib
import io
import json
import pathlib
import re
import socket
import subprocess
import time
import urllib.request

from mcommon import WORK

HOME = pathlib.Path.home()
VISION = HOME / 'physics-lab/aeon-vision'
MIND = HOME / 'pool/models/aeon-gemma-4-12b-q4km.gguf'
PROJECTOR = VISION / 'aeon-gemma-4-12b-mmproj-bf16.gguf'
BINARY = pathlib.Path('/opt/homebrew/bin/llama-server')
PORT = 8877
OUT = WORK / 'vision-battery-mamepa'


def sha(path):
    d = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            d.update(block)
    return d.hexdigest()


def gguf():
    if sha(PROJECTOR) != '4271b5b06deac7f4f608f55540b9d846563d8f6d9f31b14bb14c7b52f288e44c':
        raise RuntimeError('Original projector changed')
    probe = socket.socket()
    try: probe.bind(('127.0.0.1', PORT))
    finally: probe.close()
    log = (OUT / 'server.log').open('wb')
    proc = subprocess.Popen([str(BINARY), '-m', str(MIND), '--mmproj', str(PROJECTOR), '--alias', 'aeon', '--host', '127.0.0.1',
                             '--port', str(PORT), '-c', '8192', '-np', '1', '-ngl', '99', '-fa', 'on', '--jinja'],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    (OUT / 'owned-process.json').write_text(json.dumps({'pid': proc.pid, 'port': PORT, 'started_unix': time.time()}))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.monotonic() + 180
        while True:
            if proc.poll() is not None: raise RuntimeError('Owned server exited')
            try:
                with opener.open('http://127.0.0.1:%d/health' % PORT, timeout=2) as r:
                    if r.status == 200: break
            except Exception:
                if time.monotonic() > deadline: raise
                time.sleep(.5)
        batteries = []
        for i, cases in enumerate(['cases.json', 'cases2.json'], 1):
            rel = '../../camera-mamepa-20261113/vision-battery-mamepa/battery%d.json' % i
            with (OUT / ('battery%d.log' % i)).open('wb') as blog:
                run = subprocess.run([str(HOME / 'physics-lab/env/bin/python'), str(VISION / 'grade.py'), str(PORT), '1024', rel, cases],
                                     stdout=blog, stderr=subprocess.STDOUT, timeout=1800)
            if run.returncode: raise RuntimeError('Original grader failed')
            actual = json.loads((OUT / ('battery%d.json' % i)).read_text())
            base = json.loads((VISION / ['smoke-results-own-battery1-repeat.json', 'smoke-results-own-battery2.json'][i - 1]).read_text())
            correct = {r['file']: bool(r['correct']) for r in actual}
            batteries.append({'case_file': cases, 'correct': sum(correct.values()), 'total': len(actual),
                              'lost_cases': [r['file'] for r in base if r['correct'] and not correct.get(r['file'])]})
        return batteries
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        log.close()
        (OUT / 'owned-process-stopped.json').write_text(json.dumps({'pid': proc.pid, 'returncode': proc.returncode}))


def stream_path():
    import numpy as np
    from PIL import Image
    from mcommon import load
    from camera_mamepa import Mamepa, Model
    model = Model(WORK / 'mamepa-aeon.npz')
    boundary = json.loads((WORK / 'mamepa-choice.json').read_text())['chosen_boundary']
    from native_video_runtime import LiveSession
    mind, stream = load()
    rows = []
    for cases in ['cases.json', 'cases2.json']:
        for c in json.loads((VISION / 'synthetic' / cases).read_text()):
            rgb = np.asarray(Image.open(VISION / 'synthetic' / c['file']).convert('RGB'))
            m = Mamepa(model, boundary=boundary); m.new_stream(c['file'], 0.)
            s = LiveSession(mind, stream, on_embedding=lambda kind, at, e, ref: m.frame(stream.numpy(e).reshape(-1, e.shape[-1]).mean(0), at))
            s.frame(rgb, at=0, soft_tokens=280)
            sm = m.summary()
            ans = s.ask(c['q'], max_tokens=448, view_from=sm['onset'], note=sm['text'])['text'].strip().lower(); s.abort()
            hit = (lambda k: re.search(r'\b' + re.escape(k) + r'\b', ans)) if c.get('word_match') else (lambda k: k in ans)
            rows.append({'file': c['file'], 'correct': all(any(hit(k) for k in g) for g in c['expect'])})
    return rows


def main():
    if OUT.exists():
        raise RuntimeError('Preserve the scored result')
    OUT.mkdir()
    batteries = gguf()
    stream_rows = stream_path()
    result = {'gguf_route': batteries, 'gguf_correct': sum(b['correct'] for b in batteries),
              'vision_gate_passed': sum(b['correct'] for b in batteries) >= 19 and not any(b['lost_cases'] for b in batteries),
              'stream_path_correct': sum(r['correct'] for r in stream_rows), 'stream_path_rows': stream_rows,
              'private_media_used': False}
    (OUT / 'acceptance.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'stream_path_rows'}))


if __name__ == '__main__':
    main()
