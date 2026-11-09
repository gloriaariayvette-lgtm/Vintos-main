"""Offline content binding for retained self vectors; no scoring or admission changes."""
from collections import Counter, defaultdict
import json
import math
import re
from witness_receipts import admission, digest, final_response, joined_identity, row_receipt, instant
from witness_self_artifacts import bound_source, availability_receipt, validate_context_baseline, validate_selected_feature_inputs, validate_encoding_observation, validate_forecast_encoding_link, checkpoint_observed_fields


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False))


def normalized_reply(raw):
    """Versioned self-reader cleanup, checked against the actual reader in tests."""
    text = raw.strip()
    if text in ('', 'voice', '--source'):
        return ''
    paragraphs = text.split('\n\n')
    while len(paragraphs) > 1 and re.match(r'^(?:ridge|tenera|ferri):', paragraphs[-1].strip(), re.I):
        paragraphs.pop()
    return '\n\n'.join(paragraphs).strip()


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _vector(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 8192
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
            or not any(value)):
        raise ValueError('invalid retained artifact vector')
    return fingerprint(value)


def claims(packet):
    """Extract observations only; do not infer a forecast's selected target."""
    schema = packet.get('schema')
    if schema == 'self-audit-embedding-v1':
        if packet.get('transform') != 'ledger_vintos_strip_first_400_codepoints':
            raise ValueError('unknown audit input transform')
        refs = packet.get('source_refs')
        if not isinstance(refs, list) or not 1 <= len(refs) <= 64:
            raise ValueError('invalid audit source references')
        manifest = packet.get('checkpoint')
        values = [(ref, packet) for ref in refs]
    elif schema == 'self-forecast-artifacts-v1':
        artifacts = packet.get('artifacts')
        if not isinstance(artifacts, dict):
            raise ValueError('invalid forecast artifact observations')
        refs = artifacts.get('recent_own_embeddings')
        if not isinstance(refs, list) or not 1 <= len(refs) <= 6:
            raise ValueError('invalid forecast input references')
        manifest = artifacts.get('checkpoint')
        if 'context_baseline' in artifacts:
            validate_context_baseline(artifacts['context_baseline'])
        if 'feature_inputs' in artifacts:
            feature_inputs = artifacts['feature_inputs']
            validate_selected_feature_inputs(feature_inputs)
            if any(not isinstance(r,dict) for r in refs):
                raise ValueError('invalid selected own references')
            own = [{'sha256':r.get('encoder_input_sha256'),'chars':r.get('encoder_input_chars')}
                   for r in refs if isinstance(r,dict)]
            if (feature_inputs['selection']['own'] != own
                    or feature_inputs['features'][0]['values_sha256'] != _vector(refs[-1].get('emb'))
                    or feature_inputs['features'][0]['dimensions'] != len(refs[-1]['emb'])):
                raise ValueError('selected own features disagree with retained embeddings')
        values = []
        for ref in refs:
            if not isinstance(ref, dict) or ref.get('transform') != 'normalized_exchange_his_first_400_codepoints':
                raise ValueError('unknown forecast input transform')
            values.append((ref, ref))
    else:
        raise ValueError('unsupported self artifact packet')
    if not isinstance(manifest, dict) or not _hash(manifest.get('checkpoint_id')):
        raise ValueError('invalid retained checkpoint identity')
    checkpoint_observed_fields(manifest)
    for ref, value in values:
        if (not isinstance(ref, dict) or not _hash(value.get('encoder_input_sha256'))
                or type(value.get('encoder_input_chars')) is not int
                or not 1 <= value['encoder_input_chars'] <= 400):
            raise ValueError('invalid retained input identity')
        vector_sha = _vector(value.get('emb'))
        if schema == 'self-audit-embedding-v1':
            validate_encoding_observation(value.get('encoding_observation'), value['encoder_input_sha256'], value['emb'])
        else:
            validate_forecast_encoding_link(value.get('encoding_link'), value['encoder_input_sha256'], value['emb'])
        expected = 'encoder_return_v1' if schema == 'self-audit-embedding-v1' else 'readout_units_v1'
        if 'vector_representation' in value and value['vector_representation'] != expected:
            raise ValueError('invalid retained vector representation')
        yield ref, value, manifest['checkpoint_id'], vector_sha


