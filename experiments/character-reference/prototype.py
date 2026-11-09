#!/usr/bin/env python3
"""Private offline character-reference prototype using explicitly supplied cached vectors.

No encoder loads, fitting, network, live reads, or identity verdicts. Historical
attribution is diagnostic admission to this experiment only, never strict eligibility.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'experiments/judges-witness')]
from witness_attribution import attribution
from witness_receipts import digest, final_response, instant
from replay import scratch_root, inside, install_guard, decode_snapshot

FAMILIES=('claude','grok','gemma','other','unknown')
EVALUATION_GROUPS=('benign_novelty','refusal','opposite_stance','humor','surface_shift')
ANNOTATORS=('owner','reviewer')
MODES=('opening_everyday','intimate','unknown')
SURFACES=('avatar','reelroom','chat','phone','voice','vintos-eve','unknown')
CONTROL_SURFACES=SURFACES[:-1]+('slack','moltbook','journal')
CONTROL_REVIEWERS=ANNOTATORS+('store_authorship',)
MODE_SOURCES=('router_decision','intimate_state','conversation_transition')
STYLE=('log_chars','log_words','mean_word_chars','question_per_word','exclaim_per_word',
       'comma_per_word','uppercase_fraction','first_person_per_word','newline_per_word')


ENCODER_ARTIFACT_LIMIT=4*1024*1024*1024


def observe_encoder_artifact(path):
    """Hash one explicitly supplied regular scratch artifact, without loading it."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=ENCODER_ARTIFACT_LIMIT:
            raise ValueError('invalid encoder artifact size or type')
        sha=hashlib.sha256();size=0
        while size<=ENCODER_ARTIFACT_LIMIT:
            chunk=stream.read(min(1024*1024,ENCODER_ARTIFACT_LIMIT+1-size))
            if not chunk:break
            size+=len(chunk);sha.update(chunk)
        after=os.fstat(stream.fileno())
        keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        if size!=before.st_size or any(getattr(before,k)!=getattr(after,k) for k in keys):
            raise ValueError('encoder artifact changed during observation')
    return {'sha256':sha.hexdigest(),'bytes':size}


def encoder_pin(encoder,observation=None):
    expected=encoder.get('artifact_sha256')
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
        raise ValueError('invalid declared encoder artifact hash')
    if observation is not None and expected is not None and expected!=observation['sha256']:
        raise ValueError('encoder artifact hash mismatch')
    status=('artifact_hash_verified' if expected else 'artifact_hash_observed') if observation is not None else ('artifact_hash_declared' if expected else 'unknown')
    return {'artifact_status':status,'declared_contract':dict(encoder),
            'artifact_sha256':observation['sha256'] if observation else expected,
            'artifact_bytes':observation['bytes'] if observation else None,
            'revision_verified':False,'cache_derivation_verified':False}


def public_encoder_pin(pin):
    return {key:pin[key] for key in ('artifact_status','revision_verified','cache_derivation_verified')}


def surface_label(value):
    return value if value in SURFACES else 'unknown'


SOMATIC_FIELDS=('mode','source_field','source_record_sha256','start','end','observed_at',
                'surface','session_id','join')
SOMATIC_SOURCES=('somatic-narrated.json:narration','somatic_thread:thread')
MODE_LABEL_SOURCES=('prospective_receipt',)+MODE_SOURCES+('somatic_narration','gloria_family_rule','conflicting','unknown')
SOMATIC_WINDOW_LIMIT=7200.0


def somatic_review_binding(mark):
    return digest(json.dumps({k:mark.get(k) for k in SOMATIC_FIELDS},sort_keys=True,allow_nan=False,separators=(',',':')))


def bind_modes(rows,observations,cutoff,somatic_marks=(),family_fallback=False,raw_rows=()):
    """Bind supplied evidence; historical intervals are retrospective, never causal signals."""
    from request_trace import mode_receipt_fields
    if type(family_fallback) is not bool:raise ValueError('explicit historical fallback boolean required')
    by_id={r['id']:r for r in rows};linked=defaultdict(list);prospective=defaultdict(list);counts=Counter()
    for raw in raw_rows:
        if raw.get('role')!='assistant' or 'mode_receipt' not in raw or instant(raw['timestamp'])>=cutoff:continue
        row=by_id.get(raw.get('turn_id'))
        if row is None or digest(final_response(raw))!=row['sha']:continue
        receipt=raw['mode_receipt'];join=raw.get('generation_join')
        valid=mode_receipt_fields(receipt,row['id'],row['surface'],row['text'])
        if valid and isinstance(join,dict):
            valid=(join.get('request_trace_id')==receipt['request_id']
                   and join.get('completion_id')==receipt['selected_completion_id']
                   and join.get('raw_response_sha256')==receipt['raw_response_sha256']
                   and join.get('stored_response_sha256')==row['sha']
                   and join.get('schema')=='router-completion-join-v1'
                   and all(v is None or v<cutoff for v in
                       (receipt['started_at'],receipt['decision_at'],receipt['reroute_decision_at'])))
        else:valid=False
        if valid:
            prospective[row['id']].append((receipt['mode'],digest(json.dumps(receipt,sort_keys=True))))
            counts['prospective_linked']+=1
        else:
            counts['prospective_invalid']+=1
            prospective[row['id']].append(('unknown',None))
    for item in observations:
        if (not isinstance(item,dict) or item.get('mode') not in MODES or item.get('source') not in MODE_SOURCES
                or not isinstance(item.get('evidence_sha256'),str)
                or not re.fullmatch('[0-9a-f]{64}',item['evidence_sha256'])):
            raise ValueError('invalid independent mode observation')
        row=by_id.get(item.get('reply_id'));at=instant(item['timestamp'])
        if (row is None or item.get('reply_sha256')!=row['sha'] or item.get('link')!='exact_reply'
                or at>=cutoff or at>row['at']):
            counts['unlinked_or_outside']+=1;continue
        linked[row['id']].append(item);counts['linked_observations']+=1
    somatic=defaultdict(list)
    for mark in somatic_marks:
        if not isinstance(mark,dict):raise ValueError('invalid somatic mark')
        review=mark.get('review',{})
        if (mark.get('mode') not in MODES[:2] or mark.get('source_field') not in SOMATIC_SOURCES
                or not isinstance(mark.get('source_record_sha256'),str)
                or not re.fullmatch('[0-9a-f]{64}',mark['source_record_sha256'])
                or not isinstance(review,dict) or review.get('reviewed') is not True
                or review.get('reviewer') not in ANNOTATORS
                or review.get('binding_sha256')!=somatic_review_binding(mark)):
            raise ValueError('reviewed somatic evidence binding required')
        if mark.get('start') is None or mark.get('end') is None:
            counts['somatic_unbounded_marks']+=1;continue
        start,end,observed=(instant(mark[k]) for k in ('start','end','observed_at'))
        if not start<=end<=observed<cutoff or end-start>SOMATIC_WINDOW_LIMIT:
            counts['somatic_outside_or_overlong_marks']+=1;continue
        if (mark.get('surface') not in SURFACES[:-1] or mark.get('join') not in ('session_window','surface_window')
                or mark['join']=='session_window' and (not isinstance(mark.get('session_id'),str) or not 1<=len(mark['session_id'])<=160)
                or mark['join']=='surface_window' and mark.get('session_id') is not None):
            raise ValueError('invalid somatic join scope')
        matched=0
        for row in rows:
            if (start<=row['at']<=end and row['surface']==mark['surface']
                    and (mark['join']=='surface_window' or row.get('session_id')==mark['session_id'])):
                somatic[row['id']].append(mark);matched+=1
        counts['somatic_linked_marks' if matched else 'somatic_unmatched_marks']+=1
    for row in rows:
        rid=row['id'];rule={'claude':'opening_everyday','grok':'intimate'}.get(row['family'])
        sm={m['mode'] for m in somatic[rid]}
        if sm:
            counts['somatic_covered_replies']+=1
            if len(sm)>1:counts['somatic_conflicting_replies']+=1
            elif rule:
                counts['somatic_rule_comparable_replies']+=1
                counts['somatic_rule_disagreements']+=int(next(iter(sm))!=rule)
        if prospective[rid]:
            modes={m for m,_ in prospective[rid]};source='prospective_receipt'
            evidence=[e for _,e in prospective[rid] if e]
        elif linked[rid]:
            modes={m['mode'] for m in linked[rid]}
            source=next(src for src in MODE_SOURCES if any(m['source']==src for m in linked[rid]))
            evidence=[m['evidence_sha256'] for m in linked[rid]]
        elif sm:
            modes=sm;source='somatic_narration';evidence=[m['source_record_sha256'] for m in somatic[rid]]
        elif family_fallback and rule:
            modes={rule};source='gloria_family_rule';evidence=[]
        else:modes={'unknown'};source='unknown';evidence=[]
        row['mode']=next(iter(modes)) if len(modes)==1 else 'unknown'
        if len(modes)>1:counts['conflicting_replies']+=1;source='conflicting'
        row['mode_source']=source;row['mode_evidence_sha256']=sorted(set(evidence))
        counts[row['mode']]+=1;counts['source_'+source]+=1
    counts['family_fallback_enabled']=int(family_fallback)
    counts['somatic_window_max_seconds']=int(SOMATIC_WINDOW_LIMIT)
    counts['somatic_window_padding_seconds']=0
    return dict(counts)


