#!/usr/bin/env python3
"""Read-only: replay retained investigation step chains through the current stall and reuse rules.

    python3 scripts/probes/lab_investigation_replay.py COPY_OF_investigations.json [--since ISO] [--outputs DIR]

Give it a COPY of chemistry-lab/investigations.json. Nothing is sent, nothing is written: the Lab modules are
imported against a throwaway workspace, and the copy is only read. --outputs names the Lab's investigation-outputs
directory (read only) so a reuse is counted only where the earlier output is really retained and unchanged.

For each investigation it re-labels each recorded step the way the current code would have stored it (a repeat of
the investigation's own completed step: handed that output; a source cooldown: a wait; a cross-investigation reuse
the identity rule now refuses: a failure), then asks the current _budget_spent where the chain would have closed.
It cannot know what the planner would have chosen next, so "would have continued" means only that the recorded
steps no longer close it. Prints aggregate counts only, no content.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument('store')
ap.add_argument('--since', default='2026-10-24T22:36')
ap.add_argument('--outputs', default='')
args = ap.parse_args()
live = Path(os.path.expanduser('~/.vintos/workspace/memory/chemistry-lab/investigations.json'))
if live.exists() and Path(args.store).resolve() == live.resolve():
    sys.exit('give a copy of investigations.json, not the live store')
os.environ['SPARK_WORKSPACE'] = tempfile.mkdtemp(prefix='lab-replay-')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab_investigations as I   # noqa: E402

data = json.load(open(args.store))
REPEAT_TEXT = ('you already asked this', 'you already ran this exact lookup', 'prior model read already includes')


def old_rule(steps):
    run = 0
    for s in reversed(steps):
        if s.get('state') in ('failed', 'outcome_unknown', 'superseded_not_sent'): run += 1
        else: break
    return len(steps) >= I.MAX_STEPS or run >= I.MAX_FAILED_RUN


def retained(step):
    if not args.outputs:
        return bool(step.get('output_file'))
    path = Path(args.outputs) / Path(str(step.get('output_file') or '')).name
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest() == step.get('output_sha256')


def payload_of(step):
    if not args.outputs: return None
    try: return json.loads((Path(args.outputs) / Path(str(step.get('output_file') or '')).name).read_text())
    except (OSError, ValueError): return None


relabel = Counter()


def before(at):
    """The store as it stood when a step was made: a later step cannot have been the one reused."""
    return {'investigations': [dict(i, steps=[s for s in i.get('steps', []) if str(s.get('at') or '') < str(at or '')])
                               for i in data.get('investigations', [])]}


def replay(inv):
    by_id = {s.get('id'): s for s in inv.get('steps', [])}
    out = []
    for s in inv.get('steps', []):
        s = dict(s)
        err = str(s.get('error') or '')
        own = re.match(r'already done in this investigation as (S-[0-9a-f]+)', err)
        if s.get('state') == 'failed' and own:
            src = by_id.get(own.group(1))
            if src and src.get('state') == 'completed' and retained(src):
                s.update(state='completed', repeat_within=True, reused_from=src['id']); relabel['repeat handed its own output'] += 1
            else:
                relabel['repeat whose own output is not retained: still a failure'] += 1
        elif s.get('state') == 'failed' and err.strip() == I.COOLDOWN:
            s['state'] = 'waiting_not_sent'; relabel['cooldown now a wait'] += 1
        elif s.get('state') == 'superseded_not_sent':
            relabel['set-aside send now neutral'] += 1
        elif s.get('state') == 'failed' and any(t in err for t in REPEAT_TEXT):
            probe = {k: v for k, v in s.items() if k not in ('state', 'error')}
            earlier = I._answered_before(err, probe, before(s.get('at')))
            if earlier is not None and earlier.get('id') in by_id and retained(earlier):
                s.update(state='completed', repeat_within=True, reused_from=earlier['id'])
                relabel['repeat-check refusal now handed its own step'] += 1
            else:
                relabel['repeat-check refusal with nothing to reuse: still a failure'] += 1
        elif s.get('reused_because'):
            probe = {k: v for k, v in s.items() if k not in ('state', 'reused_from', 'reused_because')}
            earlier = I._answered_before(s['reused_because'], probe, before(s.get('at')))
            payload = payload_of(earlier) if earlier is not None else None
            if earlier is None or (payload is not None and not I._carries(payload, probe)):
                s.update(state='failed', error='identity: reuse refused'); relabel['earlier reuse now refused on identity'] += 1
            else:
                relabel['earlier reuse still accepted'] += 1
        out.append(s)
    return out


recent = [i for i in data.get('investigations', []) if str(i.get('opened_at') or '') >= args.since]
outcome, reasons, old_closed = Counter(), Counter(), 0
for inv in recent:
    steps = inv.get('steps') or []
    if any(old_rule(steps[:k]) for k in range(1, len(steps) + 1)):
        old_closed += 1
    new = replay(inv)
    closes = next((k for k in range(1, len(new) + 1) if I._budget_spent({'steps': new[:k]})), None)
    if inv.get('state') != 'stalled' or not str(inv.get('closed_reason') or '').endswith(('nothing', 'finish')) \
            and 'produced nothing' not in str(inv.get('closed_reason')) and 'step budget' not in str(inv.get('closed_reason')):
        outcome['not closed by the step rules (open, or closed before any step)'] += 1
        continue
    if closes is None:
        outcome['would have continued: recorded steps no longer close it'] += 1
    elif closes < len(new):
        outcome['would close earlier (a reuse now refused on identity)'] += 1
        reasons[re.sub(r'\d+', 'N', I._budget_spent({'steps': new[:closes]}))[:150]] += 1
    else:
        outcome['would still close at the same step'] += 1
        reasons[re.sub(r'\d+', 'N', I._budget_spent({'steps': new[:closes]}))[:150]] += 1

print('investigations opened since %s: %d (states: %s)' % (args.since, len(recent),
      dict(Counter(i.get('state') for i in recent))))
print('closed by the old stall/step rules on their recorded steps: %d' % old_closed)
print('step relabels under the current code:')
for k, n in relabel.most_common(): print('  %4d  %s' % (n, k))
print('replayed through the current rules:')
for k, n in outcome.most_common(): print('  %4d  %s' % (n, k))
print('closure reasons the current rules would give:')
for k, n in reasons.most_common(10): print('  %4d  %s' % (n, k))
print('retained outputs checked against their digests: %s' % ('yes' if args.outputs else 'no (give --outputs)'))
