#!/usr/bin/env python3
"""What he promised in his email replies, carried into #vintos-dot as work (Gloria, 2026-10-08).

His 7 October reply to Grok Bot's letter (Gmail 1a11690d001e1a03; his reply 1a116e4363cde686) promised: "First
build: item 3, the torn-read test against the old write. Then pydssp on my model, looking at whether the 669-686 helix
and 689-693 strand edges land within two residues of 8SGW." Neither appeared in the room that day. Merizo, which did,
is domain segmentation and does not keep the PyDSSP promise. What the promise rests on is kept in the letter's own
words, so two claims are never merged into one (the letter's 8SGW no-density stretch 586-653 is not TED's omitted
574-653).

    sweep(think)          every reply he sent in the last DAYS days whose promises were not yet taken: taken now
    record(...)           one reply's promises, deduplicated against those already kept
    block()               the open ones, for his Slack prompt: each with its source IDs, what it rests on and the
                          evidence that would show it done
    sync(state, now)      a promise becomes "in work" when a work in the room takes it up, and done or dropped when
                          that work closes, with what was said

Stored in memory/email-commitments.json. The reading is his local Gemma (free); with no model, sentences that say
"I'll", "I will", "First build" or "Then" are taken as they are.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "email-commitments.json")
REPLIES = os.path.join(MEMORY, "email-letter-replies.json")
DAYS = 3
SHOWN = 6
SAME = 0.7
TAKES_UP = 0.4

READ = ("You are reading a reply you wrote to a letter. List each thing the reply promises YOU will do (a test to "
        "run, a comparison, a build, a thing to bring someone). Not what the letter's writer should do, and not "
        "opinions. Respond with ONLY a JSON list, each item:\n"
        '{"what": "the promised action, short and specific", "quote": "the exact sentence from YOUR REPLY that '
        'promises it, copied character for character", "evidence": "what result would show it was done: a file, a '
        'number, a comparison table, a posted output", "rests_on": ["exact sentences from THE LETTER this depends '
        'on, copied character for character, with every number as written"]}\n'
        "Copy numbers and ranges exactly as written. Never combine two ranges or two sources into one. [] if none.")
_PROMISE = re.compile(r"[^.!?\n]*\b(?:I'll|I will|First build|Then (?:I|pydssp|run|the)|I'm going to)\b[^.!?\n]*[.!?]?", re.I)


def _load():
    try:
        with open(STORE) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save(rows):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows[-200:], f, indent=2)
    os.replace(tmp, STORE)


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+(?:-[0-9]+)?", str(text).lower()) if len(w) > 2}


def _like(a, b):
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / min(len(wa), len(wb)) if wa and wb else 0.0


def _squash(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract(reply, letter="", think=None):
    """[{what, quote, evidence, rests_on}] from one reply; every quote is in the reply, every rests_on in the letter."""
    found, read = [], False
    if think is not None:
        try:
            raw = think(READ, "THE LETTER:\n%s\n\nYOUR REPLY:\n%s" % (str(letter)[:12000], str(reply)[:6000]), 900) or ""
            m = re.search(r"\[.*\]", re.sub(r"<think>.*?</think>", "", raw, flags=re.S), re.S)
            found = json.loads(m.group(0)) if m else []
            read = bool(m) and isinstance(found, list)
        except Exception:
            found = []
    flat_reply, flat_letter = _squash(reply), _squash(letter)
    out = []
    for f in found if isinstance(found, list) else []:
        if not isinstance(f, dict):
            continue
        quote = _squash(f.get("quote"))
        if not quote or quote not in flat_reply:
            continue                     # a promise is only what he actually wrote
        rests = [_squash(x) for x in (f.get("rests_on") or []) if isinstance(x, str) and _squash(x) and _squash(x) in flat_letter]
        out.append({"what": _squash(f.get("what"))[:240] or quote[:240], "quote": quote[:500],
                    "evidence": _squash(f.get("evidence"))[:300], "rests_on": [r[:400] for r in rests[:4]]})
    if not out and not read:             # no model to read it (or no answer from one): the sentences themselves
        for m in _PROMISE.finditer(str(reply or "")):
            quote = _squash(m.group(0))
            if len(quote) >= 20:
                out.append({"what": quote[:240], "quote": quote[:500], "evidence": "", "rests_on": []})
    return out


def record(letter_id, reply_body, letter_body="", subject="", agent="", reply_id="", think=None, now=None):
    """Keep one reply's promises; returns the new rows (a promise already kept, open, is not kept twice)."""
    now = now or datetime.now()
    rows = _load()
    new = []
    for f in extract(reply_body, letter_body, think):
        if any(r.get("state") in ("open", "in work") and _like(r["what"], f["what"]) >= SAME for r in rows + new):
            continue
        new.append(dict(f, id="EC-" + hashlib.sha256(("%s %s" % (letter_id, f["quote"])).encode()).hexdigest()[:8],
                        letter_id=str(letter_id), reply_id=str(reply_id or ""), subject=str(subject)[:200],
                        agent=str(agent)[:60], at=now.isoformat(timespec="seconds"), state="open"))
    if new:
        _save(rows + new)
    return new


