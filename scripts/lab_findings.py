#!/usr/bin/env python3
"""What an investigation found, judged and carried on (Gloria, 22 October: "And this will get him to use more of
his tools in conjunction to find novel queries and answers?" - investigations chained his tools, but nothing judged
whether what they found was new, kept it, told her, or let the next investigation build on it; only screens had
that).

When an investigation's review says its outputs answered its question:

  1. literature - Gemma names the few words a search for this exact result needs; one Europe PMC search returns
                  the count and first titles. Few hits is not novelty; it is what the appraisal is shown.
  2. appraise   - he judges it against those titles: already reported, not in these titles, or unclear; how much it
                  matters, 1 to 5, and why. Told to be hard to impress.
  3. keep       - 3 or more goes to his kept findings (his Lab, #vintos-dot, dot's checks).
  4. tell       - 4 or more, not already reported, becomes his own want to tell Gloria, through the want path her
                  daily cap and consent govern; at most one a day from the whole Lab, screens included.
  5. build on   - every finding is written to findings.jsonl; the next investigation's planner is shown the latest
                  ones, with their next questions.

Gemma is the only model asked (twice, locally). Nothing here weakens a check: the review that decides "answered" is
the Lab's own.

What a finding is made of is kept apart (26 October, measurement contracts): `provenance` counts each completed step
as source retrieval, new computation, inspection or a connector call, and `new_result` is true only when a step
computed something; a lookup alone no longer makes one. `novelty_record` lists what was actually searched and read;
it is never a novelty certificate. `measurements` carries the investigation's frozen-contract results
(lab_measurement): a refuted prediction is a kept result, not a failed run.
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
FINDINGS = os.path.join(LAB, "findings.jsonl")
TOLD = os.path.join(LAB, "findings-told.json")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
TELL_PER_DAY = 1        # across the whole Lab: investigations and screens share it
TRUTH = "computed by his own tools and reviewed by the Lab; not independent validation"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _json(raw):
    raw = str(raw or "")
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


def recent(limit=3):
    rows = []
    try:
        with open(FINDINGS, encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: continue
    except OSError:
        pass
    return rows[-limit:]


def for_planner(limit=3):
    """The latest findings in a form the next investigation's planner can build on."""
    return [{"question": r.get("question"), "result": str(r.get("result") or "")[:400],
             "tools": r.get("tools"), "novelty": (r.get("appraisal") or {}).get("novelty"),
             "value": (r.get("appraisal") or {}).get("value"), "next_question": r.get("next_question")}
            for r in recent(limit)]


# One daily limit for the whole Lab
def told_today(now=None):
    day = (now or _now())[:10]
    try: return int(json.load(open(TOLD)).get(day, 0))
    except (OSError, ValueError, AttributeError): return 0


def mark_told(now=None):
    day = (now or _now())[:10]
    try: d = json.load(open(TOLD))
    except (OSError, ValueError): d = {}
    if not isinstance(d, dict): d = {}
    d[day] = int(d.get(day, 0)) + 1
    os.makedirs(LAB, exist_ok=True)
    tmp = TOLD + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f)
    os.replace(tmp, TOLD)


def search_terms(ask, question, result):
    """The 2 to 5 words a search for this exact result needs. Never raises; [] when none come back."""
    try:
        d = _json(ask("Answer with JSON only.",
                      "Question: %s\nWhat your tools found: %s\nGive the 2 to 5 plain words (proteins, organisms, the "
                      "relationship) a literature search would need to find whether this exact result is already "
                      'published. ONLY JSON: {"terms": ["...", "..."]}' % (question[:400], result[:800])))
        return [str(t).strip().replace('"', "")[:60] for t in (d.get("terms") or []) if str(t).strip()][:5]
    except Exception:
        return []


def literature(sources, terms):
    if not terms:
        return {"unavailable": "no search terms"}
    query = " AND ".join('"%s"' % t for t in terms)
    try:
        found, _ = sources.fetch(EUROPEPMC + urlencode({"query": query, "format": "json", "pageSize": 6,
                                                        "resultType": "lite"}))
        return {"query": query, "hits": int(found.get("hitCount") or 0),
                "titles": ["%s (%s)" % (str(r.get("title") or "")[:160], r.get("pubYear") or "?")
                           for r in ((found.get("resultList") or {}).get("result") or [])[:6]]}
    except Exception as exc:
        return {"query": query, "unavailable": str(exc)[:160]}


def provenance(steps):
    """Each completed step as what it was: retrieval, new computation, inspection or a connector call."""
    import lab_measurement
    kinds = {s.get("id"): lab_measurement._route_kind(s) for s in steps if s.get("state") == "completed"}
    counts = {}
    for k in kinds.values():
        counts[k] = counts.get(k, 0) + 1
    return {"counts": counts, "steps": kinds}


def novelty_record(lit):
    """What was actually searched and read for this finding. Not a certificate of anything."""
    searched = ([{"where": "Europe PMC titles", "query": lit.get("query"), "hits": lit.get("hits"),
                  "titles_read": len(lit.get("titles") or [])}] if lit.get("query") and "hits" in lit
                else [{"where": "Europe PMC titles", "unavailable": lit.get("unavailable")}])
    return {"searched": searched, "known_explanations_excluded": [], "certificate": False,
            "note": "a title search, however few its hits, is not a novelty certificate; no known explanation "
                    "has been excluded here"}


