#!/usr/bin/env python3
"""Pure offline recurrence counts and candidate groups; no runtime imports or effects."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

KINDS={'original_act','context','copy','generated','judge_effect','emotion_nudge','tactical','imported'}
INFLUENCE=KINDS-{'original_act','context'}
SURFACES={'avatar','reelroom','voice','journal','action'}
MODES={'everyday','intimate'}
LIMIT=512


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def hashed(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def identifier(value):
    return isinstance(value,str) and 0<len(value)<=256


def stamp(value):
    if type(value) in (int,float) and math.isfinite(value):return float(value)
    if isinstance(value,str):
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is not None:return d.timestamp()
    raise ValueError('explicit finite timestamp required')


def bounded(value):
    if not isinstance(value,list) or len(value)>LIMIT:raise ValueError('bounded list required')
    return value


def admit(events,nodes,cutoff,zone='UTC'):
    """Supplied lineage is audited structurally, not independently authenticated."""
    cutoff=stamp(cutoff);tz=ZoneInfo(zone);graph={};counts=Counter();versions={}
    for n in bounded(nodes):
        if (not isinstance(n,dict) or set(n)!={'id','kind','at','parents','complete'}
                or not identifier(n['id']) or not isinstance(n['kind'],str) or n['kind'] not in KINDS
                or type(n['complete']) is not bool or not isinstance(n['parents'],list)
                or len(n['parents'])>LIMIT or any(not identifier(p) for p in n['parents'])):
            raise ValueError('invalid lineage node')
        normalized=dict(n,at=stamp(n['at']),parents=sorted(set(n['parents'])))
        if n['id'] in graph and graph[n['id']]!=normalized:raise ValueError('conflicting lineage node')
        graph[n['id']]=normalized
    memo={}
    def reason(key,trail=()):
        if key in trail:return 'lineage_cycle'
        if len(trail)>=64:return 'lineage_depth'
        if key in memo:return memo[key]
        node=graph.get(key)
        if node is None:return 'lineage_missing'
        if not node['complete']:return 'lineage_incomplete'
        if node['at']>=cutoff:return 'outside_cutoff'
        if node['kind'] in INFLUENCE:return 'influenced_or_derived'
        for parent in node['parents']:
            if parent in graph and graph[parent]['at']>node['at']:return 'future_parent'
            why=reason(parent,trail+(key,))
            if why:return why
        memo[key]=None
        return None
    accepted=[]
    for event in bounded(events):
        if (not isinstance(event,dict) or set(event)!={'node_id','origin_id','at','content_sha256','surface','mode','source'}
                or not identifier(event['node_id']) or not identifier(event['origin_id'])
                or not hashed(event['content_sha256']) or not identifier(event['source'])):
            raise ValueError('invalid original-event contract')
        row=dict(event,at=stamp(event['at']))
        key=row['node_id'];encoded=canonical(row)
        if key in versions:
            if versions[key]!=encoded:raise ValueError('conflicting event identity')
            counts['duplicate_copy']+=1;continue
        versions[key]=encoded
        node=graph.get(key);why=reason(key)
        if not why and (node['kind']!='original_act' or row['origin_id']!=key):why='not_original_act'
        if not why and row['at']!=node['at']:why='timestamp_mismatch'
        if not why and (not isinstance(row['surface'],str) or row['surface'] not in SURFACES
                        or not isinstance(row['mode'],str) or row['mode'] not in MODES):why='scope_unknown'
        if why:counts[why]+=1;continue
        row['day']=datetime.fromtimestamp(row['at'],tz).date().isoformat();accepted.append(row)
    return sorted(accepted,key=lambda r:r['node_id']),{
        'input_rows':len(events),'admitted_original_acts':len(accepted),'excluded':dict(sorted(counts.items())),
        'lineage_independently_verified':False}


def recurrence(events,nodes,assignments,cutoff,zone='UTC'):
    rows,coverage=admit(events,nodes,cutoff,zone);by_id={r['node_id']:r for r in rows}
    labels={};counts=Counter()
    for a in bounded(assignments):
        if (not isinstance(a,dict) or set(a)!={'node_id','content_sha256','topic_id','reviewed','evidence_sha256'}
                or not identifier(a['node_id']) or not identifier(a['topic_id'])
                or not hashed(a['content_sha256']) or not hashed(a['evidence_sha256']) or type(a['reviewed']) is not bool):
            raise ValueError('invalid topic assignment')
        if a['node_id'] in labels:
            if labels[a['node_id']]!=a:raise ValueError('conflicting topic assignment')
            counts['duplicate_assignment']+=1;continue
        labels[a['node_id']]=dict(a)
    groups=defaultdict(list)
    for key,a in labels.items():
        row=by_id.get(key)
        if not a['reviewed'] or row is None or row['content_sha256']!=a['content_sha256']:
            counts['unreviewed_or_unlinked']+=1;continue
        # Keep distinct contexts distinct even if the supplied topic label is shared.
        groups[(a['topic_id'],row['surface'],row['mode'])].append(row)
    private=[]
    for (topic,surface,mode),members in sorted(groups.items()):
        private.append({'topic_id':topic,'surface':surface,'mode':mode,
            'original_ids':sorted(r['node_id'] for r in members),
            'unique_acts':len(members),'distinct_days':len({r['day'] for r in members})})
    public={'schema':'offline-recurrence-v1','coverage':coverage,'assignment_exclusions':dict(sorted(counts.items())),
        'assigned_acts':sum(g['unique_acts'] for g in private),
        'unassigned_admitted_acts':len(rows)-sum(g['unique_acts'] for g in private),
        'topic_scope_groups':len(private),
        'group_counts':sorted([{'unique_acts':g['unique_acts'],'distinct_days':g['distinct_days']} for g in private],
                              key=lambda g:(g['unique_acts'],g['distinct_days'])),
        'meaning':'observed_recurrence_not_yearning_or_resolution','topic_assignments_independently_verified':False,
        'effects':'none'}
    return public,private


def vector(value,dimension):
    if (not isinstance(value,list) or len(value)!=dimension
            or any(type(v) not in (float,int) or not math.isfinite(v) for v in value)):
        raise ValueError('invalid cached vector')
    norm=math.sqrt(sum(v*v for v in value))
    if abs(norm-1)>1e-6:raise ValueError('cached vector must be unit length')
    return tuple(v/norm for v in value)


def candidate_groups(events,nodes,embeddings,encoder,cutoff,minimum_cosine,zone='UTC'):
    """Complete-link suggestions within source/day/surface/mode; no merge or removal."""
    if type(minimum_cosine) not in (float,int) or not math.isfinite(minimum_cosine) or not -1<=minimum_cosine<=1:
        raise ValueError('explicit finite cosine threshold required')
    if (not isinstance(encoder,dict) or set(encoder)!={'id','artifact_sha256','dimension','frozen_at','frozen'}
            or not identifier(encoder['id']) or not hashed(encoder['artifact_sha256']) or encoder['frozen'] is not True
            or type(encoder['dimension']) is not int or not 1<=encoder['dimension']<=2048):
        raise ValueError('explicit frozen encoder contract required')
    frozen=stamp(encoder['frozen_at']);rows,coverage=admit(events,nodes,cutoff,zone);cache={};counts=Counter()
    if len(rows)>128:raise ValueError('candidate grouping limited to 128 admitted acts')
    for e in bounded(embeddings):
        if (not isinstance(e,dict) or set(e)!={'node_id','content_sha256','encoder_id','vector'}
                or not identifier(e['node_id']) or not hashed(e['content_sha256'])):
            raise ValueError('invalid cache record')
        if e['node_id'] in cache and cache[e['node_id']]!=e:raise ValueError('conflicting cache record')
        vector(e['vector'],encoder['dimension']);cache[e['node_id']]=dict(e)
    by_scope=defaultdict(list);vectors={}
    for row in rows:
        e=cache.get(row['node_id'])
        if frozen>row['at'] or frozen>=stamp(cutoff):counts['encoder_not_frozen_before_event']+=1;continue
        if e is None:counts['cache_missing']+=1;continue
        if e['encoder_id']!=encoder['id'] or e['content_sha256']!=row['content_sha256']:
            counts['cache_binding_mismatch']+=1;continue
        vectors[row['node_id']]=vector(e['vector'],encoder['dimension'])
        by_scope[(row['source'],row['day'],row['surface'],row['mode'])].append(row['node_id'])
    pairs={}
    def cosine(a,b):
        key=tuple(sorted((a,b)))
        if key not in pairs:pairs[key]=max(-1.,min(1.,sum(x*y for x,y in zip(vectors[a],vectors[b]))))
        return pairs[key]
    private=[]
    for scope,ids in sorted(by_scope.items()):
        clusters=[(key,) for key in sorted(ids)]
        while True:
            choices=[]
            for i,a in enumerate(clusters):
                for j in range(i+1,len(clusters)):
                    b=clusters[j];score=min(cosine(x,y) for x in a for y in b)
                    if score>=minimum_cosine:choices.append((-score,tuple(sorted(a+b)),i,j))
            if not choices:break
            _,merged,i,j=min(choices)
            clusters=[c for k,c in enumerate(clusters) if k not in (i,j)]+[merged];clusters.sort()
        for members in clusters:
            minimum=min((cosine(a,b) for i,a in enumerate(members) for b in members[i+1:]),default=None)
            private.append({'source':scope[0],'day':scope[1],'surface':scope[2],'mode':scope[3],
                            'member_ids':list(members),'size':len(members),'minimum_pair_cosine':minimum})
    public={'schema':'offline-thread-groups-v1','coverage':coverage,'cache_exclusions':dict(sorted(counts.items())),
        'minimum_cosine':minimum_cosine,'scored_acts':len(vectors),
        'suggested_groups':sum(g['size']>1 for g in private),'singletons':sum(g['size']==1 for g in private),
        'groups':sorted([{'size':g['size'],'minimum_pair_cosine':g['minimum_pair_cosine']} for g in private],
                        key=lambda g:(g['size'],g['minimum_pair_cosine'] or 0)),
        'meaning':'similarity_suggestions_not_duplicate_or_resolution_verdicts',
        'encoder_artifact_verified':False,'cache_derivation_verified':False,'effects':'none'}
    return public,private


def demo():
    sha=lambda text:hashlib.sha256(text.encode()).hexdigest()
    nodes=[];events=[];assignments=[];embeddings=[]
    for i in range(3):
        key='synthetic-act-'+str(i);at=1609459200.+i
        nodes.append(dict(id=key,kind='original_act',at=at,parents=[],complete=True))
        events.append(dict(node_id=key,origin_id=key,at=at,content_sha256=sha(key),surface='avatar',mode='everyday',source='synthetic'))
        assignments.append(dict(node_id=key,content_sha256=sha(key),topic_id='synthetic-topic',reviewed=True,evidence_sha256=sha('synthetic evidence')))
        embeddings.append(dict(node_id=key,content_sha256=sha(key),encoder_id='synthetic-encoder',vector=[1.,0.] if i<2 else [0.,1.]))
    encoder=dict(id='synthetic-encoder',artifact_sha256=sha('synthetic artifact'),dimension=2,frozen_at=1609459100.,frozen=True)
    cutoff=1609459300.
    return {'input_kind':'synthetic','recurrence':recurrence(events,nodes,assignments,cutoff)[0],
            'groups':candidate_groups(events,nodes,embeddings,encoder,cutoff,.9)[0]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--demo',action='store_true',required=True)
    parser.parse_args();print(json.dumps(demo(),sort_keys=True,allow_nan=False))
