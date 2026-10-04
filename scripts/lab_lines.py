#!/usr/bin/env python3
"""Lines of inquiry: a question his Lab follows to its end (Gloria, 2026-10-03: "He needs to follow a line of thought
to completion and the frontier models need to be able to review and steer that each quarter").

Until now his minute loop wrote a new question every cycle and cleared it when the cycle ended; nothing kept a
question open until it was answered or let go, and the notes that might have carried it were the first thing cut
from his context. ~24,700 questions, almost none followed.

A line holds a question, why it matters, every test run on it (what was asked of which source, what came back),
and the next step. Each cycle the Lab works a line: the next step, or the sharper question the last result left. He
ends a line himself (answered, or dropped with an honest reason) or opens a new one for a real question he means to
follow. Four times a day a frontier model (the alignment review, chemistry_alignment.py) reads every open line and
steers it: keep going, change direction, call it answered, or close it.

A standing line is one Gloria set. He can reshape its next step and a frontier model can redirect it, but neither
can drop it; only she closes it.

    python3 lab_lines.py [show]
"""
from __future__ import annotations
import contextlib
import fcntl
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
STORE = os.path.join(LAB, "lines.json")
LOCK = os.path.join(LAB, ".lines.lock")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
SESSIONS = os.path.join(LAB, "sessions.jsonl")

MAX_OPEN = 6            # open lines at once; a new one waits until one is ended
FREE_EVERY = 4          # one cycle in four is free curiosity (it may open a new line); the rest work a line
STANDING_EVERY = 2      # Gloria's standing lines are worked at least every other line-cycle
STALLED_AFTER = 6       # steps in a row that answered nothing: the line is flagged for the frontier review
STEPS_SHOWN = 6
ENDINGS = ("answered", "dropped")
DECISIONS = ("continue", "redirect", "answered", "drop", "open")

