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
STYLE=('log_chars','log_words','mean_word_chars','question_per_word','exclaim_per_word',
       'comma_per_word','uppercase_fraction','first_person_per_word','newline_per_word')


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
            if (a['day']!=b['day'] or not a['language'] or a['language']!=b['language']
                    or not .5<=len(a['text'])/max(1,len(b['text']))<=2):continue
            similarity=float(a['context_vector']@b['context_vector'])
            if similarity>=.7:choices.append((-similarity,b['id']))
        if choices:
            negative,bid=min(choices);pairs.append((a,available.pop(bid),-negative))
    return pairs


def context_family_comparisons(scored):
    by_family=defaultdict(list);out=[]
    for row,percentiles in scored:by_family[row['family']].append(row)
    outcomes={r['id']:p for r,p in scored}
    for i,left in enumerate(FAMILIES[:3]):
        for right in FAMILIES[i+1:3]:
            a,b=by_family[left],by_family[right]
            pairs=context_pairs(a,b)
            metrics={k:summarize([(x['day'],outcomes[x['id']][k]-outcomes[y['id']][k])
                for x,y,_ in pairs if outcomes[x['id']][k] is not None and outcomes[y['id']][k] is not None])
                for k in ('semantic','style','centroid','recent_centroid')}
            out.append({'families':[left,right],'left_scored':len(a),'right_scored':len(b),
                'matched_pairs':len(pairs),'left_unmatched':len(a)-len(pairs),'right_unmatched':len(b)-len(pairs),
                'context_cosine':summarize([(x['day'],c) for x,y,c in pairs]),
                'percentile_differences':metrics})
    return {'matching':'same_day_language_length_ratio_0.5_to_2_context_cosine_at_least_0.7',
        'assignment':'left_reply_id_order_best_available_context_then_right_id',
        'meaning':'descriptive_matched_association_not_causal_model_effect',
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


def prepare(bundle,cutoff):
    if bundle.get('input_kind') not in ('synthetic','retained_snapshot'):raise ValueError('explicit input kind required')
    encoder=bundle['encoder']
    fields={'family','revision','pooling','normalization','prefix_chars','frozen','id'}
    if (not isinstance(encoder,dict) or set(encoder)!=fields or encoder['family']!='nomic'
            or encoder['frozen'] is not True or encoder['normalization']!='l2'
            or type(encoder['prefix_chars']) is not int or not 1<=encoder['prefix_chars']<=65536
            or any(not isinstance(encoder[k],str) or not 1<=len(encoder[k])<=256 for k in ('id','revision','pooling'))):
        raise ValueError('explicit frozen encoder contract required')
    zone=ZoneInfo(bundle['timezone']);cutoff=instant(cutoff)
    rows=bundle['rows']
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded explicit history required')
    cfg=dict(bundle['historical_attribution']);ledger=cfg.pop('compute_ledger')
    cfg['window30_enabled']=True
    if cfg.get('window_seconds',10)!=10:raise ValueError('primary attribution must use ten seconds')
    attribution_report,details=attribution(rows,ledger,cfg,cutoff)
    for key,limit in (('embeddings',10000),('feedback',10000),('controls',4096),('evaluation_annotations',10000)):
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
    users={};engagement=Counter();excluded=Counter();prepared=[];versions={}
    all_versions={}
    for row in rows:
        if row.get('role')=='assistant' and row.get('turn_id'):
            key=row['turn_id'];version=digest(final_response(row))
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
                         'language':row.get('language'),'surface':row.get('surface')})
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
    controls=[];control_versions={}
    for item in bundle.get('controls',[]):
        row=by_id.get(item.get('matched_reply_id'))
        if row is None or item.get('kind') not in ('foreign','other_surface'):continue
        text=item['content']
        if not isinstance(text,str) or not 0<len(text)<=65536:raise ValueError('invalid control text')
        key=(item['matched_reply_id'],item['kind'],digest(text));version=json.dumps(item,sort_keys=True,allow_nan=False)
        if key in control_versions:
            if control_versions[key]!=version:raise ValueError('conflicting control copies')
            continue
        control_versions[key]=version
        v=unit(item['vector'],dimension);c=unit(item['context_vector'],dimension)
        if (item['encoder_id']!=encoder['id'] or item['input_sha256']!=digest(text[:encoder['prefix_chars']])
                or item['context_sha256']!=digest(item['context'])):raise ValueError('control encoder/input mismatch')
        if digest(text) in seen:excluded['control_reuses_reply_text']+=1;continue
        if (not row['language'] or item.get('language')!=row['language']
                or not .5<=max(1,len(text))/max(1,len(row['text']))<=2
                or float(c@row['context_vector'])<.7):excluded['control_not_matched']+=1;continue
        controls.append({'id':item['matched_reply_id'],'kind':item['kind'],'vector':v,'style':style(text)})
    return unique,controls,candidates,positive,{'excluded':dict(excluded),'attribution':attribution_report,
        'feedback':dict(feedback_counts),'positive_reply_links':len(positive),
        'admission_bases':dict(Counter(r['basis'] for r in unique)),
        'admitted_primary_replies':sum(r['primary'] for r in unique),'admitted_window30_replies':len(unique),
        'matched_controls':len(controls),'evaluation_annotations':dict(annotation_counts),
        'candidate_days':[{'date':d,'user_messages':engagement[d],
            'attributed_replies_10s':sum(r['day']==d and r['primary'] for r in unique),
            'attributed_replies_window30':sum(r['day']==d for r in unique)} for d in candidates],
        'selection':{'observed_user_days':len(counts),'median_user_messages':median,'top_quarter_threshold':threshold}}


