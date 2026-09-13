#!/usr/bin/env python3
"""A reading the Lab still owes. Scratch HOME only; no model, no network, no bench."""
import contextlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-owed-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos, curious and particular.")

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module

@contextlib.contextmanager
def admitted(*a, **k): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the suite must never reach a model"))
O = load("chemistry_reading", os.path.join(REPO, "scripts", "chemistry_reading.py"))
lab.set_enabled(True)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in O.OWED and not lab.ROOT.startswith("/home/gloria"), O.OWED)
check("the model is stubbed out", O.default_reader is not None and lab._ask.__name__ == "<lambda>")

RESULT = {"ok": True, "run_id": "RUN-A", "run": {"result": {"results": [{"vqe_energy": -1.1}]}}}
PLAN = {"experiment": "molecule", "parameters": {}, "shots": 4096}
GRADE = {"execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}

# --- the debt is recorded, once ------------------------------------------------------------
lab._append(os.path.join(lab.ROOT, "sessions.jsonl"), {
    "session_id": "CHEM-1", "state": "experiment_completed_reading_held",
    "mac_run_id": "RUN-A", "plan": PLAN, "grade": GRADE,
})
row = O.owe("CHEM-1", "claude", PLAN, RESULT, GRADE, "ctx-sha")
check("a held reading becomes an open debt", row and O.state()["owed"] == 1, O.state())
check("owing twice does not double the debt", O.owe("CHEM-1", "claude", PLAN, RESULT) is None and O.state()["owed"] == 1)
check("the debt is visible in the notebook",
      any(n.get("kind") == "reading_owed" and n.get("session_id") == "CHEM-1" for n in lab._jsonl(lab.NOTEBOOK)))
check("the Lab status reports what it owes", lab.status()["reading_owed"]["owed"] == 1, lab.status()["reading_owed"])

# --- paying it reads the preserved result and never re-runs ---------------------------------
seen = {}
def reader(debt):
    seen["debt"] = debt
    return {"reading": "a shallow basin", "what_surprised_me": "how far off it sat",
            "next_question": "would a deeper ansatz change this curve?"}
out = O.settle_one(reader=reader)
check("the owed reading is paid", out["outcome"] == O.READ and out["session_id"] == "CHEM-1", out)
check("it read the preserved result rather than a fresh one", seen["debt"]["result"] == RESULT)
check("it never asked the bench for anything",
      "chemistry_mac" not in open(os.path.join(REPO, "scripts", "chemistry_reading.py")).read())
note = [n for n in lab._jsonl(lab.NOTEBOOK) if n.get("kind") == "owed_reading"][-1]
check("the reading says it is a later reading of a preserved result",
      note["reread_of_preserved_result"] is True and "no_rerun" in note["truth_status"] and note["owed_since"], note)
import chemistry_spark as spark_mod
check("paying an owed reading refreshes the Lab spark feed",
      spark_mod.feed() and spark_mod.feed()[-1]["provenance"]["mac_run_id"] == "RUN-A",
      spark_mod.feed())
check("the debt is retired with a receipt, not deleted",
      O.state()["owed"] == 0 and O.state()["retired"] == 1
      and O._book()["retired"][0]["how"] == "read" and O._book()["retired"][0]["session_id"] == "CHEM-1", O.state())
check("nothing is owed twice", O.settle_one(reader=reader)["outcome"] == O.NOTHING_OWED)

# --- idempotence: a crash after the note, before the retire ---------------------------------
O.owe("CHEM-2", "sol", PLAN, RESULT)
lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "owed_reading", "session_id": "CHEM-2"})
out2 = O.settle_one(reader=reader)
check("a reading already written is retired without paying twice",
      out2["outcome"] == O.ALREADY_READ and O.state()["owed"] == 0, out2)

# --- a held house leaves the debt exactly where it was ---------------------------------------
O.owe("CHEM-3", "grok", PLAN, RESULT)
def timeout_reader(debt): raise TimeoutError("foreground live")
out3 = O.settle_one(reader=timeout_reader)
check("a preempted reading stays owed", out3["outcome"] == O.STILL_HELD and O.state()["owed"] == 1, out3)
check("a released claim can be taken again", O._take() is not None)
O._release("CHEM-3")
def broken_reader(debt): raise ValueError("model returned nothing")
out4 = O.settle_one(reader=broken_reader)
check("a broken reading is a fault, not a settlement",
      out4["outcome"] == O.REFUSED and O.state()["owed"] == 1 and lab._jsonl(lab.FAULTS), out4)

# --- the claim lease ---------------------------------------------------------------------------
O._release("CHEM-3"); claimed = O._take()
check("a claimed debt is not handed to a second reader", claimed and O._take() is None, claimed and claimed["session_id"])
book = O._book()
for entry in book["open"]: entry["claimed_at"] = time.time() - O.CLAIM_LEASE_S - 60
lab._atomic(O.OWED, book)
check("a stale claim returns the debt rather than stranding it", O._take() is not None)