def family(value):
    if not isinstance(value,str) or not value:return 'unknown'
    matched=[f for f in FAMILIES[:3] if re.search(r'(?:^|[/_.:-])'+f+r'(?:$|[-_.:/0-9])',value.lower())]
    return matched[0] if len(matched)==1 else 'other'


def style(text):
    words=re.findall(r"\b\w+\b",text.lower());n=max(1,len(words));letters=[c for c in text if c.isalpha()]
    return np.asarray([math.log1p(len(text)),math.log1p(len(words)),sum(map(len,words))/n,
        text.count('?')/n,text.count('!')/n,text.count(',')/n,
        sum(c.isupper() for c in letters)/max(1,len(letters)),
        sum(w in ('i','me','my','mine','myself') for w in words)/n,text.count('\n')/n],dtype=float)


def unit(value,dimension=None):
    if (not isinstance(value,list) or not 1<=len(value)<=8192 or
            any(type(v) not in (float,int) or not math.isfinite(v) for v in value)):
        raise ValueError('invalid cached vector')
    a=np.asarray(value,dtype=float)
    if dimension is not None and len(a)!=dimension:raise ValueError('mixed encoder dimensions')
    norm=np.linalg.norm(a)
    if not math.isfinite(norm) or abs(norm-1)>1e-4:raise ValueError('cached vectors must be unit normalized')
    return a/norm


def percentile(value,calibration):
    if not calibration:return None
    return float((sum(v<value for v in calibration)+.5*sum(v==value for v in calibration))/len(calibration))


def summarize(values,seed=17):
    """Day-equal means and percentile day-bootstrap intervals, descriptive only."""
    groups=defaultdict(list)
    for day,value in values:
        if value is not None:groups[day].append(float(value))
    means=np.asarray([np.mean(groups[d]) for d in sorted(groups)])
    result={'days':len(means),'observations':sum(map(len,groups.values())),
            'mean':float(means.mean()) if len(means) else None,'interval95':None}
    if len(means)>=2:
        rng=np.random.default_rng(seed)
        draws=means[rng.integers(0,len(means),size=(1000,len(means)))].mean(axis=1)
        result['interval95']=[float(x) for x in np.quantile(draws,[.025,.975])]
    return result


def context_pairs(left,right):
    """Deterministic one-to-one matching on supplied context, never outcome scores."""
    available={r['id']:r for r in right};pairs=[]
    for a in sorted(left,key=lambda r:r['id']):
        choices=[]
        for b in available.values():
            if (a['day']!=b['day'] or a.get('mode','unknown')!=b.get('mode','unknown')
                    or a.get('surface')!=b.get('surface') or not a['language'] or a['language']!=b['language']
                    or not .5<=len(a['text'])/max(1,len(b['text']))<=2):continue
            similarity=float(a['context_vector']@b['context_vector'])
            if similarity>=.7:choices.append((-similarity,b['id']))
        if choices:
            negative,bid=min(choices);pairs.append((a,available.pop(bid),-negative))
    return pairs


def context_family_comparisons(scored):
    by_family=defaultdict(list);out=[]
    for row,percentiles in scored:
        if row.get('family_comparison_eligible',True):by_family[row['family']].append(row)
    outcomes={r['id']:p for r,p in scored}
    for i,left in enumerate(FAMILIES[:3]):
        for right in FAMILIES[i+1:3]:
            a,b=by_family[left],by_family[right]
            pairs=context_pairs(a,b)
            metrics={k:summarize([(x['day'],outcomes[x['id']][k]-outcomes[y['id']][k])
                for x,y,_ in pairs if outcomes[x['id']][k] is not None and outcomes[y['id']][k] is not None])
                for k in ('semantic','style','centroid','recent_centroid')}
            out.append({'families':[left,right],'left_scored':len(a),'right_scored':len(b),
                'matched_pairs':len(pairs),'identifiability':'matched_comparison_available' if pairs else 'not_identifiable',
                'left_unmatched':len(a)-len(pairs),'right_unmatched':len(b)-len(pairs),
                'context_cosine':summarize([(x['day'],c) for x,y,c in pairs]),
                'percentile_differences':metrics})
    return {'matching':'same_mode_surface_day_language_length_ratio_0.5_to_2_context_cosine_at_least_0.7',
        'assignment':'left_reply_id_order_best_available_context_then_right_id',
        'meaning':'descriptive_matched_association_not_causal_model_effect',
        'excluded_family_derived_mode_or_reference':sum(not r.get('family_comparison_eligible',True) for r,_ in scored),
        'pairs':out}


