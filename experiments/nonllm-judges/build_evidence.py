#!/usr/bin/env python3
"""Build numerical evidence from bounded retained projections; never discover stores."""
import copy
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('numerical_runner',HERE/'run_private.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
C=R.C;P=R.P;Q=R.Q
import witness_receipts as W


def unique(records,key):
    result={}
    for record in P.bounded(records):
        if not isinstance(record,dict) or not P.identifier(record.get(key)):raise ValueError('invalid projection identity')
        name=record[key]
        if name in result and P.canonical(result[name])!=P.canonical(record):raise ValueError('conflicting projection identity')
        result[name]=record
    return result


def build(bundle,lineage,cache,humor,cutoff):
    cutoff=P.stamp(cutoff)
    if 'numerical_evidence' in bundle:raise ValueError('refusing to replace existing numerical evidence')
    clean=copy.deepcopy(bundle)
    for k in ('controls','control_pool','feedback'):clean[k]=[]
    prepared,_,_,_,_=C.prepare(clean,cutoff)
    P.bounded(prepared)
    graph=unique(lineage,'id')
    # Include producer-attested final nodes, checking every copy before any selection.
    for row in bundle['rows']:
        if row.get('role')=='assistant' and isinstance(row.get('reply_node'),dict):
            node=row['reply_node'];key=node.get('id')
            if not P.identifier(key):raise ValueError('invalid final node identity')
            if key in graph and P.canonical(graph[key])!=P.canonical(node):raise ValueError('conflicting final node')
            graph[key]=node
    if len(graph)>P.LIMIT:raise ValueError('lineage exceeds bound')
    grouped=defaultdict(list)
    for row in bundle['rows']:
        if row.get('role')=='assistant':
            key,_=W.joined_identity(row)
            # A conflicting envelope still denies the explicit top-level act.
            key=key or row.get('turn_id')
            if P.identifier(key):grouped[key].append(row)
    reasons={k:Counter() for k in ('original_act','encoder_pin','encoder_freeze','humor_attempt','positive_anchor','taste_attempt')}
    evidence=dict(schema='numerical-evidence-v1',nodes=[],bindings=[],items=[],anchors=[],humor_attempt_ids=[],taste_attempt_ids=[])
    receipts=[];converted={}
    for row in prepared:
        copies=grouped.get(row['id'],[]);statuses=[]
        for raw in copies:
            status=W.admission(raw,graph,cutoff)
            receipt=W.row_receipt(raw)
            if status=='eligible' and 'reply_node' not in raw:status='final_lineage_not_recorded'
            if status=='eligible' and W.final_reply_status(raw,graph,receipt)!='clean':status='final_lineage_not_clean'
            if status=='eligible' and (receipt['finalized_at']!=row['at'] or receipt['response_sha256']!=row['sha']):status='final_binding_mismatch'
            statuses.append(status)
        why=next((s for s in statuses if s!='eligible'),None) or ('missing_source_copy' if not copies else 'recorded')
        reasons['original_act'][why]+=1
        receipts.append({'node_id':row['id'],'original_act':why,'source_copy_sha256':[W.digest(P.canonical(r)) for r in copies]})
        if why!='recorded':continue
        raw=copies[0];root=raw['reply_node']['id'];seen=set()
        def convert(key):
            # Keep the full validated ancestry, with deterministic private namespace IDs.
            out_id='ancestry-'+W.digest(key)
            if key in seen:return out_id
            seen.add(key);node=graph[key]
            parents=[convert(p) for p in node['parents']]
            value=dict(id=out_id,kind='context',at=W.instant(node['at']),parents=parents,complete=True)
            if out_id in converted and converted[out_id]!=value:raise ValueError('conflicting normalized ancestry')
            converted[out_id]=value
            return out_id
        ancestor=convert(root)
        if row['id'] in converted:raise ValueError('normalized identity collision')
        converted[row['id']]=dict(id=row['id'],kind='original_act',at=row['at'],parents=[ancestor],complete=True)
        evidence['bindings'].append(dict(node_id=row['id'],origin_id=row['id'],content_sha256=row['sha'],source='retained_witness_receipt'))
    evidence['nodes']=list(converted.values());P.bounded(evidence['nodes'])
    # Cache metadata must be bound to the exact cached input/context, not a nearby model label.
    cache_rows=unique(cache,'reply_sha256');embedding={r['reply_sha256']:r for r in bundle['embeddings']}
    pins=[];freezes=[];qualifiers=[];freeze_receipts=[];source_counts=Counter()
    for row in prepared:
        meta=cache_rows.get(row['sha']);old=embedding[row['sha']]
        linked=bool(meta and all(meta.get(k)==old.get(k) for k in ('reply_sha256','input_sha256','context_sha256','encoder_id')))
        pin=meta.get('artifact_sha256') if linked else None
        pin_reason='recorded' if P.hashed(pin) else ('missing_metadata' if meta is None else 'missing_or_unbound_pin')
        declared=bundle['encoder'].get('artifact_sha256')
        if pin_reason=='recorded' and declared is not None and declared!=pin:pin_reason='conflicting_declared_pin'
        frozen=None
        if linked and meta.get('frozen_at') is not None:
            try:frozen=P.stamp(meta['frozen_at'])
            except (ValueError,TypeError,OverflowError):pass
        source='legacy_unknown';freeze_receipt=None
        if linked:
            source=meta.get('freeze_source','legacy_unknown');freeze_receipt=meta.get('freeze_receipt')
            if source in ('copy_time','published_artifact'):
                Q.verify(freeze_receipt,pin,meta.get('frozen_at'),source)
            elif source!='legacy_unknown' or freeze_receipt is not None:raise ValueError('invalid freeze qualifier')
        source_counts[source if linked and frozen is not None else 'unknown']+=1
        qualifiers.append(source);freeze_receipts.append(freeze_receipt)
        freeze_reason='recorded' if frozen is not None and 0<=frozen<row['at'] else ('missing_metadata' if meta is None else 'missing_invalid_or_late_freeze')
        reasons['encoder_pin'][pin_reason]+=1;reasons['encoder_freeze'][freeze_reason]+=1
        pins.append(pin if pin_reason=='recorded' else None);freezes.append(frozen if freeze_reason=='recorded' else None)
    output=copy.deepcopy(bundle)
    coherent=bool(prepared and None not in pins and None not in freezes and len(set(pins))==len(set(freezes))==len(set(qualifiers))==1
                  and len({P.canonical(r) for r in freeze_receipts})==1)
    if coherent:
        output['encoder']['artifact_sha256']=pins[0];evidence['encoder_frozen_at']=freezes[0]
        evidence['encoder_freeze_source']=qualifiers[0]
        if freeze_receipts[0] is not None:evidence['encoder_freeze_receipt']=freeze_receipts[0]
    elif prepared and None not in pins and None not in freezes:
        reasons['encoder_pin']['inconsistent_cache_metadata']+=len(prepared)
        reasons['encoder_freeze']['inconsistent_cache_metadata']+=len(prepared)
    drafts=unique(humor,'joke_id');used=set()
    for row in prepared:
        copies=grouped.get(row['id'],[]);ids=[r.get('joke_id') for r in copies]
        key=ids[0] if ids and all(i==ids[0] for i in ids) else None
        draft=drafts.get(key) if P.identifier(key) else None
        why='recorded' if draft and isinstance(draft.get('joke'),str) and draft['joke']==row['text'] else 'missing_or_unbound_joke_id'
        if why=='recorded':
            for raw in copies:
                binding=raw.get('joke_binding')
                if ('joke_text_sha256' in raw and raw['joke_text_sha256']!=row['sha'] or
                        binding is not None and binding!=dict(schema='humor-reply-binding-v1',turn_id=row['id'],
                            joke_id=key,joke_text_sha256=row['sha'],response_sha256=row['sha'],source='exact_full_reply_draft')):
                    why='conflicting_joke_binding';break
        reasons['humor_attempt'][why]+=1
        evidence['items'].append(dict(node_id=row['id'],kind='joke' if why=='recorded' else 'message'))
        if why=='recorded':evidence['humor_attempt_ids'].append(row['id']);used.add(key)
    reasons['positive_anchor']['not_derived_from_attempts']=len(prepared)
    reasons['taste_attempt']['not_recorded']=len(prepared)
    output['numerical_evidence']=evidence
    output['evidence_builder']={'schema':'evidence-builder-private-v1','receipts':receipts,
        'lineage_projection':lineage,'cache_metadata_projection':cache,'humor_drafts_projection':humor,
        'source_claims_independently_verified':False,'cutoff':cutoff}
    summary={'schema':'evidence-builder-counts-v1','character_replies':len(prepared),
        'original_act_bindings':len(evidence['bindings']),'normalized_ancestry_nodes':len(evidence['nodes']),
        'encoder_metadata_available':coherent,'encoder_freeze_sources':{s:source_counts[s] for s in Q.SOURCES},'humor_attempts':len(evidence['humor_attempt_ids']),
        'unjoined_humor_drafts':len(drafts)-len(used),'per_field_reason_counts':{k:dict(sorted(v.items())) for k,v in reasons.items()},
        'source_claims_independently_verified':False,'model_calls':0}
    return output,summary


def main(argv=None):
    p=R.Parser(description=__doc__)
    for k in ('input','scratch','output','summary','cutoff'):p.add_argument('--'+k,required=True)
    for k in ('lineage','cache','humor'):p.add_argument('--'+k)
    args=p.parse_args(argv);root=C.scratch_root(args.scratch)
    if any((parent/'.git').exists() for parent in (root,*root.parents)):raise ValueError('scratch cannot be inside repository')
    paths={k:C.inside(root,getattr(args,k)) for k in ('input','lineage','cache','humor') if getattr(args,k)}
    output=C.inside(root,args.output);summary=C.inside(root,args.summary);out=output.parent
    if output==summary or out!=summary.parent or out==root or out.exists():raise ValueError('outputs require shared new directory')
    if any(out==s or out in s.parents for s in paths.values()):raise ValueError('input cannot be output descendant')
    C.install_guard(root,out);inputs={};hashes={}
    for k,path in paths.items():inputs[k],hashes[k]=R.read_projection(path,64*1024*1024 if k=='input' else 16*1024*1024)
    fields={'lineage':('witness-lineage-projection-v1','nodes'),'cache':('encoder-cache-metadata-v1','entries'),'humor':('humor-drafts-projection-v1','drafts')}
    for key,(schema,field) in fields.items():
        if key in inputs:
            value=inputs[key]
            if set(value)!={'schema',field} or value['schema']!=schema:raise ValueError('invalid projection schema')
            inputs[key]=value[field]
    private,public=build(inputs['input'],inputs.get('lineage',[]),inputs.get('cache',[]),inputs.get('humor',[]),args.cutoff)
    private['evidence_builder']['manifest']={'input_sha256':hashes,'code_sha256':{str(path.relative_to(R.REPO)):W.digest(path.read_text()) for path in
        (Path(__file__),Path(Q.__file__),Q.PIN_FILE,HERE/'run_private.py',HERE/'prototype.py',HERE/'voice_drift.py',HERE/'witnessed_facets.py',
         HERE.parent/'character-reference/prototype.py',HERE.parent/'judges-witness/replay.py',
         R.REPO/'scripts/witness_attribution.py',R.REPO/'scripts/witness_receipts.py',R.REPO/'scripts/evidence_view.py',R.REPO/'scripts/evidence_provenance.py')},
        'served_model':None,'fallback':None,'model_calls':0}
    payloads=[(output,json.dumps(private,sort_keys=True,allow_nan=False)),(summary,json.dumps(public,sort_keys=True,allow_nan=False))]
    out.mkdir(mode=0o700)
    for path,data in payloads:
        with path.open('x') as f:path.chmod(0o600);f.write(data+'\n')
    print(json.dumps({'written':True,'reports':2}))


if __name__=='__main__':
    try:main()
    except Exception:
        print(json.dumps({'written':False,'error':'evidence_build_failed'}),file=sys.stderr);sys.exit(1)
