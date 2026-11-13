#!/usr/bin/env python3
"""His own ambitions, finished or revised by him, with every earlier wording kept.

12 November: his journal said a sentence in his ambitions had stopped mid-word since 8 November, and he tried to
finish it with creative_write, which writes fiction into creative-writing/. The stored text was whole; the journal
pass showed him the first 600 *bytes* of the ambitions log (idle-journal.sh, `head -c 600`), which cut the sentence
inside a curly apostrophe. This module is the one door that changes an ambition's wording:

- revise():  one field of one ACTIVE ambition in ambitions.json gets his new wording; the old wording goes into the
             goal's own `history`. Nothing else in the file, and no other file, is written. Prose is never stored
             mid-sentence: it is trimmed back to its last sentence end (and flagged), or refused.
- seal_cut(): the ambition review's guard for a model reply that ran out of tokens mid-field.
- excerpt():  a bounded view that ends at a sentence or line end and says it continues, never inside a word.
"""
import json
import os
import re
import sys
from datetime import datetime

FIELDS = ("goal", "why", "progress", "next_step")
PROSE = ("why", "progress", "next_step")
MAX_TEXT = 1500
_CLOSE = "\"'”’)]*_"
_END = re.compile(r"[.!?…][%s]*\s*$" % re.escape(_CLOSE))
_INNER_END = re.compile(r"[.!?…][%s]*(?=\s)" % re.escape(_CLOSE))


def path():
    return os.path.join(os.path.expanduser("~/.vintos/workspace"), "memory", "ambitions.json")


def ends_sentence(text):
    return bool(_END.search(str(text or "").strip()))


def trim_to_sentence(text):
    """(text, trimmed). Cut back to the last sentence end; unchanged when it already ends one or has none."""
    s = str(text or "").strip()
    if not s or ends_sentence(s):
        return s, False
    ends = [m.end() for m in _INNER_END.finditer(s)]
    if not ends:
        return s, False
    return s[:ends[-1]].rstrip(), True


def excerpt(text, limit):
    """At most `limit` characters, ending at a sentence or line end (else a word end) with a marker that more
    follows. Characters, not bytes: a byte cut can split a character and a word."""
    s = str(text or "")
    if len(s) <= limit:
        return s
    marker = " [...continues]"
    room = max(0, limit - len(marker))
    head = s[:room]
    cut = max([m.end() for m in _INNER_END.finditer(head + " ")] + [head.rfind("\n")])
    if cut < room // 3:
        cut = head.rfind(" ")
    if cut <= 0:
        cut = room
    return head[:cut].rstrip() + marker


def is_active(goal):
    return str((goal or {}).get("progress", "")).strip().lower() != "completed"


def find_goal(goals, ref):
    """Index of the active goal `ref` names: its 1-based number among the active goals, or words from its goal
    text. None when nothing or more than one goal matches."""
    active = [i for i, g in enumerate(goals) if isinstance(g, dict) and is_active(g)]
    r = str(ref if ref is not None else "").strip()
    if r.isdigit():
        n = int(r)
        return active[n - 1] if 1 <= n <= len(active) else None
    low = re.sub(r"\s+", " ", r.lower()).strip(" .\"'")
    if len(low) < 4:
        return None
    hits = [i for i in active if low in re.sub(r"\s+", " ", str(goals[i].get("goal", "")).lower())]
    return hits[0] if len(hits) == 1 else None


def incomplete_fields(goal):
    """Prose fields recorded as cut, or flagged incomplete by the review."""
    flagged = goal.get("incomplete") or []
    return [f for f in PROSE if f in flagged and goal.get(f) and not ends_sentence(goal.get(f))]


def revise(ref, field, text, by="him", reason="", store=None, now=None):
    """Write his new wording into one field of one of his active ambitions. Returns a result dict with 'ok'."""
    store = store or path()
    now = now or datetime.now().isoformat()
    field = str(field or "").strip().lower().replace(" ", "_")
    if field == "next":
        field = "next_step"
    if field not in FIELDS:
        return {"ok": False, "why": "field must be one of %s" % ", ".join(FIELDS)}
    new = re.sub(r"[ \t]+", " ", str(text or "")).strip()
    if not new:
        return {"ok": False, "why": "no text"}
    if len(new) > MAX_TEXT:
        return {"ok": False, "why": "text longer than %d characters" % MAX_TEXT}
    trimmed = False
    if field in PROSE and not ends_sentence(new):
        new, trimmed = trim_to_sentence(new)
        if not trimmed:
            return {"ok": False, "why": "the text stops mid-sentence and has no complete sentence to keep"}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from store_guard import transaction, save_json
    with transaction(store):
        try:
            with open(store) as f:
                data = json.load(f)
        except FileNotFoundError:
            return {"ok": False, "why": "no ambitions yet"}
        if not isinstance(data, dict) or not isinstance(data.get("goals"), list):
            return {"ok": False, "why": "ambitions store is not {goals: [...]}"}
        i = find_goal(data["goals"], ref)
        if i is None:
            return {"ok": False, "why": "no single active ambition matches %r" % str(ref)[:60]}
        g = data["goals"][i]
        before = g.get(field)
        if before == new:
            return {"ok": True, "index": i, "field": field, "unchanged": True}
        g.setdefault("history", []).append({"at": now, "field": field, "before": before, "by": by,
                                            **({"reason": str(reason)[:300]} if reason else {})})
        g[field] = new
        g["revised_at"] = now
        left = [f for f in (g.get("incomplete") or []) if f != field]
        if left:
            g["incomplete"] = left
        else:
            g.pop("incomplete", None)
        if trimmed:
            g.setdefault("trimmed_at_sentence", []).append({"at": now, "field": field})
        save_json(store, data)
    return {"ok": True, "index": i, "field": field, "trimmed": trimmed, "history": len(g["history"])}


def seal_cut(goals, cut, now=None):
    """The review's reply ran out of tokens (`cut`): the last prose field of the last goal is trimmed back to a
    sentence end, or, when it has none, kept and flagged `incomplete` so the next review or his revise_ambition
    finishes it. Returns the fields it touched as (goal index, field, 'trimmed'|'flagged')."""
    out = []
    if not cut or not goals:
        return out
    now = now or datetime.now().isoformat()
    g = goals[-1]
    last = next((f for f in reversed(g.get("_order", [])) if f in PROSE), None) or \
        next((f for f in ("next_step", "progress", "why") if g.get(f)), None)
    if not last or not g.get(last) or ends_sentence(g[last]):
        return out
    text, trimmed = trim_to_sentence(g[last])
    if trimmed:
        g[last] = text
        g.setdefault("trimmed_at_sentence", []).append({"at": now, "field": last})
        out.append((len(goals) - 1, last, "trimmed"))
    else:
        g["incomplete"] = sorted(set(g.get("incomplete") or []) | {last})
        out.append((len(goals) - 1, last, "flagged"))
    return out


if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "excerpt":
    # idle-journal.sh: python3 ambition_revise.py excerpt LIMIT FILE
    try:
        with open(sys.argv[3], encoding="utf-8", errors="replace") as f:
            sys.stdout.write(excerpt(f.read(), int(sys.argv[2])))
    except FileNotFoundError:
        pass