def reference_statistics(reference):
    groups=defaultdict(list)
    for r in reference:groups[r['day']].append(r['vector'])
    centers=[]
    for values in groups.values():
        c=np.mean(values,axis=0);norm=np.linalg.norm(c)
        if norm>1e-12:centers.append(c/norm)
    if not centers:return None
    styles=np.asarray([r['style'] for r in reference]);mu=styles.mean(axis=0)
    scale=np.maximum(styles.std(axis=0),.05)
    all_center=np.mean([r['vector'] for r in reference],axis=0)
    norm=np.linalg.norm(all_center)
    recent_days=sorted(groups)[-2:]
    recent=np.mean([r['vector'] for r in reference if r['day'] in recent_days],axis=0)
    recent_norm=np.linalg.norm(recent)
    return centers,mu,scale,all_center,norm,recent,recent_norm


def score_statistics(row,state):
    if state is None:return None
    centers,mu,scale,all_center,norm,recent,recent_norm=state
    return {'semantic':max(float(row['vector']@c) for c in centers),
            'style':-float(np.sqrt(np.mean(((row['style']-mu)/scale)**2))),
            'centroid':float(row['vector']@all_center/norm) if norm>1e-12 else None,
            'recent_centroid':float(row['vector']@recent/recent_norm) if recent_norm>1e-12 else None}


def evaluation_groups(rows,scored):
    """Describe supplied evaluation annotations without using them to fit or admit."""
    outcomes={r['id']:p for r,p in scored};groups={}
    for source in ANNOTATORS:
        groups[source]={}
        for category in EVALUATION_GROUPS:
            members=[r for r in rows if (source,category) in r.get('evaluation_annotations',set())]
            available=[r for r in members if r['id'] in outcomes]
            groups[source][category]={'annotated_replies':len(members),'scored_replies':len(available),
                'unscored_replies':len(members)-len(available),
                'percentiles':{k:summarize([(r['day'],outcomes[r['id']][k]) for r in available])
                    for k in ('semantic','style','centroid','recent_centroid')}}
    return {'meaning':'supplied_descriptive_groups_not_identity_or_acceptance_labels',
        'overlap':'a_reply_may_belong_to_multiple_groups_and_annotators',
        'groups':groups}


def scores(row,reference):
    return score_statistics(row,reference_statistics(reference))


def control_review_binding(item):
    """Bind a supplied review to text, source classification and matching metadata."""
    fields=('candidate_id','content','context','timestamp','kind','author','mode','surface','language')
    return digest(json.dumps({k:item.get(k) for k in fields},sort_keys=True,allow_nan=False))


def control_reviewed(item,cutoff):
    review=item.get('review',{})
    try:at=instant(item.get('timestamp'))
    except (ValueError,TypeError):return False
    return (isinstance(review,dict) and review.get('reviewed') is True
        and review.get('reviewer') in CONTROL_REVIEWERS and review.get('link')=='exact_control'
        and review.get('binding_sha256')==control_review_binding(item)
        and isinstance(review.get('evidence_sha256'),str)
        and re.fullmatch(r'[0-9a-f]{64}',review['evidence_sha256']) is not None
        and isinstance(item.get('candidate_id'),str) and 0<len(item['candidate_id'])<=256
        and item.get('author')==('non_subject' if item.get('kind')=='foreign' else 'subject')
        and item.get('mode') in MODES[:2] and item.get('surface') in CONTROL_SURFACES
        and at<cutoff)


def control_cache(item,encoder,dimension):
    text=item.get('content');context=item.get('context')
    if (not isinstance(text,str) or not 0<len(text)<=65536 or not isinstance(context,str)
            or not 0<len(context)<=65536):raise ValueError('invalid control text or context')
    v=unit(item['vector'],dimension);c=unit(item['context_vector'],len(v))
    if (item['encoder_id']!=encoder['id'] or item['input_sha256']!=digest(text[:encoder['prefix_chars']])
            or item['context_sha256']!=digest(context)):raise ValueError('control encoder/input mismatch')
    return v,c


def control_match(item,row,context):
    return (row['mode']!='unknown' and item.get('mode')==row['mode']
        and row['surface']!='unknown'
        and (item['surface']==row['surface'] if item['kind']=='foreign' else item['surface']!=row['surface'])
        and bool(row['language']) and item.get('language')==row['language']
        and .5<=len(item['content'])/max(1,len(row['text']))<=2
        and float(context@row['context_vector'])>=.7)


def select_control_pool(pool,rows,encoder,dimension,own_hashes,cutoff):
    """Greedy context-only matching; every source text is used at most once."""
    counts=Counter();versions={};texts={};valid=[]
    for item in pool:
        if not isinstance(item,dict):raise ValueError('invalid control candidate')
        key=item.get('candidate_id');raw=json.dumps(item,sort_keys=True,allow_nan=False)
        if isinstance(key,str) and key in versions:
            if versions[key]!=raw:raise ValueError('conflicting control candidate identity')
            counts['duplicate_candidate']+=1;continue
        if isinstance(key,str):versions[key]=raw
        if item.get('kind') not in ('foreign','other_surface') or not control_reviewed(item,cutoff):
            counts['unreviewed_or_invalid_provenance']+=1;continue
        _,context=control_cache(item,encoder,dimension)
        sha=digest(item['content'])
        if sha in own_hashes:counts['reuses_input_reply']+=1;continue
        if sha in texts:
            if texts[sha]!=control_review_binding(item):raise ValueError('conflicting control text provenance')
            counts['duplicate_text']+=1;continue
        texts[sha]=control_review_binding(item);valid.append((item,context,sha))
    selected=[];used=set()
    for row in sorted(rows,key=lambda r:(not r['primary'],r['id'])):
        for kind in ('foreign','other_surface'):
            eligible=[(float(c@row['context_vector']),item['candidate_id'],item,sha)
                for item,c,sha in valid if sha not in used and item['kind']==kind and control_match(item,row,c)]
            if not eligible:continue
            _,_,item,sha=min(eligible,key=lambda x:(-x[0],x[1]))
            selected.append(dict(item,matched_reply_id=row['id']));used.add(sha)
    return selected,{'input_candidates':len(pool),'reviewed_candidates':len(valid),'excluded':dict(counts),
        'unused_reviewed_candidates':len(valid)-len(used),'matching':'primary_first_context_greedy_without_replacement'}


