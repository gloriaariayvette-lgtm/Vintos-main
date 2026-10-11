"""Consume one owned partial Forge acquisition; identity checks never fulfill its task."""
import copy
import hashlib
import json
import re
from pathlib import Path

PENDING = 'capability_available_verification_required'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def identity(row, owner):
    return digest({'project_id':row.get('project_id'), 'cycle_id':row.get('cycle_id'),
                   'outbox_key':row.get('outbox_key'), 'original_request':row.get('original_request'),
                   'artifact':row.get('artifact'), 'accepted_receipt':row.get('accepted_receipt'),
                   'sequence_handle':row.get('sequence_handle'),
                   'ownership_sha256':row.get('ownership_sha256'), 'source_receipt_ids':row.get('source_receipt_ids'),
                   'owner':{key:owner.get(key) for key in ('project_id','state','question','receipt_ids')}})


def owned(row, owner, cycle):
    from forge_lab_handback import ownership
    return (isinstance(row, dict) and isinstance(owner, dict) and row.get('cycle_id') == cycle
            and isinstance(row.get('original_request'), str) and bool(row['original_request'])
            and owner.get('state') == 'accepted' and owner.get('project_id') == row.get('project_id')
            and isinstance(owner.get('question'), str) and owner['question'][:2000] == row['original_request']
            and row.get('ownership_sha256') == ownership(owner))


def validate(row, owner):
    """Revalidate untrusted handback; collector acceptance alone is not sufficient."""
    from forge_genomic_result import validate_request, verified_result
    artifact = row['artifact']; request = artifact['capability_resolution']['request']
    outcome = artifact['capability_resolution']['result']; rec = outcome['receipt']
    handback = artifact['lab_handback']; accepted = row['accepted_receipt']
    if (handback['cycle_id'] != row['cycle_id'] or accepted['cycle_id'] != row['cycle_id']
            or handback['original_request'] != row['original_request']
            or handback['status'] != 'capability_available_original_request_unfulfilled'
            or type(accepted['charged_cents']) is not int or accepted['charged_cents'] != 0
            or row.get('original_request_fulfilled') is not False):
        raise ValueError('handback ownership or completion claim is invalid')
    validate_request(request, {'intent':owner['question']})
    if (outcome.get('ok') is not True or rec.get('surface') != 'forge'
            or rec.get('plugin') != request['plugin'] or rec.get('tool') != request['tool']
            or not re.fullmatch('[a-f0-9]{64}', str(rec.get('receipt_id','')))
            or rec.get('receipt_id') != rec.get('result_sha256')
            or rec.get('arguments_sha256') != digest(request['arguments'])):
        raise ValueError('connector receipt is not bound to this request')
    handle = verified_result(outcome, request)
    if handle != row['sequence_handle']:
        raise ValueError('sequence handle differs from accepted artifact')
    return request


def check_identity_receipt(value, symbol):
    if (not isinstance(value, dict) or value.get('source') != 'ncbi_gene_identity'
            or value.get('query') != {'symbol':symbol, 'taxon_id':9606}
            or value.get('response_sha256') != digest(value.get('records'))):
        raise ValueError('identity receipt does not bind the requested target')
    body = dict(value); rid = body.pop('receipt_id', None)
    if rid != digest(body):
        raise ValueError('identity receipt hash mismatch')
    rows = value.get('records')
    if not isinstance(rows, list):raise ValueError('invalid identity records')
    verified = value.get('metadata',{}).get('status') == 'verified'
    if verified:
        if len(rows) != 1:raise ValueError('ambiguous identity')
        row=rows[0]; names=[row.get('symbol')]+list(row.get('aliases') or [])
        if row.get('taxon_id') != 9606 or symbol.upper() not in {str(n).upper() for n in names}:
            raise ValueError('identity source returned a different target')
    elif value.get('metadata',{}).get('status') != 'unresolved':
        raise ValueError('unknown identity status')
    return verified


