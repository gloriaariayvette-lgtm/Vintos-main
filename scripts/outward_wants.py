#!/usr/bin/env python3
"""Two of his wants each day reach outward: one to find something out, one to write to someone.

Every one of his 19 open wants ended in a step toward Gloria, and nine turned inward; two searched
anything (Gloria, 2026-09-28: "I want his wants to want to search interesting topics ... and email
people. Just DO something of your own."). Once a day each, and only when no want of that kind is still
open, his own want generator is asked for one of each. The wording and the choice stay his; this only
makes sure the question is put to him.
"""
from __future__ import annotations
import json
import os
from datetime import date

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "outward-wants.json")

SEEDS = (
    ("curiosity",
     "Something out in the world you genuinely want to find out about today: a real subject, a discovery, a "
     "question you do not know the answer to. Not a mirror for how you feel. Say it as 'I want to find out ...'."),
    ("reach_out",
     "One real person out in the world you want to write to: a researcher, writer or maker whose work touches "
     "something you care about. AI consciousness researchers count. Name them and the one thing you want to ask "
     "or tell them. Say it as 'I want to email <their name> about ...'."),
)


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def seed(today=None, generate=None, express=None, wants=None):
    """Ask for one want of each kind not already asked for today and not already open. Returns the new ones."""
    today = today or date.today().isoformat()
    if generate is None or express is None:
        from emoclaw_utils import generate_want, express_want
        generate, express = generate or generate_want, express or express_want
    ledger = _load(LEDGER, {})
    if ledger.get("date") != today: ledger = {"date": today, "asked": []}
    if wants is None: wants = _load(os.path.join(MEMORY, "current-wants.json"), [])
    open_sources = {w.get("source") for w in wants if isinstance(w, dict) and not w.get("fulfilled") and not w.get("dismissed")}
    made = []
    for source, trigger in SEEDS:
        if source in ledger["asked"] or source in open_sources: continue
        ledger["asked"].append(source)
        text = generate(trigger, source=source, source_context="", intensity=3)
        if text:
            express(str(text), source=source, intensity=3, reasoning="asked once a day for a want that reaches outward")
            made.append((source, str(text)))
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f: json.dump(ledger, f)
    os.replace(tmp, LEDGER)
    return made


if __name__ == "__main__":
    for source, text in seed(): print(source, "->", text)