def prepare(bundle,cutoff):
    if bundle.get('input_kind') not in ('synthetic','retained_snapshot'):raise ValueError('explicit input kind required')
    encoder=bundle['encoder']
    fields={'family','revision','pooling','normalization','prefix_chars','frozen','id'}
    if (not isinstance(encoder,dict) or not fields<=set(encoder) or set(encoder)-fields-{'artifact_sha256'} or encoder['family']!='nomic'
            or encoder['frozen'] is not True or encoder['normalization']!='l2'
            or type(encoder['prefix_chars']) is not int or not 1<=encoder['prefix_chars']<=65536
            or any(not isinstance(encoder[k],str) or not 1<=len(encoder[k])<=256 for k in ('id','revision','pooling'))):
        raise ValueError('explicit frozen encoder contract required')
    encoder_pin(encoder)
    zone=ZoneInfo(bundle['timezone']);cutoff=instant(cutoff)
    rows=bundle['rows']
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded explicit history required')
    cfg=dict(bundle['historical_attribution']);ledger=cfg.pop('compute_ledger')
    cfg['window30_enabled']=True
    if cfg.get('window_seconds',10)!=10:raise ValueError('primary attribution must use ten seconds')
    attribution_report,details=attribution(rows,ledger,cfg,cutoff)
    for key,limit in (('embeddings',10000),('feedback',10000),('controls',4096),('control_pool',4096),('evaluation_annotations',10000),('mode_observations',10000),('somatic_marks',4096)):
        if not isinstance(bundle.get(key,[]),list) or len(bundle.get(key,[]))>limit:raise ValueError('unbounded prototype input')
    caches={};dimension=None
    for cache in bundle['embeddings']:
        if cache['encoder_id']!=encoder['id']:raise ValueError('encoder contract mismatch')
        v=unit(cache['vector'],dimension);dimension=len(v)
        c=unit(cache['context_vector'],dimension)
        key=cache['reply_sha256']
        raw=json.dumps(cache,sort_keys=True,allow_nan=False)
        if key in caches and caches[key][0]!=raw:raise ValueError('conflicting cached vectors')
        caches[key]=(raw,cache,v,c)
    users={};user_surfaces=defaultdict(set);engagement=Counter();excluded=Counter();prepared=[];versions={}
    all_versions={};sessions=defaultdict(set)
    for row in rows:
        if row.get('role')=='assistant' and row.get('turn_id'):
            key=row['turn_id'];version=digest(final_response(row))
            session=row.get('session_id')
            if session is not None:
                if not isinstance(session,str) or not 1<=len(session)<=160:raise ValueError('invalid session identity')
                sessions[key].add(session)
                if len(sessions[key])>1:raise ValueError('conflicting session identity')
            if key in all_versions and all_versions[key]!=version:raise ValueError('conflicting reply content')
            all_versions[key]=version
    assistants=iter(details)
    for row in rows:
        d=next(assistants) if row.get('role')=='assistant' else None
        at=instant(row['timestamp'])
        if at>=cutoff:continue
        day=datetime.fromtimestamp(at,zone).date().isoformat()
        if row.get('role')=='user':
            key=row.get('turn_id')
            if not isinstance(key,str) or not key:excluded['user_id_missing']+=1;continue
            version=(day,digest(row.get('content','')))
            if key in users and users[key]!=version:raise ValueError('conflicting user event')
            user_surfaces[key].add(surface_label(row.get('surface')))
            if key not in users:engagement[day]+=1;users[key]=version
            continue
        if d is None:continue
        text=final_response(row);tid=d['turn_id']
        if not isinstance(text,str) or not 0<len(text)<=65536 or not tid:
            excluded['reply_identity_missing']+=1;continue
        sha=digest(text)
        if d['response_sha256']!=sha:raise ValueError('attribution response mismatch')
        context=row.get('context')
        cached=caches.get(sha)
        if cached is None or not isinstance(context,str):excluded['cached_embedding_missing']+=1;continue
        _,cache,v,c=cached
        if cache['input_sha256']!=digest(text[:encoder['prefix_chars']]) or cache['context_sha256']!=digest(context):
            raise ValueError('cached input content mismatch')
        ledger_match=d['join_state']=='matched' and d['ledger_model'] is not None
        observed,label=d.get('observed_model'),d.get('recorded_label')
        label_agrees=bool(observed and label and (observed==label or
            family(observed) in FAMILIES[:3] and family(observed)==family(label)))
        primary=(ledger_match or label_agrees) and not d['label_conflict']
        extra=d.get('window30',{})
        extended=primary or extra.get('tier')=='ledger_attributed_window30'
        if not extended:excluded['attribution_not_admitted']+=1;continue
        version=(sha,day,(d['ledger_model'] if ledger_match else observed) if primary else extra['ledger_model'])
        if tid in versions:
            if versions[tid]!=version:raise ValueError('conflicting reply identity')
            excluded['duplicate_reply_copy']+=1;continue
        versions[tid]=version
        prepared.append({'id':tid,'sha':sha,'day':day,'at':at,'text':text,'vector':v,'context_vector':c,
                         'style':style(text),'family':family(version[2]),'primary':primary,
                         'basis':'ledger_10s_or_exact_id' if ledger_match else 'label_observed_agreement' if primary else 'window30',
                         'language':row.get('language'),'surface':surface_label(row.get('surface')),'session_id':next(iter(sessions[tid]),None)})
    # A copied/repeated text cannot appear on both sides of a held-out split.
    seen=set();unique=[]
    for row in sorted(prepared,key=lambda r:(r['at'],r['id'])):
        if row['sha'] in seen:excluded['repeated_reply_text']+=1;continue
        seen.add(row['sha']);unique.append(row)
    if len(unique)>4096:raise ValueError('prototype reply bound')
    counts=sorted(engagement.values());median=float(np.median(counts)) if counts else 0
    threshold=sorted(counts,reverse=True)[max(0,math.ceil(len(counts)/4)-1)] if counts else 0
    candidates=sorted(d for d,n in engagement.items() if n>=threshold and n>median)
    positive=defaultdict(set);feedback_counts=Counter();by_id={r['id']:r for r in unique}
    mode_counts=bind_modes(unique,bundle.get('mode_observations',[]),cutoff,
        bundle.get('somatic_marks',[]),bundle.get('historical_family_fallback',False),rows)
    for event in bundle.get('feedback',[]):
        row=by_id.get(event.get('reply_id'))
        if (row is None or event.get('reply_sha256')!=row['sha'] or event.get('link')!='exact_reply'
                or event.get('witnessed') is not True or not row['at']<=instant(event['timestamp'])<cutoff):
            feedback_counts['unlinked_or_outside']+=1;continue
        laugh=event.get('kind')=='laugh' and isinstance(event.get('value'),str) and re.search(r'\b(?:ha){2,}\b',event['value'],re.I)
        rating=event.get('kind')=='rating' and type(event.get('value')) in (int,float) and 4<=event['value']<=5
        if laugh or rating:positive[row['id']].add(datetime.fromtimestamp(instant(event['timestamp']),zone).date().isoformat())
        else:feedback_counts['not_positive_evidence']+=1
    annotation_counts=Counter();annotation_links=set()
    for event in bundle.get('evaluation_annotations',[]):
        if (not isinstance(event,dict) or event.get('category') not in EVALUATION_GROUPS
                or event.get('annotator') not in ANNOTATORS):raise ValueError('invalid evaluation annotation')
        row=by_id.get(event.get('reply_id'))
        if row is None or event.get('reply_sha256')!=row['sha'] or event.get('link')!='exact_reply':
            annotation_counts['unlinked_or_not_admitted']+=1;continue
        key=(row['id'],event['annotator'],event['category'])
        if key in annotation_links:annotation_counts['duplicate']+=1;continue
        annotation_links.add(key);annotation_counts['linked']+=1
        row.setdefault('evaluation_annotations',set()).add((event['annotator'],event['category']))
    supplied=bundle.get('controls',[]);pool=bundle.get('control_pool',[])
    if supplied and pool:raise ValueError('supply paired controls or a control pool, not both')
    own_hashes={digest(final_response(r)) for r in rows if r.get('role')=='assistant'}
    selection={'input_candidates':len(supplied),'matching':'explicit_pairs'}
    if pool:supplied,selection=select_control_pool(pool,unique,encoder,dimension,own_hashes,cutoff)
    controls=[];control_versions={};candidate_versions={};used_control_text=set();used_pairs=set()
    for item in supplied:
        row=by_id.get(item.get('matched_reply_id'))
        if row is None or item.get('kind') not in ('foreign','other_surface'):continue
        candidate_id=item.get('candidate_id')
        candidate_version=json.dumps({k:v for k,v in item.items() if k!='matched_reply_id'},sort_keys=True,allow_nan=False)
        if isinstance(candidate_id,str):
            if candidate_id in candidate_versions and candidate_versions[candidate_id]!=candidate_version:
                raise ValueError('conflicting control candidate identity')
            candidate_versions[candidate_id]=candidate_version
        text=item['content']
        if not isinstance(text,str) or not 0<len(text)<=65536:raise ValueError('invalid control text')
        key=(item['matched_reply_id'],item['kind'],digest(text));version=json.dumps(item,sort_keys=True,allow_nan=False)
        if key in control_versions:
            if control_versions[key]!=version:raise ValueError('conflicting control copies')
            continue
        control_versions[key]=version
        v,c=control_cache(item,encoder,dimension)
        if digest(text) in own_hashes:excluded['control_reuses_reply_text']+=1;continue
        if item.get('mode','unknown') not in MODES:raise ValueError('invalid control mode')
        if row['mode']=='unknown' or item.get('mode','unknown')!=row['mode']:
            excluded['control_mode_unknown_or_mismatched']+=1;continue
        if (not row['language'] or item.get('language')!=row['language']
                or not .5<=max(1,len(text))/max(1,len(row['text']))<=2
                or float(c@row['context_vector'])<.7):excluded['control_not_matched']+=1;continue
        if not control_reviewed(item,cutoff):excluded['control_provenance_unreviewed']+=1;continue
        if not control_match(item,row,c):excluded['control_surface_not_matched']+=1;continue
        pair=(row['id'],item['kind'])
        if digest(text) in used_control_text or pair in used_pairs:
            excluded['control_reused_text_or_pair']+=1;continue
        used_control_text.add(digest(text));used_pairs.add(pair)
        controls.append({'id':item['matched_reply_id'],'kind':item['kind'],'vector':v,'style':style(text),'mode':item['mode'],
            'candidate_id':item['candidate_id'],'sha':digest(text),'review_binding':control_review_binding(item),
            'context_cosine':float(c@row['context_vector']),'source_surface':item['surface'],
            'reviewer_class':item['review']['reviewer']})
    selection['by_mode_surface']=[{'mode':mode,'surface':surface,'kind':kind,
        'admitted_replies':sum(r['mode']==mode and r['surface']==surface for r in unique),
        'matched_replies':sum(c['kind']==kind and by_id[c['id']]['mode']==mode and by_id[c['id']]['surface']==surface for c in controls)}
        for mode in MODES[:2] for surface in SURFACES[:-1] for kind in ('foreign','other_surface')]
    for cell in selection['by_mode_surface']:cell['unmatched_replies']=cell['admitted_replies']-cell['matched_replies']
    selection['selected_source_counts']=[{'surface':surface,'reviewer_class':reviewer,'kind':kind,
        'pairs':sum(c['source_surface']==surface and c['reviewer_class']==reviewer and c['kind']==kind for c in controls)}
        for surface in CONTROL_SURFACES for reviewer in CONTROL_REVIEWERS for kind in ('foreign','other_surface')
        if any(c['source_surface']==surface and c['reviewer_class']==reviewer and c['kind']==kind for c in controls)]
    selection['source_authorship_independently_verified']=False
    return unique,controls,candidates,positive,{'excluded':dict(excluded),'attribution':attribution_report,
        'feedback':dict(feedback_counts),'positive_reply_links':len(positive),
        'admission_bases':dict(Counter(r['basis'] for r in unique)),
        'admitted_primary_replies':sum(r['primary'] for r in unique),'admitted_window30_replies':len(unique),
        'matched_controls':len(controls),'control_selection':selection,'mode_observations':mode_counts,
        'engagement_surfaces':{surface:sum((next(iter(labels)) if len(labels)==1 else 'unknown')==surface for labels in user_surfaces.values()) for surface in SURFACES},
        'evaluation_annotations':dict(annotation_counts),
        'candidate_days':[{'date':d,'user_messages':engagement[d],
            'attributed_replies_10s':sum(r['day']==d and r['primary'] for r in unique),
            'attributed_replies_window30':sum(r['day']==d for r in unique)} for d in candidates],
        'selection':{'observed_user_days':len(counts),'median_user_messages':median,'top_quarter_threshold':threshold}}


