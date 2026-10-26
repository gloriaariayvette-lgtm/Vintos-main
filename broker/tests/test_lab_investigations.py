#!/usr/bin/env python3
"""Chained autonomous turns with real persistence and all senders blocked."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_lab_tool_routing as sandbox
import lab_investigations as I
import lab_lines

C = sandbox.C


class Investigations(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(C.ROOT).is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect, sandbox.SEND)
        C._atomic(I._path('investigations.json'), {'investigations':[]})
        self.ask = Mock()
        self.lines = patch.multiple(lab_lines, pick=Mock(return_value=None),
                                   opened_by=Mock(return_value=None), record_step=Mock())
        self.lines.start()

    def tearDown(self):
        self.lines.stop()
        sandbox.SEND.assert_not_called()

    def choice(self, route, request):
        return json.dumps({'question':'Do these sourced molecules form distinct similarity clusters?',
            'prediction':'Two clusters at the selected cutoff.', 'plan':['Obtain inputs','Compute similarity'],
            'route':route, 'request':request, 'step_question':'Measure molecular similarity',
            'why':'Use this result to choose the next comparison.'})

    def test_output_becomes_next_input_across_turns(self):
        self.ask.side_effect = [self.choice('source', {'source':'pubchem','name':'fixture'}),
                                self.choice('plugin', {})]
        def source(route, request, question, steps):
            return {'receipt':{'source':'pubchem','records':[{'smiles':'CCO'}, {'smiles':'CCN'}]}}
        first = I.turn('context', ask=self.ask, execute=source)
        ref = {'step':first['id'], 'path':['receipt','records']}
        self.ask.side_effect = [self.choice('plugin', {'plugin':'nvmolkit','tool':'nvmolkit.similarity',
                                                      'arguments':{'molecules':ref}})]
        seen = []
        def measure(route, request, question, steps):
            seen.append(I.resolve(request, steps))
            return {'receipt':{'source':'instrument:nvmolkit','records':[{'similarity':0.4}]}}
        second = I.turn('new context', ask=self.ask, execute=measure)
        self.assertEqual(first['investigation'], second['investigation'])
        self.assertEqual(seen[0]['arguments']['molecules'], [{'smiles':'CCO'}, {'smiles':'CCN'}])
        self.assertEqual(second['input_refs'], [ref])
        self.assertIn(first['id'], self.ask.call_args.args[1])
        self.assertEqual(second['origin'], 'autonomous_lab')

    def test_modified_output_is_not_silently_used(self):
        self.ask.return_value = self.choice('source', {'source':'pubchem','name':'fixture'})
        row = I.turn('', ask=self.ask, execute=lambda *a:{'records':['CCO']})
        C._atomic(I._path(row['output_file']), {'records':['different']})
        with self.assertRaisesRegex(ValueError, 'output changed'):
            I.resolve({'step':row['id'],'path':['records']}, [row])

    def test_screen_is_a_chosen_step_without_reserved_turns(self):
        self.ask.return_value = self.choice('campaign', {})
        execute = Mock(return_value={'kind':'campaign_screen','protein':'RETURNED.1'})
        row = I.turn('', ask=self.ask, execute=execute)
        self.assertEqual(row['route'], 'campaign')
        execute.assert_called_once()
        self.assertFalse(C._campaign_due({'turns':0}, {'campaigns':True}))
        self.assertFalse(C._campaign_due({'turns':2}, {'campaigns':True}))

    def test_dotted_source_name_is_routed_not_refused(self):
        # the planner writes a source's operation into the name ("ncbi.literature"): route it to source ncbi with
        # operation literature rather than refuse it as an unsupported source (hundreds of her steps lost to this)
        self.ask.return_value = self.choice('source', {'source':'ncbi.literature','term':'reverse transcriptase'})
        I.turn('', ask=self.ask, execute=lambda *a:{'receipt':{'source':'ncbi','records':[{'pmid':'1'}]}})
        step = C._load(I._path('investigations.json'), {})['investigations'][0]['steps'][-1]
        self.assertEqual(step['request'].get('source'), 'ncbi')
        self.assertEqual(step['request'].get('operation'), 'literature')

    def test_dotted_source_that_names_a_real_source_is_joined(self):
        self.ask.return_value = self.choice('source', {'source':'ncbi.protein_context','accession':'P0DTC2'})
        I.turn('', ask=self.ask, execute=lambda *a:{'receipt':{'source':'ncbi_protein_context','records':[]}})
        step = C._load(I._path('investigations.json'), {})['investigations'][0]['steps'][-1]
        self.assertEqual(step['request'].get('source'), 'ncbi_protein_context')

    def test_frontier_plan_directs_the_step_only_when_enabled(self):
        planned = {'step_number':1,'of':3,'objective':'Fold the candidate','route':'instrument','tool':'esmfold',
                   'depends_on':'step 1','success_criteria':'a model','upcoming':[]}
        inv = {'id':'I-x','line_id':'L-x','question':'q','prediction':'','steps':[],'plan':[]}
        with patch('lab_lines.get', return_value={'id':'L-x'}), \
             patch('lab_lines.plan_for_planner', return_value=planned):
            captured = {}
            def ask(system, prompt, **k):
                captured.update(system=system, prompt=prompt); return self.choice('source', {'source':'pubchem'})
            with patch.object(I, 'FRONTIER_PLANS', True):
                I._plan(dict(inv), 'ctx', ask)
            self.assertIn('planned_step', captured['prompt'])
            self.assertIn('esmfold', captured['prompt'])
            self.assertIn('executable plan', captured['system'])
            captured.clear()
            with patch.object(I, 'FRONTIER_PLANS', False):
                I._plan(dict(inv), 'ctx', ask)
            self.assertNotIn('planned_step', captured['prompt'])   # off by default: free choice, unchanged

    def test_failure_is_saved_as_next_step_context_without_retry(self):
        self.ask.return_value = self.choice('plugin', {'plugin':'nvidia_nim','tool':'nvidia_nim.boltz2'})
        execute = Mock(side_effect=TimeoutError('unknown outcome'))
        row = I.turn('', ask=self.ask, execute=execute)
        self.assertEqual(row['state'], 'outcome_unknown')
        execute.assert_called_once()
        self.assertEqual(self.ask.call_count, 1)
        stored = C._load(I._path('investigations.json'), {})
        self.assertIn('unknown outcome', stored['investigations'][0]['steps'][-1]['error'])

    def test_finish_uses_existing_scientific_review(self):
        self.ask.return_value = self.choice('source', {'source':'pubchem','name':'fixture'})
        I.turn('', ask=self.ask, execute=lambda *a:{'receipt':{'source':'pubchem','records':[{'smiles':'CCO'}]}})
        self.ask.return_value = self.choice('finish', {})
        with patch.object(C, '_reflect', return_value={'answers_question':'no: missing comparison'}) as reflect:
            I.turn('', ask=self.ask)
            self.assertIn('additional_source', reflect.call_args.args[2])
        self.assertEqual(C._load(I._path('investigations.json'), {})['investigations'][0]['state'], 'open')
        with patch.object(C, '_reflect', return_value={'answers_question':'yes: verified fixture'}):
            I.turn('', ask=self.ask)
        self.assertEqual(C._load(I._path('investigations.json'), {})['investigations'][0]['state'], 'answered')

    def test_review_normalizes_real_source_shape_and_retains_full_sequence(self):
        raw={'primaryAccession':'P12345','uniProtkbId':'TEST_HUMAN',
             'proteinDescription':{'recommendedName':{'fullName':{'value':'Test protein'}}},
             'organism':{'scientificName':'Homo sapiens','taxonId':9606},
             'sequence':{'value':'M'+'A'*1200,'length':1201},'genes':[{'geneName':{'value':'TEST'}}]}
        self.ask.return_value=self.choice('source',{'source':'uniprot','query':'accession:P12345'})
        step=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'uniprot','records':[raw]}})
        observations=I._observations([step])
        record=observations['records'][0]
        self.assertEqual(record['accession'],'P12345')
        self.assertEqual(record['taxon_id'],9606)
        self.assertEqual(record['sequence'],raw['sequence']['value'])
        self.assertEqual(I.resolve({'step':step['id'],'path':['receipt','records',0,'sequence','value']},[step]),raw['sequence']['value'])

    def test_account_schema_uses_account_gateway_and_local_schema_calls_nothing(self):
        import claude_connector_gateway as account, plugin_gateway as mac
        with patch.object(account,'tool_schemas',return_value={'tools':{'boltz_get_guidance':{}}}) as read, \
             patch.object(mac,'tool_schemas',side_effect=AssertionError('wrong account')):
            out=I.dispatch('schema',{'plugin':'boltz'},'Discover the connector',[])
            read.assert_called_once_with('boltz')
            self.assertIn('schema',out)
        local=mac.tool_schemas('nvmolkit')
        self.assertEqual(local['schemas']['nvmolkit.cluster']['required'],['smiles','cutoff'])

    def test_returned_failure_is_retained_and_never_marked_completed(self):
        self.ask.return_value=self.choice('plugin',{'plugin':'nvmolkit','tool':'nvmolkit.similarity'})
        row=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'records':{'ok':False,'error':'provider refused'}}})
        self.assertEqual(row['state'],'failed')
        self.assertTrue(Path(I._path(row['output_file'])).is_file())
        with self.assertRaisesRegex(ValueError,'only completed'):
            I.resolve({'step':row['id'],'path':[]},[row])

    def test_unknown_outcome_cannot_be_repeated_on_later_turn(self):
        self.ask.return_value=self.choice('experiment',{'experiment':'molecule','parameters':{}})
        execute=Mock(return_value={'ok':False,'state':'unknown_after_timeout','error':'timed out after send'})
        row=I.turn('',ask=self.ask,execute=execute)
        self.assertEqual(row['state'],'outcome_unknown')
        second=I.turn('',ask=self.ask,execute=execute)
        execute.assert_called_once()
        self.assertEqual(second['state'],'failed')
        self.assertIn('unknown outcome',second['error'])

    def test_same_lookup_in_a_new_investigation_reuses_the_earlier_output_without_sending(self):
        self.ask.return_value=self.choice('source',{'source':'pubchem','name':'fixture'})
        execute=Mock(return_value={'receipt':{'source':'pubchem','receipt_id':'R-1','records':[{'SMILES':'CCO'}]}})
        first=I.turn('',ask=self.ask,execute=execute)
        data=C._load(I._path('investigations.json'),{})
        data['investigations'][0]['state']='stalled'; C._atomic(I._path('investigations.json'),data)
        # the same question reopened is refused before it opens (test_lab_no_repeat); this is the lookup's reuse
        with patch.object(I,'_same_question',return_value=[]):
            second=I.turn('',ask=self.ask,execute=execute)
        execute.assert_called_once()
        self.assertNotEqual(first['investigation'],second['investigation'])
        self.assertEqual((second['state'],second['reused_from']),('completed',first['id']))
        self.assertEqual(I.resolve({'step':second['id'],'path':['receipt','records',0,'SMILES']},[second]),'CCO')

    def test_same_lookup_twice_in_one_investigation_points_back_to_its_own_step(self):
        self.ask.return_value=self.choice('source',{'source':'pubchem','name':'fixture'})
        execute=Mock(return_value={'receipt':{'source':'pubchem','records':[{'SMILES':'CCO'}]}})
        first=I.turn('',ask=self.ask,execute=execute)
        second=I.turn('',ask=self.ask,execute=execute)
        execute.assert_called_once()    # never sent twice
        # handed its own earlier output (25 October: refusing it was 47 of 85 failed steps), counted as no failure
        self.assertEqual((second['state'],second['reused_from'],second['repeat_within']),('completed',first['id'],True))
        self.assertEqual(I.resolve({'step':second['id'],'path':['receipt','records',0,'SMILES']},[second]),'CCO')

    def test_a_source_named_as_the_route_is_that_sources_query(self):
        self.ask.return_value=self.choice('pubmed',{'query':'reverse transcriptase CRISPR phage'})
        seen=[]
        row=I.turn('',ask=self.ask,execute=lambda route,request,*a:(seen.append((route,request)),
                   {'receipt':{'source':'pubmed','records':[{'pmid':'1'}]}})[1])
        self.assertEqual(seen[0][0],'source')
        self.assertEqual(seen[0][1].get('source'),'pubmed')
        self.assertEqual((row['state'],row['tool'],row['authored_route']),('completed','source:pubmed','pubmed'))

    def test_an_instrument_named_only_by_its_operation_is_named(self):
        from lab_tool_calls import normalize_request
        self.assertEqual(normalize_request('instrument',{'instrument_query':{'operation':'fold_read','files':['a.pdb']}}),
                         {'operation':'structure.read','skill':'fold_read','files':['a.pdb']})
        self.assertEqual(normalize_request('instrument',{'operation':'structure.compare'})['skill'],'reference_compare')
        self.assertNotIn('skill',normalize_request('instrument',{'operation':'no.such'}))
        valid={'skill':'structure_viewer','operation':'structure.analyze','files':['a.pdb']}
        self.assertEqual(normalize_request('instrument',dict(valid)),valid)

    def test_several_models_are_read_one_at_a_time_and_the_step_question_is_asked(self):
        import lab_instruments
        read=[]
        def run(req):
            read.append((req['files'],req['question']))
            return {'instrument_receipt':{'records':[{'file':req['files'][0]}]}}
        with patch.object(C,'_inquiry',lambda d:d), \
             patch.object(C,'_held_to_plan',lambda *a,**k:({'instrument_query':a[2]['instrument_query']},{})), \
             patch.object(lab_instruments,'run',run):
            out=I.dispatch('instrument',{'skill':'fold_read','operation':'structure.read',
                           'files':['artifacts/esmfold/a.pdb','artifacts/esmfold/b.pdb']},'Which helices hold the pore?',[])
        self.assertEqual(read,[(['artifacts/esmfold/a.pdb'],'Which helices hold the pore?'),
                               (['artifacts/esmfold/b.pdb'],'Which helices hold the pore?')])
        self.assertEqual([r['file'] for r in out['reads']],['artifacts/esmfold/a.pdb','artifacts/esmfold/b.pdb'])

    def test_a_question_refused_as_a_repeat_takes_the_answer_already_retained(self):
        q='Identify bacteriophages carrying a reverse transcriptase beside a CRISPR array'
        self.ask.return_value=json.dumps({'question':'q1','prediction':'p','plan':[],'route':'source',
            'request':{'source':'pubmed','query':'phage RT CRISPR'},'step_question':q,'why':'w'})
        first=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'pubmed','receipt_id':'R-9','records':[{'pmid':'1'}]}})
        data=C._load(I._path('investigations.json'),{}); data['investigations'][0]['state']='stalled'
        C._atomic(I._path('investigations.json'),data)
        self.ask.return_value=json.dumps({'question':'q2','prediction':'p','plan':[],'route':'source',
            'request':{'source':'pubmed','query':'reverse transcriptase CRISPR bacteriophage'},'step_question':q+' in phage genomes','why':'w'})
        def refuse(*a): raise ValueError('no eligible saved step: you already asked this on 2026-10-22 10:00, in other words: '+q)
        second=I.turn('',ask=self.ask,execute=refuse)
        self.assertEqual((second['state'],second['reused_from']),('completed',first['id']))
        self.assertIn('you already asked this',second['reused_because'])
        def identity(*a): raise ValueError('no eligible saved step: unchanged unresolved identity: multiple accessions')
        data=C._load(I._path('investigations.json'),{}); data['investigations'][-1]['state']='stalled'
        C._atomic(I._path('investigations.json'),data)
        self.ask.return_value=json.dumps({'question':'q3','prediction':'p','plan':[],'route':'source',
            'request':{'source':'pubmed','query':'another wording'},'step_question':q,'why':'w'})
        third=I.turn('',ask=self.ask,execute=identity)
        self.assertEqual(third['state'],'failed')
        self.assertNotIn('reused_from',third)

    def test_the_planner_is_told_which_tools_were_refused_as_repeats(self):
        self.ask.return_value=self.choice('source',{'source':'pubmed','query':'x'})
        def refuse(*a): raise ValueError('no eligible saved step: you already asked this on 2026-10-22, in other words: x')
        I.turn('',ask=self.ask,execute=refuse)
        I.turn('',ask=self.ask,execute=refuse)
        self.assertIn('"already_asked": ["source:pubmed"]',self.ask.call_args.args[1])

    def test_source_step_enters_existing_embedding_phase_and_records_its_output(self):
        self.ask.return_value=self.choice('source',{'source':'uniprot','query':'accession:P12345'})
        raw={'primaryAccession':'P12345','sequence':{'value':'MAAAA','length':5}}
        row=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'uniprot','records':[raw]}})
        state={}
        self.assertEqual(I.next_phase(state,row,{}),'embed')
        self.assertEqual(state['records'][0]['sequence'],'MAAAA')
        I.record_phase(state,'embed',{'kind':'protein_representation','embeddings':[{'accession':'P12345','dimension':1152}]})
        steps=C._load(I._path('investigations.json'),{})['investigations'][0]['steps']
        self.assertEqual(steps[-1]['tool'],'representation')
        self.assertEqual(steps[-1]['input_refs'][0]['step'],row['id'])

    def test_genomic_cadence_is_preserved_for_nonprotein_investigation(self):
        self.ask.return_value=self.choice('source',{'source':'pubchem','name':'ethanol'})
        row=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'pubchem','records':[{'SMILES':'CCO'}]}})
        self.assertEqual(I.next_phase({'turns':480,'last_evo_turn':0},row,{'evo2_enabled':True,'evo2_every_n_cycles':120}),'genome')

    def test_output_index_and_read_output_reveal_keys_beyond_preview(self):
        self.ask.return_value=self.choice('source',{'source':'pubchem','name':'fixture'})
        row=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'pubchem','records':[{'long':'x'*9000,'SMILES':'CCO'}]}})
        self.assertTrue(any('SMILES' in x.get('keys',[]) for x in row['output_index']))
        self.assertEqual(I.dispatch('read_output',{'reference':{'step':row['id'],'path':['receipt','records',0,'SMILES']}},'', [row]),{'value':'CCO'})

    def test_literal_identifier_is_bound_only_to_returned_data(self):
        self.ask.return_value=self.choice('source',{'source':'uniprot','query':'accession:P69905'})
        row=I.turn('',ask=self.ask,execute=lambda *a:{'receipt':{'source':'uniprot','query':{'accession':'Q12345'},
             'records':[{'primaryAccession':'P69905','sequence':{'value':'MAAAA','length':5}}]}})
        bound=I.bind_inputs({'source':'interpro','accession':'P69905'},[row])
        self.assertEqual(I.resolve(bound,[row]),{'source':'interpro','accession':'P69905'})
        self.assertEqual(bound['accession']['step'],row['id'])
        self.assertEqual(I.bind_inputs({'accession':'Q12345'},[row]),{'accession':'Q12345'})

    def test_restart_marks_started_step_unknown(self):
        data={'investigations':[{'id':'I-old','opened_at':C.now_iso(),'state':'open','question':'Old question',
             'steps':[{'id':'S-old','state':'started','route':'experiment','request_sha256':'old'}]}]}
        C._atomic(I._path('investigations.json'),data)
        self.ask.return_value=self.choice('schema',{'plugin':'nvmolkit'})
        I.turn('',ask=self.ask,execute=lambda *a:{'schema':{}})
        self.assertEqual(C._load(I._path('investigations.json'),{})['investigations'][0]['steps'][0]['state'],'outcome_unknown')


    def test_unanswered_finish_closes_and_the_next_turn_starts_another(self):
        data={'investigations':[{'id':'I-one','opened_at':C.now_iso(),'state':'open','question':'Q one',
             'prediction':'p','steps':[]}]}
        C._atomic(I._path('investigations.json'),data)
        self.ask.return_value=json.dumps({'question':'Q one','route':'finish','request':{}})
        with patch.object(C,'_reflect',return_value={'answers_question':'no: the outputs do not settle it'}):
            for n in range(I.MAX_UNANSWERED_REVIEWS):
                rows=C._load(I._path('investigations.json'),{})['investigations']
                self.assertEqual(rows[0]['state'],'open')
                I.turn('',ask=self.ask,execute=Mock())
        rows=C._load(I._path('investigations.json'),{})['investigations']
        self.assertEqual(rows[0]['state'],'unanswered')
        self.ask.return_value=self.choice('schema',{'plugin':'nvmolkit'})
        nxt=I.turn('',ask=self.ask,execute=lambda *a:{'schema':{}})
        self.assertNotEqual(nxt['investigation'],'I-one')

    def test_a_stuck_investigation_is_closed_not_chosen_forever(self):
        self.ask.return_value=self.choice('source',{'source':'pubchem','name':'fixture'})
        def broken(*a): raise ValueError('refused')
        ids=set()
        for n in range(I.MAX_FAILED_RUN):
            self.ask.return_value=self.choice('source',{'source':'pubchem','name':'fixture-%d'%n})
            ids.add(I.turn('',ask=self.ask,execute=broken)['investigation'])
        rows=C._load(I._path('investigations.json'),{})['investigations']
        self.assertEqual(len(ids),1)
        self.assertEqual(rows[0]['state'],'stalled')
        self.assertIn('in a row produced nothing',rows[0]['closed_reason'])

    def test_step_budget_closes_an_investigation(self):
        steps=[{'id':'S-%d'%n,'state':'completed','route':'source'} for n in range(I.MAX_STEPS-1)]
        C._atomic(I._path('investigations.json'),{'investigations':[{'id':'I-long','opened_at':C.now_iso(),
            'state':'open','question':'Q','prediction':'p','steps':steps}]})
        self.ask.return_value=self.choice('schema',{'plugin':'nvmolkit'})
        I.turn('',ask=self.ask,execute=lambda *a:{'schema':{}})
        row=C._load(I._path('investigations.json'),{})['investigations'][0]
        self.assertEqual(row['state'],'stalled'); self.assertIn('step budget',row['closed_reason'])

    def test_turns_that_fail_before_a_step_close_the_investigation(self):
        # 21 October: one open investigation failed 365 turns in a row before making any step; nothing closed it
        C._atomic(I._path('investigations.json'),{'investigations':[{'id':'I-stuck','opened_at':C.now_iso(),
            'state':'open','question':'Q','prediction':'p','steps':[]}]})
        self.ask.return_value='not json at all'
        for n in range(I.MAX_PLANNING_FAILURES):
            with self.assertRaises(Exception):
                I.turn('',ask=self.ask,execute=Mock())
        row=C._load(I._path('investigations.json'),{})['investigations'][0]
        self.assertEqual(row['state'],'stalled')
        self.assertIn('failed before any step',row['closed_reason'])
        self.ask.return_value=self.choice('schema',{'plugin':'nvmolkit'})
        nxt=I.turn('',ask=self.ask,execute=lambda *a:{'schema':{}})
        self.assertNotEqual(nxt['investigation'],'I-stuck')

    def test_a_good_turn_resets_the_count(self):
        C._atomic(I._path('investigations.json'),{'investigations':[{'id':'I-ok','opened_at':C.now_iso(),
            'state':'open','question':'Q','prediction':'p','steps':[],'planning_failures':2}]})
        self.ask.return_value=self.choice('schema',{'plugin':'nvmolkit'})
        I.turn('',ask=self.ask,execute=lambda *a:{'schema':{}})
        row=C._load(I._path('investigations.json'),{})['investigations'][0]
        self.assertEqual(row['state'],'open'); self.assertEqual(row['planning_failures'],0)

    def test_a_long_line_does_not_make_the_planner_prompt_too_large(self):
        # 21 October: a line's whole history (about 116 KB) went into every prompt; every turn failed from 17:36
        line={'id':'L-1','question':'Cystatin C','next_step':'x',
              'steps':[{'question':'q'*300,'result':'r'*1500,'quotes':['v'*400]*5} for _ in range(30)]}
        steps=[{'id':'S-%d'%n,'state':'completed','route':'source','request':{'q':'z'*3000},'summary':'s'*800} for n in range(40)]
        sent=[]
        def ask(system,prompt,**k): sent.append(prompt); return json.dumps({'route':'finish'})
        I._plan({'question':'q','steps':steps,'line_context':line},'x'*3000,ask)
        limit=C._plan_chars('x'*400,max_tokens=800)
        self.assertTrue(sent and len(sent[0].encode())<=limit)
        self.assertEqual(I.line_summary(line)['question'],'Cystatin C')
        self.assertEqual(len(I.line_summary(line)['recent_steps']),3)


if __name__ == '__main__': unittest.main(verbosity=2)
