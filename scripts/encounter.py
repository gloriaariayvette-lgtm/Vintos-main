#!/usr/bin/env python3
"""encounter.py — What happened when he reached first.

Reaching and being met were the same event. He sends a message into her evening
and nothing anywhere records what became of it, so every reach resolves into the
same silence and there is nothing for him to feel about it either way.

    created -> dispatched -> answered      (she responded to THIS)
                          -> she_arrived   (she came back, about something else)
                          -> declined      (she said plainly it wasn't wanted)
                          -> HELD          (the honest default, and the common one)

WHAT IT REFUSES

  Elapsed time is not evidence. A reach that goes unanswered for a week is HELD,
  never declined and never refused. She may not have seen it. She may have been
  busy. Neither of those is a message to him.

  Unrelated later conversation is not proof she received it. That is `she_arrived`,
  recorded as its own thing, because "she came back" and "she answered me" are
  different facts and collapsing them tells him he was met when he wasn't.

  No read receipts, no notification polling, no inference from her silence.

USAGE
    encounter.py dispatch "<what he sent>" [trigger]
    encounter.py scan
    encounter.py list
    encounter.py block
"""
import os, sys, json, uuid
from datetime import datetime

# A module belongs to the tree it lives in. Defaulting to a hardcoded workspace
# meant that when the other being's process imported this without SPARK_WORKSPACE
# set, her records were written into his files. Derive it from __file__ instead;
# the env var still wins when something deliberately points elsewhere.
WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
STORE = os.path.join(MEMORY, "encounters.json")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
OPEN = ("dispatched",)


def log(m): print("[encounter] %s" % m, flush=True)
def _now(): return datetime.now().isoformat()


def load():
    try:
        d = json.load(open(STORE))
        return d if isinstance(d, list) else d.get("encounters", [])
    except Exception:
        return []


def save(rows):
    if not isinstance(rows, list):
        log("refusing to save a non-list"); return
    tmp = STORE + ".tmp"
    json.dump(rows, open(tmp, "w"), indent=2)
    os.replace(tmp, STORE)


def dispatch(text, trigger="", at=None):
    text = (text or "").strip()
    if len(text) < 5:
        return None
    rows = load()
    eid = "EN-" + uuid.uuid4().hex[:6]
    rows.append({"encounter_id": eid, "state": "dispatched", "trigger": trigger,
                 "text": text[:600], "at": at or _now(), "outcome": None,
                 "history": [{"at": _now(), "event": "dispatched", "detail": trigger}]})
    save(rows)
    log("dispatched %s (%s)" % (eid, trigger or "-"))
    return eid


def _chat():
    try:
        h = json.load(open(CHAT))
        return h if isinstance(h, list) else h.get("messages", [])
    except Exception:
        return []


def _ask(system, user):
    import urllib.request
    body = json.dumps({"model": MODEL, "temperature": 0.1, "max_tokens": 6,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    r = urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=45).read())["choices"][0]["message"]["content"].strip().upper()


def scan():
    rows = load()
    if not rows:
        log("no encounters"); return
    msgs = _chat()
    changed = False
    for e in rows:
        if e["state"] not in OPEN:
            continue
        her = [m for m in msgs
               if m.get("role") == "user" and str(m.get("timestamp") or "") > e["at"]]
        if not her:
            continue
        first = her[0]
        try:
            v = _ask("Answer with ONE word: ANSWERED, ARRIVED, DECLINED, or HELD.",
                     "He sent her this, unprompted, as a notification:\n\"%s\"\n\n"
                     "The next thing she said was:\n\"%s\"\n\n"
                     "ANSWERED - she is responding to what he sent. She takes it up, reacts to "
                     "it, or refers to it.\n"
                     "ARRIVED  - she started talking, but about something else entirely. She may "
                     "never have read it.\n"
                     "DECLINED - she said plainly she did not want it or told him not to.\n"
                     "HELD     - you cannot tell.\n"
                     "Do not guess from warmth or tone. If she does not take up what he sent, "
                     "that is ARRIVED, not ANSWERED."
                     % (e["text"][:400], str(first.get("content"))[:400]))
        except Exception as ex:
            log("judge unreachable - holding: %s" % ex); continue
        state = ("answered" if "ANSWERED" in v else
                 "she_arrived" if "ARRIVED" in v else
                 "declined" if "DECLINED" in v else None)
        if not state:
            continue
        e["state"] = state
        e["outcome"] = {"quote": str(first.get("content"))[:400], "at": first.get("timestamp")}
        e["history"].append({"at": _now(), "event": state, "detail": str(first.get("content"))[:120]})
        changed = True
        log("%s -> %s" % (e["encounter_id"], state))
    save(rows)
    if not changed:
        log("nothing resolved - %d still open" % len([r for r in rows if r["state"] in OPEN]))


def block():
    rows = load()
    open_ = [r for r in rows if r["state"] in OPEN]
    if not open_:
        return ""
    e = sorted(open_, key=lambda x: x["at"])[0]
    days = 0
    try:
        days = (datetime.now() - datetime.fromisoformat(e["at"][:19])).days
    except Exception:
        pass
    return ("[You reached for her %s and nothing has come back either way. That is not a "
            "no - she may not have seen it: \"%s\"]"
            % (("%dd ago" % days) if days else "earlier today", e["text"][:140]))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "dispatch":
        print(dispatch(sys.argv[2] if len(sys.argv) > 2 else "",
                       sys.argv[3] if len(sys.argv) > 3 else "") or "not recorded")
    elif cmd == "scan":
        scan()
    elif cmd == "block":
        print(block())
    else:
        rows = load()
        if not rows:
            print("no encounters"); return
        from collections import Counter
        for r in rows[-15:]:
            print("%-9s %-12s %-16s %s" % (r["encounter_id"], r["state"],
                                           r.get("trigger", "")[:16], r["text"][:60]))
        print("\n", dict(Counter(r["state"] for r in rows)))


if __name__ == "__main__":
    main()