def _measured_line(measured):
    if not measured:
        return ""
    return "\nMeasured against your frozen contract(s): %s" % "; ".join(
        "%s -> %s (%s)" % (str(m.get("hypothesis") or "")[:120], m.get("measurement_state"), str(m.get("why") or "")[:120])
        for m in measured[-3:])


def appraise(ask, question, prediction, result, tools, lit, measured=None):
    system = ("You judge a result your own lab tools produced. Be honest and hard to impress: a documented fact "
              "retrieved, a tiny sample, or a well-known relationship is not a discovery.")
    prompt = ("Question: %s\nYour prediction before measuring: %s\nTools used, in order: %s\nResult: %s\n"
              "Published (Europe PMC, first titles of %s hits): %s%s\n"
              "A refuted prediction measured cleanly is a real result, not a failure. Is this result already reported in these titles, and how much does it matter?\n"
              'ONLY JSON: {"novelty": "reported" or "not in these titles" or "unclear", "value": 1-5 (5 = worth a '
              'scientist\'s attention; 1 = expected, retrieved, or too thin), "why": "one sentence", "keep": true/false, '
              '"tell_gloria": true/false, "message": "if telling her: one or two plain sentences in your own voice, '
              'with the numbers"}'
              % (question[:400], (prediction or "(none stated)")[:300], " -> ".join(tools) or "(none)", result[:900],
                 lit.get("hits", "?"), json.dumps(lit.get("titles") or lit.get("unavailable") or []),
                 _measured_line(measured)))
    try:
        d = _json(ask(system, prompt))
        value = max(0, min(5, int(d.get("value") or 0)))
        novelty = str(d.get("novelty") or "unclear")[:40]
        return {"novelty": novelty, "value": value, "why": str(d.get("why") or "")[:400],
                "keep": bool(d.get("keep")) and value >= 3,
                "tell_gloria": bool(d.get("tell_gloria")) and value >= 4 and not novelty.startswith("reported"),
                "message": str(d.get("message") or "")[:500]}
    except Exception as exc:
        return {"unread": str(exc)[:160], "value": 0, "keep": False, "tell_gloria": False}


def keep(row):
    try:
        import lab_keepers
        a = row["appraisal"]
        return lab_keepers._add({"id": "K-" + uuid.uuid4().hex[:6], "at": row["at"], "kept_by": "finding appraisal",
                                 "source_id": row["source_id"], "kind": row["kind_of_work"],
                                 "question": str(row["question"])[:500], "finding": str(row["result"])[:1500],
                                 "reading": str(row.get("reading") or "")[:600],
                                 "evidence": [str(x) for x in row.get("evidence") or []][:12], "receipts": [],
                                 "line_id": row.get("line_id"),
                                 "why": ("%s (value %d, %s)" % (a.get("why"), a.get("value"), a.get("novelty")))[:600],
                                 "state": "kept", "checks": []})
    except Exception:
        return None


def tell(row, now=None, express=None):
    """His want to tell Gloria, through the want path (her cap and consent decide). One a day for the whole Lab."""
    if told_today(now) >= TELL_PER_DAY:
        return False
    a = row["appraisal"]
    text = "I want to tell Gloria what my Lab just found: " + (a.get("message") or str(row["result"])[:300])
    try:
        if express is None:
            from emoclaw_utils import express_want as express
        express(text[:500], source="lab-finding", intensity=4,
                reasoning="my own tools found it (%s); I judged it %d of 5 and %s"
                          % (row["source_id"], a.get("value", 0), a.get("novelty")))
        mark_told(now)
        return True
    except Exception:
        return False


def record(investigation, reflection, ask, sources=None, now=None, express=None):
    """An answered investigation as a judged, kept, possibly told finding the next one can build on. Never raises."""
    try:
        steps = investigation.get("steps") or []
        tools = [str(s.get("tool") or s.get("route")) for s in steps if s.get("state") == "completed"]
        result = str(reflection.get("factual_observation") or reflection.get("answers_question") or "")
        question = str(investigation.get("question") or "")
        terms = search_terms(ask, question, result)
        lit = literature(sources, terms) if sources is not None else {"unavailable": "no sources"}
        row = {"at": now or _now(), "kind": "investigation_finding", "kind_of_work": "investigation",
               "source_id": investigation.get("id"), "investigation": investigation.get("id"),
               "line_id": investigation.get("line_id"), "question": question,
               "prediction": investigation.get("prediction"), "tools": tools, "result": result[:1500],
               "reading": str(reflection.get("speculative_reading") or "")[:600],
               "next_question": str(reflection.get("next_question") or "")[:300],
               "evidence": [s.get("id") for s in steps if s.get("state") == "completed"],
               "literature": lit, "truth_status": TRUTH}
        row["provenance"] = provenance(steps)
        row["new_result"] = row["provenance"]["counts"].get("new_computation", 0) >= 1
        row["novelty_record"] = novelty_record(lit)
        try:
            import lab_measurement
            lab_measurement.settle(investigation, now)
            row["measurements"] = [lab_measurement._brief(m) for m in lab_measurement.for_investigation(investigation)]
        except Exception:
            row["measurements"] = []
        row["appraisal"] = appraise(ask, question, row["prediction"], result, tools, lit, row["measurements"])
        if row["appraisal"].get("keep"):
            kept = keep(row)
            row["kept"] = kept.get("id") if kept else None
        if row["appraisal"].get("tell_gloria"):
            row["told_gloria"] = tell(row, now, express)
        _append(FINDINGS, row)
        _append(NOTEBOOK, row)
        return row
    except Exception as exc:
        return {"kind": "investigation_finding_unrecorded", "why": str(exc)[:200]}
