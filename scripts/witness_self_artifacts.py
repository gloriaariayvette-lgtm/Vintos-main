"""Retain already computed self-readout evidence in the optional private sink.

These are observations, not a training-time attestation, encoder-weight identity,
final-reply origin, or permission to score. No encoder calls are added.
"""
from collections import Counter, OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib
import math
import numbers
import time
import sys
import uuid

COUNTERS = Counter()
MAX_CHECKPOINT = 64 * 1024 * 1024
MAX_AUDIT_OBSERVATIONS = 8192
MAX_ENCODER_STATE_BYTES = 1024 * 1024 * 1024
MAX_ENCODER_TENSORS = 8192
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



def checkpoint_observed_fields(value):
    """Validate this producer's manifest shape; legacy identity-only data stays unknown."""
    def hashed(v):
        return isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v)
    if not isinstance(value,dict) or not hashed(value.get('checkpoint_id')):
        raise ValueError('invalid checkpoint observation identity')
    if value.get('schema') is None:
        return None
    required = {'schema','checkpoint_id','byte_count','metadata_sha256','source','mode',
                'reported_trained_through','reported_calibrated_through','reported_trained_at',
                'reported_encoder_label','trained_at','encoder_id','training_completion_evidence',
                'encoder_weights_identity','weights_retained'}
    if (set(value)-{'availability'}!=required or value['schema']!='self-checkpoint-observation-v1'
            or type(value['byte_count']) is not int or not 0<value['byte_count']<=MAX_CHECKPOINT
            or not hashed(value['metadata_sha256']) or value['mode'] not in ('self_ahead','self_on_message')
            or value['trained_at'] is not None or value['encoder_id'] is not None
            or value['training_completion_evidence']!='unobserved'
            or value['encoder_weights_identity']!='unobserved' or value['weights_retained'] is not False):
        raise ValueError('invalid checkpoint observation contract')
    for key in ('source','reported_trained_through','reported_calibrated_through','reported_trained_at','reported_encoder_label'):
        if value[key] is not None and _text(value[key]) != value[key]:
            raise ValueError('invalid reported checkpoint field')
    if 'availability' in value and availability_receipt(value['availability'])!=value['availability']:
        raise ValueError('invalid checkpoint availability observation')
    # Read clocks vary across uses of identical bytes and are compared separately.
    return {key:value[key] for key in sorted(required-{'schema','checkpoint_id'})}


def vector(value):
    if not hasattr(value, '__len__') or not 1 <= len(value) <= 8192:
        raise ValueError('invalid vector size')
    if any(isinstance(v, bool) or not isinstance(v, numbers.Real) for v in value):
        raise ValueError('invalid vector values')
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result) or not any(result):
        raise ValueError('invalid vector values')
    return result


def forecast_artifacts(exchanges, bank, model, forecast, encoding_records=None):
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
                         'encoding_link': forecast_encoding_link(encoded, bank[encoded], encoding_records),
                         'source_identity': 'unverified', 'encoder_id': None,
                         'reply_source': bound_source(row.get('_witness_reply_source'), text, row.get('turn_id'))})
    return {'checkpoint': manifest, 'recent_own_embeddings': retained,
            'coverage': 'selected_recent_own_inputs_only', 'target_finalization': 'unobserved',
            'encoder_weights_identity': 'unobserved'}



