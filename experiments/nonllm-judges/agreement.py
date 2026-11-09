#!/usr/bin/env python3
"""Compare retained judgments with offline numerical receipts; counts only."""
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


G = load('agreement_private_io', HERE / 'render_gloria.py')
R = load('agreement_numerical_runner', HERE / 'run_private.py')
BANDS = ('abstain', 'flag', 'pass')
PAIRS = {
    'voice_coherence': ('voice', ('memory/voice-coherence.md',), 'selected_flags_only'),
    'deviation_check': ('voice', ('memory/voice-coherence.md',), 'selected_mixed_judgment_events'),
    'presence_audit': ('voice', ('memory/presence-audit.json', 'memory/presence-audit-history.jsonl'), 'retained_audits'),
    'humor_detector': ('humor', ('memory/humor-moments.json',), 'selected_positive_moments_only'),
}
# Stores are source-code inventory, not a claim that a private file exists.
UNPAIRED = {
    'thread_triage': ('memory/thread-triage.md', 'memory/unfinished-threads.json'),
    'thread_weaver': ('memory/unfinished-threads.json',),
    'thread_resolution': ('memory/retired-threads.json', 'memory/unfinished-threads.json'),
    'wonder': ('memory/wonder-log.json',),
    'hallucination': ('memory/hallucination-flags.json',),
    'surprise': ('memory/surprise-log.md',),
    'self_prediction': ('memory/self-blind-spots.jsonl', 'memory/.self-prediction-history.json', 'memory/self-prediction-held.jsonl'),
    'self_model_update': ('SELF-MODEL.md', 'memory/self-model-refusals.jsonl'),
    'soul_review': ('memory/soul-proposals', 'SOUL.md'),
    'pride_mirror': ('memory/pride-reflections.md',),
    'value_map': ('memory/value-map.md',),
    'introspection': ('memory/introspection',),
    'mirror': ('memory/mirror',),
    'conversation_review': ('memory/conversation-insights.json',),
    'emotion_read': (),
    'emotional_reflection': ('memory/emotional-reflections.md', 'memory/reflection-history.json'),
    'owner_prediction': ('memory/gloria-prediction.json', 'memory/gloria-prediction-history.json'),
    'withheld': ('memory/withheld.json', 'memory/withheld-history.json'),
    'causality': ('memory/causality-hypotheses.json', 'memory/causality-retired.jsonl'),
    'world_model': ('memory/world-state.json',),
    'yearning_scars': ('memory/current-yearning.json', 'memory/yearning-scars.json'),
    'pearl': ('memory/candidate-pearls.json',),
    'reality_anchor': ('memory/reality-anchor.json',),
    'unprecedented': ('memory/unprecedented-states.md',),
    'search_question': ('memory/web-search-log.json', 'memory/web-discoveries.md'),
    'creative_search': ('memory/creative-discoveries.md',),
    'social_score': ('memory/moltbook-replies.txt',),
    'social_members': ('memory/moltbook-members.json',),
    'social_post_check': ('memory/moltbook-post-log.md',),
}
LIMIT = 4096


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def number(value, low=0, high=1):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def band(judge, record, store):
    """Read native retained fields. Absence and parse failure never mean pass."""
    if judge in ('voice_coherence', 'deviation_check'):
        if not isinstance(record, str): return None
        lines = record.strip().splitlines()
        if not lines: return None
        if judge == 'voice_coherence':
            found = re.fullmatch(r'## \d{4}-\d\d-\d\d \d\d:\d\d — Score ([1-5])', lines[0])
            if not found or len(lines) < 3 or not lines[-1].startswith('Reply excerpt: '): return None
            # This writer persists only <=3 with a nonempty, non-none note.
            if int(found[1]) > 3 or not '\n'.join(lines[1:-1]).strip() or lines[1].strip().lower() == 'none': return None
            return 'flag'
        found = re.fullmatch(r'## \d{4}-\d\d-\d\d \d\d:\d\d — (Deviation|Aligned) \(score: (\d+(?:\.\d+)?)\)', lines[0])
        if not found or not number(float(found[2])): return None
        if found[1] == 'Deviation':
            return 'flag' if float(found[2]) > .30 and '**Not aligned.** Something resisted.' in lines else None
        # The writer also calls commitment_friction "Aligned". Do not infer pass.
        return 'abstain'
    if not isinstance(record, dict): return None
    if judge == 'presence_audit':
        if not isinstance(record.get('id'), str) or not number(record.get('composite')): return None
        # History drops both flag and requested-work exemption: it cannot recover the decision.
        if store.endswith('history.jsonl'): return 'abstain'
        if record.get('exempt') == 'requested_work': return 'abstain'
        return ('flag' if record['flag'] else 'pass') if type(record.get('flag')) is bool else None
    if judge == 'humor_detector':
        if record.get('source') != 'vintos' or not number(record.get('signal')) or record['signal'] < .5: return None
        return 'pass'
    return None


