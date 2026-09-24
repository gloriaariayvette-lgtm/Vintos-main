#!/usr/bin/env python3
"""Every divergence lens, one preserved artifact, one question each. Scratch HOME; no frontier, no bench."""
import contextlib
import hashlib
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
REAL_LENS_CALL, REAL_READING = session._lens_call, session._reading
session._divergence_specs = lambda: {
    "astra": ("openai", "astra-test"),
    "fable": ("anthropic", "fable-test"),
    "grok": ("xai", "grok-test"),
    "opus": ("anthropic", "opus-test"),
}
PROVIDER = {"astra": "openai", "fable": "anthropic", "grok": "xai", "opus": "anthropic"}
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

# --- on, as she approved (2026-09-24), including for a config saved while it was off --------------
check("daily divergence is on by default", lab.DEFAULTS["divergence_enabled"] is True and lab.config()["divergence_enabled"] is True)
cfg = lab.config(); cfg["divergence_enabled"] = False; cfg.pop("divergence_version", None); lab._atomic(lab.CONFIG, cfg)
check("a config saved before her yes is switched on once", lab.config()["divergence_enabled"] is True)
cfg = lab.config(); cfg["divergence_enabled"] = False; lab._atomic(lab.CONFIG, cfg)
check("after that, turning it off stays off", lab.config()["divergence_enabled"] is False)
cfg["divergence_enabled"] = True; lab._atomic(lab.CONFIG, cfg)
check("the four lenses are Astra, Fable 5.1, Grok 4.6 and Opus 5.5",
      session.DIVERGENCE_MODELS == {"astra": ("openai", "gpt-6-astra"), "fable": ("anthropic", "claude-fable-5-1"),
                                    "grok": ("xai", "grok-4.6"), "opus": ("anthropic", "claude-opus-5-5")})

# --- the same artifact and the same context to each lens -----------------------------------------
seen = []
def _frontier(lens, system, user, paid_reservation=None):
    seen.append({"lens": lens, "system": system, "user": user})
    check("the lens receives its exact prepaid reservation", paid_reservation["provider"] == PROVIDER[lens])
    return json.dumps({"question": "what would %s ask?" % lens, "why_this": "curiosity",
                       "what_you_notice": "the gap"})
async def _async_frontier(lens, system, user, paid_reservation=None):
    return _frontier(lens, system, user, paid_reservation)
session._lens_call = _async_frontier

context, receipt = lab.lab_context()
row = session._run_divergence("CHEM-D1", {}, context, receipt)
check("every divergence lens was asked", [s["lens"] for s in seen] == list(session.DIVERGENCE_LENSES), [s["lens"] for s in seen])
check("every lens got a byte-identical prompt",
      len({s["user"] for s in seen}) == 1 and len({s["system"] for s in seen}) == 1, len({s["user"] for s in seen}))
check("the identical prompt is hashed onto the row",
      row["identical_prompt_sha256"] and len(row["identical_prompt_sha256"]) == 64)
expected_envelope = hashlib.sha256(json.dumps({"system": seen[0]["system"], "user": seen[0]["user"]},
                                              sort_keys=True).encode()).hexdigest()
check("the hash binds the system and user prompt together",
      row["identical_prompt_sha256"] == expected_envelope)
check("each lens is blind to the others' answers",
      not any("what would astra ask" in s["user"] or "what would fable ask" in s["user"] for s in seen))
check("the same base Vintos context reached every lens", all("I am Vintos" in s["user"] for s in seen))
check("it reads the preserved artifact and runs nothing",
      row["read_of"] == "RUN-A" and row["source_session_id"] == "CHEM-SRC", row)

# --- three questions, no verdict ------------------------------------------------------------------
check("the readings are kept side by side",
      len(row["readings"]) == 4 and {r["question"] for r in row["readings"]} ==
      {"what would %s ask?" % lens for lens in session.DIVERGENCE_LENSES}, row["readings"])
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
check("the notebook keeps each question as its own question",
      len(note["questions"]) == 4 and note["agreement"] == "not_computed", note)

# --- a lens that fails is held, never replaced --------------------------------------------------------
async def _one_fails(lens, system, user, paid_reservation=None):
    if lens == "grok": raise RuntimeError("provider refused")
    return _frontier(lens, system, user, paid_reservation)
session._lens_call = _one_fails
held = session._run_divergence("CHEM-D2", {}, context, receipt)
check("a failed lens is held", held["lenses_held"] == ["grok"] and held["lenses_read"] == ["astra", "fable", "opus"], held)
check("a partial read is not recorded as completed", held["state"] == "completed_with_held_lenses", held)
check("no other provider quietly fills in",
      len(held["readings"]) == 4 and [r["lens"] for r in held["readings"]] == list(session.DIVERGENCE_LENSES))
check("it is still not a two-lens finding", held["agreement"] == "not_computed")