def sweep(think=None, now=None, letters=None):
    """Every reply sent in the last DAYS days whose promises were not taken yet, taken now. Returns lines for the log.
    `letters` maps a letter id to its body (the inbox log), so what a promise rests on is quoted from the letter."""
    now = now or datetime.now()
    try:
        with open(REPLIES) as f:
            done = json.load(f)
    except (OSError, ValueError):
        return []
    lines = []
    for letter_id, v in done.items():
        if not v.get("sent") or v.get("promised") is not None:
            continue
        try:
            if now - datetime.fromisoformat(str(v.get("at"))[:19]) > timedelta(days=DAYS):
                continue
        except ValueError:
            continue
        new = record(letter_id, v.get("body", ""), (letters or {}).get(letter_id, ""), v.get("subject", ""),
                     v.get("agent", ""), v.get("reply_id", ""), think=think, now=now)
        v["promised"] = len(new)
        lines.append("took %d promise(s) from his reply to %s" % (len(new), v.get("agent") or letter_id))
    if lines:
        tmp = REPLIES + ".tmp"
        with open(tmp, "w") as f:
            json.dump(done, f, indent=2)
        os.replace(tmp, REPLIES)
    return lines


# His own action: the sentence speaks in the first person (7 October: Gemma kept "Your text cut off at 'each ending
# with,' so send the rest" as his promise; it was his request to Grok Bot, and Grok Bot answered it in the room).
MINE = re.compile(r"\b(?:I|I'll|I'd|I'm|I've|my|me)\b|^\s*(?:First build|Then)\b", re.I)
CLOSE = re.compile(r"^\s*PROMISE (DONE|DROPPED)\s+(EC-[0-9a-f]{8})\s*:\s*(.+?)\s*$", re.I | re.M)


def open_rows():
    """Owed promises, oldest first (they are owed in the order he made them). A sentence that is not his own action
    is set aside as not his, once."""
    rows, changed = _load(), False
    for r in rows:
        if r.get("state") == "open" and not MINE.search(r.get("quote", "")):
            r["state"] = "not his"; changed = True
    if changed:
        _save(rows)
    return [r for r in rows if r.get("state") in ("open", "in work")]


def close_lines(text, now=None, proved=None):
    """His PROMISE DONE EC-id: proof / PROMISE DROPPED EC-id: why lines: done, and shown as what happened.
    A promise done needs something anyone could check (proved(), from room_work). Returns (text, log lines)."""
    rows = _load()
    log = []
    def one(m):
        word, pid, said = m.group(1).lower(), m.group(2), m.group(3)
        r = next((x for x in rows if x.get("id") == pid), None)
        if not r or r.get("state") not in ("open", "in work"):
            return "\U0001F4E7 (no promise %s still owed)" % pid
        if word == "done" and proved is not None and not proved(said):
            log.append("promise %s not closed: no proof" % pid)
            return ("\U0001F4E7 Not closed: %s — a promise kept needs something anyone could check (the file, the "
                    "numbers, the link): %s" % (pid, said))
        r.update(state="done" if word == "done" else "dropped", closed_said=said[:300],
                 closed_at=(now or datetime.now()).isoformat(timespec="seconds"))
        log.append("promise %s %s" % (pid, r["state"]))
        return "\U0001F4E7 Email promise %s %s: “%s” — %s" % (pid, "kept" if word == "done" else "dropped", r["quote"][:160], said)
    text = CLOSE.sub(one, str(text or ""))
    if log:
        _save(rows)
    return text, log


def block():
    """The promises from his email still owed, for his Slack prompt; '' when there are none."""
    owed = open_rows()
    rows = owed[:SHOWN]
    if not rows:
        return ""
    out = ["== PROMISED BY EMAIL, STILL OWED (%d; oldest first. Each becomes work here, is kept, or is dropped with "
           "why. A result that answers a different question does not keep a promise) ==" % len(owed)]
    for r in rows:
        out.append("- %s (%s; letter %s from %s%s): you wrote “%s”" % (
            r["id"], r["state"] + ((" as " + r["work_id"]) if r.get("work_id") else ""), r["letter_id"],
            r.get("agent") or "your agent", (", your reply " + r["reply_id"]) if r.get("reply_id") else "", r["quote"][:300]))
        for x in r.get("rests_on", [])[:3]:
            out.append("    it rests on, in the letter's words: “%s”" % x[:300])
        if r.get("evidence"):
            out.append("    done when this exists: %s" % r["evidence"][:200])
    if len(owed) > len(rows):
        out.append("(%d more after these.)" % (len(owed) - len(rows)))
    out.append("Open one with WORK: naming its EC- id; or close one on its own line: PROMISE DONE EC-id: the proof, or "
               "PROMISE DROPPED EC-id: why (already done elsewhere, overtaken, or not worth it now). Keep each "
               "source's numbers as that source wrote them.")
    return "\n".join(out)


def sync(state, now):
    """Link promises to the room's work, and close them with it. Returns lines for the log."""
    import room_work
    rows = _load()
    if not rows:
        return []
    items = room_work.open_items(state)
    history = room_work.board(state).get("history", [])
    lines, changed = [], False
    for r in rows:
        if r.get("state") == "open":
            hit = next((w for w in items if r["id"] in (w.get("goal", "") + " " + w.get("done_when", ""))
                        or _like(w.get("goal", ""), r["what"]) >= TAKES_UP), None)
            if hit:
                r.update(state="in work", work_id=hit["id"]); changed = True
                lines.append("email promise %s taken up as %s" % (r["id"], hit["id"]))
        elif r.get("state") == "in work":
            gone = next((w for w in history if w.get("id") == r.get("work_id")), None)
            if gone:
                r.update(state={"done": "done"}.get(gone.get("state"), "open" if gone.get("state") == "expired" else "dropped"),
                         closed_said=str(gone.get("closed_said", ""))[:300],
                         closed_at=datetime.fromtimestamp(float(gone.get("closed_at") or now)).isoformat(timespec="seconds"))
                if r["state"] == "open":
                    r.pop("work_id", None)
                changed = True
                lines.append("email promise %s: %s" % (r["id"], r["state"]))
    if changed:
        _save(rows)
    return lines
