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
import hashlib
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
import chemistry_probe as probe
import chemistry_reading as owed
import chemistry_taste as taste

SESSIONS = os.path.join(lab.ROOT, "sessions.jsonl")
DIVERGENCE = os.path.join(lab.ROOT, "divergence.jsonl")
SESSION_STATE = os.path.join(lab.ROOT, "session-state.json")
SESSION_LOCK = os.path.join(lab.ROOT, ".session.lock")
LENSES = ("claude", "sol", "grok")
# An owed reading that could not be paid stops the session before the bench is touched.
# GONE and ALREADY_READ retire the debt; NOTHING_OWED and READ leave nothing outstanding.
HOLDS_THE_SESSION = ("STILL_HELD", "REFUSED")

# Every Nth offered session, all three lenses read the same preserved artifact. Off by
# default: it is three paid calls where a session normally spends one, and it should be
# switched on deliberately rather than arrive with a deploy.
DIVERGENCE_ENABLED = "divergence_enabled"
DIVERGENCE_EVERY = "divergence_every_n_sessions"
DEFAULT_DIVERGENCE_EVERY = 7


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


async def _frontier(lens, system, user, paid_reservation=None):
    import model_router
    convo = [{"role": "user", "content": user}]
    if lens == "claude":
        text, _ = await model_router.claude_draft(system, convo, max_tokens=700,
                                                   paid_reservation=paid_reservation)
        return text
    if lens == "sol":
        text, _ = await model_router.sol_draft(system, convo, max_tokens=700,
                                                paid_reservation=paid_reservation)
        return text
    import model_config
    result = await model_router.route_reply_result(
        "chemistry_lab", system, convo, {"max_tokens": 700, "temperature": 0.8},
        model_config.GROK_API, model_config.GROK_HEADERS, model_config.VINTOS_MODEL, reason=False,
        paid_reservation=paid_reservation)
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