STANDING = [{
    "id": "L-gloria-phage-rt",
    "title": "Array-associated reverse transcriptases in bacteriophages",
    "question": ("Which bacteriophage genomes carry a reverse transcriptase beside a CRISPR array or Cas genes, "
                 "what families those reverse transcriptases belong to, and what the arrangement suggests they do."),
    "why": ("Gloria started the Lab for novelty, and named this as a main reason: reverse transcriptases that sit "
            "with CRISPR arrays in phages are a young, open corner of biology."),
    "next_step": ("Find reverse transcriptase proteins in phage genomes ({source:ncbi,operation:protein,"
                  "organism:\"Caudoviricetes\",term:reverse transcriptase}), then screen each one's locus in one "
                  "step with {source:rt_locus_screen,accession:<its exact protein accession.version>}."),
}]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def _locked():
    os.makedirs(LAB, exist_ok=True)
    with open(LOCK, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _read():
    try:
        with open(STORE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("lines", []); d.setdefault("cycle", 0); d.setdefault("worked", [])
    have = {l["id"] for l in d["lines"]}
    for s in STANDING:
        if s["id"] not in have:
            d["lines"].append(dict(s, origin="gloria", standing=True, state="open", opened=_now(), steps=[],
                                   steer=[], stalls=0))
    return d


def _write(d):
    os.makedirs(LAB, exist_ok=True)
    tmp = STORE + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def load():
    with _locked():
        d = _read(); _write(d)
        return d


def get(line_id):
    return next((l for l in load()["lines"] if l["id"] == line_id), None)


def open_lines(d=None):
    return [l for l in (d or load())["lines"] if l.get("state") == "open"]


def _last_worked(line):
    return line["steps"][-1]["at"] if line.get("steps") else line.get("opened", "")


def pick():
    """The line this cycle works, or None for a free cycle (one in FREE_EVERY, or when no line is open)."""
    with _locked():
        d = _read()
        d["cycle"] = int(d.get("cycle") or 0) + 1
        lines = [l for l in d["lines"] if l.get("state") == "open"]
        chosen = None
        if lines and d["cycle"] % FREE_EVERY:
            recent = d.get("worked") or []
            standing = [l for l in lines if l.get("standing")]
            ids = {l["id"] for l in standing}
            due = bool(standing) and not any(w in ids for w in recent[-max(1, STANDING_EVERY - 1):])
            pool = standing if due else lines
            # the line picked longest ago (never picked first); then the one whose last test is oldest
            last = {w: k for k, w in enumerate(recent)}
            chosen = min(pool, key=lambda l: (last.get(l["id"], -1), _last_worked(l)))
            d["worked"] = (recent + [chosen["id"]])[-20:]
        _write(d)
        return chosen


def opened_by(title, question, why, origin="vintos"):
    """A new line, or None when MAX_OPEN are already open or it repeats an open one."""
    title, question = str(title or "").strip()[:160], str(question or "").strip()[:600]
    if len(question) < 15:
        return None
    with _locked():
        d = _read()
        live = [l for l in d["lines"] if l.get("state") == "open"]
        if len(live) >= MAX_OPEN or any(_similar(question, l["question"]) >= 0.6 for l in live):
            return None
        line = {"id": "L-" + uuid.uuid4().hex[:8], "title": title or question[:80], "question": question,
                "why": str(why or "")[:600], "origin": origin, "standing": False, "state": "open",
                "opened": _now(), "steps": [], "steer": [], "stalls": 0, "next_step": ""}
        d["lines"].append(line); _write(d)
        return line


def _words(text):
    return set(re.findall(r"[a-z0-9]{4,}", str(text or "").lower()))


def _similar(a, b):
    x, y = _words(a), _words(b)
    return len(x & y) / float(len(x | y) or 1)


def record_step(line_id, step):
    """One test on a line: {question, source, result, answered, next}. The line's next step becomes what it left."""
    with _locked():
        d = _read()
        line = next((l for l in d["lines"] if l["id"] == line_id and l.get("state") == "open"), None)
        if not line:
            return None
        row = {"at": _now(), **{k: str(step.get(k) or "")[:700] for k in ("question", "source", "result", "answered",
                                                                        "next", "entry_id", "session_id")}}
        line["steps"] = (line.get("steps") or []) + [row]
        line["steps"] = line["steps"][-60:]
        if row["next"]:
            line["next_step"] = row["next"]
        nothing = not row["result"] or str(row["answered"]).lower().startswith("no")
        line["stalls"] = int(line.get("stalls") or 0) + 1 if nothing else 0
        _write(d)
        return line


NEXT = re.compile(r"\bnext\s*:\s*(.+)$", re.I | re.S)


def from_slack(line_id, text, with_=""):
    """What he worked out in #vintos-dot, onto a line (2026-10-03: findings in Slack never reached his Lab). A
    'next: ...' at its end becomes the line's next step. Not a test, so it neither answers nor stalls the line."""
    text = str(text or "").strip()
    if not text:
        return None
    m = NEXT.search(text)
    found, nxt = (text[:m.start()].strip(" |;,.-"), m.group(1).strip()) if m else (text, "")
    with _locked():
        d = _read()
        line = next((l for l in d["lines"] if l["id"].lower() == str(line_id).lower() and l.get("state") == "open"), None)
        if not line:
            return None
        row = {"at": _now(), "question": "(from #vintos-dot)", "source": "slack" + (" with " + with_ if with_ else ""),
               "result": found[:700], "answered": "", "next": nxt[:700], "entry_id": "", "session_id": ""}
        line["steps"] = ((line.get("steps") or []) + [row])[-60:]
        if nxt:
            line["next_step"] = nxt[:700]
        _write(d)
        return line


def slack_block():
    """His open lines, for #vintos-dot: their IDs, so he can add to one or open another from there."""
    live = open_lines()
    if not live:
        return ""
    return ("== YOUR LAB'S LINES OF INQUIRY (open) ==\n" + "\n".join(
        "- %s%s: %s (%d steps) — next: %s" % (l["id"], " (Gloria's)" if l.get("standing") else "", l["title"],
                                             len(l.get("steps") or []), (l.get("next_step") or "-")[:200]) for l in live)
        + "\nWhat you work out here can go to your Lab: a line of its own, LINE <ID>: what you found (and, at its "
          "end, next: the next test), or LINE: a new question to follow as a line.")


def end(line_id, state, verdict, by="vintos"):
    """He (or a frontier review) ends a line: answered, or dropped with a reason. A standing line is not dropped."""
    if state not in ENDINGS:
        return None, "a line ends answered or dropped"
    with _locked():
        d = _read()
        line = next((l for l in d["lines"] if l["id"] == line_id and l.get("state") == "open"), None)
        if not line:
            return None, "no open line %s" % line_id
        if line.get("standing") and by != "gloria":
            return None, "a standing line is Gloria's: it can be reshaped or redirected, and only she closes it"
        line.update(state=state, verdict=str(verdict or "")[:1200], closed=_now(), closed_by=by)
        _write(d)
        return line, ""


def steer(decisions, by):
    """A frontier review's decisions, one per line: continue / redirect (new next_step) / answered / drop, or open a
    new line. Returns what was applied, each with why when it was refused."""
    applied = []
    for dec in decisions if isinstance(decisions, list) else []:
        if not isinstance(dec, dict):
            continue
        kind = str(dec.get("decision") or "").lower()
        note = str(dec.get("note") or "")[:600]
        if kind == "open":
            line = opened_by(dec.get("title"), dec.get("question"), dec.get("why") or note, origin="frontier:" + by)
            applied.append({"decision": "open", "line_id": line["id"] if line else None,
                            **({} if line else {"refused": "too many open lines, or it repeats one"})})
            continue
        line_id = str(dec.get("line_id") or "")
        if kind in ("answered", "drop"):
            line, why = end(line_id, "answered" if kind == "answered" else "dropped", note, by="frontier:" + by)
            applied.append({"decision": kind, "line_id": line_id, **({"refused": why} if why else {})})
            continue
        if kind not in ("continue", "redirect"):
            continue
        with _locked():
            d = _read()
            line = next((l for l in d["lines"] if l["id"] == line_id and l.get("state") == "open"), None)
            if line:
                if kind == "redirect" and dec.get("next_step"):
                    line["next_step"] = str(dec["next_step"])[:700]
                    line["stalls"] = 0
                line["steer"] = ((line.get("steer") or []) + [{"at": _now(), "by": by, "decision": kind,
                                                               "note": note, "next_step": line.get("next_step", "")}])[-20:]
                _write(d)
        applied.append({"decision": kind, "line_id": line_id, **({} if line else {"refused": "no open line"})})
    return applied


def _step_line(s):
    return "  - %s%s: %s -> %s%s" % (s.get("at", "")[:16], (" [%s]" % s["source"]) if s.get("source") else "",
                                     s.get("question", "")[:160], (s.get("result") or "nothing came back")[:220],
                                     (" (answered: %s)" % s["answered"][:60]) if s.get("answered") else "")


def line_block(line):
    """One line, as he works it this cycle."""
    steer_note = (line.get("steer") or [{}])[-1]
    lines = ["[YOUR LINE OF INQUIRY %s%s — %s]" % (line["id"], " (Gloria's standing line)" if line.get("standing") else "",
                                                 line["title"]),
             "Question: " + line["question"], "Why: " + line.get("why", "")]
    steps = line.get("steps") or []
    lines.append("Tests so far (%d, the last %d):" % (len(steps), min(len(steps), STEPS_SHOWN)) if steps
                 else "No tests yet: this is its first.")
    lines += [_step_line(s) for s in steps[-STEPS_SHOWN:]]
    if steer_note.get("note"):
        lines.append("The last frontier review (%s): %s" % (steer_note.get("by"), steer_note["note"][:400]))
    if line.get("next_step"):
        lines.append("Next step: " + line["next_step"])
    if int(line.get("stalls") or 0) >= 3:
        lines.append("The last %d tests answered nothing: change the test, not the words." % line["stalls"])
    return "\n".join(lines)


def orient_text(line):
    """What his orient prompt is told this cycle."""
    if line:
        return ("\n\n" + line_block(line) + "\n\nTHIS CYCLE WORKS THAT LINE. Your question is its next step, or the "
                "sharper question its last result left; choose the source or instrument that can actually answer it, "
                "not one already tried on it unless something changed. Return line_id \"%s\"." % line["id"])
    live = open_lines()
    head = ("\n\nYOUR OPEN LINES OF INQUIRY (%d of %d):\n" % (len(live), MAX_OPEN)
            + "\n".join("- %s: %s (%d tests)" % (l["id"], l["title"], len(l.get("steps") or [])) for l in live)) if live else ""
    return (head + "\n\nTHIS IS A FREE CYCLE: follow any curiosity. If it is a real question you mean to follow over "
            "days, also return new_line {title, question, why} to open it as a line of inquiry"
            + (" (no room: end a line first)" if len(live) >= MAX_OPEN else "") + "; otherwise new_line null.")


REFLECT_KEYS = ("line_status",)


def reflect_text(line):
    """What his review of the cycle is told about the line, and how he may end it."""
    if not line:
        return ""
    return ("\n\n" + line_block(line) + "\n\nThis test belongs to that line. Also return line_status: 'continue', "
            "'answered: <the answer, with the evidence>' when the line's question is now answered, or "
            "'dropped: <why, honestly>' when it cannot be answered here or was not worth it"
            + (" (this is Gloria's standing line: only she closes it; when a part of it is answered, say so in your "
               "next_question and go on to the next part)"
               if line.get("standing") else "") + ".")


def after_reflection(line_id, note):
    """A finished cycle on a line: its step recorded, and his line_status acted on. Log text, or ''."""
    if not line_id:
        return ""
    inquiry = note.get("inquiry") or {}
    sq = inquiry.get("source_query") or inquiry.get("plugin_query") or inquiry.get("instrument_query") or {}
    source = sq.get("source") or sq.get("plugin") or sq.get("skill") or "uniprot" if isinstance(sq, dict) else ""
    line = record_step(line_id, {"question": inquiry.get("question"), "source": source,
                                 "result": note.get("factual_observation"), "answered": note.get("answers_question"),
                                 "next": note.get("next_question"), "entry_id": note.get("entry_id")})
    if not line:
        return ""
    status = str(note.get("line_status") or "").strip()
    m = re.match(r"(answered|dropped)\s*:\s*(.+)", status, re.I | re.S)
    if m:
        ended, why = end(line_id, m.group(1).lower(), m.group(2).strip())
        return ("line %s %s" % (line_id, m.group(1).lower())) if ended else ("line %s kept: %s" % (line_id, why))
    return "line %s: step %d" % (line_id, len(line["steps"]))


def frontier_block(limit_steps=10, with_tests=True):
    """Every open line with its tests, for the frontier review. with_tests=False is for the day's experiment
    planner, which never reads Gemma's journal (Gloria, 2026-09-28): the lines' questions, next steps and last steer,
    not the local loop's results."""
    live = open_lines()
    if not live:
        return ""
    out = []
    for l in live:
        out.append({"line_id": l["id"], "title": l["title"], "question": l["question"], "standing": bool(l.get("standing")),
                    "opened": l.get("opened", "")[:10], "tests": len(l.get("steps") or []),
                    "stalled_tests": int(l.get("stalls") or 0), "next_step": l.get("next_step", ""),
                    **({"recent_tests": [{k: s.get(k, "")[:260] for k in ("at", "source", "question", "result", "answered")}
                                         for s in (l.get("steps") or [])[-limit_steps:]]} if with_tests else {}),
                    "last_steer": (l.get("steer") or [{}])[-1].get("note", "")})
    return ("[HIS OPEN LINES OF INQUIRY — each a question he follows to its end; standing lines are Gloria's]\n"
            + json.dumps(out, ensure_ascii=False))


# ---- his test record -------------------------------------------------------------------------------------------
def _tail(path, nbytes):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); start = max(0, f.tell() - nbytes); f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()[1 if start else 0:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def tests_block(limit=10, budget=1400, notebook=True):
    """What he has run lately, and what came of it: the minute loop's sources and the day's experiments
    (notebook=False: the experiments only, for the frontier planner)."""
    rows = []
    for r in (_tail(NOTEBOOK, 1500 * 1024) if notebook else []):
        k = r.get("kind")
        if k == "additional_source":
            q = r.get("query_sent") or {}
            what = q.get("source") if isinstance(q, dict) else "source"
            target = next((str(q.get(x)) for x in ("accession", "entry_id", "gene", "term", "query", "name")
                           if isinstance(q, dict) and q.get(x)), "")
            rows.append("%s %s %s -> %s record(s)" % (str(r.get("at", ""))[:16], what, target[:60], r.get("records_returned", 0)))
        elif k in ("source_unavailable", "unsourced_id"):
            rows.append("%s %s -> %s" % (str(r.get("at", ""))[:16], k.replace("_", " "),
                                         str(r.get("reason") or r.get("ids") or "")[:80]))
        elif k == "reflection":
            rows.append("%s review: %s -> answered: %s" % (str(r.get("at", ""))[:16],
                                                           str((r.get("inquiry") or {}).get("question", ""))[:90],
                                                           str(r.get("answers_question", ""))[:40]))
    for r in _tail(SESSIONS, 600 * 1024)[-3:]:
        plan = r.get("plan") or {}
        rows.append("%s EXPERIMENT %s %s -> %s, answer %s" % (str(r.get("at", ""))[:16], plan.get("experiment", ""),
                                                              json.dumps(plan.get("parameters") or {})[:60],
                                                              r.get("state"), (r.get("grade") or {}).get("aggregate_accuracy")))
    rows.sort()
    text = "[YOUR RECENT TESTS — what you ran and what came back; do not run one again without a reason]\n" + \
           "\n".join("- " + x for x in rows[-limit:])
    try:
        import lab_phage
        cov = lab_phage.coverage_block(6)
        if cov:
            text += "\n" + cov
    except Exception:
        pass
    return text[:budget] if rows else ""


if __name__ == "__main__":
    print(frontier_block() or "no open lines")
    print()
    print(tests_block())
