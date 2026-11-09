#!/usr/bin/env python3
"""Synthetic write/read diagnostics; never grant ancestry or reach external services."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import witness_capture as W
from witness_receipts import digest
spec = importlib.util.spec_from_file_location('write_replay', ROOT / 'experiments/judges-witness/replay.py')
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='map-write-observations-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.assertNotIn('.vintos', self.root.parts)
        self.path = self.root / 'value-map.md'
        self.result = 'Synthetic carried theme. ' * 100
        self.entry = '\n## 2026-01-02 12:00 — Value Map\n\n' + self.result + '\n\n---\n'
        self.sender = Mock(side_effect=AssertionError('external action forbidden'))
        for p in (patch.dict(os.environ, JUDGES_CAPTURE_SCRATCH=str(self.root), SPARK_WORKSPACE=str(self.root)),
                  patch.object(socket.socket, 'connect', self.sender)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)

    def build(self, resource=True):
        with patch.object(W.time, 'time', return_value=10):
            build = W.begin_value_map_build()
        with patch.object(W.time, 'time', return_value=20):
            self.assertTrue(W.finish_value_map_build(build, 'draft_a', self.result, self.entry, 'w',
                                                     self.path if resource else None))
        return next(json.loads(p.read_text()) for p in self.root.glob('value-map-build-*.json')
                    if json.loads(p.read_text())['build_id'] == build['build_id'])

    def nodes(self, text=None, path=None, at=30, legacy=False):
        text = self.entry if text is None else text
        selected = text.split('\n## ')[-1]
        selected = ('## ' + selected).strip()[:1500]
        read = W.value_map_read(text, selected, at, None if legacy else path or self.path)
        c = W.Capture('synthetic-turn', 'synthetic-chat', at+1)
        self.assertTrue(c.bind_value_map(read, 'Your value map:\n' + selected))
        return {n['id']: n for n in c._nodes}

    def test_real_receipt_functions_match_without_changing_ancestry(self):
        build, nodes = self.build(), self.nodes()
        before = copy.deepcopy(nodes)
        census_before = R.census([], nodes, 100)
        summary, detail = R.value_map_write_observations(nodes, [build], 100)
        self.assertEqual(summary['states'], {'one_matching_write': 1})
        self.assertEqual(detail[0]['candidate_build_ids'], [build['build_id']])
        self.assertEqual(build['schema'], 'value-map-build-v2')
        self.assertEqual(summary['admission_effect'], 'none')
        self.assertEqual(nodes, before)
        self.assertEqual(R.census([], nodes, 100), census_before)
        self.assertTrue(all(n['complete'] is False for n in nodes.values()))
        for secret in (str(self.path), self.result, build['build_id'], build['write']['entry_sha256']):
            self.assertNotIn(secret, json.dumps(summary))
        self.assertNotIn(str(self.path), json.dumps(build))

    def test_same_content_different_locator_never_matches(self):
        summary, _ = R.value_map_write_observations(self.nodes(path=self.root/'other.md'), [self.build()], 100)
        self.assertEqual(summary['states'], {'no_matching_write': 1})

    def test_same_selected_prefix_different_full_entry_never_matches(self):
        nodes = self.nodes(text=self.entry.replace('---', 'changed tail'))
        summary, _ = R.value_map_write_observations(nodes, [self.build()], 100)
        self.assertEqual(summary['states'], {'no_matching_write': 1})

    def test_prior_entries_do_not_turn_entry_match_into_whole_file_claim(self):
        build = self.build()
        nodes = self.nodes(text='## 2025-01-01 12:00\nOlder fixture\n' + self.entry)
        summary, _ = R.value_map_write_observations(nodes, [build], 100)
        self.assertEqual(summary['states'], {'one_matching_write': 1})
        self.assertEqual(build['write']['whole_file'], 'unverified')

    def test_all_matches_retained_not_latest_and_exact_duplicates_deduped(self):
        builds = [self.build(), self.build()]
        builds[1]['ended_at'] = 25
        summary, detail = R.value_map_write_observations(self.nodes(), builds + [copy.deepcopy(builds[0])], 100)
        self.assertEqual(summary['unique_builds'], 2)
        self.assertEqual(summary['states'], {'multiple_matching_writes': 1})
        self.assertEqual(detail[0]['candidate_build_ids'], sorted(b['build_id'] for b in builds))

    def test_future_writes_and_exclusive_cutoff(self):
        build = self.build()
        for at, cutoff, state in ((19,100,'no_matching_write'), (20,100,'one_matching_write'),
                                   (20,20,'outside_cutoff'), (30,30,'outside_cutoff')):
            summary, _ = R.value_map_write_observations(self.nodes(at=at), [build], cutoff)
            self.assertEqual(summary['states'], {state: 1})

    def test_legacy_identity_stays_unavailable(self):
        summary, _ = R.value_map_write_observations(self.nodes(legacy=True), [self.build()], 100)
        self.assertEqual(summary['states'], {'read_identity_unavailable': 1})
        summary, _ = R.value_map_write_observations(self.nodes(), [self.build(resource=False)], 100)
        self.assertEqual(summary['states'], {'no_matching_write': 1})
        self.assertEqual(summary['builds_without_resource_identity'], 1)

    def test_conflicting_duplicates_abort_in_either_order_even_beyond_cutoff(self):
        build = self.build(); bad = copy.deepcopy(build)
        bad['write']['entry_chars'] = True
        for records in ([build,bad], [bad,build]):
            with self.assertRaises(ValueError) as caught:
                R.value_map_write_observations(self.nodes(), records, 1)
            self.assertNotIn(build['build_id'], str(caught.exception))

    def test_malformed_build_fields_fail_closed(self):
        build = self.build()
        changes = [('schema','unknown'), ('upstream_complete',0), ('attempt_coverage_complete',0),
                   ('started_at',21), ('ended_at',True), ('ended_at',float('nan'))]
        for field,value in changes:
            bad = copy.deepcopy(build); bad[field] = value
            with self.assertRaises(ValueError): R.value_map_write_observations(self.nodes(), [bad], 100)
        for field,value in [('resource_sha256','bad'), ('entry_chars',True), ('entry_chars',4194305),
                            ('scope','opened'), ('durability','confirmed'), ('mode','unknown')]:
            bad = copy.deepcopy(build); bad['write'][field] = value
            with self.assertRaises(ValueError): R.value_map_write_observations(self.nodes(), [bad], 100)
        with self.assertRaises(ValueError): R.value_map_write_observations({}, {}, 100)

    def test_malformed_v2_binding_rejected_without_nodes(self):
        read = W.value_map_read(self.entry, self.entry.strip()[:1500], 30, self.path)
        for field,value in [('resource_sha256',None), ('stripped_entry_sha256','bad')]:
            bad = dict(read); bad[field] = value
            c = W.Capture('synthetic-turn','synthetic-chat',31)
            before = copy.deepcopy(c._nodes)
            self.assertFalse(c.bind_value_map(bad, 'Your value map:\n' + self.entry.strip()[:1500]))
            self.assertEqual(c._nodes, before)

    def test_cli_opt_in_private_output_and_manifest_no_admission_change(self):
        build, nodes = self.build(), self.nodes()
        base = {'input_kind':'synthetic', 'lineage':list(nodes.values()), 'sources':[]}
        reports = []
        for enabled in (False,True):
            bundle = dict(base)
            if enabled: bundle['value_map_builds'] = [build]
            source, output = self.root/('input-%s.json'%enabled), self.root/('output-%s'%enabled)
            source.write_text(json.dumps(bundle))
            run = subprocess.run([sys.executable, R.__file__, '--scratch',str(self.root), '--input',str(source),
                                  '--output',str(output), '--cutoff','1970-01-01T00:01:40Z'],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            report = json.loads((output/'aggregate.json').read_text()); reports.append(report)
            private = output/'private-value-map-writes.json'
            self.assertEqual(private.exists(),enabled)
            if enabled:
                self.assertEqual(private.stat().st_mode & 0o777,0o600)
                manifest = json.loads((output/'private-run.json').read_text())
                self.assertIn(hashlib.sha256(private.read_bytes()).hexdigest(),json.dumps(manifest))
                self.assertEqual(report['value_map_write_observations']['states'], {'one_matching_write':1})
            else: self.assertNotIn('value_map_write_observations',report)
        reports[1].pop('value_map_write_observations')
        self.assertEqual(reports[0],reports[1])


if __name__ == '__main__': unittest.main()