def evaluate(rows,controls,candidates,positive):
    metrics=defaultdict(list);families=defaultdict(list);private=[];status=Counter();scored=[]
    by_day=defaultdict(list);by_reply_controls=defaultdict(list)
    for r in rows:by_day[r['day']].append(r)
    for c in controls:by_reply_controls[c['id']].append(c)
    composition={'candidate_days':[], 'evaluation_folds':[]}
    def family_counts(selected):return {f:sum(r['family']==f for r in selected) for f in FAMILIES}
    for candidate in candidates:
        selected=by_day.get(candidate,[])
        composition['candidate_days'].append({'day':candidate,'replies':len(selected),'families':family_counts(selected)})
    for day,held in sorted(by_day.items()):
        ref=[r for r in rows if r['day'] in candidates and r['day']!=day]
        composition['evaluation_folds'].append({'day':day,'reference_days':len({r['day'] for r in ref}),
            'reference_replies':len(ref),'families':family_counts(ref)})
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
            families[r['family']].append((day,pct['semantic']))
            scored.append((r,pct))
            hs=score_statistics(r,humor_state)
            if hs:metrics['witnessed_positive_similarity'].append((day,hs['semantic']))
            for control in by_reply_controls[r['id']]:
                cs=score_statistics(control,state)
                if cs:
                    for k in ('semantic','style','centroid','recent_centroid'):
                        if s[k] is not None and cs[k] is not None:
                            metrics[control['kind']+'_'+k+'_paired_win'].append((day,float(s[k]>cs[k])+.5*(s[k]==cs[k])))
            private.append({'turn_id':r['id'],'day':day,'family':r['family'],'percentiles':pct,
                            'reference_days':reference_days,'reference_turns':len(ref)})
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
    return {'status':dict(status),'metrics':results,'reference_family_composition':composition,
            'model_families':{f:summarize(families[f]) for f in FAMILIES},'shared_day_family_differences':differences,
            'context_matched_family_comparisons':context_family_comparisons(scored),
            'evaluation_groups':evaluation_groups(rows,scored)},private


