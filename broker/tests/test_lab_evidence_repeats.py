#!/usr/bin/env python3
"""Replay Oct 9 SLC26A11 rereads. All stores and senders are isolated."""
import contextlib, copy, json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
scratch = tempfile.TemporaryDirectory(prefix='lab-evidence-')
os.environ['HOME'] = scratch.name
os.environ['SPARK_WORKSPACE'] = scratch.name + '/workspace'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
def denied(*a, **k): raise AssertionError('external call forbidden')
socket.socket.connect = denied
import chemistry_lab as C
import lab_repeats as L
for name in ('CONFIG','STATE','NOTEBOOK','RECEIPTS','FAULTS','ROOT','LOCK','STOP','ELIOT_LOG'):
    assert getattr(C, name).startswith(scratch.name), name
assert L.LOOKUPS.startswith(scratch.name)
assert socket.socket.connect is denied
C._ask = denied
C._gather_material = Mock(return_value=True)
C.lab_context = Mock(return_value=('fixture', {'context_sha256':'fixture'}))
@contextlib.contextmanager
def admit(*a, **k): yield
settle = Mock(return_value=None)
sys.modules['compute_admission'] = types.SimpleNamespace(admit=admit)
sys.modules['chemistry_reading'] = types.SimpleNamespace(settle_one=settle)
sys.modules['chemistry_taste'] = types.SimpleNamespace(observe_reflection=Mock())
sys.modules['chemistry_frontier_bridge'] = types.SimpleNamespace(assess=Mock(return_value={
    'entry_id':'fixture','interest_score':0,'reason_for_score':'fixture',
    'flagged_for_next_lab_session':False,'truth_status':'fixture'}))
assert C._ask is denied and isinstance(C.lab_context, Mock) and isinstance(C._gather_material, Mock)
assert sys.modules['chemistry_reading'].settle_one is settle
C._ensure()
cfg = C.config(); cfg.update(enabled=True, evo2_enabled=False, forge_report_intake=None)
C._atomic(C.CONFIG, cfg)
# Compact record fields captured from Aegis's source_read on 2026-10-09.
protein = {'accession':'Q86WA9','length':606,'protein_name':'Sodium-independent sulfate anion transporter',
           'organism':'Homo sapiens','pdb_ids':[], 'found_by':'as_gene', 'partial_match':False}
paper = {'pmid':'24647542','title':'fixture paper', 'abstract':'fixture abstract'}
state = {'phase':'reflect', 'inquiry':{'question':'SLC26A11 topology?', 'source_query':{
    'source':'pubmed_abstracts','terms':['human SLC26A11','structure','STAS domain']}},
    'records':[protein], 'material':{'records':[]},
    'additional_source':{'receipt':{'source':'pubmed_abstracts','receipt_id':'first',
        'response_sha256':'query-dependent-one','records':[paper]}}}
C._reflect = Mock(return_value={'answers_question':'yes','factual_observation':'fixture', 'instrument_gap':''})
assert isinstance(C._reflect, Mock)
C._atomic(C.STATE,state)
assert C.tick()['kind'] == 'reflection'
assert C._reflect.call_count == 1
assert C._jsonl(C.NOTEBOOK)[-1]['evidence_sha256']
again = copy.deepcopy(state)
again['inquiry']['question'] = 'Where is its STAS boundary?'
again['inquiry']['source_query']['terms'] = ['SLC26A11','STAS domain','structure']
again['records'][0]['found_by'] = 'exact'
again['additional_source']['receipt'].update(receipt_id='second',response_sha256='different-query-hash')
C._atomic(C.STATE, again)
assert C.tick()['kind'] == 'browse_stale'
assert C._reflect.call_count == 1, 'duplicate must never reach reviewer'
assert C._load(C.STATE,{})['phase'] == 'orient'
assert C._jsonl(C.NOTEBOOK)[-1]['reason'] == 'same_evidence_already_reviewed'
# Route and order do not turn an already-read paper into new evidence.
rerouted = copy.deepcopy(state)
rerouted['material']['records'] = [paper]
rerouted['additional_source'] = {}
assert C.repeated_review(rerouted)
new = copy.deepcopy(state)
new['additional_source']['receipt']['records'].append({'pmid':'99999999','title':'new fixture','abstract':'new'})
assert not C.repeated_review(new), 'new paper must remain eligible'
changed = copy.deepcopy(state); changed['records'][0]['length'] = 607
assert not C.repeated_review(changed), 'updated source content must remain eligible'
instrument = copy.deepcopy(state); instrument['inquiry']['instrument_query'] = {'skill':'fold_read'}
assert not C.repeated_review(instrument), 'a new measurement is not a database reread'
plugin = copy.deepcopy(state); plugin['inquiry']['plugin_query'] = {'plugin':'tamarind'}
assert not C.repeated_review(plugin), 'other plugin results are not database rereads'
old = C._jsonl(C.NOTEBOOK)[0]; old['at'] = (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
Path(C.NOTEBOOK).write_text(json.dumps(old)+'\n')
assert not C.repeated_review(state), 'expiry permits a later reread'
print('PASS: duplicate tick skips reviewer; new evidence, instruments, expiry preserved')
scratch.cleanup()
