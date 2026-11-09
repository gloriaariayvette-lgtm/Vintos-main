#!/usr/bin/env python3
"""Offline numerical judges from explicit private projections, never live stores."""
import argparse
from collections import Counter, defaultdict
import copy
from datetime import date, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
sys.dont_write_bytecode=True

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('positive_facets',HERE/'witnessed_facets.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
V=F.V;P=V.P;C=V.C


class Parser(argparse.ArgumentParser):
    def error(self,message):raise ValueError('invalid command options')


def read_projection(path,limit):
    if not stat.S_ISREG(path.stat().st_mode):raise ValueError('regular projection file required')
    with path.open('rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('projection exceeds bound')
    return C.decode_snapshot(raw),hashlib.sha256(raw).hexdigest()


def adapt(bundle,cutoff):
    # Foreign-control review is independent work, not part of these numerical judges.
    char=copy.deepcopy(bundle)
    for field in ('controls','control_pool','feedback'):char[field]=[]
    prepared,_,candidate_days,_,char_coverage=C.prepare(char,cutoff)
    if len(prepared)>P.LIMIT:raise ValueError('numerical projection exceeds 512 admitted replies')
    supplied=bundle.get('numerical_evidence',{})
    if not isinstance(supplied,dict):raise ValueError('invalid numerical evidence')
    allowed={'schema','nodes','bindings','encoder_frozen_at','items','anchors','humor_attempt_ids','taste_attempt_ids','reference_ids'}
    if supplied and (supplied.get('schema')!='numerical-evidence-v1' or set(supplied)-allowed):
        raise ValueError('unknown numerical evidence schema')
    nodes=supplied.get('nodes',[]);bindings={}
    for binding in P.bounded(supplied.get('bindings',[])):
        if (not isinstance(binding,dict) or set(binding)!={'node_id','origin_id','content_sha256','source'}
                or not P.identifier(binding['node_id']) or not P.identifier(binding['origin_id'])
                or not P.hashed(binding['content_sha256']) or not P.identifier(binding['source'])):
            raise ValueError('invalid original-act binding')
        key=binding['node_id']
        if key in bindings and bindings[key]!=binding:raise ValueError('conflicting original-act binding')
        bindings[key]=binding
    events=[];features=[];reasons=Counter();encoder=None
    old=bundle['encoder'];artifact=old.get('artifact_sha256');frozen=supplied.get('encoder_frozen_at')
    # A missing pin/time is unknown, never a zero timestamp or an invented artifact.
    if artifact is not None and not P.hashed(artifact):raise ValueError('invalid artifact pin')
    if frozen is not None:frozen=P.stamp(frozen)
    if artifact is not None and frozen is not None:
        dimensions={len(r['vector']) for r in prepared}
        if dimensions:encoder=dict(id=old['id'],artifact_sha256=artifact,frozen_at=frozen,frozen=True,dimension=next(iter(dimensions)))
    for row in prepared:
        binding=bindings.get(row['id'])
        if binding is None or binding['content_sha256']!=row['sha']:
            reasons['missing_or_unbound_original_act']+=1;continue
        if encoder is None:reasons['encoder_pin_or_freeze_unknown']+=1;continue
        # New preparation enforces known modes, supported surfaces and complete ancestry.
        mode={'opening_everyday':'everyday','intimate':'intimate'}.get(row.get('mode'),'unknown')
        source={'prospective_receipt':'router_decision','somatic_narration':'reviewed_somatic_interval'}.get(row.get('mode_source'),row.get('mode_source'))
        if source not in V.MODE_SOURCES:source='unknown'
        mode_binding={'mode':row.get('mode'),'source':row.get('mode_source'),
                      'evidence':row.get('mode_evidence_sha256',[])}
        events.append(dict(node_id=row['id'],origin_id=binding['origin_id'],at=row['at'],content_sha256=row['sha'],
                           surface=row['surface'],mode=mode,source=binding['source']))
        features.append(dict(node_id=row['id'],content_sha256=row['sha'],text=row['text'],vector=row['vector'].tolist(),
                             encoder_id=old['id'],artifact_sha256=artifact,mode_source=source,
                             mode_evidence_sha256=hashlib.sha256(P.canonical(mode_binding).encode()).hexdigest()))
    items=supplied.get('items',[{'node_id':r['id'],'kind':'message'} for r in prepared])
    return prepared,candidate_days,char_coverage,supplied,events,nodes,features,encoder,items,dict(sorted(reasons.items()))


def date_windows(days):
    result=[]
    for day in sorted(set(days)):
        date.fromisoformat(day)
        if result and date.fromisoformat(day)==date.fromisoformat(result[-1]['end_date'])+timedelta(days=1):
            result[-1]['end_date']=day
        else:result.append({'start_date':day,'end_date':day})
    return result


def facet_counts(report,details,requested):
    if report is None:return {'requested':requested,'scored':0,'unscored':requested,'abstain':requested,
                              'positive_acts':None,'positive_act_days':None,'positive_observation_days':None,'outcomes_unassessed':True}
    scored=sum(d['similarity'] is not None for d in details)
    return {'requested':requested,'scored':scored,'unscored':requested-scored,
            'abstain':requested-sum(d['band_location']!='abstain' for d in details),
            'empirically_ranked':report['empirically_ranked_attempts'],
            'positive_acts':report['outcomes']['positive_original_acts'],
            'positive_act_days':report['outcomes']['positive_act_days'],
            'positive_observation_days':report['outcomes']['positive_observation_days'],
            'outcomes_unassessed':False,'observation_counts':report['outcomes']['excluded_or_unknown']}


def evaluate(bundle,landings,cutoff,view='both'):
    cutoff=P.stamp(cutoff)
    if view not in {'both','primary_10s','window30'}:raise ValueError('invalid attribution view')
    rows,candidates,char_coverage,supplied,events,nodes,features,encoder,items,adapter_counts=adapt(bundle,cutoff)
    if landings is None:landings={'schema':'landings-projection-v1','anchors':[]}
    if not isinstance(landings,dict) or set(landings)!={'schema','anchors'} or landings['schema']!='landings-projection-v1':
        raise ValueError('invalid Landings projection')
    for anchor in P.bounded(landings['anchors']):
        if (not isinstance(anchor,dict) or anchor.get('source')!='landings' or anchor.get('value')!='landed'
                or anchor.get('link',{}).get('kind')!='exact_item' or anchor.get('actor')!='owner'
                or anchor.get('witnessed') is not True):raise ValueError('Landings projection requires exact witnessed landed anchors')
    base_anchors=P.bounded(supplied.get('anchors',[]))
    if any(not isinstance(a,dict) or a.get('source')=='landings' for a in base_anchors):
        raise ValueError('Landings anchors require separate read-only projection')
    attempts={facet:supplied.get(facet+'_attempt_ids',[]) for facet in ('humor','taste')}
    for ids in attempts.values():
        if not isinstance(ids,list) or len(ids)>P.LIMIT or any(not P.identifier(i) for i in ids) or len(set(ids))!=len(ids):
            raise ValueError('explicit unique attempt IDs required')
    reference=supplied.get('reference_ids',[r['id'] for r in rows if r['day'] in candidates])
    if not isinstance(reference,list) or len(reference)>P.LIMIT or any(not P.identifier(i) for i in reference) or len(set(reference))!=len(reference):
        raise ValueError('explicit unique reference IDs required')
    # Keep the original attribution evidence private; recorded labels are not served-model proof.
    cfg=dict(bundle['historical_attribution']);ledger=cfg.pop('compute_ledger');cfg['window30_enabled']=True
    _,attribution=C.attribution(bundle['rows'],ledger,cfg,cutoff)
    private={'schema':'numerical-private-run-v1','character_coverage':char_coverage,'attribution':attribution,
             'mode_assignments':[{k:r.get(k) for k in ('id','sha','day','mode','surface','mode_source','mode_evidence_sha256','basis','primary')} for r in rows],
             'source_receipts':[{'turn_id':r.get('turn_id'),**{k:r[k] for k in
                ('served_by','model','served_model','fallback','provenance','witness_receipt','generation_receipt','generation_join','mode_receipt') if k in r}}
                for r in bundle['rows'] if r.get('role')=='assistant' and C.instant(r['timestamp'])<cutoff],
             'encoder_claim':bundle['encoder'],'encoder_frozen_at':supplied.get('encoder_frozen_at'),'views':{}}
    public={'schema':'numerical-counts-v1','character_admitted_replies':len(rows),'character_days':len({r['day'] for r in rows}),
            'adapter_unavailable':adapter_counts,'encoder_metadata_available':encoder is not None,
            'legacy_feedback_not_promoted':len(bundle.get('feedback',[])),
            'views':{},'strict_admission_invented':False,'source_claims_independently_verified':False}
    for name in ('primary_10s','window30'):
        if view not in {'both',name}:continue
        selected=[r for r in rows if name=='window30' or r['primary']];ids={r['id'] for r in selected}
        ev=[e for e in events if e['node_id'] in ids];fe=[f for f in features if f['node_id'] in ids]
        voice=None;vd={'voice':[],'drift':[],'revisions':[],'adoptions':[]};facets={};fd={};eligible=[];coverage={}
        if encoder is not None:
            eligible,coverage=V.prepare(ev,nodes,fe,encoder,cutoff,bundle['timezone'])
            allowed_ids={r['id'] for r in eligible};refs=[i for i in reference if i in allowed_ids]
            voice,vd=V.analyze(ev,nodes,fe,encoder,refs,cutoff,zone=bundle['timezone'])
            for facet,anchors in (('humor',base_anchors),('taste',landings['anchors'])):
                scoped_attempts=[i for i in attempts[facet] if i in ids]
                facets[facet],fd[facet]=F.analyze(ev,nodes,fe,encoder,items,scoped_attempts,anchors,cutoff,facet=facet,zone=bundle['timezone'])
        else:
            for facet in ('humor','taste'):facets[facet]=None;fd[facet]=[]
        private['views'][name]={'voice_drift':voice,'voice_drift_receipts':vd,'facets':facets,'facet_receipts':fd,
                                'unavailable_reference_ids':[i for i in reference if i not in {r['id'] for r in eligible}]}
        per_scope=[]
        for mode,surface in sorted({(r.get('mode','unknown'),r['surface']) for r in selected}):
            normalized={'opening_everyday':'everyday','intimate':'intimate'}.get(mode,'unknown')
            scoped=[r for r in selected if (r.get('mode','unknown'),r['surface'])==(mode,surface)]
            scores=[d for d in vd['voice'] if d['scope']==[normalized,surface]]
            drift=[d for d in vd['drift'] if d['scope']==[normalized,surface] and d['sustained_shift']]
            per_scope.append({'mode':normalized,'surface':surface,'replies':len(scoped),'days':len({r['day'] for r in scoped}),
                'voice_scored':len(scores),'voice_unscored':len(scoped)-len(scores),
                'voice_abstain':len(scoped)-sum(d['band_location']!='abstain' for d in scores),
                'flagged_drift_windows':date_windows([d['day'] for d in drift])})
        public['views'][name]={'selected_replies':len(selected),'admitted_original_acts':len(eligible),
            'lineage_exclusions':coverage.get('excluded',{}),'feature_exclusions':coverage.get('feature_exclusions',{}),
            'reference_ids_unavailable':len(private['views'][name]['unavailable_reference_ids']),
            'per_mode_surface':per_scope,'facets':{f:facet_counts(facets[f],fd[f],sum(i in ids for i in attempts[f])) for f in ('humor','taste')},
            'attempt_ids_outside_view':{f:sum(i not in ids for i in attempts[f]) for f in ('humor','taste')}}
    return private,public


def main(argv=None):
    p=Parser(description=__doc__)
    for key in ('input','scratch','output','summary','cutoff'):p.add_argument('--'+key,required=True)
    p.add_argument('--landings');p.add_argument('--view',choices=('both','primary_10s','window30'),default='both')
    args=p.parse_args(argv);root=C.scratch_root(args.scratch)
    if any((parent/'.git').exists() for parent in (root,*root.parents)):raise ValueError('scratch cannot be inside any repository')
    source=C.inside(root,args.input);land=C.inside(root,args.landings) if args.landings else None
    output=C.inside(root,args.output);summary=C.inside(root,args.summary);out=output.parent
    if output==summary or out!=summary.parent or out==root or out.exists():raise ValueError('outputs require a shared new private directory')
    if any(out==s or out in s.parents for s in (source,land) if s is not None):raise ValueError('input cannot be an output descendant')
    C.install_guard(root,out)
    bundle,input_hash=read_projection(source,64*1024*1024)
    landings,land_hash=read_projection(land,16*1024*1024) if land is not None else (None,None)
    private,public=evaluate(bundle,landings,args.cutoff,args.view)
    private['manifest']={'input_sha256':input_hash,'landings_sha256':land_hash,'cutoff':P.stamp(args.cutoff),'view':args.view,
        'code_sha256':{str(path.relative_to(REPO)):hashlib.sha256(path.read_bytes()).hexdigest() for path in
            (Path(__file__),HERE/'witnessed_facets.py',HERE/'voice_drift.py',HERE/'prototype.py',HERE.parent/'character-reference/prototype.py',
             REPO/'scripts/witness_attribution.py',REPO/'scripts/witness_receipts.py',REPO/'scripts/request_trace.py',REPO/'experiments/judges-witness/replay.py')},
        'python':list(sys.version_info[:3]),'numpy':V.np.__version__,
        'model_calls':0,'served_model':None,'fallback':None}
    payloads=[(output,json.dumps(private,sort_keys=True,allow_nan=False)),(summary,json.dumps(public,sort_keys=True,allow_nan=False))]
    out.mkdir(mode=0o700)
    for path,data in payloads:
        with path.open('x') as f:
            path.chmod(0o600)
            f.write(data+'\n')
    print(json.dumps({'written':True,'reports':2}))


def cli():
    try:main()
    except Exception as exc:
        allowed={'ValueError','TypeError','KeyError','OSError','PermissionError','FileNotFoundError','RuntimeError'}
        print(json.dumps({'written':False,'error':'private_run_failed','error_type':type(exc).__name__ if type(exc).__name__ in allowed else 'Exception'}),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(cli())
