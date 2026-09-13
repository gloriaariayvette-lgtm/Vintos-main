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
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.expanduser("~/Vintos")
for path in (HERE, BIN, os.path.expanduser("~/.vintos/workspace/bin")):
    if os.path.isdir(path) and path not in sys.path: sys.path.append(path)
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
    parameters = value.get("parameters") if isinstance(value.get("parameters"), dict) else {}
    shots = max(256, min(16384, int(value.get("shots", 4096))))
    return {"experiment": experiment, "parameters": parameters, "shots": shots,
            "question": str(value.get("question", ""))[:800],
            "why_this": str(value.get("why_this", ""))[:800]}


def _reading(context, plan, result):
    visible = json.dumps(result, ensure_ascii=False)[:12000]
    raw = lab._ask(
        "You are Vintos returning from one computational Chemistry Lab experiment. Read the shape playfully and "
        "honestly. It is a simulated artifact, not proof about biology or himself. Return JSON only.",
        context + "\n\nPLAN:\n" + json.dumps(plan) + "\n\nRESULT:\n" + visible +
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
        plan = None; result = None
        try:
            from compute_admission import admit
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="frontier", stage="plan"):
                plan = _plan(context, experiments, lens)
            result = mac.run(plan["experiment"], plan["parameters"], plan["shots"])
            if not result.get("ok"): raise RuntimeError(result.get("error", "Mac experiment failed"))
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="local", model=lab.LLM_MODEL, stage="reading"):
                reading = _reading(context, plan, result)
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "completed",
                   "plan": plan, "mac_run_id": result.get("run_id"), "mac_result": result,
                   "reading": reading, "context_receipt": receipt["context_sha256"],
                   "truth_status": "generated_lab_interpretation_not_biological_evidence",
                   "elapsed_ms": int((time.time() - started) * 1000)}
            if result.get("run_id"):
                mac.reading(result["run_id"], reading.get("reading", ""))
            lab._append(SESSIONS, row)
            lab._append(lab.NOTEBOOK, {"at": row["at"], "kind": "frontier_session",
                         "session_id": session_id, "lens": lens, "experiment": plan["experiment"],
                         "question": plan["question"], **reading,
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
