"""Text parity, no regression: the stream's positioned caches vs the NativeMind text route on the first 2,000 unique
reviewed-eleven inputs (by sha256). Hashes and numeric errors only; no stimulus or prose is saved."""
import hashlib
import json
import pathlib

import numpy as np

from mcommon import WORK, load

DATA = pathlib.Path.home() / 'review-scratch-native-audio-voice-compat-20261113/offline/residual_emotion/datasets/reviewed-eleven'
COUNT = 2000


def main():
    out = WORK / 'text-parity-mamepa.json'
    if out.exists():
        raise RuntimeError('Preserve the scored result')
    unique = {}
    for path in sorted(DATA.glob('*.jsonl')):
        if path.name.endswith('-base-reviewed.jsonl'):
            continue
        for line in (l for l in path.read_text().splitlines() if l.strip()):
            row = json.loads(line)
            for side in ['target', 'control']:
                text = row[side] + row['suffix']
                unique[hashlib.sha256(text.encode()).hexdigest()] = text
    keys = sorted(unique)[:COUNT]
    mind, stream = load()
    tok = mind.tokenizer
    maximum, mismatches = 0., 0
    for key in keys:
        messages = [{'role': 'user', 'content': unique[key]}]
        expected = mind.session(messages, max_tokens=8).scores
        ids = tok.encode(tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False),
                         add_special_tokens=False)
        actual = stream.forward(stream.text(ids), stream.new_cache())
        maximum = max(maximum, float(np.max(np.abs(actual - expected))))
        mismatches += int(actual.argmax()) != int(expected.argmax())
    result = {'inputs': len(keys), 'argmax_mismatches': mismatches, 'maximum_absolute_error': maximum,
              'passed': mismatches == 0 and maximum == 0.}
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
