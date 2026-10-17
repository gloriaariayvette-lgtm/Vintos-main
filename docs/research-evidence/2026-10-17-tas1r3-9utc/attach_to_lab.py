#!/usr/bin/env python3
"""Attach this fixed, verified 9UTC data packet using installed Lab APIs. Does not deploy code.
Default: offline validation only. --apply: import the existing completed PDB source receipt and append research evidence.
No models, folding, state-machine turns, holds release, conclusions editing, or correspondence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from verify_packet import verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scripts',type=Path,default=Path.home()/'.vintos/workspace/scripts')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    packet=Path(__file__).resolve().parent
    verification=verify(packet,args.scripts)
    observation=json.loads((packet/'verified-record.json').read_text())
    key=hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest()
    if not args.apply:
        print(json.dumps({'applied':False,'verification':verification,'evidence_key':key},indent=2));return
    sys.path.insert(0,str(args.scripts))
    import chemistry_lab as lab
    from lab_sources import receipt
    notebook=lab._tail_jsonl(lab.NOTEBOOK,nbytes=32*1024*1024)
    question=observation['original_question']
    targets=[r for r in notebook if r.get('entry_id') in observation['linked_lab_entries']
             and ((r.get('coverage_check') or {}).get('original_question') or (r.get('inquiry') or {}).get('question'))==question]
    if not targets:raise ValueError('original investigation not found in bounded recent notebook; refusing unowned attachment')
    folder=Path(lab.ROOT)/'artifacts/reference'/('9UTC-TAS1R3-'+key[:12])
    marker=folder/'ingestion.json'
    if marker.exists():
        print(json.dumps({'already_attached':True,**json.loads(marker.read_text())},indent=2));return
    # The public retrieval was already completed with lab_sources.Sources. Import that exact receipt;
    # this is a data handoff, not another provider request and not an override of source cooldowns.
    raw_receipt=json.loads((packet/'lab-structure-receipt.json').read_text())
    unsigned=dict(raw_receipt); recorded_id=unsigned.pop('receipt_id')
    assert hashlib.sha256(json.dumps(unsigned,sort_keys=True).encode()).hexdigest()==recorded_id
    assert hashlib.sha256(json.dumps(raw_receipt['records'],sort_keys=True,allow_nan=False).encode()).hexdigest()==raw_receipt['response_sha256']
    expected_pdb_sha=next(x['sha256'] for x in observation['provenance'] if x['file']=='9UTC.pdb')
    analysis=receipt('pdb_coordinate_analysis',
        {'entry_id':'9UTC','accession':'Q7RTX0','author_chain':'B','source_receipt_id':raw_receipt['receipt_id']},
        [observation],metadata={'evidence':'derived_from_deposited_occupied_coordinates_and_archive_mapping',
            'evidence_key':key,'coordinate_sha256':expected_pdb_sha,'scope':'TAS1R3 coordinate availability and coverage; not affinity or mechanism validation',
            'linked_lab_entries':[r['entry_id'] for r in targets],'original_question_answered':False})
    # Text first: the existing recent-source projection exposes these facts inside its bounded excerpt.
    summary=('9UTC chain B is human TAS1R3/Q7RTX0: occupied native residues 22-356 and 366-556 (526 total), '
             '3.33 A cryo-EM. Native residues 21, 357-365 and 557-852 are sequence-only; 1-20 are outside the '
             'mapped construct. mNeonGreen is engineered sequence-only material. Sucralose binding is reported '
             'for TAS1R2, not established for TAS1R3. This corrects coordinate availability; the original '
             'TAS1R3/L-glutamate mechanism question remains unresolved.')
    note={'at':lab.now_iso(),'kind':'additional_source','entry_id':'SRC-TAS1R3-'+key[:16],
        'receipt_id':analysis['receipt_id'],'source_receipt_id':raw_receipt['receipt_id'],
        'source_accessions':['Q7RTX0','9UTC'],'source_summary':summary,
        'source_metadata':{'entry_id':'9UTC','author_chain':'B','accession':'Q7RTX0','evidence_key':key,
                           'linked_lab_entries':[r['entry_id'] for r in targets]},
        'question':question,'original_question':question,'original_question_sha256':observation['question_sha256'],
        'original_question_answered':False,'artifact':str(folder),'discovered_by':'Grok Bot',
        'truth_status':'verified_coordinate_availability_and_coverage_not_binding_or_mechanism_validation'}
    outcome={'attached':True,'at':note['at'],'evidence_key':key,'entry_id':note['entry_id'],
             'source_receipt_id':raw_receipt['receipt_id'],'analysis_receipt_id':analysis['receipt_id'],
             'source_receipt_origin':'completed bounded public retrieval using lab_sources.Sources on the Mac',
             'provider_requests_during_import':0,'source_throttle_modified':False,
             'original_question_sha256':observation['question_sha256'],'linked_lab_entries':[r['entry_id'] for r in targets],
             'artifact':str(folder),'deployed':False,'models_called':0,'folding_jobs':0,
             'prior_reflections_edited':False,'original_question_answered':False}
    with lab._locked():
        if marker.exists():
            print(json.dumps({'already_attached':True,**json.loads(marker.read_text())},indent=2));return
        folder.mkdir(parents=True,exist_ok=True)
        for name in list(json.loads((packet/'packet-sha256.json').read_text()))+['packet-sha256.json']:
            shutil.copyfile(packet/name,folder/name)
        recent_receipts=lab._tail_jsonl(str(Path(lab.ROOT)/'source-receipts.jsonl'),nbytes=8*1024*1024)
        if not any(r.get('receipt_id')==raw_receipt['receipt_id'] for r in recent_receipts):
            lab._append(str(Path(lab.ROOT)/'source-receipts.jsonl'),raw_receipt)
        lab._append(str(Path(lab.ROOT)/'source-receipts.jsonl'),analysis)
        lab._append(lab.NOTEBOOK,note)
        marker.write_text(json.dumps(outcome,indent=2)+'\n')
    # Existing readers must be able to see both the raw structure receipt and the attributed correction.
    assert lab._structure_cached('9UTC')['receipt']['receipt_id']==raw_receipt['receipt_id']
    assert any(r.get('entry_id')==note['entry_id'] for r in lab._tail_jsonl(lab.NOTEBOOK,nbytes=1024*1024))
    context,_=lab.lab_context()
    outcome['existing_lab_context_exposes_coverage']='9UTC' in context and '22-356' in context
    marker.write_text(json.dumps(outcome,indent=2)+'\n')
    print(json.dumps(outcome,indent=2))


if __name__=='__main__':main()
