#!/usr/bin/env python3
"""Ordinary Lab ticks against real sources in an operator-created scratch workspace.

Run under a read-only-root OS sandbox. This validates mechanics, never the
post-deploy two-day autonomy requirement. No sender, hosted inference, model
reload or live Mac bench call is available to this validation process.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--turns',type=int,default=12);a=p.parse_args()
    workspace=Path(os.environ['SPARK_WORKSPACE']).resolve()
    home=Path.home().resolve()
    if 'lab-tools-review-' not in str(workspace) or workspace==Path('/home/gloria/.vintos/workspace'):
        raise RuntimeError('explicit review scratch required')
    if not home.is_relative_to(workspace.parent):raise RuntimeError('scratch HOME required')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import chemistry_lab as lab
    import lab_investigations as investigations
    import plugin_gateway
    import chemistry_mac
    import chemistry_evo2
    def blocked(*a,**k):raise RuntimeError('not available in this scratch validation: live/paid side effect')
    chemistry_mac.request=blocked;chemistry_mac._with_gemma_unloaded=blocked
    chemistry_evo2._lms=blocked
    plugin_gateway._send=blocked
    cfg={'enabled':True,'forge_report_intake':False,'divergence_enabled':False,'campaigns':False,
         'allow_public_database_reads':True,'evo2_enabled':False,'atlas_evo2_enabled':False,
         'coverage_context_tokens':24576,'coverage_tokens_per_byte':0.4231,'cadence_version':3,'divergence_version':2}
    lab._atomic(lab.CONFIG,cfg)
    Path(lab.WS,'SOUL.md').write_text('Scratch validation of an investigation on human hemoglobin alpha (P69905): '
        'measure whether its source-defined chain has whole-chain representation coverage and where its annotated globin domain lies. '
        'Use computed outputs and reference annotations; this validation is not a novel biological finding. '
        'Choose the next available tool yourself from the result of the prior step. Prefer exact stored input references.')
    if not Path(investigations._path('investigations.json')).exists():
        lab._atomic(investigations._path('investigations.json'),{'investigations':[{
            'id':'I-scratch-validation','opened_at':lab.now_iso(),'state':'open','line_id':None,
            'question':'For human hemoglobin alpha (P69905), do UniProt and independent InterPro globin-domain intervals agree when mapped onto the complete chain represented by the local sequence model?',
            'prediction':'The two sources will overlap on most of the globin interval, and the computed representation will cover the complete retrieved chain; coordinate disagreement or unrepresented residues would refute this.',
            'plan':[],'steps':[],'origin':'operator_scratch_validation'}]})
    menu=investigations._menu
    def available():
        out=menu();out['connectors']={k:v for k,v in out['connectors'].items() if k=='nvmolkit'}
        out['account_connectors']='Unavailable in this scratch process; account policies remain unchanged.'
        for key in ('experiments','genome','regulatory_genome','campaign','protein_design_mcp','native'):
            out.pop(key,None)
        out['instruments']='Local reference_compare and fold_read on retained models; no live relay in this scratch process.'
        return out
    investigations._menu=available
    # Tokens still come from the installed local planner. No forced tool choice or mocked result.
    for i in range(a.turns):
        result=lab.tick();print(json.dumps({'turn':i,**result}),flush=True)
        if result.get('state')=='held_fault':print(json.dumps(lab._tail_jsonl(lab.FAULTS)[-1:]),flush=True)
        data=lab._load(investigations._path('investigations.json'),{'investigations':[]})
        for inv in data['investigations']:
            tools={s.get('tool') for s in inv.get('steps',[]) if s.get('state')=='completed'}
            links=[s for s in inv.get('steps',[]) if s.get('state')=='completed' and s.get('input_refs')]
            print(json.dumps({'investigation':inv['id'],'tools':sorted(str(x) for x in tools),
                              'steps':[{'id':s['id'],'state':s['state'],'tool':s.get('tool'),'input_refs':s.get('input_refs'),
                                        'error':s.get('error')} for s in inv.get('steps',[])]}),flush=True)
            by_id={step['id']:step for step in inv.get('steps',[]) if step.get('state')=='completed'}
            def chain(step,seen=()):
                own=step.get('tool')
                if own in ('reflect','read_output','schema','genome_reflect'):own=None
                current=seen+((own,) if own else ())
                best=len(set(current))
                for ref in step.get('input_refs') or []:
                    if ref.get('step') in by_id:best=max(best,chain(by_id[ref['step']],current))
                return best
            if any(chain(step)>=3 for step in by_id.values()):
                print(json.dumps({'acceptance':'three distinct tools on a retained dataflow path','investigation':inv['id']}),flush=True)
                return 0
        if result.get('state')=='waiting_for_source':time.sleep(2)
    return 1


if __name__=='__main__':raise SystemExit(main())
