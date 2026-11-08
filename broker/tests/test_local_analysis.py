#!/usr/bin/env python3
"""Synthetic artifacts only; real child runs use OS isolation, never providers."""
import ast
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import local_analysis as L


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-analysis-test-')
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name).resolve()
        self.art = self.ws / 'memory/art'; self.art.mkdir(parents=True)
        self.input = self.art / 'fixture.json'
        self.input.write_text('{"values":[2,4,6]}')
        self.assertNotIn('.vintos', self.ws.parts)
        self.env = patch.dict(os.environ, SPARK_WORKSPACE=str(self.ws))
        self.env.start(); self.addCleanup(self.env.stop)
        self.job = {'code': 'import json\nv=json.load(open(inputs["data.json"]))["values"]\n(output_dir / "answer.json").write_text(json.dumps({"sum":sum(v)}))',
                    'inputs': {'data.json':'memory/art/fixture.json'},
                    'outputs': {'answer.json': {'kind':'json','required_keys':['sum']}}}

    def run_job(self, **kwargs): return L.run(self.job, 'fixture-want', workspace=self.ws, **kwargs)

    def test_real_isolated_execution_and_verified_reuse(self):
        before = self.input.read_bytes()
        result = self.run_job()
        self.assertEqual(result['status'], 'SUCCEEDED', result)
        self.assertEqual(self.input.read_bytes(), before)
        output = Path(result['receipt']).parent / 'artifacts/answer.json'
        self.assertEqual(json.loads(output.read_text()), {'sum':12})
        self.assertEqual(result['scientific_validation'], 'not_asserted')
        def forbidden(*a, **k): self.fail('verified exact job was rerun')
        again = self.run_job(runner=forbidden)
        self.assertTrue(again['reused'])
        output.write_text('{"sum":13}')
        self.assertEqual(self.run_job(runner=forbidden)['status'], 'BLOCKED')

    def test_real_preparation_produces_audio_score_and_bar_table(self):
        self.job['code'] = '''import wave, struct, math
with wave.open(str(output_dir / 'excerpt.wav'), 'wb') as f:
 f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
 f.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*i/8000))) for i in range(800)))
(output_dir / 'score.txt').write_text('Synthetic score: one test tone. No musical accuracy claim.')
(output_dir / 'bars.csv').write_text('bar,status\\n1,needs_listener\\n')
'''
        self.job['outputs'] = {'excerpt.wav':{'kind':'wav'}, 'score.txt':{'kind':'text'},
                               'bars.csv':{'kind':'csv','required_columns':['bar','status']}}
        result = self.run_job()
        self.assertEqual(result['status'], 'SUCCEEDED', result)
        self.assertEqual(len(result['artifacts']), 3)

    def test_child_cannot_write_outside_its_scratch(self):
        outside = self.ws / 'do-not-write.txt'
        self.job['code'] = 'open(%r,"w").write("forbidden")' % str(outside)
        result = self.run_job()
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(outside.exists())

    def test_child_cannot_read_unlisted_private_input(self):
        private = self.ws / 'private.txt'; private.write_text('synthetic private sentinel')
        self.job['code'] = '(output_dir / "answer.json").write_text(open(%r).read())' % str(private)
        result = self.run_job()
        self.assertEqual(result['status'], 'FAILED')
        self.assertNotIn('synthetic private sentinel', json.dumps(result))

    def test_child_cannot_send(self):
        # Connection attempt is denied by the OS sandbox; no service or listener.
        self.job['code'] = 'import socket\nsocket.create_connection(("127.0.0.1",9),timeout=1)'
        self.assertEqual(self.run_job()['status'], 'FAILED')

    def test_no_file_is_not_success_even_with_stdout_claim(self):
        self.job['code'] = 'print("I did it")'
        result = self.run_job()
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['artifacts'], [])
        self.assertTrue(Path(result['receipt']).is_file())

    def test_output_parent_symlink_cannot_make_parent_read_private_files(self):
        private = self.ws / 'private'; private.mkdir(); (private / 'answer.json').write_text('{"sum":99}')
        self.job['code'] = 'output_dir.rmdir()\noutput_dir.symlink_to(%r)' % str(private)
        result = self.run_job()
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['artifacts'], [])

    def test_missing_tool_error_is_retained_and_exact_failure_not_rerun(self):
        self.job['code'] = 'import fixture_missing_analysis_library'
        result = self.run_job()
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('fixture_missing_analysis_library', Path(result['receipt']).with_name('stderr.txt').read_text())
        def forbidden(*a, **k): self.fail('unchanged failed program rerun')
        again = self.run_job(runner=forbidden)
        self.assertEqual(again['status'], 'BLOCKED'); self.assertTrue(again['reused'])

    def test_bad_paths_missing_inputs_and_bad_contract_do_not_launch(self):
        def forbidden(*a, **k): self.fail('invalid contract launched')
        examples = [dict(self.job,inputs={'x':'memory/current-wants.json'}),
                    dict(self.job,inputs={'x':'../secret'}),dict(self.job,inputs={'x':'/etc/passwd'}),
                    dict(self.job,outputs={'../answer.json':{'kind':'json'}}),dict(self.job,outputs={}),
                    dict(self.job,code=''),dict(self.job,outputs={'x':{'kind':'invented'}})]
        for spec in examples:
            self.assertEqual(L.run(spec,'fixture-want',workspace=self.ws,runner=forbidden)['status'], 'BLOCKED')
        alias = self.art / 'alias.json'; alias.symlink_to(self.input)
        spec = dict(self.job,inputs={'x':'memory/art/alias.json'})
        self.assertEqual(L.run(spec,'fixture-want',workspace=self.ws,runner=forbidden)['status'], 'BLOCKED')

    def test_failed_output_shape_and_nonzero_exit_never_succeed(self):
        for code in ('(output_dir / "answer.json").write_text("{}")', 'raise RuntimeError("synthetic fault")'):
            self.job['code'] = code
            self.assertEqual(self.run_job()['status'], 'FAILED')

    def test_timeout_is_durable_failure(self):
        def expired(*a, **k): raise TimeoutError('synthetic timeout')
        result = self.run_job(runner=expired)
        self.assertEqual(result['status'], 'FAILED')
        self.assertTrue(Path(result['receipt']).exists())

    def test_same_job_is_locked_and_results_are_bound_to_want(self):
        entered, release = threading.Event(), threading.Event()
        def controlled(argv, scratch, **kw):
            entered.set(); self.assertTrue(release.wait(3))
            (Path(scratch)/'outputs/answer.json').write_text('{"sum":12}')
            return types.SimpleNamespace(returncode=0,stdout='',stderr='')
        result=[]
        t=threading.Thread(target=lambda:result.append(self.run_job(runner=controlled)));t.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.run_job(runner=controlled)['status'],'RUNNING')
        finally: release.set();t.join(4)
        self.assertEqual(result[0]['status'],'SUCCEEDED')
        other=L.run(self.job,'fixture-other',workspace=self.ws,runner=controlled)
        self.assertNotEqual(other['job_id'],result[0]['job_id'])

    def test_receipt_retention_refuses_changed_step_and_never_fulfills(self):
        step={'capability':'local_analysis','params':copy.deepcopy(self.job),'status':'pending'}
        want={'id':'fixture-want','want':'Synthetic analysis','steps':[step],'current_step_index':0,'fulfilled':False}
        path=self.ws/'memory/current-wants.json';path.write_text(json.dumps([want]))
        result=self.run_job()
        self.assertTrue(L.retain_result(want,result,str(path)))
        row=json.loads(path.read_text())[0]
        self.assertFalse(row['fulfilled']);self.assertEqual(row['steps'][0]['status'],'pending')
        row['steps'][0]['params']['code']='revised';path.write_text(json.dumps([row]))
        self.assertFalse(L.retain_result(want,result,str(path)))

    def test_actual_router_only_advances_bound_successful_receipt(self):
        tree=ast.parse((ROOT/'bin/wants-router.py').read_text())
        branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and any(
            isinstance(a,ast.ImportFrom) and a.module=='local_analysis' and any(x.name=='retain_result' for x in a.names)
            for a in n.body))
        function=ast.FunctionDef(name='exercise',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='success')],kwonlyargs=[],kw_defaults=[],defaults=[]),
            body=[ast.For(target=ast.Name(id='_',ctx=ast.Store()),iter=ast.List(elts=[ast.Constant(1)],ctx=ast.Load()),
              body=[copy.deepcopy(branch)]+ast.parse('advanced.append(success)').body,orelse=[])],decorator_list=[])
        code=compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),'real-router-analysis-branch','exec')
        for status,retained in [('SUCCEEDED',True),('FAILED',True),('BLOCKED',True),('SUCCEEDED',False)]:
            advanced=[];ns={'action':'local_analysis','success':{'status':status,'findings':'checked artifact'},
                           '_agent_request':lambda *a,**k:None,'want':{},'os':os,'MEMORY':str(self.ws/'memory'),'log':lambda *a:None,'advanced':advanced}
            with patch.object(L,'retain_result',return_value=retained):
                exec(code,ns);ns['exercise'](ns['success'])
            self.assertEqual(bool(advanced),status=='SUCCEEDED' and retained)

    def test_inventory_is_artifacts_only(self):
        (self.ws/'memory/private.txt').write_text('not an artifact')
        menu=L.artifact_menu(self.ws)
        self.assertIn('memory/art/fixture.json',menu)
        self.assertNotIn('private.txt',menu)

if __name__=='__main__': unittest.main(verbosity=2)