# --- every lens reserved before the first is spent -------------------------------------------------------
session._lens_call = _async_frontier
reserved.clear(); released.clear(); seen.clear()
_refuse.add("xai")
capped = session._run_divergence("CHEM-D3", {}, context, receipt)
check("a refused reservation stops the whole thing",
      capped["state"] == "held_paid_cap" and "grok" in capped["detail"], capped)
check("no lens was called at all", seen == [], seen)
check("the reservations use and release the real provider buckets",
      [p for p, _ in reserved] == ["openai", "anthropic", "xai"]
      and [p for p, _ in released] == ["openai", "anthropic"], (reserved, released))
check("the row says why nothing was spent", "no_lens_was_spent" in capped["truth_status"])
_refuse.clear()

# --- nothing to read ---------------------------------------------------------------------------------------
empty = tempfile.mkdtemp(prefix="vintos-chem-empty-")
saved = session.SESSIONS
session.SESSIONS = os.path.join(empty, "sessions.jsonl")
check("with no preserved artifact it holds rather than running an experiment for one",
      session._run_divergence("CHEM-D4", {}, context, receipt)["state"] == "held_no_preserved_artifact")
session.SESSIONS = saved

# --- the session turn: the experiment first, then every lens reads that same result -------------------
sys.modules["chemistry_mac"].run = lambda *a, **k: {"ok": True, "run_id": "RUN-DAY", "result": {"lowest_energy": -1.1}}
session.mac.run = sys.modules["chemistry_mac"].run
session._plan = lambda *a, **k: {"experiment": "molecule", "parameters": {}, "shots": 512, "question": "q",
                                 "why_this": "w", "prediction": "the likeliest state is the lowest-energy one",
                                 "addressed_entry_ids": []}
read_by = []
def _reading(context, plan, result, grade=None, lens=None):
    read_by.append(lens); return {"reading": "r", "what_surprised_me": "s", "prediction_vs_result": "p", "next_question": "n"}
session._reading = _reading
reserved.clear(); seen.clear()
lab._atomic(session.SESSION_STATE, {"offered": 6, "lens_index": 0})
turn = session.run()
check("the day's experiment runs and completes", turn.get("state") == "completed" and turn.get("mac_run_id") == "RUN-DAY", turn)
check("the frontier lens that planned it also reads it", read_by == [session.LENSES[0]], read_by)
check("then every divergence lens reads that same day's result",
      turn.get("divergence_state") == "completed" and [s["lens"] for s in seen] == list(session.DIVERGENCE_LENSES)
      and lab._jsonl(session.DIVERGENCE)[-1]["read_of"] == "RUN-DAY", (turn.get("divergence_state"), seen[:1]))
check("the divergence prompt carries the prediction made before the run",
      "the likeliest state is the lowest-energy one" in seen[0]["user"])
check("the plan lens still advances; divergence does not spend it",
      json.load(open(session.SESSION_STATE))["lens_index"] == 1)

# --- each lens calls exactly its own model; the day's reading is the frontier lens's ----------------------
import asyncio
calls = []
async def _claude(system, convo, max_tokens=0, paid_reservation=None, model=None):
    calls.append(("anthropic", model)); return "{}", ""
async def _sol(system, convo, max_tokens=0, paid_reservation=None, model=None):
    calls.append(("openai", model)); return "{}", ""
async def _grok_result(convo, params, endpoint, headers, model, system):
    calls.append(("xai", model)); return {"status": "valid", "text": "{}"}
fake_router = types.SimpleNamespace(claude_draft=_claude, sol_draft=_sol, _grok_result=_grok_result,
                                    _reserve_provider=lambda *a, **k: None)
sys.modules["model_router"] = fake_router
sys.modules["model_config"] = types.SimpleNamespace(GROK_API="stub", GROK_HEADERS={})
for lens in session.DIVERGENCE_LENSES:
    asyncio.run(REAL_LENS_CALL(lens, "s", "u", {"provider": session.DIVERGENCE_MODELS[lens][0]}))
check("each lens is called on exactly its reserved model",
      calls == [session.DIVERGENCE_MODELS[l] for l in session.DIVERGENCE_LENSES], calls)
asked = []
async def _frontier_reading(lens, system, user, paid_reservation=None):
    asked.append((lens, user)); return json.dumps({"reading": "r", "prediction_vs_result": "it missed"})
session._frontier = _frontier_reading
lab._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a lens reading must not use the local model"))
out = REAL_READING("ctx", {"prediction": "fold A is lowest"}, {"ok": True}, None, lens="grok")
check("a lens reading goes to the frontier lens with the prediction in front of it",
      asked and asked[0][0] == "grok" and "fold A is lowest" in asked[0][1]
      and out["prediction_vs_result"] == "it missed", (asked[:1], out))
del sys.modules["model_router"]

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