def parameter_snapshot(enc):
    """Hash already loaded CPU parameters/buffers; no load, transfer or encode."""
    unavailable = {'schema': 'encoder-parameter-snapshot-v1', 'state': 'unavailable',
                   'sha256': None, 'tensors': 0, 'bytes': 0}
    try:
        import numpy as np
        state = enc.state_dict()
        if (not isinstance(state, dict) or not 0 < len(state) <= MAX_ENCODER_TENSORS
                or any(not isinstance(k, str) or not 0 < len(k) <= 1024 for k in state)):
            return unavailable
        torch = sys.modules.get('torch')
        arrays, total = [], 0
        for name in sorted(state):
            value = state[name]
            if isinstance(value, np.ndarray):
                if value.dtype.kind not in 'biufc': return unavailable
                count = value.nbytes
                descriptor = [name, 'numpy', value.dtype.str, list(value.shape)]
            elif torch is not None and isinstance(value, torch.Tensor):
                if value.device.type != 'cpu' or value.layout != torch.strided:
                    return unavailable
                count = value.numel() * value.element_size()
                descriptor = [name, 'torch', str(value.dtype), list(value.shape)]
            else: return unavailable
            total += count
            if total > MAX_ENCODER_STATE_BYTES: return unavailable
            arrays.append((value, descriptor))
        if not total: return unavailable
        h = hashlib.sha256(b'encoder-parameter-snapshot-v1\x00')
        for value, descriptor in arrays:
            header = json.dumps(descriptor, separators=(',', ':'), ensure_ascii=True).encode()
            h.update(len(header).to_bytes(8, 'big')); h.update(header)
            if isinstance(value, np.ndarray):
                raw = memoryview(np.ascontiguousarray(value)).cast('B')
            else:
                # CPU only; the byte view also handles scalar and reduced-precision tensors.
                raw = memoryview(value.detach().contiguous().reshape(-1).view(torch.uint8).numpy()).cast('B')
            h.update(len(raw).to_bytes(8, 'big')); h.update(raw)
        return dict(unavailable, state='observed', sha256=h.hexdigest(), tensors=len(arrays), bytes=total)
    except Exception:
        return unavailable


def parameter_state(before, after):
    if before['state'] != 'observed' or after['state'] != 'observed': return 'unavailable'
    return 'observed_equal' if before == after else 'observed_changed'


TIMING_STAGES = ('parameter_before_seconds', 'encode_seconds', 'parameter_after_seconds')

RUNTIME_COUNTS = ('modules', 'module_settings', 'configs', 'tokenizers',
                  'tokenizer_settings', 'runtime_versions')
RUNTIME_FIELDS = ('training', 'max_seq_length', 'do_lower_case', 'truncate_dim',
                  'prompts', 'default_prompt_name', '_similarity_fn_name')
TOKENIZER_FIELDS = ('init_kwargs', 'model_max_length', 'padding_side', 'truncation_side',
                    'clean_up_tokenization_spaces', 'split_special_tokens')
RUNTIME_PACKAGES = ('sentence_transformers', 'transformers', 'tokenizers', 'torch', 'numpy')


