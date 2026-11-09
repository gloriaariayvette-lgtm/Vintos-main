#!/usr/bin/env python3
"""Offline reference familiarity and sustained drift from supplied cached features."""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import importlib.util
from pathlib import Path
import math
import numpy as np

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

P=load('numeric_evidence',HERE/'prototype.py')
C=load('character_metrics',HERE.parent/'character-reference/prototype.py')
MODE_SOURCES={'router_decision','intimate_state','conversation_transition','reviewed_somatic_interval',
              'adjacent_reply_rule','gloria_family_rule','unknown'}


def prepare(events,nodes,features,encoder,cutoff,zone):
    if (not isinstance(encoder,dict) or set(encoder)!={'id','artifact_sha256','dimension','frozen_at','frozen'}
            or not P.identifier(encoder['id']) or not P.hashed(encoder['artifact_sha256'])
            or type(encoder['dimension']) is not int or not 1<=encoder['dimension']<=2048
            or encoder['frozen'] is not True):raise ValueError('frozen encoder contract required')
    frozen=P.stamp(encoder['frozen_at']);rows,coverage=P.admit(events,nodes,cutoff,zone)
    cache={};excluded=Counter()
    for f in P.bounded(features):
        if (not isinstance(f,dict) or set(f)!={'node_id','content_sha256','text','vector','encoder_id',
                'artifact_sha256','mode_source','mode_evidence_sha256'}
                or not P.identifier(f['node_id']) or not P.hashed(f['content_sha256'])
                or not isinstance(f['text'],str) or not 0<len(f['text'])<=10000
                or not isinstance(f['mode_source'],str) or f['mode_source'] not in MODE_SOURCES or not P.hashed(f['mode_evidence_sha256'])):
            raise ValueError('invalid feature contract')
        P.vector(f['vector'],encoder['dimension'])
        if f['node_id'] in cache and cache[f['node_id']]!=f:raise ValueError('conflicting features')
        cache[f['node_id']]=f
    accepted=[]
    for r in rows:
        f=cache.get(r['node_id'])
        if f is None:excluded['missing_features']+=1;continue
        if (f['content_sha256']!=r['content_sha256'] or hashlib.sha256(f['text'].encode()).hexdigest()!=r['content_sha256']
                or f['encoder_id']!=encoder['id'] or f['artifact_sha256']!=encoder['artifact_sha256']):
            excluded['feature_binding_mismatch']+=1;continue
        if frozen>r['at'] or frozen>=P.stamp(cutoff):excluded['encoder_not_frozen_before_event']+=1;continue
        if f['mode_source']=='unknown':excluded['mode_provenance_unknown']+=1;continue
        accepted.append(dict(r,id=r['node_id'],vector=np.asarray(P.vector(f['vector'],encoder['dimension'])),
                             style=C.style(f['text']),mode_source=f['mode_source'],mode_evidence_sha256=f['mode_evidence_sha256'],
                             encoder_id=encoder['id'],artifact_sha256=encoder['artifact_sha256'],frozen_at=frozen))
    coverage['feature_exclusions']=dict(sorted(excluded.items()))
    coverage['featured_acts']=len(accepted)
    return sorted(accepted,key=lambda r:(r['at'],r['id'])),coverage


def version(rows):
    """Exact immutable scope/reference binding, including modes and cached features."""
    bindings=[{k:r[k] for k in ('id','at','day','source','content_sha256','surface','mode','mode_source','mode_evidence_sha256',
                                                    'encoder_id','artifact_sha256','frozen_at')}
              | {'vector':r['vector'].tolist(),'style':r['style'].tolist()} for r in sorted(rows,key=lambda r:r['id'])]
    return hashlib.sha256(P.canonical(bindings).encode()).hexdigest()


def distance(row,state):
    scores=C.score_statistics(row,state)
    if scores is None or scores['centroid'] is None:return None
    semantic=max(0.,min(1.,(1-scores['centroid'])/2))
    raw_style=max(0.,-scores['style']);sty=raw_style/(1+raw_style)
    # Ignore sub-picounit arithmetic noise before empirical tie ranking.
    semantic=round(semantic,12);sty=round(sty,12)
    return {'semantic_distance':semantic,'style_distance':sty,'joint_distance':(semantic+sty)/2}


def day_balanced(rows):
    # One average feature row per day keeps prolific days from dominating the reference.
    groups=defaultdict(list)
    for r in rows:groups[r['day']].append(r)
    out=[]
    for day,group in sorted(groups.items()):
        v=np.mean([r['vector'] for r in group],axis=0);norm=np.linalg.norm(v)
        if norm<=1e-12:return []
        out.append(dict(day=day,vector=v/norm,style=np.mean([r['style'] for r in group],axis=0)))
    return out