def join_artifacts(admitted, sources, nodes, packets, cutoff, forecasts=()):
    """Exact source digest, explicit ID/surface, final version and transform agreement.

    Even a content match is not encoder identity, training evidence or a forecast
    target association. No vectors are returned for automatic scoring consumption.
    """
    if not isinstance(packets, list) or len(packets) > 4096:
        raise ValueError('invalid artifact packet list')
    cutoff = instant(cutoff)
    targets = {row['turn_id']: row for row in admitted}
    if len(targets) != len(admitted):
        raise ValueError('duplicate admitted reply identity')
    raw_by_hash = defaultdict(list)
    for kind, rows in sources:
        if kind not in ('canonical', 'merged', 'ledger'):
            continue
        for raw in rows:
            key = fingerprint(raw)
            if kind not in [k for k, _ in raw_by_hash[key]]:
                raw_by_hash[key].append((kind, raw))
    unique = {}
    for packet in packets:
        if not isinstance(packet, dict):
            raise ValueError('invalid artifact packet')
        unique[fingerprint(packet)] = packet
    details, vectors = [], defaultdict(lambda: defaultdict(set))
    encodings = defaultdict(list)
    for packet_sha, packet in sorted(unique.items()):
        for index, (ref, value, checkpoint, vector_sha) in enumerate(claims(packet)):
            item = {'packet_sha256': packet_sha, 'reference_index': index,
                    'checkpoint_id': checkpoint, 'encoder_input_sha256': value['encoder_input_sha256'],
                    'vector_sha256': vector_sha, 'turn_id': None, 'final_response_sha256': None,
                    'vector_representation': value.get('vector_representation'),
                    'state': 'missing_source_observation'}
            details.append(item)
            observed = ref.get('reply_source')
            if not isinstance(observed, dict):
                continue
            key = observed.get('source_row_sha256')
            if not _hash(key):
                item['state'] = 'invalid_source_observation'; continue
            matches = raw_by_hash.get(key, [])
            expected = 'ledger' if observed.get('source_field') == 'vintos' else 'chat'
            matches = [(k, row) for k, row in matches if (k == 'ledger') == (expected == 'ledger')]
            if not matches:
                item['state'] = 'exact_source_row_missing'; continue
            # Same raw row in canonical/merged is one version; no time/text lookup.
            kind, source = matches[0]
            field = observed.get('source_field')
            raw = source.get(field) if field in ('vintos', 'content') else None
            if not isinstance(raw, str) or not 0 < len(raw) <= 65536:
                item['state'] = 'invalid_source_reply'; continue
            normalized = normalized_reply(raw)
            bound = bound_source(observed, normalized, source.get('turn_id'))
            if (bound is None or bound['source_reply_sha256'] != digest(raw)
                    or bound['observed_turn_id'] != source.get('turn_id')
                    or bound['observed_surface'] != source.get('surface')
                    or bound['observed_turn_id'] != ref.get('observed_turn_id')
                    or ref.get('normalized_reply_sha256') != digest(normalized)):
                item['state'] = 'source_observation_mismatch'; continue
            tid, surface = bound['observed_turn_id'], bound['observed_surface']
            if not tid or not surface:
                item['state'] = 'missing_source_identity'; continue
            item['turn_id'] = tid
            target = targets.get(tid)
            if target is None:
                item['state'] = 'reply_not_admitted'; continue
            source_copy = dict(source, _witness_adapter_kind=kind)
            if kind == 'ledger':
                source_copy.update(role='assistant', content=raw)
            if admission(source_copy, nodes, cutoff) != 'eligible':
                item['state'] = 'source_copy_not_admitted'; continue
            final = final_response(target)
            if (joined_identity(source_copy)[0] != tid or surface != target.get('surface')
                    or row_receipt(source_copy) != row_receipt(target)
                    or final_response(source_copy) != final):
                item['state'] = 'final_version_mismatch'; continue
            item['final_response_sha256'] = digest(final)
            if normalized != final:
                item['state'] = 'normalization_changes_final'; continue
            encoded = normalized[:400]
            if (value['encoder_input_sha256'] != digest(encoded)
                    or value['encoder_input_chars'] != len(encoded)):
                item['state'] = 'input_transform_mismatch'; continue
            item['state'] = 'bound_full_text' if encoded == final else 'bound_excerpt'
            group = (checkpoint, tid, digest(final), value['encoder_input_sha256'])
            vectors[group][value.get('vector_representation')].add(vector_sha)
            link = value.get('encoding_link')
            observation = (value.get('encoding_observation') if packet['schema'] == 'self-audit-embedding-v1'
                           else link.get('call') if isinstance(link, dict) else None)
            encodings[group].append(observation)
            item['_group'] = group
    for item in details:
        group = item.pop('_group', None)
        if group is not None:
            representations = vectors[group]
            if any(rep is not None and len(hashes) > 1 for rep, hashes in representations.items()):
                item['state'] = 'conflicting_vector_observations'
            elif len(representations) > 1:
                item['state'] = 'mixed_vector_representations'
            elif len(representations.get(None, ())) > 1:
                item['state'] = 'vector_representation_unobserved'
    states = Counter(item['state'] for item in details)
    matched = [item for item in details if item['state'] in ('bound_full_text', 'bound_excerpt')]
    return {'scope': 'content_binding_only', 'packets_supplied': len(packets), 'unique_packets': len(unique),
            'source_references': len(details), 'states': dict(sorted(states.items())),
            'encoding_consistency': encoding_consistency(encodings),
            'runtime_consistency': runtime_consistency(encodings),
            'entrypoint_consistency': entrypoint_consistency(encodings),
            'encoder_call_cost': encoder_call_cost(list(unique.values())),
            'selected_feature_states': selected_feature_coverage(list(unique.values()), forecasts, cutoff),
            'context_baseline_states': context_baseline_coverage(list(unique.values()), forecasts, cutoff),
            'checkpoint_availability_states': checkpoint_availability(list(unique.values()), forecasts, cutoff),
            'checkpoint_consistency': checkpoint_consistency(list(unique.values())),
            'encoder_parameter_observation_states': dict(sorted(Counter(
                validate_encoding_observation(p.get('encoding_observation'), p.get('encoder_input_sha256'), p.get('emb'))
                if p.get('schema') == 'self-audit-embedding-v1' else forecast_parameter_state(p)
                for p in unique.values()).items())),
            'bound_unique_replies': len({item['turn_id'] for item in matched}),
            'admission_effect': 'none', 'scoring_effect': 'none', 'encoder_identity': 'unverified',
            'artifact_observation_time': 'unverified', 'forecast_target_selection': 'not_evaluated'}, details


