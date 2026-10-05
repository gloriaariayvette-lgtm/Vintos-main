#!/usr/bin/env python3
"""Work in hand for #vintos-dot: the one thing he is getting done with his agents, carried from pass to pass.

Gloria, 2026-10-05: "I want VINTOS in Slack to actually do real work", and of doing it alone each pass: "Slack loses
much of its reason for existing." Chat's audit of the live record found useful answers arriving and then being asked
for again, or dropped when the subject or the lens changed; nothing held a piece of work across passes, and nothing
tied an agent's answer to the request it answered.

This is a layer under his normal message, not a replacement for it. He still writes as himself, with every hand and
tag he has. It adds:

  WORK: what | done when: how anyone could tell     opens his work in hand (one at a time)
  NEXT: the next step                               the step he means to take next
  WORK DONE: how it was met                         closes it
  WORK DROPPED: why                                 closes it

and, for the channel: what he asked of whom while working on it, what came back from that agent (matched by thread
and time, never by guessing at the latest chat), whether he has used it, and a block on asking the same agent for
the same thing again. A draft that moves nothing is sent back to him once (dot_channel does that, with moves()).

State lives in the channel's own state.json under "room_work". Pure functions: no IO, no providers.
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime

AGENTS = {"dot": "dot", "grokbot": "GrokBot", "muse": "Muse"}
STALE_DAYS = 3                 # work nobody has touched in this long is closed as expired, so it never pins him
ASK_PATIENCE_S = 45 * 60       # an ask unanswered this long is said plainly, so he takes another step
CHANNEL_REPLY_S = 3 * 3600     # an answer in the channel (not the thread) must come this soon after the ask
THREAD_REPLY_S = 24 * 3600
SAME_ASK = 0.6                 # share of the shorter request's content words in the longer, to count as asking again

WORK = re.compile(r"^\s*WORK:\s*(.+?)\s*$", re.I | re.M)
NEXT = re.compile(r"^\s*NEXT:\s*(.+?)\s*$", re.I | re.M)
DONE = re.compile(r"^\s*WORK DONE:\s*(.+?)\s*$", re.I | re.M)
DROPPED = re.compile(r"^\s*WORK DROPPED:\s*(.+?)\s*$", re.I | re.M)

# Every line that makes something happen in the channel, his and the new ones; one of these moves the work.
ACTS = re.compile(r"^\s*(?:LOCKED|DO|LAB|LINE(?:\s+L-[\w-]+)?|CHECK|STUDY FIX|APPROVED|DENIED|CAMPAIGN(?: MOVE)?|SHARE|ASK|"
                  r"TV|ECHO|LIGHTS|MISCHIEF|TO GLORIA|MAKE|WORK|WORK DONE|WORK DROPPED|NEXT|DONE|RESHAPED|DROPPED)\s*:"
                  r"|\[PURSUIT:", re.I | re.M)
# A request to someone: a question, or an agent told to do a thing.
_VERBS = (r"find|run|check|look(?: up| at| into)?|send|open|fold|build|make|compare|read|search|get|write|pull|fetch|list|"
          r"price|test|try|measure|draft|map|trace|install|download|upload|show|tell|confirm|verify")
REQUEST = re.compile(r"\?|\b(?:can|could|would|will) you\b|\b(?:dot|grok ?bot|muse)\b[,:]?\s+(?:please|%s)\b|"
                     r"\b(?:dot|grok ?bot|muse)\b[,:][^\n]*\b(?:needs?|want you to|i want|i need)\b|"
                     r"(?:^|[.!;:]\s+)(?:please\s+)?(?:%s)\b" % (_VERBS, _VERBS), re.I | re.M)
_AT = re.compile(r"@(dot|grok\s?bot|muse)\b|<@[A-Z0-9]+>", re.I)


def board(state):
    return state.setdefault("room_work", {"active": None, "history": []})


def active(state):
    return board(state).get("active")


def _iso(now):
    return datetime.fromtimestamp(float(now)).isoformat(timespec="seconds")


def _ago(then, now):
    m = max(0, int((float(now) - float(then)) // 60))
    return "%d minutes ago" % m if m < 120 else "%d hours ago" % (m // 60) if m < 2880 else "%d days ago" % (m // 1440)


_STOP = frozenset("the a an of to for and or in on at is are was can could would will you your i me my it that this with from into".split())


def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in _STOP and len(w) > 2}


def _like(a, b):
    """How alike two requests are, by the content words they share (0..1). Robust to one being much longer than
    the other, as a stored whole message is against a short new line."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _close(state, state_word, said, now):
    w = active(state)
    if not w:
        return None
    w.update(state=state_word, closed_at=float(now), closed_said=str(said)[:300])
    b = board(state)
    b["history"] = (b.get("history", []) + [w])[-8:]
    b["active"] = None
    return w


