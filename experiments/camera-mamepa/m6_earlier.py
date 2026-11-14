"""Earlier-scene recall, scored once (CAMERA-MAMEPA-PREREG-2.json): the question is about a scene that ended before
the current one and has left the window."""
import hashlib
import json
import time

import numpy as np

import mcommon
from mcommon import LABELS, WORK, load, mamepa_hook, pct, word
from camera_mamepa import Mamepa, Model
from native_video_runtime import LiveSession

mcommon.SETS.update({'earlier-A': (2026111503, 256, [14, 16])})


def current_scene(seed, count=16, size=192):
    """One continuous synthetic scene: a fixed gradient background and one drifting disc (never a square)."""
    rng = np.random.default_rng(seed)
    top, bottom = rng.integers(0, 256, 3), rng.integers(0, 256, 3)
    g = np.linspace(0, 1, size)[:, None, None]
    bg = np.broadcast_to(top * (1 - g) + bottom * g, (size, size, 3)).astype(np.uint8)
    r = int(rng.integers(10, 17)); c = rng.uniform(50, size - 50, 2)
    v = rng.uniform(2, 4) * np.array([[-1, 0], [1, 0], [0, -1], [0, 1]][int(rng.integers(4))])
    color = rng.integers(0, 256, 3, dtype=np.uint8)
    yy, xx = np.ogrid[:size, :size]
    out = []
    for j in range(count):
        cy, cx = c + v * j
        f = bg.copy(); f[np.hypot(yy - cy, xx - cx) < r] = color
        out.append(f)
    return out


def main():
    out = WORK / 'final-earlier.json'
    if out.exists():
        raise RuntimeError('Preserve the scored result')
    prereg_path = WORK / 'CAMERA-MAMEPA-PREREG-2.json'
    prereg = json.loads(prereg_path.read_text())
    question, margin = prereg['question'], prereg['bars']['margin']
    choice = json.loads((WORK / 'mamepa-choice.json').read_text())
    model = Model(WORK / 'mamepa-aeon.npz')
    if model.checkpoint_id != choice['checkpoint_id']:
        raise RuntimeError('Checkpoint changed after the development choice')
    mind, stream = load()
    log = (WORK / 'final-earlier.jsonl').open('a')
    rows, added, frame_times, started = [], [], [], time.perf_counter()
    for i, (frames, label) in enumerate(mcommon.clips('earlier-A')):
        row = {'id': i, 'label': LABELS[label], 'clip_sha256': hashlib.sha256(frames.tobytes()).hexdigest()}
        m = Mamepa(model, boundary=choice['chosen_boundary']); m.new_stream('earlier-%d' % i, 0.)
        s = LiveSession(mind, stream, instruction=question, on_embedding=mamepa_hook([m], stream, frame_times, keep=True))
        for j, f in enumerate(list(frames) + current_scene(1200000 + i)):
            s.frame(f, at=j * .5)
        row['square_in_window'] = any(w['kind'] == 'frame' and w['at'] < 2.0 for w in s.window())
        rec = m.recall()
        row['recall_found_earlier_scene'] = bool(rec and rec['segment']['start'] == 0.0 and rec['segment']['frames'] >= 2)
        row['recalled_segment'] = rec and rec['segment']
        first = {}
        for arm in (['recall', 'plain'] if i % 2 == 0 else ['plain', 'recall']):
            if arm == 'recall':
                a = s.ask('', max_tokens=8, note=rec['note'] if rec else None, recall_frames=rec['frames'] if rec else None)
                row['mamepa_recall'] = word(a['text'])
            else:
                a = s.ask('', max_tokens=8)
                row['no_recall'] = word(a['text'])
            first[arm] = a['first_token_seconds'] or 0.
        added.append(first['recall'] - first['plain'])
        s.abort()
        rows.append(row)
        log.write(json.dumps(row) + '\n'); log.flush()
    acc = {k: sum(r[k] == r['label'] for r in rows) / len(rows) for k in ['mamepa_recall', 'no_recall']}
    found = [r for r in rows if r['recall_found_earlier_scene']]
    result = {'prereg_sha256': hashlib.sha256(prereg_path.read_bytes()).hexdigest(), 'cases': len(rows), 'accuracy': acc,
              'recall_found_earlier_scene': len(found) / len(rows),
              'accuracy_when_found': sum(r['mamepa_recall'] == r['label'] for r in found) / max(1, len(found)),
              'square_still_in_window': sum(r['square_in_window'] for r in rows),
              'added_first_token': {'p50': pct(added, 50), 'p95': pct(added, 95)},
              'frame_p95': pct(frame_times, 95), 'seconds': time.perf_counter() - started}
    result['checks'] = {'earlier_scene_margin': acc['mamepa_recall'] >= acc['no_recall'] + margin}
    result['passed'] = all(result['checks'].values())
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