# --- expiry stays visibly unresolved -------------------------------------------------------------
book = O._book()
for entry in book["open"]:
    entry["at"] = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(); entry["claimed_at"] = None
lab._atomic(O.OWED, book)
out5 = O.settle_one(reader=reader)
check("an expired debt is not actionable", out5["outcome"] == O.NOTHING_OWED, out5)
check("an expired debt is never retired as settled",
      O.state()["expired_unread"] == 1 and O.state()["retired"] == 2
      and all(r.get("session_id") != "CHEM-3" for r in O._book()["retired"]), O.state())
expired = [r for r in O._book()["open"] if r["state"] == "expired_unread"][0]
check("it says plainly that it was never read",
      expired["truth_status"] == "experiment_completed_and_was_never_read" and expired.get("expired_at"), expired["truth_status"])
check("the Lab status keeps showing it", lab.status()["reading_owed"]["expired_unread"] == 1)

# --- the Tune switch --------------------------------------------------------------------------
lab.set_enabled(False)
check("an off Lab does no reading", O.settle_one(reader=reader)["outcome"] == O.REFUSED)
check("switching off preserves every debt", O.state()["expired_unread"] == 1 and O.state()["retired"] == 2)
lab.set_enabled(True)

# --- concurrency: one debt, two readers, one payment ------------------------------------------
lab._atomic(O.OWED, {"open": [], "retired": []})
open(lab.NOTEBOOK, "w").close()
O.owe("CHEM-RACE", "claude", PLAN, RESULT)

def _settle(index):
    import importlib.util as _u, os as _o, sys as _s, contextlib as _c, types as _t, time as _time
    _o.environ["HOME"] = HOME; _o.environ["SPARK_WORKSPACE"] = WS
    _s.path.insert(0, os.path.join(REPO, "scripts"))
    @_c.contextmanager
    def _admitted(*a, **k): yield object()
    _s.modules["compute_admission"] = _t.SimpleNamespace(admit=_admitted)
    def _load(name, path):
        spec = _u.spec_from_file_location(name, path)
        mod = _u.module_from_spec(spec); _s.modules[name] = mod; spec.loader.exec_module(mod); return mod
    _load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
    owed = _load("chemistry_reading", os.path.join(REPO, "scripts", "chemistry_reading.py"))
    def _slow(debt):
        _time.sleep(0.4)   # long enough that both readers are inside settle_one at once
        return {"reading": "read by %d" % index, "what_surprised_me": "", "next_question": ""}
    return owed.settle_one(reader=_slow)["outcome"]

import multiprocessing
with multiprocessing.get_context("fork").Pool(2) as pool:
    outcomes = pool.map(_settle, range(2))
check("exactly one reader pays the debt", outcomes.count(O.READ) == 1, outcomes)
check("the other is turned away rather than paying it again",
      set(outcomes) - {O.READ} <= {O.REFUSED, O.NOTHING_OWED, O.ALREADY_READ}, outcomes)
check("the reading is written exactly once",
      sum(1 for n in lab._jsonl(lab.NOTEBOOK) if n.get("kind") == "owed_reading"
          and n.get("session_id") == "CHEM-RACE") == 1,
      [n.get("kind") for n in lab._jsonl(lab.NOTEBOOK)])
check("the debt is retired exactly once",
      sum(1 for r in O._book()["retired"] if r["session_id"] == "CHEM-RACE") == 1
      and not O._book()["open"], O.state())

# --- the wiring ---------------------------------------------------------------------------------
session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the held branch now owes the reading instead of stranding it",
      "owed.owe(session_id, lens, plan, result, grade" in session_source
      and "experiment_completed_reading_held" in session_source)
check("the session settles a debt before starting anything new",
      session_source.index("owed.settle_one()") < session_source.index("remote = mac.status()"))
check("a debt that could not be paid stops the session before the bench is touched",
      'HOLDS_THE_SESSION = ("STILL_HELD", "REFUSED")' in session_source
      and session_source.index("HOLDS_THE_SESSION:") < session_source.index("remote = mac.status()")
      and "held_reading_owed" in session_source)
lab_source = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the daemon settles inside its own admission, without asking for the slot twice",
      "chemistry_reading.settle_one(already_admitted=True)" in lab_source)
check("the reading module holds its own lock, not the session's or the daemon's",
      O.OWED_LOCK.endswith(".reading.lock") and O.OWED_LOCK != lab.LOCK)
check("the reading module writes only below the Lab root", O.OWED.startswith(lab.ROOT))
check("the reading module never touches the Atelier",
      "atelier" not in open(os.path.join(REPO, "scripts", "chemistry_reading.py")).read().lower())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