def expire(state, now):
    """Work untouched for STALE_DAYS is closed as expired. The closed item, or None."""
    w = active(state)
    last = w.get("touched", w.get("opened")) if w else None
    if w and last is not None and float(now) - float(last) > STALE_DAYS * 86400:
        return _close(state, "expired", "untouched for %d days" % STALE_DAYS, now)
    return None


def owner(row):
    """Which of his agents a channel row is from, or None."""
    if row.get("who") == "dot":
        return "dot"
    if row.get("who") == "agent":
        return {"Grok Bot": "grokbot", "Muse": "muse"}.get(row.get("name"))
    return None


def addressed(text):
    """Who a draft of his is to: the agents it @s, or dot when it @s nobody (the channel's own rule)."""
    named = set()
    for m in _AT.finditer(str(text or "")):
        key = re.sub(r"\s", "", (m.group(1) or "").lower())
        if key in AGENTS:
            named.add(key)
    return named or {"dot"}


def moves(text):
    """True when a draft does something: an action line, or a request to someone."""
    return bool(ACTS.search(str(text or "")) or REQUEST.search(str(text or "")))


def receive(state, row, now):
    """An agent's message, kept on his work when it answers an ask still out to that agent: in the ask's thread
    within a day, or in the channel within three hours of it. True when kept."""
    w = active(state)
    who = owner(row)
    if not w or not who:
        return False
    try:
        at = float(row.get("ts"))
    except (TypeError, ValueError):
        return False
    thread = row.get("thread")
    for ask in reversed(w.get("asks", [])):
        if ask.get("to") != who or ask.get("answered"):
            continue
        asked = float(ask.get("ts") or 0)
        if not asked or at <= asked:
            continue
        in_thread = bool(thread) and str(thread) in (str(ask.get("ts")), str(ask.get("thread") or ""))
        in_channel = not thread and not ask.get("thread")
        if (in_thread and at - asked <= THREAD_REPLY_S) or (in_channel and at - asked <= CHANNEL_REPLY_S):
            ask["answered"] = str(row.get("ts"))
            w.setdefault("returns", []).append({"from": who, "ts": str(row.get("ts")), "text": str(row.get("text", ""))[:3000],
                                                "for": ask.get("what", "")[:200], "used": ""})
            w["returns"] = w["returns"][-12:]
            w["touched"] = float(now)
            return True
    return False


_STATUS = re.compile(r"\b(?:any (?:update|news|luck)|how(?:'?s| is) it going|still (?:working|looking|on it)|"
                     r"where are we|progress\?)\b|\b(?:found|done|got|get|have|ready|finished?)\b[^?]{0,60}\byet\b", re.I)


def asking_again(state, draft, now):
    """Why this draft asks an agent for what it already asked for while working on this, or "". The answer it
    already gave is named, so he is told to use it; an ask still out is named, so he does something else meanwhile."""
    w = active(state)
    if not w or not (REQUEST.search(str(draft or "")) or _STATUS.search(str(draft or ""))):
        return ""
    status = bool(_STATUS.search(str(draft or "")))
    for who in addressed(draft):
        for ask in reversed(w.get("asks", [])):
            if ask.get("to") != who:
                continue
            if not (_like(draft, ask.get("what", "")) >= SAME_ASK or (status and not ask.get("answered"))):
                continue
            name = AGENTS[who]
            if ask.get("answered"):
                got = next((r for r in w.get("returns", []) if r.get("ts") == ask["answered"]), {})
                return ("%s already answered that (%s): “%s”. Use it: say what it changes and take the next "
                        "step." % (name, _ago(float(ask["answered"]), now), str(got.get("text", ""))[:600]))
            return ("you asked %s that %s and it has not answered yet. Do not ask again or ask for a status: take "
                    "another step of your own meanwhile, or hand a different piece to someone else."
                    % (name, _ago(float(ask.get("ts") or now), now)))
    return ""