def project_records(projection, rows, cutoff):
    if not isinstance(projection, dict) or projection.get('schema') != 'judge-verdict-projection-v1': raise ValueError('schema')
    records = projection.get('records')
    if not isinstance(records, list) or len(records) > LIMIT: raise ValueError('record bound')
    if G.instant(projection['cutoff_at']).timestamp() != cutoff: raise ValueError('cutoff mismatch')
    indexes = {r['id']: r for r in rows}
    candidates = defaultdict(list); counts = {j: Counter() for j in (*PAIRS, *UNPAIRED)}
    seen = {}; poisoned = set()
    for entry in records:
        if not isinstance(entry, dict) or entry.get('judge') not in counts: raise ValueError('judge')
        judge = entry['judge']; c = counts[judge]; c['projected_records'] += 1
        stores = PAIRS[judge][1] if judge in PAIRS else UNPAIRED[judge]
        if entry.get('store') not in stores: raise ValueError('store')
        if judge not in PAIRS:
            c['no_equivalent_reply_comparator'] += 1; continue
        record = entry.get('record'); key = (judge, entry['store'], digest(record))
        # A copied retained event is never a second vote. Conflicting bindings poison both.
        signature = digest(entry)
        if key in seen:
            if seen[key] == signature: c['duplicate_records'] += 1
            else: poisoned.add(key); c['conflicting_copies'] += 1
            continue
        seen[key] = signature
        result = band(judge, record, entry['store'])
        if result is None: c['invalid_or_unsupported_verdict'] += 1; continue
        binding = entry.get('binding')
        if not isinstance(binding, dict) or binding.get('kind') != 'recorded_full_reply':
            c['missing_exact_binding'] += 1; continue
        row = indexes.get(binding.get('turn_id'))
        if row is None: c['reply_not_admitted'] += 1; continue
        mode = {'opening_everyday': 'everyday', 'intimate': 'intimate'}.get(row.get('mode'), 'unknown')
        try:
            valid = (binding['content_sha256'] == row['sha'] and binding['surface'] == row['surface']
                     and binding['mode'] == mode and G.instant(binding['finalized_at']).timestamp() == row['at']
                     and row['at'] <= G.instant(entry['recorded_at']).timestamp() < cutoff
                     and entry.get('clock_order') == 'known')
        except (KeyError, TypeError, ValueError): valid = False
        if not valid: c['binding_or_time_mismatch'] += 1; continue
        # These are recorded metadata claims, never inferred from configured defaults.
        served = entry.get('served_model'); fallback = entry.get('fallback')
        metadata = ('known' if isinstance(served, str) and served.strip() else 'unknown',
                    'known' if type(fallback) is bool else 'unknown')
        candidates[(judge, row['id'])].append((key, result, metadata))
    selected = {j: {} for j in PAIRS}
    for (judge, turn), entries in candidates.items():
        if any(k in poisoned for k, _, _ in entries) or len(entries) != 1:
            counts[judge]['ambiguous_reply_verdicts'] += 1; continue
        _, result, metadata = entries[0]
        selected[judge][turn] = result
        counts[judge]['exact_joined_verdicts'] += 1
        counts[judge]['served_model_' + metadata[0]] += 1
        counts[judge]['fallback_' + metadata[1]] += 1
    return selected, {j: dict(sorted(c.items())) for j, c in counts.items()}


def numerical_bands(view, facet):
    records = view['voice_drift_receipts']['voice'] if facet == 'voice' else view['facet_receipts'][facet]
    result = {}; invalid = set()
    for receipt in records:
        key = receipt['turn_id'] if facet == 'voice' else receipt['attempt_id']
        if key in result: invalid.add(key); continue
        value = receipt['band_location']
        result[key] = {'below_band': 'flag', 'above_band': 'pass', 'abstain': 'abstain'}[value]
    for key in invalid: result.pop(key, None)
    return result


