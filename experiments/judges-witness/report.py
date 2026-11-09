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
from forecast_handoffs import validate_coverage as validate_handoffs, STATES as HANDOFF_STATES
from fit_completions import validate_coverage as validate_fits, STATES as FIT_STATES, COUNTS as FIT_COUNTS


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


def artifact_coverage(section, eligible):
    if section is None:
        return []
    if (section['scope'] != 'content_binding_only' or section['admission_effect'] != 'none'
            or section['scoring_effect'] != 'none' or section['encoder_identity'] != 'unverified'
            or section['artifact_observation_time'] != 'unverified'
            or section['forecast_target_selection'] != 'not_evaluated'):
        invalid()
    supplied, unique, refs, bound = (count(section[k]) for k in
        ('packets_supplied','unique_packets','source_references','bound_unique_replies'))
    states = section['states']
    if not isinstance(states, dict): invalid()
    total = sum(count(v) for v in states.values())
    full, excerpt, conflicts = (count(states.get(k,0)) for k in
        ('bound_full_text','bound_excerpt','conflicting_vector_observations'))
    mixed = count(states.get('mixed_vector_representations', 0))
    unobserved = count(states.get('vector_representation_unobserved', 0))
    if (unique > supplied or refs < unique or total != refs or bound > eligible
            or bound > full + excerpt or bool(bound) != bool(full + excerpt)):
        invalid()
    timing = []
    if 'checkpoint_availability_states' in section:
        values = section['checkpoint_availability_states']
        if not isinstance(values,dict) or sum(count(n) for n in values.values()) != unique: invalid()
        labels = ('parsed_by_logged_forecast','parsed_after_logged_forecast','audit_snapshot_observed',
                  'clock_discontinuity','unobserved','parameters_not_loaded','exact_forecast_row_missing',
                  'forecast_identity_mismatch','forecast_clock_mismatch','forecast_outside_cutoff')
        if set(values) - set(labels): invalid()
        for label in labels:
            timing.append(f'- Checkpoint availability {label}: {count(values.get(label,0))} packets.')
        timing += ['', 'These clock checks do not supply a training date or authenticate a forecast. Metadata-only reads never attest loaded parameters.', '']
    if 'encoder_parameter_observation_states' in section:
        values = section['encoder_parameter_observation_states']
        labels = ('observed_equal','observed_changed','unavailable','missing','not_instrumented_forecast','mixed_forecast_observations')
        if not isinstance(values,dict) or set(values)-set(labels) or sum(count(n) for n in values.values()) != unique: invalid()
        timing += [f'- Encoder parameter observation {label}: {count(values.get(label,0))} packets.' for label in labels]
        timing += ['', 'Matching CPU parameter snapshots and retained feature-call links are partial observations. Tokenizer, execution code and training lineage remain unverified; missing call links are not inferred.', '']
    if 'checkpoint_consistency' in section:
        from witness_artifact_join import validate_checkpoint_consistency, CHECKPOINT_CONSISTENCY_STATES
        c=section['checkpoint_consistency']
        validate_checkpoint_consistency(c,unique)
        timing += [f"- Checkpoint observation copies: {c['manifest_copies']}; checkpoint groups: {c['checkpoint_groups']}; validated observation shapes: {c['observed_manifests']}; legacy shapes: {c['legacy_manifests']}."]
        timing += [f"- Checkpoint consistency {key}: {c['states'][key]} groups." for key in CHECKPOINT_CONSISTENCY_STATES]
        timing += ['', 'These compare supplied fields grouped by checkpoint hash. Read-availability clocks are separate; missing legacy fields stay unknown. Consistent fields do not authenticate checkpoint bytes, encoder identity or fitting lineage, and reported dates remain reported. Content joins and scoring permission are unchanged.', '']
    else:
        timing += ['Checkpoint field-consistency coverage is unavailable in this legacy report.', '']
    if 'encoder_call_cost' in section:
        from witness_artifact_join import validate_encoder_call_cost
        from witness_self_artifacts import TIMING_STAGES
        c=section['encoder_call_cost']
        validate_encoder_call_cost(c,refs)
        timing += [f"- Retained encoder calls: {c['calls']}; with timing fields: {c['timed_calls']}; legacy without timing: {c['legacy_calls']}; conflicting cost receipts excluded: {c['conflicting_calls']}.",
                   f"- Encoding observations without call identity: {c['unidentified_observations']} of {c['observations']}."]
        for key in TIMING_STAGES:
            stage=c['stages'][key]
            timing += [f"- {key}: {stage['measured_calls']} measured calls, {stage['unavailable_calls']} unavailable; total {stage['total_seconds']:.6f} s, max {stage['max_seconds']:.6f} s."]
        sizes=c['parameter_snapshots']
        timing += [f"- Retained CPU parameter snapshots: {sizes['observed']}; bytes scanned {sizes['total_bytes']}; maximum snapshot bytes {sizes['max_bytes']}.",
                   '', 'Costs cover supplied retained calls, including unbound inputs, deduplicated by invocation. Conflicting cost copies are excluded. Durations are monotonic wall time, not CPU time, whole-job latency or complete-stream coverage. Missing stages are unavailable, not zero. Snapshot bytes are repeated scan volume, not resident model size. No encoder identity, delivery or training admission is inferred.', '']
    else:
        timing += ['Retained encoder call-cost coverage is unavailable in this legacy report.', '']
    if 'encoding_consistency' in section:
        from witness_artifact_join import ENCODING_CONSISTENCY_LABELS
        c = section['encoding_consistency']
        if not isinstance(c, dict) or set(c) != {'groups', 'references', *ENCODING_CONSISTENCY_LABELS}: invalid()
        groups, compared = count(c['groups']), count(c['references'])
        if (groups > compared or compared > refs or bool(groups) != bool(compared)
                or compared != full + excerpt + conflicts + mixed + unobserved): invalid()
        timing += [f'- Encoding consistency content groups: {groups}; references: {compared}.']
        for axis, labels in ENCODING_CONSISTENCY_LABELS.items():
            values = c[axis]
            if not isinstance(values, dict) or set(values)-set(labels) or sum(count(n) for n in values.values()) != groups: invalid()
            timing += [f'- Encoding consistency {axis} {label}: {count(values.get(label, 0))} groups.' for label in labels]
        timing += ['', 'Each axis counts exact content groups independently, before representation-conflict classification. Differences remain visible with incomplete peers; matching requires every reference and at least two distinct call markers. Raw outputs are compared only through validated call receipts, never by converting legacy vectors. Matching is partial evidence, not encoder identity, forecast-target selection or scoring permission.', '']
    return ['## Retained artifact content joins', '',
            f'- Packets supplied: {supplied}; unique packets: {unique}.',
            f'- Source references: {refs}; full-text bindings: {full}; excerpt bindings: {excerpt}.',
            f'- Conflicting-vector references: {conflicts}; mixed vector representations: {mixed}; unresolved representation differences: {unobserved}.',
            f'- Other unresolved references: {refs-full-excerpt-conflicts-mixed-unobserved}.',
            f'- Unique eligible replies with a content binding: {bound}.', '',
            'These are content-consistency counts, not scorable forecasts. Encoder identity, artifact observation time and forecast-target selection are unverified. Encoder-return and readout-normalized vectors are separate representations; no conversion is inferred. Excerpt vectors do not become full-reply vectors, and no admission or score changes.', ''] + timing


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
        if 'forecast_handoffs' in report:
            handoffs=report['forecast_handoffs']
            validate_handoffs(handoffs)
            lines += ['## Forecast pending handoffs', '']
            for name in ('forecast_rows','unique_receipts','launch_receipts','job_receipts','launch_receipts_without_job','job_receipts_without_row'):
                lines.append(f'- {name}: {handoffs[name]}.')
            for state in HANDOFF_STATES:
                lines.append(f'- {state}: {handoffs["states"][state]}.')
            lines += ['', 'These compare supplied launcher, pending-file and forecast-log observations. A join does not authenticate the caller, establish forecast-to-delivered-reply association or grant training eligibility. Missing origin markers remain unknown; scoring is unchanged.', '']
        if 'fit_completion_observations' in report:
            fits=report['fit_completion_observations']
            validate_fits(fits)
            lines += ['## Fitting completion observations', '']
            for name in FIT_COUNTS:
                lines.append(f'- {name}: {fits[name]}.')
            for state in FIT_STATES:
                lines.append(f'- {state}: {fits["states"][state]}.')
            lines += ['', 'Counts compare supplied local fit receipts with exact checkpoint observations. They do not authenticate sources, establish encoder ancestry, reconstruct historical training dates or grant eligibility. Multiple distinct receipts are held without choosing one; scoring is unchanged.', '']
        if 'historical_attribution' in report:
            historical = report['historical_attribution']
            if (not isinstance(historical, dict)
                    or historical['scope'] != 'per_assistant_source_copy_not_unique_training_turns'
                    or historical['admission_effect'] != 'none' or historical['training_effect'] != 'none'):
                invalid()
            tiers = historical['tiers']
            tier_names = ('observed','ledger_attributed','recorded_label','unknown')
            if not isinstance(tiers, dict) or set(tiers) != set(tier_names): invalid()
            counts = {tier:count(tiers[tier]) for tier in tier_names}
            exclusions = historical['excluded']
            if not isinstance(exclusions, dict) or set(exclusions) - {'outside_cutoff'}: invalid()
            excluded = count(exclusions.get('outside_cutoff',0))
            agreement = historical['label_ledger_agreement']
            agreement_names = ('agree','disagree','label_conflict','label_missing','ledger_unavailable')
            joins = historical['join_states']
            missing_clock = count(historical['copies_without_cutoff_clock'])
            if (sum(counts.values()) + excluded != copies or count(historical['assistant_copies']) != copies
                    or missing_clock > copies
                    or not isinstance(agreement, dict) or set(agreement) - set(agreement_names)
                    or sum(count(n) for n in agreement.values()) != sum(counts.values())
                    or not isinstance(joins, dict) or sum(count(n) for n in joins.values()) != sum(counts.values())):
                invalid()
            lines += ['## Historical model attribution', '']
            for tier, n in counts.items(): lines.append(f'- {tier}: {n} assistant source copies.')
            for state in agreement_names:
                lines.append(f'- Label/ledger {state}: {count(agreement.get(state,0))}.')
            lines += [f'- Outside cutoff: {excluded}.',
                      f"- Without a usable cutoff clock: {missing_clock}.", '',
                      'Historical labels and ledger matches are separate evidence tiers. They do not grant observed identity, strict eligibility, clean ancestry or a training decision. Counts are per source copy, not unique training turns.', '']
            if 'matched_methods' in historical:
                methods = historical['matched_methods']
                labels = {'generation_completion_id':'selected completion key',
                          'provider_request_id':'provider request key', 'nearest_time':'bounded nearest time'}
                if (not isinstance(methods, dict) or set(methods) != set(labels)
                        or sum(count(n) for n in methods.values()) != count(joins.get('matched',0))):
                    invalid()
                lines += [f'- Retained ledger matches by {label}: {count(methods[key])} source copies.'
                          for key,label in labels.items()]
                lines += ['', 'This breakdown overlaps the attribution tiers: an observed reply can also have a ledger match. It counts source copies after ambiguity and reuse checks, not unique calls or training turns. Exact correlation keys do not prove delivery or clean ancestry. The optional 30-second view remains separate.', '']
            else:
                lines += ['Match-method coverage not supplied; exact-key counts cannot be inferred from the aggregate tier totals.', '']
            if 'window30' in historical:
                extension = historical['window30']
                names = ('observed','ledger_attributed','recorded_label','unknown','ledger_attributed_window30')
                alternative = {name:count(extension['tiers'][name]) for name in names}
                added = count(extension['added_copies'])
                comparisons = {state:count(extension['added_label_ledger_agreement'].get(state,0))
                               for state in ('agree','disagree','label_conflict','label_missing')}
                if (type(extension['window_seconds']) is not int or extension['window_seconds'] != 30
                        or extension['selection'] != 'sole_call_all_replies_compete'
                        or extension['admission_effect'] != 'none' or extension['training_effect'] != 'none'
                        or sum(alternative.values()) != sum(counts.values())
                        or any(alternative[k] != counts[k] for k in ('observed','ledger_attributed'))
                        or any(alternative[k] > counts[k] for k in ('recorded_label','unknown'))
                        or alternative['ledger_attributed_window30'] != added
                        or sum(comparisons.values()) != added
                        or sum(count(v) for v in extension['join_states'].values()) != sum(counts.values())
                        or count(extension['join_states'].get('matched_window30',0)) != added):
                    invalid()
                lines += ['## Optional 30-second historical view', '',
                          'Alternative partition of the same source copies; do not add these counts to the original tiers.', '']
                for name in names:
                    lines.append(f'- {name}: {alternative[name]} assistant source copies.')
                for state, n in comparisons.items():
                    lines.append(f'- Added-copy exact label agreement {state}: {n}.')
                denominator = comparisons['agree'] + comparisons['disagree']
                lines += [f'- Exact agreement among added copies with one label: {comparisons["agree"]}/{denominator}.'
                          if denominator else '- Exact agreement is undefined: no added copies have one comparable label.', '',
                          'This uses a sole call within 30 seconds, not the nearest of several. All nearby replies compete. Exact string disagreement can reflect route aliases; no model family is inferred. This is sensitivity evidence, not validated accuracy, independent samples or a training decision.', '']
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
        lines += artifact_coverage(report.get('self_artifact_joins'), eligible)
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