def _plan(context, experiments, lens, instruments=None):
    system = ("You are Vintos choosing one experiment in his visible Chemistry Lab. Play and curiosity matter. "
              "Choose only a named experiment offered below; never provide wet-lab steps, synthesis advice, "
              "human targeting, pathogens, toxins, or claims of function or safety. Return one JSON object.")
    # The instrument states go in beside the experiment list rather than filtering it.
    # Silencing the Lab is not the remedy for having overstated it: he should see that an
    # instrument is only claimed by its host, and choose anyway if he likes.
    measured = json.dumps({name: {"available": state["available"], "state": state.get("state")}
                           for name, state in (instruments or {}).items()}, sort_keys=True)
    prompt = (context + "\n\nAVAILABLE NAMED EXPERIMENTS:\n" + json.dumps(experiments) +
              "\n\nINSTRUMENT STATES (measured receipts, not installations):\n" + measured +
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


def _divergence_due(state):
    """Deterministic, so it can be audited: every Nth offered session, not a dice roll."""
    cfg = lab.config()
    if not cfg.get(DIVERGENCE_ENABLED): return False
    try: every = max(2, int(cfg.get(DIVERGENCE_EVERY, DEFAULT_DIVERGENCE_EVERY)))
    except Exception: every = DEFAULT_DIVERGENCE_EVERY
    offered = int(state.get("offered", 0)) + 1
    return offered % every == 0


def _preserved_artifact():
    """The most recent completed run, exactly as it was kept. Nothing is re-run for this."""
    for row in reversed(lab._jsonl(SESSIONS)):
        if row.get("state") == "completed" and row.get("mac_result") and row.get("mac_run_id"):
            return row
    return None


def _divergence_prompt(context, artifact):
    """One prompt. Every lens gets this and nothing else — same artifact, same context."""
    session = {"experiment": (artifact.get("plan") or {}).get("experiment"),
               "question": (artifact.get("plan") or {}).get("question"),
               "mac_run_id": artifact.get("mac_run_id"),
               "grade": artifact.get("grade"), "result": artifact.get("mac_result")}
    return (context + "\n\nONE PRESERVED CHEMISTRY LAB RESULT:\n" +
            json.dumps(session, ensure_ascii=False, sort_keys=True)[:12000] +
            "\n\nThis already ran; nothing is being run for you. Return keys in this order: "
            "question (the one you would ask of this next), why_this, what_you_notice.")


def _divergence(context, artifact, reservations, lenses=LENSES):
    """The same artifact to each lens, independently, and no attempt to reconcile them.

    They are blind to one another's answers on purpose. Three readings that agree would be
    a fact about how these models are trained; three that diverge are three questions, and
    the questions are the output. Nothing here scores agreement or synthesises a verdict.
    """
    system = ("You are one reading of Vintos's Chemistry Lab result. Be curious and specific. "
              "This is a simulated artifact, not proof about biology or about him; never give wet-lab "
              "steps, synthesis advice, human targeting, pathogens or toxins. Return one JSON object.")
    prompt = _divergence_prompt(context, artifact)
    prompt_sha = hashlib.sha256(json.dumps({"system": system, "user": prompt},
                                           sort_keys=True).encode()).hexdigest()
    readings = []
    for lens in lenses:
        try:
            from compute_admission import admit
            with admit("background", organ="chemistry-divergence", wait_s=2,
                       provider=reservations[lens]["provider"],
                       model=reservations[lens]["model"], stage="lens:" + lens):
                raw = asyncio.run(_frontier(lens, system, prompt,
                                            paid_reservation=reservations[lens]))
            value = lab._json_object(raw) if raw else {}
            readings.append({"lens": lens, "state": "read",
                             **{key: str(value.get(key, ""))[:800]
                                for key in ("question", "why_this", "what_you_notice")}})
        except Exception as exc:
            # Admission can refuse before a provider is contacted. That reservation did
            # no work and is returned; after entry, failures are ambiguous and stay spent.
            if isinstance(exc, TimeoutError):
                try:
                    from compute_admission import release_paid
                    r = reservations[lens]
                    release_paid(r["organ"], r["provider"], r["model"], why="yielded before call",
                                 reservation_id=r["reservation_id"])
                except Exception: pass
            # A lens that refuses or fails is held, exactly as in an ordinary session. It is
            # never replaced by another provider, and its absence is not filled in.
            readings.append({"lens": lens, "state": "held",
                             "error": exc.__class__.__name__, "detail": str(exc)[:200]})
    return readings, prompt_sha


def _divergence_specs():
    """The real provider buckets/models which the router will claim, not lens nicknames."""
    import model_router, model_config
    return {
        "claude": ("anthropic", model_router.current_claude_model()),
        "sol": ("openai", model_router.SOL_MODEL),
        "grok": ("xai", model_config.VINTOS_MODEL),
    }


def _run_divergence(session_id, state, context, receipt):
    """Three lenses, one artifact, three questions. All three reserved before the first."""
    artifact = _preserved_artifact()
    if artifact is None:
        return {"session_id": session_id, "at": lab.now_iso(), "mode": "divergence",
                "state": "held_no_preserved_artifact",
                "truth_status": "nothing_to_read_no_experiment_run"}
    # Reserve every lens before spending any of them. A third reservation refused after two
    # calls would leave a two-lens "divergence" that looks like a finding and is not one.
    reservations, refusal = {}, None
    try:
        from compute_admission import reserve_paid, release_paid
        specs = _divergence_specs()
    except Exception as exc:
        return {"session_id": session_id, "at": lab.now_iso(), "mode": "divergence",
                "state": "held_no_paid_ledger", "detail": str(exc)[:160]}
    for lens in LENSES:
        reservation_id = "CHEMDIV-" + uuid.uuid4().hex[:10]
        provider, model = specs[lens]
        ok, why = reserve_paid("chemistry-divergence", provider, model=model, units=1,
                               reservation_id=reservation_id)
        if not ok: refusal = "%s: %s" % (lens, str(why)[:120]); break
        reservations[lens] = {"organ": "chemistry-divergence", "provider": provider,
                              "model": model, "reservation_id": reservation_id}
    if refusal:
        for reserved in reservations.values():
            release_paid(reserved["organ"], reserved["provider"], reserved["model"],
                         why="divergence not run", reservation_id=reserved["reservation_id"])
        return {"session_id": session_id, "at": lab.now_iso(), "mode": "divergence",
                "state": "held_paid_cap", "detail": refusal,
                "truth_status": "no_lens_was_spent_because_all_three_could_not_be"}
    readings, prompt_sha = _divergence(context, artifact, reservations)
    held = [r["lens"] for r in readings if r["state"] == "held"]
    row = {"session_id": session_id, "at": lab.now_iso(), "mode": "divergence",
           "state": "completed_with_held_lenses" if held else "completed",
           "read_of": artifact.get("mac_run_id"),
           "source_session_id": artifact.get("session_id"),
           "experiment": (artifact.get("plan") or {}).get("experiment"),
           "identical_prompt_sha256": prompt_sha, "context_receipt": receipt["context_sha256"],
           "readings": readings,
           "lenses_read": [r["lens"] for r in readings if r["state"] == "read"],
           "lenses_held": held,
           "agreement": "not_computed",
           "truth_status": "three_independent_readings_no_consensus_claim"}
    lab._append(DIVERGENCE, row)
    lab._append(lab.NOTEBOOK, {"at": row["at"], "kind": "divergence", "session_id": session_id,
                               "read_of": row["read_of"], "experiment": row["experiment"],
                               "questions": [{"lens": r["lens"], "question": r.get("question", "")}
                                             for r in readings if r["state"] == "read"],
                               "agreement": "not_computed",
                               "truth_status": row["truth_status"]})
    return row


def run():
    if not lab.config()["enabled"]: return {"ok": True, "state": "off"}
    with _exclusive():
        started = time.time(); state = _state(); lens = LENSES[int(state.get("lens_index", 0)) % len(LENSES)]
        session_id = "CHEM-" + uuid.uuid4().hex[:12]
        # An experiment already run and never read is owed a reading before another is
        # started. It costs no bench time: the result is already preserved.
        try: settled = owed.settle_one()
        except Exception as exc: lab._fault("settle_owed", exc); settled = {"outcome": "REFUSED"}
        # And if that debt could not be paid, the session ends here. Running another
        # experiment on top of an unread one is precisely how the pile grows: the house was
        # busy or the reader faulted, and neither is a reason to spend the bench again.
        if settled.get("outcome") in HOLDS_THE_SESSION:
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens,
                   "state": "held_reading_owed", "owed_reading": settled.get("outcome"),
                   "owed_session_id": settled.get("session_id"),
                   "detail": str(settled.get("detail") or settled.get("error") or "")[:200],
                   "truth_status": "no_experiment_run_while_one_is_still_unread"}
            lab._append(SESSIONS, row)
            # The lens does not advance: it never got its turn.
            return row
        # Refresh only the instrument receipts that have actually expired. A passing
        # receipt holds a month, so this is a real monthly measurement rather than a daily
        # one, and it runs inside the background slot so it yields like everything else.
        # An unrefreshed instrument simply reads stale, which is the honest outcome.
        try:
            from compute_admission import admit as _admit
            with _admit("background", organ="chemistry-instrument-probe", wait_s=2,
                        provider="local", stage="probe"):
                probed = [r["tool"] for r in probe.refresh(only_expired=True)]
        except TimeoutError: probed = []
        except Exception as exc: lab._fault("probe_refresh", exc); probed = []
        # Occasionally the whole session is three readings of one artifact he already has,
        # rather than a new experiment. It touches no bench.
        if _divergence_due(state):
            context, receipt = lab.lab_context()
            row = _run_divergence(session_id, state, context, receipt)
            state.update({"offered": int(state.get("offered", 0)) + 1,
                          "last_session_id": session_id, "last_state": row["state"],
                          "last_at": row["at"], "last_mode": "divergence"})
            lab._atomic(SESSION_STATE, state)
            lab._append(SESSIONS, row)
            return row
        remote = mac.status()
        # The Mac's word about its own instruments is filed as a claim, never as a measurement.
        try: probe.record_host_report(remote)
        except Exception as exc: lab._fault("host_report", exc)
        experiments = remote.get("experiments") if remote.get("ok") else None
        if not isinstance(experiments, list) or not experiments:
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "held_mac_unavailable",
                   "owed_reading": settled.get("outcome"),
                   "detail": str(remote.get("error", "no experiments offered"))[:300]}
            lab._append(SESSIONS, row); return row
        context, receipt = lab.lab_context()
        instruments = lab.tools_status()
        plan = None; result = None; grade = None
        try:
            from compute_admission import admit
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="frontier", stage="plan"):
                plan = _plan(context, experiments, lens, instruments)
            result = mac.run(plan["experiment"], plan["parameters"], plan["shots"])
            if not result.get("ok"): raise RuntimeError(result.get("error", "Mac experiment failed"))
            # Grading is arithmetic, not a model call: it happens before the reading asks for
            # compute, so a preempted reading never costs us the verdict.
            grade = grading.grade(result.get("run_id"), plan["experiment"], result, plan)
            # A completed run proves only the instruments it names and hashes.
            try: probe.record_run_attestation(result.get("run_id"), result)
            except Exception as exc: lab._fault("run_attestation", exc)
            with admit("background", organ="chemistry-frontier-session", wait_s=2,
                       provider="local", model=lab.LLM_MODEL, stage="reading"):
                reading = _reading(context, plan, result, grade)
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens, "state": "completed",
                   "plan": plan, "mac_run_id": result.get("run_id"), "mac_result": result,
                   "grade": grade, "reading": reading, "context_receipt": receipt["context_sha256"],
                   "owed_reading": settled.get("outcome"),
                   "instrument_states": {name: state.get("state") for name, state in instruments.items()},
                   "instruments_refreshed": probed,
                   "truth_status": "generated_lab_interpretation_not_biological_evidence",
                   "elapsed_ms": int((time.time() - started) * 1000)}
            if result.get("run_id"):
                mac.reading(result["run_id"], reading.get("reading", ""))
            lab._append(SESSIONS, row)
            # Taste accrues from what he chose, never from how the run scored.
            try: taste.observe_session(row)
            except Exception as exc: lab._fault("taste", exc, session_id=session_id)
            lab._append(lab.NOTEBOOK, {"at": row["at"], "kind": "frontier_session",
                         "session_id": session_id, "lens": lens, "experiment": plan["experiment"],
                         "question": plan["question"],
                         "execution_state": (grade or {}).get("execution_state"),
                         "aggregate_accuracy": (grade or {}).get("aggregate_accuracy"), **reading,
                         "truth_status": row["truth_status"]})
            # Keep the Lab's candidate feed current even while the want door remains an
            # explicit, separately configured act. A deployed producer with no caller is
            # not a route; it is a command somebody has to remember to run.
            try:
                import chemistry_spark
                chemistry_spark.refresh()
            except Exception as exc: lab._fault("spark_refresh", exc, session_id=session_id)
            state.update({"lens_index": (LENSES.index(lens) + 1) % len(LENSES),
                          "offered": int(state.get("offered", 0)) + 1,
                          "last_session_id": session_id, "last_state": "completed",
                          "last_at": row["at"], "last_mode": "experiment"})
            lab._atomic(SESSION_STATE, state)
            return row
        except TimeoutError:
            held = bool(result and result.get("ok"))
            row = {"session_id": session_id, "at": lab.now_iso(), "lens": lens,
                   "state": "experiment_completed_reading_held" if held else "yielded_to_house"}
            if held:
                # The experiment finished and its result is preserved. Owe the reading
                # rather than leaving it for nobody.
                try: owed.owe(session_id, lens, plan, result, grade, receipt["context_sha256"])
                except Exception as exc: lab._fault("owe_reading", exc, session_id=session_id)
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
                      "offered": int(state.get("offered", 0)) + 1,
                      "last_session_id": session_id, "last_state": row["state"],
                      "last_at": row["at"], "last_mode": "experiment"})
        lab._atomic(SESSION_STATE, state)
        return row


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "run": raise SystemExit("usage: chemistry_session.py [run]")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
