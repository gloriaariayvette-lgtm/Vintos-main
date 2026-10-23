"""Read-only, exact-window Lab executions and explicit downstream evidence use."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os


def timestamp(value):
    try:
        t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
    except (ValueError,TypeError):return None


def report(root, since, until):
    root=Path(root);start,end=timestamp(since),timestamp(until)
    if not start or not end or end<=start:raise ValueError('an exact increasing ISO time window is required')
    def inside(r):
        t=timestamp(r.get('at') or r.get('retrieved_at') or r.get('fetched_at'))
        return t is not None and start<=t<end
    def rows(name):
        p=root/name
        if not p.is_file():return []
        out=[]
        with p.open() as stream:
            for line in stream:
                try:r=json.loads(line)
                except ValueError:continue
                if isinstance(r,dict):out.append(r)
        return out
    counts=Counter(); failures=Counter(); use=Counter(); paths=defaultdict(Counter);seen=set()
    def record(tool, identity, path, good=True):
        key=(tool,identity)
        if identity and key in seen:return
        if identity:seen.add(key)
        (counts if good else failures)[tool]+=1;paths[tool][path]+=1
    for r in rows('source-receipts.jsonl'):
        if inside(r):
            source=str(r.get('source')); tool='source:'+source
            if source=='evo2_local':
                for run in r.get('records') or []:
                    record('regulatory_genome' if run.get('atlas_receipt_id') else 'genome',run.get('run_id'),'computed_source_projection',run.get('ok') is True)
                continue
            if source.startswith('plugin:'):
                plugin=source.split(':',1)[1]; name=str((r.get('query') or {}).get('tool') or '')
                tool='plugin:'+(name if name.startswith(plugin+'.') else plugin+'.'+name)
            record(tool,r.get('receipt_id'),'source_receipts')
    for r in rows('notebook.jsonl'):
        if not inside(r):continue
        if r.get('kind')=='protein_representation':record('representation',r.get('at'),'legacy_embed',bool(r.get('embeddings')))
    for r in rows('evo2-runs.jsonl'):
        if inside(r):record('regulatory_genome' if r.get('atlas_receipt_id') else 'genome',r.get('run_id'),'genomic_phase',r.get('ok') is True)
    for r in rows('sessions.jsonl'):
        if inside(r):record('experiment:'+str((r.get('plan') or {}).get('experiment')),r.get('session_id'),'daily_session',r.get('state')=='completed')
    try:data=json.loads((root/'investigations.json').read_text())
    except (OSError,ValueError):data={'investigations':[]}
    all_steps={s['id']:s for inv in data.get('investigations',[]) for s in inv.get('steps',[])}
    chains=[]
    for inv in data.get('investigations',[]):
        links=[]
        for s in inv.get('steps',[]):
            if not inside(s):continue
            tool=s.get('tool') or s.get('route') or 'unknown'
            if s.get('origin')=='autonomous_lab' and not s.get('reused_from') and s.get('state') in ('completed','failed','outcome_unknown') and s.get('route') not in ('read_output','schema'):
                record(tool,s.get('execution_receipt_id') or s.get('run_id') or s['id'],'investigation',s.get('state')=='completed')
            if s.get('state')!='completed':continue
            for ref in s.get('input_refs') or []:
                prior=all_steps.get(ref.get('step'))
                if prior and prior.get('state')=='completed':
                    use[prior.get('tool') or prior.get('route') or 'unknown']+=1
                    links.append({'from':prior['id'],'to':s['id'],'path':ref.get('path'),'consumer':tool})
        if links:chains.append({'investigation':inv['id'],'question':inv.get('question'),'links':links})
    expected={'representation','genome','regulatory_genome','campaign'}
    expected.update('experiment:'+name for name in ('protein','molecule','fold','titrate'))
    expected.update('source:'+name for name in ('uniprot','pdb','ncbi','ncbi_sequence','ncbi_gene_identity','ncbi_protein_context',
        'ncbi_neighborhood','rt_locus_screen','atlas','interpro','chembl','pubchem','pubmed','pubmed_abstracts','reactome','rhea','quickgo','mgnify','imgvr','bvbrc'))
    from plugin_catalog import PLUGINS
    from claude_connector_catalog import PLUGINS as ACCOUNT
    from lab_instruments import OFFERED
    from lab_native_instruments import OPERATIONS
    for name,entry in {**PLUGINS,**ACCOUNT}.items():
        if entry.get('enabled') is False or 'lab' not in entry.get('surfaces',()):continue
        for tool in entry.get('tools',()) or (entry.get('read',frozenset())|entry.get('action',frozenset())):
            expected.add('plugin:'+(tool if tool.startswith(name+'.') else name+'.'+tool))
    expected.update('instrument:'+name for name in set(OFFERED)|set(OPERATIONS))
    return {'since':start.isoformat(),'until_exclusive':end.isoformat(),
            'tools':{tool:{'completed_executions':counts[tool],'failed_or_unknown':failures[tool],
                           'explicit_downstream_uses':use[tool],'paths':dict(paths[tool])} for tool in sorted(expected|set(counts)|set(failures)|set(use))},
            'chains':chains,'qualification':'retained executions and explicit data references; novelty and biological validation are separate',
            'acceptance':'a tool needs an autonomous execution and downstream use in the two-day post-deploy window; zero or absent is not a pass'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--since',required=True);p.add_argument('--until',required=True)
    p.add_argument('--root',default=os.path.join(os.environ.get('SPARK_WORKSPACE',os.path.expanduser('~/.vintos/workspace')),'memory/chemistry-lab'))
    a=p.parse_args();print(json.dumps(report(a.root,a.since,a.until),indent=2))
