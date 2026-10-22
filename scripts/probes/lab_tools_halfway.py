#!/usr/bin/env python3
"""Read-only: halfway through the two-day check (23 October). Is his Lab using its tools and connectors TOGETHER, in
investigations, on its own since the deploy that brought them (890160f)? Writes nothing.

The window starts at the first deploy whose rev contains 890160f and runs to now. The counts are lab_usage_report's:
an execution counts only when his Lab chose it (origin autonomous_lab in an investigation, or his own source and
plugin receipts); a downstream use counts only when a later step's input names that step's output.

    python3 lab_tools_halfway.py
"""
import glob, json, os, subprocess, sys, time
from collections import Counter

WS = os.path.expanduser("~/.vintos/workspace")
LAB = os.path.join(WS, "memory", "chemistry-lab")
REPO = os.path.expanduser("~/Vintos-main")
sys.path.insert(0, os.path.join(WS, "scripts"))
import lab_usage_report as U

start = None
for p in sorted(glob.glob(os.path.expanduser("~/.vintos/deploy/releases/*.json"))):
    try: rec = json.load(open(p))
    except Exception: continue
    rev = str(rec.get("git_rev") or "")
    if rev and subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", "890160f", rev],
                              capture_output=True).returncode == 0:
        start = rec.get("at"); print("window opens at the deploy of %s, %s" % (rev[:8], start)); break
if not start:
    sys.exit("no deploy containing 890160f found in ~/.vintos/deploy/releases")
now = time.strftime("%Y-%m-%dT%H:%M:%S")
r = U.report(LAB, start, now)
hours = (time.mktime(time.strptime(now, "%Y-%m-%dT%H:%M:%S")) - time.mktime(time.strptime(start[:19], "%Y-%m-%dT%H:%M:%S"))) / 3600
print("window: %.0f hours of the 48\n" % hours)

used, ran_only, failed_only, never = [], [], [], []
for tool, t in r["tools"].items():
    row = (tool, t["completed_executions"], t["failed_or_unknown"], t["explicit_downstream_uses"], t["paths"])
    if t["explicit_downstream_uses"]: used.append(row)
    elif t["completed_executions"]: ran_only.append(row)
    elif t["failed_or_unknown"]: failed_only.append(row)
    else: never.append(tool)
def show(title, rows):
    print("== %s (%d) ==" % (title, len(rows)))
    for tool, ok, bad, use, paths in sorted(rows, key=lambda x: (-x[3], -x[1], x[0])):
        print("  %-48s ran %3d  failed %3d  fed a next step %3d   via %s" % (tool, ok, bad, use, ", ".join(paths)))
    print()
show("ran AND its output fed another tool (what we planned)", used)
show("ran, but nothing used its output", ran_only)
show("only failed", failed_only)
print("== never called in the window (%d) ==\n  %s\n" % (len(never), ", ".join(never)))

print("== chains: one tool's output into the next (%d investigations) ==" % len(r["chains"]))
for c in r["chains"][-8:]:
    print("  %s: %s" % (c["investigation"], str(c.get("question"))[:110]))
    for l in c["links"]:
        print("     %s -> %s" % (l["from"], l["consumer"]))

try: inv = json.load(open(os.path.join(LAB, "investigations.json"))).get("investigations", [])
except (OSError, ValueError): inv = []
recent = [i for i in inv if any(str(s.get("at") or "") >= start[:19] for s in i.get("steps", []))]
print("\n== investigations with a step in the window: %d; their states: %s" % (
    len(recent), dict(Counter(str(i.get("state")) for i in recent))))
print("   step states: %s" % dict(Counter(str(s.get("state")) for i in recent for s in i.get("steps", []) if str(s.get("at") or "") >= start[:19])))
print("   steps per investigation: %s" % sorted((sum(1 for s in i.get("steps", []) if s.get("route") not in ("read_output", "schema")) for i in recent), reverse=True)[:15])