def evaluate(rows,controls,candidates,positive):
    metrics=defaultdict(list);families=defaultdict(list);private=[];status=Counter();scored=[]
    by_day=defaultdict(list);by_stratum=defaultdict(list);by_reply_controls=defaultdict(list)
    for r in rows:
        by_day[r['day']].append(r)
        by_stratum[(r['day'],r.get('mode','unknown'),r.get('surface','unknown'))].append(r)
    for c in controls:by_reply_controls[c['id']].append(c)
    composition={'candidate_days':[], 'evaluation_folds':[]}
    def family_counts(selected):return {f:sum(r['family']==f for r in selected) for f in FAMILIES}
    for candidate in candidates:
        selected=by_day.get(candidate,[])
        composition['candidate_days'].append({'day':candidate,'replies':len(selected),'families':family_counts(selected)})
    for (day,mode,surface),held in sorted(by_stratum.items()):
        if mode=='unknown':status['mode_unknown']+=len(held);continue
        if surface=='unknown':status['surface_unknown']+=len(held);continue
        ref=[r for r in rows if r['day'] in candidates and r['day']!=day
             and r.get('mode')==mode and r.get('surface')==surface]
        composition['evaluation_folds'].append({'day':day,'mode':mode,'surface':surface,'reference_days':len({r['day'] for r in ref}),
            'reference_replies':len(ref),'families':family_counts(ref),
            'mode_sources':dict(Counter(r.get('mode_source','unknown') for r in ref))})
        if len({r['day'] for r in ref})<2:status['insufficient_reference_days']+=len(held);continue
        reference_days=sorted({r['day'] for r in ref})
        state=reference_statistics(ref)
        calibration_states={d:reference_statistics([x for x in ref if x['day']!=d]) for d in reference_days}
        humor=[x for x in ref if x['id'] in positive and any(d!=day for d in positive[x['id']])]
        humor_state=reference_statistics(humor) if len({x['day'] for x in humor})>=2 else None
        calibration=defaultdict(list)
        for r in ref:
            s=score_statistics(r,calibration_states[r['day']])
            if s:
                for k,v in s.items():
                    if v is not None:calibration[k].append(v)
        fold=[]
        for r in held:
            s=score_statistics(r,state)
            if s is None:status['degenerate_reference']+=1;continue
            pct={k:percentile(v,calibration[k]) if v is not None else None for k,v in s.items()}
            for k,v in pct.items():metrics[k+'_percentile'].append((day,v))
            r['family_comparison_eligible']=(r.get('mode_source')!='gloria_family_rule'
                and all(x.get('mode_source')!='gloria_family_rule' for x in ref))
            if r['family_comparison_eligible']:families[r['family']].append((day,pct['semantic']))
            scored.append((r,pct))
            hs=score_statistics(r,humor_state)
            if hs:metrics['witnessed_positive_similarity'].append((day,hs['semantic']))
            for control in by_reply_controls[r['id']]:
                cs=score_statistics(control,state)
                if cs:
                    for k in ('semantic','style','centroid','recent_centroid'):
                        if s[k] is not None and cs[k] is not None:
                            metrics[control['kind']+'_'+k+'_paired_win'].append((day,float(s[k]>cs[k])+.5*(s[k]==cs[k])))
            private.append({'turn_id':r['id'],'day':day,'family':r['family'],'mode':mode,'mode_source':r.get('mode_source','unknown'),
                            'mode_evidence_sha256':r.get('mode_evidence_sha256',[]),
                            'family_comparison_eligible':r['family_comparison_eligible'],'surface':surface,'percentiles':pct,
                            'reference_days':reference_days,'reference_turns':len(ref),
                            'control_matches':[{k:c[k] for k in ('kind','candidate_id','sha','review_binding','context_cosine','source_surface','reviewer_class')}
                                for c in by_reply_controls[r['id']]]})
            fold.append((r,s));status['scored']+=1
        if len(fold)>=2:
            vectors=[r['vector'] for r,s in fold];raw=[s['semantic'] for r,s in fold]
            shuffled=raw[1:]+raw[:1]
            auc=np.mean([float(a>b)+.5*(a==b) for a in raw for b in shuffled])
            metrics['shuffled_own_semantic_marginal_auc'].append((day,float(auc)))
            for i,(r,s) in enumerate(fold):
                metrics['context_alignment_shuffle_delta'].append((day,float(r['context_vector']@(r['vector']-vectors[(i+1)%len(vectors)]))))
    results={key:summarize(values) for key,values in sorted(metrics.items())}
    # Differences use shared evaluation days, avoiding a pure day-composition comparison.
    differences=[]
    for i,left in enumerate(FAMILIES):
        for right in FAMILIES[i+1:]:
            a=defaultdict(list);b=defaultdict(list)
            for d,v in families[left]:
                if v is not None:a[d].append(v)
            for d,v in families[right]:
                if v is not None:b[d].append(v)
            overlap=sorted(set(a)&set(b))
            if overlap:differences.append({'families':[left,right],**summarize([(d,np.mean(a[d])-np.mean(b[d])) for d in overlap])})
    return {'admitted_replies':len(rows),'status':dict(status),'mode_sources':dict(Counter(r.get('mode_source','unknown') for r in rows)),'metrics':results,'reference_family_composition':composition,
            'family_comparison_interpretation':'not_identifiable_family_derived_mode_or_reference' if any(not r.get('family_comparison_eligible',True) for r,_ in scored) else 'within_mode_descriptive' if len({r.get('mode','unknown') for r in rows})==1 and all(r.get('mode','unknown')!='unknown' for r in rows) else 'confounded_with_mode',
            'model_families':{f:summarize(families[f]) for f in FAMILIES},'shared_day_family_differences':differences,
            'context_matched_family_comparisons':context_family_comparisons(scored),
            'evaluation_groups':evaluation_groups(rows,scored)},private