def runtime_snapshot(enc):
    """Hash bounded stored fields only; never call config/tokenizer methods or load files.

    Deliberately partial: encoder and two child levels, not every leaf module.
    Vocabulary, backend tokenizer bytes, code, hardware and fitting remain unknown.
    Unsupported fields are distinguished from absent fields inside the digest.
    """
    unavailable = dict(schema='encoder-runtime-snapshot-v1', state='unavailable', sha256=None,
                       **dict.fromkeys(RUNTIME_COUNTS, 0))
    try:
        budget = [4096, 65536]

        def plain(value, depth=0):
            budget[0] -= 1
            if budget[0] < 0 or depth > 12: raise ValueError('runtime field bound')
            if value is None or type(value) is bool: return value
            if type(value) is int and value.bit_length() <= 128: return value
            if type(value) is float and math.isfinite(value): return value
            if type(value) is str:
                budget[1] -= len(value)
                if budget[1] < 0: raise ValueError('runtime string bound')
                return value
            if type(value) in (list, tuple) and len(value) <= 1024:
                return [plain(v, depth+1) for v in value]
            if type(value) in (dict, OrderedDict) and len(value) <= 1024:
                if any(type(k) is not str for k in value): raise TypeError('runtime key type')
                return {plain(k, depth+1):plain(value[k], depth+1) for k in sorted(value)}
            raise TypeError('unsupported stored runtime value')

        def stored(obj):
            try: value = object.__getattribute__(obj, '__dict__')
            except Exception: return None
            return value if type(value) is dict else None

        def component(value):
            try: return ['observed', plain(value)]
            except TypeError: return ['unsupported', None]

        counts = dict.fromkeys(RUNTIME_COUNTS, 0)
        rows, pending = [], [((), enc, 0)]
        while pending:
            path, obj, depth = pending.pop(0)
            counts['modules'] += 1
            if counts['modules'] > 64: return unavailable
            data = stored(obj)
            if data is None: return unavailable
            cls = type(obj)
            row = [path, plain([cls.__module__, cls.__qualname__])]
            fields = {k:data[k] for k in RUNTIME_FIELDS if k in data}
            observed = component(fields) if fields else ['absent', None]
            counts['module_settings'] += int(observed[0] == 'observed')
            row.append(observed)
            config = stored(data['config']) if 'config' in data else None
            observed = component(config) if config is not None else ['unavailable', None]
            counts['configs'] += int(observed[0] == 'observed')
            row.append(observed)
            tokenizer = stored(data['tokenizer']) if 'tokenizer' in data else None
            counts['tokenizers'] += int(tokenizer is not None)
            fields = {k:tokenizer[k] for k in TOKENIZER_FIELDS if k in tokenizer} if tokenizer is not None else {}
            observed = component(fields) if fields else ['unavailable', None]
            counts['tokenizer_settings'] += int(observed[0] == 'observed')
            row.append(observed)
            children = data.get('_modules', {})
            if type(children) not in (dict, OrderedDict) or len(children) > 64: return unavailable
            if any(type(k) is not str or len(k) > 256 for k in children): return unavailable
            # Preserve child order: sequential encoders can change behavior when reordered.
            row.append(list(children))
            rows.append(row)
            if depth < 2:
                pending.extend((path+(k,), v, depth+1) for k,v in children.items() if v is not None)
                if len(pending)+counts['modules'] > 64: return unavailable
        versions = {}
        for name in RUNTIME_PACKAGES:
            data = stored(sys.modules[name]) if name in sys.modules else None
            version = data.get('__version__') if data is not None else None
            versions[name] = plain(version) if type(version) is str else None
            counts['runtime_versions'] += int(versions[name] is not None)
        raw = json.dumps([rows, versions], sort_keys=True, ensure_ascii=True, allow_nan=False,
                         separators=(',', ':')).encode()
        if len(raw) > 131072: return unavailable
        return dict(unavailable, state='observed', sha256=hashlib.sha256(raw).hexdigest(), **counts)
    except Exception:
        return unavailable


def validate_runtime_observation(value):
    if (not isinstance(value, dict) or set(value) != {'schema','before','after','state','scope'}
            or value['schema'] != 'encoder-runtime-observation-v1'
            or value['scope'] != 'stored_fields_two_child_levels_not_tokenizer_content_code_or_fitting'):
        raise ValueError('invalid runtime observation')
    for key in ('before', 'after'):
        snap = value[key]
        if (not isinstance(snap, dict) or set(snap) != {'schema','state','sha256',*RUNTIME_COUNTS}
                or snap['schema'] != 'encoder-runtime-snapshot-v1'
                or any(type(snap[k]) is not int or not 0 <= snap[k] <= 64 for k in RUNTIME_COUNTS)
                or snap['runtime_versions'] > len(RUNTIME_PACKAGES)
                or any(snap[k] > snap['modules'] for k in ('module_settings','configs','tokenizers'))
                or snap['tokenizer_settings'] > snap['tokenizers']):
            raise ValueError('invalid runtime snapshot')
        if snap['state'] == 'observed':
            h = snap['sha256']
            if (not snap['modules'] or not isinstance(h,str) or len(h)!=64
                    or any(c not in '0123456789abcdef' for c in h)):
                raise ValueError('invalid runtime fingerprint')
        elif (snap['state'] != 'unavailable' or snap['sha256'] is not None
              or any(snap[k] for k in RUNTIME_COUNTS)):
            raise ValueError('invalid unavailable runtime snapshot')
    if value['state'] != parameter_state(value['before'],value['after']):
        raise ValueError('inconsistent runtime comparison')


def _clock():
    try:
        value = time.perf_counter()
        return value if type(value) in (int,float) and math.isfinite(value) else None
    except Exception:
        return None


def _elapsed(start, stop):
    if start is None or stop is None: return None
    elapsed = stop-start
    return elapsed if math.isfinite(elapsed) and 0 <= elapsed <= 86400 else None


ENTRYPOINT_SCOPE = 'python_entry_code_not_globals_defaults_closures_helpers_or_native_code'


