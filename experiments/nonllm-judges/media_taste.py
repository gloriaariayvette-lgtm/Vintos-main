"""Offline design prototype over supplied media vectors. No I/O or encoding."""
from datetime import datetime, timezone
import math


def stamp(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None: raise ValueError('unknown clock')
    return d.timestamp()


def digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def frozen(encoder, pins):
    """Pins are supplied by an independently reviewed registry, never a model name."""
    if (not isinstance(encoder['id'], str) or not encoder['id']
            or not digest(encoder['artifact_sha256']) or type(encoder['dim']) is not int
            or not 1 <= encoder['dim'] <= 4096): raise ValueError('encoder')
    copied = stamp(encoder['copied_at']); freeze = stamp(encoder['frozen_at'])
    if encoder['freeze_source'] == 'copy_time':
        if freeze != copied: raise ValueError('copy time')
    elif encoder['freeze_source'] == 'published_artifact':
        pin = pins.get((encoder['id'], encoder['artifact_sha256']))
        if (not pin or pin.get('external_pretrained') is not True
                or pin.get('subject_trained') is not False or not digest(pin.get('receipt_sha256'))
                or pin['receipt_sha256'] != encoder.get('pin_receipt_sha256')
                or stamp(pin['published_at']) != freeze or freeze > copied): raise ValueError('pin')
    else: raise ValueError('unknown freeze')
    return freeze, copied


def checked(item, encoder, freeze, copied):
    if (item['kind'] not in ('image', 'video', 'audio') or not digest(item['sha256'])
            or item['media_id'] != 'sha256:'+item['sha256']
            or item['encoder'] != encoder): raise ValueError('identity or encoder')
    created, encoded = stamp(item['created_at']), stamp(item['encoded_at'])
    if freeze >= created or encoded < max(copied, created): raise ValueError('time')
    v = item['vec']
    if (not isinstance(v, list) or len(v) != encoder['dim']
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)):
        raise ValueError('vector')
    norm = math.hypot(*v)
    if not math.isfinite(norm) or norm == 0: raise ValueError('norm')
    return [x/norm for x in v], created


def assess(candidate, items, ratings, encoder, pins, cutoff):
    """Diagnostic similarity only; all claims supplied, no historical cache attestation.

    Frozen snapshot cutoff precedes candidate creation. Latest prior rating per
    exact byte revision wins. Sparse or unverifiable evidence abstains.
    """
    try:
        if len(items) > 4096 or len(ratings) > 4096: raise ValueError('bound')
        freeze, copied = frozen(encoder, pins)
        q, created = checked(candidate, encoder, freeze, copied)
        cut = stamp(cutoff)
        if cut > created: raise ValueError('late cutoff')
        by_id = {}
        for item in items:
            key = item['media_id']
            if key in by_id and by_id[key] != item: raise ValueError('conflicting revision')
            by_id[key] = item
        latest = {}; seen = {}
        for rating in ratings:
            rid = rating['id']
            if not isinstance(rid, str) or not rid: raise ValueError('rating id')
            if rid in seen and seen[rid] != rating: raise ValueError('conflicting rating')
            if rid in seen: continue
            seen[rid] = rating
            at = stamp(rating['at'])
            if at >= cut: continue
            if rating['value'] not in ('landed', 'partly', 'missed'): raise ValueError('rating')
            key = rating['media_id']
            if rating.get('binding') != 'exact_media_revision': raise ValueError('binding')
            if key in latest and at == stamp(latest[key]['at']): raise ValueError('tied rating')
            if key not in latest or at > stamp(latest[key]['at']): latest[key] = rating
        sims = []; days = set()
        for key, rating in latest.items():
            if rating['value'] != 'landed' or key == candidate['media_id']: continue
            item = by_id.get(key)
            if item is None: raise ValueError('missing revision')
            v, made = checked(item, encoder, freeze, copied)
            if item['kind'] != candidate['kind']: continue
            observed = stamp(rating['at'])
            if made > observed or stamp(item['encoded_at']) >= cut: raise ValueError('late evidence')
            sims.append(max(-1., min(1., sum(a*b for a,b in zip(q,v)))))
            days.add(datetime.fromtimestamp(observed, timezone.utc).date())
        if len(sims) < 3 or len(days) < 2:
            return {'status': 'abstain', 'reason': 'sparse_prior_positive_revisions', 'references': len(sims)}
        return {'status': 'diagnostic', 'references': len(sims), 'reference_days_utc': len(days),
                'mean_cosine': sum(sims)/len(sims), 'max_cosine': max(sims),
                'predicts_landing': False, 'source_claims_verified': False}
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        return {'status': 'abstain', 'reason': 'invalid_or_unqualified_evidence'}
