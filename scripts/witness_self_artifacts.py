"""Retain already computed self-readout evidence in the optional private sink.

These are observations, not a training-time attestation, encoder-weight identity,
final-reply origin, or permission to score. No encoder calls are added.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib
import math
import numbers
import time

COUNTERS = Counter()
MAX_CHECKPOINT = 64 * 1024 * 1024
MAX_AUDIT_OBSERVATIONS = 8192
_source_scope = ContextVar("self_audit_sources", default=None)


def _text(value, limit=256):
    return value if isinstance(value, str) and value.strip() and len(value) <= limit else None


def checkpoint(raw, meta, availability=None):
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
            'weights_retained': False, 'availability': availability_receipt(availability)}


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
                         'vector_representation': 'readout_units_v1',
                         'source_identity': 'unverified', 'encoder_id': None,
                         'reply_source': bound_source(row.get('_witness_reply_source'), text, row.get('turn_id'))})
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
                   'source_reply_sha256': digest(raw), 'normalized_reply_sha256': digest(text),
                   'reply_source': bound_source(row.get('_witness_reply_source'), raw, row.get('turn_id'))}
            self.refs.setdefault(text[:400], []).append(ref)

    def encode(self, texts, *args, **kwargs):
        result = self.enc.encode(texts, *args, **kwargs)
        try:
            from witness_capture import _publish_private, _private_root, _fingerprint
            from witness_receipts import digest
            if not isinstance(texts, list) or len(texts) > 256 or len(result) != len(texts):
                raise ValueError('unbounded audit encoding')
            for text, emb in zip(texts, result):
                if text not in self.refs:
                    continue
                values = vector(emb)
                observation = (digest(text), _fingerprint(values))
                if observation in self.seen:
                    continue
                if len(self.seen) >= MAX_AUDIT_OBSERVATIONS:
                    COUNTERS['audit_observation_limit'] += 1
                    continue
                refs = self.refs[text]
                if len(refs) > 64:
                    COUNTERS['ambiguous_source_limit'] += 1
                    continue
                packet = {'schema': 'self-audit-embedding-v1', 'checkpoint': self.manifest,
                          'encoder_input_sha256': digest(text), 'encoder_input_chars': len(text),
                          'transform': 'ledger_vintos_strip_first_400_codepoints',
                          'vector_representation': 'encoder_return_v1',
                          'emb': values, 'source_refs': refs, 'source_identity': 'unverified',
                          'coverage': 'self_texts_encoded_by_existing_ranking_audit',
                          'target_selection': 'unasserted', 'encoder_id': None,
                          'encoder_weights_identity': 'unobserved', 'target_finalization': 'unobserved'}
                if _publish_private(_private_root(self.root), packet, 'self-audit-embedding-'):
                    self.seen.add(observation)
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


@contextmanager
def audit_source_scope():
    """Scope optional source metadata; an unavailable sink changes no source read."""
    root = None
    try:
        from witness_capture import _capture_location, _private_root
        location = _capture_location()
        if location:
            root = str(_private_root(location))
    except Exception:
        pass
    token = _source_scope.set(root)
    try:
        yield root
    finally:
        _source_scope.reset(token)


def reply_source(row, field, normalized):
    """Observe the exact source row and actual reader output before cleanup is lost."""
    from witness_capture import _fingerprint
    from witness_receipts import digest
    if (not isinstance(row, dict) or len(row) > 128 or field not in ('content', 'vintos')
            or not isinstance(row.get(field), str) or not 0 < len(row[field]) <= 65536
            or not isinstance(normalized, str) or not 0 < len(normalized) <= 65536):
        return None
    if len(json.dumps(row, ensure_ascii=True, allow_nan=False)) > 262144:
        return None
    return {'schema': 'self-reply-source-v1', 'source_field': field,
            'source_row_sha256': _fingerprint(row), 'source_reply_sha256': digest(row[field]),
            'normalized_reply_sha256': digest(normalized),
            'observed_turn_id': _text(row.get('turn_id')), 'observed_surface': _text(row.get('surface')),
            'transform': 'self_reader_his_words', 'source_identity': 'unverified'}


def bound_source(value, normalized, selected_id):
    """No clock-based ID backfill; metadata must travel with the selected text/ID."""
    from witness_receipts import digest
    if (not isinstance(value, dict) or set(value) != {'schema', 'source_field', 'source_row_sha256',
            'source_reply_sha256', 'normalized_reply_sha256', 'observed_turn_id', 'observed_surface',
            'transform', 'source_identity'} or value['schema'] != 'self-reply-source-v1'
            or value['source_field'] not in ('content', 'vintos')
            or value['transform'] != 'self_reader_his_words' or value['source_identity'] != 'unverified'
            or not isinstance(normalized, str) or value['normalized_reply_sha256'] != digest(normalized)):
        return None
    for key in ('source_row_sha256', 'source_reply_sha256', 'normalized_reply_sha256'):
        v = value[key]
        if not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v):
            return None
    for key in ('observed_turn_id', 'observed_surface'):
        if value[key] is not None and _text(value[key]) != value[key]:
            return None
    # Legacy readers stringify IDs. Never upgrade a non-string original identifier.
    if value['observed_turn_id'] is not None and value['observed_turn_id'] != _text(selected_id):
        return None
    return dict(value)


def ledger_rows(exchanges, retain=False):
    """Same three audit fields; optional private metadata only for the chosen source."""
    result = []
    for exchange in exchanges:
        row = {'timestamp': exchange['ts'], 'gloria': exchange['her'], 'vintos': exchange['his']}
        if retain:
            try:
                ref = bound_source(exchange.get('_witness_reply_source'), exchange['his'], exchange.get('turn_id'))
                if ref is not None:
                    row['_witness_reply_source'] = ref
                    row['turn_id'] = ref['observed_turn_id']
            except Exception:
                pass
        result.append(row)
    return result


def begin_checkpoint_read():
    """Two clock readings only; no filesystem, model or encoder invocation."""
    return (time.time(), time.monotonic())


def finish_checkpoint_read(start, stage="parameters_loaded"):
    return availability_receipt({'read_started_at': start[0], 'parsed_at': time.time(),
                                 'monotonic_elapsed': time.monotonic() - start[1], 'stage': stage})


def availability_receipt(value):
    """Availability of parsed parameters is not their training-completion timestamp."""
    missing = {'schema': 'checkpoint-availability-v1', 'state': 'unobserved',
               'parameters_available_by': None, 'bytes_observed_by': None, 'stage': None,
               'meaning': 'checkpoint_read_observation_not_training_time'}
    if value is None:
        return missing
    if not isinstance(value, dict):
        return missing
    # Revalidation preserves a finished receipt, including an explicit clock gap.
    if value.get('schema') == 'checkpoint-availability-v1':
        expected = set(missing) | {'read_started_at', 'parsed_at', 'monotonic_elapsed'}
        if set(value) == set(missing) and value == missing:
            return missing
        if (set(value) != expected or value.get('meaning') != missing['meaning']
                or (value.get('parameters_available_by') is not None
                    and type(value['parameters_available_by']) not in (int,float))
                or (value.get('bytes_observed_by') is not None
                    and type(value['bytes_observed_by']) not in (int,float))):
            return missing
        candidate = availability_receipt({k:value[k] for k in ('read_started_at','parsed_at','monotonic_elapsed','stage')})
        return candidate if candidate == value else missing
    if (set(value) != {'read_started_at','parsed_at','monotonic_elapsed','stage'}
            or value.get('stage') not in ('parameters_loaded','metadata_loaded')):
        return missing
    if any(type(value[k]) not in (int,float) or not math.isfinite(value[k]) for k in ('read_started_at','parsed_at','monotonic_elapsed')):
        return missing
    start, parsed, elapsed = (value[k] for k in ('read_started_at','parsed_at','monotonic_elapsed'))
    if start < 0 or parsed < 0 or elapsed < 0 or elapsed > 600:
        return missing
    consistent = parsed >= start and abs((parsed-start)-elapsed) <= 1.0
    return dict(missing, **value, state='observed' if consistent else 'clock_discontinuity',
                bytes_observed_by=parsed if consistent else None,
                parameters_available_by=parsed if consistent and value['stage']=='parameters_loaded' else None)
