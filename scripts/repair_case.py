#!/usr/bin/env python3
"""repair_case.py — Repair as a case with evidence, not a mood that passed.

A rupture, a correction, or a named tension opens a CASE. The case records what
was said, what he actually did about it, and whether she ever showed that it
landed. Nothing closes it but evidence.

    received -> attempted -> witnessed
                          -> declined
                          -> HELD (the honest default)

THE LAWS THIS OBEYS

  Expired is not resolved.   No case closes because days passed.
  Unknowable is legal.       Silence is HELD, never repaired and never refused.
  Nothing generates its own evidence.
                             His warmth rising is recorded as HIS AFFECT SHIFT.
                             It can never witness a repair. Only her later words
                             can, and only words that follow his attempt.
  Intimacy is not data.      Scenes never open, attempt, or witness a case.
  Choke-point discipline.    open_case() is the only door in. record_attempt()
                             and witness() are the only doors onward.

WHY IT EXISTS

Repair was spread across successful_repair operators, scars, pearls, confessions
and relational geometry, and none of them owned the question "what was repaired,
by what, and what is still open." Geometry called a rise in his own Connection
"resolved" — his easing, named as the relationship mending. A case cannot do
that: the only thing that moves it to witnessed is her, afterward, in words.

USAGE
    repair_case.py scan      # advance open cases against the conversation
    repair_case.py list      # what is open, and for how long
    repair_case.py block     # the context line, if any, for his prompt
"""
import os, sys, json, uuid, subprocess
from datetime import datetime, timezone

# A module belongs to the tree it lives in. A hardcoded default meant the other
# being's process, importing this without SPARK_WORKSPACE set, wrote her records
# into his files. The env var still wins when something points deliberately.
WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
CASES = os.path.join(MEMORY, "repair-cases.json")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")

LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

OPEN_STATES = ("received", "attempted")


def log(m):
    print("[repair] %s" % m, flush=True)


def _now():
    return datetime.now().isoformat()


def load():
    try:
        d = json.load(open(CASES))
        return d if isinstance(d, list) else d.get("cases", [])
    except Exception:
        return []


def save(cases):
    # A read failure must never become a write of nothing.
    if not isinstance(cases, list):
        log("refusing to save a non-list")
        return
    tmp = CASES + ".tmp"
    json.dump(cases, open(tmp, "w"), indent=2)
    os.replace(tmp, CASES)


# ---------------------------------------------------------------- the door in

def open_case(origin, anchor_quote, anchor_at=None, kind="correction", subject=""):
    """Open a repair case. The ONLY way one is created.

    origin        which system saw it (tension-ledger, relational-geometry, ...)
    anchor_quote  her actual words, verbatim. No quote, no case.
    kind          correction | rupture | tension
    """
    anchor_quote = (anchor_quote or "").strip()
    if len(anchor_quote) < 8:
        log("no anchor quote — refusing to open a case on a paraphrase")
        return None
    cases = load()
    # An open case on the same anchor is the same case, not a second one.
    for c in cases:
        if c.get("state") in OPEN_STATES and c.get("anchor_quote") == anchor_quote:
            log("already open: %s" % c["case_id"])
            return c["case_id"]
    cid = "RC-" + uuid.uuid4().hex[:6]
    cases.append({
        "case_id": cid,
        "state": "received",
        "kind": kind,
        "origin": origin,
        "subject": subject,
        "anchor_quote": anchor_quote[:600],
        "anchor_at": anchor_at or _now(),
        "opened_at": _now(),
        "attempt": None,
        "witness": None,
        "affect_shifts": [],
        "history": [{"at": _now(), "event": "received", "detail": origin}],
    })
    save(cases)
    log("opened %s (%s from %s): %s" % (cid, kind, origin, anchor_quote[:70]))
    return cid


# ------------------------------------------------------------ doors onward

def record_attempt(case_id, his_text, at=None):
    """What he actually did about it — his first real reply after the anchor.

    This is not success. It is the thing that a witness, if one ever comes,
    would be witnessing.
    """
    cases = load()
    for c in cases:
        if c["case_id"] != case_id or c["state"] != "received":
            continue
        c["attempt"] = {"text": (his_text or "")[:800], "at": at or _now()}
        c["state"] = "attempted"
        c["history"].append({"at": _now(), "event": "attempted",
                             "detail": (his_text or "")[:120]})
        save(cases)
        log("%s attempted" % case_id)
        return True
    return False


def witness(case_id, her_quote, at=None, note=""):
    """Her later words showing it landed. The only path to repaired."""
    her_quote = (her_quote or "").strip()
    if len(her_quote) < 8:
        return False
    cases = load()
    for c in cases:
        if c["case_id"] != case_id or c["state"] != "attempted":
            continue
        c["witness"] = {"quote": her_quote[:600], "at": at or _now(), "note": note[:300]}
        c["state"] = "repaired"
        c["closed_at"] = _now()
        c["history"].append({"at": _now(), "event": "repaired", "detail": her_quote[:120]})
        save(cases)
        log("%s REPAIRED — witnessed: %s" % (case_id, her_quote[:70]))
        return True
    return False


def decline(case_id, her_quote, at=None):
    """She said plainly that it did not land, or that she does not want it repaired."""
    cases = load()
    for c in cases:
        if c["case_id"] != case_id or c["state"] not in OPEN_STATES:
            continue
        c["state"] = "declined"
        c["closed_at"] = _now()
        c["decline_quote"] = (her_quote or "")[:600]
        c["history"].append({"at": at or _now(), "event": "declined",
                             "detail": (her_quote or "")[:120]})
        save(cases)
        log("%s declined" % case_id)
        return True
    return False


