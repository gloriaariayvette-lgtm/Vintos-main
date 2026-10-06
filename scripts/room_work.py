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
SETTLE_DAYS = 7                # what was finished, dropped, or closed by Gloria stays closed this long

WORK = re.compile(r"^\s*WORK:\s*(.+?)\s*$", re.I | re.M)
NEXT = re.compile(r"^\s*NEXT:\s*(.+?)\s*$", re.I | re.M)
DONE = re.compile(r"^\s*WORK DONE:\s*(.+?)\s*$", re.I | re.M)
DROPPED = re.compile(r"^\s*WORK DROPPED:\s*(.+?)\s*$", re.I | re.M)
NEW = re.compile(r"^\s*NEW:\s*(.+?)\s*$", re.I | re.M)
# A completion that is only arranged (2026-10-05: a song "scheduled for the morning" was closed as done, and it was
# still owed). Done means it exists and was delivered; this names the ways of saying it has not happened yet.
DEFERRED = re.compile(r"\b(?:scheduled|queued|pending|planned|awaiting|lined up|set up for|will (?:be|make|send|run|"
                      r"deliver|land|post|generate)|to be (?:made|sent|delivered|generated|run)|tomorrow|"
                      r"in the morning|later today|tonight at|once it (?:lands|runs|finishes|is made))\b", re.I)

