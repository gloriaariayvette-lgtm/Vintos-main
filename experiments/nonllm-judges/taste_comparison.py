#!/usr/bin/env python3
"""Read-only literal profile comparison against explicit private rating snapshots."""
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('taste_comparison_io', Path(__file__).with_name('landings_project.py'))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
G = L.G
KINDS = ('likes', 'dislikes', 'principles')
RATINGS = ('landed', 'partly', 'missed')
TEXT = {'message': 'message', 'joke': 'joke', 'journal': 'entry'}
MEDIA = {'image': ('prompt', 'seen'), 'video': ('prompt', 'said'), 'song': ('felt_sense', 'want_text', 'style')}


def tokens(text):
    return tuple(re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold()))


def phrases(profile):
    if not isinstance(profile, dict) or not set(profile).intersection(KINDS): raise ValueError('profile shape')
    out = {}; counts = {}
    for kind in KINDS:
        rows = profile.get(kind, [])
        if not isinstance(rows, list) or len(rows) > 500: raise ValueError('profile bound')
        if any(not isinstance(x, str) or not 0 < len(x) <= 2048 or not tokens(x) for x in rows):
            raise ValueError('profile phrase')
        out[kind] = set(map(tokens, rows))
        counts[kind+'_phrases'] = len(out[kind])
        counts[kind+'_duplicates'] = len(rows)-len(out[kind])
    counts['unsupported_profile_fields'] = len(set(profile)-set(KINDS))
    return out, counts


def documents(row):
    kind = row['surface']; made = row.get('made'); piece = row.get('piece')
    if not isinstance(made, dict) or not isinstance(piece, dict) or piece.get('type') != kind: return []
    if kind in TEXT:
        value = piece.get('text')
        if not isinstance(value, str) or value != made.get(TEXT[kind]): return []
        values = [value]
    elif kind in MEDIA:
        values = [made.get(key, '') for key in MEDIA[kind]]
    else: return []
    if any(not isinstance(x, str) or len(x) > 10000 for x in values): return []
    return [part for x in values if (part := tokens(x))]


def matched(needles, docs):
    haystacks = ['\0'+'\0'.join(doc)+'\0' for doc in docs]
    return any('\0'+'\0'.join(phrase)+'\0' in doc for phrase in needles for doc in haystacks)


def compare(profile, records, cutoff, source_zone=None):
    needles, profile_counts = phrases(profile)
    cut = L.instant(cutoff)
    if not isinstance(records, list) or len(records) > L.LIMIT: raise ValueError('record bound')
    counts = Counter(dict(input_records=len(records), duplicate_records=0, at_or_after_cutoff=0,
        unknown_time=0, superseded_records=0, ambiguous_items=0, invalid_rating=0,
        unsupported_piece=0, compared_items=0, text_items=0, media_description_items=0,
        like_only=0, dislike_only=0, both=0, neither=0, principle_match=0,
        decisive_proxy_items=0, literal_proxy_agreements=0))
    seen = {}; latest = {}; poisoned = set()
    for row in records:
        if (not isinstance(row, dict) or not L.identifier(row.get('id')) or not L.identifier(row.get('ref'))
                or not isinstance(row.get('surface'), str)): raise ValueError('identity')
        rid = row['id']; key = (row['surface'], row['ref']); encoded = L.canonical(row)
        if rid in seen:
            if seen[rid] != encoded: raise ValueError('conflicting record')
            counts['duplicate_records'] += 1; continue
        seen[rid] = encoded
        try: at = L.instant(row.get('at'), source_zone)
        except (ValueError, TypeError, OverflowError):
            poisoned.add(key); counts['unknown_time'] += 1; continue
        if at >= cut: counts['at_or_after_cutoff'] += 1; continue
        if key in latest:
            counts['superseded_records'] += 1
            # Retain physical append order, refusing backward or tied observations.
            if at <= latest[key][1]: poisoned.add(key)
        latest[key] = row, at
    table = {group: {rating: 0 for rating in RATINGS} for group in ('like_only','dislike_only','both','neither')}
    for key, (row, _) in latest.items():
        if key in poisoned: counts['ambiguous_items'] += 1; continue
        rating = row.get('rating')
        if rating not in RATINGS or not isinstance(row.get('why'), str) or not row['why'].strip():
            counts['invalid_rating'] += 1; continue
        docs = documents(row)
        if not docs: counts['unsupported_piece'] += 1; continue
        like, dislike = matched(needles['likes'], docs), matched(needles['dislikes'], docs)
        group = 'both' if like and dislike else 'like_only' if like else 'dislike_only' if dislike else 'neither'
        counts['compared_items'] += 1
        counts['text_items' if key[0] in TEXT else 'media_description_items'] += 1
        counts[group] += 1; table[group][rating] += 1
        counts['principle_match'] += int(matched(needles['principles'], docs))
        if group in ('like_only','dislike_only') and rating in ('landed','missed'):
            counts['decisive_proxy_items'] += 1
            counts['literal_proxy_agreements'] += int((group, rating) in (('like_only','landed'),('dislike_only','missed')))
    denominator = counts['decisive_proxy_items']
    return dict(schema='taste-profile-comparison-counts-v1', profile_counts=profile_counts,
        counts=dict(counts), literal_overlap_by_rating=table,
        agreement_rates={'literal_polarity_proxy': counts['literal_proxy_agreements']/denominator if denominator else None},
        comparison_only=True, semantic_agreement_measured=False, historical_prediction=False,
        anchors_emitted=0, labels_emitted=0, training_signals_emitted=0, policy_inputs_emitted=0)


def main(argv=None):
    parser = G.Parser(description=__doc__)
    for key in ('scratch', 'profile', 'landings', 'cutoff'): parser.add_argument('--'+key, required=True)
    parser.add_argument('--source-timezone')
    args = parser.parse_args(argv); root = G.private_root(args.scratch)
    def guard(event, values):
        if event.startswith(('socket.', 'subprocess.', 'os.spawn', 'os.exec', 'os.system')): raise PermissionError('external operation')
        if event == 'open' and isinstance(values[2], int) and values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): raise PermissionError('write')
        if event in ('os.mkdir','os.remove','os.rename','os.rmdir','os.chmod','os.link','os.symlink','os.fork','os.forkpty'): raise PermissionError('mutation')
    sys.addaudithook(guard)
    report = compare(G.read(root, args.profile), L.read_jsonl(root, args.landings), args.cutoff, args.source_timezone)
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('taste_comparison_refused', file=sys.stderr); sys.exit(1)