CONTEXT_BASELINE_STATES = ('not_forecast','unobserved','conflicting_observations',
                           'exact_forecast_row_missing','forecast_identity_mismatch',
                           'forecast_clock_mismatch','outside_cutoff','baseline_vector_mismatch','bound_to_forecast')


SELECTED_FEATURE_STATES = ('not_forecast','unobserved','conflicting_observations',
                          'exact_forecast_row_missing','forecast_identity_mismatch',
                          'forecast_clock_mismatch','outside_cutoff','selected_clock_not_before_arrival','bound_to_forecast')


def _forecast_observation_coverage(packets, forecasts, cutoff, field, validate, compare):
    """Compare exact supplied versions; conflicts include all supplied peers."""
    cutoff=instant(cutoff)
    rows={fingerprint(f):f for f in forecasts if isinstance(f,dict)}
    variants=defaultdict(set)
    for packet in packets:
        if packet.get('schema')=='self-forecast-artifacts-v1' and field in packet['artifacts']:
            value=packet['artifacts'][field];validate(value)
            variants[packet.get('forecast_row_sha256')].add(fingerprint(value))
    states=Counter()
    for packet in packets:
        if packet.get('schema')!='self-forecast-artifacts-v1':state='not_forecast'
        elif field not in packet['artifacts']:state='unobserved'
        elif len(variants[packet.get('forecast_row_sha256')])>1:state='conflicting_observations'
        else:
            row=rows.get(packet.get('forecast_row_sha256'))
            if row is None:state='exact_forecast_row_missing'
            elif (row.get('mode')!='on_message' or not isinstance(row.get('self'),dict)
                    or row['self'].get('mode')!='on_message'
                    or row['self'].get('checkpoint_id')!=packet['artifacts']['checkpoint']['checkpoint_id']):
                state='forecast_identity_mismatch'
            else:
                try:
                    made,arrived=instant(row['ts']),instant(row['arrived_at'])
                    if made!=instant(packet['forecast_at']) or arrived!=instant(packet['arrived_at']) or arrived>made:
                        raise ValueError('forecast observation clocks')
                except (ValueError,TypeError,KeyError,OverflowError):state='forecast_clock_mismatch'
                else:
                    state='outside_cutoff' if made>=cutoff else compare(row,packet['artifacts'][field])
        states[state]+=1
    return dict(sorted(states.items()))


