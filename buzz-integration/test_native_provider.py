"""Offline regression checks: scratch registry and a stubbed service executor."""
import copy
import importlib.machinery
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

provider = importlib.machinery.SourceFileLoader('aegis_provider', str(Path(__file__).with_name('buzz-backend-aegis'))).load_module()
registration = importlib.machinery.SourceFileLoader('aegis_registration', str(Path(__file__).with_name('register-native.py'))).load_module()


class RegistrationTests(unittest.TestCase):
    def test_repeat_registration_preserves_identity_receipt_and_other_agents(self):
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch)
            store = home / '.local/share/xyz.block.buzz.app/agents/managed-agents.json'
            store.parent.mkdir(parents=True)
            original = dict(pubkey='existing', private_key_nsec='fixture-existing', name='Existing')
            store.write_text(json.dumps([original]))
            identity = home / '.config/buzz/agents/gemma'
            identity.mkdir(parents=True)
            (identity / 'key.hex').write_text('fixture-gemma')
            (identity / 'auth.json').write_text('fixture-attestation')
            (identity / 'public.json').write_text(json.dumps(dict(pubkey='gemma-fixture', owner='owner-fixture')))
            manifest = [dict(id='gemma', name='Gemma', model='fixture-model', provider='fixture', instructions='Fixture only')]
            assert store.is_relative_to(home) and identity.is_relative_to(home)
            self.assertEqual(registration.register(home, manifest), 1)
            rows = json.loads(store.read_text())
            instance = next(r for r in rows if r.get('pubkey') == 'gemma-fixture')
            self.assertIsNone(instance['backend_agent_id'])
            instance['backend_agent_id'] = 'verified-fixture-receipt'
            store.write_text(json.dumps(rows))
            registration.register(home, manifest)
            rows = json.loads(store.read_text())
            self.assertEqual(len(rows), 3)
            self.assertIn(original, rows)
            definition = next(r for r in rows if not r.get('pubkey'))
            instance = next(r for r in rows if r.get('pubkey') == 'gemma-fixture')
            self.assertEqual(instance['persona_id'], definition['slug'])
            self.assertEqual(instance['private_key_nsec'], 'fixture-gemma')
            self.assertEqual(instance['backend_agent_id'], 'verified-fixture-receipt')
            self.assertFalse(instance['start_on_app_launch'])
            self.assertEqual(definition['private_key_nsec'], '')
            self.assertEqual(store.stat().st_mode & 0o777, 0o600)
            self.assertEqual((home / '.config/buzz/native-registration.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(store.parent.glob('managed-agents.before-aegis-*.json'))), 2)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / 'registry.json'
        self.row = dict(id='gemma', private_key_nsec='fixture-secret', auth_tag='fixture-auth',
                        relay_url='ws://fixture.invalid', model='fixture-model', provider='fixture',
                        system_prompt='fixture prompt', owner_pubkey='fixture-owner',
                        agent_command='buzz-agent', agent_args=[])
        self.path.write_text(json.dumps([self.row]))
        self.agent = {k: v for k, v in self.row.items() if k not in ('id', 'owner_pubkey')}
        self.agent.update(respond_to='owner-only', respond_to_allowlist=[], parallelism=1,
                          env_vars={}, launch=dict(command='buzz-agent', args=[], env={}, owner_pubkey='fixture-owner'))
        self.run = Mock(side_effect=[subprocess.CompletedProcess([], 0, ''), subprocess.CompletedProcess([], 0, 'active\n')])
        assert self.path.is_relative_to(Path(self.scratch.name)) and isinstance(self.run, Mock)

    def call(self, agent=None):
        return provider.dispatch(dict(op='deploy', provider_config={}, agent=agent or self.agent), self.path, self.run)

    def test_installed_identity_starts_only_fixed_unit(self):
        self.assertEqual(self.call()['agent_id'], 'buzz-gemma.service')
        self.assertEqual(self.run.call_args_list[0].args[0], ['systemctl', 'start', 'buzz-gemma.service'])

    def test_all_identity_policy_and_config_changes_fail_before_execution(self):
        for field, value in [('private_key_nsec', 'other'), ('model', 'paid-model'), ('auth_tag', 'other'),
                             ('relay_url', 'ws://other.invalid'), ('provider', 'other'), ('system_prompt', 'other'),
                             ('respond_to', 'anyone'), ('parallelism', 2), ('env_vars', {'SECRET': 'fixture'})]:
            with self.subTest(field=field):
                agent = copy.deepcopy(self.agent)
                agent[field] = value
                with self.assertRaises(ValueError): self.call(agent)
        self.run.assert_not_called()

    def test_launch_override_fails_before_execution(self):
        for field, value in [('command', '/bin/sh'), ('args', ['-c', 'bad']), ('owner_pubkey', 'other'), ('env', {'PATH': '/bad'})]:
            agent = copy.deepcopy(self.agent)
            agent['launch'][field] = value
            with self.assertRaises(ValueError): self.call(agent)
        self.run.assert_not_called()

    def test_native_derived_model_env_is_accepted_but_cannot_change_model(self):
        self.agent['launch']['env'] = {'BUZZ_AGENT_MODEL': 'fixture-model', 'BUZZ_AGENT_PROVIDER': 'fixture'}
        self.assertTrue(self.call()['ok'])
        self.run.reset_mock()
        self.agent['launch']['env']['BUZZ_AGENT_MODEL'] = 'another-model'
        with self.assertRaises(ValueError): self.call()
        self.run.assert_not_called()

    def test_failed_or_inactive_unit_is_not_success(self):
        for results in [[subprocess.CompletedProcess([], 1, '', 'fixture-secret')],
                        [subprocess.CompletedProcess([], 0, ''), subprocess.CompletedProcess([], 3, 'inactive')]]:
            self.run.side_effect = results
            with self.assertRaises(ValueError) as raised: self.call()
            self.assertNotIn('fixture-secret', str(raised.exception))

    def test_info_needs_no_registry_or_executor(self):
        self.assertEqual(provider.dispatch({'op': 'info'}, Path('/does-not-exist'), self.run)['protocol_version'], 1)
        self.run.assert_not_called()


if __name__ == '__main__': unittest.main()
