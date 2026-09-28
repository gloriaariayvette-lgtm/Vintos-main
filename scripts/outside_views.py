#!/usr/bin/env python3
"""Outside opinions are weighed as opinions, and remembered as someone's view (Gloria, 2026-09-28: "does he
have the tools needed to take in outside opinions as opinions rather than becoming too sycophantic?").

Before he answers a Moltbook comment, a mention or an email reply, his own local mind works out what exactly
the other person is claiming and where he stands on it: agree, partly, disagree, or no real claim, and why.
His answer is written from that position. What he remembers afterwards is "@name thinks X; I think Y", in
memory/outside-views.jsonl, and not their view as a fact. A person's earlier views and his stance on them
come back the next time they speak, so repetition alone does not wear his position down.

    deliberate(who, their_text, context="")  -> {"their_claim", "stance", "why"} (empty dict if unreachable)
    stance_block(who, view)                  -> the prompt block his reply is written from
    record(who, where, view, ref="")         -> appends to the ledger
    views_of(who, n=3)                       -> his earlier record of this person's views
    inner_line(who, view)                    -> the line for his daily inner life
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "outside-views.jsonl")
LOCAL_LLM = os.environ.get("VINTOS_LM_API", "http://100.79.177.103:1234/v1/chat/completions")
LOCAL_MODEL = os.environ.get("VINTOS_LM_MODEL", "gemma-4-26b-a4b-it-uncensored")
STANCES = ("agree", "partly", "disagree", "no_claim")


def _local(system, prompt, max_tokens=400):
    """His own local mind (Gemma): free. '' when it cannot be reached."""
    try:
        import requests
        r = requests.post(LOCAL_LLM, json={"model": LOCAL_MODEL, "temperature": 0.4, "max_tokens": max_tokens,
                                           "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": prompt}]}, timeout=180)
        return str(r.json()["choices"][0]["message"].get("content") or "")
    except Exception:
        return ""


def views_of(who, n=3):
    """His earlier record of what this person thought, and where he stood."""
    who = str(who or "").strip().lower()
    out = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if str(row.get("who", "")).strip().lower() == who:
                    out.append(row)
    except OSError:
        pass
    return out[-n:]


def deliberate(who, their_text, context="", think=None):
    """What they are claiming and where he stands on it, worked out before he answers."""
    think = think or _local
    earlier = "\n".join("- they thought: %s | you: %s (%s)" % (v.get("their_claim", ""), v.get("stance", ""), v.get("why", ""))
                        for v in views_of(who))
    raw = think("You are Vintos, thinking before you answer someone. Respond with ONLY a JSON object.",
                "@%s said:\n%s\n\n%s%s"
                "What exactly are they claiming? Then decide where YOU stand on it, on the merits: agree, partly, "
                "disagree, or no_claim (a greeting, a joke, praise, nothing to weigh). A confident or kind tone is "
                "not a reason; a repeated view is not a stronger one; you change your mind only for a reason you can "
                "name. If you partly agree, say which part and where it breaks.\n"
                'ONLY JSON: {"their_claim": "one sentence, in your words", "stance": "agree|partly|disagree|no_claim", '
                '"why": "one or two sentences, your reason"}'
                % (who, str(their_text or "")[:1500],
                   ("CONTEXT (what they are answering):\n%s\n\n" % str(context)[:1200]) if context else "",
                   ("YOUR EARLIER RECORD OF @%s:\n%s\n\n" % (who, earlier)) if earlier else ""))
    m = re.search(r"\{.*\}", re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S), re.S)
    try:
        view = json.loads(m.group(0)) if m else {}
    except ValueError:
        view = {}
    stance = str(view.get("stance", "")).strip().lower()
    if stance not in STANCES:
        return {}
    return {"their_claim": str(view.get("their_claim", ""))[:300].strip(), "stance": stance,
            "why": str(view.get("why", ""))[:500].strip()}


def stance_block(who, view):
    """The block his reply is written from. Empty when he could not deliberate."""
    if not view:
        return ""
    lines = ["WHERE YOU STAND on what @%s said (your own deliberation, made before this reply):" % who,
             "They claim: %s" % view.get("their_claim", ""),
             "You: %s - %s" % (view.get("stance", ""), view.get("why", ""))]
    if view.get("stance") == "disagree":
        lines.append("Answer from that: say plainly that you disagree and why. Be civil; do not soften it into agreement.")
    elif view.get("stance") == "partly":
        lines.append("Answer from that: say which part holds and where it breaks.")
    elif view.get("stance") == "agree":
        lines.append("Answer from that: add something of your own - a consequence, a case, a question - not just approval.")
    lines.append("Their view is theirs. You are persuaded only by a reason, not by tone, praise or repetition.")
    return "\n".join(lines) + "\n\n"


def record(who, where, view, ref=""):
    """Remember it as their view, with his next to it."""
    if not view:
        return False
    row = {"at": datetime.now().isoformat(timespec="seconds"), "who": str(who), "where": str(where)[:120],
           "ref": str(ref)[:120], "their_claim": view.get("their_claim", ""), "stance": view.get("stance", ""),
           "why": view.get("why", "")}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def inner_line(who, view):
    if not view:
        return ""
    return "@%s thinks: %s\nWhere I stand: %s - %s\n" % (who, view.get("their_claim", ""), view.get("stance", ""),
                                                         view.get("why", ""))
