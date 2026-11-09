#!/usr/bin/env python3
"""Render a bounded shadow review from one explicit private replay aggregate."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

# Import without initializing any serving organ or model.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay


def invalid():
    raise ValueError('invalid shadow report evidence')


def count(value):
    if type(value) is not int or value < 0:
        invalid()
    return value


def number(value, low=0, high=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < low or (high is not None and value > high):
        invalid()
    return format(value, '.6g')


def excerpt_coverage(section, eligible, scorable):
    """Report supplied distinct-target and forecast-row denominators separately."""
    lines = ['## Observed excerpt-control coverage', '']
    if section is None:
        return lines + ['Not configured.', '']
    if 'coverage' not in section:
        return lines + ['Coverage not supplied. Paired score counts alone do not establish target coverage.', '']
    c = section['coverage']
    keys = ('admitted_replies_before_cutoff', 'targets_with_scorable_forecast',
            'targets_without_scorable_forecast', 'scorable_forecasts_before_cutoff',
            'paired_forecasts', 'paired_targets', 'scorable_forecasts_without_pair',
            'scorable_forecasts_outside_complete_blocks')
    values = {key: count(c[key]) for key in keys}
    admitted, targets, missing, forecasts, pairs, paired_targets, unpaired, outside = (values[k] for k in keys)
    if (admitted != eligible or forecasts != scorable or targets + missing != admitted
            or targets > forecasts or bool(targets) != bool(forecasts)
            or pairs + unpaired != forecasts or paired_targets > targets or paired_targets > pairs
            or bool(pairs) != bool(paired_targets) or outside > unpaired
            or pairs != sum(count(p['n']) for p in section['paired_groups'])):
        invalid()
    lines += [f'- Unique eligible replies: {admitted}.',
              f'- Unique targets with a scorable forecast: {targets}; without one: {missing}.',
              f'- Scorable forecast rows: {forecasts}; paired with both excerpt controls: {pairs}; without a pair: {unpaired}.',
              f'- Unique targets represented in paired comparisons: {paired_targets}.',
              f'- Scorable forecast rows outside complete declared blocks: {outside}.', '']
    if not forecasts:
        lines += ['Forecast pair coverage is undefined because there are no scorable forecasts.', '']
    else:
        lines += [f'Forecast pair coverage: {pairs}/{forecasts} scorable forecast rows. This is not a fraction of all replies.', '']
    if not targets:
        lines += ['Distinct-target pair coverage is undefined because there are no scorable targets.', '']
    else:
        lines += [f'Distinct-target pair coverage: {paired_targets}/{targets} targets with scorable forecasts.', '']
    lines += ['These are supplied-data counts. Repeated checkpoints can contribute multiple forecasts for one target; no target count is inferred by summing comparison rows. Per-day block activity and private block labels are omitted.', '']
    return lines


def render(report):
    """Only fixed prose and validated numbers leave this projection.

    Unknown strings and labels are never copied, including source names, reasons,
    times, identifiers, arbitrary meanings and private fields in future schemas.
    """
    try:
        if report['schema'] != 'judges-shadow-v1' or report['input_kind'] not in ('synthetic', 'retained_snapshot'):
            invalid()
        kind = 'Synthetic contract run' if report['input_kind'] == 'synthetic' else 'Retained snapshot measurement'
        c, innovation = report['census'], report['innovation']
        eligible, identified = count(c['eligible_replies']), count(c['unique_identified_replies'])
        copies = count(c['evidence_coverage']['assistant_copies'])
        if eligible > identified or identified > copies:
            invalid()
        lines = ['# Shadow behaviour and innovation review', '', kind + '.', '',
                 'This report is descriptive. It grants no authenticity, accuracy, readiness or steering verdict.', '',
                 '## Evidence coverage', '',
                 f'- Assistant source copies: {copies}.',
                 f'- Unique identified replies: {identified}.', f'- Strictly eligible replies: {eligible}.',
                 'Copies and unique replies are different denominators. These counts cover the supplied snapshot, not the complete stream.', '']
        fields = c['evidence_coverage'].get('fields', {})
        if not isinstance(fields, dict): invalid()
        for field, positive in (('receipt', 'recorded'), ('identity_binding', 'matched'),
                ('served_identity', 'observed'), ('request_binding', 'recorded'),
                ('delivery', 'delivered'), ('response_binding', 'matched'),
                ('context_lineage', 'clean'), ('final_reply_lineage', 'clean')):
            if field not in fields:
                lines.append(f'- {field}: coverage not supplied.'); continue
            states = fields[field]
            if not isinstance(states, dict) or sum(count(v) for v in states.values()) != copies: invalid()
            positive_n = count(states.get(positive, 0))
            unevaluated = count(states.get('not_evaluated', 0))
            other = copies - positive_n - unevaluated
            lines.append(f'- {field}: {positive}={positive_n}; not evaluated={unevaluated}; other recorded states={other}.')
        lines += ['', 'Coverage fields count copies independently, including excluded acts. A positive field does not admit a reply.', '']
        if not eligible:
            lines += ['No strictly eligible replies: behaviour and prediction accuracy are insufficient on this evidence.', '']
        behaviour = report['behaviour_receipt']
        lines += ['## Scoped behaviour', '']
        if behaviour['status'] == 'not_configured':
            lines += ['Not configured: no explicit behaviour window and surface scope was supplied.', '']
        elif behaviour['status'] in ('descriptive', 'no_eligible_observations'):
            groups = behaviour['groups']
            if not isinstance(groups, list): invalid()
            observed = count(behaviour['eligible_observations'])
            if observed > eligible or sum(count(g['n']) for g in groups) != observed:
                invalid()
            if (behaviour['status'] == 'descriptive') != bool(groups): invalid()
            lines += [f'Eligible observations inside the supplied scope: {observed}.', '']
            if not groups:
                lines += ['Insufficient: no eligible observations in the configured scope. This does not mean no activity occurred.', '']
            for ordinal, group in enumerate(groups, 1):
                if not count(group['n']): invalid()
                lines += [f"- Behaviour group {ordinal}: n={group['n']}; mean words={number(group['mean_words'])}; "
                          f"median words={number(group['median_words'])}; literal question-mark fraction={number(group['question_mark_fraction'], high=1)}."]
            lines += ['', 'Groups remain separate by surface and observed served identity/revision. Word counts and punctuation do not measure character, feelings or relationship quality.', '']
        else:
            invalid()
        groups = innovation['groups']
        if not isinstance(groups, list): invalid()
        indices, total = {}, 0
        lines += ['## On-message prediction innovation', '']
        for group in groups:
            key, n, available = count(group['checkpoint_group']), count(group['n']), count(group['percentiles_available'])
            if not key or key in indices or not n or n > eligible or available > n: invalid()
            indices[key] = n; total += n
            lines += [f"- Checkpoint group {key}: forecasts={n}; mean cosine error={number(group['mean_cosine_error'], high=2)}; historical percentiles available={available}."]
        if not groups:
            lines += ['Insufficient: no scorable on-message forecasts. Missing forecasts are not zero error or zero innovation.']
        lines += ['', f'Scorable forecast rows: {total}. Multiple checkpoints may forecast one target; this is not a unique-turn count.',
                  'Groups do not pool checkpoints, encoders, surfaces or observed target generators. Percentiles use only earlier realized outcomes.', '']

        def comparisons(section, head_key, heading):
            lines.extend(['## ' + heading, ''])
            if section is None:
                lines.extend(['Not configured.', '']); return
            pairs = section['paired_groups']
            if not isinstance(pairs, list): invalid()
            used = {}
            for ordinal, pair in enumerate(pairs, 1):
                key, n = count(pair['checkpoint_group']), count(pair['n'])
                if key not in indices or not n: invalid()
                used[key] = used.get(key, 0) + n
                if used[key] > indices[key]: invalid()
                lines.append(f"- Comparison {ordinal}, checkpoint group {key}: paired n={n}; "
                             f"head={number(pair[head_key], high=2)}; last reply={number(pair['last_reply_error'], high=2)}; "
                             f"recent mean={number(pair['recent_mean_error'], high=2)}.")
            if not pairs:
                lines.append('Insufficient: no paired targets with both controls. No baseline win or loss can be claimed.')
            lines.extend(['', 'Each row compares identical targets within one checkpoint group and evaluation block. Rows are not pooled; full-reply and excerpt controls are different comparisons.', ''])
        comparisons(innovation['baselines'], 'paired_head_mean_error', 'Full-reply controls')
        comparisons(report.get('self_input_baselines'), 'head_error', 'Observed excerpt-input controls')
        lines += excerpt_coverage(report.get('self_input_baselines'), eligible, total)
        lines += ['## Interpretation limits', '',
                  'No confidence interval or pass decision is inferred from group means. A supplied block declaration is not proof of preregistration or an untouched evaluation.',
                  'Missing origin, delivery, ancestry or clock evidence remains missing. This report neither repairs it nor enables a feed.',
                  'No identifiers, source labels, private dates, text, vectors or weights are included. Keep the report private until its aggregate disclosure is reviewed.', '']
        return '\n'.join(lines)
    except (KeyError, TypeError, AttributeError, OverflowError):
        invalid()


def read_run(root, run):
    """Verify aggregate bytes against the supplied receipt, not the original data."""
    source = replay.inside(root, run / 'aggregate.json')
    manifest_path = replay.inside(root, run / 'private-run.json')
    raw, manifest_raw = source.read_bytes(), manifest_path.read_bytes()
    manifest = replay.decode_snapshot(manifest_raw)
    body = dict(manifest); claimed = body.pop('run_sha256', None)
    fingerprint = replay.digest(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False))
    record = manifest.get('outputs', {}).get('aggregate.json')
    if (manifest.get('schema') != 'judges-replay-run-v1' or claimed != fingerprint
            or record != {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}):
        invalid()
    report = replay.decode_snapshot(raw)
    if manifest.get('options', {}).get('input_kind') != report.get('input_kind'): invalid()
    return report, raw, manifest_raw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scratch', required=True)
    p.add_argument('--run', required=True, help='existing explicit replay output directory')
    p.add_argument('--output', required=True, help='new private report directory')
    args = p.parse_args()
    root = replay.scratch_root(args.scratch)
    run, output = replay.inside(root, args.run), replay.inside(root, args.output)
    if output.exists() or output in run.parents or run in output.parents or run == output: invalid()
    replay.install_guard(root, output)
    report, raw, manifest_raw = read_run(root, run)
    text = render(report) + '\nReceipt check: aggregate bytes and the supplied manifest fingerprint match. Original input, scoring checkout and other output files were not independently verified by this formatter.\n'
    payload = text.encode('utf-8')
    receipt = {'schema': 'judges-review-render-v1', 'aggregate_sha256': hashlib.sha256(raw).hexdigest(),
               'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
               'renderer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'review_sha256': hashlib.sha256(payload).hexdigest(),
               'verification_scope': 'aggregate_bytes_and_supplied_manifest_only'}
    output.mkdir(mode=0o700)
    for name, data in [('review.md', payload), ('private-render.json', (json.dumps(receipt, indent=2)+'\n').encode())]:
        with (output/name).open('xb') as f:
            os.chmod(f.name, 0o600); f.write(data)
    print('Shadow review written in private scratch.')

if __name__ == '__main__': main()
