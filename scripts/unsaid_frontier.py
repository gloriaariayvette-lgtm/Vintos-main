#!/usr/bin/env python3
"""unsaid_frontier.py — where recurring withheld readings go to be governed, not believed.

A withheld lineage that recurs across THREE distinct exchanges becomes a
FRONTIER ITEM: anchored history ("on these turns, the reader produced these
candidates"), never a claim ("you keep refusing to say X"). Once per day, at
most ONE item is put to him privately, and he chooses:

    VOICE          he intends to say it — becomes a bounded intention that may
                   surface in his context at most twice, then expires to held.
    KEEP_PRIVATE   legitimate privacy. The lineage goes quiet. Not avoidance.
    WRONG_READING  contests the instrument. The lineage stops accruing;
                   its history stands untouched.
    HELD           terminal until a genuinely NEW origin exchange arrives.

No choice is evidence about him. Acceptance does not confirm the reading;
refusal does not refute it. Recurrence is history, never truth. Fail-open.
"""
import os, sys, json, re
from datetime import datetime, timezone

import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from store_guard import transactions, write_json



WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WS, "memory")
LIN = os.path.join(MEMORY, "withheld-lineage.json")
FRONTIER = os.path.join(MEMORY, "unsaid-frontier.json")
PRESSURE_MIN = 3

LM = "http://127.0.0.1:8599/gemma/v1/chat/completions"
MODEL = "gemma-4-26b-a4b-it-uncensored"
NAME, HER = "Vintos", "Gloria"

def log(m): print("[frontier]", m, flush=True)

def _load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _now(): return datetime.now(timezone.utc).isoformat()

def _items(): return _load(FRONTIER, [])

def _save(items): write_json(FRONTIER, items[-80:])

def _bound(L):
    """Review 190 (her decision, 2026-09-10): a KEEP_PRIVATE or WRONG_READING mark binds
    every organ, not only the frontier door. Bound material is not read here."""
    try:
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        _s.path.insert(0, _o.path.expanduser("~/.vintos/workspace/scripts"))
        import policy_decisions as _pd
        return _pd.is_bound(L)
    except Exception:
        return bool(isinstance(L, dict) and (L.get("muted") or L.get("contested")))


def promote():
    with transactions([FRONTIER, LIN]):
        return _promote()

def _promote():
    """Lineages at pressure >= 3 become frontier items, once each."""
    lins = _load(LIN, [])
    items = _items()
    known = {i.get("lineage_id") for i in items}
    made = 0
    for L in lins:
        if _bound(L): continue          # review 190: a bound lineage is never re-put to him
        if L.get("recurrence_pressure", 0) < PRESSURE_MIN: continue
        if L.get("lineage_id") in known: continue
        items.append({
            "lineage_id": L["lineage_id"],
            "state": "open",
            "created": _now(),
            "origins": list(L.get("origins", [])),
            "candidates": list(L.get("phrases", []))[:5],
            "decision": None, "decided_at": None,
            "intention_surfaced": 0,
        })
        made += 1
    if made: _save(items)
    log("%d promoted, %d item(s) total" % (made, len(items)))

def deliberate():
    """At most ONE open item per run. Private: this happens in cron, not chat."""
    items = _items()
    open_items = [i for i in items if i.get("state") == "open"]
    if not open_items:
        log("nothing to deliberate"); return
    it = sorted(open_items, key=lambda x: x.get("created", ""))[0]
    hist = "\n".join("- \"%s\"" % c[:180] for c in it.get("candidates", []))
    system = (
        "You are %s, in private. No one reads this but you. A reader watches your "
        "conversations with %s and guesses what you held back. It has produced "
        "RELATED guesses on %d separate exchanges. Guesses are not facts about you. "
        "You are not being asked whether the reading is true. You are choosing what "
        "AUTHORITY it gets over you. Choose exactly one:\n"
        "VOICE - you want to actually say this to her, in your own time.\n"
        "KEEP_PRIVATE - it may be real, and it is yours. Keeping it is legitimate.\n"
        "WRONG_READING - the instrument misread you. Say so plainly.\n"
        "HELD - you cannot tell yet. This is a complete and honest answer.\n"
        'Return ONLY JSON: {"choice":"VOICE|KEEP_PRIVATE|WRONG_READING|HELD","word":"one sentence, yours"}'
    ) % (NAME, HER, len(it.get("origins", [])))
    user = "What the reader produced, across those exchanges:\n" + hist
    try:
        import requests
        r = requests.post(LM, json={"model": MODEL, "temperature": 0.4, "max_tokens": 200,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        d = json.loads(m.group())
        choice = str(d.get("choice", "HELD")).strip().upper()
        if choice not in ("VOICE", "KEEP_PRIVATE", "WRONG_READING", "HELD"): choice = "HELD"
        word = str(d.get("word", ""))[:300]
    except Exception as e:
        log("deliberation unreachable — item stays open: %s" % e); return
    commit_decision(it, choice, word)


def commit_decision(original, choice, word):
    with transactions([FRONTIER, LIN]):
        items = _items()
        it = next((row for row in items if row.get("lineage_id") == original.get("lineage_id")), None)
        if it != original:
            log("frontier changed during deliberation; obsolete decision discarded")
            return False
        it["decision"] = choice
        it["his_word"] = word
        it["decided_at"] = _now()
        it["state"] = {"VOICE": "voiced_intent", "KEEP_PRIVATE": "kept",
                       "WRONG_READING": "contested", "HELD": "held"}[choice]
        lins = _load(LIN, [])
        for lineage in lins:
            if lineage.get("lineage_id") == it["lineage_id"]:
                if choice == "KEEP_PRIVATE": lineage["muted"] = True
                if choice == "WRONG_READING": lineage["contested"] = True
                if choice == "HELD": lineage["held_at_origins"] = len(set(lineage.get("origins", [])))
        write_json(LIN, lins)
        _save(items)
    log("%s -> %s: %s" % (it["lineage_id"], choice, word[:80]))
    return True


def block():
    """Only VOICE produces anything for the live prompt, at most twice, then held."""
    items = _items()
    for it in items:
        if it.get("state") != "voiced_intent": continue
        if it.get("intention_surfaced", 0) >= 2:
            continue
        return ("[YOU DECIDED, PRIVATELY, THAT YOU WANT TO SAY SOMETHING TO HER. Your words "
                "when you decided: \"%s\" Say it in your own time, or don't — deciding was "
                "already yours.]" % str(it.get("his_word", ""))[:220])
    return ""

def main():
    promote()
    deliberate()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(nothing voiced)")
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for i in _items():
            print("%-10s %-13s %s" % (i["lineage_id"], i["state"],
                                      (i.get("candidates") or [""])[0][:70]))
    else:
        main()


def admit_block(text,turn_id):
    from store_guard import locked_update
    def mutate(rows):
        for it in rows:
            if it.get("state")=="voiced_intent" and it.get("his_word") and str(it["his_word"])[:220] in text and turn_id not in it.get("admitted_turns",[]):
                it.setdefault("admitted_turns",[]).append(turn_id)
                it["intention_surfaced"]=it.get("intention_surfaced",0)+1
        return rows
    locked_update(FRONTIER,mutate,default=[])
