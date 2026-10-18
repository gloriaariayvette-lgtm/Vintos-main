#!/usr/bin/env python3
"""Synthetic, temporary-store tests: no devices, models, senders or live stores."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import press_hold_bench as B

WORDS = ["tap", "press", "hold", "push", "pause", "stay", "touch", "wait"]
DURATIONS = [100, 250, 500, 750, 1000]


class BenchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="press-hold-test-")
        self.addCleanup(temp.cleanup)
        self.scratch = Path(temp.name).resolve()
        self.store = self.scratch / "store"
        self.assertTrue(self.store.is_relative_to(self.scratch))
        blocker = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.network = blocker.start()
        self.addCleanup(blocker.stop)
        self.assertIs(socket.socket.connect, self.network)
        self.create()

    def tearDown(self):
        self.network.assert_not_called()

    def create(self, run_id="run-a", **changes):
        config = dict(words=list(WORDS), durations_ms=list(DURATIONS), data_kind="synthetic", run_id=run_id)
        config.update(changes)
        return B.create_run(self.store, **config)

    def trial(self, trial_id="t1", **changes):
        row = dict(trial_id=trial_id, word=WORDS[0], requested_duration_ms=100,
                   measured_duration_ms=101, expected_label="press", observed_label="press",
                   score=0.75, score_method="synthetic-test-v1", status="scored")
        row.update(changes)
        return row

    def record(self, run_id="run-a", **changes):
        return B.record_trial(self.store, run_id, **self.trial(**changes))

    def logfile(self, run_id="run-a"):
        path = self.store / run_id / "scores.jsonl"
        self.assertTrue(path.is_relative_to(self.scratch))
        return path

    def cli(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = B.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_manifest_and_empty_run(self):
        manifest = json.loads((self.store / "run-a/manifest.json").read_text())
        self.assertEqual(manifest["words"], WORDS)
        self.assertEqual(manifest["durations_ms"], DURATIONS)
        self.assertEqual(manifest["data_kind"], "synthetic")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(self.logfile().read_bytes(), b"")
        result = B.coverage(self.store, "run-a")
        self.assertEqual(result["expected_cells"], 40)
        self.assertEqual(len(result["missing_scored_cells"]), 40)
        self.assertEqual(result["trial_count"], 0)
        self.assertFalse(result["complete"])

    def test_invalid_run_config_creates_no_run(self):
        bad = [dict(words=WORDS[:-1]), dict(words=[WORDS[0]] * 8), dict(words=[" bad"] + WORDS[1:]),
               dict(durations_ms=DURATIONS[:-1]), dict(durations_ms=[100] * 5),
               *[dict(durations_ms=[value] + DURATIONS[1:]) for value in [0, -1, True, float("nan"), float("inf"), 10**400]],
               dict(data_kind="assumed"), dict(source_commit="not-a-sha"), dict(run_id="../escape")]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                options = dict(run_id="invalid")
                options.update(change)
                self.create(**options)
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), ["run-a"])

    def test_existing_run_is_never_reinitialized(self):
        self.record()
        before = {p.name: p.read_bytes() for p in (self.store / "run-a").iterdir()}
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.store / "run-a").iterdir()})

    def test_store_is_required_and_empty_store_is_rejected(self):
        with self.assertRaises(ValueError):
            B.create_run("", words=WORDS, durations_ms=DURATIONS, data_kind="synthetic")
        with self.assertRaises(ValueError):
            B.coverage(" ", "run-a")
        before = self.logfile().read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            B.main(["coverage", "--run-id", "run-a"])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.logfile().read_bytes(), before)

    def test_append_preserves_prefix_and_records_metadata(self):
        first = self.record()["record"]
        prefix = self.logfile().read_bytes()
        second = self.record(trial_id="t2", word=WORDS[1])["record"]
        after = self.logfile().read_bytes()
        self.assertTrue(after.startswith(prefix))
        self.assertEqual(len(after.splitlines()), 2)
        self.assertEqual(first["data_kind"], "synthetic")
        self.assertEqual(second["run_id"], "run-a")
        self.assertEqual(first["requested_duration_ms"], 100)
        self.assertTrue(first["recorded_at_utc"].endswith("+00:00"))

    def test_invalid_trial_never_changes_log(self):
        self.record()
        before = self.logfile().read_bytes()
        bad = [dict(word="not-in-run"), dict(requested_duration_ms=999), dict(requested_duration_ms=True),
               dict(requested_duration_ms=float("nan")), dict(measured_duration_ms=-1),
               dict(measured_duration_ms=True), dict(measured_duration_ms=float("inf")),
               dict(expected_label="guess"), dict(observed_label="unknown"), dict(status="done"),
               dict(measured_duration_ms=None), dict(observed_label=None), dict(score=None),
               dict(score=True), dict(score=-0.1), dict(score=1.1), dict(score=float("nan")), dict(score=10**400),
               dict(score_method=None), dict(score_method=""), dict(error_code="unexpected"),
               dict(trial_id="../escape"), dict(raw_prompt="must-not-be-logged")]
        for change in bad:
            values = self.trial(trial_id="invalid")
            values.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                B.record_trial(self.store, "run-a", **values)
            self.assertEqual(self.logfile().read_bytes(), before)

    def test_duplicate_id_replay_is_idempotent_conflict_is_refused(self):
        first = self.record()
        before = self.logfile().read_bytes()
        duplicate = self.record()
        self.assertTrue(first["appended"])
        self.assertFalse(duplicate["appended"])
        self.assertEqual(duplicate["record"], first["record"])
        with self.assertRaisesRegex(ValueError, "different data"):
            self.record(score=0.5)
        self.assertEqual(self.logfile().read_bytes(), before)

    def test_independent_repeats_do_not_inflate_coverage(self):
        self.record()
        self.record(trial_id="repeat2")
        result = B.coverage(self.store, "run-a")
        self.assertEqual((result["trial_count"], result["attempted_cells"], result["scored_cells"]), (2, 1, 1))
        with self.assertRaisesRegex(ValueError, "consistent"):
            self.record(trial_id="contradiction", expected_label="hold")

    def test_failed_and_missing_scores_remain_null_and_incomplete(self):
        failure = self.record(trial_id="failure", status="failed", measured_duration_ms=None,
                              observed_label=None, score=None, score_method=None, error_code="timeout")["record"]
        unscored = self.record(trial_id="unscored", word=WORDS[1], status="unscored",
                               score=None, score_method=None)["record"]
        self.assertIsNone(failure["score"])
        self.assertIsNone(failure["measured_duration_ms"])
        self.assertIsNone(unscored["score"])
        result = B.coverage(self.store, "run-a")
        self.assertEqual((result["attempted_cells"], result["measured_cells"], result["scored_cells"]), (2, 1, 0))
        self.assertFalse(result["complete"])
        for changes in [dict(status="failed", score=None, score_method=None),
                        dict(status="failed", error_code="timeout"), dict(status="unscored")]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.record(trial_id="bad", **changes)

    def test_zero_is_a_real_score_and_zero_measured_duration_is_allowed(self):
        self.record(score=0, measured_duration_ms=0)
        self.assertEqual(B.coverage(self.store, "run-a")["scored_cells"], 1)

    def test_linear_retry_preserves_failures_and_refuses_forks(self):
        failed = dict(status="failed", measured_duration_ms=None, observed_label=None,
                      score=None, score_method=None, error_code="timeout")
        self.record(trial_id="f1", **failed)
        self.record(trial_id="f2", retry_of="f1", **failed)
        self.record(trial_id="s3", retry_of="f2")
        result = B.coverage(self.store, "run-a")
        self.assertEqual(result["status_counts"], {"scored": 1, "unscored": 0, "failed": 2})
        self.assertEqual(result["retry_count"], 2)
        self.assertEqual(result["scored_cells"], 1)
        before = self.logfile().read_bytes()
        for values in [dict(retry_of="absent"), dict(retry_of="f1"), dict(retry_of="s3"),
                       dict(retry_of="f2", word=WORDS[1])]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.record(trial_id="bad", **values)
        self.assertEqual(self.logfile().read_bytes(), before)

    def test_unscored_trial_can_be_retried(self):
        self.record(trial_id="u1", status="unscored", score=None, score_method=None)
        self.record(trial_id="u2", retry_of="u1")
        self.assertEqual(B.coverage(self.store, "run-a")["scored_cells"], 1)

    def test_runs_do_not_share_trials_or_coverage(self):
        self.create("run-b")
        self.record()
        self.assertEqual(B.coverage(self.store, "run-b")["trial_count"], 0)
        self.record(run_id="run-b", score=0.1)
        self.assertNotEqual(self.logfile("run-a").read_bytes(), self.logfile("run-b").read_bytes())
        self.assertEqual(B.coverage(self.store, "run-a")["trial_count"], 1)

    def test_full_and_incomplete_40_cell_coverage(self):
        for index, (word, duration) in enumerate((w, d) for w in WORDS for d in DURATIONS):
            if index == 39:
                result = B.coverage(self.store, "run-a")
                self.assertFalse(result["complete"])
                self.assertEqual(result["missing_scored_cells"], [{"word": word, "requested_duration_ms": duration}])
            self.record(trial_id="cell%d" % index, word=word, requested_duration_ms=duration, score=0)
        result = B.coverage(self.store, "run-a")
        self.assertTrue(result["complete"])  # Coverage does not mean good scores.
        self.assertEqual((result["trial_count"], result["scored_cells"]), (40, 40))
        self.assertEqual(result["missing_scored_cells"], [])
        self.assertEqual(result["unattempted_cells"], [])

    def test_concurrent_append_and_duplicate_id(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: self.record(), range(12)))
        self.assertEqual(sum(row["appended"] for row in outcomes), 1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: self.record(trial_id="independent%d" % i), range(16)))
        self.assertEqual(B.coverage(self.store, "run-a")["trial_count"], 17)
        self.assertEqual(len(self.logfile().read_bytes().splitlines()), 17)

    def test_malformed_or_torn_log_is_never_repaired_or_appended(self):
        self.record()
        valid = self.logfile().read_bytes()
        row = json.loads(valid)
        foreign = dict(row, run_id="another-run")
        boolean_version = dict(row, schema_version=True)
        cases = [valid[:-1], valid + b"\n", valid + valid,
                 (json.dumps(foreign) + "\n").encode(), (json.dumps(boolean_version) + "\n").encode(),
                 valid.replace(b'"score":0.75', b'"score":NaN'),
                 valid.replace(b'"score":0.75', b'"score":0.75,"score":0.5')]
        for raw in cases:
            with self.subTest(raw=raw[:30]):
                self.logfile().write_bytes(raw)  # External corruption, scratch store only.
                with self.assertRaisesRegex(ValueError, "invalid ledger record"):
                    self.record(trial_id="new")
                with self.assertRaises(ValueError):
                    B.coverage(self.store, "run-a")
                self.assertEqual(self.logfile().read_bytes(), raw)

    def test_symlink_ledger_cannot_redirect_a_write(self):
        target = self.scratch / "sentinel"
        target.write_text("unchanged")
        self.logfile().unlink()
        self.logfile().symlink_to(target)
        with self.assertRaises((OSError, ValueError)):
            self.record()
        self.assertEqual(target.read_text(), "unchanged")

    def test_cli_init_record_and_read_only_coverage(self):
        code, output, error = self.cli(["init", "--store", str(self.store), "--run-id", "cli-run",
                                         "--words", *WORDS, "--durations-ms", *map(str, DURATIONS),
                                         "--data-kind", "synthetic"])
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["manifest"]["run_id"], "cli-run")
        args = ["record", "--store", str(self.store), "--run-id", "cli-run", "--trial-id", "cli1",
                "--word", "tap", "--requested-duration-ms", "100", "--measured-duration-ms", "101",
                "--expected-label", "press", "--observed-label", "press", "--score", "0.75",
                "--score-method", "synthetic-test-v1", "--status", "scored"]
        self.assertEqual(self.cli(args)[0], 0)
        self.assertFalse(json.loads(self.cli(args)[1])["appended"])
        before = {p.name: p.read_bytes() for p in (self.store / "cli-run").iterdir()}
        code, output, error = self.cli(["coverage", "--store", str(self.store), "--run-id", "cli-run", "--require-complete"])
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(json.loads(output)["scored_cells"], 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.store / "cli-run").iterdir()})
        args[args.index("--word") + 1] = "absent"
        code, output, error = self.cli(args)
        self.assertEqual((code, output), (2, ""))
        self.assertIn("word is not in this run", error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