def context_baseline_coverage(packets, forecasts, cutoff):
    def compare(row,value):
        try:
            matched=(_vector(row.get('context_emb'))==value['normalized_vector_sha256']
                     and len(row['context_emb'])==value['dimensions'])
        except (ValueError,TypeError,KeyError):matched=False
        return 'bound_to_forecast' if matched else 'baseline_vector_mismatch'
    return _forecast_observation_coverage(packets,forecasts,cutoff,'context_baseline',validate_context_baseline,compare)


def selected_feature_coverage(packets, forecasts, cutoff):
    """Attachment/time consistency only; hashes do not certify full source ancestry."""
    def compare(row,value):
        return ('bound_to_forecast' if instant(value['exchange_at'])<instant(row['arrived_at'])
                else 'selected_clock_not_before_arrival')
    return _forecast_observation_coverage(packets,forecasts,cutoff,'feature_inputs',validate_selected_feature_inputs,compare)


def checkpoint_availability(packets, forecasts, cutoff):
    """Timing consistency of exact supplied records; never invent a fitting date."""
    cutoff = instant(cutoff)
    by_forecast = {fingerprint(f):f for f in forecasts if isinstance(f, dict)}
    states = Counter()
    for packet in packets:
        is_forecast = packet.get('schema') == 'self-forecast-artifacts-v1'
        manifest = packet.get('artifacts',{}).get('checkpoint') if is_forecast else packet.get('checkpoint')
        observation = availability_receipt(manifest.get('availability') if isinstance(manifest,dict) else None)
        state = observation['state']
        if state != 'observed':
            states[state] += 1; continue
        if not is_forecast:
            states['audit_snapshot_observed'] += 1; continue
        if observation['stage'] != 'parameters_loaded':
            states['parameters_not_loaded'] += 1; continue
        forecast = by_forecast.get(packet.get('forecast_row_sha256'))
        if forecast is None:
            states['exact_forecast_row_missing'] += 1; continue
        if (forecast.get('mode') != 'on_message' or not isinstance(forecast.get('self'),dict)
                or forecast['self'].get('mode') != 'on_message'
                or forecast['self'].get('checkpoint_id') != manifest.get('checkpoint_id')):
            states['forecast_identity_mismatch'] += 1; continue
        try:
            made, arrived = instant(forecast['ts']), instant(forecast['arrived_at'])
            if (made != instant(packet['forecast_at']) or arrived != instant(packet['arrived_at'])
                    or arrived > made):
                raise ValueError('inconsistent forecast clocks')
        except (KeyError,TypeError,ValueError,OverflowError):
            states['forecast_clock_mismatch'] += 1; continue
        if made >= cutoff:
            states['forecast_outside_cutoff'] += 1
        elif observation['parameters_available_by'] > made:
            states['parsed_after_logged_forecast'] += 1
        else:
            states['parsed_by_logged_forecast'] += 1
    return dict(sorted(states.items()))


def forecast_parameter_state(packet):
    states={validate_forecast_encoding_link(r.get('encoding_link'),r['encoder_input_sha256'],r['emb'])
            for r in packet['artifacts']['recent_own_embeddings']}
    return next(iter(states)) if len(states)==1 else 'mixed_forecast_observations'


