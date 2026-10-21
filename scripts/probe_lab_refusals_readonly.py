#!/usr/bin/env python3
"""Read-only retrospective Lab audit. Stdlib only; no application imports/calls.

Writes JSONL to stdout only. It cannot recover unsaved planner prompts or prior
hold timestamps. Unknown means unknown, not 'the planner ignored the list'.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True


def readonly(event, args):
    if event == 'open':
        if (args[2] or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise RuntimeError('probe forbids file writes')
    if event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.truncate',
                 'os.link', 'os.symlink', 'subprocess.Popen', 'os.system', 'socket.connect', 'socket.sendto'):
        raise RuntimeError('probe forbids mutation/network/process: ' + event)


def stamp(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def matches(text, subject):
    # Same ASCII-alphanumeric boundaries as chemistry_lab.spent_matches.
    return bool(subject and re.search(r'(?<![A-Za-z0-9])' + re.escape(subject) +
                                      r'(?![A-Za-z0-9])', str(text or ''), re.I))


def classify(inquiry):
    """Conservative intent classification; neither execution nor novelty proof.

    Mixed/unclear are retained rather than forcing every question into two bins.
    Explicit documented-fact wording wins over merely having a measuring tool.
    """
    q = str(inquiry.get('question') or '')
    doc = bool(re.search(r'\b(?:documented|source-backed|curated|annotated|annotations?|literature|'
                         r'published|records? (?:list|state|establish)|structural hallmarks)\b', q, re.I))
    measurement = bool(re.search(
        r'\b(?:measure|calculate|compute|superimpose|align|screen|map residues|fold (?:a|the|this))\b|'
        r'\bcompare\b.*\b(?:across species|between species|structures|sequences)\b|'
        r'\b(?:test|compare)\b.*\bprediction\b.*\b(?:measured|experimental)\b|'
        r'\b(?:RMSD|TM-score|per-residue confidence)\b.*\b(?:model|reference|predicted|range)\b', q, re.I))
    if not measurement and re.search(r'^\s*(?:what|which)\b.*\b(?:function|cellular role|localization|'
                                     r'domain annotations)\b', q, re.I):
        doc = True
    iq = inquiry.get('instrument_query') or {}
    sq = inquiry.get('source_query') or {}
    op = iq.get('operation') if isinstance(iq, dict) else None
    computational_route = op in ('structure.read', 'structure.compare', 'structure.measure',
        'structure.analyze', 'sequence.run_analysis', 'sequence.align',
        'esmc.mutation_landscape', 'esmc.feature_interpretation') or (
        isinstance(sq, dict) and sq.get('source') == 'rt_locus_screen')
    if doc and measurement:
        label = 'mixed'
    elif doc:
        label = 'documented_fact_lookup'
    elif measurement or computational_route:
        label = 'new_measurement_question'
    else:
        label = 'unclear'
    return {'kind': label, 'documented_wording': doc, 'measurement_wording': measurement,
            'computational_route': bool(computational_route),
            'method': 'transparent_rules_manual_review_required; intent_not_result'}


def verdict_category(value):
    verdict = str(value or '').strip()
    return ('not assessed' if verdict.lower().startswith('not assessed') else
            'not established' if verdict.lower().startswith('not established') else
            'yes' if re.match(r'^yes\b', verdict, re.I) else
            'no' if re.match(r'^no\b', verdict, re.I) else 'other')


class QuestionAudit:
    """Attribute notebook operations conservatively to accepted inquiry intervals.

    There is no cycle ID. Only the daemon's accepted inquiry -> outcome order is
    used; emit each link for audit. Reviews with different queries remain unlinked.
    Provider HTTP requests, internal retries and unlogged validation reads cannot
    be counted from notebook events. Source-operation counts are lower bounds.
    """
    def __init__(self):
        self.current = None
        self.groups = {kind: {'question_rows_by_kind': Counter(), 'unique_questions': set(),
                     'review_verdicts': Counter(), 'source_operation_events': Counter(),
                     'instrument_result_events': 0, 'measurement_receipt_ids': set(),
                     'material_receipt_ids': set(), 'source_failure_events': 0,
                     'reused_structure_events': 0}
                     for kind in ('documented_fact_lookup', 'new_measurement_question', 'mixed', 'unclear', 'unattributed')}

    def observe(self, number, row):
        kind = row.get('kind')
        inquiry = row.get('inquiry') if isinstance(row.get('inquiry'), dict) else {}
        if kind in ('inquiry', 'inquiry_refused', 'evidence_wait', 'reflection'):
            inquiry = dict(inquiry, question=inquiry.get('question') or row.get('question') or '')
            classification = classify(inquiry)
            label = classification['kind']
            group = self.groups[label]
            group['question_rows_by_kind'][kind] += 1
            group['unique_questions'].add(' '.join(inquiry['question'].casefold().split()))
            if kind == 'inquiry':
                self.current = {'line': number, 'inquiry': inquiry, 'classification': classification}
            emit({'type': 'question_classification', 'line': number, 'at': row.get('at'),
                  'row_kind': kind, 'question': inquiry['question'], 'classification': classification,
                  'source_query': inquiry.get('source_query'), 'instrument_query': inquiry.get('instrument_query'),
                  'uniprot_query': inquiry.get('uniprot_query')})
            if kind == 'reflection':
                group['review_verdicts'][verdict_category(row.get('answers_question'))] += 1
                if row.get('material_receipt_id'):
                    group['material_receipt_ids'].add(row['material_receipt_id'])
                # A rewrite is allowed only when the recorded discovery query
                # names the accepted input. Otherwise do not silently join cycles.
                origin = (inquiry.get('query_resolution') or {}).get('requested_query')
                linked = bool(self.current and (inquiry.get('question') == self.current['inquiry'].get('question') or
                    (origin and origin == self.current['inquiry'].get('uniprot_query'))))
                emit({'type': 'question_review_link', 'review_line': number,
                      'accepted_inquiry_line': self.current['line'] if linked else None,
                      'accepted_kind': self.current['classification']['kind'] if linked else None,
                      'reviewed_kind': label, 'verdict': row.get('answers_question'),
                      'link_basis': 'chronological_plus_question_or_discovery_query' if linked else 'unknown'})
                self.current = None
            elif kind in ('inquiry_refused', 'evidence_wait'):
                self.current = None
            return
        label = self.current['classification']['kind'] if self.current else 'unattributed'
        group = self.groups[label]
        event = None
        if kind == 'source_read' and row.get('source') == 'UniProtKB REST':
            event = 'uniprot_browse'
        elif kind == 'additional_source':
            query = row.get('query_sent') or {}
            if not isinstance(query, dict):
                query = {}
            if query.get('skill'):
                group['instrument_result_events'] += 1
                if row.get('receipt_id'):
                    group['measurement_receipt_ids'].add(row['receipt_id'])
                event = 'instrument:' + str(query.get('skill'))
            else:
                event = 'source:' + str(query.get('source') or query.get('plugin') or 'unknown')
        elif kind == 'structure_read':
            if row.get('reused_receipt'):
                group['reused_structure_events'] += 1
                event = 'structure_cache_reuse'
            else:
                event = 'pdb_structure_operation'
        elif kind == 'source_unavailable':
            group['source_failure_events'] += 1
            event = 'source_failure_not_proof_request_sent'
        if event:
            # Cache/instrument/failure counts are separated from source calls.
            if not event.startswith(('instrument:', 'structure_cache', 'source_failure')):
                group['source_operation_events'][event] += 1
            emit({'type': 'question_operation_link', 'line': number, 'at': row.get('at'),
                  'accepted_inquiry_line': self.current['line'] if self.current else None,
                  'question_kind': label, 'event': event, 'receipt_id': row.get('receipt_id') or row.get('source_receipt_id'),
                  'query_sent': row.get('query_sent'),
                  'attribution': 'chronological_daemon_interval_not_attempt_id' if self.current else 'unknown'})
        if kind in ('browse_stale', 'fault_redirect'):
            self.current = None

    def summary(self):
        result = {}
        for kind, group in self.groups.items():
            result[kind] = {key: (len(value) if isinstance(value, set) else dict(value)
                                  if isinstance(value, Counter) else value) for key, value in group.items()}
        accepted = sum(g['question_rows_by_kind'].get('inquiry', 0) for g in self.groups.values())
        for group in result.values():
            group['accepted_question_share_percent'] = round(
                100 * group['question_rows_by_kind'].get('inquiry', 0) / accepted, 2) if accepted else None
        return result


def read_json(path, default):
    try:
        with path.open() as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def rows(path, start, end, errors):
    try:
        with path.open('rb') as f:
            for n, raw in enumerate(f, 1):
                try:
                    row = json.loads(raw)
                    if not isinstance(row, dict):
                        raise ValueError('not a mapping')
                except (ValueError, UnicodeDecodeError):
                    errors[str(path.name)] += 1
                    continue
                t = stamp(row.get('at'))
                if t is not None and start <= t <= end:
                    yield n, row, t
    except FileNotFoundError:
        errors[str(path.name) + ':missing'] += 1


def hold_status(subject, t, spent):
    found = []
    for row in spent.values():
        if not isinstance(row, dict):
            continue
        clean = re.split(r'\s+(?:AND|OR|NOT)\b|"|\s*:', str(row.get('subject') or ''),
                         maxsplit=1, flags=re.I)[0].strip().strip("'").strip()
        if clean.casefold() == subject.casefold():
            at = stamp(row.get('at'))
            if at is not None:
                found.append(at)
    if not found:
        return {'status': 'absent_from_current_store'}
    before = [at for at in found if at <= t]
    if any(0 <= t - at < 86400 for at in before):
        at = max(at for at in before if t - at < 86400)
        return {'status': 'within_retained_24h_interval', 'age_hours_at_refusal': round((t-at)/3600, 4)}
    if any(at > t for at in found):
        return {'status': 'unknown_latest_stamp_postdates_refusal_prior_interval_overwritten'}
    return {'status': 'retained_interval_expired', 'age_hours_at_refusal': round((t-max(before))/3600, 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-root', type=Path, default=Path(os.environ.get(
        'SPARK_WORKSPACE', str(Path.home()/'.vintos/workspace'))) / 'memory/chemistry-lab')
    parser.add_argument('--end', help='ISO timestamp with zone; default current UTC')
    parser.add_argument('--hours', type=float, default=24)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('chemistry_lab.py'))
    args = parser.parse_args()
    end = stamp(args.end) if args.end else datetime.now(timezone.utc).timestamp()
    if end is None or args.hours <= 0:
        parser.error('valid --end and positive --hours required')
    start = end - args.hours * 3600
    sys.addaudithook(readonly)
    root = args.lab_root
    source = args.source.read_bytes()
    tree = ast.parse(source)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SPENT_HOURS', 'SPENT_PROMPT_CHARS', 'CLASS_WORDS'):
                    constants[target.id] = ast.literal_eval(node.value)
    if constants.get('SPENT_HOURS') != 24:
        raise SystemExit('source hold duration differs from this probe; review before interpreting')
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in
              (root/'notebook.jsonl', root/'spent-subjects.json', root/'lookups.jsonl') if p.exists()}
    spent = read_json(root/'spent-subjects.json', {})
    if not isinstance(spent, dict):
        raise SystemExit('spent-subjects.json is not a mapping')
    emit({'type': 'metadata', 'start_utc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
          'end_utc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
          'source_sha256': hashlib.sha256(source).hexdigest(),
          'spent_store_entries': len(spent), 'spent_prompt_cap': constants.get('SPENT_PROMPT_CHARS'),
          'limits': ['No saved prompts or attempt IDs in these ledgers.',
                     'Current hold timestamps cannot reconstruct overwritten historical intervals.',
                     'Gate also unions recent dead-end subjects; store membership is not prompt membership.',
                     'Question-only matches are candidates for inspection, not proof of false refusal.']})
    errors, counts, matched, interval_counts, review_counts, outcomes = (Counter() for _ in range(6))
    n_spent = question_only_all = 0
    previous_inquiry = None
    feature_inquiries = discovery_reviews = connection_reviews = 0
    question_audit = QuestionAudit()
    for number, row, t in rows(root/'notebook.jsonl', start, end, errors):
        question_audit.observe(number, row)
        kind = row.get('kind')
        counts[str(kind)] += 1
        inquiry = row.get('inquiry') or {}
        if not isinstance(inquiry, dict):
            inquiry = {}
        if kind == 'inquiry':
            previous_inquiry = {'at': row.get('at'), 'question': inquiry.get('question'),
                                'uniprot_query': inquiry.get('uniprot_query')}
            feature_inquiries += str(inquiry.get('question') or '').startswith(
                'Which domains, binding sites and annotated residues does the curated record of ')
        why = str(row.get('why') or '')
        if kind in ('inquiry_refused', 'evidence_wait') and 'spent subject:' in why:
            n_spent += 1
            m = re.search(r'spent subject:.*?without an answer \(([^)]*)\)', why)
            names = [s.strip() for s in m[1].split(',') if s.strip()] if m else []
            q = str(inquiry.get('question') or row.get('question') or '')
            query = str(inquiry.get('uniprot_query') or '') + ' ' + json.dumps(inquiry.get('source_query') or {})
            pairs = []
            for name in names:
                status = hold_status(name, t, spent)
                interval_counts[status['status']] += 1
                matched[name] += 1
                pairs.append({'subject': name, 'in_question': matches(q, name),
                              'in_query_text': matches(query, name), 'retained_store_interval': status,
                              'in_actual_planner_spent_prompt': 'unknown_prompt_not_recorded',
                              'class_word_excluded_now': name.casefold() in
                                  {s.casefold() for s in constants.get('CLASS_WORDS', set())}})
            only = bool(pairs) and all(p['in_question'] and not p['in_query_text'] for p in pairs)
            question_only_all += only
            hint = ('stored_wait_may_have_no_new_planner_call' if inquiry.get('planning_wait') else
                    'replan_false_gate_branch' if 'no eligible saved step:' in why else
                    'after_gate_replan_or_deterministic_recovery' if why.startswith('repeat: spent subject:') else
                    'unclassified')
            emit({'type': 'spent_refusal', 'line': number, 'at': row.get('at'), 'kind': kind,
                  'question': q, 'uniprot_query': inquiry.get('uniprot_query'), 'source_query': inquiry.get('source_query'),
                  'why': why, 'pairs': pairs, 'all_named_matches_question_only': only,
                  'named_list_may_be_truncated': len(names) >= 4,
                  'planner_first_or_replan': 'unknown_attempt_not_recorded', 'control_flow_hint': hint,
                  'strategy_resolution': inquiry.get('strategy_resolution'),
                  'planning_scope': inquiry.get('planning_scope')})
        if kind == 'reflection':
            verdict = str(row.get('answers_question') or '').strip()
            category = verdict_category(verdict)
            review_counts[category] += 1
            outcomes[str(row.get('review_outcome'))] += 1
            coverage = row.get('coverage_check') or {}
            q = str(inquiry.get('question') or '')
            resolution = inquiry.get('query_resolution') or {}
            discovery = resolution.get('reason') == 'plain_name_discovery_resolved_to_returned_record'
            discovery_reviews += discovery
            connection_reviews += 'and any source-backed relationship between those features' in q
            emit({'type': 'review', 'line': number, 'at': row.get('at'), 'question': q,
                  'compound_template': bool(re.search(r'structural hallmarks.*cellular roles.*relationships', q, re.I)),
                  'answers_question': verdict, 'reader_answers_question': row.get('reader_answers_question'),
                  'review_outcome': row.get('review_outcome'), 'missing': coverage.get('missing', row.get('missing_evidence')),
                  'supports_count': len(coverage.get('supports') or []),
                  'independent_sufficiency': coverage.get('independent_sufficiency'),
                  'validation_failure': row.get('validation_failure', coverage.get('validation_failure')),
                  'source_accessions': row.get('source_accessions'), 'literature_count': len(row.get('literature') or []),
                  'source_query_succeeded': row.get('source_query_succeeded'),
                  'query_resolution': resolution, 'assignment_resolution': inquiry.get('assignment_resolution'),
                  'previous_inquiry_temporal_candidate_not_attempt_id': previous_inquiry,
                  'previous_inquiry_query_matches_discovery': bool(discovery and previous_inquiry and
                      previous_inquiry['uniprot_query'] == resolution.get('requested_query')),
                  'fulltext_passages_count': len(row.get('fulltext_passages') or []),
                  'claim_evidence': row.get('claim_evidence')})
    lookup_counts = Counter()
    for _, row, _ in rows(root/'lookups.jsonl', start, end, errors):
        reason = str(row.get('refused') or '')
        lookup_counts['refused' if reason else 'accepted'] += 1
        if 'spent subject:' in reason:
            lookup_counts['spent_refused'] += 1
            if reason.startswith('no eligible saved step:'):
                lookup_counts['spent_replan_false'] += 1
    # Steering context, reported separately from the daemon's 24h question split.
    for line in (read_json(root/'lines.json', {}).get('lines') or []):
        if isinstance(line, dict) and line.get('state') == 'open':
            emit({'type': 'current_open_line_not_historical', 'id': line.get('id'),
                  'origin': line.get('origin'), 'standing': line.get('standing'),
                  'question': line.get('question'), 'classification': classify(line),
                  'next_step': line.get('next_step'),
                  'next_step_classification': classify({'question': line.get('next_step')})})
    sessions = {}
    for _, session, _ in rows(root/'sessions.jsonl', start, end, errors):
        if session.get('state') == 'completed' and session.get('session_id'):
            sessions[session['session_id']] = session
    for session in sessions.values():
        plan, reading = session.get('plan') or {}, session.get('reading') or {}
        emit({'type': 'frontier_session_separate_from_daemon_split', 'session_id': session['session_id'],
              'at': session.get('at'), 'experiment': plan.get('experiment'), 'question': plan.get('question'),
              'classification': classify(plan), 'prediction': plan.get('prediction'),
              'next_question': reading.get('next_question'),
              'next_question_classification': classify({'question': reading.get('next_question')}),
              'prediction_vs_result': reading.get('prediction_vs_result')})
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in
             (root/'notebook.jsonl', root/'spent-subjects.json', root/'lookups.jsonl') if p.exists()}
    emit({'type': 'summary', 'notebook_kinds': dict(counts), 'spent_refusal_rows': n_spent,
          'named_subject_counts': dict(matched), 'store_interval_counts': dict(interval_counts),
          'all_named_matches_question_only': question_only_all,
          'question_only_share_of_spent_rows_percent': round(100*question_only_all/n_spent, 2) if n_spent else None,
          'reviews': dict(review_counts), 'review_outcomes': dict(outcomes),
          'feature_only_inquiries': feature_inquiries, 'discovery_resolved_reviews': discovery_reviews,
          'code_connection_template_reviews': connection_reviews,
          'question_kind_breakdown': question_audit.summary(),
          'novel_findings_per_day': 'not_established_by_these_ledgers; measurement_intent_or_yes_is_not_novelty',
          'source_count_limit': 'recorded operations only, not HTTP requests; material receipt use is separate; '
                               'internal retries, cache hits, validation reads and fulltext searches may be unlogged',
          'lookup_ledger_counts_not_notebook_passes': dict(lookup_counts), 'parse_errors': dict(errors),
          'files_changed_during_read': before != after})


if __name__ == '__main__':
    main()
