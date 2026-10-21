"""Native invocations, daily variety and window accounting; scratch stores, no sends."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_lab_tool_routing as sandbox
import lab_native_instruments as native
import lab_usage_report as usage
import lab_instruments as instruments
import chemistry_session as session


class RuntimePaths(unittest.TestCase):
    def setUp(self):
        self.assertTrue(instruments.LAB.is_relative_to(sandbox.SCRATCH))
        self.assertIs(sandbox.socket.socket.connect,sandbox.SEND)

    def tearDown(self):sandbox.SEND.assert_not_called()

    def test_daily_planner_keeps_all_other_offered_experiments_after_repeated_protein(self):
        offered={x:x for x in ['protein','molecule','fold','titrate']}
        recent=[{'experiment':'protein'}]*14
        self.assertEqual(set(session.experiment_choices(offered,recent)),{'molecule','fold','titrate'})
        self.assertEqual(session.experiment_choices({'protein':'only available'},recent),{'protein':'only available'})
        self.assertEqual(session.experiment_choices(offered,[]),offered)

    def test_native_design_uses_retained_input_and_requires_a_real_output(self):
        source=instruments.ARTIFACTS/'esmfold/input.pdb';source.parent.mkdir(parents=True,exist_ok=True)
        source.write_text('ATOM  fixture')
        req={'skill':'protein_mpnn','operation':'sequence.design','files':[str(source.relative_to(instruments.LAB))]}
        def runner(argv,**kwargs):
            self.assertIn(str(source),argv)
            self.assertEqual(argv[argv.index('--num_seq_per_target')+1],'1')
            out=Path(argv[argv.index('--out_folder')+1]);(out/'designed.fa').write_text('>source\nMAAA\n>designed\nMAVA\n')
            return SimpleNamespace(returncode=0,stderr='')
        result=native.run(req,runner=runner)
        self.assertTrue(result['ok']);self.assertEqual(len(result['inputs']),1)
        self.assertEqual(len(result['files']),1)
        with self.assertRaisesRegex(RuntimeError,'artifact absent'):
            native.run(req,runner=lambda *a,**k:SimpleNamespace(returncode=0,stderr=''))
        with self.assertRaises(ValueError):native.run(dict(req,samples=100),runner=runner)
        with self.assertRaises(ValueError):native.run(dict(req,files=['/etc/passwd']),runner=runner)

    def test_actual_titrate_and_toy_fold_output_shapes_are_graded_in_model_units(self):
        import chemistry_grade as grade
        run={'ok':True,'run':{'result':{'curve':[{'value':0.0,'energy':-2.0,'exact_energy':-2.0},
                                               {'value':0.3,'energy':-1.1,'exact_energy':-1.1}]}}}
        row=grade.grade('TOY-CURVE','titrate',run)
        self.assertEqual(row['graded_points'],2)
        self.assertEqual(row['aggregate_accuracy'],'MATCHED_LATTICE_REFERENCE')
        self.assertEqual(row['energy_units'],'bench_model_units_not_hartree')
        fold={'ok':True,'run':{'result':{'best_fold':{'energy':-1.55},'likeliest_fold':{'energy':2.45}}}}
        row=grade.grade('TOY-FOLD','fold',fold)
        self.assertEqual(row['points'][0]['gap'],4.0)
        self.assertEqual(row['aggregate_accuracy'],'LATTICE_REFERENCE_GAP')

    def test_account_discovery_has_separate_route_and_no_model_query(self):
        import claude_connector_gateway as gateway
        requests=[]
        out=gateway.tool_schemas('boltz',transport=lambda r:(requests.append(r) or {'ok':True,'schemas':{},'tools':{}}))
        self.assertEqual(requests,[{'action':'schema','plugin':'boltz','surface':'lab'}])
        self.assertTrue(out['ok'])

    def test_report_deduplicates_phase_projection_and_counts_only_completed_reference_use(self):
        root=sandbox.SCRATCH/'usage';root.mkdir(exist_ok=True)
        t='2026-10-22T01:00:00+00:00'
        (root/'source-receipts.jsonl').write_text(json.dumps({'retrieved_at':t,'source':'uniprot','receipt_id':'r'})+'\n')
        steps=[{'id':'S-source','at':t,'state':'completed','route':'source','tool':'source:uniprot','origin':'autonomous_lab'},
               {'id':'S-embed','at':t,'state':'completed','route':'embed','tool':'representation','origin':'autonomous_phase',
                'input_refs':[{'step':'S-source','path':['normalized_records']}]},
               {'id':'S-failed','at':t,'state':'outcome_unknown','route':'plugin','tool':'plugin:boltz','origin':'autonomous_lab',
                'input_refs':[{'step':'S-embed','path':[]}]}]
        (root/'investigations.json').write_text(json.dumps({'investigations':[{'id':'I-test','question':'Keep question','steps':steps}]}))
        r=usage.report(root,'2026-10-22T00:00:00+00:00','2026-10-24T00:00:00+00:00')
        self.assertEqual(r['tools']['source:uniprot']['explicit_downstream_uses'],1)
        self.assertEqual(r['tools']['representation']['explicit_downstream_uses'],0) if 'representation' in r['tools'] else None
        self.assertEqual(r['tools']['plugin:boltz']['failed_or_unknown'],1)
        self.assertEqual(len(r['chains'][0]['links']),1)


if __name__=='__main__':unittest.main(verbosity=2)