def run(bundle,cutoff,private_control_matches=None,private_mode_assignments=None):
    rows,controls,days,positive,coverage=prepare(bundle,cutoff)
    if private_mode_assignments is not None:
        private_mode_assignments.extend({
            'turn_id':r['id'],'response_sha256':r['sha'],'timestamp':r['at'],
            'day':r['day'],'surface':r['surface'],'family':r['family'],
            'primary':r['primary'],'attribution_basis':r['basis'],
            'mode':r['mode'],'mode_source':r['mode_source'],
            'mode_evidence_sha256':list(r['mode_evidence_sha256'])} for r in rows)
    if private_control_matches is not None:
        private_control_matches.extend({k:c[k] for k in ('id','kind','candidate_id','sha','review_binding','context_cosine','source_surface','reviewer_class')} for c in controls)
    primary,details=evaluate([r for r in rows if r['primary']],controls,days,positive)
    sensitivity,_=evaluate(rows,controls,days,positive)
    for view,selected in ((primary,[r for r in rows if r['primary']]),(sensitivity,rows)):
        view['per_mode']={mode:evaluate([r for r in selected if r.get('mode','unknown')==mode],controls,days,positive)[0] for mode in MODES}
    return {'schema':'character-reference-prototype-v3','input_kind':bundle['input_kind'],
        'reference_status':'candidate_days_not_owner_confirmed','strict_admission_effect':'none','live_effect':'none',
        'encoder_evidence':'supplied_frozen_cache_contract_not_runtime_attestation',
        'encoder_pin':public_encoder_pin(encoder_pin(bundle['encoder'])),
        'meaning':'reference familiarity and style, not authenticity or truth',
        'interval_method':'day_equal_mean_percentile_day_bootstrap_1000_seed17',
        'style_features':list(STYLE),'coverage':coverage,'primary_10s':primary,'sensitivity_window30':sensitivity,
        'limitations':['label_only_without_independent_agreement_excluded','other_surface_is_not_automatically_foreign',
            'shuffling_own_replies_preserves_semantic_marginal_distribution','positive_feedback_is_not_a_negative_label',
            'candidate_selection_is_observational','supplied_controls_and_encoder_contract_are_unverified']},details


def mode_source_summary(report):
    counts=report['coverage']['mode_observations']
    def n(key):
        value=counts.get(key,0)
        if type(value) is not int or value<0:raise ValueError('invalid mode coverage')
        return str(value)
    return ['Mode source counts across all admitted replies (including sensitivity): '+', '.join(src+'='+n('source_'+src) for src in MODE_LABEL_SOURCES)+'.',
        'Somatic coverage: '+n('somatic_covered_replies')+' replies; '+n('somatic_rule_disagreements')+
        ' disagreements among '+n('somatic_rule_comparable_replies')+' comparable family-rule labels. '+
        n('somatic_unbounded_marks')+' marks have no usable interval. Reviewed intervals use zero padding and a 7200-second cap.',
        'Somatic intervals are retrospective supplied reviews, not independently authenticated per-turn decisions. '+
        'Family fallback is an owner assumption, not evidence of cross-model stability.', '']


