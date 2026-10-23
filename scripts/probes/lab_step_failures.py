#!/usr/bin/env python3
"""Read-only: why his Lab's investigation steps fail (23 October; 2,465 failed of 2,612 since the 21 October deploy).
Writes nothing. Groups every failed step since the deploy by what it called and why it failed, and every stalled
investigation by why it closed.

    python3 lab_step_failures.py [since, default 2026-10-21T16:24]
"""
import json, os, re, sys
from collections import Counter

LAB = os.path.expanduser("~/.vintos/workspace/memory/chemistry-lab")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-10-21T16:24"
data = json.load(open(os.path.join(LAB, "investigations.json")))
inv = [i for i in data.get("investigations", []) if any(str(s.get("at") or "") >= SINCE for s in i.get("steps", []))
       or str(i.get("opened_at") or i.get("at") or "") >= SINCE]


def norm(text):
    text = re.sub(r"\b(?:S|I)-[0-9a-f]{6,}\b", "<id>", str(text or ""))
    text = re.sub(r"\b[A-Z][0-9][A-Z0-9]{3,8}\b", "<acc>", text)
    text = re.sub(r"\d{2,}", "<n>", text)
    return text[:150]


def what(s):
    req = s.get("request") or {}
    if not isinstance(req, dict): req = {}
    name = req.get("source") or req.get("plugin") or req.get("instrument") or req.get("experiment") or ""
    op = req.get("operation") or req.get("tool") or ""
    return "%s:%s%s" % (s.get("route"), name, ("." + str(op)) if op else "")


steps = [s for i in inv for s in i.get("steps", []) if str(s.get("at") or "") >= SINCE]
print("since %s: %d investigations, %d steps, %s" % (SINCE, len(inv), len(steps), dict(Counter(s.get("state") for s in steps))))
print("\n== what the steps asked for (all states) ==")
for k, n in Counter(what(s) for s in steps).most_common(30):
    print("  %5d  %s" % (n, k))
print("\n== why steps failed: (what it called, the error), most common ==")
for (w, e), n in Counter((what(s), norm(s.get("error"))) for s in steps if s.get("state") != "completed").most_common(35):
    print("  %5d  %-40s %s" % (n, w[:40], e))
print("\n== why investigations closed ==")
for k, n in Counter(norm(i.get("closed_reason") or i.get("state")) for i in inv).most_common(15):
    print("  %5d  %s" % (n, k))
print("\n== planning failures (before any step) ==")
for k, n in Counter(norm(i.get("last_planning_error")) for i in inv if i.get("last_planning_error")).most_common(10):
    print("  %5d  %s" % (n, k))
