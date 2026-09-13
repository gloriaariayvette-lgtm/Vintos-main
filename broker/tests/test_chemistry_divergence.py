#!/usr/bin/env python3
"""Three lenses, one preserved artifact, three questions. Scratch HOME; no frontier, no bench."""
import contextlib
import importlib.util
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-diverge-")
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
reserved, released = [], []
def reserve_paid(organ, provider, model="", units=1, cap=None, reservation_id=None):
    reserved.append((provider, reservation_id))
    return (False, "daily cap reached") if provider in _refuse else (True, "")
def release_paid(organ, provider, model="", units=1, why="", *, reservation_id=None):
    released.append((provider, reservation_id)); return True
_refuse = set()
sys.modules["compute_admission"] = types.SimpleNamespace(
    admit=admitted, reserve_paid=reserve_paid, release_paid=release_paid)
sys.modules["chemistry_mac"] = types.SimpleNamespace(
    status=lambda: {"ok": True, "experiments": ["molecule"]},
    run=lambda *a, **k: {"ok": False, "error": "the bench must not be touched here"},
    reading=lambda *a, **k: {"ok": True})

lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no local model in this suite"))
session = load("chemistry_session", os.path.join(REPO, "scripts", "chemistry_session.py"))
lab.set_enabled(True)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:220]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in session.DIVERGENCE
      and not lab.ROOT.startswith("/home/gloria"), session.DIVERGENCE)
check("no frontier client is reachable from this suite", "model_router" not in sys.modules)

ARTIFACT = {"session_id": "CHEM-SRC", "at": lab.now_iso(), "state": "completed",
            "lens": "claude", "mac_run_id": "RUN-A",
            "plan": {"experiment": "molecule", "question": "how flat is it?"},
            "mac_result": {"ok": True, "run": {"result": {"results": [{"vqe_energy": -0.478}]}}},
            "grade": {"execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK"}}
lab._append(session.SESSIONS, ARTIFACT)

# --- off by default ---------------------------------------------------------------------------
check("divergence is off until she turns it on",
      lab.DEFAULTS["divergence_enabled"] is False and lab.config()["divergence_enabled"] is False)
check("it is not due while it is off", session._divergence_due({"offered": 6}) is False)
lab.set_enabled(True)
cfg = lab.config(); cfg["divergence_enabled"] = True; lab._atomic(lab.CONFIG, cfg)
check("switched on, it is due on every Nth offered session and no other",
      [session._divergence_due({"offered": n}) for n in range(0, 8)]
      == [False, False, False, False, False, False, True, False],
      [session._divergence_due({"offered": n}) for n in range(0, 8)])
check("the cadence is deterministic, not a dice roll",
      all(session._divergence_due({"offered": 6}) for _ in range(5)))

# --- the same artifact and the same context to each lens -----------------------------------------
seen = []
def _frontier(lens, system, user):
    seen.append({"lens": lens, "system": system, "user": user})
    return json.dumps({"question": "what would %s ask?" % lens, "why_this": "curiosity",
                       "what_you_notice": "the gap"})
async def _async_frontier(lens, system, user): return _frontier(lens, system, user)
session._frontier = _async_frontier

context, receipt = lab.lab_context()
row = session._run_divergence("CHEM-D1", {}, context, receipt)
check("all three lenses were asked", [s["lens"] for s in seen] == list(session.LENSES), [s["lens"] for s in seen])
check("every lens got a byte-identical prompt",
      len({s["user"] for s in seen}) == 1 and len({s["system"] for s in seen}) == 1, len({s["user"] for s in seen}))
check("the identical prompt is hashed onto the row",
      row["identical_prompt_sha256"] and len(row["identical_prompt_sha256"]) == 64)
check("each lens is blind to the others' answers",
      not any("what would claude ask" in s["user"] or "what would sol ask" in s["user"] for s in seen))