def render_summary(report):
    """Render aggregate measurements only; never include row-level inputs or IDs."""
    def count(value):
        if type(value) is not int or value<0:raise ValueError('invalid summary count')
        return str(value)
    def number(value):
        if value is None:return 'unknown'
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('invalid summary number')
        return f'{value:.4f}'
    def measurement(value):
        if not value:return ('unknown','unknown','0','0')
        interval=value['interval95']
        ci='unknown' if interval is None else f'[{number(interval[0])}, {number(interval[1])}]'
        return number(value['mean']),ci,count(value['days']),count(value['observations'])
    kind=report['input_kind']
    if kind not in ('synthetic','retained_snapshot'):raise ValueError('invalid summary input kind')
    lines=['# Character-reference results', '',
        'Input: '+('synthetic fixtures; not findings about real history.' if kind=='synthetic' else
                  'supplied copied history; source and encoder declarations are not independently authenticated.'),
        '', 'Measures familiarity relative to a provisional reference, not authenticity or truth.',
        'No live effect or strict-admission change. Candidate dates are not owner-confirmed.',
        'Percentiles and paired wins are on a 0–1 scale. Other similarities/deltas retain their named units.',
        'Mode sources are reported separately: prospective decisions, independent exact links, reviewed somatic intervals, and optional owner family fallback. Unknown modes are unscored.',
        'Means weight days equally; intervals are descriptive day-bootstrap intervals, not independence guarantees.',
        'Unknown means absent or insufficient evidence, never a failure or proof of invariance.', '',
        '## Coverage', '', '| View | Admitted replies | Scored replies |', '| --- | ---: | ---: |']
    pin=report['encoder_pin']
    names={'unknown':'unknown','artifact_hash_declared':'supplied hash; not checked against artifact bytes',
        'artifact_hash_observed':'hash observed from supplied scratch artifact',
        'artifact_hash_verified':'supplied hash matches observed scratch artifact bytes'}
    if pin['artifact_status'] not in names:raise ValueError('invalid encoder identity status')
    lines[3:3]=['Encoder artifact identity: '+names[pin['artifact_status']]+'.',
        'Declared revision is retained privately; cached-vector derivation and revision are not attested by this hash.', '']
    coverage=report['coverage']
    for label,key,field in (('Primary 10 s / exact ID','primary_10s','admitted_primary_replies'),
                           ('Window30 sensitivity','sensitivity_window30','admitted_window30_replies')):
        lines.append(f"| {label} | {count(coverage[field])} | {count(report[key]['status'].get('scored',0))} |")
    lines+=['', '### Engagement by surface', '', '| Surface | Unique owner events |', '| --- | ---: |']
    for surface in SURFACES:lines.append('| '+surface+' | '+count(coverage['engagement_surfaces'][surface])+' |')
    lines+=['', 'The two views overlap and must not be added together.', '', '## Proposed reference dates', '',
            '| Local date | Owner messages | Primary replies | Window30 replies |', '| --- | ---: | ---: | ---: |']
    for day in coverage['candidate_days']:
        date=day['date']
        if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):raise ValueError('invalid summary date')
        lines.append(f"| {date} | {count(day['user_messages'])} | {count(day['attributed_replies_10s'])} | {count(day['attributed_replies_window30'])} |")
    if not coverage['candidate_days']:lines+=['', 'No candidate dates from the supplied engagement counts.']
    facets=('semantic_percentile','style_percentile','centroid_percentile','recent_centroid_percentile',
            'foreign_semantic_paired_win','other_surface_semantic_paired_win','witnessed_positive_similarity',
            'shuffled_own_semantic_marginal_auc','context_alignment_shuffle_delta')
    for title,key in (('Primary results','primary_10s'),('Window30 sensitivity','sensitivity_window30')):
        view=report[key]
        lines+=['', '## '+title, '', '| Measurement | Mean | 95% interval | Days | Observations |',
                '| --- | ---: | --- | ---: | ---: |']
        for facet in facets:lines.append('| '+' | '.join((facet,*measurement(view['metrics'].get(facet))))+' |')
        lines+=['', '### Candidate reference composition', '',
                'Counts before each evaluation day is held out; exact per-fold counts are in aggregate.json.',
                'Unequal family composition can affect familiarity. These counts do not correct it or establish model invariance.', '',
                '| Date | Replies | '+' | '.join(FAMILIES)+' |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for entry in view['reference_family_composition']['candidate_days']:
            day=entry['day']
            if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('invalid summary date')
            lines.append('| '+' | '.join((day,count(entry['replies']),*(count(entry['families'][f]) for f in FAMILIES)))+' |')
        lines+=['', '### Mode-specific familiarity and comparisons', '',
                'Controls require an exact bound supplied provenance review; reviewer claims are not independently authenticated.',
                'Store-authorship evidence is a separate supplied class, not a human review or verified authorship.',
                'Foreign controls match surface; other-surface controls are his own text elsewhere, not non-him negatives.',
                'References and controls must match mode; reference replies also match surface. Unknown mode is unscored.',
                'Pooled family differences are confounded with mode and are omitted here.', '',
                '| Mode | Admitted / scored | Facet | Mean | 95% interval | Days | Observations |',
                '| --- | ---: | --- | ---: | --- | ---: | ---: |']
        for mode in MODES:
            mv=view['per_mode'][mode]
            for facet in ('semantic_percentile','style_percentile','centroid_percentile','recent_centroid_percentile'):
                lines.append('| '+' | '.join((mode,count(mv['admitted_replies'])+' / '+count(mv['status'].get('scored',0)),facet,*measurement(mv['metrics'].get(facet))))+' |')
        lines+=['', '| Mode | Families (left minus right) | Matched pairs | Identifiability | Facet | Mean difference | 95% interval | Days | Observations |',
                '| --- | --- | ---: | --- | --- | ---: | --- | ---: | ---: |']
        for mode in MODES[:2]:
            for pair in view['per_mode'][mode]['context_matched_family_comparisons']['pairs']:
                names=pair['families']
                if len(names)!=2 or any(f not in FAMILIES[:3] for f in names):raise ValueError('invalid summary family')
                identifiable='matched comparison available' if pair['matched_pairs'] else 'not identifiable'
                prefix=(mode,names[0]+' / '+names[1],count(pair['matched_pairs']),identifiable)
                for facet in ('semantic','style','centroid','recent_centroid'):
                    lines.append('| '+' | '.join((*prefix,facet,*measurement(pair['percentile_differences'][facet])))+' |')
        lines+=['', '### Optional evaluation groups', '',
                'Declared annotations; overlapping groups do not define identity or supply witnessed positive feedback.', '',
                '| Annotator | Group | Annotated / scored / unscored | Facet | Mean percentile | 95% interval | Days | Observations |',
                '| --- | --- | --- | --- | ---: | --- | ---: | ---: |']
        found=False
        for source in ANNOTATORS:
            for category in EVALUATION_GROUPS:
                group=view['evaluation_groups']['groups'][source][category]
                if not group['annotated_replies']:continue
                found=True
                counts=' / '.join(count(group[k]) for k in ('annotated_replies','scored_replies','unscored_replies'))
                for facet in ('semantic','style','centroid','recent_centroid'):
                    lines.append('| '+' | '.join((source,category,counts,facet,*measurement(group['percentiles'][facet])))+' |')
        if not found:lines+=['', 'No linked evaluation annotations in this view; group behavior is unknown.']
    lines+=['', 'Own-reply shuffling preserves marginal familiarity (expected AUC 0.5); context alignment is a separate check.',
            'Other-surface text is not automatically foreign. Positive ratings/laughs do not label unobserved replies as failures.',
            'No acceptance threshold or identity decision is produced.', '']
    return '\n'.join(lines+mode_source_summary(report))


def render_reader_summary(report):
    """A short reader page, using only fixed labels and aggregate numbers."""
    def count(value):
        if type(value) is not int or value<0:raise ValueError('invalid reader count')
        return str(value)
    def number(value):
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
            raise ValueError('invalid reader proportion')
        return f'{value:.2f}'
    def measure(value):
        if not value or value.get('mean') is None:return 'not measured'
        interval=value.get('interval95')
        uncertainty='interval unavailable'
        if interval is not None:
            if not isinstance(interval,list) or len(interval)!=2 or interval[0]>interval[1]:
                raise ValueError('invalid reader interval')
            uncertainty='95% interval '+number(interval[0])+'–'+number(interval[1])
        return number(value['mean'])+' ('+uncertainty+'; '+count(value['observations'])+' observations across '+count(value['days'])+' days)'
    if report.get('schema')!='character-reference-prototype-v3':raise ValueError('reader requires schema v3')
    if report.get('input_kind') not in ('synthetic','retained_snapshot'):raise ValueError('invalid reader input kind')
    primary=report['primary_10s'];coverage=report['coverage']
    scored=count(primary['status'].get('scored',0))
    lines=['# What the character judge can say', '',
        '**Synthetic demonstration only — these are not findings about his conversations.**' if report['input_kind']=='synthetic'
        else 'Offline results from a supplied copy of historical records. No live behavior was changed.', '',
        'The primary analysis scored '+scored+' of '+count(primary['admitted_replies'])+' attributable replies.' if int(scored)
        else '**The primary analysis has no scored replies. It cannot yet support a familiarity comparison.**', '',
        'This measures how familiar a reply is compared with his replies on higher-engagement days. '
        'Each reply uses references from other days in the same conversation mode and surface. '
        'It does not determine identity, truth, or whether a reply is good.', '',
        '## What was measurable', '',
        'Primary uses the narrower attribution rule. The 30-second sensitivity check uses a broader rule; '
        'it cannot replace missing primary evidence. The two views overlap and must not be added.', '',
        '| View | Conversation mode | Attributable / scored replies | Familiarity percentile | Own vs other-author comparison |',
        '| --- | --- | ---: | --- | --- |']
    labels={'opening_everyday':'Opening / everyday','intimate':'Intimate','unknown':'Unknown mode'}
    for title,key in (('Primary','primary_10s'),('30-second sensitivity','sensitivity_window30')):
        view=report[key]
        for mode in MODES:
            cell=view['per_mode'][mode];metrics=cell['metrics']
            lines.append('| '+' | '.join((title,labels[mode],count(cell['admitted_replies'])+' / '+count(cell['status'].get('scored',0)),
                measure(metrics.get('semantic_percentile')),measure(metrics.get('foreign_semantic_paired_win'))))+' |')
    lines+=['', 'A percentile is a rank against the reference replies, not a probability that a reply is him. '
        'The other-author number is how often his reply scored higher than its matched comparison '
        '(ties count half). Days receive equal weight. These intervals describe this sample, not a validated identity detector.', '',
        '## What remains uncertain', '',
        '- '+count(coverage['matched_controls'])+' control pairs were selected. Selection is not the same as scoring: '
        'the table shows the comparisons that had usable references. His own writing on another surface is a separate check, not another-author evidence.',
        '- '+count(coverage['positive_reply_links'])+' replies have linked positive laughs or ratings. '
        'These support a limited positive-example facet, not a general humor verdict; missing reactions are not failures.',
        '- '+count(len(coverage['candidate_days']))+' higher-engagement dates are provisional reference candidates. '
        'High engagement does not certify every reply on those days.',
        '- Mode uses decision receipts first, then independent evidence or reviewed somatic intervals. Explicit owner family fallback is labelled; unknown stays unscored. '
        'Cross-family comparisons exclude family-labelled targets and any fold with family-labelled references. No independent overlap means not identifiable, not invariant.',
        '- Control authorship and source reviews are supplied claims. Store metadata is kept separate from human review. '
        'Even a verified artifact hash does not establish the revision label or how cached vectors were produced.', '',
        'The detailed summary contains style, surface coverage, source classes and within-mode comparisons. '
        'Private text, individual reply records and vectors remain in local scratch. '
        'No acceptance threshold, model switch or deployment follows from this report.', '']
    return '\n'.join(lines+mode_source_summary(report))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('scratch','input','output','cutoff'):p.add_argument('--'+arg,required=True)
    p.add_argument('--encoder-artifact',help='explicit regular artifact copy inside private scratch; hash only')
    args=p.parse_args();root=scratch_root(args.scratch)
    source,out=inside(root,args.input),inside(root,args.output)
    if out.exists() or out in source.parents:raise ValueError('new output directory required')
    install_guard(root,out)
    with source.open('rb') as f:raw=f.read(64*1024*1024+1)
    if len(raw)>64*1024*1024:raise ValueError('snapshot exceeds prototype limit')
    bundle=decode_snapshot(raw)
    control_matches=[];mode_assignments=[]
    report,details=run(bundle,args.cutoff,control_matches,mode_assignments)
    artifact=inside(root,args.encoder_artifact) if args.encoder_artifact else None
    pin=encoder_pin(bundle['encoder'],observe_encoder_artifact(artifact) if artifact is not None else None)
    report['encoder_pin']=public_encoder_pin(pin)
    out.mkdir(mode=0o700)
    for name,data in (('aggregate.json',report),('private-evaluation.json',details),('private-controls.json',control_matches),
                      ('private-mode-assignments.json',mode_assignments),
                      ('private-run.json',{'input_sha256':hashlib.sha256(raw).hexdigest(),'cutoff':instant(args.cutoff),'encoder_pin':pin,
                        'code_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                            ('experiments/character-reference/prototype.py','scripts/witness_attribution.py','scripts/witness_receipts.py','scripts/request_trace.py')}})):
        with (out/name).open('x') as f:json.dump(data,f,sort_keys=True,allow_nan=False)
        (out/name).chmod(0o600)
    for name,renderer in (('summary.md',render_summary),('reader-summary.md',render_reader_summary)):
        with (out/name).open('x') as f:f.write(renderer(report))
        (out/name).chmod(0o600)
    print(json.dumps({'written':True,'scored':report['primary_10s']['status'].get('scored',0)}))


def cli():
    try:main()
    except Exception as exc:
        name=type(exc).__name__
        allowed={'ValueError','TypeError','KeyError','OSError','PermissionError','FileNotFoundError','RuntimeError'}
        print(json.dumps({'written':False,'error':'prototype_failed',
            'error_type':name if name in allowed else 'Exception'}),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':sys.exit(cli())
