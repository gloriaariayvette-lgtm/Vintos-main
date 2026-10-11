"""Saved-source, mocked-boundary replay. This does NOT measure Gemma quality."""
import contextlib, copy, io, json, os, pathlib, shutil, socket, subprocess, sys, tempfile, types, unittest
from unittest.mock import Mock, patch

scratch = tempfile.TemporaryDirectory(prefix='lab-productive-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name+'/workspace', VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a, **k): raise AssertionError('external operation forbidden')
socket.socket.connect = forbidden
socket.create_connection = forbidden
subprocess.Popen = forbidden
sys.path.insert(0, os.environ.get('LAB_REPLAY_SCRIPTS',str(pathlib.Path(__file__).resolve().parents[2]/'scripts')))
import chemistry_lab as C, lab_sources as S, lab_repeats as R
REAL_FRONTIER = R.frontier_step
C._ask = forbidden
C.urllib.request.urlopen = forbidden
S.open_request = forbidden
assert all(str(x).startswith(scratch.name) for x in (C.ROOT,C.STATE,C.NOTEBOOK,C.FAULTS,C.SPENT,C.RECEIPTS,R.LOOKUPS,R.SESSIONS))
assert C._ask is forbidden and socket.socket.connect is forbidden and subprocess.Popen is forbidden
fixtures = pathlib.Path(__file__).parent/'fixtures'
positive = json.loads((fixtures/'lab_oct10_coverage.json').read_text())
actual = json.loads((fixtures/'lab_oct10_productive.json').read_text())
receipts = json.loads((fixtures/'lab_oct10_productive_receipts.json').read_text())
modules = {
 'compute_admission':types.SimpleNamespace(admit=lambda *a,**k:contextlib.nullcontext()),
 'chemistry_reading':types.SimpleNamespace(settle_one=lambda **k:None),
 'chemistry_taste':types.SimpleNamespace(observe_reflection=lambda note:None),
 'chemistry_frontier_bridge':types.SimpleNamespace(assess=lambda *a,**k:{'entry_id':'offline','interest_score':0,'reason_for_score':'offline','flagged_for_next_lab_session':False,'truth_status':'offline'}),
 'forge_gaps':types.SimpleNamespace(judge=forbidden),
 'atelier_lab_lean':types.SimpleNamespace(today=lambda:None),
 'plugin_catalog':types.SimpleNamespace(prompt_instructions=lambda *a:''),
 'claude_connector_catalog':types.SimpleNamespace(prompt_instructions=lambda *a:''),
 'lab_genome_mining':types.SimpleNamespace(campaign_instructions=lambda:''),
 'lab_keepers':types.SimpleNamespace(block=lambda **k:''),
 'lab_asks':types.SimpleNamespace(block=lambda:''),
 'lab_instruments':types.SimpleNamespace(menu_block=lambda:'',run=forbidden),
}

class Productive(unittest.TestCase):
 def setUp(self):
  shutil.rmtree(C.WS, ignore_errors=True); C._ensure()
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  self.stack.enter_context(patch.dict(sys.modules,modules))
  self.cfg=dict(C.DEFAULTS,enabled=True,evo2_enabled=False,atlas_evo2_enabled=False,forge_report_intake=None)
  self.stack.enter_context(patch.object(C,'config',return_value=self.cfg))
  self.stack.enter_context(patch.object(C,'stop_requested',return_value=False))
  self.stack.enter_context(patch.object(C,'lab_context',return_value=('offline scientific context',{'context_sha256':'offline'})))
  self.stack.enter_context(patch.object(C,'atlas_turn_due',return_value=False))
  self.stack.enter_context(patch.object(C,'_existing_model_read',side_effect=lambda x:x))
  self.stack.enter_context(patch.object(R,'frontier_step',return_value=None))
  self.line={'id':'L-offline','question':'Offline chosen line','next_step':'Read available evidence'}
  self.lines=types.SimpleNamespace(pick=lambda:self.line,orient_text=lambda line:'',tests_block=lambda:'',get=lambda _:None,reflect_text=lambda _: '',after_reflection=lambda *a:'')
  self.stack.enter_context(patch.dict(sys.modules,{'lab_lines':self.lines}))
  self.stack.enter_context(patch.object(C,'dead_ends',return_value={'subjects':[],'questions':[],'count':0}))
  self.stack.enter_context(patch.object(C,'_embed_records',return_value={'embeddings':[]}))

 def browse_casr(self):
  raw=receipts['casr']['receipt']['records']
  with patch.object(C.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps({'results':raw}).encode())):
   return C._browse(positive['inquiry']['uniprot_query'],3)

 def test_actual_original_casr_end_to_end_cited_answer(self):
  self.line=None
  evidence=copy.deepcopy(positive['evidence'])
  source=types.SimpleNamespace(query=Mock(return_value=evidence['additional_source']),material=Mock(return_value={'records':evidence['LITERATURE'],'receipt_id':'saved-literature'}))
  calls=[]
  def model(system,prompt,**kw):
   calls.append(system)
   if 'Choose ONE' in prompt:return json.dumps(positive['inquiry'])
   if 'reading sourced' in system:return json.dumps({'answers_question':'no: residue coordinates are missing','factual_observation':'Reader incorrectly claims chemical coordination from 3.2 Å proximity and assigns the 2.1 Å Mg structure resolution to 5FBH','next_question':'Find residue coordinates'})
   if 'technical evidence-coverage' in system:return json.dumps(positive['checker_responses'][0])
   if 'Independently assess' in system:return json.dumps({'sufficient':True,'missing':[],'rationale':'The saved abstracts cover human receptor organization, its bilobed VFT and ligand coordination; the original question does not request residue coordinates.'})
   raise AssertionError(system)
  raw=receipts['casr']['receipt']['records']
  with patch.dict(sys.modules,{'chemistry_sources':source}),patch.object(C,'_ask',side_effect=model),patch.object(C.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps({'results':raw}).encode())):
   kinds=[]
   for _ in range(6):
    result=C.tick();self.assertTrue(result['ok'],result);kinds.append(result.get('kind'))
    if result.get('kind')=='reflection':break
  self.assertEqual(kinds,['inquiry','source_read','additional_source','protein_representation','reflection'])
  note=C._tail_jsonl(C.NOTEBOOK)[-1]
  self.assertEqual(note['inquiry']['question'],positive['inquiry']['question'])
  self.assertTrue(note['answers_question'].startswith('yes:'),note)
  self.assertIn('PMID 23856260',note['factual_observation'])
  self.assertIn('PMID 27746744',note['factual_observation'])
  self.assertTrue(note['coverage_check']['independent_sufficiency']['sufficient'])
  self.assertNotIn('Reader incorrectly',note['factual_observation'])
  self.assertNotIn('chemical coordination',note['factual_observation'])
  self.assertNotIn('2.1 Å',note['factual_observation'])
  self.assertNotIn('3.2 Å',note['factual_observation'])
  self.assertEqual(note['next_question'],'');self.assertEqual(note['missing_evidence'],'')
  self.assertEqual(note['evidence_status'],'answered')
  self.assertEqual(C._load(C.STATE,{})['phase'],'orient')
  self.assertEqual(len(calls),4)
  print('POSITIVE_SAVED_SOURCE_ANSWER',note['factual_observation'])

 def test_same_source_insufficient_original_remains_partial(self):
  q=copy.deepcopy(positive['inquiry']); q['question'] += ' Also provide a computed hydropathy profile.'
  obs=copy.deepcopy(positive['evidence']);obs['records']=self.browse_casr()['records']
  replies=[{'answers_question':'no: computed hydropathy profile is absent','line_status':'answered: everything'},positive['checker_responses'][0],{'sufficient':False,'missing':['computed hydropathy profile is absent'],'rationale':'Annotations and sequence do not compute a hydropathy profile.'}]
  with patch.object(C,'_ask',side_effect=[json.dumps(x) for x in replies]):result=C._reflect('',q,obs)
  self.assertTrue(result['answers_question'].startswith('no:'))
  self.assertEqual(result['evidence_status'],'partial');self.assertEqual(result['line_status'],'continue')
  self.assertIn('PMID 23856260',result['factual_observation'])
  self.assertIn('hydropathy',result['missing_evidence']);self.assertFalse(result['evidence_gap']['automatic_followup'])
  self.assertEqual(result['coverage_check']['original_question'],q['question'])

 def test_numeric_source_leaf_is_exactly_addressable(self):
  q={'question':'What organism and sequence length does UniProt report for Q16740?',
     'uniprot_query':'accession:Q16740'}
  observations={'records':[{'accession':'Q16740','organism':'Homo sapiens','length':277}]}
  verdict={'answered':False,'missing':['annotated domains'], 'supports':[
   {'requirement':'organism','address':'UniProt:Q16740/organism','quote':'Homo sapiens'},
   {'requirement':'sequence length','address':'UniProt:Q16740/length','quote':'277'}]}
  with patch.object(C,'_ask',return_value=json.dumps(verdict)):
   coverage=C._coverage_check(q,observations)
  self.assertFalse(coverage['answered'])
  self.assertNotEqual(coverage.get('assessment_status'),'incomplete')
  self.assertEqual({x['quote'] for x in coverage['supports']},{'Homo sapiens','277'})

 def test_actual_f430_not_identity_but_bibliography_not_mechanism(self):
  q=actual[0]['inquiry']; original=q['question']
  self.assertNotIn('F430',S.human_question_symbols(original))
  obs={'records':[],'additional_source':{'receipt':receipts['f430']['receipt']},'LITERATURE':[]}
  with patch.object(C,'_ask',side_effect=[json.dumps({'answers_question':'no: bibliography lacks coordination and transition-state evidence'}),json.dumps({'answered':False,'missing':['coordination and transition-state evidence absent'],'supports':[]})]) as model:
   result=C._reflect('',q,obs)
  self.assertEqual(model.call_count,0);self.assertTrue(result['answers_question'].startswith('no:'))
  self.assertIn('no substantive article evidence',result['answers_question'])
  self.assertNotIn('requested target',result['missing_evidence']);self.assertEqual(q['question'],original)

 def test_explicit_f430_constraints_survive(self):
  for question in ('gene:F430 cofactor binding','F430 gene and F430 cofactor','protein F430 cofactor binding'):
   self.assertIn('F430',S.human_question_symbols(question))
  q={'question':'Describe the F430 cofactor','uniprot_query':'gene:F430'}
  self.assertEqual(S.question_entity_context(q,[])['status'],'unresolved')
  self.assertEqual(S.human_question_symbols('Describe Ni-F430 coordination'),[])

 def test_wrong_species_and_mscl_still_rejected(self):
  for q in ({'question':'human MscL structure','uniprot_query':'protein_name:MscL AND organism_id:9606'},
            {'question':positive['inquiry']['question'],'uniprot_query':positive['inquiry']['uniprot_query']}):
   wrong={'accession':'Q9JLI6','protein_name':'Selenocysteine lyase','taxon_id':10090,'organism':'Mus musculus'}
   result=C._reflect('',q,{'records':[wrong]})
   self.assertTrue(result['answers_question'].startswith('no:'))

 def test_name_phrase_does_not_fuzzy_match_or_resolve_ambiguity(self):
  q=positive['inquiry'];rows=self.browse_casr()['records']
  self.assertEqual(S.question_entity_context(q,rows)['status'],'consistent')
  wrong=copy.deepcopy(rows[0]);wrong['protein_name']='Extracellular sodium-sensing receptor';wrong['protein_aliases']=[]
  self.assertEqual(S.question_entity_context(q,[wrong])['status'],'unresolved')
  second=copy.deepcopy(rows[0]);second['accession']='Q00001'
  self.assertEqual(S.question_entity_context(q,rows+[second])['status'],'unresolved')
  inhibitor=copy.deepcopy(rows[0]);inhibitor.update(accession='Q00001',protein_name='Calcium-sensing receptor inhibitor',protein_aliases=[],genes=[{'geneName':{'value':'OTHER'}}])
  self.assertEqual(S.question_entity_context(q,[inhibitor])['status'],'unresolved')
  bare=dict(q,question='What is the structural organization of the human calcium sensing receptor?')
  self.assertEqual(S.question_entity_context(bare,rows)['status'],'unresolved')
  greek={'question':'Which protein is supplied?','uniprot_query':'protein_name:"β-galactosidase protein"'}
  self.assertEqual(S.question_entity_context(greek,[{'protein_name':'α-galactosidase protein'}])['status'],'unresolved')

 def exhaust(self):
  q=copy.deepcopy(actual[2]['inquiry']);q.pop('refused',None)
  self.line={'id':'L-pendrin','question':q['question'],'next_step':'Compare isolated and full-length structures'}
  R.record(q)
  with patch.object(C,'_ask',return_value=json.dumps(q)),patch.object(C,'_strategy_change',return_value=None),patch.object(C,'_next_evidence_work',return_value=None):
   result=C.tick()
  self.assertEqual(result['kind'],'inquiry_refused')
  note=C._tail_jsonl(C.NOTEBOOK)[-1];self.assertIn('planning_scope',note['inquiry'])
  return note['inquiry']

 FRESH=(('7DTV','What does the cryo-EM structure 7DTV show about the calcium-bound active state of human CASR?'),
        ('5K5S','Which residues line the extracellular ligand pocket of human CASR in crystal structure 5K5S?'),
        ('7M3F','How are the two subunits of the human CASR homodimer arranged in the nanobody complex 7M3F?'),
        ('7DD5','Where do phosphate anions bind the inactive human CASR extracellular domain in 7DD5?'))
 def fresh(self):
  # distinct new work each time: an admitted proposal is itself a lookup that may not be repeated
  self.n=getattr(self,'n',-1)+1;entry,question=self.FRESH[self.n]
  return dict(positive['inquiry'],question=question,source_query={'source':'pdb','entry_id':entry,'operation':'structure_evidence'})

 def yielded_pass(self,held):
  # 11 October from 07:21 UTC every line was held and every pass logged evidence_wait: the Lab stood still for
  # over an hour. A held line keeps its hold (nothing on it is asked or retrieved again) but does not take the
  # pass; the pass plans free curiosity, which here chooses unrelated work.
  new=self.fresh()
  with patch.object(C,'_ask',return_value=json.dumps(new)) as model,patch.object(C,'_browse',side_effect=forbidden),patch.object(C,'_strategy_change',return_value=None),patch.object(C,'_next_evidence_work',return_value=None):
   result=C.tick()
  self.assertEqual(result.get('kind'),'inquiry',(result,C._tail_jsonl(C.NOTEBOOK)[-1].get('why')));self.assertEqual(model.call_count,1)
  admitted=C._load(C.STATE,{})['inquiry']
  self.assertEqual(admitted['question'],new['question']);self.assertNotEqual(admitted['question'],held['question'])
  self.assertIsNone(admitted['planning_scope']['line'])
  with patch.object(C,'_strategy_change',return_value=None):
   self.assertTrue(C._planning_hold(held['planning_scope'],R,{'subjects':[]},None)['planning_wait'])
  C._atomic(C.STATE,{'phase':'orient'})   # that free work's cycle is done; the next pass orients again

 def test_same_exhausted_assignment_waits_and_yields_its_pass(self):
  q=self.exhaust()
  for _ in range(2):self.yielded_pass(q)

 def test_unrelated_new_assignment_proceeds(self):
  self.exhaust();self.line={'id':'L-casr','question':positive['inquiry']['question'],'next_step':'Read saved receptor evidence'}
  with patch.object(C,'_ask',return_value=json.dumps(positive['inquiry'])) as model:
   self.assertEqual(C.tick()['kind'],'inquiry')
  self.assertEqual(model.call_count,1)

 def test_free_wait_does_not_block_new_unrelated_input(self):
  q=copy.deepcopy(actual[2]['inquiry']);q.pop('refused',None);self.line=None;R.record(q)
  with patch.object(C,'_ask',return_value=json.dumps(q)),patch.object(C,'_strategy_change',return_value=None),patch.object(C,'_next_evidence_work',return_value=None):
   self.assertEqual(C.tick()['kind'],'inquiry_refused')
  # A repeat refusal does not hold free curiosity (it has no assignment to exhaust): the next pass plans again.
  with patch.object(C,'_ask',return_value=json.dumps(self.fresh())) as model,patch.object(C,'_strategy_change',return_value=None):
   self.assertEqual(C.tick()['kind'],'inquiry')
  self.assertEqual(model.call_count,1)
  C._atomic(C.STATE,{'phase':'orient'})
  with patch.object(C,'_ask',return_value=json.dumps(positive['inquiry'])) as model:
   inquiry=C._orient('New unrelated CASR question with saved supporting abstracts')
  self.assertNotIn('refused',inquiry);self.assertEqual(model.call_count,1)

 def test_changed_relevant_evidence_reopens_but_receipt_time_does_not(self):
  q=self.exhaust();scope=q['planning_scope']
  path=os.path.join(C.ROOT,'source-receipts.jsonl')
  C._append(path,{'records':[{'accession':'UNRELATED','value':'new'}]})
  with patch.object(C,'_strategy_change',return_value=None):
   self.assertTrue(C._planning_hold(scope,R,{'subjects':[]},None)['planning_wait'])
   C._append(path,{'records':[{'accession':'O43511','pdb_ids':['1ABC']}]})
   self.assertIsNone(C._planning_hold(scope,R,{'subjects':[]},None))
  revision=C._planning_evidence(q)
  C._append(path,{'retrieved_at':'new time','records':[{'accession':'O43511','pdb_ids':['1ABC']}]})
  self.assertEqual(revision,C._planning_evidence(q))
  C._append(path,{'records':[{'accession':'O43511','pdb_ids':['1ABC'],'retrieved_at':'later','receipt_id':'new-id','metadata':{'timestamp':'later'}}]})
  self.assertEqual(revision,C._planning_evidence(q))
  C._append(path,{'records':[{'accession':'OTHER','description':'STAS domain Pendrin protein_name:PENDRIN'}]})
  self.assertEqual(revision,C._planning_evidence(q))
  C._append(path,{'records':[{'accession':'UNRELATED','value':'another'}, {'accession':'O43511','pdb_ids':['1ABC']}]})
  self.assertEqual(revision,C._planning_evidence(q))

 def test_viable_unread_route_reopens_without_planner(self):
  q=self.exhaust();new=dict(q,source_query={'source':'interpro','accession':'O43511'})
  with patch.object(C,'_strategy_change',return_value=new),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_ask',side_effect=forbidden):
   self.assertEqual(C.tick()['kind'],'inquiry')
  admitted=C._load(C.STATE,{})['inquiry']
  self.assertNotIn('refused',admitted);self.assertEqual(admitted['question'],q['question'])

 def test_coverage_deferred_assignment_yields_to_unrelated_actionable_work(self):
  q=self.exhaust();q['coverage_deferred']=True
  C._append(C.NOTEBOOK,{'kind':'reflection','inquiry':q,'coverage_deferred':True})
  alternate={'question':'Read unrelated source','source_query':{'source':'interpro','accession':'P35523'},
             'planning_scope':{'stale':True},'planning_evidence':'stale'}
  with patch.object(C,'_strategy_change',return_value=None),patch.object(C,'_next_evidence_work',return_value=alternate),patch.object(C,'_held_to_plan',return_value=(alternate,{})) as gate,patch.object(C,'_ask',side_effect=forbidden):
   result=C._orient('offline scientific context')
  self.assertEqual(result['question'],alternate['question']);gate.assert_called_once()
  self.assertEqual(result['planning_scope'],q['planning_scope'])
  self.assertEqual(result['planning_evidence'],C._planning_evidence(result))
  self.assertEqual(alternate['planning_scope'],{'stale':True})
  C._append(os.path.join(C.ROOT,'source-receipts.jsonl'),{'records':[{'accession':'O43511','new_distinct_fact':'changed evidence'}]})
  with patch.object(C,'_strategy_change',return_value=None):
   self.assertIsNone(C._planning_hold(q['planning_scope'],R,{'subjects':[]},None))

 def test_context_expansion_resumes_preserved_coverage_before_sourced_fallback(self):
  self.line=None
  q=C._inquiry({'question':'What does the saved literature establish about P12345?',
                'uniprot_query':'accession:P12345'})
  observations=None
  for size in range(24000,34001,250):
   candidate={'records':[{'accession':'P12345','function':'E'*size}],
              'LITERATURE':[{'pmid':'123','abstract':'Saved literature evidence.'}]}
   prepared=C._coverage_request(q,candidate)
   totals=[C._coverage_budget(prepared[3])['conservative_total'],
           C._coverage_budget(C._coverage_sufficiency_request(q,prepared[0]))['conservative_total']]
   if max(totals)>32000 and max(totals)<=35000:
    observations=candidate;break
  self.assertIsNotNone(observations)
  with patch.object(C,'COVERAGE_CONTEXT_BUDGET',32000),patch.object(C,'_ask',side_effect=forbidden):
   deferred=C._coverage_check(q,observations)
  self.assertTrue(deferred['coverage_deferred'])
  held=dict(q,refused=deferred['missing_evidence'],evidence_status='insufficient',coverage_deferred=True,
            planning_evidence=C._planning_evidence(q))
  C._append(C.NOTEBOOK,dict(deferred,kind='reflection',inquiry=held))
  C._append(C.NOTEBOOK,{'kind':'evidence_wait','inquiry':held,'why':held['refused']})
  with patch.object(C,'_next_assigned_archive_step',return_value=None),patch.object(C,'_next_assigned_model_step',return_value=None),patch.object(C,'_next_sourced_record',side_effect=forbidden),patch.object(C,'_ask',side_effect=forbidden):
   resumed=C._orient('offline scientific context')
  self.assertEqual(resumed['assignment_resolution']['reason'],'deferred_coverage_now_fits')
  payload,digest=C._coverage_snapshot(resumed['coverage_retry_snapshot'])
  self.assertEqual(payload['observations'],observations);self.assertEqual(digest,resumed['coverage_retry_sha256'])
  with patch.object(C,'_orient',return_value=resumed):
   result=C.tick()
  self.assertEqual(result['next_phase'],'reflect')
  state=C._load(C.STATE,{})
  self.assertEqual(state['coverage_retry_observations'],observations)
  self.assertEqual(state['records'],observations['records'])
  answer={'answers_question':'yes: saved evidence','factual_observation':'Saved literature evidence. [PMID 123]',
          'speculative_reading':'','next_question':'','instrument_gap':'','line_status':'continue',
          'evidence_status':'answered','missing_evidence':'','truth_status':'saved_evidence_test'}
  with patch.object(C,'repeated_review',return_value=True),patch.object(C,'_gather_material',return_value=None),patch.object(C,'_reflect',return_value=answer) as reader:
   result=C.tick()
  self.assertTrue(result.get('ok'),result)
  self.assertEqual(result['kind'],'reflection');self.assertEqual(result['next_phase'],'orient')
  reader.assert_called_once_with('offline scientific context',resumed,observations)
  note=C._tail_jsonl(C.NOTEBOOK)[-1]
  self.assertEqual(note['coverage_retry_sha256'],digest)
  self.assertNotIn('coverage_retry_observations',C._load(C.STATE,{}))

 def test_post_refusal_alternate_admission_refreshes_scope(self):
  q=self.exhaust()
  alternate={'question':'Unrelated actionable work','planning_scope':{'stale':True},'planning_evidence':'stale'}
  with patch.object(C,'_next_evidence_work',return_value=alternate),patch.object(C,'_held_to_plan',return_value=(alternate,{})),patch.object(C,'_ask',side_effect=forbidden):
   result=C._orient('offline scientific context')
  self.assertEqual(result['planning_scope'],q['planning_scope'])
  self.assertEqual(result['planning_evidence'],C._planning_evidence(result))
  self.assertEqual(alternate['planning_scope'],{'stale':True})

 def test_waiting_pass_uses_an_unread_exact_sourced_record(self):
  self.line=None
  records=[
   {'accession':'P21579','protein_name':'Synaptotagmin-1','organism':'Homo sapiens'},
   {'accession':'Q16740','protein_name':'ATP-dependent Clp protease proteolytic subunit, mitochondrial',
    'organism':'Homo sapiens'}]
  C._append(C.NOTEBOOK,{'kind':'source_read','source':'UniProtKB REST','records':records})
  used=C._inquiry({'question':'What does the curated UniProt record for Synaptotagmin-1 (P21579) in Homo sapiens establish about its sequence length, annotated domains, and membrane topology?',
                   'uniprot_query':'accession:P21579'})
  C._append(C.NOTEBOOK,{'kind':'reflection','inquiry':used,'source_accessions':['P21579'],
                        'evidence_status':'answered','factual_observation':'saved test review'})
  C._append(C.NOTEBOOK,{'kind':'evidence_wait','inquiry':{'question':'held'},'why':'no eligible proposal'})
  with patch.object(C,'_next_assigned_archive_step',return_value=None),patch.object(C,'_next_assigned_model_step',return_value=None),patch.object(C,'_next_evidence_work',return_value=None),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_ask',side_effect=forbidden):
   inquiry=C._orient('offline scientific context')
  self.assertEqual(inquiry['uniprot_query'],'accession:Q16740')
  self.assertEqual(inquiry['material_terms'],[])
  self.assertNotIn('Homo sapiens',inquiry['question'])
  self.assertEqual(inquiry['assignment_resolution']['reason'],'exact_previously_sourced_record')
  self.assertEqual(inquiry['planning_scope'],{'sourced_fallback':'Q16740'})

 def test_waiting_pass_indexes_sourced_records_outside_recent_notebook_tail(self):
  self.line=None
  C._append(C.NOTEBOOK,{'kind':'source_read','source':'UniProtKB REST','records':[
   {'accession':'P02792','protein_name':'Ferritin light chain','organism':'Homo sapiens'}]})
  R.record(C._inquiry({'question':'Prior unfinished review of P02792','uniprot_query':'accession:P02792'}))
  C._append(C.NOTEBOOK,{'kind':'old_context','payload':'x'*(9*1024*1024)})
  C._append(C.NOTEBOOK,{'kind':'evidence_wait','inquiry':{'question':'held'},'why':'no eligible proposal'})
  self.assertFalse(any(row.get('kind')=='source_read' for row in C._tail_jsonl(C.NOTEBOOK,nbytes=8*1024*1024)))
  indexed_size=os.path.getsize(C.NOTEBOOK)
  with patch.object(C,'_next_assigned_archive_step',return_value=None),patch.object(C,'_next_assigned_model_step',return_value=None),patch.object(C,'_next_evidence_work',return_value=None),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_browse',side_effect=forbidden),patch.object(C,'_ask',side_effect=forbidden):
   result=C.tick()
  self.assertEqual(result['next_phase'],'reflect')
  state=C._load(C.STATE,{})
  self.assertEqual(state['inquiry']['uniprot_query'],'accession:P02792')
  self.assertEqual(state['records'][0]['accession'],'P02792')
  index=C._load(os.path.join(C.ROOT,'sourced-record-index.json'),{})
  self.assertEqual(index['offset'],indexed_size)
  self.assertEqual(index['candidates'][0]['accession'],'P02792')
  self.assertEqual(index['candidates'][0]['record']['protein_name'],'Ferritin light chain')

 def test_free_pass_uses_unread_saved_record_before_calling_planner(self):
  self.line=None
  C._append(C.NOTEBOOK,{'kind':'source_read','source':'UniProtKB REST','records':[
   {'accession':'Q8N4E7','protein_name':'Ferritin, mitochondrial','organism':'Homo sapiens'}]})
  with patch.object(C,'_next_assigned_archive_step',return_value=None),patch.object(C,'_next_assigned_model_step',return_value=None),patch.object(C,'_next_evidence_work',return_value=None),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_ask',side_effect=forbidden):
   inquiry=C._orient('offline scientific context')
  self.assertEqual(inquiry['uniprot_query'],'accession:Q8N4E7')
  self.assertEqual(inquiry['assignment_resolution']['reason'],'exact_previously_sourced_record')

 def test_exact_sourced_record_browse_goes_directly_to_reflection(self):
  inquiry=C._inquiry({'question':'What does the curated UniProt record for a protein (Q16740) establish about its organism, sequence length, annotated domains, and membrane topology?',
                      'uniprot_query':'accession:Q16740'})
  inquiry['assignment_resolution']={'reason':'exact_previously_sourced_record','accession':'Q16740'}
  C._atomic(C.STATE,{'phase':'browse','inquiry':inquiry})
  record={'accession':'Q16740','protein_name':'Protein','organism':'Homo sapiens','taxon_id':9606,
          'length':277,'domains':[],'topology':[],'topology_summary':'','pdb_ids':['1TG6'],'sequence':'A'*277}
  browse={'records':[record],'source_receipt':None,'requested_query':'accession:Q16740',
          'executed_query':'accession:Q16740','fallback_reason':None}
  with patch.object(C,'_browse',return_value=browse),patch.object(C,'_embed_records',side_effect=forbidden):
   result=C.tick()
  self.assertEqual(result['kind'],'source_read')
  self.assertEqual(result['next_phase'],'reflect')
  state=C._load(C.STATE,{})
  self.assertEqual(state['phase'],'reflect')
  self.assertIsNone(state['inquiry']['source_query'])

 def test_recovered_route_actual_overflow_next_cycle_waits_without_generation(self):
  old=self.exhaust()
  def recover(inquiry,repeats):return dict(inquiry,source_query={'source':'interpro','accession':'O43511'})
  with patch.object(C,'_strategy_change',side_effect=recover),patch.object(C,'_next_evidence_work',return_value=None),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_ask',side_effect=forbidden):
   self.assertEqual(C.tick()['kind'],'inquiry')
  state=C._load(C.STATE,{})
  admitted=state['inquiry']
  self.assertEqual(admitted['planning_scope'],old['planning_scope'])
  self.assertEqual(admitted['planning_evidence'],C._planning_evidence(admitted))
  self.assertNotIn('refused',admitted)
  # Keep the admitted inquiry verbatim: no manually seeded planning metadata.
  state.update(phase='reflect',records=[{'accession':'O43511','protein_name':'Pendrin','taxon_id':9606,
               'organism':'Homo sapiens','genes':[{'geneName':{'value':'SLC26A4'}}]}],
               material={'records':[{'pmid':'overflow','abstract':'Distinct saved evidence '*4000}]})
  C._atomic(C.STATE,state)
  with patch.object(C,'_gather_material',return_value=None),patch.object(C,'_ask',side_effect=forbidden):
   self.assertEqual(C.tick()['kind'],'reflection')
  note=C._tail_jsonl(C.NOTEBOOK)[-1]
  self.assertTrue(note['coverage_deferred'],note)
  self.assertEqual(note['inquiry']['planning_scope'],old['planning_scope'])
  self.assertTrue(pathlib.Path(note['coverage_snapshot']).is_file())
  # The deferred line is not generated again while its evidence is unchanged; the passes go to other work.
  for _ in range(2):self.yielded_pass(note['inquiry'])

 def test_oversize_reflection_tick_persists_hold_and_returns_to_orient(self):
  old=self.exhaust();q={'question':'What does the supplied evidence establish?',
                       'planning_scope':old['planning_scope']}
  self.cfg['evo2_enabled']=True
  C._atomic(C.STATE,{'phase':'reflect','inquiry':q,'records':[],
                   'material':{'records':[{'pmid':'overflow','abstract':'Full saved distinct evidence '*4000}]}})
  with patch.object(C,'_gather_material',return_value=None),patch.object(C,'_ask',side_effect=forbidden):
   result=C.tick()
  self.assertEqual(result['kind'],'reflection',result)
  note=C._tail_jsonl(C.NOTEBOOK)[-1]
  self.assertTrue(note['coverage_deferred']);self.assertTrue(note['inquiry']['coverage_deferred'])
  self.assertEqual(note['truth_status'],'incomplete_context_budget_no_scientific_adjudication')
  self.assertEqual(note['evidence_status'],'deferred')
  self.assertEqual(C._load(C.STATE,{})['phase'],'orient')
  with patch.object(C,'_strategy_change',return_value=None):
   self.assertTrue(C._planning_hold(q['planning_scope'],R,{'subjects':[]},None)['planning_wait'])

 def test_route_reopens_after_a_wait_for_ordinary_and_frontier_assignment(self):
  for frontier in (False,True):
   shutil.rmtree(C.WS,ignore_errors=True);C._ensure()
   question=actual[2]['inquiry']['question']
   step={'session_id':'offline-wait','lens':'offline','at':'2026-10-10','left':6,'subjects':['O43511'],'next_question':question} if frontier else None
   with patch.object(R,'frontier_step',return_value=step):
    q=self.exhaust()
    if frontier:
     # The frontier session's plan is its budgeted cycles; it waits there, counted against that budget.
     with patch.object(C,'_ask',side_effect=forbidden),patch.object(C,'_strategy_change',return_value=None):
      self.assertEqual(C.tick()['kind'],'evidence_wait')
     self.assertTrue(C._tail_jsonl(C.NOTEBOOK)[-1]['inquiry']['planning_wait'])
    else:
     self.yielded_pass(q)
    # Production _strategy_change copies the last waiting inquiry, not the
    # pre-wait value. Preserve that shape so stale flags cannot hide in tests.
    def recovered(old,repeats):return dict(old,source_query={'source':'interpro','accession':'O43511'})
    with patch.object(C,'_strategy_change',side_effect=recovered),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}),patch.object(C,'_ask',side_effect=forbidden):
     result=C.tick();self.assertEqual(result.get('kind'),'inquiry',result)
    admitted=C._load(C.STATE,{})['inquiry']
    self.assertNotIn('planning_wait',admitted);self.assertNotIn('refused',admitted)
    self.assertEqual(admitted['question'],q['question'])

 def test_frontier_waiting_does_not_pin_other_work_forever(self):
  from datetime import datetime,timezone,timedelta
  q=copy.deepcopy(actual[2]['inquiry']);q.pop('refused',None)
  now=datetime.now(timezone.utc)
  R.record(q,now=now-timedelta(minutes=1))
  C._append(R.SESSIONS,{'at':(now-timedelta(seconds=1)).isoformat(),'session_id':'offline-session','state':'completed',
                       'reading':{'next_question':q['question']},'lens':'offline'})
  with patch.object(R,'frontier_step',side_effect=REAL_FRONTIER),patch.object(C,'_strategy_change',return_value=None),patch.object(C,'_next_evidence_work',return_value=None):
   with patch.object(C,'_ask',return_value=json.dumps(q)):
    self.assertEqual(C.tick()['kind'],'inquiry_refused')
   with patch.object(C,'_ask',side_effect=forbidden):
    for _ in range(R.FRONTIER_CYCLES-1):self.assertEqual(C.tick()['kind'],'evidence_wait')
   self.assertIsNone(R.frontier_step())

 def test_recovered_route_still_requires_identity_and_question_suitability(self):
  q=self.exhaust();new=dict(q,source_query={'source':'interpro','accession':'O43511'})
  with patch.object(C,'_strategy_change',return_value=new),patch.object(C,'_ground_inquiry',return_value={'status':'unresolved','symbol':'SLC26A4','receipt_ids':['offline'], 'reason':'target identity unresolved'}) as ground,patch.object(C,'_ask',side_effect=forbidden):
   self.assertEqual(C.tick()['kind'],'inquiry_refused')
  ground.assert_called_once()
  self.assertIn('target identity unresolved',C._tail_jsonl(C.NOTEBOOK)[-1]['why'])
  self.assertIsNone(C._strategy_change({'question':'Which regulatory expression effect is measured?'},R))

 def test_scope_diagnostic_preserves_original_question(self):
  q=C._inquiry({'question':'What is human MscL structure?','uniprot_query':'protein_name:MscL AND organism_id:9606'})
  C._atomic(C.STATE,{'phase':'browse','inquiry':q})
  wrong={'accession':'Q9JLI6','protein_name':'Selenocysteine lyase','taxon_id':10090,'organism':'Mus musculus'}
  reply={'records':[wrong],'requested_query':q['uniprot_query'],'executed_query':'MscL','fallback_reason':None,'scope_resolution':{'requested_taxonomy_id':'9606'}}
  with patch.object(C,'_browse',return_value=reply):self.assertEqual(C.tick()['kind'],'source_read')
  after=C._load(C.STATE,{})['inquiry']
  self.assertEqual(after['question'],q['question']);self.assertEqual(after['uniprot_query'],q['uniprot_query'])
  self.assertTrue(C._reflect('',after,{'records':[wrong]})['answers_question'].startswith('no:'))

if __name__=='__main__':unittest.main(verbosity=2)
