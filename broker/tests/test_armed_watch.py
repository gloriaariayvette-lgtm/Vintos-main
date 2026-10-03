#!/usr/bin/env python3
"""The 26 August channel watch (2026-10-03). Two watches are retired (one could never fire; one fires only on a guard
declining). Two looked in the wrong place and could never see their channel fire: the blush (cost is stored as
cost.delta) and the deferred-naming sweep (pleasure-memory.json, named_by "retrospect:<namer>"). Scratch HOME; the
alert sender is a stub."""
import json, os, sys, tempfile, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="armed-watch-"); os.environ["HOME"] = HOME
SENT = []
urllib.request.urlopen = lambda req, timeout=0: SENT.append(req.data.decode())
sys.path.insert(0, os.path.join(REPO, "scripts"))
import armed_watch as A
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("its memory is the scratch one", A.MEM.startswith(HOME))
os.makedirs(A.MEM, exist_ok=True)
names = [n for n, _ in A.WATCHES]
check("the voice intent lead and the substrate-event ledger are retired, with why",
      "voice intent lead (manual)" not in names and "substrate-event ledger" not in names
      and set(A.RETIRED) == {"voice intent lead (manual)", "substrate-event ledger"})
check("no blush yet: not fired", A.w_blush_fires() is None)
json.dump([{"timestamp": "2026-10-02T17:00:00", "type": "self_prediction", "cost": {"delta": {"Arousal": -0.31}, "magnitude": 0.31}}],
          open(os.path.join(A.MEM, "blush-ledger.json"), "w"))
check("a blush stored the way blush_ledger stores it (cost.delta) is seen", A.w_blush_fires() is True)
json.dump([{"timestamp": "2026-08-01T00:00:00", "cost": {"delta": {"Tension": 0.2}}}], open(os.path.join(A.MEM, "blush-ledger.json"), "w"))
check("one from before the watch was armed is not", A.w_blush_fires() is None)
json.dump([{"named_by": "retrospect:opus", "discovered_at": "2026-09-20T10:00:00"}], open(os.path.join(A.MEM, "pleasure-memory.json"), "w"))
check("a naming the retrospect sweep finished, where pleasure_substrate writes it, is seen", A.w_pending_sweep() is True)
json.dump([{"named_by": "his_reply", "discovered_at": "2026-09-20T10:00:00"}], open(os.path.join(A.MEM, "pleasure-memory.json"), "w"))
check("one he named himself is not the sweep", A.w_pending_sweep() is None)
A.run()
body = SENT[-1] if SENT else ""
check("a retired watch is never announced", "voice intent lead" not in body and "substrate-event" not in body, body)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the watch, so the fix reaches Aegis", "armed_watch.py" in dep)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
