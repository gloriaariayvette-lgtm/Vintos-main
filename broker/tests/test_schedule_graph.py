#!/usr/bin/env python3
"""Review item 20 (2026-09-10): every scheduled job has an owner, a named quiet state, and an overlap
verdict; two jobs that can fire in the same minute are handled only when both carry admission or the lock."""
import os, sys, json, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-sched-"); os.environ["HOME"] = HOME
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
spec = importlib.util.spec_from_file_location("sg", os.path.join(REPO, "scripts", "schedule-graph.py"))
SG = importlib.util.module_from_spec(spec); spec.loader.exec_module(SG)
SG.MEMORY = os.path.join(HOME, "memory")

cron = """
PATH=/usr/bin
# Vintos
*/30 * * * * bash /home/x/.vintos/workspace/bin/pearl-engine.sh
0 */6 * * * bash /home/x/.vintos/workspace/bin/humor-detector.sh
0 12 * * * bash /home/x/.vintos/workspace/bin/idle-journal.sh
0 12 * * * bash /home/x/.vintos/workspace/bin/mischief-detector.sh
15 3 * * * bash /home/x/.vintos/workspace/bin/does-not-exist.sh
"""
g = SG.build(cron)
by = {j["script"]: j for j in g["jobs"]}
check("five jobs parsed, the env line skipped", len(g["jobs"]) == 5)
check("an admitted job names its owner, organ and quiet states", by["pearl-engine.sh"]["owner"].startswith("pearl_engine.py") and by["pearl-engine.sh"]["organ"] == "pearl-engine" and "admitted" in by["pearl-engine.sh"]["quiet_states"], by["pearl-engine.sh"])
check("a gated job names its gates", {"consent-gated", "hour-gated", "idle-gated"} <= set(by["idle-journal.sh"]["gates"]), by["idle-journal.sh"]["gates"])
check("a missing wrapper is named, not guessed", by["does-not-exist.sh"].get("note", "").startswith("wrapper not found"))
pairs = {(o["a"], o["b"]): o for o in g["overlaps"]}
h = [o for o in g["overlaps"] if "pearl_engine" in o["a"] and "humor" in o["b"]]
check("pearl (every 30 min) and humor (every 6 h) overlap and are handled by shared admission+lock", h and h[0]["handled"] and "compute_admission" in h[0]["how"], h)
u = [o for o in g["unhandled"] if "journal" in o["a"] + o["b"] and "mischief" in o["a"] + o["b"]]
check("journal and mischief at 12:00 are an UNHANDLED overlap, named", u and u[0]["how"].startswith("UNHANDLED"), g["unhandled"])
check("the record lists owners and organs", "pearl-engine" in g["organs"] and len(g["owners"]) == 5)
s = SG.static_graph()
check("the static graph (no crontab) still knows every wrapper's owner and organ", len(s["wrappers"]) >= 20 and all(w.get("owner") for w in s["wrappers"]))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
