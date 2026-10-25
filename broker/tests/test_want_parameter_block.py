#!/usr/bin/env python3
"""Exercise the actual router parameter-failure branch and board wake-up, in scratch."""
import ast
import copy
import datetime as dt
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
SCRATCH = tempfile.TemporaryDirectory(prefix='want-parameter-block-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = str(Path(SCRATCH.name)/'.vintos/workspace')
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'scripts'))
import want_board as B

tree = ast.parse((REPO/'bin/wants-router.py').read_text())
branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
              and 'startswith' in ast.unparse(n.test) and "'missing required'" in ast.unparse(n.test))


class ReturnInsteadOfContinue(ast.NodeTransformer):
    def visit_Continue(self, node):
        return ast.copy_location(ast.Return(value=ast.Constant(None)), node)


# The branch normally continues the outer want loop. Run it as a function,
# retaining its actual body and imports but returning to this scratch harness.
body = ReturnInsteadOfContinue().visit(copy.deepcopy(branch))
wrapper = ast.parse('def reject(want, action, _param_problems):\n    pass').body[0]
wrapper.body = [body]
namespace = {'log':Mock(), 'datetime':dt.datetime}
exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),
             'router-parameter-failure-branch', 'exec'), namespace)
validator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='validate_step_params')
schemas = next(n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='PARAM_SCHEMAS' for t in n.targets))
exec(compile(ast.Module(body=[schemas,validator],type_ignores=[]), 'router-validator', 'exec'),namespace)


class ParameterBlock(unittest.TestCase):
    def setUp(self):
        self.path = Path(B.CURRENT)
        self.assertTrue(self.path.is_relative_to(SCRATCH.name))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.now = dt.datetime.now()
        self.want = {'id':'invalid-plan','want':'Format the retained fixture document',
                     'timestamp':self.now.isoformat(),'multistep':True,'current_step_index':0,
                     'budget_used':{'steps_run':2},'authored':'keep me',
                     'steps':[{'capability':'plugin_skill','params':{'plugin':'document',
                               'arguments':{'instruction':'Use the fixture'}},'status':'pending'}]}
        self.write(self.want)
        self.net = patch.object(socket.socket,'connect',side_effect=AssertionError('no network'))
        self.net.start()

    def tearDown(self):
        self.net.stop()

    def write(self,want):
        self.path.write_text(json.dumps([want]))

    def read(self):
        return json.loads(self.path.read_text())[0]

    def reject(self,want=None):
        namespace['reject'](copy.deepcopy(want or self.read()),'plugin_skill',
                            ['missing required parameter: skill','missing required parameter: instruction'])

    def tend(self):
        B.tend(now=self.now,discussions={},age=Mock(side_effect=AssertionError('no aging/model')))

    def test_router_branch_persists_typed_block_without_charging_or_completing(self):
        self.reject()
        row=self.read()
        self.assertEqual(row.get('blocked',{}).get('block_type'),'INVALID_STEP_PARAMS')
        self.assertEqual(row['blocked']['blocked_step'],'plugin_skill')
        self.assertEqual(row['budget_used'],self.want['budget_used'])
        self.assertEqual(row['authored'],'keep me')
        self.assertEqual(row['steps'][0]['status'],'pending')
        self.assertFalse(row.get('fulfilled'))

    def test_unchanged_invalid_step_stays_parked(self):
        self.reject(); self.tend()
        self.assertEqual(self.read().get('board'),'blocked')
        self.tend()
        self.assertEqual(self.read().get('board'),'blocked')

    def test_recent_progress_does_not_reexecute_a_deterministically_invalid_step(self):
        row=self.read();row['step_history']=[{'completed_at':self.now.isoformat()}]
        self.write(row);self.reject();self.tend()
        self.assertEqual(self.read().get('board'),'blocked')

    def test_unrelated_metadata_revision_does_not_clear_parameter_block(self):
        self.reject();self.tend()
        row=self.read();row['intensity']=5;row['steps'][0]['note']='Reworded fixture note'
        self.write(row);self.tend()
        self.assertEqual(self.read()['blocked']['block_type'],'INVALID_STEP_PARAMS')
        self.assertEqual(self.read().get('board'),'blocked')

    def test_revised_params_wake_the_want_and_validate(self):
        self.reject(); self.tend()
        row=self.read();row['steps'][0]['params']={'skill':'pdf','instruction':'Use the fixture'}
        self.write(row);self.tend();row=self.read()
        self.assertNotIn('blocked',row)
        self.assertFalse(row.get('board'))
        clean,problems=namespace['validate_step_params']('plugin_skill',row['steps'][0]['params'])
        self.assertEqual(problems,[]);self.assertEqual(clean,row['steps'][0]['params'])

    def test_stale_validation_does_not_block_a_concurrently_revised_plan(self):
        old=self.read();row=self.read()
        row['steps'][0]['params']={'skill':'pdf','instruction':'Already corrected'}
        self.write(row);self.reject(old)
        self.assertNotIn('blocked',self.read())

    def test_stale_validation_does_not_block_a_concurrently_completed_step(self):
        old=self.read();row=self.read();row['steps'][0]['status']='completed'
        self.write(row);self.reject(old)
        self.assertNotIn('blocked',self.read())

    def test_existing_capability_block_is_preserved(self):
        row=self.read();row['blocked']={'block_type':'CAPABILITY_ABSENT','evidence':'fixture'}
        self.write(row);self.reject()
        self.assertEqual(self.read()['blocked'],row['blocked'])

    def test_ended_want_cannot_be_reblocked(self):
        for key in ('fulfilled','dismissed'):
            row=copy.deepcopy(self.want);row[key]=True;self.write(row);self.reject()
            self.assertNotIn('blocked',self.read())

    def test_repeated_forced_validation_preserves_original_block_time(self):
        self.reject();block=self.read().get('blocked')
        self.assertIsNotNone(block)
        self.reject();self.assertEqual(self.read()['blocked'],block)


if __name__=='__main__':
    unittest.main(verbosity=2)