def calibrate(reference,min_days):
    days=sorted({r['day'] for r in reference})
    if len(days)<min_days:return None
    balanced=day_balanced(reference)
    if not balanced:return None
    state=C.reference_statistics(balanced);held=[]
    for day in days:
        other=[r for r in balanced if r['day']!=day]
        fold=C.reference_statistics(other)
        values=[distance(r,fold) for r in reference if r['day']==day]
        if any(v is None for v in values):return None
        held.append((day,values))
    return state,held


def score(row,calibration,band):
    state,held=calibration;raw=distance(row,state)
    if raw is None:return None
    # Equal day weights. A survival midrank is familiarity, not P(authentic).
    pct={key:sum(1-C.percentile(raw[key],[x[key] for x in values]) for _,values in held)/len(held)
         for key in raw}
    value=pct['joint_distance']
    location='abstain' if band[0]<=value<=band[1] else 'below_band' if value<band[0] else 'above_band'
    return dict(raw=raw,score=value,component_scores=pct,band_location=location)


def analyze(events,nodes,features,encoder,reference_ids,cutoff,*,adoptions=(),zone='UTC',
            min_days=4,abstain_band=(.2,.8),sustain_days=4,drift_margin=.05):
    """Returns aggregate-only report and private receipts. No writes, sends or encoder runs."""
    if type(min_days) is not int or not 4<=min_days<=32:raise ValueError('min_days must be 4..32')
    if type(sustain_days) is not int or not min_days<=sustain_days<=32:raise ValueError('sustain_days must cover calibration days')
    if (not isinstance(abstain_band,(tuple,list)) or len(abstain_band)!=2
            or any(type(x) not in (int,float) or not math.isfinite(x) for x in abstain_band)
            or not 0<=abstain_band[0]<abstain_band[1]<=1):raise ValueError('invalid abstain band')
    if type(drift_margin) not in (int,float) or not math.isfinite(drift_margin) or not 0<drift_margin<1:
        raise ValueError('invalid drift margin')
    if not isinstance(reference_ids,list) or len(reference_ids)>P.LIMIT or any(not P.identifier(i) for i in reference_ids):
        raise ValueError('explicit bounded reference IDs required')
    if len(set(reference_ids))!=len(reference_ids):raise ValueError('duplicate reference ID')
    rows,coverage=prepare(events,nodes,features,encoder,cutoff,zone);by_id={r['id']:r for r in rows}
    if any(i not in by_id for i in reference_ids):raise ValueError('reference ID not admitted')
    scoped=defaultdict(list)
    for r in rows:scoped[(r['mode'],r['surface'])].append(r)
    reviews=[]
    for a in P.bounded(list(adoptions)):
        if (not isinstance(a,dict) or set(a)!={'reference_version','members','reviewer','decision','observed_at','evidence_sha256'}
                or not P.hashed(a['reference_version']) or not P.hashed(a['evidence_sha256'])
                or a['reviewer']!='owner' or a['decision']!='adopt' or not isinstance(a['members'],list)
                or not 1<=len(a['members'])<=P.LIMIT):raise ValueError('explicit owner adoption receipt required')
        members=[]
        for m in a['members']:
            if not isinstance(m,dict) or set(m)!={'node_id','content_sha256'}:raise ValueError('invalid adoption member')
            if not P.identifier(m['node_id']) or not P.hashed(m['content_sha256']):raise ValueError('invalid adoption member')
            r=by_id.get(m['node_id'])
            if r is None or m['content_sha256']!=r['content_sha256']:raise ValueError('adoption member not admitted or bound')
            members.append(r)
        if len({r['id'] for r in members})!=len(members):raise ValueError('duplicate adoption member')
        observed=P.stamp(a['observed_at'])
        if not max(r['at'] for r in members)<=observed<P.stamp(cutoff):raise ValueError('adoption timestamp outside evidence bounds')
        if len({(r['mode'],r['surface']) for r in members})!=1:raise ValueError('adoption crosses mode or surface')
        normalized=dict(a,observed_at=observed,members=sorted(a['members'],key=lambda m:m['node_id']))
        key=hashlib.sha256(P.canonical(normalized).encode()).hexdigest()
        if not any(x['key']==key for x in reviews):reviews.append(dict(key=key,receipt=normalized,rows=members))
    private={'voice':[],'drift':[],'revisions':[],'adoptions':[]};status=Counter();used=set()
    calibration_cache={}
    def cached_calibration(reference):
        key=tuple(sorted(r['id'] for r in reference))
        if key not in calibration_cache:calibration_cache[key]=calibrate(reference,min_days)
        return calibration_cache[key]
    for scope,group in sorted(scoped.items()):
        reference=[r for r in group if r['id'] in reference_ids]
        if not reference:
            status['no_reference_scope']+=len(group);continue
        baseline_last=max(r['day'] for r in reference)
        current_version=version(reference);run=[];previous=None;shifted=set()
        for day in sorted({r['day'] for r in group}):
            batch=[r for r in group if r['day']==day]
            # Process only receipts already available before this entire local day.
            eligible=[a for a in reviews if a['key'] not in used and (a['rows'][0]['mode'],a['rows'][0]['surface'])==scope
                      and a['receipt']['observed_at']<min(r['at'] for r in batch)
                      and P.datetime.fromtimestamp(a['receipt']['observed_at'],P.ZoneInfo(zone)).date().isoformat()<day
                      and max(r['day'] for r in a['rows'])<day]
            for a in sorted(eligible,key=lambda a:(a['receipt']['observed_at'],a['key'])):
                receipt=a['receipt'];replacement=a['rows'];why=None
                if receipt['reference_version']!=current_version:why='stale_reference_version'
                elif not all(r['id'] in shifted for r in replacement):why='not_sustained_shift_evidence'
                elif len({r['day'] for r in replacement})<min_days:why='insufficient_adoption_days'
                elif any(r['mode_source'] in {'gloria_family_rule','adjacent_reply_rule'} for r in replacement+reference):why='independent_mode_required_for_adoption'
                elif cached_calibration(replacement) is None:why='degenerate_adoption_reference'
                used.add(a['key'])
                private['adoptions'].append(dict(receipt_sha256=a['key'],status=why or 'applied',day=day))
                if why:continue
                prior=current_version;reference=replacement;current_version=version(reference)
                baseline_last=max(r['day'] for r in reference);run=[];shifted=set();previous=None
                private['revisions'].append(dict(prior_version=prior,reference_version=current_version,effective_day=day,
                    adoption_receipt_sha256=a['key'],members=[r['id'] for r in reference],scope=list(scope)))
            # Strictly prior days only; target day never fits its own reference or calibration.
            past=[r for r in reference if r['day']<day]
            cal=cached_calibration(past)
            if cal is None:
                status['insufficient_or_degenerate_past_reference']+=len(batch);run=[];previous=None;continue
            for row in batch:
                result=score(row,cal,abstain_band)
                if result is None:status['degenerate_score']+=1;continue
                private['voice'].append(dict(turn_id=row['id'],day=day,scope=list(scope),mode_source=row['mode_source'],
                    reference_version=version(past),reference_days=sorted({r['day'] for r in past}),
                    calibration_days=len(cal[1]),**result))
                status['scored']+=1
            if day<=baseline_last:continue
            daily=[distance(r,cal[0]) for r in batch]
            if any(x is None for x in daily):run=[];previous=None;continue
            daily_distance=float(np.mean([x['joint_distance'] for x in daily]))
            held_means=[float(np.mean([x['joint_distance'] for x in values])) for _,values in cal[1]]
            threshold=min(1.,max(held_means)+drift_margin)
            is_shift=daily_distance>threshold
            consecutive=previous is not None and (date.fromisoformat(day)-date.fromisoformat(previous)).days==1
            if not is_shift:run=[]
            else:
                if not consecutive:run=[]
                run.append(batch)
            sustained=len(run)>=sustain_days
            if sustained:shifted.update(r['id'] for b in run for r in b)
            private['drift'].append(dict(day=day,scope=list(scope),reference_version=current_version,
                distance=daily_distance,threshold=threshold,consecutive_shift_days=len(run),
                sustained_shift=sustained,interpretation='descriptive_shift_not_error_or_identity'))
            previous=day
    private['adoptions'].extend(dict(receipt_sha256=a['key'],status='not_yet_applicable') for a in reviews if a['key'] not in used)
    vals=[x['score'] for x in private['voice']]
    public={'schema':'offline-voice-drift-v1','coverage':coverage,'status':dict(sorted(status.items())),
        'voice':{'scored_replies':len(vals),'mean_score':sum(vals)/len(vals) if vals else None,
                 'band_counts':dict(sorted(Counter(x['band_location'] for x in private['voice']).items())),
                 'abstain_band':list(abstain_band),'calibration':'past_only_leave_one_day_out_equal_day_empirical_midrank',
                 'meaning':'reference_familiarity_not_authenticity_probability'},
        'drift':{'evaluated_scope_days':len(private['drift']),
                 'sustained_scope_days':sum(x['sustained_shift'] for x in private['drift']),
                 'reference_revisions':len(private['revisions']),'sustain_days':sustain_days,'margin':drift_margin,
                 'adoption_status':dict(sorted(Counter(x['status'] for x in private['adoptions']).items()))},
        'mode_sources':dict(sorted(Counter(r['mode_source'] for r in rows).items())),
        'verification':{'source_and_adoption_claims':False,'encoder_artifact_and_cache_derivation':False},
        'effects':'none','encoder_calls':0,'verdict':None}
    return public,private
