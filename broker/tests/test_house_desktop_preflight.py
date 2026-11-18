"""Board approvals bind to independently checked inputs and one computer; offline only."""
import copy
import json
import os
import socket
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HOME = tempfile.TemporaryDirectory()
os.environ.update(HOME=HOME.name, SPARK_WORKSPACE=HOME.name+'/workspace')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
def no_network(*args, **kwargs): raise AssertionError('network is forbidden')
socket.socket.connect = no_network
import house_context as H
import house_boards as B


class DesktopPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HOME.name)
        self.addCleanup(self.temp.cleanup)
        self.mem = Path(self.temp.name)
        self.patch = patch.object(H, 'MEM', self.mem)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.write('desktop-target.json', {'target':'imac', 'ssh_host':'fixture',
                                         'python':'/Users/fixture/helper-python', 'root':'/Users/fixture/helper'})
        self.write('current-wants.json', [{'id':'research', 'want':'compare the document files'}])
        self.plan = {'target':'imac', 'kind':'native', 'task':'compare the document files',
                     'inputs':['/Users/fixture/research/test.py'], 'environment':'/Users/fixture/venv/bin/python',
                     'done_when':'comparison is saved and visible', 'want_id':'research'}
        self.probe = patch.object(H, '_desktop_inputs_available', return_value=None)
        self.checked = self.probe.start(); self.addCleanup(self.probe.stop)
        self.assertTrue(self.mem.is_relative_to(Path(HOME.name)))
        self.asks = []
        self.sender = types.SimpleNamespace(ask=lambda question, **kw: (self.asks.append(question) or {'id':'Q-fixture'}, 'asked'))

    def write(self, name, data): (self.mem/name).write_text(json.dumps(data))

    def act(self, value):
        state = {'desktop':[]}
        with patch.dict(sys.modules, gloria_asks=self.sender):
            result = B.act('DESKTOP', value, 'office', 'house-touch', state, 100, B.DEFAULTS)
        return result, state

    def test_original_vague_calculation_does_not_notify(self):
        result, state = self.act('run AllSinglesDoubles from hf_state and compare against frozen-core column')
        self.assertFalse(result[0]); self.assertFalse(self.asks); self.assertFalse(state['desktop'])
        self.checked.assert_not_called()

    def test_aegis_files_are_not_assumed_to_exist_on_imac(self):
        self.plan['inputs'] = ['/home/gloria/.vintos/workspace/research/test.py']
        result, _ = self.act(json.dumps(self.plan))
        self.assertFalse(result[0]); self.assertFalse(self.asks); self.checked.assert_not_called()

    def test_question_discloses_target_files_runtime_and_result(self):
        result, state = self.act(json.dumps(self.plan))
        self.assertTrue(result[0]); self.checked.assert_called_once()
        for part in ('iMac', self.plan['inputs'][0], self.plan['environment'], self.plan['done_when']):
            self.assertIn(part, self.asks[0])
        self.assertEqual(state['desktop'][0]['preflight']['plan'], self.plan)

    def test_absent_inputs_prevent_approval(self):
        self.checked.side_effect = ValueError('required files or runtime absent')
        result, _ = self.act(json.dumps(self.plan))
        self.assertFalse(result[0]); self.assertFalse(self.asks)

    def test_held_or_owned_source_is_neither_suggested_nor_relaunched(self):
        for work in ({'blocked':{'reason':'per_want_call_cap'}}, {'status':'in_work'}, {'status':'queued'}):
            self.write('current-wants.json', [{'id':'research','want':'compare the document files','agent_work':work}])
            self.assertEqual(H.action_candidates('house-touch', []), [])
            result, _ = self.act(json.dumps(self.plan))
            self.assertFalse(result[0]); self.assertFalse(self.asks)

    def test_approved_legacy_ask_never_launches(self):
        state = {'desktop':[{'ask':'Q-21d0871a','task':'old calculation','at':100}]}
        sender = types.SimpleNamespace(get=lambda _: {'state':'answered','answer':'yes'})
        control = types.SimpleNamespace(start_from_chat=no_network)
        with patch.dict(sys.modules, gloria_asks=sender, desktop_control=control):
            B.tend_desktop(state, 101)
        self.assertEqual(state['desktop'][0]['status'], 'needs_preflight')
        old = {'id':'Q-21d0871a','question':'old calculation','ref':'house-desktop:100'}
        self.assertFalse(B.desktop_ask_current(old, state))

    def test_source_goal_change_after_approval_requires_new_approval(self):
        prepared = H.desktop_preflight(self.plan)
        state = {'desktop':[{'ask':'Q-fixture','preflight':prepared,'at':100}]}
        self.write('current-wants.json', [{'id':'research','want':'compare a different document'}])
        sender = types.SimpleNamespace(get=lambda _: {'state':'answered','answer':'yes','question':prepared['question']})
        with patch.dict(sys.modules, gloria_asks=sender, desktop_control=types.SimpleNamespace(start_from_chat=no_network)):
            B.tend_desktop(state, 101)
        self.assertEqual(state['desktop'][0]['status'], 'preflight_blocked')

    def test_target_change_or_disappearing_runtime_prevents_launch(self):
        prepared = H.desktop_preflight(self.plan)
        sender = types.SimpleNamespace(get=lambda _: {'state':'answered','answer':'yes','question':prepared['question']})
        for scenario in ('target', 'runtime'):
            state = {'desktop':[{'ask':'Q-fixture','task':prepared['task'],'preflight':copy.deepcopy(prepared),'at':100}]}
            if scenario == 'target': self.write('desktop-target.json', {'target':'aegis'})
            else:
                self.write('desktop-target.json', {'target':'imac','ssh_host':'fixture','python':'/Users/fixture/helper-python','root':'/Users/fixture/helper'})
                self.checked.side_effect = ValueError('runtime disappeared')
            with patch.dict(sys.modules, gloria_asks=sender, desktop_control=types.SimpleNamespace(start_from_chat=no_network)):
                B.tend_desktop(state, 101)
            self.assertIn(state['desktop'][0]['status'], ('needs_preflight','preflight_blocked'))

    def test_no_ssh_back_to_aegis_and_no_truncated_disclosure(self):
        self.plan['task'] = 'SSH to Aegis and run the comparison'
        with self.assertRaises(ValueError): H.desktop_preflight(self.plan)
        self.plan['task'] = 'compare files'
        self.plan['inputs'] = ['/Users/fixture/'+('x'*250)]*5
        with self.assertRaises(ValueError): H.desktop_preflight(self.plan)

    def test_real_probe_checks_files_and_executable_without_running_task(self):
        self.probe.stop()
        calls = []
        def ssh(command, **kwargs):
            calls.append((command, kwargs))
            return types.SimpleNamespace(returncode=0, stdout=b'{"inputs":true,"runtime":true}')
        with patch.dict(sys.modules, browser_mac=types.SimpleNamespace(_ssh=ssh)):
            H.desktop_preflight(self.plan)
        command, kwargs = calls[0]
        self.assertIn('os.path.isfile', command); self.assertIn('os.access', command)
        self.assertNotIn(self.plan['task'], command)
        self.assertEqual(kwargs['timeout'], 7)
        self.assertEqual(json.loads(kwargs['input'])['inputs'], self.plan['inputs'])


if __name__ == '__main__': unittest.main()
