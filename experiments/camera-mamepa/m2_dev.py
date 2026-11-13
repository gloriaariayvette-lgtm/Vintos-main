"""Development clips only: choose the mamepa boundary by the rule in CAMERA-MAMEPA-PREREG.json and write the choice
before any fresh clip is generated."""
import json

from mcommon import LABELS, QUESTION, WORK, clips, load, mamepa_hook, plain_stills, word
from camera_mamepa import Mamepa, Model
from native_video_runtime import LiveSession

ARMS = [5., 10., 20.]


def main():
    out = WORK / 'mamepa-choice.json'
    if out.exists():
        raise RuntimeError('Preserve the choice')
    mind, stream = load()
    model = Model(WORK / 'mamepa-aeon.npz')
    hits = {str(b): 0 for b in ARMS}
    hits['window_only'] = 0
    timings, n = [], 0
    for i, (frames, label) in enumerate(clips('resampler-development')):
        n += 1
        ms = [Mamepa(model, boundary=b) for b in ARMS]
        for m in ms:
            m.new_stream('dev-%d' % i, 0.)
        s = LiveSession(mind, stream, instruction=QUESTION, on_embedding=mamepa_hook(ms, stream, timings))
        for j, f in enumerate(plain_stills(900000 + i, 20) + list(frames)):
            s.frame(f, at=j * .5)
        a = s.ask('', max_tokens=8)
        hits['window_only'] += word(a['text']) == LABELS[label]
        for b, m in zip(ARMS, ms):
            sm = m.summary()
            a = s.ask('', max_tokens=8, view_from=sm['onset'], note=sm['text'])
            hits[str(b)] += word(a['text']) == LABELS[label]
        s.abort()
    acc = {k: v / n for k, v in hits.items()}
    best = max(ARMS, key=lambda b: (acc[str(b)], b == 10.))
    out.write_text(json.dumps({'clips': n, 'accuracy': acc, 'chosen_boundary': best,
                               'checkpoint_id': model.checkpoint_id, 'ssm': model.trained}, indent=2))
    print(json.dumps({'accuracy': acc, 'chosen_boundary': best}))


if __name__ == '__main__':
    main()
