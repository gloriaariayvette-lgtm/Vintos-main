"""Fresh seeds, scored once: motion (no regression vs the MLX-native bulk reference), retention with the camera
mamepa, and the latency it adds."""
import hashlib
import json
import time

import numpy as np

import mcommon
from mcommon import LABELS, QUESTION, WORK, Tracer, bulk_reference, load, mamepa_hook, pct, plain_stills, word
from camera_mamepa import Mamepa, Model
from native_video_runtime import LiveSession

mcommon.SETS.update({'apple5-A': (2026111501, 128, [14, 16]), 'apple5-B': (2026111502, 256, [14, 16])})


def recall_ask(session, mamepa):
    started = time.perf_counter()
    sm = mamepa.summary()
    build = time.perf_counter() - started
    a = session.ask('', max_tokens=8, view_from=sm['onset'], note=sm['text'])
    return a, build, sm


def main():
    out = WORK / 'final-mamepa.json'
    if out.exists():
        raise RuntimeError('Preserve the scored result')
    prereg_path = WORK / 'CAMERA-MAMEPA-PREREG.json'
    bars = json.loads(prereg_path.read_text())['bars']
    choice = json.loads((WORK / 'mamepa-choice.json').read_text())
    model = Model(WORK / 'mamepa-aeon.npz')
    if model.checkpoint_id != choice['checkpoint_id']:
        raise RuntimeError('Checkpoint changed after the development choice')
    boundary = choice['chosen_boundary']
    mind, stream = load()
    tracer = Tracer(stream)
    log = (WORK / 'final-mamepa.jsonl').open('a')
    results, frame_times, added = {}, [], []
    for name in ['apple5-A', 'apple5-B']:
        rows, started = [], time.perf_counter()
        for i, (frames, label) in enumerate(mcommon.clips(name)):
            row = {'set': name, 'id': i, 'label': LABELS[label], 'clip_sha256': hashlib.sha256(frames.tobytes()).hexdigest()}
            tracer.reset()
            m = Mamepa(model, boundary=boundary); m.new_stream('%s-%d' % (name, i), 0.)
            q = LiveSession(mind, stream, instruction=QUESTION, on_embedding=mamepa_hook([m], stream, frame_times))
            for j, f in enumerate(frames):
                q.frame(f, at=j * .5)
            k = len(tracer.calls)
            a = q.ask('', max_tokens=8)
            ref = bulk_reference(stream, mind, tracer.calls[:k + 2])
            b, _, _ = recall_ask(q, m); q.abort()
            row.update(stream_primary=word(a['text']), bulk_reference=word(ref), stream_mamepa=word(b['text']))
            if name == 'apple5-B':
                m = Mamepa(model, boundary=boundary); m.new_stream('ret-%d' % i, 0.)
                r = LiveSession(mind, stream, instruction=QUESTION, on_embedding=mamepa_hook([m], stream, frame_times))
                for j, f in enumerate(plain_stills(1100000 + i, 20) + list(frames)):
                    r.frame(f, at=j * .5)
                first = {}
                for arm in (['mamepa', 'plain'] if i % 2 == 0 else ['plain', 'mamepa']):
                    if arm == 'mamepa':
                        c, build, sm = recall_ask(r, m)
                        row.update(retained=word(c['text']), onset=sm['onset'], segments=sm['segments'])
                    else:
                        c, build = r.ask('', max_tokens=8), 0.
                        row['retained_window_only'] = word(c['text'])
                    first[arm] = (c['first_token_seconds'] or 0.) + build
                added.append(first['mamepa'] - first['plain'])
                r.abort()
            rows.append(row)
            log.write(json.dumps(row) + '\n'); log.flush()
        keys = ['stream_primary', 'bulk_reference', 'stream_mamepa', 'retained', 'retained_window_only']
        acc = {k: sum(r.get(k) == r['label'] for r in rows) / len(rows) for k in keys if k in rows[0]}
        acc['bulk_parsed'] = sum(r['bulk_reference'] is not None for r in rows) / len(rows)
        results[name] = {'cases': len(rows), 'accuracy': acc, 'seconds': time.perf_counter() - started}
        print(json.dumps({name: results[name]}), flush=True)
    m_, rm, lim = bars['stream_vs_bulk_margin'], bars['retention_margin'], bars['latency_added_p95_seconds']
    B = results['apple5-B']['accuracy']
    latency = {'frame_p95': pct(frame_times, 95), 'frame_max': max(frame_times), 'ask_added_p95': pct(added, 95),
               'ask_added_median': pct(added, 50)}
    checks = {'motion_' + n: results[n]['accuracy']['stream_mamepa'] >= results[n]['accuracy']['bulk_reference'] - m_ for n in results}
    checks['reference_parses'] = all(results[n]['accuracy']['bulk_parsed'] >= .9 for n in results)
    checks['retention_absolute'] = B['retained'] >= bars['retention_absolute']
    checks['retention_vs_stream'] = B['retained'] >= B['stream_primary'] - rm
    checks['latency_frame'] = latency['frame_p95'] < lim
    checks['latency_ask'] = latency['ask_added_p95'] < lim
    out.write_text(json.dumps({'prereg_sha256': hashlib.sha256(prereg_path.read_bytes()).hexdigest(), 'choice': choice,
                               'results': results, 'latency': latency, 'checks': checks,
                               'passed': all(checks.values())}, indent=2))
    print(json.dumps({'latency': latency, 'checks': checks, 'passed': all(checks.values())}))


if __name__ == '__main__':
    main()
