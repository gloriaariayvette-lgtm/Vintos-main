"""Offline full-question coverage and explicit entity constraints; no live calls."""
import hashlib, contextlib, json, os, pathlib, socket, sys, tempfile, types, unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-relevance-v2-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a,**k):raise AssertionError('external operation forbidden')
socket.socket.connect=forbidden
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C, lab_sources as S, lab_repeats as R
import urllib.request
C._ask=forbidden;urllib.request.urlopen=forbidden;S.open_request=forbidden
assert all(str(p).startswith(scratch.name) for p in (C.ROOT,C.STATE,C.NOTEBOOK,C.FAULTS,C.SPENT,C.RECEIPTS,R.LOOKUPS,R.SESSIONS))
assert C._ask is forbidden and socket.socket.connect is forbidden and S.open_request is forbidden
def protein(gene='CLCN1',accession='P35523',taxon=9606):
    return {'accession':accession,'protein_name':'Chloride channel protein 1','genes':[{'geneName':{'value':gene},'synonyms':[{'value':'CLC1'}]}],
            'taxon_id':taxon,'organism':'Homo sapiens' if taxon==9606 else 'Rattus norvegicus','topology_summary':'119-150','sequence':'ACACA','length':5}
def cover(answer=True):
    return {'answered':answer,'missing':[] if answer else ['computed hydropathy profile is absent'],
            'supports':[{'requirement':'source annotated range','address':'UniProt:P35523/topology_summary','quote':'119-150'}]}
def suff(answer=True):
    return {'sufficient':answer,'missing':[] if answer else ['computed hydropathy profile is absent'],
            'rationale':'Independent offline assessment of the full original question.'}