def entrypoint_snapshot(call):
    """Fingerprint already loaded Python code only, excluding file/line locations."""
    import types
    missing = dict(schema='encode-python-code-v1', state='unavailable', sha256=None,
                   code_objects=0, observed_bytes=0)
    try:
        if type(call) is types.MethodType: call = call.__func__
        if type(call) is not types.FunctionType: return missing
        budget = [8192, 1024*1024, 128]

        def charged(raw):
            budget[1] -= len(raw)
            if budget[1] < 0: raise ValueError('entrypoint byte bound')
            return raw.hex()

        def visit(value, depth=0):
            budget[0] -= 1
            if budget[0]<0 or depth>16: raise ValueError('entrypoint traversal bound')
            if value is None: return ['none']
            if value is Ellipsis: return ['ellipsis']
            if type(value) is bool: return ['bool',value]
            if type(value) is int:
                if value.bit_length()>4096: raise ValueError('entrypoint integer bound')
                return ['int',charged(str(value).encode())]
            if type(value) is float: return ['float',charged(value.hex().encode())]
            if type(value) is complex: return ['complex',visit(value.real,depth+1),visit(value.imag,depth+1)]
            if type(value) is str:
                if len(value)>budget[1]: raise ValueError('entrypoint string bound')
                return ['str',charged(value.encode('utf-8','surrogatepass'))]
            if type(value) is bytes: return ['bytes',charged(value)]
            if type(value) in (tuple,frozenset):
                if len(value)>8192: raise ValueError('entrypoint sequence bound')
                items=[visit(v,depth+1) for v in value]
                if type(value) is frozenset: items.sort(key=lambda v:json.dumps(v,separators=(',',':')))
                return ['tuple' if type(value) is tuple else 'frozenset',items]
            if type(value) is types.CodeType:
                budget[2]-=1
                if budget[2]<0: raise ValueError('entrypoint code bound')
                fields=('co_argcount','co_posonlyargcount','co_kwonlyargcount','co_nlocals','co_stacksize',
                        'co_flags','co_code','co_consts','co_names','co_varnames','co_freevars','co_cellvars',
                        'co_exceptiontable')
                return ['code',[(k,visit(getattr(value,k,None),depth+1)) for k in fields]]
            raise ValueError('unsupported entrypoint constant')

        body = visit(call.__code__)
        raw = json.dumps([sys.implementation.name,list(sys.version_info[:2]),body],
                         ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>4*1024*1024: return missing
        return dict(missing,state='observed',sha256=hashlib.sha256(raw).hexdigest(),
                    code_objects=128-budget[2],observed_bytes=1024*1024-budget[1])
    except Exception:
        return missing


def validate_entrypoint_observation(value):
    if (not isinstance(value,dict) or set(value)!={'schema','before','after','state','scope'}
            or value['schema']!='encode-entrypoint-observation-v1' or value['scope']!=ENTRYPOINT_SCOPE):
        raise ValueError('invalid encode entrypoint observation')
    for key in ('before','after'):
        snap=value[key]
        if (not isinstance(snap,dict) or set(snap)!={'schema','state','sha256','code_objects','observed_bytes'}
                or snap['schema']!='encode-python-code-v1'
                or type(snap['code_objects']) is not int or type(snap['observed_bytes']) is not int):
            raise ValueError('invalid encode entrypoint snapshot')
        if snap['state']=='observed':
            h=snap['sha256']
            if (not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h)
                    or not 1<=snap['code_objects']<=128 or not 1<=snap['observed_bytes']<=1024*1024):
                raise ValueError('invalid encode entrypoint fingerprint')
        elif (snap['state']!='unavailable' or snap['sha256'] is not None
              or snap['code_objects']!=0 or snap['observed_bytes']!=0):
            raise ValueError('invalid unavailable entrypoint snapshot')
    if value['state']!=parameter_state(value['before'],value['after']):
        raise ValueError('inconsistent encode entrypoint comparison')


