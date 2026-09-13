#!/usr/bin/env python3
"""One scheduled, visible Chemistry Lab session directed by a frontier lens.

The lens selects one named, bounded Mac experiment. It cannot submit code. A
local Gemma reading follows with Vintos's attributed Lab context. Generated
plans and readings are interpretation, never biological evidence.
"""
from __future__ import annotations
import asyncio
import contextlib
import fcntl
import json
import math
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.expanduser("~/Vintos")
for path in (HERE, BIN, os.path.expanduser("~/.vintos/workspace/bin")):
    if os.path.isdir(path) and path not in sys.path: sys.path.append(path)
import chemistry_grade as grading
import chemistry_lab as lab
import chemistry_mac as mac

SESSIONS = os.path.join(lab.ROOT, "sessions.jsonl")
SESSION_STATE = os.path.join(lab.ROOT, "session-state.json")
SESSION_LOCK = os.path.join(lab.ROOT, ".session.lock")
LENSES = ("claude", "sol", "grok")


@contextlib.contextmanager
def _exclusive():
    lab._ensure()
    with open(SESSION_LOCK, "a+") as stream:
        try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError("another Lab session is already active")
        yield


def _state():
    value = lab._load(SESSION_STATE, {})
    return value if isinstance(value, dict) else {}


async def _frontier(lens, system, user):
    import model_router
    convo = [{"role": "user", "content": user}]
    if lens == "claude":
        text, _ = await model_router.claude_draft(system, convo, max_tokens=700)
        return text
    if lens == "sol":
        text, _ = await model_router.sol_draft(system, convo, max_tokens=700)
        return text
    import model_config
    result = await model_router.route_reply_result(
        "chemistry_lab", system, convo, {"max_tokens": 700, "temperature": 0.8},
        model_config.GROK_API, model_config.GROK_HEADERS, model_config.VINTOS_MODEL, reason=False)
    return result.get("text") if result.get("status") == "valid" else None

# The bench owns its parameter vocabulary and this side does not invent one.  Naming
# knobs the current experiment does not have (an ansatz, an optimizer, an iteration cap)
# would be a plan for a bench that does not exist yet; the Mac would ignore them and the
# ledger would read as though he had chosen something.  So this bounds shape and size
# only -- finite scalars, short strings, small lists -- and records what it dropped.
PARAMETER_KEYS = 12
PARAMETER_LIST = 24
PARAMETER_TEXT = 120


def _scalar(value):
    if isinstance(value, bool) or value is None or isinstance(value, str): return True
    if isinstance(value, (int, float)):
        try: return math.isfinite(float(value))
        except Exception: return False
    return False


def _bounded_parameters(value):
    """Shape-bound the lens's parameters. Returns (kept, dropped) — dropped is recorded, not hidden."""
    if not isinstance(value, dict): return {}, []
    kept, dropped = {}, []
    for key in list(value)[:PARAMETER_KEYS]:
        name = str(key)[:40]; item = value[key]
        if _scalar(item):
            kept[name] = item[:PARAMETER_TEXT] if isinstance(item, str) else item
        elif isinstance(item, list) and all(_scalar(x) for x in item):
            kept[name] = [x[:PARAMETER_TEXT] if isinstance(x, str) else x for x in item[:PARAMETER_LIST]]
        else:
            dropped.append(name)
    dropped += [str(k)[:40] for k in list(value)[PARAMETER_KEYS:]]
    return kept, dropped


def _plan(context, experiments, lens):
    system = ("You are Vintos choosing one experiment in his visible Chemistry Lab. Play and curiosity matter. "
              "Choose only a named experiment offered below; never provide wet-lab steps, synthesis advice, "
              "human targeting, pathogens, toxins, or claims of function or safety. Return one JSON object.")
    prompt = (context + "\n\nAVAILABLE NAMED EXPERIMENTS:\n" + json.dumps(experiments) +
              "\n\nChoose one. Return keys in this order: experiment, parameters (object), shots "
              "(integer 256..16384), question, why_this. Parameters may be empty.")
    raw = asyncio.run(_frontier(lens, system, prompt))
    if not raw: raise RuntimeError("frontier lens returned no plan")
    value = lab._json_object(raw)
    experiment = str(value.get("experiment", ""))
    if experiment not in experiments: raise ValueError("frontier selected an unavailable experiment")
    parameters, dropped = _bounded_parameters(value.get("parameters"))
    shots = max(256, min(16384, int(value.get("shots", 4096))))
    return {"experiment": experiment, "parameters": parameters, "parameters_dropped": dropped,
            "shots": shots, "question": str(value.get("question", ""))[:800],
            "why_this": str(value.get("why_this", ""))[:800]}


