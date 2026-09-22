#!/usr/bin/env python3
"""Vintos's calendar: dated events fire autonomously as ready wants.

Isolation (CLAUDE.md): the calendar store AND the wants store are repointed into a throwaway dir, and
one test stubs the enqueue so firing reaches no store at all. Both facts are asserted so a later edit
cannot quietly let the suite open her live calendar or append to her live wants.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import vintos_calendar as cal


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vintos-calendar-")
        self.cal_path = os.path.join(self.tmp.name, "calendar.json")
        self.wants_path = os.path.join(self.tmp.name, "current-wants.json")
        self._old = (cal.CALENDAR_FILE, cal.WANTS_FILE)
        cal.CALENDAR_FILE, cal.WANTS_FILE = self.cal_path, self.wants_path

    def tearDown(self):
        cal.CALENDAR_FILE, cal.WANTS_FILE = self._old
        self.tmp.cleanup()

    def _wants(self):
        return json.loads(Path(self.wants_path).read_text()) if os.path.exists(self.wants_path) else []

    def test_stores_are_isolated(self):
        cal.add_event("2030-01-01", "new year")
        self.assertTrue(cal.CALENDAR_FILE.startswith(self.tmp.name), "calendar store escaped the throwaway dir")
        self.assertTrue(cal.WANTS_FILE.startswith(self.tmp.name), "wants store escaped the throwaway dir")

    def test_add_and_list_roundtrip(self):
        e = cal.add_event("2030-06-01", "wish her a good month")
        self.assertEqual(e["status"], "scheduled")
        listed = cal.list_events()
        self.assertEqual([x["id"] for x in listed], [e["id"]])

    def test_malformed_date_is_refused(self):
        with self.assertRaises(ValueError):
            cal.add_event("next tuesday", "vague")

    def test_bad_capability_is_refused(self):
        with self.assertRaises(ValueError):
            cal.add_event("2030-06-01", "x", action={"capability": "Not A Cap!"})

    def test_due_gates_on_time(self):
        past = (cal._now() - timedelta(days=1)).isoformat()
        future = (cal._now() + timedelta(days=1)).isoformat()
        a = cal.add_event(past, "already due")
        cal.add_event(future, "not yet")
        due = cal.due()
        self.assertEqual([e["id"] for e in due], [a["id"]])

    def test_fire_enqueues_a_ready_manually_routed_want(self):
        past = (cal._now() - timedelta(hours=1)).isoformat()
        e = cal.add_event(past, "tell her good morning",
                          action={"capability": "tell_gloria", "params": {"tone": "warm"}})
        fired = cal.fire()
        self.assertEqual(len(fired), 1)
        wants = self._wants()
        self.assertEqual(len(wants), 1)
        w = wants[0]
        # The shape the router runs immediately: pre-planned, manually routed, no 8h hold.
        self.assertTrue(w["multistep"])
        self.assertTrue(w["manually_routed"])
        self.assertTrue(w["timer_bypass"])
        self.assertEqual(w["current_step_index"], 0)
        self.assertEqual(w["source"], "calendar")
        self.assertEqual(w["calendar_event_id"], e["id"])
        self.assertEqual(w["steps"][0]["capability"], "tell_gloria")
        self.assertEqual(w["steps"][0]["params"], {"tone": "warm"})
        self.assertEqual(w["steps"][0]["status"], "pending")
        # The one-off event is retired, not left to fire again.
        done = [x for x in json.loads(Path(self.cal_path).read_text()) if x["id"] == e["id"]][0]
        self.assertEqual(done["status"], "fired")
        self.assertEqual(done["want_id"], w["id"])

    def test_default_action_is_tell_gloria(self):
        past = (cal._now() - timedelta(hours=1)).isoformat()
        cal.add_event(past, "just a reminder")     # no action
        cal.fire()
        self.assertEqual(self._wants()[0]["steps"][0]["capability"], "tell_gloria")

    def test_fire_with_stub_touches_no_real_store(self):
        past = (cal._now() - timedelta(hours=1)).isoformat()
        cal.add_event(past, "stubbed")
        seen = []
        cal.fire(enqueue=lambda want: seen.append(want))
        self.assertEqual(len(seen), 1)
        self.assertFalse(os.path.exists(self.wants_path), "stubbed fire still wrote the wants store")

    def test_recurrence_reschedules_and_does_not_double_fire(self):
        past = (cal._now() - timedelta(hours=1))
        e = cal.add_event(past.isoformat(), "daily standup", recurrence="daily")
        cal.fire()
        self.assertEqual(len(self._wants()), 1)
        row = [x for x in json.loads(Path(self.cal_path).read_text()) if x["id"] == e["id"]][0]
        self.assertEqual(row["status"], "scheduled")           # recurring: stays on the calendar
        self.assertEqual(row["fire_count"], 1)
        self.assertGreater(cal.parse_at(row["at"]), past)      # advanced to the next day
        # A second fire at the SAME now must not re-enqueue (next occurrence is in the future now).
        cal.fire(now=cal._now())
        self.assertEqual(len(self._wants()), 1)

    def test_cancel(self):
        e = cal.add_event("2030-06-01", "changed my mind")
        self.assertTrue(cal.cancel(e["id"]))
        self.assertEqual(cal.list_events(), [])
        self.assertFalse(cal.cancel("nope"))


if __name__ == "__main__":
    unittest.main()