def observed_encode(enc, texts, args, kwargs, sample, runtime=None, entrypoint=None):
    """Time existing work; observer failures never retry or replace the encode."""
    missing = {'schema':'encoder-parameter-snapshot-v1','state':'unavailable',
               'sha256':None,'tensors':0,'bytes':0}
    before = after = missing
    timing = dict.fromkeys(TIMING_STAGES)
    timing['schema'] = 'encoder-call-timing-v1'
    if sample:
        start = _clock()
        try: before = parameter_snapshot(enc)
        except Exception: pass
        timing['parameter_before_seconds'] = _elapsed(start,_clock())
    if runtime is not None:
        try: runtime['before'] = runtime_snapshot(enc)
        except Exception: pass
    if entrypoint is not None:
        call = enc.encode  # Resolve the actual callable once, at the existing call boundary.
        try: entrypoint['before'] = entrypoint_snapshot(call)
        except Exception: pass
        start = _clock()
        result = call(texts,*args,**kwargs)
    else:
        start = _clock()
        result = enc.encode(texts,*args,**kwargs)
    timing['encode_seconds'] = _elapsed(start,_clock())
    if entrypoint is not None:
        try:
            entrypoint['after'] = entrypoint_snapshot(call)
            entrypoint.update(schema='encode-entrypoint-observation-v1',scope=ENTRYPOINT_SCOPE,
                              state=parameter_state(entrypoint['before'],entrypoint['after']))
            validate_entrypoint_observation(entrypoint)
        except Exception: entrypoint.clear()
    if runtime is not None:
        try:
            runtime['after'] = runtime_snapshot(enc)
            runtime.update(schema='encoder-runtime-observation-v1',
                           state=parameter_state(runtime['before'],runtime['after']),
                           scope='stored_fields_two_child_levels_not_tokenizer_content_code_or_fitting')
            validate_runtime_observation(runtime)
        except Exception: runtime.clear()
    if sample:
        start = _clock()
        try: after = parameter_snapshot(enc)
        except Exception: pass
        timing['parameter_after_seconds'] = _elapsed(start,_clock())
    return result,before,after,timing


def validate_call_timing(value):
    if (not isinstance(value,dict) or set(value) != {'schema',*TIMING_STAGES}
            or value['schema'] != 'encoder-call-timing-v1'):
        raise ValueError('invalid encoding timing')
    for key in TIMING_STAGES:
        v = value[key]
        if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=86400):
            raise ValueError('invalid encoding timing')


def encoding_observation(text, values, before, after, settings, invocation, timing=None, runtime=None, entrypoint=None):
    from witness_receipts import digest
    from witness_capture import _fingerprint
    observation = {'schema': 'audit-encoding-observation-v1', 'invocation': invocation,
            'input_sha256': digest(text), 'raw_vector_sha256': _fingerprint(values),
            'settings_sha256': settings, 'parameter_before': before, 'parameter_after': after,
            'parameter_state': parameter_state(before, after),
            'encoder_identity': 'unverified',
            'meaning': 'loaded_cpu_parameter_snapshots_only_not_tokenizer_code_or_training_identity'}
    if timing is not None:
        validate_call_timing(timing)
        observation['timing'] = dict(timing)
    if runtime:
        validate_runtime_observation(runtime)
        observation['runtime'] = json.loads(json.dumps(runtime))
    if entrypoint:
        validate_entrypoint_observation(entrypoint)
        observation['entrypoint'] = json.loads(json.dumps(entrypoint))
    return observation


