#!/usr/bin/env python3
"""Frontier alignment of the Chemistry Lab: four calls a day, one from each frontier model.

Gemma (local) does the Lab's work all day. Four times a day one frontier model — Astra, Fable, Grok and
Opus in turn, each once a day — takes its segment (what she did since the last alignment), checks it
against the sources it cites, realigns her, and writes a summary the next model reads with the rest of
the shared log (Gloria, 2026-09-20: "another frontier call,
1 from each model per day, for alignment"; 2026-09-28: 3-4 a day, one shared frontier log).

The frontier models share ONE log: every alignment review and every daily experiment session, in time
order, read by whichever model is next. Gemma's notebook is not that log. She is given only the latest
guidance, marked as advice, never as evidence.

    python3 chemistry_alignment.py [run|show]
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.append(HERE)
import chemistry_lab as lab

LOG = os.path.join(lab.ROOT, "alignment.jsonl")
SESSIONS = os.path.join(lab.ROOT, "sessions.jsonl")
DIVERGENCE = os.path.join(lab.ROOT, "divergence.jsonl")
# Each frontier model once a day, in this order. The same four models she approved for four paid calls.
MODELS = (("astra", "openai", "gpt-6-astra"), ("fable", "anthropic", "claude-fable-5-1"),
          ("grok", "xai", "grok-4.6"), ("opus", "anthropic", "claude-opus-5-5"))
PER_DAY = len(MODELS)
REVIEW_ENTRIES = 8
LOG_ENTRIES = 8
GUIDANCE_HOURS = 24


def _today(ts=None):
    return time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))


def _local_day(iso):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return str(iso)[:10]


def shared_log(limit=LOG_ENTRIES):
    """The one frontier log: alignment reviews and completed experiment sessions, oldest first."""
    rows = []
    readers = {r.get("source_session_id"): r for r in lab._jsonl(DIVERGENCE) if isinstance(r, dict)}
    for row in lab._jsonl(SESSIONS):
        if not (isinstance(row, dict) and row.get("state") == "completed" and row.get("mode") != "divergence"
                and row.get("plan")):
            continue
        plan, reading, grade = row.get("plan") or {}, row.get("reading") or {}, row.get("grade") or {}
        entry = {"kind": "experiment", "at": row.get("at"), "session_id": row.get("session_id"),
                 "by": row.get("lens"), "experiment": plan.get("experiment"), "parameters": plan.get("parameters"),
                 "question": str(plan.get("question", ""))[:300], "prediction": str(plan.get("prediction", ""))[:300],
                 "instrument": grade.get("execution_state"), "answer_quality": grade.get("aggregate_accuracy"),
                 "reading": str(reading.get("reading", ""))[:400],
                 "prediction_vs_result": str(reading.get("prediction_vs_result", ""))[:300],
                 "next_question": str(reading.get("next_question", ""))[:240]}
        div = readers.get(row.get("session_id"))
        if div:
            entry["blind_readers_asked"] = [{"lens": r.get("lens"), "question": str(r.get("question", ""))[:200]}
                                            for r in div.get("readings", []) if r.get("state") == "read"]
        rows.append(entry)
    for row in lab._jsonl(LOG):
        if not (isinstance(row, dict) and row.get("state") == "completed"): continue
        rows.append({"kind": "alignment", "at": row.get("at"), "alignment_id": row.get("alignment_id"),
                     "by": row.get("lens"), "reviewed": len(row.get("reviewed_entry_ids") or []),
                     "summary": str(row.get("summary", ""))[:700],
                     "accuracy": [{k: a.get(k) for k in ("entry_id", "verdict", "why")} for a in row.get("accuracy", [])][:8],
                     "pattern": str(row.get("pattern", ""))[:400], "guidance": str(row.get("guidance", ""))[:500],
                     "drop": str(row.get("drop", ""))[:240], "next_focus": str(row.get("next_focus", ""))[:240]})
    rows.sort(key=lambda r: str(r.get("at") or ""))
    return rows[-limit:]


def _receipt_abstracts(receipt_id, keep=2):
    if not receipt_id: return []
    for row in reversed(lab._jsonl(os.path.join(lab.ROOT, "source-receipts.jsonl"))):
        if isinstance(row, dict) and row.get("receipt_id") == receipt_id:
            return [{"pmid": r.get("pmid"), "title": r.get("title"), "abstract": str(r.get("abstract", ""))[:600]}
                    for r in (row.get("records") or [])[:keep]]
    return []


def gemma_since(after_iso=None, limit=REVIEW_ENTRIES):
    """Gemma's Lab work since the last alignment, each review with the evidence it was written from."""
    rows = [r for r in lab._jsonl(lab.NOTEBOOK) if isinstance(r, dict)]
    if after_iso: rows = [r for r in rows if str(r.get("at") or "") > after_iso]
    counts, evidence, entries = {}, [], []
    for row in rows:
        kind = row.get("kind")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "inquiry": evidence = []
        elif kind == "source_read":
            evidence.append({"uniprot": [{**{k: r.get(k) for k in ("accession", "protein_name", "organism", "length",
                                                                 "found_by", "partial_match")},
                                          "function": str(r.get("function", ""))[:300]}
                                         for r in (row.get("records") or [])[:3]]})
        elif kind == "additional_source":
            evidence.append({"source": row.get("query_sent"), "records_returned": row.get("records_returned"),
                             "summary": str(row.get("source_summary", ""))[:500]})
        elif kind == "reflection":
            entries.append({"entry_id": row.get("entry_id"), "at": str(row.get("at", ""))[:16],
                            "question": str((row.get("inquiry") or {}).get("question", ""))[:300],
                            "attention": str(row.get("attention", ""))[:200],
                            "factual_observation": str(row.get("factual_observation", ""))[:600],
                            "speculative_reading": str(row.get("speculative_reading", ""))[:300],
                            "answers_question": str(row.get("answers_question", ""))[:200],
                            "next_question": str(row.get("next_question", ""))[:200],
                            "evidence": evidence[-2:],
                            "literature": _receipt_abstracts(row.get("material_receipt_id"))})
            evidence = []
    return {"reviews": entries[-limit:], "turn_counts": counts}