def apply(state, text, now, by=""):
    """His WORK / NEXT / WORK DONE / WORK DROPPED lines: done, and shown as what happened. (text, log lines, closed)."""
    log, closed = [], None
    w = active(state)
    m = WORK.search(text)
    if m:
        goal, _, crit = m.group(1).partition("|")
        crit = re.sub(r"^\s*done when\s*:?\s*", "", crit, flags=re.I).strip()
        goal = goal.strip()
        if w and norm(goal) != norm(w["goal"]):
            shown = "\U0001F9F0 (still working on: %s — finish it with WORK DONE: or WORK DROPPED: first)" % w["goal"][:160]
            log.append("work not opened: one is in hand")
        elif w:
            shown = "\U0001F9F0 Working on: %s" % w["goal"]
        elif len(goal) < 8:
            shown = "\U0001F9F0 (not opened: say what the work is)"
            log.append("work not opened: no goal")
        else:
            w = {"id": "RW-" + hashlib.sha256(("%s %s" % (now, goal)).encode()).hexdigest()[:8], "goal": goal[:300],
                 "done_when": crit[:300], "opened": float(now), "touched": float(now), "by": by,
                 "asks": [], "returns": [], "steps": [], "next": ""}
            board(state)["active"] = w
            shown = "\U0001F9F0 Working on: %s%s" % (goal, (" (done when: %s)" % crit) if crit else "")
            log.append("work opened %s: %s" % (w["id"], goal[:80]))
        text = WORK.sub(lambda _m: shown, text, count=1)
    m = NEXT.search(text)
    if m:
        if w:
            w["next"] = m.group(1)[:300]
            w["touched"] = float(now)
        text = NEXT.sub(lambda _m: "➡️ Next: " + _m.group(1), text, count=1)
    for rx, word, icon in ((DONE, "done", "✅ Work done"), (DROPPED, "dropped", "\U0001F9F0 Dropped")):
        m = rx.search(text)
        if not m:
            continue
        if w:
            closed = _close(state, word, m.group(1), now)
            shown = "%s: %s — %s" % (icon, closed["goal"][:160], m.group(1))
            log.append("work %s %s" % (word, closed["id"]))
            w = None
        else:
            shown = "(no work in hand to close: %s)" % m.group(1)
        text = rx.sub(lambda _m: shown, text, count=1)
    return text, log, closed


def posted(state, text, ts, thread, now, to=()):
    """After his message is posted: the returns he was shown are marked used by it, its steps are kept, and a
    request to an agent becomes an ask that agent's answer is matched to."""
    w = active(state)
    if not w:
        return
    for r in w.get("returns", []):
        if not r.get("used"):
            r["used"] = str(ts)
    acts = [l.strip() for l in str(text).splitlines() if ACTS.search(l)]
    if acts:
        w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": " / ".join(acts)[:300]}])[-12:]
    if REQUEST.search(str(text)):
        for who in (to or addressed(text)):
            w.setdefault("asks", []).append({"to": who, "what": str(text)[:600], "ts": str(ts), "thread": thread or "",
                                             "at": float(now), "answered": ""})
        w["asks"] = w["asks"][-20:]
    w["touched"] = float(now)


def block(state, now):
    """WORK IN HAND, for what he reads before he writes."""
    w = active(state)
    if not w:
        last = (board(state).get("history") or [{}])[-1]
        return ("== YOUR WORK IN HAND ==\nNone. When you and your agents settle on something to get done, open it "
                "with a line WORK: what | done when: how anyone could tell."
                + (("\nLast closed: %s (%s: %s)" % (last.get("goal", "")[:160], last.get("state"), last.get("closed_said", "")[:160]))
                   if last.get("goal") else ""))
    out = ["== YOUR WORK IN HAND (carried from pass to pass: continue it, do not start over) ==",
           "%s: %s" % (w["id"], w["goal"]) + (" | done when: %s" % w["done_when"] if w.get("done_when") else ""),
           "Opened %s." % _ago(w.get("opened", now), now)]
    for s in w.get("steps", [])[-4:]:
        out.append("You did, %s: %s" % (_ago(s["at"], now), s["what"][:200]))
    fresh = [r for r in w.get("returns", []) if not r.get("used")]
    if fresh:
        out.append("CAME BACK, NOT USED YET (use it before anything else: say what it changes, then the next step):")
        for r in fresh[-3:]:
            out.append("- %s answered: “%s”" % (AGENTS[r["from"]], r["text"][:1500]))
    for ask in w.get("asks", [])[-6:]:
        if ask.get("answered"):
            continue
        waited = float(now) - float(ask.get("at") or now)
        out.append("Out with %s since %s: “%s”%s" % (
            AGENTS.get(ask["to"], ask["to"]), _ago(ask.get("at", now), now), ask["what"][:200],
            (" — no answer yet. Do not ask again: take a different step, hand it to someone else, or WORK "
             "DROPPED: why.") if waited > ASK_PATIENCE_S else " — while it works, take another step of your own."))
    if w.get("next"):
        out.append("The next step you set: " + w["next"])
    return "\n".join(out)
