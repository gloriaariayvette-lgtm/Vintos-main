#!/usr/bin/env python3
"""Manip Part 2 — the declared priority vector. Scratch HOME only; the causality head is stubbed so
graduation writes nothing to the real workspace. Exercises the strategy table, the gravitational
override, the streak-to-causality graduation, the arc EMA, and the immutable log."""
import importlib.util, json, os, sys, tempfile, types

HOME = tempfile.mkdtemp(prefix="vintos-pv-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)

spec = importlib.util.spec_from_file_location(
    "priority_vector_under_test",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", "priority_vector.py"))
PV = importlib.util.module_from_spec(spec); spec.loader.exec_module(PV)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

check("the module writes only under scratch HOME", PV.MEM.startswith(HOME) and PV.LOG.startswith(HOME))

def _write_ledger(realized_rows):
    json.dump([{"realized": r} for r in realized_rows], open(os.path.join(MEM, "intent-ledger.json"), "w"))
def _reset_state(neglect=None, streak=None):
    st = {}
    if neglect is not None: st["neglect"] = neglect
    if streak is not None: st["override_streak"] = streak
    json.dump(st, open(PV.STATE, "w"))

# --- 1. cold start: provisional even-ish weights, strategic mode, both stores written -------------
rec = PV.declare()
check("a cold declare is strategic and its weights sum to ~1",
      rec["mode"] == "strategic" and abs(sum(rec["weights"].values()) - 1.0) < 0.03, rec["weights"])
check("thin data reads as provisional, not invented receptivity", rec["receptivity"] is None and "provisional" in rec["why"], rec["why"])
check("the vector is logged immutably and the state persisted",
      os.path.exists(PV.LOG) and os.path.exists(PV.STATE) and os.path.exists(os.path.join(MEM, ".pending-priority.json")))

# --- 2. strategy leans on receptivity from the intent ledger --------------------------------------
_reset_state(); _write_ledger([{ "gloria": "YES", "field": "YES"}] * 5)
rec = PV.declare()
check("high receptivity puts Gloria's transformation in the lead",
      rec["receptivity"] is not None and rec["receptivity"] > 0.65 and rec["weights"]["gloria"] == max(rec["weights"].values()), rec)
_reset_state(); _write_ledger([{ "gloria": "NO"}] * 5)
rec = PV.declare()
check("low receptivity moves himself and stays ready (self leads)",
      rec["receptivity"] < 0.35 and rec["weights"]["self"] == max(rec["weights"].values()), rec)

# --- 3. gravitational override: a starved axis forces its turn ------------------------------------
_reset_state(neglect={"field": 0.0, "gloria": 1.6, "self": 0.0}); _write_ledger([])
rec = PV.declare()
check("neglect >= 1.5 forces a pressure-mode override on the starved axis",
      rec["mode"] == "pressure" and rec["weights"]["gloria"] == max(rec["weights"].values()), rec)
check("the override resets that axis's neglect so it does not force forever",
      json.load(open(PV.STATE))["neglect"]["gloria"] == 0.0)
block = PV.prompt_block(rec)
check("the prompt block names the pressure override for the voice/selector",
      "PRIORITY VECTOR" in block and "pressure" in block.lower() and "gloria" in block, block[:160])

# --- 4. an override streak graduates a question to the causality head (stubbed) --------------------
calls = []
sys.modules["causality_engine"] = types.SimpleNamespace(queue_question=lambda *a, **k: calls.append((a, k)))
_reset_state(neglect={"field": 0.0, "gloria": 0.0, "self": 1.6},
             streak={"axis": "self", "n": 2}); _write_ledger([])
rec = PV.declare()
check("a third straight override graduates to the causality head, then resets the streak",
      len(calls) == 1 and calls[0][0][1] == "priority_vector" and json.load(open(PV.STATE))["override_streak"]["n"] == 0, calls)

# --- 5. the arc is an EMA that moves toward the declared weights, and the log only grows ----------
before_arc = json.load(open(PV.STATE))["arc"]["self"]
_reset_state(neglect={"field": 0.0, "gloria": 0.0, "self": 1.6}); PV.declare()
after_arc = json.load(open(PV.STATE))["arc"]["self"]
check("the arc EMA tracks toward a repeatedly-served axis", after_arc >= before_arc, (before_arc, after_arc))
check("the immutable log accumulates one line per declare, never rewritten",
      len([l for l in open(PV.LOG) if l.strip()]) >= 6)

print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