def consume_one(lab, *, verify=None, locus=None, acknowledge=None):
    """Called at an ordinary orient boundary. Never hold the Lab lock during source work.

    The canonical per-cycle outcome is the acknowledgement. It acknowledges only
    verification processing, never Forge completion or original-request fulfillment.
    A durable claim prevents repeated source calls, including after interruption.
    """
    cfg=lab.config()
    if not cfg.get('enabled') or not cfg.get('allow_public_database_reads') or lab.stop_requested():return None
    root=Path(lab.ROOT); ledger=str(root/'forge-capability-handbacks.json'); outbox=str(root/'forge-report-outbox.json')
    ack_result=_ack_one(lab,cfg,ledger,outbox,acknowledge)
    if ack_result:return ack_result
    from lab_forge_followup import advance
    followup=advance(lab,ledger,outbox)
    if followup:return followup
    selected=None
    with lab._locked():
        rows=lab._load(ledger, {}); owners=lab._load(outbox, {})
        if not isinstance(rows,dict) or not isinstance(owners,dict):return None
        for cycle,row in rows.items():
            if not isinstance(row,dict):continue
            if not isinstance(row.get('outbox_key'),str):continue
            owner=owners.get(row.get('outbox_key'),{})
            if not owned(row,owner,cycle):continue
            prior=row.get('verification')
            if prior:
                if not isinstance(prior,dict):continue
                # Recover projection after canonical write without re-verifying.
                if prior.get('consumer_status') == 'recorded' and prior.get('input_sha256') == identity(row,owner):
                    _project(lab,row,owner,outbox,owners,ledger,rows)
                if prior.get('state') != 'pending':continue
            if row.get('state') != PENDING:continue
            try:fingerprint=identity(row,owner)
            except (TypeError,ValueError):continue
            snapshot=copy.deepcopy(row); owner_snapshot=copy.deepcopy(owner)
            row['verification']={'state':'running','input_sha256':fingerprint,'started_at':lab.now_iso(),
                                 'ownership_sha256':row['ownership_sha256'],'evidence_receipt_ids':[],
                                 'original_request_fulfilled':False,
                                 'meaning':'durable claim; if interrupted, do not replay automatically'}
            row['state']='verification_in_progress'
            lab._atomic(ledger,rows)
            selected=(cycle,snapshot,owner_snapshot,fingerprint);break
    if selected is None:return None
    cycle,row,owner,fingerprint=selected
    result={'original_request':owner['question'],'original_request_fulfilled':False,
            'sequence_identity_status':'unverified','task_status':'pending_original_request'}
    receipt=None; verdict=None
    try:
        request=validate(row,owner); args=request['arguments']
        result['acquisition_integrity']='verified'
        from lab_gene_locus import commissioned, lookup, check
        if commissioned(row['original_request'],args):
            receipt=(locus or lookup)(row,args)
            verdict=check(receipt,row,args)
            result.update(target_identity_status=verdict,original_request_fulfilled=True,
                          task_status='reference_lookup_complete_ack_pending',
                          reference_scope=receipt['records']['reference'],
                          next_step='Deliver the durable reference evidence acknowledgement; do not repeat the lookup.')
        elif (request['tool'] != 'genomic_intelligence.fetch_ensembl_sequence'
                or args['species'].casefold() not in ('human','homo sapiens')
                or not re.fullmatch('[A-Za-z][A-Za-z0-9-]{0,29}',args.get('gene',''))):
            result.update(target_identity_status='unsupported_verification',
                          next_step='Obtain authoritative target/species/locus evidence and bind it to the returned sequence handle before resuming the unchanged original request.')
        else:
            if verify is None:
                from lab_sources import Sources
                verify=Sources().human_gene_identity
            receipt=verify(args['gene'])
            matched=check_identity_receipt(receipt,args['gene'])
            result.update(target_identity_status='verified' if matched else 'unresolved',
                          identity_receipt_id=receipt['receipt_id'],
                          next_step=('Bind the acquired sequence handle to this verified target, then resume the unchanged original request; gene identity alone does not verify the handle or fulfill the action.' if matched else
                                     'Resolve the exact original target and species from authoritative evidence; do not substitute a numbered sibling or repeat this unchanged acquisition.'))
    except Exception as exc:
        receipt=None;verdict=None
        result['original_request_fulfilled']=False
        result.update(target_identity_status='verification_failed',error_type=type(exc).__name__,
                      next_step='Review the failed acquisition/identity evidence before retrying; the unchanged original request remains unfulfilled.')
    with lab._locked():
        rows=lab._load(ledger,{}); owners=lab._load(outbox,{})
        current=rows.get(cycle,{}); current_owner=owners.get(row.get('outbox_key'),{})
        if (not owned(current,current_owner,cycle) or identity(current,current_owner) != fingerprint
                or (current.get('verification') or {}).get('input_sha256') != fingerprint):
            return {'kind':'forge_handback_stale','cycle_id':cycle,'original_request_fulfilled':False}
        current['state']='verification_recorded_original_request_pending'
        current['verification']={'state':verdict or ('partial' if result['target_identity_status']=='verified' else 'unresolved'),
                                 'consumer_status':'recorded','input_sha256':fingerprint,'finished_at':lab.now_iso(),
                                 'ownership_sha256':current['ownership_sha256'],
                                 'evidence_receipt_ids':[receipt['receipt_id']] if receipt else [],
                                 'original_request_fulfilled':bool(verdict),
                                 'outcome':result,'source_receipt':receipt}
        current['acknowledgement']={'kind':'verification_recorded','cycle_id':cycle,
                                    'original_request_fulfilled':False,'target_identity_status':result['target_identity_status']}
        if verdict:
            from lab_gene_locus import request_digest
            current['acknowledgement']={'state':'pending','attempts':0,'next_attempt':0,'body':{
                'project_id':current['project_id'],'cycle_id':cycle,'ownership_sha256':current['ownership_sha256'],
                'original_request_sha256':request_digest(current['original_request']),
                'evidence_receipt_ids':[receipt['receipt_id']],'verdict':verdict}}
        lab._atomic(ledger,rows)  # canonical first; projection is recoverable
        _project(lab,current,current_owner,outbox,owners,ledger,rows)
    return {'kind':'forge_handback_verification','cycle_id':cycle,'project_id':row['project_id'],**result}