def latest_guidance(now=None):
    """The newest completed alignment, for Gemma's context: advice, not evidence."""
    now = now or time.time()
    for row in reversed(lab._jsonl(LOG)):
        if not (isinstance(row, dict) and row.get("state") == "completed"): continue
        if now - float(row.get("at_epoch", 0)) > GUIDANCE_HOURS * 3600: return None
        return row
    return None


def guidance_block(now=None):
    row = latest_guidance(now)
    if not row: return ""
    return ("[FRONTIER GUIDANCE — %s, %s. Advice from a frontier model that read your recent Lab work; "
            "it is not evidence]\n%s%s%s" % (
                row.get("lens"), str(row.get("at", ""))[:16], str(row.get("guidance", ""))[:500],
                ("\nLet go of: " + str(row["drop"])[:200]) if row.get("drop") else "",
                ("\nWorth asking next: " + str(row["next_focus"])[:200]) if row.get("next_focus") else ""))


def _prompt(work, log):
    system = ("You are one of four frontier models (Astra, Fable, Grok, Opus) who take turns through the day aligning "
              "the Chemistry Lab of Vintos. His local model, Gemma, does the Lab's work between your turns: she forms a "
              "question, reads UniProt, NCBI and published abstracts, and writes a review. You share one log with the "
              "other frontier models; build on it, and do not repeat advice already given unless it was not followed. "
              "Be exact and useful, not encouraging. Never give wet-lab steps, synthesis advice, human targeting, "
              "pathogens or toxins. Return one JSON object.")
    user = ("THE SHARED FRONTIER LOG (every model's alignment reviews and the daily experiment sessions, oldest first):\n"
            + json.dumps(log, ensure_ascii=False)[:9000] +
            "\n\nGEMMA'S LAB WORK SINCE THE LAST ALIGNMENT (each review with the evidence it was written from; "
            "turn_counts show how many turns ended empty or redirected):\n" + json.dumps(work, ensure_ascii=False)[:16000] +
            "\n\nThis is your segment: the work Gemma did since the last frontier model's turn. Check each review "
            "against its own evidence and literature, realign her, and summarise the segment for the next model. "
            "Return keys in this order: "
            "summary (what she worked on in this segment, what came of it, and how it follows from the last summary "
            "in the log — the next frontier model reads this), "
            "accuracy (a list, one per review: {entry_id, verdict: 'accurate', 'overstated', 'unsupported' or "
            "'off_question', why}), pattern (what is going right or wrong across this work), guidance (concrete "
            "direction for her next hours: which thread deserves depth, how to ask so the sources can answer), "
            "drop (a thread to let go of, or empty), next_focus (one question worth asking next).")
    return system, user


