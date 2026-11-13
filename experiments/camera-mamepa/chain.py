"""Camera mamepa chain, one lock hold: train on synthetic clips and the DAVIS 2017 train set (AEON embeddings), development choice, fresh
motion/retention/latency, earlier-scene recall, text parity, vision. Stops at the first failure; every step logs to its own file."""
import subprocess
import sys

from mcommon import HOME, MIND, SHA, WORK

DAVIS = HOME / 'datasets' / 'davis2017' / 'DAVIS'   # public, approved 2026-11-13; frames are only decoded

STEPS = [
    ['src/studio/camera_mamepa_train.py', '--encoder', 'aeon', '--mind', str(MIND), '--expected-sha256', SHA,
     '--clips', '384', '--val-clips', '48', '--epochs', '30', '--dz', '64', '--out', 'mamepa-aeon.npz',
     '--davis', str(DAVIS), '--davis-clips', '192', '--davis-val-clips', '48', '--report', 'train-aeon.json'],
    ['m2_dev.py'], ['m3_fresh.py'], ['m6_earlier.py'], ['m4_parity.py'], ['m5_vision.py'],
]
for step in STEPS:
    name = step[0].rsplit('/', 1)[-1][:-3]
    print('=== ' + name, flush=True)
    with (WORK / (name + '.log')).open('ab') as log:
        rc = subprocess.run([sys.executable, '-u'] + step, cwd=WORK, stdout=log, stderr=subprocess.STDOUT).returncode
    print('rc', rc, flush=True)
    if rc:
        break