def validate_encoding_observation(observation, text_hash, values, expected_schema='audit-encoding-observation-v1'):
    """Validate binding, never turn parameter equality into complete encoder identity."""
    from witness_capture import _fingerprint
    def ishash(value):
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
    if observation is None: return 'missing'
    expected = {'schema','invocation','input_sha256','raw_vector_sha256','settings_sha256',
                'parameter_before','parameter_after','parameter_state','encoder_identity','meaning'}
    if (not isinstance(observation,dict) or set(observation)-{'timing','runtime','entrypoint'} != expected
            or observation['schema'] != expected_schema
            or observation['encoder_identity'] != 'unverified'
            or observation['meaning'] != 'loaded_cpu_parameter_snapshots_only_not_tokenizer_code_or_training_identity'
            or not isinstance(observation['invocation'],str) or len(observation['invocation']) != 32
            or any(c not in '0123456789abcdef' for c in observation['invocation'])
            or not ishash(observation['input_sha256']) or observation['input_sha256'] != text_hash
            or observation['raw_vector_sha256'] != _fingerprint(values)
            or (observation['settings_sha256'] is not None and not ishash(observation['settings_sha256']))):
        raise ValueError('invalid encoding observation')
    if 'timing' in observation: validate_call_timing(observation['timing'])
    if 'runtime' in observation: validate_runtime_observation(observation['runtime'])
    if 'entrypoint' in observation: validate_entrypoint_observation(observation['entrypoint'])
    for key in ('parameter_before','parameter_after'):
        snap = observation[key]
        if (not isinstance(snap,dict) or set(snap) != {'schema','state','sha256','tensors','bytes'}
                or snap['schema'] != 'encoder-parameter-snapshot-v1'
                or type(snap['tensors']) is not int or type(snap['bytes']) is not int):
            raise ValueError('invalid parameter snapshot')
        if snap['state'] == 'observed':
            if not ishash(snap['sha256']) or not 0 < snap['tensors'] <= MAX_ENCODER_TENSORS or not 0 < snap['bytes'] <= MAX_ENCODER_STATE_BYTES:
                raise ValueError('invalid parameter snapshot')
        elif snap['state'] != 'unavailable' or snap['sha256'] is not None or snap['tensors'] != 0 or snap['bytes'] != 0:
            raise ValueError('invalid parameter snapshot')
    state = parameter_state(observation['parameter_before'], observation['parameter_after'])
    if observation['parameter_state'] != state: raise ValueError('inconsistent parameter comparison')
    return state



class FeatureEncoder:
    """Observe existing feature encoding only; never change its output or retry it."""
    def __init__(self, enc):
        self.enc, self.records, self._parameter_pairs = enc, {}, 1
        self._retained_values = 0

    def encode(self, texts, *args, **kwargs):
        sampled = False
        try:
            sampled = bool(self._parameter_pairs)
            if sampled: self._parameter_pairs -= 1
        except Exception: pass
        runtime, entrypoint = {}, {}
        result,before,after,timing = observed_encode(self.enc,texts,args,kwargs,sampled,runtime,entrypoint)
        try:
            from witness_receipts import digest
            if (not isinstance(texts,list) or len(texts)>256 or len(result)!=len(texts)
                    or any(not isinstance(t,str) or not 0 < len(t)<=65536 for t in texts)):
                raise ValueError('unbounded encoding inputs')
            values = [vector(v) for v in result]
            if sum(map(len,values))>65536: raise ValueError('unbounded feature observations')
            try:
                options=json.dumps([args,kwargs],sort_keys=True,allow_nan=False)
                settings=digest(options) if len(options)<=4096 else None
            except Exception: settings=None
            invocation=uuid.uuid4().hex
            for text, raw in zip(texts,values):
                if text in self.records: continue  # Bank entries were filled by the first call.
                if len(self.records)>=256 or self._retained_values+len(raw)>65536:
                    COUNTERS['feature_encoding_observation_limit'] += 1
                    break
                self._retained_values += len(raw)
                observation=encoding_observation(text,raw,before,after,settings,invocation,timing,runtime,entrypoint)
                observation['schema']='forecast-encoding-observation-v1'
                self.records[text]={'schema':'readout-encoding-link-v1','transform':'readout_units_v1',
                                    'raw_emb':raw,'call':observation}
        except Exception:
            COUNTERS['feature_encoding_observation_failed'] += 1
        return result


def forecast_encoding_link(text, stored, records):
    """Copy only a validated link for this exact input and normalized bank value."""
    if records is None: return None
    from witness_receipts import digest
    value=records.get(text) if isinstance(records,dict) else None
    if value is None: return None
    validate_forecast_encoding_link(value,digest(text),vector(stored))
    return json.loads(json.dumps(value,allow_nan=False))