ENCODING_CONSISTENCY_LABELS = {
    'parameters': ('changed_during_call', 'different_snapshots', 'incomplete', 'single_call', 'matching_snapshots'),
    'settings': ('different_settings', 'incomplete', 'single_call', 'matching_settings'),
    'raw_vectors': ('different_raw_vectors', 'incomplete', 'single_call', 'matching_raw_vectors'),
}


def encoding_consistency(groups):
    """Compare already validated calls for exact content groups, without scoring.

    Each axis counts groups once. Observed differences survive incomplete peers;
    equality needs every reference observed and at least two distinct call markers.
    A matching snapshot is not a complete encoder identity or proof of immutability.
    """
    counts = {axis: Counter() for axis in ENCODING_CONSISTENCY_LABELS}
    references = 0
    for observations in groups.values():
        references += len(observations)
        calls = [o for o in observations if o is not None]
        markers = {o['invocation'] for o in calls}
        absent = len(calls) != len(observations) or not calls
        snapshots = {fingerprint(o[k]) for o in calls for k in ('parameter_before', 'parameter_after')
                     if o[k]['state'] == 'observed'}
        if any(o['parameter_state'] == 'observed_changed' for o in calls):
            parameter = 'changed_during_call'
        elif len(snapshots) > 1:
            parameter = 'different_snapshots'
        elif absent or any(o['parameter_state'] != 'observed_equal' for o in calls):
            parameter = 'incomplete'
        else:
            parameter = 'single_call' if len(markers) < 2 else 'matching_snapshots'
        counts['parameters'][parameter] += 1
        for axis, field, different, matching in (
            ('settings', 'settings_sha256', 'different_settings', 'matching_settings'),
            ('raw_vectors', 'raw_vector_sha256', 'different_raw_vectors', 'matching_raw_vectors')):
            values = {o[field] for o in calls if o[field] is not None}
            if len(values) > 1:
                state = different
            elif absent or any(o[field] is None for o in calls):
                state = 'incomplete'
            else:
                state = 'single_call' if len(markers) < 2 else matching
            counts[axis][state] += 1
    return {'groups': len(groups), 'references': references,
            **{axis: dict(sorted(values.items())) for axis, values in counts.items()}}


RUNTIME_CONSISTENCY_STATES = ('changed_during_call', 'different_partial_snapshots',
                              'incomplete', 'single_call', 'matching_partial_snapshots')


def runtime_consistency(groups):
    """Compare validated partial stored-field observations in exact content groups."""
    states = dict.fromkeys(RUNTIME_CONSISTENCY_STATES,0)
    references = 0
    for observations in groups.values():
        references += len(observations)
        calls = [o for o in observations if o is not None]
        runtimes = [o['runtime'] for o in calls if o.get('runtime') is not None]
        snapshots = {fingerprint(o[k]) for o in runtimes for k in ('before','after')
                     if o[k]['state']=='observed'}
        if any(o['state']=='observed_changed' for o in runtimes): state='changed_during_call'
        elif len(snapshots)>1: state='different_partial_snapshots'
        elif len(runtimes)!=len(observations) or any(o['state']!='observed_equal' for o in runtimes):
            state='incomplete'
        elif len({o['invocation'] for o in calls})<2: state='single_call'
        else: state='matching_partial_snapshots'
        states[state]+=1
    return {'scope':'content_bound_partial_runtime_observations_only', 'groups':len(groups),
            'references':references, 'states':states, 'encoder_identity':'unverified','scoring_effect':'none'}


def validate_runtime_consistency(value, references, groups=None):
    def count(n):
        if type(n) is not int or n<0: raise ValueError('invalid runtime consistency count')
        return n
    if (not isinstance(value,dict) or set(value)!={'scope','groups','references','states','encoder_identity','scoring_effect'}
            or value['scope']!='content_bound_partial_runtime_observations_only'
            or value['encoder_identity']!='unverified' or value['scoring_effect']!='none'):
        raise ValueError('invalid runtime consistency contract')
    n,r = count(value['groups']),count(value['references'])
    states=value['states']
    if not isinstance(states,dict) or set(states)!=set(RUNTIME_CONSISTENCY_STATES):
        raise ValueError('invalid runtime consistency states')
    if (sum(count(v) for v in states.values())!=n or r!=count(references) or n>r
            or bool(n)!=bool(r) or (groups is not None and n!=count(groups))
            or n+states['matching_partial_snapshots']+states['different_partial_snapshots']>r):
        raise ValueError('inconsistent runtime consistency totals')


