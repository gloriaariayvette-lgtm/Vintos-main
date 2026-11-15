#!/usr/bin/env python3
"""Aegis's house model (Gloria, 14 November 2026): the Lab planner worm (lab-c1) is the one 12B model on the card; plain
AEON (aeon/gemma-4-12b) is loaded in its place only for the causality window, with the Lab paused, and the worm comes
back after whatever happens. AEGIS_HOUSE_MODEL=worm is the switch; without it the house model is AEON.

LM Studio's CLI and curl are fakes in a scratch PATH; nothing here reaches LM Studio, the GPU or the network."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOADER = os.path.join(REPO, 'scripts', 'aegis-gemma-load.sh')
WINDOW = os.path.join(REPO, 'scripts', 'aegis-model-window.sh')
AEON, WORM, EMBED = 'aeon/gemma-4-12b', 'lab-c1', 'text-embedding-nomic-embed-text-v1.5'

FAKE_LMS = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_LMS_STATE"]
s = json.load(open(state))
a = sys.argv[1:]
def save(): json.dump(s, open(state, "w"))
s.setdefault("log", []).append(" ".join(a)); save()
if a[:2] == ["ls", "--json"]:
    print(json.dumps(s["installed"]))
elif a[:2] == ["ps", "--json"]:
    print(json.dumps([{"identifier": i, "type": "embedding" if "embed" in i else "llm"} for i in s["resident"]]))
elif a[:1] == ["unload"]:
    s["resident"] = [i for i in s["resident"] if i != a[1]]; save()
elif a[:1] == ["load"]:
    if s.get("fail_load"): sys.exit(1)
    ident = a[a.index("--identifier") + 1]
    s["resident"].append(ident)
    if s.get("late"): s["resident"].append(s.pop("late"))       # a cut-off load that lands anyway
    s["loaded_keys"] = s.get("loaded_keys", []) + [a[1]]; save()
'''
INSTALLED = [
    {"modelKey": "gemma-4-12b-it-aeon-abliterated-k4", "architecture": "gemma4",
     "path": "mradermacher/Gemma-4-12B-it-AEON-Abliterated-K4-BF16-GGUF/Gemma-4-12B-it-AEON-Abliterated-K4-BF16.Q4_K_M.gguf",
     "quantization": {"name": "Q4_K_M", "bits": 4}, "sizeBytes": 7381383520},
    {"modelKey": "lab-c1-gemma-4-12b-aeon", "architecture": "gemma4",
     "path": "vintos/lab-c1-gemma-4-12b-aeon-GGUF/lab-c1-gemma-4-12b-aeon.Q4_K_M.gguf",
     "quantization": {"name": "Q4_K_M", "bits": 4}, "sizeBytes": 7381381760},
]


class House(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='aegis-house-')
        self.bin = os.path.join(self.tmp, 'bin'); os.makedirs(self.bin)
        self.mem = os.path.join(self.tmp, 'memory'); os.makedirs(self.mem)
        lms = os.path.join(self.bin, 'lms'); open(lms, 'w').write(FAKE_LMS); os.chmod(lms, 0o755)
        curl = os.path.join(self.bin, 'curl'); open(curl, 'w').write('#!/bin/sh\nexit 0\n'); os.chmod(curl, 0o755)
        self.state = os.path.join(self.tmp, 'lms.json')
        self.envfile = os.path.join(self.tmp, 'vintos.env')
        self.set_state(resident=[EMBED, AEON])
        self.house('worm')

    def set_state(self, **kw):
        s = {"installed": INSTALLED, "resident": [EMBED, AEON]}
        s.update(kw)
        json.dump(s, open(self.state, 'w'))

    def lms(self):
        return json.load(open(self.state))

    def house(self, value):
        open(self.envfile, 'w').write('OTHER=1\n' + ('AEGIS_HOUSE_MODEL=%s\n' % value if value else ''))

    def env(self, **kw):
        e = {k: v for k, v in os.environ.items() if k not in ('AEGIS_HOUSE_MODEL', 'AEGIS_MODEL_WINDOW')}
        e.update(PATH=self.bin + ':' + e.get('PATH', '/usr/bin:/bin'), FAKE_LMS_STATE=self.state,
                 VINTOS_LMS_CLI=os.path.join(self.bin, 'lms'), VINTOS_ENV_FILE=self.envfile, HOME=self.tmp,
                 AEGIS_WINDOW_STATE=os.path.join(self.mem, 'aegis-model-window.json'), AEGIS_WINDOW_MEM=self.mem,
                 AEGIS_WINDOW_LOG=os.path.join(self.tmp, 'window.log'), AEGIS_MODEL_LOG=os.path.join(self.tmp, 'model.log'),
                 AEGIS_MODEL_LOADER=LOADER)
        e.update(kw)
        return e

    def run_(self, argv, **kw):
        return subprocess.run(argv, env=self.env(**kw), capture_output=True, text=True, timeout=60)

    def which(self, **kw):
        return self.run_(['bash', LOADER, '--which'], **kw).stdout.strip()

    # --- which model ------------------------------------------------------------------------------------------------
    def test_the_switch_names_the_house_model_and_unset_is_aeon(self):
        self.assertEqual(self.which(), WORM)
        self.house('aeon'); self.assertEqual(self.which(), AEON)
        self.house(None); self.assertEqual(self.which(), AEON)
        self.house('nonsense'); self.assertEqual(self.which(), AEON)
        self.assertEqual(self.which(AEGIS_HOUSE_MODEL='worm'), WORM)   # the environment first

    def test_a_live_window_means_aeon_and_a_dead_or_late_one_is_ignored(self):
        st = os.path.join(self.mem, 'aegis-model-window.json')
        json.dump({'pid': os.getpid(), 'until': time.time() + 600}, open(st, 'w'))
        self.assertEqual(self.which(), AEON)
        json.dump({'pid': os.getpid(), 'until': time.time() - 1}, open(st, 'w'))
        self.assertEqual(self.which(), WORM)
        dead = subprocess.Popen(['true']); dead.wait()
        json.dump({'pid': dead.pid, 'until': time.time() + 600}, open(st, 'w'))
        self.assertEqual(self.which(), WORM)

    # --- loading ----------------------------------------------------------------------------------------------------
    def test_load_puts_the_worm_alone_on_the_card(self):
        r = self.run_(['bash', LOADER])
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.lms()
        self.assertEqual(sorted(s['resident']), sorted([EMBED, WORM]))
        log = s['log']
        self.assertLess(log.index('unload ' + AEON), next(i for i, l in enumerate(log) if l.startswith('load ')))
        self.assertIn('lab-c1-gemma-4-12b-aeon', s['loaded_keys'])

    def test_a_late_landing_load_is_swept_off(self):
        self.set_state(resident=[EMBED, AEON], late=AEON)
        self.assertEqual(self.run_(['bash', LOADER]).returncode, 0)
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, WORM]))

    def test_a_worm_artifact_that_is_not_the_sealed_file_means_aeon_not_an_empty_card(self):
        bad = [dict(INSTALLED[0]), dict(INSTALLED[1], sizeBytes=1)]
        self.set_state(installed=bad, resident=[EMBED, WORM])
        self.assertEqual(self.run_(['bash', LOADER]).returncode, 0)
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, AEON]))

    def test_unload_leaves_only_the_embedding_model(self):
        self.set_state(resident=[EMBED, WORM, 'something-odd'])
        self.assertEqual(self.run_(['bash', LOADER, '--unload']).returncode, 0)
        self.assertEqual(self.lms()['resident'], [EMBED])

    # --- the causality window ---------------------------------------------------------------------------------------
    def window(self, *cmd, **kw):
        return self.run_(['bash', WINDOW] + list(cmd), **kw)

    def test_window_runs_the_command_on_aeon_and_puts_the_worm_back(self):
        self.set_state(resident=[EMBED, WORM])
        probe = os.path.join(self.tmp, 'during.json')
        r = self.window('sh', '-c', 'cp "$FAKE_LMS_STATE" %s; echo "$AEGIS_MODEL_WINDOW" > %s.held' % (probe, probe))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(json.load(open(probe))['resident']), sorted([EMBED, AEON]))
        self.assertEqual(open(probe + '.held').read().strip(), 'held')
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, WORM]))
        self.assertFalse(os.path.exists(os.path.join(self.mem, 'aegis-model-window.json')))
        log = open(os.path.join(self.tmp, 'window.log')).read()
        for line in ('Lab paused', 'window open', 'AEON loaded', 'command ended rc=0', 'house model back: lab-c1',
                     'Lab resumed'):
            self.assertIn(line, log)

    def test_a_failing_command_still_gets_the_worm_back_and_keeps_its_exit_code(self):
        self.set_state(resident=[EMBED, WORM])
        r = self.window('sh', '-c', 'exit 3')
        self.assertEqual(r.returncode, 3)
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, WORM]))

    def test_the_timeout_ends_a_long_run_and_the_worm_comes_back(self):
        self.set_state(resident=[EMBED, WORM])
        started = time.time()
        r = self.window('sleep', '30', AEGIS_WINDOW_TIMEOUT='1')
        self.assertLess(time.time() - started, 20)
        self.assertEqual(r.returncode, 124)
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, WORM]))

    def test_a_signal_mid_run_still_gets_the_worm_back(self):
        self.set_state(resident=[EMBED, WORM])
        p = subprocess.Popen(['bash', WINDOW, 'sleep', '30'], env=self.env(), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline and 'running' not in (open(os.path.join(self.tmp, 'window.log')).read()
                                                           if os.path.exists(os.path.join(self.tmp, 'window.log')) else ''):
            time.sleep(0.2)
        p.terminate(); p.wait(30)
        self.assertEqual(sorted(self.lms()['resident']), sorted([EMBED, WORM]))
        self.assertIn('signal received', open(os.path.join(self.tmp, 'window.log')).read())

    def test_the_lab_lock_is_held_for_the_whole_run(self):
        self.set_state(resident=[EMBED, WORM])
        lock = os.path.join(self.mem, '.aegis-model-window.lock')
        r = self.window('sh', '-c', 'flock -n -s %s true && echo free || echo held' % lock)
        self.assertEqual(r.stdout.strip(), 'held')
        r2 = subprocess.run(['flock', '-n', '-s', lock, 'true'])
        self.assertEqual(r2.returncode, 0)            # let go after

    def test_with_aeon_as_house_model_the_command_just_runs(self):
        self.house('aeon')
        self.set_state(resident=[EMBED, AEON])
        r = self.window('sh', '-c', 'exit 0')
        self.assertEqual(r.returncode, 0)
        self.assertFalse(any(l.startswith('load') or l.startswith('unload') for l in self.lms().get('log', [])))

    def test_aeon_failing_to_load_skips_the_command_and_restores_the_worm(self):
        self.set_state(resident=[EMBED, WORM], fail_load=True)
        marker = os.path.join(self.tmp, 'ran')
        r = self.window('touch', marker)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(marker))
        self.assertIn('SWAP-BACK FAILED', open(os.path.join(self.tmp, 'window.log')).read())

    # --- the callers of the window -----------------------------------------------------------------------------------
    def test_causality_local_runs_go_through_the_window_and_count_only_plain_aeon(self):
        for path in ('scripts/causality-engine.py', 'bin/causality-engine.py'):
            src = open(os.path.join(REPO, path)).read()
            self.assertIn('if not _args.compact:\n        _in_window()', src)
            self.assertIn('"aegis-model-window.sh"', src)
            self.assertIn('if _BACKEND != "self" and not plain_aeon(d):', src)
        import importlib.util
        spec = importlib.util.spec_from_file_location('ce', os.path.join(REPO, 'scripts', 'causality-engine.py'))
        src = open(os.path.join(REPO, 'scripts', 'causality-engine.py')).read()
        fn = src[src.index('def plain_aeon('):src.index('\n\n', src.index('def plain_aeon('))]
        ns = {}; exec(fn, ns)
        self.assertTrue(ns['plain_aeon']({'model': 'aeon/gemma-4-12b'}))
        self.assertTrue(ns['plain_aeon']({'model': 'aeon-gemma-4-12b'}))
        for model in ('lab-c1', 'grok-4', '', None):
            self.assertFalse(ns['plain_aeon']({'model': model}))

    def test_the_watchdog_watches_the_house_model_the_loader_names(self):
        src = open(os.path.join(REPO, 'bin', 'gemma-watchdog.sh')).read()
        self.assertIn('MODEL="$(bash "$LOADER" --which', src)
        self.assertLess(src.index('MODEL="$(bash'), src.index('flock -n 9'))


if __name__ == '__main__':
    unittest.main()
