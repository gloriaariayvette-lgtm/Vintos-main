#!/usr/bin/env python3
"""Positive-outcome familiarity facets; pure in-memory analysis, no private readers."""
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import re
from zoneinfo import ZoneInfo
from pathlib import Path
import importlib.util

spec=importlib.util.spec_from_file_location('voice_metrics',Path(__file__).with_name('voice_drift.py'))
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
P=V.P;C=V.C
KINDS={'message','joke','journal','image','song','video'}
TEXT_KINDS={'message','joke','journal'}
LAUGH=re.compile(r'\b(?:ha){2,}\b',re.I)


def outcome_anchors(anchors,rows,items,facet,cutoff,zone):
    """Normalize exact positive claims; all other observations stay unknown."""
    seen={};reaction_claims={};positive=defaultdict(list);counts=Counter();sources=Counter();tz=ZoneInfo(zone)
    for a in P.bounded(anchors):
        if (not isinstance(a,dict) or set(a)!={'evidence_id','node_id','content_sha256','actor','witnessed',
                'observed_at','source','value','link','source_record_sha256'}
                or not P.identifier(a['evidence_id']) or not P.identifier(a['node_id'])
                or not P.hashed(a['content_sha256']) or not P.hashed(a['source_record_sha256'])
                or not isinstance(a['source'],str) or not isinstance(a['actor'],str)
                or type(a['witnessed']) is not bool or not isinstance(a['link'],dict)):
            raise ValueError('invalid outcome anchor contract')
        norm=dict(a,observed_at=P.stamp(a['observed_at']))
        encoded=P.canonical(norm)
        if a['evidence_id'] in seen:
            if seen[a['evidence_id']]!=encoded:raise ValueError('conflicting outcome identity')
            counts['duplicate_observation']+=1;continue
        seen[a['evidence_id']]=encoded
        row=rows.get(a['node_id']);kind=items.get(a['node_id']);observed=norm['observed_at']
        if row is None or a['content_sha256']!=row['content_sha256']:
            counts['unlinked_original']+=1;continue
        if a['actor']!='owner' or not a['witnessed']:
            counts['not_owner_witness']+=1;continue
        if not row['at']<=observed<cutoff:counts['outside_evidence_time']+=1;continue
        if kind not in TEXT_KINDS or (facet=='humor' and kind not in {'message','joke'}):
            counts['unsupported_item_kind']+=1;continue
        link=a['link'];source=a['source'];qualifies=False
        if facet=='humor' and source=='adjacent_exchange':
            keys={'kind','exchange_id','target_id','target_sha256','reaction_id','reaction_sha256','target_index','reaction_index'}
            if (set(link)!=keys or link['kind']!='adjacent_exchange' or not P.identifier(link['exchange_id'])
                    or link['target_id']!=row['id'] or link['target_sha256']!=row['content_sha256']
                    or not P.identifier(link['reaction_id']) or link['reaction_id']==row['id']
                    or not isinstance(a['value'],str) or not 0<len(a['value'])<=10000
                    or hashlib.sha256(a['value'].encode()).hexdigest()!=link['reaction_sha256']
                    or type(link['target_index']) is not int or type(link['reaction_index']) is not int
                    or not 0<=link['target_index']<1000000 or link['reaction_index']!=link['target_index']+1):
                counts['adjacency_unbound']+=1;continue
            claim=(link['exchange_id'],link['target_id'],link['target_sha256'],link['target_index'],link['reaction_index'],link['reaction_sha256'])
            if link['reaction_id'] in reaction_claims and reaction_claims[link['reaction_id']]!=claim:
                raise ValueError('conflicting reaction adjacency')
            reaction_claims[link['reaction_id']]=claim
            qualifies=bool(LAUGH.search(a['value']))
        elif ((facet=='humor' and source=='humor_practice' and kind=='joke')
              or (facet=='taste' and source=='landings')):
            if (set(link)!={'kind','item_id','item_sha256','item_kind'} or link['kind']!='exact_item'
                    or link['item_id']!=row['id'] or link['item_sha256']!=row['content_sha256']
                    or link['item_kind']!=kind):
                counts['item_unbound']+=1;continue
            qualifies=(type(a['value']) in (int,float) and 4<=a['value']<=5) if source=='humor_practice' else a['value']=='landed'
        else:counts['unsupported_source']+=1;continue
        if not qualifies:counts['unknown_outcome']+=1;continue
        positive[row['id']].append({'observed_at':observed,'day':datetime.fromtimestamp(observed,tz).date().isoformat(),
            'evidence_id':a['evidence_id'],'source_record_sha256':a['source_record_sha256'],'source':source,
            'anchor_sha256':hashlib.sha256(encoded.encode()).hexdigest()})
        sources[source]+=1
    for values in positive.values():values.sort(key=lambda a:(a['observed_at'],a['evidence_id']))
    return positive,dict(sorted(counts.items())),dict(sorted(sources.items())),len(seen)