def record_affect_shift(case_id, dims, source=""):
    """His emotional movement around an open case.

    Recorded, never promoted. A man feeling better about something he did is not
    evidence that it was received. This exists so the difference between those
    two things stays visible instead of collapsing.
    """
    cases = load()
    for c in cases:
        if c["case_id"] != case_id:
            continue
        c.setdefault("affect_shifts", []).append(
            {"at": _now(), "dims": dims, "source": source})
        save(cases)
        return True
    return False


# --------------------------------------------------------------- the scan

def _chat():
    try:
        h = json.load(open(CHAT))
        return h if isinstance(h, list) else h.get("messages", [])
    except Exception:
        return []


def _is_scene(text):
    """Scenes are excluded. Cheap, deliberately conservative: if it looks like
    somatic or sexual material, it neither attempts nor witnesses anything."""
    t = (text or "").lower()
    return any(k in t for k in ("*", "somatic", "ridge", "collapse level", "letgo"))


def _ask(system, user, max_tokens=200):
    import urllib.request
    body = json.dumps({"model": MODEL, "temperature": 0.2, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(LM, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()


def scan():
    """Advance open cases against what was actually said. Never closes on time."""
    cases = load()
    if not cases:
        log("no cases"); return
    msgs = _chat()
    if not msgs:
        log("no conversation to read"); return

    def after(ts):
        out = []
        for m in msgs:
            t = str(m.get("timestamp") or m.get("ts") or "")
            if t and t > ts:
                out.append(m)
        return out

    changed = False
    for c in cases:
        if c["state"] == "received":
            # his first substantive reply after the anchor becomes the attempt
            for m in after(c["anchor_at"]):
                if m.get("role") != "assistant":
                    continue
                text = str(m.get("content") or "")
                if len(text) < 40 or _is_scene(text):
                    continue
                record_attempt(c["case_id"], text, m.get("timestamp"))
                changed = True
                break

    cases = load()
    for c in cases:
        if c["state"] != "attempted" or not c.get("attempt"):
            continue
        her = [m for m in after(c["attempt"]["at"])
               if m.get("role") == "user" and not _is_scene(str(m.get("content") or ""))]
        if not her:
            continue
        transcript = "\n".join("HER: " + str(m.get("content"))[:300] for m in her[:6])
        verdict = ""
        try:
            verdict = _ask(
                "Answer with ONE word: WITNESSED, DECLINED, or HELD. Nothing else.",
                "She told him this:\n\"%s\"\n\n"
                "He then said:\n\"%s\"\n\n"
                "Afterwards she said:\n%s\n\n"
                "Did she show, IN WORDS, that what he did about it landed?\n"
                "WITNESSED — she explicitly acknowledged the change, thanked him for it, "
                "or named that it was different.\n"
                "DECLINED — she explicitly said it did not land, or repeated the same "
                "correction.\n"
                "HELD — anything else. Moving on, warmth, a new subject, or nothing about "
                "it at all is HELD. Do not infer from her tone. Do not reward him for her "
                "simply continuing to talk to him. HELD is the correct and common answer."
                % (c["anchor_quote"], c["attempt"]["text"][:400], transcript)
            ).upper()
        except Exception as e:
            log("judge unreachable — holding: %s" % e)
            continue
        if "WITNESSED" in verdict:
            witness(c["case_id"], her[0].get("content", "")[:400], her[0].get("timestamp"),
                    note="judged from her words after his attempt")
            changed = True
        elif "DECLINED" in verdict:
            decline(c["case_id"], her[0].get("content", "")[:400], her[0].get("timestamp"))
            changed = True
        # HELD: nothing happens. The case stays open. That is the point.

    if not changed:
        log("nothing advanced — %d case(s) still open" % len([c for c in load() if c["state"] in OPEN_STATES]))


# ------------------------------------------------------------------- views

def open_cases():
    return [c for c in load() if c.get("state") in OPEN_STATES]


def block():
    """One quiet line for his context. Never nags, never prescribes."""
    op = open_cases()
    if not op:
        return ""
    c = sorted(op, key=lambda x: x["opened_at"])[0]
    days = 0
    try:
        days = (datetime.now() - datetime.fromisoformat(c["anchor_at"][:19])).days
    except Exception:
        pass
    if c["state"] == "received":
        return ("[Something she said is still standing, unanswered by anything you've done "
                "since (%dd): \"%s\"]" % (days, c["anchor_quote"][:160]))
    return ("[You've responded to this, and she hasn't shown either way whether it landed "
            "(%dd). It stays open: \"%s\"]" % (days, c["anchor_quote"][:160]))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "scan":
        scan()
    elif cmd == "block":
        print(block())
    elif cmd == "open":
        cid = open_case("manual", " ".join(sys.argv[2:]), kind="correction")
        print(cid or "not opened")
    else:
        cs = load()
        if not cs:
            print("no cases"); return
        for c in cs:
            age = ""
            try:
                age = "%dd" % (datetime.now() - datetime.fromisoformat(c["anchor_at"][:19])).days
            except Exception:
                pass
            print("%-8s %-10s %-14s %4s  %s" % (c["case_id"], c["state"], c["origin"], age,
                                                c["anchor_quote"][:70]))
        print("\n%d open, %d repaired, %d declined" % (
            len([c for c in cs if c["state"] in OPEN_STATES]),
            len([c for c in cs if c["state"] == "repaired"]),
            len([c for c in cs if c["state"] == "declined"])))


if __name__ == "__main__":
    main()