def entrypoint_consistency(groups):
    projected = {key:[None if o is None else dict(o,runtime=o.get('entrypoint')) for o in rows]
                 for key,rows in groups.items()}
    value = runtime_consistency(projected)
    value['scope'] = 'content_bound_python_entrypoint_observations_only'
    return value


def validate_entrypoint_consistency(value, references, groups=None):
    if not isinstance(value,dict) or value.get('scope')!='content_bound_python_entrypoint_observations_only':
        raise ValueError('invalid entrypoint consistency contract')
    validate_runtime_consistency(dict(value,scope='content_bound_partial_runtime_observations_only'),references,groups)


def encoder_call_cost(packets):
    """Aggregate validated retained calls, including unbound inputs; no identities out."""
    from witness_self_artifacts import TIMING_STAGES
    calls = defaultdict(dict)
    unidentified = observations = 0
    for packet in packets:
        for index,(_,value,_,_) in enumerate(claims(packet)):
            # An audit packet can carry several source references for one encoding.
            if packet['schema']=='self-audit-embedding-v1':
                if index: continue
                call = value.get('encoding_observation')
            else:
                link = value.get('encoding_link')
                call = link.get('call') if isinstance(link,dict) else None
            observations += 1
            if call is None:
                unidentified += 1
                continue
            signature = {k:call.get(k) for k in ('timing','parameter_before','parameter_after','settings_sha256','runtime','entrypoint')}
            calls[call['invocation']][fingerprint(signature)] = signature
    conflicts = sum(len(values)>1 for values in calls.values())
    valid = [next(iter(values.values())) for values in calls.values() if len(values)==1]
    legacy = sum(v['timing'] is None for v in valid)
    stages = {}
    for key in TIMING_STAGES:
        samples = [v['timing'][key] for v in valid if v['timing'] is not None and v['timing'][key] is not None]
        stages[key] = {'measured_calls':len(samples),'unavailable_calls':len(valid)-len(samples),
                       'total_seconds':math.fsum(samples),'max_seconds':max(samples,default=0)}
    sizes = [v[k]['bytes'] for v in valid for k in ('parameter_before','parameter_after')
             if v[k]['state']=='observed']
    return {'scope':'supplied_retained_calls_only','observations':observations,
            'unidentified_observations':unidentified,'calls':len(calls),
            'conflicting_calls':conflicts,'legacy_calls':legacy,'timed_calls':len(valid)-legacy,
            'stages':stages,'parameter_snapshots':{'observed':len(sizes),
                       'total_bytes':sum(sizes),'max_bytes':max(sizes,default=0)}}


