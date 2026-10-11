"""Resume the observed human-gene question; never fulfill its build/connect wrapper."""
import copy
import re
from pathlib import Path

def scientific_question(original,gene):
    expected=f'Does the {gene} gene exist in the human genome, and what is its structural topology or functional context if it does?'
    if original==expected:return expected
    marker='It came up on this question: '+expected+'\nBuild or connect this capability for him; do not write up the question and do not claim discovery.'
    return expected if original.endswith(marker) else None

def advance(lab,ledger,outbox):
    from lab_forge_consumer import identity,owned,validate,digest
    from lab_sources import verified_human_identity
    claim=None
    with lab._locked():
        rows=lab._load(ledger,{});owners=lab._load(outbox,{})
        for cycle,row in rows.items():
            if not isinstance(row,dict):continue
            owner=owners.get(row.get('outbox_key'),{})
            if not owned(row,owner,cycle):continue
            v=row.get('verification') or {}
            if v.get('consumer_status')!='recorded' or v.get('original_request_fulfilled') or v.get('input_sha256')!=identity(row,owner):continue
            try:args=validate(row,owner)['arguments']
            except (ValueError,KeyError,TypeError):continue
            if args.get('species','').casefold() not in ('human','homo sapiens','homo_sapiens'):continue
            question=scientific_question(owner['question'],args.get('gene'))
            if not question:continue
            follow=row.setdefault('continuation',{'stage':'identity_blocked','scientific_question':question,
                'original_request':owner['question'],'original_request_fulfilled':False,
                'blockers':['authoritative exact-target identity','sequence-handle binding','capability build/connect evidence']})
            # Resume only when genuinely different, fully validated identity evidence exists.
            if follow['stage']=='identity_blocked':
                candidates=[v.get('source_receipt')]+lab._tail_jsonl(str(Path(lab.ROOT)/'source-receipts.jsonl'),nbytes=8*1024*1024)
                found=next((r for r in reversed(candidates) if isinstance(r,dict) and verified_human_identity(r,args['gene'])
                            and r.get('response_sha256')!=follow.get('identity_response_sha256')),None)
                if found:
                    follow.update(stage='browse_pending',identity_receipt=found,identity_response_sha256=found['response_sha256'])
                else:
                    # Record the blocked checkpoint once, then leave ordinary work free to advance.
                    first=not follow.get('recorded');follow['recorded']=True;lab._atomic(ledger,rows)
                    if first:return {'kind':'forge_followup_blocked','cycle_id':cycle,'original_request_fulfilled':False,'blocker':'authoritative exact-target identity'}
                    continue
            stage=follow['stage']
            if stage not in ('browse_pending','assessment_pending'):continue
            follow.update(stage=stage.replace('_pending','_running'),started_at=lab.now_iso())
            lab._atomic(ledger,rows)
            claim=(cycle,copy.deepcopy(row),copy.deepcopy(owner),identity(row,owner),stage,args);break
    if claim is None:return None
    cycle,snapshot,owner,fingerprint,stage,args=claim
    follow=snapshot['continuation'];result=None;error=None
    try:
        if stage=='browse_pending':
            query='gene:'+args['gene']+' AND taxonomy_id:9606'
            result=lab._browse(query,4,allow_relaxation=False)
            rec=result['source_receipt'];unsigned=dict(rec);rid=unsigned.pop('receipt_id',None)
            if (rid!=digest(unsigned) or rec.get('response_sha256')!=digest(rec.get('records'))
                    or rec.get('source')!='uniprot' or rec.get('query')!={'requested_query':query,'executed_query':query}
                    or result.get('relaxed') or result.get('scope_resolution')):raise ValueError('strict browse evidence required')
        else:
            context,_=lab.lab_context()
            result=lab._reflect(context,{'question':follow['scientific_question'],
                                'query':'gene:'+args['gene']+' AND taxonomy_id:9606'},follow['browse']['records'])
    except Exception as exc:error=type(exc).__name__
    with lab._locked():
        rows=lab._load(ledger,{});owners=lab._load(outbox,{})
        row=rows.get(cycle,{});owner=owners.get(row.get('outbox_key'),{})
        if not owned(row,owner,cycle) or identity(row,owner)!=fingerprint:return {'kind':'forge_handback_stale','cycle_id':cycle}
        current=row['continuation']
        if current['stage']!=stage.replace('_pending','_running'):return {'kind':'forge_handback_stale','cycle_id':cycle}
        if error:current.update(stage='blocked',error_type=error,blockers=['failed bounded follow-up; explicit review required'])
        elif stage=='browse_pending':
            current.update(stage='assessment_pending' if result.get('records') else 'blocked',browse=result)
            lab._append(str(Path(lab.ROOT)/'source-receipts.jsonl'),result['source_receipt'])
            if not result.get('records'):current['blockers']=['exact-target protein annotation unavailable','sequence-handle binding','capability build/connect evidence']
        else:
            answered=(result.get('evidence_status')=='answered' and (result.get('coverage_check') or {}).get('answered') is True)
            current.update(stage='blocked',assessment=result,scientific_question_answered=answered,
                           blockers=([] if answered else ['full scientific-question coverage'])+['sequence-handle binding','capability build/connect evidence'])
        lab._atomic(ledger,rows)
    return {'kind':'forge_followup_'+current['stage'],'cycle_id':cycle,'original_request_fulfilled':False,
            'scientific_question':follow['scientific_question']}
