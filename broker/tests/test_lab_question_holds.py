"""Replay the saved CFTR hold through the ordinary selector and daemon ticks, fully offline."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_query_perimeter import Perimeter, C, REPO, forbidden, NET
from pathlib import Path
import contextlib, copy, hashlib, json, sys
from unittest.mock import patch
import unittest

SNAPSHOT = REPO/'broker/tests/fixtures/cftr_coverage_deferred_20261011.json'
QUESTION = 'What are the structural features of the CFTR regulatory domain (R-domain) and how does its interaction with the A-kinase anchoring protein (AKAP) influence the phosphorylation-dependent gating of the chloride channel?'
SECOND = {'question':'How does MscL gate under membrane tension?', 'uniprot_query':'gene:mscL', 'source_query':None}
THIRD = {'question':'Which residues coordinate calcium in calmodulin?', 'uniprot_query':'gene:calM', 'source_query':None}

class QuestionHolds(Perimeter):
    def setUp(self):
        super().setUp()
        self.snapshot=json.loads(SNAPSHOT.read_text())
        self.cftr=copy.deepcopy(self.snapshot['inquiry'])
        self.assertEqual(self.cftr['question'], QUESTION)
        self.context='offline context'
        self.free={'line':None,'frontier':None,'lean':None,'atlas':False,
                   'context_sha256':hashlib.sha256(self.context.encode()).hexdigest()}
        self.cftr['planning_scope']=self.free
        self.hold(self.cftr)
        self.stack.enter_context(patch.object(C, '_strategy_change', return_value=None))
        self.stack.enter_context(patch.object(C, '_next_evidence_work', return_value=None))
        # Keep real repeat helpers, but isolate this ownership gate from the separate executed-lookup ledger.
        import lab_repeats
        self.stack.enter_context(patch.object(lab_repeats, 'repeat', return_value=''))
        self.stack.enter_context(patch.object(C, '_browse', side_effect=forbidden))

    def hold(self, inquiry):
        held=dict(inquiry, refused='coverage deferred: full original question and evidence exceed context budget',
                  evidence_status='insufficient', coverage_deferred=True,
                  planning_evidence=C._planning_evidence(inquiry))
        C._append(C.NOTEBOOK, {'kind':'reflection','inquiry':held,'coverage_deferred':True})
        return held

    def test_selector_executes_unrelated_work_then_advances(self):
        # Every phase is tick(), including _orient and _held_to_plan. Only external
        # science/model boundaries are fixtures; this is not live research proof.
        record={'accession':'P0A742','protein_name':'Large-conductance mechanosensitive channel',
                'sequence':'MAAAA','gene_names':['mscL'],'organism':'Escherichia coli',
                'function':'Responds to membrane tension.'}
        browse={'records':[record],'requested_query':'gene:mscL','executed_query':'gene:mscL',
                'fallback_reason':None,'source_receipt':{'receipt_id':'offline-mscl','records':[record]}}
        reflection={'answers_question':'partial: the record establishes a tension-responsive channel, not the full mechanism',
                    'factual_observation':'Responds to membrane tension. [P0A742]',
                    'missing_evidence':'Gating intermediates are absent from this fixture.',
                    'original_question':SECOND['question'],'next_question':'','instrument_gap':'',
                    'truth_status':'offline_fixture_partial','line_status':'continue'}
        with patch.object(C,'_ask',side_effect=[json.dumps(SECOND),json.dumps(THIRD)]), \
             patch.object(C,'_browse',return_value=browse) as read, \
             patch.object(C,'resolve_taxa',side_effect=lambda query,*a,**k:(query,None)), \
             patch.object(C,'_structure_followup',side_effect=lambda inquiry,records:inquiry), \
             patch.object(C,'_embed_records',return_value={'embeddings':[]}), \
             patch.object(C,'_write_collision_adapter',return_value=[]), \
             patch.object(C,'_gather_material',return_value=False), \
             patch.object(C,'_reflect',return_value=reflection) as review:
            for kind in ('inquiry','source_read','protein_representation','reflection'):
                result=C.tick();self.assertEqual(result.get('kind'),kind,result)
            note=C._tail_jsonl(C.NOTEBOOK)[-1]
            self.assertEqual(note['inquiry']['question'],SECOND['question'])
            self.assertEqual(note['original_question'],SECOND['question'])
            self.assertIn('P0A742',note['source_accessions'])
            self.assertIn('[P0A742]',note['factual_observation'])
            self.assertEqual(C.tick()['kind'],'inquiry')
            self.assertEqual(C._load(C.STATE,{})['inquiry']['question'],THIRD['question'])
            self.assertEqual(read.call_count,1);self.assertEqual(review.call_count,1)
        self.assertIsNotNone(C._held_question(self.cftr))
        self.assertEqual(NET,[])

    def test_legacy_hold_survives_notebook_tail_rollover(self):
        self.assertIsNotNone(C._held_question(self.cftr))
        C._append(C.NOTEBOOK,{'kind':'unrelated','payload':'x'*(2*1024*1024+1)})
        self.assertIsNotNone(C._held_question(self.cftr))
        with patch.object(C,'_ask',return_value=json.dumps(self.cftr)):
            self.assertEqual(C.tick()['kind'],'evidence_wait')
        self.assertEqual(NET,[])

    def test_corrupt_saved_hold_does_not_release_or_run_work(self):
        self.assertIsNotNone(C._held_question(self.cftr))
        Path(C.ROOT,'question-holds.json').write_text('{broken')
        with patch.object(C,'_ask',side_effect=forbidden):
            result=C.tick()
        self.assertNotEqual(result.get('kind'),'inquiry')
        self.assertNotIn('inquiry',C._load(C.STATE,{}))
        self.assertEqual(NET,[])

    def test_saved_snapshot_stays_complete_and_guard_unchanged(self):
        self.assertEqual(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
                         '79a1677b0882af9a797671f730f1c7724f032a35bc66191932410fd957e0434a')
        self.assertEqual(self.snapshot['original_question'],QUESTION)
        self.assertEqual(C._coverage_budget(('s','x'*40957,1100))['conservative_total'],43082)
        self.assertFalse(C._coverage_budget(('s','x'*40957,1100))['fits'])

    def test_direct_free_slot_reaches_independent_inquiry(self):
        with patch.object(C,'_ask',return_value=json.dumps(SECOND)):
            self.assertEqual(C.tick()['kind'],'inquiry')
        got=C._load(C.STATE,{})['inquiry']
        self.assertEqual(got['question'],SECOND['question'])
        self.assertEqual(got['planning_scope']['question'],SECOND['question'].casefold())
        self.assertIsNotNone(C._held_question(self.cftr))

    def test_named_held_fallback_does_not_inherit_or_erase_either_hold(self):
        line={'id':'L-held','question':THIRD['question'],'next_step':'read its recorded calcium evidence'}
        scope=dict(self.free,line=line);scope.pop('context_sha256')
        named=self.hold(dict(THIRD,planning_scope=scope))
        sys.modules['lab_lines'].pick=lambda:line
        with patch.object(C,'_ask',return_value=json.dumps(SECOND)):
            self.assertEqual(C.tick()['kind'],'inquiry')
        got=C._load(C.STATE,{})['inquiry']
        self.assertEqual(got['question'],SECOND['question'])
        self.assertIsNone(got['planning_scope']['line'])
        self.assertIsNotNone(C._held_question(self.cftr))
        self.assertIsNotNone(C._held_question(named))

    def test_two_held_questions_all_held_repeated_ticks_are_honest_idle(self):
        self.hold(dict(SECOND,planning_scope=self.free))
        with patch.object(C,'_ask',side_effect=[json.dumps(self.cftr),json.dumps(SECOND)]*3):
            for _ in range(3):
                result=C.tick();self.assertEqual(result['kind'],'evidence_wait',result)
                note=C._tail_jsonl(C.NOTEBOOK)[-1]
                self.assertTrue(note['inquiry']['selection_idle'])
                self.assertIn('no eligible proposal this pass',note['why'])
                self.assertNotIn('evidence_status',note['inquiry'])
                self.assertNotIn('inquiry',C._load(C.STATE,{}))
        self.assertEqual(len(C._question_holds()),2)
        self.assertEqual(NET,[])

    def test_new_scope_and_attempt_id_do_not_release_legacy_cftr(self):
        proposal=copy.deepcopy(self.cftr)
        proposal.update(planning_scope={'context_sha256':'new'},id='fresh-id')
        proposal['source_query']['request_id']='another-attempt'
        with patch.object(C,'_ask',return_value=json.dumps(proposal)):
            self.assertEqual(C.tick()['kind'],'evidence_wait')
        self.assertIsNotNone(C._held_question(proposal))

    def test_paraphrase_with_changed_search_words_does_not_release(self):
        proposal=copy.deepcopy(self.cftr)
        proposal['question']='How do structural features of the CFTR regulatory R-domain and A-kinase anchoring protein AKAP interactions influence phosphorylation-dependent chloride channel gating?'
        proposal['source_query']['terms']=['CFTR AKAP R-domain phosphorylation gating']
        self.assertIsNotNone(C._held_question(proposal))
        with patch.object(C,'_ask',return_value=json.dumps(proposal)):
            self.assertEqual(C.tick()['kind'],'evidence_wait')

    def test_changed_evidence_releases_only_its_question(self):
        self.hold(dict(SECOND,planning_scope=self.free))
        original=C._planning_evidence
        with patch.object(C,'_planning_evidence',side_effect=lambda q:'new-cftr-evidence' if q['question']==QUESTION else original(q)):
            self.assertIsNone(C._held_question(self.cftr))
            self.assertIsNotNone(C._held_question(SECOND))
            with patch.object(C,'_ask',return_value=json.dumps(self.cftr)):
                self.assertEqual(C.tick()['kind'],'inquiry')

    def test_distinct_instrument_retains_existing_release_route(self):
        candidate=dict(self.cftr,source_query={'source':'pdb','entry_id':'5UAK','operation':'structure_evidence'})
        self.assertIsNone(C._held_question(candidate))

    def test_nohold_metadata_on_generated_proposal_cannot_clear_saved_hold(self):
        C._append(C.NOTEBOOK,{'kind':'inquiry_refused','inquiry':dict(self.cftr,refused='another planning refusal')})
        self.assertIsNotNone(C._held_question(self.cftr))

if __name__=='__main__': unittest.main()