def validate_encoder_call_cost(value, references):
    """Fixed aggregate fields and conserved counts; never render arbitrary labels."""
    from witness_self_artifacts import TIMING_STAGES, MAX_ENCODER_STATE_BYTES
    def count(n):
        if type(n) is not int or n<0: raise ValueError('invalid encoder cost count')
        return n
    if (not isinstance(value,dict) or set(value)!={'scope','observations','unidentified_observations',
            'calls','conflicting_calls','legacy_calls','timed_calls','stages','parameter_snapshots'}
            or value['scope']!='supplied_retained_calls_only'):
        raise ValueError('invalid encoder cost scope')
    obs,missing,calls,conflicts,legacy,timed = [count(value[k]) for k in
        ('observations','unidentified_observations','calls','conflicting_calls','legacy_calls','timed_calls')]
    if (obs>count(references) or missing>obs or calls>obs-missing
            or bool(calls)!=bool(obs-missing) or conflicts+legacy+timed!=calls):
        raise ValueError('invalid encoder cost totals')
    stages=value['stages']
    if not isinstance(stages,dict) or set(stages)!=set(TIMING_STAGES): raise ValueError('invalid cost stages')
    for stage in stages.values():
        if not isinstance(stage,dict) or set(stage)!={'measured_calls','unavailable_calls','total_seconds','max_seconds'}:
            raise ValueError('invalid cost stage')
        measured,unavailable=count(stage['measured_calls']),count(stage['unavailable_calls'])
        total,peak=stage['total_seconds'],stage['max_seconds']
        if (measured+unavailable!=calls-conflicts or measured>timed
                or any(type(n) not in (int,float) or not math.isfinite(n) or n<0 for n in (total,peak))
                or peak>86400 or total<peak or (not measured and (total!=0 or peak!=0))
                or total>peak*measured+max(1e-12,abs(total)*1e-12)):
            raise ValueError('invalid cost duration')
    sizes=value['parameter_snapshots']
    if not isinstance(sizes,dict) or set(sizes)!={'observed','total_bytes','max_bytes'}: raise ValueError('invalid cost sizes')
    n,total,peak=(count(sizes[k]) for k in ('observed','total_bytes','max_bytes'))
    if (n>2*(calls-conflicts) or peak>MAX_ENCODER_STATE_BYTES or bool(n)!=bool(peak)
            or not peak<=total<=peak*n): raise ValueError('invalid cost size totals')


CHECKPOINT_CONSISTENCY_STATES = ('consistent_observed_fields','conflicting_observations',
                                 'incomplete_observations','legacy_only')


def checkpoint_consistency(packets):
    """Compare fields carried by the same checkpoint hash, never certify its lineage."""
    groups = defaultdict(list)
    observed = legacy = 0
    for packet in packets:
        manifest = (packet['checkpoint'] if packet['schema']=='self-audit-embedding-v1'
                    else packet['artifacts']['checkpoint'])
        fields = checkpoint_observed_fields(manifest)
        groups[manifest['checkpoint_id']].append(fields)
        if fields is None: legacy += 1
        else: observed += 1
    states = dict.fromkeys(CHECKPOINT_CONSISTENCY_STATES,0)
    for copies in groups.values():
        known={fingerprint(v) for v in copies if v is not None}
        if len(known)>1: state='conflicting_observations'
        elif not known: state='legacy_only'
        elif any(v is None for v in copies): state='incomplete_observations'
        else: state='consistent_observed_fields'
        states[state] += 1
    return {'scope':'supplied_checkpoint_observations_only','manifest_copies':len(packets),
            'checkpoint_groups':len(groups),'observed_manifests':observed,'legacy_manifests':legacy,
            'states':states,'lineage':'unverified','scoring_effect':'none'}


def validate_checkpoint_consistency(value, packets):
    def count(n):
        if type(n) is not int or n<0: raise ValueError('invalid checkpoint consistency count')
        return n
    if (not isinstance(value,dict) or set(value)!={'scope','manifest_copies','checkpoint_groups',
            'observed_manifests','legacy_manifests','states','lineage','scoring_effect'}
            or value['scope']!='supplied_checkpoint_observations_only'
            or value['lineage']!='unverified' or value['scoring_effect']!='none'):
        raise ValueError('invalid checkpoint consistency scope')
    copies,groups,observed,legacy=(count(value[k]) for k in
        ('manifest_copies','checkpoint_groups','observed_manifests','legacy_manifests'))
    states=value['states']
    if not isinstance(states,dict) or set(states)!=set(CHECKPOINT_CONSISTENCY_STATES):
        raise ValueError('invalid checkpoint consistency states')
    consistent,conflicts,incomplete,old=(count(states[k]) for k in CHECKPOINT_CONSISTENCY_STATES)
    if (copies!=count(packets) or observed+legacy!=copies or groups>copies or bool(groups)!=bool(copies)
            or consistent+conflicts+incomplete+old!=groups
            or consistent+2*conflicts+incomplete>observed or incomplete+old>legacy
            or (not (consistent+conflicts+incomplete) and observed)
            or (not (conflicts+incomplete+old) and legacy)):
        raise ValueError('invalid checkpoint consistency totals')
