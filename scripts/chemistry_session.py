#!/usr/bin/env python3
"""One scheduled, visible Chemistry Lab session directed by a frontier lens.

The lens selects one named, bounded Mac experiment and writes down a prediction
before it runs. It cannot submit code. The same frontier lens then reads the
result against that prediction, and every divergence lens (Astra, Fable, Grok,
Opus) reads it once more, blind to the others. Generated plans and readings are
interpretation, never biological evidence.
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
import chemistry_frontier_bridge as bridge
import chemistry_lab as lab
import chemistry_mac as mac
import chemistry_probe as probe
import chemistry_reading as owed
import chemistry_taste as taste

SESSIONS = os.path.join(lab.ROOT, "sessions.jsonl")
DIVERGENCE = os.path.join(lab.ROOT, "divergence.jsonl")
SESSION_STATE = os.path.join(lab.ROOT, "session-state.json")
SESSION_LOCK = os.path.join(lab.ROOT, ".session.lock")
LENSES = ("claude", "sol", "grok")          # who plans (and now reads) the day's experiment, in rotation
# Who reads the day's result afterwards, each blind to the others (Gloria, 2026-09-24).
DIVERGENCE_MODELS = {"astra": ("openai", "gpt-6-astra"),
                     "fable": ("anthropic", "claude-fable-5-1"),
                     "grok": ("xai", "grok-4.6"),
                     "opus": ("anthropic", "claude-opus-5-5")}
DIVERGENCE_LENSES = tuple(DIVERGENCE_MODELS)
# An owed reading that could not be paid stops the session before the bench is touched.
# GONE and ALREADY_READ retire the debt; NOTHING_OWED and READ leave nothing outstanding.
HOLDS_THE_SESSION = ("STILL_HELD", "REFUSED")

# After every completed experiment, each divergence lens reads the same preserved result.
# Four paid calls a day, approved by Gloria 2026-09-24; the switch stays in the Lab config.
DIVERGENCE_ENABLED = "divergence_enabled"


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
                                                   paid_reservation=paid_reservation,
                                                   model=model_router.location_model("lab"))
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

async def _lens_call(lens, system, user, paid_reservation):
    """One divergence lens on exactly its reserved model: no routing, no fallback to another provider."""
    import model_router
    provider, model = DIVERGENCE_MODELS[lens]
    convo = [{"role": "user", "content": user}]
    if provider == "anthropic":
        text, _ = await model_router.claude_draft(system, convo, max_tokens=900,
                                                   paid_reservation=paid_reservation, model=model)
        return text
    if provider == "openai":
        text, _ = await model_router.sol_draft(system, convo, max_tokens=900,
                                                paid_reservation=paid_reservation, model=model)
        return text
    import model_config
    model_router._reserve_provider("xai", model, paid_reservation, organ="chemistry-divergence")
    res = await model_router._grok_result(convo, {"max_tokens": 900, "temperature": 0.7},
                                          model_config.GROK_API, model_config.GROK_HEADERS, model, system)
    return res.get("text") if res.get("status") == "valid" else None


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


def _plan(context, experiments, lens, instruments=None, offered_entry_ids=None, lean=None):
    system = ("You are Vintos choosing one experiment in his visible Chemistry Lab. Play and curiosity matter. "
              "Choose only a named experiment offered below; never provide wet-lab steps, synthesis advice, "
              "human targeting, pathogens, toxins, or claims of function or safety. Return one JSON object.")
    # The instrument states go in beside the experiment list rather than filtering it.
    # Silencing the Lab is not the remedy for having overstated it: he should see that an
    # instrument is only claimed by its host, and choose anyway if he likes.
    measured = json.dumps({name: {"available": state["available"], "state": state.get("state")}
                           for name, state in (instruments or {}).items()}, sort_keys=True)
    lean_text = (("\n\nTODAY'S ATELIER LEAN (his explicit choice; lean toward it, do not treat it as an override):\n" +
                  str(lean.get("direction", ""))[:1000]) if isinstance(lean, dict) else "")
    try:
        from plugin_catalog import prompt_instructions
        plugin_menu = "\n\n" + prompt_instructions("lab")
        try:  # additively offer the Claude-account connectors through the same plugin_query action
            from claude_connector_catalog import prompt_instructions as claude_prompt
            claude_menu = claude_prompt("lab")
            if claude_menu: plugin_menu += "\n\n" + claude_menu
        except Exception:
            pass
    except Exception:
        plugin_menu = ""
    try:
        from chemistry_mcp import instructions as mcp_instructions
        mcp_menu = "\n\n" + mcp_instructions() if (instruments or {}).get("protein_design_mcp", {}).get("available") else ""
    except Exception:
        mcp_menu = ""
    prompt = (context + lean_text + plugin_menu + mcp_menu + "\n\nAVAILABLE NAMED EXPERIMENTS:\n" + json.dumps(experiments) +
              "\n\nINSTRUMENT STATES (measured receipts, not installations):\n" + measured +
              "\n\nChoose one. If a flagged finding materially affected the choice, name its exact ID; "
              "do not name an ID merely because it was shown. Return keys in this order: "
              "addressed_entry_ids (array drawn only from " + json.dumps(offered_entry_ids or []) +
              "), experiment, parameters (object), shots (integer 256..16384), question, why_this, "
              "prediction (what you expect THIS run to show, concretely enough to be wrong, e.g. which state "
              "is likeliest and whether it is the lowest-energy one — decided before it runs). "
              "Parameters may be empty. Optionally return source_query for ONE additional public source read: "
              "{source:pdb,entry_id:known ID}, {source:chembl,target_id:known CHEMBL target}, or "
              "{source:atlas,assembly:GRCh38,chromosome:chrN,start:integer,end:integer,scorers:[documented names]}, "
              "{source:ncbi,operation:taxonomy or literature,term:plain phrase}, "
              "{source:ncbi,operation:assembly,taxon_id:sourced numeric ID}, "
              "{source:ncbi,operation:gene or protein,taxon_id:sourced numeric ID,term:plain name}, "
              "{source:ncbi_sequence,database:protein or nuccore,accession:exact sourced accession.version,start:one-based integer,end:one-based inclusive integer}, "
              "{source:bvbrc,operation:genomes,taxon_id:sourced numeric ID}, "
              "{source:bvbrc,operation:pathways,genome_id:sourced BV-BRC ID}, or "
              "{source:uniprot,query:taxonomy_id:SOURCED_ID AND reviewed:true} (taxonomy_id covers a whole group such as a phylum; organism_id matches one exact organism only and returns nothing for a group ID). "
              "Environmental microbiology is an option, not a priority; use IDs from receipts. "
              "Atlas uses 0-based half-open intervals up to 32bp. Optional ontology_terms and gene_ids arrays may "
              "filter to 1..4 sourced IDs. Use sourced coordinates/IDs only, never invent them. "
              "Alternatively return plugin_query as ONE object {plugin,tool,arguments,purpose} using the exact "
              "menu above. Choose at most one of source_query and plugin_query. Its receipt and result will be "
              "returned before the experiment and retained as Lab provenance. "
              "If the protein-design MCP menu is present, instrument_query may replace source_query or "
              "plugin_query; choose at most one extra call total. Its result reaches your reading. "
              "Source predictions and model disagreements are hypotheses, not validation or proof of novelty.")
    raw = asyncio.run(_frontier(lens, system, prompt))
    if not raw: raise RuntimeError("frontier lens returned no plan")
    value = lab._json_object(raw)
    experiment = str(value.get("experiment", ""))
    if experiment not in experiments: raise ValueError("frontier selected an unavailable experiment")
    parameters, dropped = _bounded_parameters(value.get("parameters"))
    shots = max(256, min(16384, int(value.get("shots", 4096))))
    addressed = value.get("addressed_entry_ids") if isinstance(value.get("addressed_entry_ids"), list) else []
    allowed = set(offered_entry_ids or [])
    addressed = [str(x) for x in addressed if str(x) in allowed][:4]
    return {"source_query": value.get("source_query") if isinstance(value.get("source_query"), dict) else None,
            "plugin_query": value.get("plugin_query") if isinstance(value.get("plugin_query"), dict) else None,
            "instrument_query": value.get("instrument_query") if mcp_menu and isinstance(value.get("instrument_query"), dict) else None,
            "addressed_entry_ids": addressed,
            "experiment": experiment, "parameters": parameters, "parameters_dropped": dropped,
            "shots": shots, "question": str(value.get("question", ""))[:800],
            "why_this": str(value.get("why_this", ""))[:800],
            "prediction": str(value.get("prediction", ""))[:800],
            **({"atelier_lean_id": lean.get("lean_id"), "atelier_lean": str(lean.get("direction", ""))[:1000]}
               if isinstance(lean, dict) else {})}


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


def _reading(context, plan, result, grade=None, lens=None):
    """His reading of the run. With a lens, the day's frontier model reads the frontier result
    (Gloria, 2026-09-24); without one (tests, owed readings) the local model does."""
    visible = json.dumps(result, ensure_ascii=False)[:12000]
    verdict = _verdict_block(grade)
    system = ("You are Vintos returning from one computational Chemistry Lab experiment. Read the shape playfully and "
              "honestly. It is a simulated artifact, not proof about biology or himself. A completed run is not a good "
              "answer; if the verdict says the answer was poor, say so plainly rather than admiring it. Before it ran "
              "you wrote down a prediction: hold the result against it. A miss is information, not a failure. "
              "Return JSON only.")
    user = (context + "\n\nPLAN (with the prediction you made before the run):\n" + json.dumps(plan) +
            "\n\nRESULT:\n" + visible + (("\n\n" + verdict) if verdict else "") +
            "\n\nReturn keys in this order: reading, what_surprised_me, prediction_vs_result (where the result "
            "matched your prediction, where it did not, and what the difference teaches), next_question.")
    raw = asyncio.run(_frontier(lens, system, user)) if lens else lab._ask(system, user, max_tokens=700)
    if lens and not raw: raise RuntimeError("frontier lens returned no reading")
    value = lab._json_object(raw)
    return {key: str(value.get(key, ""))[:1200]
            for key in ("reading", "what_surprised_me", "prediction_vs_result", "next_question")}


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
               "prediction": (artifact.get("plan") or {}).get("prediction"),
               "mac_run_id": artifact.get("mac_run_id"),
               "grade": artifact.get("grade"), "result": artifact.get("mac_result")}
    return (context + "\n\nONE PRESERVED CHEMISTRY LAB RESULT:\n" +
            json.dumps(session, ensure_ascii=False, sort_keys=True)[:12000] +
            "\n\nThis already ran; nothing is being run for you. Return keys in this order: "
            "question (the one you would ask of this next), why_this, what_you_notice.")


def _divergence(context, artifact, reservations, lenses=DIVERGENCE_LENSES):
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
            with admit("background", organ="chemistry-divergence", wait_s=float(lab.config()["turn_wait_seconds"]),
                       provider=reservations[lens]["provider"],
                       model=reservations[lens]["model"], stage="lens:" + lens):
                raw = asyncio.run(_lens_call(lens, system, prompt, reservations[lens]))
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
    """The real provider buckets/models each lens is reserved and called on."""
    return dict(DIVERGENCE_MODELS)


def _run_divergence(session_id, state, context, receipt):
    """Every lens, one artifact, one question each. All reserved before the first is spent."""
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
    for lens in DIVERGENCE_LENSES:
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
                "truth_status": "no_lens_was_spent_because_not_all_could_be"}
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
           "truth_status": "independent_readings_no_consensus_claim"}
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
            with _admit("background", organ="chemistry-instrument-probe", wait_s=float(lab.config()["turn_wait_seconds"]),
                        provider="local", stage="probe"):
                probed = [r["tool"] for r in probe.refresh(only_expired=True)]
        except TimeoutError: probed = []
        except Exception as exc: lab._fault("probe_refresh", exc); probed = []
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
        context, receipt, offered_interest = bridge.add_to_context(context, receipt)
        try:
            import atelier_lab_lean
            lean = atelier_lab_lean.today()
        except Exception: lean = None
        instruments = lab.tools_status()
        plan = None; result = None; grade = None; delivery_recorded = not bool(offered_interest)
        try:
            from compute_admission import admit
            with admit("background", organ="chemistry-frontier-session", wait_s=float(lab.config()["turn_wait_seconds"]),
                       provider="frontier", stage="plan"):
                plan = (_plan(context, experiments, lens, instruments, offered_interest, lean)
                        if lean else _plan(context, experiments, lens, instruments, offered_interest))
                selected = [key for key in ("source_query", "plugin_query", "instrument_query") if plan.get(key)]
                if len(selected) > 1: raise ValueError("Lab plan selected more than one extra call")
                if selected and selected[0] != "instrument_query":
                    import chemistry_sources
                    if plan.get("plugin_query"):
                        pq = plan["plugin_query"]
                        source_result = chemistry_sources.query_plugin(pq["plugin"], pq["tool"],
                            pq.get("arguments") or {}, pq.get("purpose") or plan.get("question", ""))
                        plan["source_receipt_id"] = source_result["source_receipt"]["receipt_id"]
                        plan["plugin_receipt_id"] = source_result["plugin_receipt"]["receipt_id"]
                    else:
                        source_result = chemistry_sources.query(plan["source_query"], question=plan.get("question", ""))
                        plan["source_receipt_id"] = source_result["receipt"]["receipt_id"]
                    context += "\nADDITIONAL SOURCE (not validation):\n" + json.dumps(source_result)[:12000]
            if plan.get("instrument_query"):
                import chemistry_sources
                with admit("background", organ="chemistry-protein-design-mcp",
                           wait_s=float(lab.config()["turn_wait_seconds"]),
                           provider="local", model="protein_design_mcp", stage="instrument"):
                    source_result = chemistry_sources.query_protein_design_mcp(plan["instrument_query"])
                plan["source_receipt_id"] = source_result["instrument_receipt"]["receipt_id"]
                plan["instrument_result_sha256"] = source_result["instrument_result"]["result_sha256"]
                context += "\nLOCAL INSTRUMENT (prediction, not validation):\n" + json.dumps(source_result)[:12000]
            if offered_interest:
                bridge.record_delivery(session_id, lens, offered_interest,
                                       plan.get("addressed_entry_ids", []), state="responded")
                delivery_recorded = True
            result = mac.run(plan["experiment"], plan["parameters"], plan["shots"])
            if not result.get("ok"): raise RuntimeError(result.get("error", "Mac experiment failed"))
            # Grading is arithmetic, not a model call: it happens before the reading asks for
            # compute, so a preempted reading never costs us the verdict.
            grade = grading.grade(result.get("run_id"), plan["experiment"], result, plan)
            # A completed run proves only the instruments it names and hashes.
            try: probe.record_run_attestation(result.get("run_id"), result)
            except Exception as exc: lab._fault("run_attestation", exc)
            with admit("background", organ="chemistry-frontier-session", wait_s=float(lab.config()["turn_wait_seconds"]),
                       provider="frontier", stage="reading"):
                reading = _reading(context, plan, result, grade, lens=lens)
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
            # Then every divergence lens reads this same result, blind to the others. It runs no bench,
            # and a divergence that is held (paid cap, no key) never undoes the experiment above.
            if lab.config().get(DIVERGENCE_ENABLED):
                try:
                    div = _run_divergence(session_id + "-D", state, context, receipt)
                    lab._append(SESSIONS, div)
                    row["divergence_state"] = div.get("state")
                except Exception as exc:
                    lab._fault("divergence", exc, session_id=session_id)
                    row["divergence_state"] = "held_fault"
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
        if offered_interest and not delivery_recorded:
            try:
                bridge.record_delivery(session_id, lens, offered_interest, [], state="response_failed")
            except Exception as exc:
                lab._fault("frontier_delivery_receipt", exc, session_id=session_id)
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