def validate_forecast_encoding_link(value, text_hash, stored):
    if value is None: return 'not_instrumented_forecast'
    if (not isinstance(value,dict) or set(value)!={'schema','transform','raw_emb','call'}
            or value['schema']!='readout-encoding-link-v1' or value['transform']!='readout_units_v1'
            or not isinstance(value['call'],dict)):
        raise ValueError('invalid forecast encoding link')
    raw=vector(value['raw_emb'])
    state=validate_encoding_observation(value['call'],text_hash,raw,expected_schema='forecast-encoding-observation-v1')
    import numpy as np
    a=np.asarray(raw,dtype=float)
    normalized=a/np.maximum(np.linalg.norm(a,axis=-1,keepdims=True),1e-12)
    if not np.array_equal(normalized,np.asarray(vector(stored),dtype=float)):
        raise ValueError('forecast vector transform mismatch')
    return state


class AuditEncoder:
    """Observe the existing self audit's encoded inputs; return its exact output."""
    def __init__(self, enc, ledger, manifest, root):
        from witness_receipts import digest
        from witness_capture import _fingerprint
        self.enc, self.manifest, self.root = enc, manifest, root
        self.refs, self.seen = {}, set()
        self._parameter_pairs = 1  # Bound audit overhead to one before/after pair.
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
        sample_parameters = False
        try:
            sample_parameters = bool(self._parameter_pairs and isinstance(texts,list)
                                     and any(isinstance(t,str) and t in self.refs for t in texts))
            if sample_parameters: self._parameter_pairs -= 1
        except Exception: pass
        runtime, entrypoint = {}, {}
        result,before,after,timing = observed_encode(self.enc,texts,args,kwargs,sample_parameters,runtime,entrypoint)
        try:
            from witness_capture import _publish_private, _private_root, _fingerprint
            from witness_receipts import digest
            if not isinstance(texts, list) or len(texts) > 256 or len(result) != len(texts):
                raise ValueError('unbounded audit encoding')
            try:
                options = json.dumps([args, kwargs], sort_keys=True, allow_nan=False)
                settings = digest(options) if len(options) <= 4096 else None
            except Exception: settings = None
            invocation = uuid.uuid4().hex
            for text, emb in zip(texts, result):
                if text not in self.refs:
                    continue
                values = vector(emb)
                encoded = encoding_observation(text, values, before, after, settings, invocation,timing,runtime,entrypoint)
                observation = (digest(text), _fingerprint(values), _fingerprint([before, after, settings, runtime, entrypoint]))
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
                          'encoding_observation': encoded,
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


FIT_BLOCKS = ('train', 'validation', 'calibration', 'test')


def _fit_array_digest(values):
    """Fingerprint bounded numeric arrays without retaining their values."""
    import numpy as np
    if not isinstance(values, dict) or not 0 < len(values) <= 32:
        raise ValueError('invalid fit arrays')
    if any(type(k) is not str or len(k) > 256 for k in values):
        raise ValueError('invalid fit array names')
    h = hashlib.sha256(b'self-fit-arrays-v1\x00'); total = 0
    for name in sorted(values):
        a = np.asarray(values[name])
        total += a.nbytes
        if (a.dtype.kind not in 'biufc' or total > MAX_CHECKPOINT or a.ndim > 4
                or not np.isfinite(a).all()):
            raise ValueError('invalid fit array value')
        descriptor = json.dumps([name,a.dtype.str,list(a.shape)],separators=(',',':')).encode()
        h.update(len(descriptor).to_bytes(8,'big')); h.update(descriptor)
        raw = memoryview(np.ascontiguousarray(a)).cast('B')
        h.update(len(raw).to_bytes(8,'big')); h.update(raw)
    return h.hexdigest()