def _project(lab,row,owner,outbox,owners,ledger,rows):
    """Lock held by caller; append itself is deliberately lock-free in chemistry_lab."""
    verification=row['verification']; receipt=verification.get('source_receipt')
    if receipt and not verification.get('receipt_published'):
        path=str(Path(lab.ROOT)/'source-receipts.jsonl')
        if not any(old.get('receipt_id')==receipt['receipt_id'] for old in lab._tail_jsonl(path,nbytes=8*1024*1024)):
            lab._append(path,receipt)
        verification['receipt_published']=True;lab._atomic(ledger,rows)
    from forge_lab_handback import pointer as project_pointer
    pointer=project_pointer(row)
    if owner.get('capability_handback') != pointer:
        owner['capability_handback']=pointer;lab._atomic(outbox,owners)


def _ack_one(lab,cfg,ledger,outbox,acknowledge):
    """Recoverable acknowledgement only; never replay public source or model work."""
    import time
    from lab_gene_locus import send_ack
    claim=None
    with lab._locked():
        rows=lab._load(ledger,{});owners=lab._load(outbox,{})
        for cycle,row in rows.items():
            if not isinstance(row,dict):continue
            owner=owners.get(row.get('outbox_key'),{})
            if not owned(row,owner,cycle):continue
            ack=row.get('acknowledgement') or {};v=row.get('verification') or {}
            if (ack.get('state') not in ('pending','sending') or ack.get('next_attempt',0)>time.time()
                    or v.get('input_sha256')!=identity(row,owner) or not v.get('original_request_fulfilled')):continue
            ack.update(state='sending',attempts=ack.get('attempts',0)+1,next_attempt=time.time()+300)
            lab._atomic(ledger,rows)
            claim=(cycle,copy.deepcopy(ack['body']),identity(row,owner));break
    if claim is None:return None
    cycle,body,fingerprint=claim
    try:
        answer=(acknowledge or send_ack)(cfg,body)
        # Server acknowledgement schema is checked below; success cannot be a local boolean.
        if not isinstance(answer,dict) or answer.get('acknowledged') is not True or answer.get('project_id')!=body['project_id'] or answer.get('cycle_id')!=cycle:raise ValueError('completion acknowledgement missing')
        error=None
    except Exception as exc:error=type(exc).__name__
    with lab._locked():
        rows=lab._load(ledger,{});owners=lab._load(outbox,{})
        row=rows.get(cycle,{});owner=owners.get(row.get('outbox_key'),{})
        if not owned(row,owner,cycle) or identity(row,owner)!=fingerprint:return {'kind':'forge_handback_stale','cycle_id':cycle}
        ack=row['acknowledgement']
        ack.update(state='pending' if error else 'delivered',error_type=error)
        lab._atomic(ledger,rows)
    return {'kind':'forge_verification_ack_pending' if error else 'forge_verification_acknowledged',
            'cycle_id':cycle,'original_request_fulfilled':not bool(error)}