def analyze(events,nodes,features,encoder,items,attempt_ids,anchors,cutoff,*,facet='humor',zone='UTC'):
    """No negative labels. Similarity never promotes itself to an outcome anchor."""
    if facet not in {'humor','taste'}:raise ValueError('unknown facet')
    cutoff=P.stamp(cutoff)
    rows,coverage=V.prepare(events,nodes,features,encoder,cutoff,zone);by_id={r['id']:r for r in rows}
    item_map={}
    for item in P.bounded(items):
        if (not isinstance(item,dict) or set(item)!={'node_id','kind'} or not P.identifier(item['node_id'])
                or not isinstance(item['kind'],str) or item['kind'] not in KINDS):raise ValueError('invalid item contract')
        if item['node_id'] in item_map and item_map[item['node_id']]!=item['kind']:raise ValueError('conflicting item kind')
        item_map[item['node_id']]=item['kind']
    if (not isinstance(attempt_ids,list) or len(attempt_ids)>P.LIMIT or any(not P.identifier(x) for x in attempt_ids)
            or len(set(attempt_ids))!=len(attempt_ids)):raise ValueError('unique bounded attempt IDs required')
    positives,excluded,sources,unique=outcome_anchors(anchors,by_id,item_map,facet,cutoff,zone)
    details=[];status=Counter();scopes=defaultdict(lambda:{'attempts':0,'scored':0,'positive_references':set(),'reference_days':set()})
    for key in sorted(attempt_ids):
        row=by_id.get(key);kind=item_map.get(key)
        if row is None:status['attempt_not_admitted']+=1;continue
        if kind not in TEXT_KINDS or (facet=='humor' and kind not in {'message','joke'}):
            status['unsupported_attempt_kind']+=1;continue
        scope=(row['mode'],row['surface'],kind);scope_counts=scopes[scope];scope_counts['attempts']+=1
        reference=[];used=[]
        for ref in rows:
            if (ref['mode'],ref['surface'],item_map.get(ref['id']))!=scope or ref['day']>=row['day']:continue
            available=[a for a in positives.get(ref['id'],[]) if a['day']<row['day'] and a['observed_at']<row['at']]
            if not available:continue
            reference.append(ref);used.append(dict(node_id=ref['id'],content_sha256=ref['content_sha256'],**available[0]))
        days=sorted({r['day'] for r in reference})
        scope_counts['positive_references'].update(r['id'] for r in reference);scope_counts['reference_days'].update(days)
        # The target's later reception is descriptive only, never used to calculate its score.
        receipt=dict(attempt_id=key,scope=list(scope),day=row['day'],mode_source=row['mode_source'],
            mode_evidence_sha256=row['mode_evidence_sha256'],outcome='witnessed_positive' if key in positives else 'unknown',
            references=used,reference_days=days,reference_count=len(reference),reference_version=V.version(reference),
            similarity=None,empirical_score=None,band_location='abstain',status='insufficient_positive_days')
        if len(days)>=2:
            balanced=V.day_balanced(reference);state=C.reference_statistics(balanced) if balanced else None
            raw=V.distance(row,state) if state else None
            if raw is None:receipt['status']='degenerate_positive_reference'
            else:
                receipt.update(similarity={k.replace('_distance','_familiarity'):1-v for k,v in raw.items()},status='similarity_only')
                scope_counts['scored']+=1
                if len(days)>=4:
                    cal=V.calibrate(reference,4)
                    calibrated=V.score(row,cal,(.2,.8)) if cal else None
                    if calibrated:
                        receipt.update(empirical_score=calibrated['score'],band_location=calibrated['band_location'],status='empirical_rank')
        status[receipt['status']]+=1;details.append(receipt)
    public_scopes=[]
    for scope,c in sorted(scopes.items()):
        public_scopes.append(dict(mode=scope[0],surface=scope[1],item_kind=scope[2],attempts=c['attempts'],scored=c['scored'],
                                  available_reference_acts=len(c['positive_references']),available_reference_days=len(c['reference_days'])))
    similarities=[d['similarity']['joint_familiarity'] for d in details if d['similarity'] is not None]
    report={'schema':'witnessed-positive-facet-v1','facet':facet,'coverage':coverage,
        'outcomes':{'input_observations':len(anchors),'unique_observations':unique,'positive_original_acts':len(positives),
                    'positive_act_days':len({by_id[key]['day'] for key in positives}),
                    'positive_observation_days':len({a['day'] for values in positives.values() for a in values}),
                    'positive_sources':sources,'excluded_or_unknown':excluded},
        'attempts':{'requested':len(attempt_ids),'with_positive_outcome':sum(k in positives for k in attempt_ids),
                    'unknown_outcome':sum(k not in positives for k in attempt_ids),'status':dict(sorted(status.items()))},
        'reference_coverage':public_scopes,'mode_sources':dict(sorted(Counter(r['mode_source'] for r in rows).items())),
        'mean_positive_familiarity':sum(similarities)/len(similarities) if similarities else None,
        'empirically_ranked_attempts':sum(d['empirical_score'] is not None for d in details),
        'meaning':'similarity_to_witnessed_positives_not_humor_success_or_personal_taste_prediction',
        'negative_labels':0,'verdict':None,'effects':'none','model_calls':0,
        'verification':{'source_identity_and_adjacency_claims':False,'encoder_artifact_and_cache_derivation':False}}
    return report,details