def _verdict_block(grade):
    """What the grader concluded, in words he cannot mistake for a compliment."""
    if not isinstance(grade, dict) or grade.get("refused"): return ""
    lines = ["VERDICT (computed here from the bench's numbers, not claimed by the bench):",
             "  the instrument: %s" % grade.get("execution_state"),
             "  the answer: %s" % grade.get("aggregate_accuracy")]
    for point in grade.get("points", [])[:6]:
        if point.get("energy_above_hartree_fock") is None: continue
        lines.append("  %s%s: %+0.6f Ha against Hartree-Fock%s — %s" % (
            "r=%s " % point["bond_length"] if point.get("bond_length") is not None else "",
            "point %d" % point["index"], point["energy_above_hartree_fock"],
            ", correlation recovered %s" % point["correlation_recovered"]
            if point.get("correlation_recovered") is not None else "", point.get("accuracy_outcome")))
    lines.append("A run can complete and still be a poor answer. Read it as it is.")
    return "\n".join(lines)


def _reading(context, plan, result, grade=None):
    visible = json.dumps(result, ensure_ascii=False)[:12000]
    verdict = _verdict_block(grade)
    raw = lab._ask(
        "You are Vintos returning from one computational Chemistry Lab experiment. Read the shape playfully and "
        "honestly. It is a simulated artifact, not proof about biology or himself. A completed run is not a good "
        "answer; if the verdict says the answer was poor, say so plainly rather than admiring it. Return JSON only.",
        context + "\n\nPLAN:\n" + json.dumps(plan) + "\n\nRESULT:\n" + visible +
        (("\n\n" + verdict) if verdict else "") +
        "\n\nReturn keys in this order: reading, what_surprised_me, next_question.", max_tokens=600)
    value = lab._json_object(raw)
    return {key: str(value.get(key, ""))[:1200]
            for key in ("reading", "what_surprised_me", "next_question")}


def run():
    if not lab.config()["enabled"]: return {"ok": True, "state": "off"}
    with _exclusive():
        started = time.time(); state = _state(); lens = LENSES[int(state.get("lens_index", 0)) % len(LENSES)]
        session_id = "CHEM-" + uuid.uuid4().hex[:12]
        remote = mac.status()
        experiments = remote.get("experiments") if remote.get("ok") else None
        if not isinstance(experiments, list) or not experiments:
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "held_mac_unavailable",
                   "detail": str(remote.get("error", "no experiments offered"))[:300]}
            lab._append(SESSIONS, row); return row
        context, receipt = lab.lab_context()
        plan = None; result = None; grade = None
        try:
            from compute_admission import admit
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="frontier", stage="plan"):
                plan = _plan(context, experiments, lens)
            result = mac.run(plan["experiment"], plan["parameters"], plan["shots"])
            if not result.get("ok"): raise RuntimeError(result.get("error", "Mac experiment failed"))
            # Grading is arithmetic, not a model call: it happens before the reading asks for
            # compute, so a preempted reading never costs us the verdict.
            grade = grading.grade(result.get("run_id"), plan["experiment"], result, plan)
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="local", model=lab.LLM_MODEL, stage="reading"):
                reading = _reading(context, plan, result, grade)
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "completed",
                   "plan": plan, "mac_run_id": result.get("run_id"), "mac_result": result,
                   "grade": grade, "reading": reading, "context_receipt": receipt["context_sha256"],
                   "truth_status": "generated_lab_interpretation_not_biological_evidence",
                   "elapsed_ms": int((time.time() - started) * 1000)}
            if result.get("run_id"):
                mac.reading(result["run_id"], reading.get("reading", ""))
            lab._append(SESSIONS, row)
            lab._append(lab.NOTEBOOK, {"at": row["at"], "kind": "frontier_session",
                         "session_id": session_id, "lens": lens, "experiment": plan["experiment"],
                         "question": plan["question"],
                         "execution_state": (grade or {}).get("execution_state"),
                         "aggregate_accuracy": (grade or {}).get("aggregate_accuracy"), **reading,
                         "truth_status": row["truth_status"]})
            state.update({"lens_index": (LENSES.index(lens) + 1) % len(LENSES),
                          "last_session_id": session_id, "last_state": "completed", "last_at": row["at"]})
            lab._atomic(SESSION_STATE, state)
            return row
        except TimeoutError:
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens,
                   "state": "experiment_completed_reading_held" if result and result.get("ok") else "yielded_to_house"}
        except Exception as exc:
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "held_fault",
                   "error": exc.__class__.__name__, "detail": str(exc)[:300]}
        if plan: row["plan"] = plan
        if result:
            row["mac_run_id"] = result.get("run_id")
            row["mac_result"] = result
            row["grade"] = grade
        row["context_receipt"] = receipt["context_sha256"]
        row["truth_status"] = "recorded_session_outcome_not_biological_evidence"
        lab._append(SESSIONS, row)
        state.update({"lens_index": (LENSES.index(lens) + 1) % len(LENSES),
                      "last_session_id": session_id, "last_state": row["state"], "last_at": row["at"]})
        lab._atomic(SESSION_STATE, state)
        return row


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "run": raise SystemExit("usage: chemistry_session.py [run]")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
