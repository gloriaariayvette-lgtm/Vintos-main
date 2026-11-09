"""Offline pending-file handoff consistency; no source authentication or admission."""
from collections import defaultdict
import json
import re
from witness_receipts import digest, instant

STATES = ('outside_cutoff','not_on_message','job_receipt_missing','conflicting_receipts',
          'launch_receipt_missing','origin_markers_missing','pending_row_mismatch','joined')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def hashed(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def validate_receipt(value):
    if not isinstance(value,dict): raise ValueError('invalid forecast handoff')
    launch=value.get('schema')=='self-forecast-launch-v1'
    keys={'schema','pending','boundary','source_identity'}
    if not launch: keys.add('forecast_row_sha256')
    if (set(value)!=keys or value['source_identity']!='unverified'
            or value['boundary']!=('runner_return' if launch else 'forecast_log_close')
            or (not launch and (value['schema']!='self-forecast-handoff-v1'
                               or not hashed(value['forecast_row_sha256'])))):
        raise ValueError('invalid forecast handoff contract')
    p=value['pending']
    if not isinstance(p,dict) or set(p)!={'resource_sha256','pending_sha256','her_sha256',
                                         'arrived_at','surface_sha256','turn_id_sha256'}:
        raise ValueError('invalid forecast pending observation')
    for key in ('resource_sha256','pending_sha256','her_sha256','surface_sha256','turn_id_sha256'):
        if key in ('surface_sha256','turn_id_sha256') and p[key] is None: continue
        if not hashed(p[key]): raise ValueError('invalid forecast pending hash')
    if type(p['arrived_at']) not in (int,float): raise ValueError('invalid pending clock')
    instant(p['arrived_at'])
    encoded(value)
    return launch


def coverage(forecasts, receipts, cutoff):
    """All supplied receipts validated before cutoff; duplicates are not new witnesses."""
    cutoff=instant(cutoff)
    if not isinstance(forecasts,list) or not isinstance(receipts,list):
        raise ValueError('forecast handoff inputs must be lists')
    rows={}
    for row in forecasts:
        if not isinstance(row,dict): raise ValueError('invalid forecast row')
        instant(row['ts'])
        rows[digest(encoded(row))]=row
    launches=defaultdict(set);jobs=defaultdict(set);resources=defaultdict(set)
    unique={}
    resource_rows=defaultdict(set)
    for packet in receipts:
        launch=validate_receipt(packet)
        key=encoded(packet);unique[key]=packet
        descriptor=encoded(packet['pending']);resource=packet['pending']['resource_sha256']
        resources[resource].add(descriptor)
        if launch: launches[resource].add(descriptor)
        else:
            jobs[packet['forecast_row_sha256']].add(descriptor)
            resource_rows[resource].add(packet['forecast_row_sha256'])
    job_descriptors=set().union(*jobs.values()) if jobs else set()
    states=dict.fromkeys(STATES,0)
    for key,row in rows.items():
        if instant(row['ts'])>=cutoff: state='outside_cutoff'
        elif row.get('mode')!='on_message': state='not_on_message'
        elif key not in jobs: state='job_receipt_missing'
        elif len(jobs[key])!=1: state='conflicting_receipts'
        else:
            descriptor=next(iter(jobs[key]));p=json.loads(descriptor);resource=p['resource_sha256']
            # Include orphan and out-of-window peers: one consumed pending file
            # cannot silently certify several distinct saved rows.
            if len(resources[resource])!=1 or len(resource_rows[resource])!=1:
                state='conflicting_receipts'
            elif descriptor not in launches[resource]: state='launch_receipt_missing'
            elif p['turn_id_sha256'] is None or p['surface_sha256'] is None: state='origin_markers_missing'
            else:
                try:
                    matched=(isinstance(row.get('turn_id'),str) and isinstance(row.get('surface'),str)
                             and digest(row['turn_id'])==p['turn_id_sha256']
                             and digest(row['surface'])==p['surface_sha256']
                             and instant(row['arrived_at'])==p['arrived_at']<=instant(row['ts']))
                except (KeyError,TypeError,ValueError,OverflowError): matched=False
                state='joined' if matched else 'pending_row_mismatch'
        states[state]+=1
    return {'scope':'supplied_forecast_handoffs_only', 'forecast_rows':len(rows),
            'unique_receipts':len(unique), 'launch_receipts':sum(p['schema']=='self-forecast-launch-v1' for p in unique.values()),
            'job_receipts':sum(p['schema']=='self-forecast-handoff-v1' for p in unique.values()),
            'launch_receipts_without_job':sum(p['schema']=='self-forecast-launch-v1' and encoded(p['pending']) not in job_descriptors for p in unique.values()),
            'job_receipts_without_row':sum(p['schema']=='self-forecast-handoff-v1' and p['forecast_row_sha256'] not in rows for p in unique.values()),
            'states':states, 'source_identity':'unverified','scoring_effect':'none'}


def validate_coverage(value):
    keys={'scope','forecast_rows','unique_receipts','launch_receipts','job_receipts',
          'launch_receipts_without_job','job_receipts_without_row','states','source_identity','scoring_effect'}
    if (not isinstance(value,dict) or set(value)!=keys or value['scope']!='supplied_forecast_handoffs_only'
            or value['source_identity']!='unverified' or value['scoring_effect']!='none'):
        raise ValueError('invalid forecast handoff aggregate')
    def count(n):
        if type(n) is not int or n<0: raise ValueError('invalid forecast handoff count')
        return n
    counts={k:count(value[k]) for k in keys-{'scope','states','source_identity','scoring_effect'}}
    if not isinstance(value['states'],dict) or set(value['states'])!=set(STATES):
        raise ValueError('invalid forecast handoff states')
    states={k:count(v) for k,v in value['states'].items()}
    if (sum(states.values())!=counts['forecast_rows']
            or counts['launch_receipts']+counts['job_receipts']!=counts['unique_receipts']
            or counts['launch_receipts_without_job']>counts['launch_receipts']
            or counts['job_receipts_without_row']>counts['job_receipts']
            or sum(states[k] for k in STATES[3:])>counts['job_receipts']-counts['job_receipts_without_row']
            or (states['joined'] and not counts['launch_receipts'])):
        raise ValueError('invalid forecast handoff totals')
