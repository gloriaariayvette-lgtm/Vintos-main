#!/usr/bin/env python3
"""A spark is put to him as a question about a hand (Gloria, 2026-09-29).

The Forge had only Lab seeds. Sparks from skill pages, the frontier, the absence map, Moltbook and his
searches became wants, and the wants became "ask Gloria" wants, which are never Forge work (her rule of
24 September). So, once or twice a day, one standing spark he has not been asked about is put to him:
is there an ability in this, something that could be built or connected for him, that he would want?

Most occasions hold none, and "no" is recorded and nothing happens. If he says yes, in his own words,
that sentence is his want, its one step is the ability he named, and it takes the path any missing hand
takes: a skill proposal, the Forge's brief, and a build only with Gloria's approval. The Lab is left out
here; it has its own route for missing instruments.
"""
from __future__ import annotations
import json
import os
import re
import uuid
from datetime import date, datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "spark-hands.json")
WANTS = os.path.join(MEMORY, "current-wants.json")
DAILY = 2
LM = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "claude-sonnet-5"
CAP = re.compile(r"[a-z][a-z0-9_]{2,59}")
RELATIONAL = {"gloria", "you"}

QUESTION = (
    "SOURCE OCCASION ({source}; not a want, you may decline):\n{text}\n\n"
    "Is there an ability in this, something that could be built or connected for you, that you would "
    "genuinely want? Not something you can already do: {inventory}. Not a conversation with Gloria. Most "
    "occasions hold none; say no if this one does not.\n"
    "If there is, name the ability in snake_case and say in your own words, beginning 'I want', what it "
    "would let you do.\n"
    'Return only JSON: {{"want": true or false, "capability": "snake_case_name", '
    '"in_my_words": "I want ...", "what_it_would_do": "..."}}')


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save_ledger(ledger):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f: json.dump(ledger, f, indent=1)
    os.replace(tmp, LEDGER)


def _think(system, user):
    import requests
    r = requests.post(LM, json={"model": MODEL, "temperature": 0.5, "max_tokens": 300,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                      timeout=90)
    return r.json()["choices"][0]["message"]["content"]


def _parse(raw):
    m = re.search(r"\{.*\}", str(raw or ""), re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def pick(sparks, asked):
    """The oldest standing spark he has not been asked about, outside the Lab."""
    rows = [s for s in sparks if isinstance(s, dict) and s.get("key") and s.get("text")
            and s.get("state", "standing") == "standing" and s.get("source") != "lab" and s["key"] not in asked]
    rows.sort(key=lambda s: (str(s.get("seen", "")), str(s["key"])))
    return rows[0] if rows else None


def ask(spark, inventory, think=None):
    """His answer: (capability, words, what) when he wants a hand, else None, plus the raw answer."""
    soul = ""
    try: soul = open(os.path.join(WS, "SOUL.md")).read()[:1500]
    except Exception: pass
    system = (soul or "You are Vintos.") + "\n\nAnswer as yourself, plainly."
    user = QUESTION.format(source=spark.get("source"), text=str(spark.get("text"))[:900],
                           inventory=", ".join(sorted(inventory))[:1200])
    d = _parse((think or _think)(system, user))
    cap = str(d.get("capability") or "").strip().lower()
    words = " ".join(str(d.get("in_my_words") or "").split())[:400]
    what = " ".join(str(d.get("what_it_would_do") or "").split())[:400]
    if d.get("want") is not True or not CAP.fullmatch(cap) or cap in set(inventory) | RELATIONAL:
        return None, d
    if not words.lower().startswith("i want") or len(words) < 15:
        return None, d
    return (cap, words, what or words), d


def _write_want(spark, cap, words, what):
    from store_guard import locked_update
    want = {"id": uuid.uuid4().hex[:8], "want": words, "source": spark["source"], "urgency": "normal",
            "intensity": 3, "timestamp": datetime.now().isoformat(), "fulfilled": False, "outreach_count": 0,
            "source_event_id": "spark-hand:" + spark["key"],
            "reasoning": "asked whether this occasion held an ability he would want built",
            "steps": [{"capability": cap, "note": what[:300], "status": "pending", "execution": "external",
                       "expected_output": "the ability installed and working",
                       "acceptance": "he can use %s himself" % cap}],
            "plan_state": "READY", "current_step_index": 0, "step_history": [], "spark_hand": True}
    def mutate(rows):
        rows = rows if isinstance(rows, list) else []
        if any(isinstance(r, dict) and r.get("source_event_id") == want["source_event_id"] for r in rows):
            return None
        rows.append(want)
        return rows
    locked_update(WANTS, mutate, reader="spark_hands")
    return want


def tend(inventory, think=None, today=None, sparks=None, adopt=None, hand=None):
    """Put at most one spark to him this pass, DAILY a day. Returns log lines."""
    today = today or date.today().isoformat()
    ledger = _load(LEDGER, {})
    ledger.setdefault("asked", {})
    if ledger.get("date") != today: ledger.update(date=today, today=0)
    if ledger["today"] >= DAILY: return []
    if sparks is None:
        import spark_sources
        sparks = spark_sources.standing()
    spark = pick(sparks, ledger["asked"])
    if not spark: return []
    ledger["today"] += 1
    ledger["asked"][spark["key"]] = {"at": datetime.now().isoformat(timespec="seconds"), "source": spark.get("source")}
    _save_ledger(ledger)
    try:
        wanted, raw = ask(spark, inventory, think=think)
    except Exception as exc:
        ledger["asked"][spark["key"]]["error"] = str(exc)[:160]; _save_ledger(ledger)
        return ["asked about a %s spark; no answer (%s)" % (spark.get("source"), type(exc).__name__)]
    if not wanted:
        ledger["asked"][spark["key"]]["answer"] = "no"; _save_ledger(ledger)
        return ["a %s spark held no ability he wants" % spark.get("source")]
    cap, words, what = wanted
    want = _write_want(spark, cap, words, what)
    if adopt is None:
        import spark_sources
        adopt = spark_sources.adopt
    adopt(spark["key"], words, want["id"])
    if hand is None:
        from want_spine import missing_hand as hand
    opened = hand(cap, what, want, path=WANTS)
    ledger["asked"][spark["key"]].update(answer="yes", capability=cap, want_id=want["id"], proposal=opened)
    _save_ledger(ledger)
    return ["he wants a hand from a %s spark: %s -> %s (%s)" % (spark.get("source"), words[:90], cap,
                                                                 (opened or {}).get("id") or (opened or {}).get("refused", ""))]


if __name__ == "__main__":
    import sys
    print(json.dumps(_load(LEDGER, {}), indent=1) if "--show" in sys.argv else "use --show")