def begin_fit(mode, rows, features, targets, indices):
    """Observe actual ordered inputs and existing partitions, not source authenticity."""
    from witness_capture import _capture_location, _private_root, _fingerprint
    import numpy as np
    if mode not in ('self_ahead','self_on_message'): return None
    location = _capture_location()
    if not location: return None
    root = str(_private_root(location))
    if (not isinstance(rows,list) or not 1 <= len(rows) <= 4096
            or not isinstance(features,(list,tuple)) or not 1 <= len(features) <= 16
            or len(indices) != 4):
        raise ValueError('unbounded fitting inputs')
    encoded = json.dumps(rows,sort_keys=True,allow_nan=False)
    if len(encoded) > 8*1024*1024: raise ValueError('unbounded fitting rows')
    arrays = {str(i):np.asarray(v) for i,v in enumerate(features)}
    arrays['target'] = np.asarray(targets)
    if any(v.ndim < 1 or len(v) != len(rows) for v in arrays.values()):
        raise ValueError('unaligned fitting inputs')
    _fit_array_digest(arrays)  # Enforce one total input-byte budget before taking subsets.
    blocks, covered = {}, []
    for name, supplied in zip(FIT_BLOCKS,indices):
        ix = np.asarray(supplied)
        if (ix.ndim != 1 or ix.dtype.kind not in 'iu' or not len(ix)
                or any(not 0 <= int(i) < len(rows) for i in ix)):
            raise ValueError('invalid fitting partition')
        selected = [int(i) for i in ix]; covered.extend(selected)
        blocks[name] = {'rows':len(ix), 'indices_sha256':_fingerprint(selected),
                        'ordered_rows_sha256':_fingerprint([rows[i] for i in selected]),
                        'arrays_sha256':_fit_array_digest({k:v[ix] for k,v in arrays.items()})}
    if sorted(covered) != list(range(len(rows))): raise ValueError('overlapping fitting partitions')
    return {'root':root,'mode':mode,'fit_started_at':time.time(),'blocks':blocks}


def prepare_fit(scope, meta, parameters):
    """Bind the completed fitter output before the existing checkpoint write."""
    from witness_capture import _fingerprint
    if scope is None: return None
    if not isinstance(meta,dict) or meta.get('mode') != scope['mode']:
        raise ValueError('fit metadata mode mismatch')
    encoded = json.dumps(meta,sort_keys=True,allow_nan=False)
    if len(encoded) > 262144: raise ValueError('unbounded fit metadata')
    return dict(scope, metadata_sha256=_fingerprint(meta),
                parameters_sha256=_fit_array_digest(parameters), parameters_ready_at=time.time())


def publish_fit(scope, path):
    """Read back bounded bytes after save returns; require exact metadata and parameters.

    This observes the matching file at this boundary, not atomic publication,
    storage durability, source authentication, or the historical fit of an old file.
    """
    if scope is None: return None
    import io
    import os
    import stat
    import zipfile
    import numpy as np
    from witness_capture import _private_root, _publish_private, _fingerprint
    root = _private_root(scope['root'])  # Honor hot disable before reading the output.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CHECKPOINT:
            raise ValueError('unbounded fitting checkpoint')
        raw = stream.read(MAX_CHECKPOINT+1)
        after = os.fstat(stream.fileno())
    identity = lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise ValueError('fitting checkpoint changed while read')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist(); names = [v.filename for v in entries]
        if (not 2 <= len(entries) <= 33 or len(set(names)) != len(names)
                or sum(v.file_size for v in entries) > MAX_CHECKPOINT):
            raise ValueError('unbounded fitting checkpoint archive')
    with np.load(io.BytesIO(raw),allow_pickle=False) as loaded:
        meta = json.loads(str(loaded['meta']))
        parameters = {k:loaded[k] for k in loaded.files if k != 'meta'}
    if (_fingerprint(meta) != scope['metadata_sha256']
            or _fit_array_digest(parameters) != scope['parameters_sha256']):
        raise ValueError('saved checkpoint does not match fitter output')
    observed_at = time.time()
    clocks = (scope['fit_started_at'],scope['parameters_ready_at'],observed_at)
    if (any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in clocks)
            or list(clocks) != sorted(clocks)):
        raise ValueError('unusable fitting observation clocks')
    packet = {k:scope[k] for k in ('mode','fit_started_at','parameters_ready_at',
                                  'blocks','metadata_sha256','parameters_sha256')}
    packet.update(schema='self-fit-completion-v1', checkpoint_id=hashlib.sha256(raw).hexdigest(),
                  checkpoint_bytes=len(raw), checkpoint_observed_at=observed_at,
                  boundary='matching_checkpoint_read_after_save_return',
                  source_identity='unverified', encoder_identity='unverified',
                  upstream_complete=False, durability='unconfirmed', scoring_effect='none')
    return _publish_private(root,packet,'self-fit-completion-')