check("the same base Vintos context reached all three", all("I am Vintos" in s["user"] for s in seen))
check("it reads the preserved artifact and runs nothing",
      row["read_of"] == "RUN-A" and row["source_session_id"] == "CHEM-SRC", row)

# --- three questions, no verdict ------------------------------------------------------------------
check("three readings are kept side by side",
      len(row["readings"]) == 3 and {r["question"] for r in row["readings"]} ==
      {"what would %s ask?" % lens for lens in session.LENSES}, row["readings"])
check("agreement is not computed", row["agreement"] == "not_computed"
      and "no_consensus_claim" in row["truth_status"])
blob = json.dumps({k: v for k, v in row.items() if k != "truth_status"})
check("nothing scores, votes, or synthesises",
      not any(word in blob for word in ("consensus", "majority", "synthes", "agreement_score", "winner")), blob[:200])
check("the only agreement field says it was not computed",
      row["agreement"] == "not_computed" and "no_consensus_claim" in row["truth_status"])
source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("no agreement is computed anywhere in the code",
      "majority" not in source and "consensus" not in source.replace("no_consensus_claim", ""))
note = [n for n in lab._jsonl(lab.NOTEBOOK) if n.get("kind") == "divergence"][-1]
check("the notebook keeps the three questions as three questions",
      len(note["questions"]) == 3 and note["agreement"] == "not_computed", note)

# --- a lens that fails is held, never replaced --------------------------------------------------------
async def _one_fails(lens, system, user):
    if lens == "grok": raise RuntimeError("provider refused")
    return _frontier(lens, system, user)
session._frontier = _one_fails
held = session._run_divergence("CHEM-D2", {}, context, receipt)
check("a failed lens is held", held["lenses_held"] == ["grok"] and held["lenses_read"] == ["claude", "sol"], held)
check("no other provider quietly fills in",
      len(held["readings"]) == 3 and [r["lens"] for r in held["readings"]] == list(session.LENSES))
check("it is still not a two-lens finding", held["agreement"] == "not_computed")

# --- all three reserved before the first is spent -------------------------------------------------------
session._frontier = _async_frontier
reserved.clear(); released.clear(); seen.clear()
_refuse.add("grok")
capped = session._run_divergence("CHEM-D3", {}, context, receipt)
check("a refused third reservation stops the whole thing",
      capped["state"] == "held_paid_cap" and "grok" in capped["detail"], capped)
check("no lens was called at all", seen == [], seen)
check("the reservations already taken are released",
      [p for p, _ in released] == ["claude", "sol"], released)
check("the row says why nothing was spent", "no_lens_was_spent" in capped["truth_status"])
_refuse.clear()

# --- nothing to read ---------------------------------------------------------------------------------------
empty = tempfile.mkdtemp(prefix="vintos-chem-empty-")
saved = session.SESSIONS
session.SESSIONS = os.path.join(empty, "sessions.jsonl")
check("with no preserved artifact it holds rather than running an experiment for one",
      session._run_divergence("CHEM-D4", {}, context, receipt)["state"] == "held_no_preserved_artifact")
session.SESSIONS = saved

# --- the session turn ------------------------------------------------------------------------------------
reserved.clear(); seen.clear()
lab._atomic(session.SESSION_STATE, {"offered": 6, "lens_index": 0})
turn = session.run()
check("the due session spends itself on divergence instead of the bench",
      turn["mode"] == "divergence" and turn["state"] == "completed", turn)
check("the offered count advances so the cadence keeps its place",
      json.load(open(session.SESSION_STATE))["offered"] == 7
      and json.load(open(session.SESSION_STATE))["last_mode"] == "divergence")
check("a divergence session does not spend a lens turn",
      json.load(open(session.SESSION_STATE))["lens_index"] == 0)
check("it is written to its own ledger and to the sessions ledger",
      lab._jsonl(session.DIVERGENCE) and any(r.get("mode") == "divergence" for r in lab._jsonl(session.SESSIONS)))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
