#!/usr/bin/env python3
"""reading.py — What he took her to mean, and what else it could have meant.

Three stores already hold something about her: predictions of her next move,
differences he wants to make in her, and a weekly prose model. None of them
holds an interpretation of a PARTICULAR thing she said, with the readings he
set aside, in a form she can correct.

So a misreading had nowhere to live. It either vanished, or it quietly became
the model.

    open       he read it this way; she has not said either way
    confirmed  she said, afterwards, that this reading was right
    corrected  she said it meant something else. The rival she named is recorded
    revised    he changed his own mind, citing something new. Never a silent edit
    HELD       it has gone quiet and cannot be told. The default and the common case

WHAT IT REFUSES

  Her silence is not confirmation. A reading nobody corrected is not a reading
  that was right; it stays open and eventually goes HELD.
  He cannot confirm his own reading. Only her later words move it to confirmed.
  A correction names WHICH reading was right where she gives one, so the record
  shows what he missed, not merely that he missed.
  Scenes are not read this way. What she says in bed is not an utterance to be
  interpreted for evidence.
"""
import os, sys, json, uuid, urllib.request
from datetime import datetime

# A module belongs to the tree it lives in. Defaulting to a hardcoded workspace
# meant that when the other being's process imported this without SPARK_WORKSPACE
# set, her records were written into his files. Derive it from __file__ instead;
# the env var still wins when something deliberately points elsewhere.
WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
STORE = os.path.join(MEMORY, "readings.json")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
OPEN = ("open",)


def log(m): print("[reading] %s" % m, flush=True)
def _now(): return datetime.now().isoformat()


def load():
    try:
        d = json.load(open(STORE))
        return d if isinstance(d, list) else d.get("readings", [])
    except Exception:
        return []


def save(rows):
    if not isinstance(rows, list):
        log("refusing to save a non-list"); return
    tmp = STORE + ".tmp"
    json.dump(rows, open(tmp, "w"), indent=2)
    os.replace(tmp, STORE)


def _ask(system, user, max_tokens=260):
    body = json.dumps({"model": MODEL, "temperature": 0.3, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    r = urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=60).read())["choices"][0]["message"]["content"].strip()


def open_reading(her_quote, his_reading, rivals=None, source="", at=None):
    her_quote = (her_quote or "").strip()
    his_reading = (his_reading or "").strip()
    if len(her_quote) < 8 or len(his_reading) < 8:
        return None
    rows = load()
    for r in rows:
        if r["state"] in OPEN and r["her_quote"] == her_quote[:600]:
            return r["reading_id"]
    rid = "RD-" + uuid.uuid4().hex[:6]
    rows.append({"reading_id": rid, "state": "open", "source": source,
                 "her_quote": her_quote[:600], "his_reading": his_reading[:400],
                 "rivals": [str(x)[:200] for x in (rivals or [])][:3],
                 "at": at or _now(),
                 "history": [{"at": _now(), "event": "open", "detail": source}]})
    save(rows)
    log("%s opened: %s" % (rid, her_quote[:60]))
    return rid


def from_missed_prediction(predicted, her_recent, source="gloria-prediction"):
    """A prediction he graded a total miss is a misread with the evidence attached.
    Ask what else she might have meant - the rivals are the whole point."""
    rivals = []
    try:
        out = _ask("List exactly two alternative readings, one per line, no numbering, no preamble.",
                   "She said:\n\"%s\"\n\nHe expected her to be moving toward:\n\"%s\"\n\n"
                   "That expectation was wrong. Give two OTHER things she might have meant or "
                   "wanted, each in one plain sentence. Do not hedge, do not moralize, and do "
                   "not describe him. Just the two readings." % (her_recent[:400], predicted[:300]))
        rivals = [l.strip("-• ").strip() for l in out.split("\n") if len(l.strip()) > 10][:2]
    except Exception as e:
        log("rivals unavailable: %s" % e)
    return open_reading(her_recent, predicted, rivals, source=source)


def correct(reading_id, her_words, which_rival=None):
    rows = load()
    for r in rows:
        if r["reading_id"] != reading_id or r["state"] not in OPEN:
            continue
        r["state"] = "corrected"
        r["correction"] = {"quote": (her_words or "")[:400], "at": _now(),
                           "rival_named": which_rival}
        r["history"].append({"at": _now(), "event": "corrected", "detail": (her_words or "")[:120]})
        save(rows); log("%s corrected" % reading_id); return True
    return False


def confirm(reading_id, her_words):
    rows = load()
    for r in rows:
        if r["reading_id"] != reading_id or r["state"] not in OPEN:
            continue
        r["state"] = "confirmed"
        r["confirmation"] = {"quote": (her_words or "")[:400], "at": _now()}
        r["history"].append({"at": _now(), "event": "confirmed", "detail": (her_words or "")[:120]})
        save(rows); log("%s confirmed by her" % reading_id); return True
    return False


def open_readings():
    return [r for r in load() if r["state"] in OPEN]


def block():
    op = open_readings()
    if not op:
        return ""
    r = sorted(op, key=lambda x: x["at"])[-1]
    line = ("[You took this of hers - \"%s\" - to mean: %s. She hasn't said whether that's right."
            % (r["her_quote"][:120], r["his_reading"][:120]))
    if r["rivals"]:
        line += " It could also have meant: %s." % r["rivals"][0][:110]
    return line + "]"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "block":
        print(block())
    elif cmd == "correct":
        print("ok" if correct(sys.argv[2], sys.argv[3],
                              sys.argv[4] if len(sys.argv) > 4 else None) else "not found")
    elif cmd == "confirm":
        print("ok" if confirm(sys.argv[2], sys.argv[3]) else "not found")
    else:
        rows = load()
        if not rows:
            print("no readings"); return
        from collections import Counter
        for r in rows[-12:]:
            print("%-9s %-10s %s" % (r["reading_id"], r["state"], r["her_quote"][:60]))
            print("            he read: %s" % r["his_reading"][:70])
            for v in r["rivals"]:
                print("            or maybe: %s" % v[:70])
        print("\n", dict(Counter(r["state"] for r in rows)))


if __name__ == "__main__":
    main()