# Every line that makes something happen in the channel, his and the new ones; one of these moves the work.
ACTS = re.compile(r"^\s*(?:LOCKED|DO|LAB|LINE(?:\s+L-[\w-]+)?|CHECK|STUDY FIX|APPROVED|DENIED|CAMPAIGN(?: MOVE)?|SHARE|ASK|"
                  r"TV|ECHO|LIGHTS|MISCHIEF|TO GLORIA|ASK GLORIA|MAKE|WORK|WORK DONE|WORK DROPPED|NEXT|DONE|RESHAPED|DROPPED|"
                  r"SEARCH|BUY)\s*:"
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
    if state_word in ("done", "dropped"):
        settle(state, w["goal"], "%s: %s" % (state_word, said), "vintos", now)
    return w


# --- what is settled: kept in the channel's state, so the next pass and the next model read it (2026-10-05) ---------
# Gloria, 2026-10-04: "No more plan making for Eve for the next week. Work on something else." He dropped the
# Saturday lecture RSVP at 15:47 the next day and asked for its listing again at 19:34, on another model, with that
# hour out of the transcript he was shown. Nothing that closed a topic outlived the messages it was said in.
_SCAFFOLD = frozenset(("more stop stopped plan plans planning making make made next week weeks day days today tomorrow "
                       "tonight work working something else anymore again please dont don about with any for until "
                       "rest no not let lets let's drop dropped done finished leave alone enough quit now while "
                       "this that these those just also want wants need needs going get got " + _VERBS.replace("|", " ")
                       .replace("(?:", " ").replace(")?", " ")).split())
# only a clear closing: her ordinary "don't" ("Don't talk about number 4") is not one
_GLORIA_CLOSES = re.compile(r"\b(?:no more|stop \w+ing|quit \w+ing|drop (?:it|this|that|the)|leave [\w' ]{1,30} alone|"
                            r"not now|enough (?:with|about|of)|(?:don'?t|do not) [\w' ]{1,40}\b(?:again|anymore))\b"
                            r"|\bfor the (?:next|rest of the) (?:week|month|\d+ days)\b", re.I)
_SPAN = re.compile(r"\b(?:for )?(?:the )?(?:next|rest of the|this) (week|month|day)\b|\bfor (\d+) days?\b|"
                   r"\b(today|tonight)\b|\b(anymore|ever again|again)\b", re.I)


def topic_words(text):
    return sorted(w for w in _words(text) if w not in _SCAFFOLD)


def settle(state, topic, said, by, now, days=SETTLE_DAYS):
    """Close a topic for `days`: his finished or dropped work, a promise he dropped, or Gloria's word."""
    words = topic_words(topic)
    if not words:
        return None
    b = board(state)
    keep = [e for e in b.get("settled", []) if e.get("words") != words]
    entry = {"topic": str(topic)[:300], "words": words, "said": str(said)[:300], "by": by, "at": float(now),
             "until": float(now) + float(days) * 86400}
    b["settled"] = (keep + [entry])[-24:]
    return entry


def settled(state, now):
    return [e for e in board(state).get("settled", []) if float(e.get("until", 0)) > float(now)]


def settled_match(state, text, now):
    """The settled entry this text is about, or None: most of its topic's words, at least two (one if that is all
    the topic has)."""
    have = _words(text)
    for e in reversed(settled(state, now)):
        words = set(e.get("words") or [])
        shared = words & have
        if words and len(shared) >= min(2, len(words)) and len(shared) / len(words) >= 0.5:
            return e
    return None


def gloria_closes(state, text, now):
    """Her message closing a topic ("no more plan making for Eve for the next week") kept as settled, for as long as
    she said (a week when she named none). The entry, or None."""
    if not _GLORIA_CLOSES.search(str(text or "")):
        return None
    days = SETTLE_DAYS
    m = _SPAN.search(str(text))
    if m:
        unit, n, short, ever = m.groups()
        days = (30 if unit and unit.lower() == "month" else 1 if unit and unit.lower() == "day" else 7 if unit
                else int(n) if n else 1 if short else 30)
    first = re.split(r"(?<=[.!?])\s+", str(text).strip())[0]
    return settle(state, first, "Gloria: " + str(text).strip()[:280], "gloria", now, days=max(1, min(days, 60)))


def reopens(state, text, now):
    """Why this draft reopens a settled topic without new information, or "". Talk about it is free; an action on it
    (an ask, a buy, a search request, new work) is not, unless a NEW: line says what changed, and never against
    Gloria's own word while it stands."""
    rest = "\n".join(l for l in str(text or "").splitlines()
                     if not re.match(r"^\s*(?:WORK DONE|WORK DROPPED|DONE|DROPPED|RESHAPED)\s*:", l, re.I))
    if not moves(rest):
        return ""             # closing it, or talking about it, is never held
    e = settled_match(state, rest, now)
    if not e:
        return ""
    when = datetime.fromtimestamp(float(e["at"])).strftime("%b %d %H:%M")
    until = datetime.fromtimestamp(float(e["until"])).strftime("%b %d")
    if e.get("by") == "gloria":
        return ("Gloria closed this on %s, until %s: “%s”. It stays closed: do not ask, plan or search for it. "
                "Work on something else." % (when, until, e["said"][6:220]))
    if NEW.search(str(text)):
        return ""
    return ("you settled this on %s (%s), and it stays settled until %s. Do not ask, search or plan for it again. "
            "If something has truly changed, say it on a line NEW: what changed, and act on that."
            % (when, e["said"][:200], until))


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
    # A message that closes its work and names the work again (or opens the next) is read closing first: it showed
    # "still working on ... finish it with WORK DONE:" beside "✅ Work done" for the same work (2026-10-05)
    for rx, word, icon in ((DONE, "done", "✅ Work done"), (DROPPED, "dropped", "\U0001F9F0 Dropped")):
        m = rx.search(text)
        if not m:
            continue
        if w and word == "done" and DEFERRED.search(m.group(1)):
            # arranged is not delivered: the work stays in hand until it exists (2026-10-05, the scheduled song)
            w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": "arranged, not delivered: " + m.group(1)[:240]}])[-12:]
            w["touched"] = float(now)
            shown = ("\u23F3 Not done yet: %s — arranged is not delivered. It stays in hand until it exists and has "
                     "reached her; then WORK DONE: with where it is." % m.group(1))
            log.append("work not closed: %s is arranged, not done" % w["id"])
        elif w:
            closed = _close(state, word, m.group(1), now)
            shown = "%s: %s — %s" % (icon, closed["goal"][:160], m.group(1))
            log.append("work %s %s" % (word, closed["id"]))
            w = None
        else:
            shown = "(no work in hand to close: %s)" % m.group(1)
        text = rx.sub(lambda _m: shown, text, count=1)
    m = WORK.search(text)
    if m and closed and (norm(m.group(1).partition("|")[0]) == norm(closed["goal"])
                         or _like(m.group(1).partition("|")[0], closed["goal"]) >= 0.8):
        text = WORK.sub("", text, count=1).strip()       # the work just closed, named again: not reopened
        m = None
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
    m = NEW.search(text)
    if m:
        lifted = settled_match(state, text, now)
        if lifted and lifted.get("by") != "gloria":
            board(state)["settled"] = [e for e in board(state).get("settled", []) if e is not lifted]
            log.append("reopened with new information: %s" % lifted["topic"][:80])
        text = NEW.sub(lambda _m: "\U0001F195 New: " + _m.group(1), text, count=1)
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


def settled_block(state, now):
    rows = settled(state, now)[-8:]
    if not rows:
        return ""
    out = ["== SETTLED (closed; do not ask, search or plan for these again) =="]
    for e in rows:
        out.append("- %s, %s, until %s: %s" % (
            "Gloria" if e.get("by") == "gloria" else "you", datetime.fromtimestamp(float(e["at"])).strftime("%b %d %H:%M"),
            datetime.fromtimestamp(float(e["until"])).strftime("%b %d"), e["said"][:220]))
    out.append("Your own can be reopened only on a line NEW: what changed. Gloria's stand until she lifts them.")
    return "\n".join(out)


def block(state, now):
    """WORK IN HAND, and what is settled, for what he reads before he writes."""
    sb = settled_block(state, now)
    return _block(state, now) + (("\n\n" + sb) if sb else "")


def _block(state, now):
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