def comparison(ids, left, right):
    keys = set(ids); l = keys & left.keys(); r = keys & right.keys(); joined = l & r
    matrix = {a: {b: 0 for b in BANDS} for a in BANDS}
    for key in joined: matrix[left[key]][right[key]] += 1
    decisive = sum(matrix[a][b] for a in ('flag', 'pass') for b in ('flag', 'pass'))
    agreed = sum(matrix[a][a] for a in BANDS)
    return dict(population_replies=len(keys), recorded_judgment_replies=len(l), numerical_receipt_replies=len(r),
        both_covered=len(joined), recorded_only=len(l-r), numerical_only=len(r-l), neither=len(keys-l-r),
        joint_coverage=len(joined)/len(keys) if keys else None,
        confusion=matrix, agreement_rate=agreed/len(joined) if joined else None,
        decisive_pairs=decisive, decisive_agreement_rate=(matrix['flag']['flag']+matrix['pass']['pass'])/decisive if decisive else None,
        disagreement_kinds=dict(recorded_flag_numerical_pass=matrix['flag']['pass'],
            recorded_pass_numerical_flag=matrix['pass']['flag'],
            recorded_abstain_numerical_decisive=matrix['abstain']['flag']+matrix['abstain']['pass'],
            numerical_abstain_recorded_decisive=matrix['flag']['abstain']+matrix['pass']['abstain']))


def report(bundle, landings, projection, cutoff):
    cutoff = R.P.stamp(cutoff)
    # Re-evaluate the existing pure pipeline: input-provided numerical bands are never trusted.
    private, _ = R.evaluate(bundle, landings, cutoff)
    rows = R.adapt(bundle, cutoff)[0]
    left, coverage = project_records(projection, rows, cutoff)
    output = dict(schema='judge-agreement-counts-v1', band_policy='descriptive-proxy-v1',
        ground_truth=False, replacement_authorized=False, source_claims_independently_verified=False,
        population='character_admitted_replies_not_all_live_replies', source_coverage=coverage, views={},
        unavailable_pairs={
            'deviation_vs_drift': 'daily_sustained_shift_is_not_a_reply_verdict',
            'taste': 'no_equivalent_retained_reply_rubric',
            'recurrence': 'no_retained_numerical_adapter_or_equivalent_reply_verdict',
            'grouping': 'no_retained_numerical_adapter_or_equivalent_reply_verdict',
            **{j: dict(stores=list(stores), both_covered=None, agreement_rate=None,
                       reason='no_equivalent_reply_comparator' if stores else 'no_durable_verdict_store_identified')
               for j, stores in UNPAIRED.items()},
        })
    for view_name, view in private['views'].items():
        selected = [r for r in rows if view_name == 'window30' or r['primary']]
        pairs = {}
        for judge, (facet, stores, retention) in PAIRS.items():
            right = numerical_bands(view, facet)
            if facet == 'humor':
                message_ids = {r['attempt_id'] for r in view['facet_receipts'][facet] if r['scope'][2] == 'message'}
                right = {key: value for key, value in right.items() if key in message_ids}
            ids = [r['id'] for r in selected]
            if facet == 'humor':
                supplied = bundle.get('numerical_evidence', {})
                attempts = set(supplied.get('humor_attempt_ids', []))
                items = {r['node_id']: r['kind'] for r in supplied.get('items', [])}
                attempts = {key for key in attempts if items.get(key, 'message') == 'message'}
                ids = [key for key in ids if key in attempts]
            scopes = []
            for mode in G.MODES:
                for surface in G.SURFACES:
                    scope_ids = [r['id'] for r in selected if r['id'] in ids and r['surface'] == surface and
                                 {'opening_everyday': 'everyday', 'intimate': 'intimate'}.get(r.get('mode')) == mode]
                    scopes.append(dict(mode=mode, surface=surface, **comparison(scope_ids, left[judge], right)))
            pairs[judge + '_vs_' + facet] = dict(counterpart=facet, stores=list(stores), retention=retention,
                construct='exploratory_proxy_not_equivalence', recorded_judgment_kind='mixed_classifier_and_embedding' if judge == 'deviation_check' else 'llm_rubric',
                **comparison(ids, left[judge], right), per_scope=scopes)
        output['views'][view_name] = pairs
    return output


def main(argv=None):
    parser = G.Parser(description=__doc__)
    for arg in ('scratch', 'input', 'verdicts', 'cutoff'): parser.add_argument('--' + arg, required=True)
    parser.add_argument('--landings')
    args = parser.parse_args(argv); root = G.private_root(args.scratch)
    def guard(event, values):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(values[2], int) and values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): raise PermissionError('write')
        if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod', 'os.link', 'os.symlink', 'os.fork', 'os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    result = report(G.read(root, args.input), G.read(root, args.landings) if args.landings else None,
                    G.read(root, args.verdicts), args.cutoff)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('judge_agreement_refused', file=sys.stderr); sys.exit(1)