class ReviewTests(unittest.TestCase):
    def test_missing_question_fails_without_model(self):
        for question in ('','   ',None):
            self.assertTrue(C._reflect('',{'question':question},{'records':[]})['answers_question'].startswith('no:'))
            self.assertIsNone(C._coverage_check({'question':question},{}))

    def test_full_question_preserved(self):
        question='What evidence is supplied? '+'context '*80+'Also compare the requested hydropathy profiles.'
        self.assertEqual(C._inquiry({'question':question})['question'],question)

    def test_independent_assessment_and_short_quote(self):
        q={'question':'Which source annotation range is supplied for human CLCN1 (P35523)?'}
        with patch.object(C,'_ask',side_effect=[json.dumps({'answers_question':'yes'}),json.dumps(cover()),json.dumps(suff())]) as calls:
            result=C._reflect('',q,{'records':[protein()]})
        self.assertEqual(calls.call_count,3);self.assertTrue(result['answers_question'].startswith('yes:'))
        independent=calls.call_args_list[2].args[1]
        self.assertIn(q['question'],independent)
        self.assertNotIn('source annotated range',independent) # first assessor's requirement never shown
        self.assertTrue(result['coverage_check']['independent_sufficiency']['sufficient'])

    def test_recorded_hydropathy_partial_not_relabelled_answered(self):
        q={'question':'What is the hydropathy profile of the CLCN1_HUMAN (P35523) protein sequence, and which specific residue ranges correspond to the predicted transmembrane helices?'}
        with patch.object(C,'_ask',side_effect=[json.dumps({'answers_question':'yes','next_question':'Compute that profile again'}),json.dumps(cover()),json.dumps(suff(False))]):
            result=C._reflect('',q,{'records':[protein()]})
        self.assertTrue(result['answers_question'].startswith('no:'))
        self.assertIn('119-150',result['factual_observation'])
        self.assertEqual(result['next_question'],'')
        self.assertFalse(result['evidence_gap']['automatic_followup'])
        self.assertFalse(hasattr(C,'profile_evidence_check'))

    def test_missing_assessment_and_invented_quote_fail_closed(self):
        q={'question':'Which range is supplied?'}
        with patch.object(C,'_ask',side_effect=[json.dumps(cover()),'{}']):
            self.assertEqual(C._coverage_check(q,{'records':[protein()]})['assessment_status'],'incomplete')
        invalid=cover();invalid['supports'][0]['quote']='absent'
        with patch.object(C,'_ask',return_value=json.dumps(invalid)) as calls:
            self.assertEqual(C._coverage_check(q,{'records':[protein()]})['assessment_status'],'incomplete')
        self.assertEqual(calls.call_count,1)

    def test_both_question_and_query_constraints(self):
        for question,query in [('human CLCN4 (P31641)','gene:CLCN4'),('human CLCN3 (P35523)','gene:CLCN3'),
                               ('human CLCN1 (P35523)','gene:CLCN3'),('human CLCN3 (P35523)','gene:CLCN1')]:
            q=C._inquiry({'question':question,'uniprot_query':query})
            row=protein('SLC6A6','P31641') if 'P31641' in question else protein()
            self.assertEqual(S.question_entity_context(q,[row])['status'],'unresolved')
        q=C._inquiry({'question':'human CLCN1 (P35523)','uniprot_query':'gene:CLC1'})
        self.assertEqual(S.question_entity_context(q,[protein()])['status'],'consistent')

    def test_original_source_query_preserved(self):
        q=C._inquiry({'question':'human CLCN1 (P35523)','uniprot_query':'accession:P35523',
                      'source_query':{'source':'uniprot','query':'gene:CLCN3 AND taxonomy_id:9606'}})
        self.assertIn('gene:CLCN3 AND taxonomy_id:9606',q['identity_queries'])
        self.assertEqual(S.question_entity_context(q,[protein()])['status'],'unresolved')

    def test_multiple_accessions_mapping_is_unresolved(self):
        self.assertEqual(S.question_entity_context({'question':'Compare P35523 and P31641'},[protein(),protein('SLC6A6','P31641')])['status'],'unresolved')

    def test_species_and_missing_isoform_metadata(self):
        cases=[{'question':'rat CLCN1 (P35523)'},{'question':'human CLCN1 (P35523)','uniprot_query':'gene:CLCN1 AND taxonomy_id:10116'},
               {'question':'CLCN1 (P35523)','uniprot_query':'gene:CLCN1 AND organism_name:"Rattus norvegicus"'},
               {'question':'CLCN1 (P35523) isoform 2'},{'question':'CLCN1 (P35523-2)'}]
        for q in cases:self.assertEqual(S.question_entity_context(q,[protein()])['status'],'unresolved',q)
        p=protein();p['isoform']='2'
        self.assertEqual(S.question_entity_context(cases[-2],[p])['status'],'consistent')
        self.assertEqual(S.question_entity_context({'question':'rat CLCN1 (P35523)'},[protein(taxon=10116)])['status'],'consistent')
        self.assertEqual(S.question_entity_context({'question':'CLCN1_HUMAN (P35523)'},[protein(taxon=10116)])['status'],'unresolved')

    def test_contextual_ranges_and_explicit_genes(self):
        for dash in ('-','–'):
            q='Describe the human channel helices S1'+dash+'S6 of TRPV1'
            self.assertEqual(S.human_question_symbols(q),['TRPV1'])
        for q in ('human gene:S1-S6 channel','human S1-S6 gene in a channel','human gene symbol S1-S6 helices'):
            self.assertIn('S1-S6',S.human_question_symbols(q))
        self.assertEqual(S.human_question_symbols('human S1 and S6 genes'),['S1','S6'])
        self.assertEqual(S.human_question_symbols('human TP53 BRCA1 G6PD'),['TP53','BRCA1','G6PD'])

    def test_unavailable_profile_does_not_revive_old_followup(self):
        inquiry={'question':'Hydropathy profile of P35523','uniprot_query':'accession:P35523'}
        rows=[{'kind':'reflection','inquiry':inquiry,'next_question':'Compute that hydropathy profile'},
              {'kind':'reflection','inquiry':inquiry,'next_question':'','evidence_gap':{'automatic_followup':False}}]
        with patch.object(C,'_tail_jsonl',return_value=rows),patch.object(C,'_strategy_change',side_effect=forbidden):
            self.assertIsNone(C._next_evidence_work({},R,None,None))
        with patch.object(C,'_ask',return_value=json.dumps({'answers_question':'no: computed hydropathy profile is absent','next_question':'Try the same profile again'})):
            result=C._reflect('',{'question':'What is the hydropathy profile?'},{'records':[]})
        self.assertEqual(result['next_question'],'')
        self.assertFalse(result['evidence_gap']['automatic_followup'])

    def test_corrected_query_rebinds_same_question(self):
        old=C._inquiry({'question':'human CLCN1 (P35523)','uniprot_query':'gene:CLCN3'})
        self.assertEqual(S.question_entity_context(old,[protein()])['status'],'unresolved')
        corrected=C._inquiry(dict(old,uniprot_query='gene:CLCN1'))
        self.assertEqual(S.question_entity_context(corrected,[protein()])['status'],'consistent')

    def test_stale_context_and_unrelated_later_retrieval(self):
        old=C._inquiry({'question':'human CLCN3 (P35523)','uniprot_query':'gene:CLCN3',
                        'source_query':{'source':'uniprot','query':'gene:CLCN3'}})
        corrected=C._inquiry(dict(old,question='human CLCN1 (P35523)',uniprot_query='gene:CLCN1'))
        self.assertNotIn('gene:CLCN3',corrected['identity_context']['original_queries'])
        self.assertEqual(S.question_entity_context(corrected,[protein()])['status'],'consistent')
        stale=dict(old,question='human CLCN1 (P35523)',uniprot_query='gene:CLCN1')
        self.assertFalse(S.question_entity_context(stale,[protein()])['context_current'])
        self.assertEqual(S.question_entity_context(stale,[protein()])['status'],'consistent')
        later=dict(corrected,uniprot_query='accession:P31641',source_query={'source':'uniprot','query':'gene:OTHER1'})
        self.assertEqual(S.question_entity_context(later,[protein()])['status'],'consistent')
        self.assertEqual(S.question_entity_context(later,[protein('OTHER1','P31641')])['status'],'unresolved')

    def test_selected_target_and_authoritative_alternative_names(self):
        p=protein();p['protein_aliases']=['Alternative channel'];p['organism_aliases']=['Human']
        q={'question':'Which range is supplied?','uniprot_query':'protein_name:"Alternative channel" AND organism_name:"Human"'}
        check=S.question_entity_context(q,[protein('OTHER1','P31641'),p])
        self.assertEqual(check['status'],'consistent');self.assertEqual(check['selected_accessions'],['P35523'])
        q={'question':'human CLCN1','uniprot_query':'gene:CLCN1 AND taxonomy_id:9606'}
        self.assertEqual(S.question_entity_context(q,[protein('OTHER1','P31641'),p,protein(taxon=10116)])['status'],'consistent')
        p['genes']=[{'geneName':{'value':'CLCN1'}}];p['protein_aliases']=['CLC1']
        self.assertEqual(S.question_entity_context({'question':'What is supplied?','uniprot_query':'gene:CLC1'},[p])['status'],'unresolved')

    def test_newer_evidence_and_explicit_request_are_not_stopped(self):
        q={'question':'Hydropathy profile of P35523','uniprot_query':'accession:P35523'}
        rows=[{'kind':'reflection','inquiry':q,'evidence_gap':{'automatic_followup':False}},
              {'kind':'reflection','inquiry':q,'next_question':'Inspect the newly supplied profile artifact'}]
        with patch.object(C,'_tail_jsonl',return_value=rows),patch.object(C,'_strategy_change',return_value={'new_evidence':True,'strategy_resolution':{}}):
            self.assertEqual(C._next_evidence_work({},R,None,None),{'new_evidence':True,'strategy_resolution':{'reason':'continued_another_self_authored_unresolved_step'}})

    def test_explicit_new_request_can_assess_new_evidence_after_stop(self):
        question='Hydropathy profile of P35523'
        stop={'kind':'reflection','inquiry':{'question':question},'evidence_gap':{'automatic_followup':False}}
        p=protein();p['profile_fixture']='Synthetic new evidence fixture: residue positions 1-5; scale and values supplied for assessment.'
        support={'answered':True,'missing':[],'supports':[{'requirement':'requested profile evidence','address':'UniProt:P35523/profile_fixture','quote':p['profile_fixture']}]}
        with patch.object(C,'_tail_jsonl',return_value=[stop]),patch.object(C,'_ask',side_effect=[json.dumps({'answers_question':'yes'}),json.dumps(support),json.dumps(suff())]) as calls:
            inquiry=C._inquiry({'question':question,'uniprot_query':'accession:P35523'})
            result=C._reflect('',inquiry,{'records':[p]})
        self.assertTrue(result['answers_question'].startswith('yes:'))
        self.assertEqual(calls.call_count,3) # workflow eligibility, not scientific validation of this synthetic fixture

    def test_tick_persists_partial_and_model_failures_do_not_retry(self):
        yes=json.dumps({'answers_question':'yes','next_question':'Compute profile again'})
        cases=[([yes,json.dumps(cover()),json.dumps(suff(False))],3,True),
               ([TimeoutError('fixture timeout')],1,False),(['not JSON'],1,False),
               ([yes,TimeoutError('coverage timeout')],2,False),
               ([yes,json.dumps(cover()),TimeoutError('sufficiency timeout')],3,False)]
        modules={
            'compute_admission':types.SimpleNamespace(admit=lambda *a,**k:contextlib.nullcontext()),
            'chemistry_reading':types.SimpleNamespace(settle_one=lambda **k:None),
            'chemistry_taste':types.SimpleNamespace(observe_reflection=lambda note:None),
            'chemistry_frontier_bridge':types.SimpleNamespace(assess=lambda *a,**k:{'entry_id':'fixture','interest_score':0,'reason_for_score':'fixture','flagged_for_next_lab_session':False,'truth_status':'fixture'}),
            'forge_gaps':types.SimpleNamespace(judge=forbidden)}
        cfg=dict(C.DEFAULTS,enabled=True,evo2_enabled=False,forge_report_intake=None)
        for replies,count,partial in cases:
            C._ensure();C._atomic(C.STATE,{'phase':'reflect','inquiry':{'question':'What hydropathy profile and annotated ranges are supplied?'},'records':[protein()],'additional_source':{}})
            with patch.dict(sys.modules,modules),patch.object(C,'config',return_value=cfg),patch.object(C,'stop_requested',return_value=False),patch.object(C,'lab_context',return_value=('fixture',{})),patch.object(C,'_gather_material',return_value=None),patch.object(C,'repeated_review',return_value=False),patch.object(C,'_ask',side_effect=replies) as calls:
                result=C.tick()
            self.assertTrue(result['ok'],result);self.assertEqual(result['kind'],'reflection')
            self.assertEqual(calls.call_count,count)
            state=C._load(C.STATE,{})
            self.assertEqual(state['phase'],'orient');self.assertNotIn('inquiry',state)
            note=C._tail_jsonl(C.NOTEBOOK)[-1]
            self.assertTrue(note['answers_question'].startswith('no:'))
            if partial:
                self.assertIn('119-150',note['factual_observation'])
                self.assertFalse(note['evidence_gap']['automatic_followup'])
                self.assertEqual(note['instrument_gap'],'')


    def test_domain_label_is_not_a_target_identity(self):
        question='What are the specific residue coordinates and chemical properties of the interface between the HR1 domain and the Cavin-1 N-terminal region that facilitate its interaction with Caveolin-1?'
        self.assertNotIn('HR1',S.human_question_symbols(question))
        row={'accession':'Q6NZI2','protein_name':'Caveolae-associated protein 1'}
        inquiry={'question':question,'uniprot_query':'accession:Q6NZI2'}
        self.assertEqual(S.question_entity_context(inquiry,[row])['status'],'consistent')
        self.assertEqual(inquiry['question'],question)
        self.assertEqual(S.human_question_symbols('Describe the interface between the ABC2 domain and the CLCN1 N-terminal region (P35523)'),['CLCN1'])

    def test_explicit_domain_spelling_gene_constraints_survive(self):
        for question in ('Describe the gene HR1 domain', 'Describe gene:HR1 domain',
                         'Describe gene symbol HR1 domain', 'Describe gene symbol: HR1 domain',
                         'Describe the HR1 gene domain', 'Describe protein HR1 domain'):
            self.assertIn('HR1',S.human_question_symbols(question),question)
        inquiry={'question':'Describe the interface between the HR1 domain and the CLCN1 N-terminal region (P35523)','uniprot_query':'gene:HR1'}
        self.assertEqual(S.question_entity_context(inquiry,[protein()])['status'],'unresolved')

    def test_conflicting_domain_and_target_occurrences_remain_unresolved(self):
        for question in ('Compare the HR1 domain with the HR1 gene in human CLCN1 (P35523)',
                         'Compare gene HR1 with the HR1 domain of CLCN1 (P35523)',
                         'Compare HR1 and the HR1 domain of CLCN1 (P35523)',
                         'Describe the interface between the HR1 domain and the CLCN1 N-terminal region (P35523), and the HR1 gene'):
            self.assertIn('HR1',S.human_question_symbols(question))
            self.assertEqual(S.question_entity_context({'question':question},[protein()])['status'],'unresolved')

    def test_target_protein_names_near_domain_are_preserved(self):
        for question in ('Describe the BRCA1 domain-containing protein',
                         'Describe the BRCA1 domain containing protein',
                         'Describe the BRCA1 domain-associated protein',
                         'Describe the BRCA1 domain protein', 'Describe the domain of BRCA1',
                         'Describe BRCA1 and its domain', 'Describe protein BRCA1 domain',
                         'Describe the BRCA1 domain', 'Describe BRCA1 domain'):
            self.assertIn('BRCA1',S.human_question_symbols(question),question)
        self.assertEqual(S.question_entity_context({'question':'Describe the BRCA1 domain-containing protein'},[protein()])['status'],'unresolved')

    def test_location_phrases_do_not_hide_target_or_query_mismatch(self):
        row=protein('BRCA1','P38398')
        for question in ('Describe the BRCA1 domain in human cells',
                         'Describe the BRCA1 domain within the nucleus',
                         'Describe the BRCA1 domain of interest'):
            self.assertIn('BRCA1',S.human_question_symbols(question),question)
            self.assertEqual(S.question_entity_context({'question':question},[protein()])['status'],'unresolved')
            self.assertEqual(S.question_entity_context({'question':question},[row])['status'],'consistent')
            self.assertEqual(S.question_entity_context({'question':question,'uniprot_query':'gene:CLCN3'},[row])['status'],'unresolved')

    def test_feature_context_does_not_weaken_accession_or_species(self):
        for inquiry in ({'question':'Describe the interface between the HR1 domain and the CLCN1 N-terminal region in rat (P35523)'},
                        {'question':'Describe the interface between the HR1 domain and the CLCN1 N-terminal region in human (P35523)','uniprot_query':'accession:P31641'},
                        {'question':'Describe the interface between the HR1 domain and the CLCN1 N-terminal region in human (P35523)','uniprot_query':'gene:CLCN3'}):
            self.assertEqual(S.question_entity_context(inquiry,[protein()])['status'],'unresolved')

    def test_unsupported_domain_claim_still_fails_independent_assessment(self):
        question='Which residues form the interface between the HR1 domain and the CLCN1 N-terminal region in human (P35523)?'
        missing={'sufficient':False,'missing':['No source establishes an HR1 domain or its residue boundaries'],
                 'rationale':'The quoted topology range does not establish the requested domain.'}
        with patch.object(C,'_ask',side_effect=[json.dumps({'answers_question':'yes'}),json.dumps(cover()),json.dumps(missing)]) as calls:
            result=C._reflect('',{'question':question},{'records':[protein()]})
        self.assertEqual(calls.call_count,3)
        self.assertTrue(result['answers_question'].startswith('no:'))
        self.assertFalse(result['coverage_check']['independent_sufficiency']['sufficient'])
        for call in calls.call_args_list:self.assertIn(question,call.args[1])

if __name__=='__main__':unittest.main()
