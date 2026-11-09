"""Retain already computed self-readout evidence in the optional private sink.

These are observations, not a training-time attestation, encoder-weight identity,
final-reply origin, or permission to score. No encoder calls are added.
"""
from collections import Counter
import hashlib
import math
import numbers

COUNTERS = Counter()
MAX_CHECKPOINT = 64 * 1024 * 1024


def _text(value, limit=256):
    return value if isinstance(value, str) and value.strip() and len(value) <= limit else None


def checkpoint(raw, meta):
    from witness_capture import _fingerprint
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CHECKPOINT or not isinstance(meta, dict):
        return None
    if meta.get('mode') not in ('self_ahead', 'self_on_message'):
        return None
    return {'schema': 'self-checkpoint-observation-v1',
            'checkpoint_id': hashlib.sha256(raw).hexdigest(), 'byte_count': len(raw),
            'metadata_sha256': _fingerprint(meta), 'source': _text(meta.get('schema')),
            'mode': meta['mode'], 'reported_trained_through': _text(meta.get('trained_through')),
            'reported_calibrated_through': _text(meta.get('calibrated_through')),
            'reported_trained_at': _text(meta.get('trained_at')),
            'reported_encoder_label': _text(meta.get('encoder')),
            'trained_at': None, 'encoder_id': None,
            'training_completion_evidence': 'unobserved', 'encoder_weights_identity': 'unobserved',
            'weights_retained': False}


def vector(value):
    if not hasattr(value, '__len__') or not 1 <= len(value) <= 8192:
        raise ValueError('invalid vector size')
    if any(isinstance(v, bool) or not isinstance(v, numbers.Real) for v in value):
        raise ValueError('invalid vector values')
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result) or not any(result):
        raise ValueError('invalid vector values')
    return result


def forecast_artifacts(exchanges, bank, model, forecast):
    """Recent-own vectors can cover earlier targets; never claim all targets exist."""
    from witness_receipts import digest
    manifest = model.get('_witness_checkpoint')
    if not isinstance(manifest, dict) or manifest.get('checkpoint_id') != forecast.get('checkpoint_id'):
        COUNTERS['checkpoint_unbound'] += 1
        return None
    selected = [e for e in exchanges if e.get('his')][-6:]
    retained = []
    for row in selected:
        text = row['his']
        if not isinstance(text, str) or not 0 < len(text) <= 65536:
            return None
        encoded = text[:400]
        retained.append({'observed_turn_id': _text(row.get('turn_id')),
                         'normalized_reply_sha256': digest(text), 'encoder_input_sha256': digest(encoded),
                         'encoder_input_chars': len(encoded), 'emb': vector(bank[encoded]),
                         'transform': 'normalized_exchange_his_first_400_codepoints',
                         'source_identity': 'unverified', 'encoder_id': None})
    return {'checkpoint': manifest, 'recent_own_embeddings': retained,
            'coverage': 'selected_recent_own_inputs_only', 'target_finalization': 'unobserved',
            'encoder_weights_identity': 'unobserved'}


class AuditEncoder:
    """Observe the existing self audit's encoded inputs; return its exact output."""
    def __init__(self, enc, ledger, manifest, root):
        from witness_receipts import digest
        from witness_capture import _fingerprint
        self.enc, self.manifest, self.root = enc, manifest, root
        self.refs, self.seen = {}, set()
        if not isinstance(ledger, list) or len(ledger) > 4096:
            raise ValueError('unbounded audit sources')
        for row in ledger:
            if not isinstance(row, dict):
                continue
            raw = row.get('vintos')
            if not isinstance(raw, str) or not 0 < len(raw) <= 65536:
                continue
            text = raw.strip()
            if not text or text in ('--source', 'voice'):
                continue
            ref = {'observed_turn_id': _text(row.get('turn_id')), 'source_row_sha256': _fingerprint(row),
                   'source_reply_sha256': digest(raw), 'normalized_reply_sha256': digest(text)}
            self.refs.setdefault(text[:400], []).append(ref)

    def encode(self, texts, *args, **kwargs):
        result = self.enc.encode(texts, *args, **kwargs)
        try:
            from witness_capture import _publish_private, _private_root
            from witness_receipts import digest
            if not isinstance(texts, list) or len(texts) > 256 or len(result) != len(texts):
                raise ValueError('unbounded audit encoding')
            for text, emb in zip(texts, result):
                if text not in self.refs or text in self.seen:
                    continue
                refs = self.refs[text]
                if len(refs) > 64:
                    COUNTERS['ambiguous_source_limit'] += 1
                    continue
                packet = {'schema': 'self-audit-embedding-v1', 'checkpoint': self.manifest,
                          'encoder_input_sha256': digest(text), 'encoder_input_chars': len(text),
                          'transform': 'ledger_vintos_strip_first_400_codepoints',
                          'emb': vector(emb), 'source_refs': refs, 'source_identity': 'unverified',
                          'coverage': 'self_texts_encoded_by_existing_ranking_audit',
                          'target_selection': 'unasserted', 'encoder_id': None,
                          'encoder_weights_identity': 'unobserved', 'target_finalization': 'unobserved'}
                if _publish_private(_private_root(self.root), packet, 'self-audit-embedding-'):
                    self.seen.add(text)
        except Exception:
            COUNTERS['audit_retention_failed'] += 1
        return result


def audit_encoder(enc, ledger, manifest):
    from witness_capture import _capture_location, _private_root
    if not isinstance(manifest, dict):
        return enc
    location = _capture_location()
    if not location:
        return enc
    return AuditEncoder(enc, ledger, manifest, str(_private_root(location)))
