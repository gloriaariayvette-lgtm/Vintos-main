#!/usr/bin/env python3
"""Dated quota integration against scratch stores, no providers or live effects."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import software_quota as Q
import forge_loop as F
import study_fix as S


class Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="software-quota-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for target, value in [("software_quota.CONFIG", self.root / "quota.json"),
                              ("software_quota.today", lambda: Q.AUTHORIZED_DAY),
                              ("forge_loop.step_day", lambda: Q.AUTHORIZED_DAY),
                              ("study_fix._today", lambda: Q.AUTHORIZED_DAY),
                              ("study_fix.MEMORY", str(self.root)),
                              ("study_fix.QUEUE", str(self.root / "queue.json")),
                              ("study_fix.RESET", str(self.root / "reset.json")),
                              ("study_fix._now", lambda: datetime(2026, 10, 7, 12))]:
            p = patch(target, value); p.start(); self.addCleanup(p.stop)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.network.start(); self.addCleanup(self.network.stop)
        for name in ("say", "tell_gloria", "fable", "_deploy"):
            p = patch.object(S, name, side_effect=AssertionError("effect forbidden"))
            p.start(); self.addCleanup(p.stop)
        self.assertTrue(Path(S.QUEUE).is_relative_to(self.root))
        self.assertTrue(Path(S.RESET).is_relative_to(self.root))
        self.assertTrue(Q.CONFIG.is_relative_to(self.root))
        self.grant = {"schema": 1, "date": Q.AUTHORIZED_DAY, "timezone": "America/Chicago",
                      "authorization": Q.AUTHORIZATION, "limits": {"forge": 10, "study": 10}}
        self.owner, self.worker = "o" * 40, "w" * 40
        self.controller = F.Controller(self.root / "forge.sqlite", self.owner, self.worker, "https://fixture.invalid")
        self.assertTrue(self.controller.path.is_relative_to(self.root))

    def activate(self):
        Q.CONFIG.write_text(json.dumps(self.grant))

    def test_missing_malformed_and_excessive_config_fails_closed(self):
        self.assertEqual(Q.limit("forge", 3), 3)
        for raw in ["{", "[]", "null", "x" * 4097,
                    json.dumps(dict(self.grant, limits={"forge": 11, "study": 10})),
                    json.dumps(dict(self.grant, limits={"forge": True, "study": 10})),
                    json.dumps(dict(self.grant, limits={"forge": 10.0, "study": 10})),
                    json.dumps(dict(self.grant, limits={"forge": 0, "study": 10})),
                    json.dumps(dict(self.grant, limits={"forge": 10})),
                    json.dumps(dict(self.grant, timezone="UTC")),
                    json.dumps(dict(self.grant, date="2026-10-08")),
                    json.dumps(dict(self.grant, authorization="unapproved")),
                    json.dumps(dict(self.grant, schema=True)),
                    json.dumps(self.grant)[:-1] + ',"schema":1}']:
            Q.CONFIG.write_text(raw)
            self.assertIsNone(Q.campaign(), raw[:100])
            self.assertEqual(Q.limit("study", 3), 3)

    def test_date_bounds_and_chicago_midnight(self):
        self.activate()
        self.assertEqual(Q.limit("forge", 3, "2026-10-06"), 3)
        self.assertEqual(Q.limit("forge", 3, "2026-10-07"), 10)
        self.assertEqual(Q.limit("forge", 3, "2026-10-08"), 3)
        # Exercise the real clock function across Chicago's midnight, not UTC's.
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("quota_clock_fixture", REPO / "scripts/software_quota.py")
        clock = module_from_spec(spec); spec.loader.exec_module(clock)
        for utc, expected in [("2026-10-07T04:59:59+00:00", "2026-10-06"),
                              ("2026-10-07T05:00:00+00:00", "2026-10-07"),
                              ("2026-10-08T04:59:59+00:00", "2026-10-07"),
                              ("2026-10-08T05:00:00+00:00", "2026-10-08")]:
            with patch.object(clock, "datetime") as dt:
                dt.now.side_effect = lambda zone, u=utc: datetime.fromisoformat(u).astimezone(zone)
                self.assertEqual(clock.today(), expected)

    def test_forge_retains_three_then_allows_seven_not_eight(self):
        c = self.controller
        for i in range(3):
            self.assertTrue(c.reserve_build(self.owner, f"{i:032x}", "SK-12345678")["reserved"])
        self.assertFalse(c.reserve_build(self.owner, f"{3:032x}", "SK-12345678")["reserved"])
        self.activate()
        self.assertEqual(c.step_budget(self.owner)["used"], 3)
        self.assertEqual(c.step_budget(self.owner)["remaining"], 7)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda i: c.reserve_build(self.owner, f"{i:032x}", "SK-12345678"), range(3, 15)))
        self.assertEqual(sum(x["reserved"] for x in outcomes), 7)
        self.assertEqual(c.step_budget(self.owner)["used"], 10)
        self.assertTrue(c.reserve_build(self.owner, f"{0:032x}", "SK-12345678")["reserved"])
        self.assertEqual(c.step_budget(self.owner)["used"], 10)
        with patch.object(F, "step_day", return_value="2026-10-08"):
            self.assertEqual(c.step_budget(self.owner)["limit"], 3)
            self.assertEqual(c.step_budget(self.owner)["used"], 0)
        self.assertEqual(c.step_budget(self.owner)["used"], 10)

    def test_forge_report_claims_share_build_budget(self):
        c = self.controller
        for i in range(3):
            c.reserve_build(self.owner, f"{i:032x}", "SK-12345678")
        self.activate()
        projects = [c.create(self.owner, "Synthetic quota fixture", ["research_report"]) for _ in range(8)]
        claims = [c.claim(self.worker, p["id"], "research_report") for p in projects]
        self.assertEqual(sum(x is not None for x in claims), 7)
        self.assertEqual(c.status(self.owner, projects[-1]["id"])["day_steps"],
                         {"day": Q.AUTHORIZED_DAY, "used": 10, "limit": 10, "remaining": 0})

    def test_study_retains_prior_submissions_despite_reset_receipt(self):
        prior = [{"id": f"SF-old{i}", "asked": "2026-10-07T01:00:00", "state": "failed", "what": "prior"} for i in range(3)]
        Path(S.QUEUE).write_text(json.dumps(prior))
        Path(S.RESET).write_text(json.dumps({"date": Q.AUTHORIZED_DAY, "at": "2026-10-07T02:00:00"}))
        reset_before = Path(S.RESET).read_bytes()
        self.activate()
        self.assertEqual(S.used_today(), 3)
        with self.assertRaisesRegex(ValueError, "reset refused"):
            S.reset_today()
        self.assertEqual(Path(S.RESET).read_bytes(), reset_before)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda i: S.request(f"Synthetic distinct software request number {i}"), range(12)))
        self.assertEqual(sum(x[0] is not None for x in outcomes), 7)
        self.assertEqual(S.used_today(), 10)
        self.assertEqual(S._load()[:3], prior)
        self.assertIn("10 Study fixes", S.request("One more distinct synthetic request")[1])
        with patch.object(S, "_today", return_value="2026-10-08"):
            self.assertEqual(S.used_today(), 0)
            self.assertEqual(Q.limit("study", 3, S._today()), 3)

    def test_malformed_config_cannot_hide_usage_behind_old_reset(self):
        Path(S.QUEUE).write_text(json.dumps([
            {"id": f"SF-old{i}", "asked": "2026-10-07T01:00:00", "state": "failed"} for i in range(3)]))
        Path(S.RESET).write_text(json.dumps({"date": Q.AUTHORIZED_DAY, "at": "2026-10-07T02:00:00"}))
        Q.CONFIG.write_text("{broken")
        self.assertEqual(S.used_today(), 3)
        self.assertIn("3 Study fixes", S.request("Synthetic request over ordinary cap")[1])
        with self.assertRaises(ValueError):
            S.reset_today()

    def test_worker_progress_preserves_new_submissions_and_usage(self):
        self.activate()
        S.request("First synthetic software request")
        snapshot = S._load()
        second, _ = S.request("Second synthetic software request")
        snapshot[0]["state"] = "failed"
        S._save_progress(snapshot)
        rows = S._load()
        self.assertEqual(rows[0]["state"], "failed")
        self.assertEqual(rows[1]["id"], second["id"])
        self.assertEqual(S.used_today(), 2)


if __name__ == "__main__":
    unittest.main()