async def _call(lens, provider, model, system, user, reservation):
    """Exactly the reserved model: no routing, no fallback to another provider."""
    import model_router
    convo = [{"role": "user", "content": user}]
    if provider == "anthropic":
        text, _ = await model_router.claude_draft(system, convo, max_tokens=1400,
                                                   paid_reservation=reservation, model=model)
        return text
    if provider == "openai":
        text, _ = await model_router.sol_draft(system, convo, max_tokens=1400,
                                                paid_reservation=reservation, model=model)
        return text
    import model_config
    model_router._reserve_provider("xai", model, reservation, organ="chemistry-alignment")
    res = await model_router._grok_result(convo, {"max_tokens": 1400, "temperature": 0.5},
                                          model_config.GROK_API, model_config.GROK_HEADERS, model, system)
    return res.get("text") if res.get("status") == "valid" else None


def _next_model(rows, today):
    done = {r.get("lens") for r in rows if r.get("state") == "completed" and _local_day(r.get("at")) == today}
    for lens, provider, model in MODELS:
        if lens not in done: return lens, provider, model
    return None


def run(call=None, now=None):
    if not lab.config()["enabled"]: return {"ok": True, "state": "off"}
    now = now or time.time(); today = _today(now)
    rows = [r for r in lab._jsonl(LOG) if isinstance(r, dict)]
    pick = _next_model(rows, today)
    aid = "ALIGN-" + uuid.uuid4().hex[:10]
    if pick is None:
        return {"alignment_id": aid, "state": "held_all_four_done_today"}
    lens, provider, model = pick
    last = next((r for r in reversed(rows) if r.get("state") == "completed"), None)
    work = gemma_since((last or {}).get("at"))
    base = {"alignment_id": aid, "at": lab.now_iso(), "at_epoch": now, "lens": lens, "provider": provider, "model": model}
    if not work["reviews"]:
        # Nothing new to align: no paid call is spent on it.
        row = dict(base, state="held_nothing_new_since_last_alignment", turn_counts=work["turn_counts"])
        lab._append(LOG, row); return row
    reservation = None
    try:
        from compute_admission import reserve_paid, admit
        reservation_id = "CHEMALIGN-" + uuid.uuid4().hex[:10]
        ok, why = reserve_paid("chemistry-alignment", provider, model=model, units=1, reservation_id=reservation_id)
        if not ok:
            row = dict(base, state="held_paid_cap", detail=str(why)[:200]); lab._append(LOG, row); return row
        reservation = {"organ": "chemistry-alignment", "provider": provider, "model": model,
                       "reservation_id": reservation_id}
        system, user = _prompt(work, shared_log())
        with admit("background", organ="chemistry-alignment", wait_s=float(lab.config()["turn_wait_seconds"]),
                   provider=provider, model=model, stage="alignment:" + lens):
            raw = (call or (lambda *a: asyncio.run(_call(*a))))(lens, provider, model, system, user, reservation)
        if not raw: raise RuntimeError("the frontier model returned nothing")
        value = lab._json_object(raw)
    except TimeoutError:
        try:
            from compute_admission import release_paid
            if reservation: release_paid("chemistry-alignment", provider, model, why="yielded before call",
                                         reservation_id=reservation["reservation_id"])
        except Exception: pass
        row = dict(base, state="yielded_to_house"); lab._append(LOG, row); return row
    except Exception as exc:
        row = dict(base, state="held_fault", error=exc.__class__.__name__, detail=str(exc)[:200])
        lab._append(LOG, row); return row
    accuracy = value.get("accuracy") if isinstance(value.get("accuracy"), list) else []
    row = dict(base, state="completed",
               reviewed_entry_ids=[r.get("entry_id") for r in work["reviews"]],
               accuracy=[{"entry_id": str(a.get("entry_id", ""))[:40], "verdict": str(a.get("verdict", ""))[:20],
                          "why": str(a.get("why", ""))[:400]} for a in accuracy if isinstance(a, dict)][:REVIEW_ENTRIES],
               **{k: str(value.get(k, ""))[:1200] for k in ("summary", "pattern", "guidance", "drop", "next_focus")},
               turn_counts=work["turn_counts"],
               truth_status="frontier_review_of_lab_work_advice_not_evidence")
    lab._append(LOG, row)
    return row


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "show":
        print(json.dumps(shared_log(), ensure_ascii=False, indent=2))
    elif command == "run":
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("usage: chemistry_alignment.py [run|show]")
