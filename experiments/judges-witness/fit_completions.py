"""Offline fitting/checkpoint consistency only; never reconstruct historical training dates."""
from collections import defaultdict
import json
import re
from witness_receipts import digest, instant
from witness_self_artifacts import FIT_BLOCKS, MAX_CHECKPOINT, checkpoint_observed_fields, availability_receipt
from witness_artifact_join import claims

STATES = ('fit_receipt_missing', 'conflicting_fit_receipts', 'conflicting_manifests',
          'fit_outside_cutoff', 'legacy_manifest', 'manifest_mismatch', 'read_clock_unknown',
          'read_outside_cutoff', 'observed_before_read', 'overlapping_read', 'observed_after_read')
COUNTS = ('supplied_receipts', 'unique_receipts', 'receipt_checkpoints',
          'supplied_artifact_packets', 'unique_checkpoint_observations', 'checkpoint_groups',
          'receipts_without_checkpoint_observation')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def hashed(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def validate_receipt(value):
    fields = {'schema','mode','fit_started_at','parameters_ready_at','checkpoint_observed_at',
              'blocks','metadata_sha256','parameters_sha256','checkpoint_id','checkpoint_bytes',
              'boundary','source_identity','encoder_identity','upstream_complete','durability','scoring_effect'}
    if (not isinstance(value,dict) or set(value)!=fields
            or value['schema']!='self-fit-completion-v1'
            or value['mode'] not in ('self_ahead','self_on_message')
            or value['boundary']!='matching_checkpoint_read_after_save_return'
            or value['source_identity']!='unverified' or value['encoder_identity']!='unverified'
            or value['upstream_complete'] is not False or value['durability']!='unconfirmed'
            or value['scoring_effect']!='none'
            or any(not hashed(value[k]) for k in ('metadata_sha256','parameters_sha256','checkpoint_id'))
            or type(value['checkpoint_bytes']) is not int or not 0<value['checkpoint_bytes']<=MAX_CHECKPOINT):
        raise ValueError('invalid fitting completion receipt')
    times = [value[k] for k in ('fit_started_at','parameters_ready_at','checkpoint_observed_at')]
    if any(type(v) not in (int,float) or not 0<v<=253402300799 for v in times) or times!=sorted(times):
        raise ValueError('invalid fitting boundary clocks')
    blocks=value['blocks']
    if not isinstance(blocks,dict) or set(blocks)!=set(FIT_BLOCKS):
        raise ValueError('invalid fitting partitions')
    total=0
    for block in blocks.values():
        if (not isinstance(block,dict) or set(block)!={'rows','indices_sha256','ordered_rows_sha256','arrays_sha256'}
                or type(block['rows']) is not int or not 1<=block['rows']<=4096
                or any(not hashed(block[k]) for k in ('indices_sha256','ordered_rows_sha256','arrays_sha256'))):
            raise ValueError('invalid fitting partition observation')
        total+=block['rows']
    if total>4096: raise ValueError('unbounded fitting partition observations')


def coverage(packets, receipts, cutoff):
    """Compare all supplied peers before filtering; duplicates collapse, alternatives hold."""
    cutoff=instant(cutoff)
    if not isinstance(packets,list) or not isinstance(receipts,list):
        raise ValueError('fitting evidence requires explicit lists')
    fits, manifests, by_checkpoint = {}, {}, defaultdict(dict)
    for receipt in receipts:
        validate_receipt(receipt)
        key=digest(encoded(receipt));fits[key]=receipt
        by_checkpoint[receipt['checkpoint_id']][key]=receipt
    fields_by_checkpoint=defaultdict(set)
    for packet in packets:
        if not isinstance(packet,dict): raise ValueError('invalid checkpoint artifact packet')
        list(claims(packet))  # Do not let malformed peers disappear behind another copy.
        manifest=packet['checkpoint'] if packet['schema']=='self-audit-embedding-v1' else packet['artifacts']['checkpoint']
        fields=checkpoint_observed_fields(manifest)
        manifests[digest(encoded(manifest))]=(manifest,fields)
        if fields is not None:
            fields_by_checkpoint[manifest['checkpoint_id']].add(digest(encoded(fields)))
    groups={m['checkpoint_id'] for m,_ in manifests.values()}
    states=dict.fromkeys(STATES,0)
    for manifest,fields in manifests.values():
        variants=by_checkpoint.get(manifest['checkpoint_id'],{})
        if not variants: state='fit_receipt_missing'
        elif len(variants)>1: state='conflicting_fit_receipts'
        elif len(fields_by_checkpoint[manifest['checkpoint_id']])>1: state='conflicting_manifests'
        else:
            fit=next(iter(variants.values()))
            if fit['checkpoint_observed_at']>=cutoff: state='fit_outside_cutoff'
            elif fields is None: state='legacy_manifest'
            elif (fit['mode']!=fields['mode'] or fit['checkpoint_bytes']!=fields['byte_count']
                  or fit['metadata_sha256']!=fields['metadata_sha256']): state='manifest_mismatch'
            else:
                clock=availability_receipt(manifest.get('availability'))
                if clock['state']!='observed' or clock['parameters_available_by'] is None:
                    state='read_clock_unknown'
                elif clock['parameters_available_by']>=cutoff: state='read_outside_cutoff'
                elif fit['checkpoint_observed_at']<=clock['read_started_at']: state='observed_before_read'
                elif fit['checkpoint_observed_at']<=clock['parameters_available_by']: state='overlapping_read'
                else: state='observed_after_read'
        states[state]+=1
    return {'scope':'supplied_fit_and_checkpoint_observations_only',
            'supplied_receipts':len(receipts),'unique_receipts':len(fits),'receipt_checkpoints':len(by_checkpoint),
            'supplied_artifact_packets':len(packets),'unique_checkpoint_observations':len(manifests),
            'checkpoint_groups':len(groups),
            'receipts_without_checkpoint_observation':sum(r['checkpoint_id'] not in groups for r in fits.values()),
            'states':states, 'source_identity':'unverified', 'encoder_identity':'unverified',
            'admission_effect':'none','scoring_effect':'none'}


def validate_coverage(value):
    fixed={'scope':'supplied_fit_and_checkpoint_observations_only','source_identity':'unverified',
           'encoder_identity':'unverified','admission_effect':'none','scoring_effect':'none'}
    if (not isinstance(value,dict) or set(value)!={*fixed,*COUNTS,'states'}
            or any(value[k]!=v for k,v in fixed.items())):
        raise ValueError('invalid fitting coverage contract')
    def count(n):
        if type(n) is not int or n<0: raise ValueError('invalid fitting coverage count')
        return n
    c={k:count(value[k]) for k in COUNTS}
    states=value['states']
    if not isinstance(states,dict) or set(states)!=set(STATES): raise ValueError('invalid fitting coverage states')
    n=c['unique_checkpoint_observations'];r=c['unique_receipts'];orphans=c['receipts_without_checkpoint_observation']
    if (sum(count(v) for v in states.values())!=n or n>c['supplied_artifact_packets']
            or r>c['supplied_receipts'] or not 0<=c['receipt_checkpoints']<=r
            or bool(c['receipt_checkpoints'])!=bool(r) or bool(r)!=bool(c['supplied_receipts'])
            or not 0<=c['checkpoint_groups']<=n or bool(c['checkpoint_groups'])!=bool(n)
            or bool(n)!=bool(c['supplied_artifact_packets']) or orphans>r
            or (not n and orphans!=r)
            or (not r and states['fit_receipt_missing']!=n)
            or (states['conflicting_fit_receipts'] and r-orphans<2)
            or (states['conflicting_manifests'] and n<2)
            or (n>states['fit_receipt_missing'] and r==orphans)):
        raise ValueError('inconsistent fitting coverage totals')