def run(bundle,cutoff):
    rows,controls,days,positive,coverage=prepare(bundle,cutoff)
    primary,details=evaluate([r for r in rows if r['primary']],controls,days,positive)
    sensitivity,_=evaluate(rows,controls,days,positive)
    return {'schema':'character-reference-prototype-v1','input_kind':bundle['input_kind'],
        'reference_status':'candidate_days_not_owner_confirmed','strict_admission_effect':'none','live_effect':'none',
        'encoder_evidence':'supplied_frozen_cache_contract_not_runtime_attestation',
        'meaning':'reference familiarity and style, not authenticity or truth',
        'interval_method':'day_equal_mean_percentile_day_bootstrap_1000_seed17',
        'style_features':list(STYLE),'coverage':coverage,'primary_10s':primary,'sensitivity_window30':sensitivity,
        'limitations':['label_only_without_independent_agreement_excluded','other_surface_is_not_automatically_foreign',
            'shuffling_own_replies_preserves_semantic_marginal_distribution','positive_feedback_is_not_a_negative_label',
            'candidate_selection_is_observational','supplied_controls_and_encoder_contract_are_unverified']},details


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
        'Means weight days equally; intervals are descriptive day-bootstrap intervals, not independence guarantees.',
        'Unknown means absent or insufficient evidence, never a failure or proof of invariance.', '',
        '## Coverage', '', '| View | Admitted replies | Scored replies |', '| --- | ---: | ---: |']
    coverage=report['coverage']
    for label,key,field in (('Primary 10 s / exact ID','primary_10s','admitted_primary_replies'),
                           ('Window30 sensitivity','sensitivity_window30','admitted_window30_replies')):
        lines.append(f"| {label} | {count(coverage[field])} | {count(report[key]['status'].get('scored',0))} |")
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
        lines+=['', '### Model-family familiarity', '', '| Family | Mean | 95% interval | Days | Replies |',
                '| --- | ---: | --- | ---: | ---: |']
        for f in FAMILIES:lines.append('| '+' | '.join((f,*measurement(view['model_families'][f])))+' |')
        lines+=['', '### Context-matched family comparisons', '',
                'Same day/language, length ratio 0.5–2, context cosine at least 0.7; descriptive association, not a causal effect.',
                '', '| Families (left minus right) | Pairs | Unmatched left / right | Facet | Mean difference | 95% interval | Days | Observations |',
                '| --- | ---: | --- | --- | ---: | --- | ---: | ---: |']
        for pair in view['context_matched_family_comparisons']['pairs']:
            names=pair['families']
            if len(names)!=2 or any(f not in FAMILIES[:3] for f in names):raise ValueError('invalid summary family')
            prefix=(names[0]+' / '+names[1],count(pair['matched_pairs']),count(pair['left_unmatched'])+' / '+count(pair['right_unmatched']))
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
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('scratch','input','output','cutoff'):p.add_argument('--'+arg,required=True)
    args=p.parse_args();root=scratch_root(args.scratch)
    source,out=inside(root,args.input),inside(root,args.output)
    if out.exists() or out in source.parents:raise ValueError('new output directory required')
    install_guard(root,out)
    with source.open('rb') as f:raw=f.read(64*1024*1024+1)
    if len(raw)>64*1024*1024:raise ValueError('snapshot exceeds prototype limit')
    report,details=run(decode_snapshot(raw),args.cutoff)
    out.mkdir(mode=0o700)
    for name,data in (('aggregate.json',report),('private-evaluation.json',details),
                      ('private-run.json',{'input_sha256':hashlib.sha256(raw).hexdigest(),'cutoff':instant(args.cutoff),
                        'code_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                            ('experiments/character-reference/prototype.py','scripts/witness_attribution.py','scripts/witness_receipts.py')}})):
        with (out/name).open('x') as f:json.dump(data,f,sort_keys=True,allow_nan=False)
        (out/name).chmod(0o600)
    with (out/'summary.md').open('x') as f:f.write(render_summary(report))
    (out/'summary.md').chmod(0o600)
    print(json.dumps({'written':True,'scored':report['primary_10s']['status'].get('scored',0)}))


if __name__=='__main__':main()
