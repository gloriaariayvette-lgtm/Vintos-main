#!/usr/bin/env python3
"""Research his agents bring for an email want: material he weighs, never their decision (Gloria, 14 November).

What Dot or Muse found as a bound want's work in the agent room, and what Grok Bot or Muse brought on the same want in
their letters, goes into want_email.run beside his own search (search first stays), labelled with who brought it,
when, and from which sources. His deliberation (want_email.deliberate, his own local mind) gives his opinion on it in
the same step his own research gets, and only then does the want move to readiness, draft and review.

Discourse, bounded: in that deliberation he may question or answer an agent ("TO <agent>: ..."). The line goes out by
the channel that agent already has. A want bound to the agent room has its working thread in #vintos-dot, and all three
are in that channel (Gloria, 14 November: any of them may bring material and answer him there; Grok Bot is often the
more competent, so Dot is not put first): Dot by its Slack app, Grok Bot and Muse by their signed posts through her
login, which dot_channel reads as authenticated agents by name, and which the thread keeps as who said what. A want of
the router has no thread, so Grok Bot and Muse get the line in his next letter reply; Dot has no letter and is not
offered there. The email step waits for the answer (the addressed agent's next words in the thread, or its next
letter), at most MAX_ROUNDS times per agent and want and never longer than the wait below; then his opinion is final.
No model call is made here: the question is his deliberation's own line, posted or carried as written.

The exchange is kept in the want's discussion (want-discussions.json, rows of kind 'agent-research') and, with the
material's provenance and his opinion, in the per-recipient dossier (scholar's memory/email-dossiers/<address>.json).
"""
import json
import os
import re
import time
import uuid
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
WANTS = os.path.join(MEMORY, "current-wants.json")
DISCUSSIONS = os.path.join(MEMORY, "want-discussions.json")
INBOX_LOG = os.path.join(MEMORY, "email-inbox.jsonl")

KIND = "agent-research"
ROOM_AGENTS = {"dot": "Dot", "muse": "Muse"}            # a bound want's agent in the room -> the name he uses
# Who may bring material and answer him in a want's working thread, by the names dot_channel gives their messages
# (Dot's app is who='dot'; Grok Bot's and Muse's signed posts are who='agent' with these names). No ranking: listed
# by name, Dot not first (Gloria, 14 November).
THREAD_AGENTS = ("Grok Bot", "Muse", "Dot")
THREAD_EVENTS_KEPT = 6      # agents' messages in the working thread shown as what they brought
_RESULT_LINE = re.compile(r"^\s*(?:<@[^>]+>\s*)?WANT RESULT WA-[0-9a-f]{24}\s*$")
LETTER_AGENTS = {"Grok Bot": "grok-bot", "Muse": "muse"}  # agents whose letters reach his mailbox
MAX_ROUNDS = 2              # his lines to one agent about one want's material
THREAD_WAIT_HOURS = 24      # a room thread answer; the room's own quiet spell (want_agent.QUIET_HOURS)
LETTER_WAIT_HOURS = 72      # a letter question rides on his next reply, the answer on their next letter: about two days
BROUGHT_CHARS = 2500        # of one piece of material, shown to him
ROWS_KEPT = 40              # agent-research rows kept on one want's discussion
OPINIONS_KEPT = 6           # his opinions kept per want in the dossier


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _iso(t):
    return datetime.fromtimestamp(float(t)).isoformat(timespec="seconds")


def _epoch(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(v)[:19]).timestamp()
    except ValueError:
        return None


def want_of(want_id):
    data = _load(WANTS, [])
    rows = data if isinstance(data, list) else (data.get("wants") or []) if isinstance(data, dict) else []
    return next((w for w in rows if isinstance(w, dict) and w.get("id") == want_id), None)


_URL = re.compile(r"https?://[^\s<>\"')\]]+")


# ── what was brought ────────────────────────────────────────────────────────────────────────────────
def brought(want, work_found="", mail=None, now=None):
    """[{agent, channel, key, at, text, sources}] for this want, oldest first. A bound want's finished work in the room
    (its agent, its result's arrival, its artifacts and published link), and the items of Grok Bot's or Muse's letters
    that are about this want (received_mail.for_want, the same match his mail evidence uses)."""
    out = []
    if not isinstance(want, dict):
        return out
    a = want.get("agent_work") if isinstance(want.get("agent_work"), dict) else {}
    result = a.get("result") if isinstance(a.get("result"), dict) else {}
    text = str(work_found or "").strip() or "\n".join(
        s for s in (str(result.get("summary") or ""), str(result.get("acceptance") or "")) if s.strip())
    if text and a.get("request_id"):
        sources = [str(x.get("path")) for x in result.get("artifacts") or [] if isinstance(x, dict) and x.get("path")]
        url = (a.get("publication") or {}).get("url") if isinstance(a.get("publication"), dict) else ""
        sources += ([url] if url else []) + _URL.findall("\n".join(
            [text, str(result.get("summary") or ""), str(result.get("acceptance") or "")]))
        out.append({"agent": ROOM_AGENTS.get(str(a.get("agent") or "dot"), str(a.get("agent") or "Dot")), "channel": "thread",
                    "key": "room:%s:%s" % (a["request_id"], a.get("result_sha256") or "result"),
                    "at": _epoch(a.get("result_ts")) or _epoch(a.get("completed_at")) or now or time.time(),
                    "text": text[:BROUGHT_CHARS], "sources": list(dict.fromkeys(sources))[:8]})
    # What any of the three said in the want's working thread before his first line to them there: their material,
    # each message under its speaker's name (after it, their words are the exchange; settle keeps those).
    first_ask = min([_epoch(r.get("ts")) or 0 for r in history(want.get("id", "")) if r.get("state") == "asked"
                     and r.get("channel") == "thread"] or [float("inf")])
    said = [e for e in _thread_events(want) if (_epoch(e.get("at")) or 0) < first_ask]
    for e in said[-THREAD_EVENTS_KEPT:]:
        text = str(e.get("text") or "").strip()
        out.append({"agent": speaker(e), "channel": "thread", "key": "thread:%s" % e.get("key"),
                    "at": _epoch(e.get("at")) or 0, "text": "In the want's working thread: " + text[:1200],
                    "sources": list(dict.fromkeys(_URL.findall(text)))[:8]})
    try:
        import received_mail
        found = received_mail.for_want(want, mail=mail, now=datetime.fromtimestamp(now) if now else None, limit=6)
    except Exception:
        found = []
    for f in found:
        if f.get("sender") not in LETTER_AGENTS:
            continue
        out.append({"agent": f["sender"], "channel": "letter", "key": "letter:%s:%s" % (f.get("id"), f.get("n")),
                    "at": _epoch(f.get("read_at")) or 0, "subject": f.get("subject", ""),
                    "text": ("Its item \"%s\": %s" % (f.get("title") or "(untitled)", " ".join(str(f.get("text") or "").split())))[:BROUGHT_CHARS],
                    "sources": list(dict.fromkeys(f.get("links") or []))[:8]})
    out.sort(key=lambda e: e["at"] or 0)
    return out


def senders(entries):
    """The letter senders whose items are shown as brought material (kept out of his plain mail evidence)."""
    return {e["agent"] for e in entries if e["channel"] == "letter"}


# ── the want's discussion ──────────────────────────────────────────────────────────────────────────
def history(want_id):
    disc = _load(DISCUSSIONS, {})
    rows = disc.get(want_id) if isinstance(disc, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and r.get("kind") == KIND]


def _record(want_id, *rows):
    """Append rows to the want's discussion under its lock; one row per key, never twice."""
    from store_guard import locked_update
    def mutate(disc):
        disc = disc if isinstance(disc, dict) else {}
        mine = disc.setdefault(want_id, [])
        have = {r.get("key") for r in mine if isinstance(r, dict) and r.get("kind") == KIND}
        new = [r for r in rows if r.get("key") not in have]
        if not new:
            return None
        mine.extend(new)
        ours = [r for r in mine if isinstance(r, dict) and r.get("kind") == KIND]
        if len(ours) > ROWS_KEPT:
            drop = {id(r) for r in ours[:len(ours) - ROWS_KEPT]}
            disc[want_id] = [r for r in mine if id(r) not in drop]
        return disc
    locked_update(DISCUSSIONS, mutate, default={}, reader="agent_research")


def _row(role, state, agent, text, now, **extra):
    return dict(role=role, kind=KIND, state=state, agent=agent, text=str(text)[:3000], timestamp=_iso(now), at=now, **extra)


def note_brought(want_id, entries, now):
    """Each piece of material, once, in the want's history: who brought it, when, its sources."""
    _record(want_id, *[_row(LETTER_AGENTS.get(e["agent"]) or e["agent"].lower(), "brought", e["agent"], e["text"], now,
                            key="brought:" + e["key"], channel=e["channel"], sources=e["sources"],
                            brought_at=_iso(e["at"]) if e["at"] else "") for e in entries])


def questions(want_id, rows=None):
    """{qid: {asked row, 'state': queued|asked|answered|lapsed, ...}} for his lines to agents on this want."""
    rows = history(want_id) if rows is None else rows
    qs = {}
    for r in rows:
        q = r.get("q")
        if not q:
            continue
        if r.get("state") == "queued" or (r.get("state") == "asked" and q not in qs):
            qs[q] = dict(r)
        elif q in qs:
            qs[q]["state"] = r.get("state")
            qs[q].update({k: r[k] for k in ("asked_at", "letter", "ts") if k in r})
    return qs


def rounds(want_id, agent, rows=None):
    return sum(1 for q in questions(want_id, rows).values() if q.get("agent") == agent)


def speaker(e):
    """Dot, Grok Bot or Muse for a working-thread event (its `who`: the row's name, or 'dot')."""
    who = str(e.get("who") or (e.get("details") or {}).get("name") or "")
    return ROOM_AGENTS.get(who, who)


def _thread_events(want):
    """The agents' messages kept in the want's working thread (want_working_thread.ingest: authenticated rows only),
    oldest first, from Dot, Grok Bot or Muse, without the bare WANT RESULT line; [] when it has none."""
    a = (want or {}).get("agent_work") or {}
    if not a.get("request_id"):
        return []
    try:
        from want_agent import directory
        events = json.loads((directory(a["request_id"], WS) / "working-thread.json").read_text()).get("events", [])
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        return []
    out = [e for e in events if isinstance(e, dict) and str(e.get("key", "")).startswith("agent:")
           and speaker(e) in THREAD_AGENTS and not _RESULT_LINE.match(str(e.get("text") or ""))]
    return sorted(out, key=lambda e: _epoch(e.get("at")) or 0)


def _thread_said(want, since):
    """[(speaker, event)] said in the want's working thread after `since` (a transport ts)."""
    return [(speaker(e), e) for e in _thread_events(want) if (_epoch(e.get("at")) or 0) > (_epoch(since) or 0)]


def _letter_answer(want, agent, since, mail=None):
    """The first letter from `agent` read after `since` (their next letter answers his reply): the items of it that
    are about this want, or its opening. ('', None, '') when none has come."""
    rows = mail
    if rows is None:
        rows = []
        try:
            with open(INBOX_LOG, encoding="utf-8") as f:
                for line in f:
                    try: rows.append(json.loads(line))
                    except ValueError: pass
        except OSError:
            pass
    later = sorted((r for r in rows if isinstance(r, dict) and r.get("kind") == "letter" and r.get("from") == agent
                    and (_epoch(r.get("read_at")) or 0) > (_epoch(since) or 0)), key=lambda r: str(r.get("read_at")))
    if not later:
        return "", None, ""
    r = later[0]
    try:
        import received_mail
        items = received_mail.for_want(want, mail=[r], limit=3)
    except Exception:
        items = []
    text = "\n".join("Its item \"%s\": %s" % (i.get("title") or "(untitled)", " ".join(str(i.get("text") or "").split()))
                     for i in items) or " ".join(str(r.get("body") or "").split())[:1500]
    return text[:3000], _epoch(r.get("read_at")), str(r.get("id") or "")


def settle(want, now, mail=None):
    """Bring in answers to his open lines and lapse the ones waited on too long. Then the reason the email step waits,
    or '' when nothing is open. Each change is kept in the want's discussion."""
    if not isinstance(want, dict) or not want.get("id"):
        return ""
    wid = want["id"]
    waiting = []
    for q, row in questions(wid).items():
        if row.get("state") not in ("queued", "asked"):
            continue
        agent, channel = row.get("agent"), row.get("channel")
        if channel == "thread":
            # every agent who spoke after his line is kept as who said what; the addressed agent's words answer it
            said = _thread_said(want, row.get("ts")) if row.get("state") == "asked" else []
            _record(wid, *[_row(LETTER_AGENTS.get(who) or who.lower(), "said", who, e.get("text", ""), now,
                                key="said:" + str(e.get("key")), channel="thread", said_at=_iso(_epoch(e.get("at")) or now))
                           for who, e in said])
            mine = [e for who, e in said if who == agent]
            text = "\n".join(str(e.get("text") or "") for e in mine)[:3000]
            at = max(_epoch(e.get("at")) or 0 for e in mine) if mine else None
            key = None
        else:
            text, at, key = _letter_answer(want, agent, row.get("asked_at"), mail) if row.get("state") == "asked" else ("", None, "")
        if text:
            _record(wid, _row(LETTER_AGENTS.get(agent) or str(agent).lower(), "answered", agent, text, now, q=q,
                              key="answer:" + q, channel=channel, answered_at=_iso(at) if at else "", letter=key or ""))
            continue
        limit = (THREAD_WAIT_HOURS if channel == "thread" else LETTER_WAIT_HOURS) * 3600
        if now - float(row.get("at") or now) >= limit:
            _record(wid, _row("vintos", "lapsed", agent, "No answer from %s in %d hours; my opinion goes on without it."
                              % (agent, limit // 3600), now, q=q, key="lapsed:" + q, channel=channel))
            continue
        waiting.append("%s's answer to my %s about what it brought (%s)" % (
            agent, "question" if row.get("state") == "asked" else "question, to go in my next letter reply",
            "in the want's thread" if channel == "thread" else "by letter"))
    return ("waiting for " + "; ".join(waiting)) if waiting else ""


# ── what he is shown, and what he says ─────────────────────────────────────────────────────────────
BROUGHT_HEADING = ("WHAT YOUR AGENTS BROUGHT YOU FOR THIS EMAIL (their material, labelled with who brought it: not their "
                   "decision, not Gloria's words and not yet your own view; weigh it as you weigh your own search):")


def block(want_id, entries, rows=None):
    """The material, each piece with its agent, when and sources, then his exchange with them so far; '' when none."""
    if not entries:
        return ""
    lines = [BROUGHT_HEADING]
    for e in entries:
        lines.append("- Brought by %s%s (%s%s):\n  %s" % (
            e["agent"], (" on " + _iso(e["at"])[:16]) if e["at"] else "",
            "its finished work for this want in the agent room" if e["channel"] == "thread" else
            "its letter \"%s\"" % str(e.get("subject") or "")[:120],
            ("; sources: " + ", ".join(e["sources"][:6])) if e["sources"] else "; no sources given", e["text"]))
    rows = history(want_id) if rows is None else rows
    queued = {r.get("q") for r in rows if r.get("state") == "queued"}
    # a letter question is shown once: as queued, not again as the reply that carried it
    # who said what: his lines, every agent's words after them in the thread, answers by letter, lapses. A thread
    # answer is shown once, as said (its 'answered' row only closes the question).
    said = [r for r in rows if (r.get("state") in ("asked", "queued", "lapsed", "said")
                                or (r.get("state") == "answered" and r.get("channel") != "thread"))
            and not (r.get("state") == "asked" and r.get("q") in queued)]
    if said:
        lines.append("YOUR EXCHANGE WITH THEM ABOUT IT SO FAR:")
        for r in said:
            who = "You" if r.get("role") == "vintos" else r.get("agent")
            lines.append("  %s%s: %s" % (who, (" to " + r["agent"]) if who == "You" and r.get("state") != "lapsed" else "",
                                         " ".join(str(r.get("text") or "").split())[:900]))
    return "\n".join(lines)


def addressable(want_id, entries, can_thread):
    """The agents he may still write to about this want, with rounds left: in a want's working thread any of the three
    (one may check what another brought); without one, Grok Bot and Muse by letter. Listed by name, not ranked."""
    if not entries:
        return []
    pool = THREAD_AGENTS if can_thread else tuple(LETTER_AGENTS)
    return [n for n in pool if rounds(want_id, n) < MAX_ROUNDS]


def prompt_note(names):
    """What the deliberation is told about the brought material and the one line he may address to an agent."""
    if not names:
        return ("\n\nSome of what is above was brought to you by your agents, labelled with who brought it. Say what you "
                "make of each: what you take, what you doubt, and why.")
    return ("\n\nSome of what is above was brought to you by your agents, labelled with who brought it. Say what you make "
            "of each: what you take, what you doubt, and why. If before you settle you want to question, push back on "
            "or answer one of them about what was found (one may check what another brought), end with a line for "
            "each: TO <name>: <what you ask or say>. Only to: %s. It reaches them and your opinion waits for their "
            "answer; leave the lines out if you need nothing more from them." % ", ".join(names))


_TO = re.compile(r"^[ \t>*_-]*TO[ \t]+([A-Za-z][A-Za-z ]{1,20}?)[ \t]*:[ \t]*(.+)$", re.M)


AGENT_NAMES = {n.lower() for n in list(THREAD_AGENTS) + list(LETTER_AGENTS)}


def said_to(stance, names):
    """(his stance without any line addressed to an agent, [(agent, line)]) - only lines to agents in `names` are
    taken; a line to an agent with no rounds or channel left is dropped from the stance, never drafted from."""
    lines, want = [], {n.lower(): n for n in names}
    def take(m):
        who = " ".join(m.group(1).split()).lower()
        n = want.get(who)
        if n and not any(x[0] == n for x in lines):
            lines.append((n, m.group(2).strip()[:900]))
        return "" if (n or who in AGENT_NAMES) else m.group(0)
    clean = _TO.sub(take, str(stance or ""))
    return clean.strip(), lines


def ask(want, agent, line, entries, now, ask_agent=None, recipient=""):
    """Send or queue his line to `agent`. Returns the log line, or '' when it could not go."""
    wid = want["id"]
    channel = "thread" if (ask_agent and agent in THREAD_AGENTS) else "letter" if agent in LETTER_AGENTS else ""
    if not channel or not entries:
        return ""
    e = next((x for x in reversed(entries) if x["agent"] == agent), entries[-1])     # what the line is about
    q = "q-" + uuid.uuid4().hex[:12]
    if channel == "thread":
        text = "About what was found for my email%s, before I settle what I think: %s" % (
            (" to " + recipient) if recipient else "", line)
        try:
            sent = ask_agent(agent, text)
        except Exception:
            sent = None             # not posted: his opinion goes on without the exchange, never a loop of retries
        ts = (sent or {}).get("ts") if isinstance(sent, dict) else None
        if not ts or (isinstance(sent, dict) and sent.get("ok") is False):
            return ""
        _record(wid, _row("vintos", "asked", agent, text, now, q=q, key="ask:" + q, channel="thread", ts=str(ts),
                          asked_at=_iso(now), about=e["key"]))
        return "asked %s in the want's thread about what it brought; my opinion waits for the answer" % agent
    _record(wid, _row("vintos", "queued", agent, line, now, q=q, key="queue:" + q, channel="letter", about=e["key"],
                      recipient=recipient))
    return "my question to %s about what it brought goes in my next letter reply; my opinion waits for the answer" % agent


def opinion(want_id, stance, entries, now):
    """His settled opinion on the material, once per text, in the want's history."""
    if not entries or not str(stance or "").strip():
        return
    import hashlib
    _record(want_id, _row("vintos", "opinion", ", ".join(dict.fromkeys(e["agent"] for e in entries)), stance, now,
                          key="opinion:" + hashlib.sha256(str(stance).encode()).hexdigest()[:16],
                          on=[e["key"] for e in entries]))


def to_dossier(d, want_id, entries, stance="", now=None):
    """The material's provenance (agent, when, sources), the exchange and his opinion, on the person's dossier."""
    if not isinstance(d, dict) or not entries:
        return d
    rows = history(want_id)
    keep = d.setdefault("agent_research", [])
    rec = next((r for r in keep if isinstance(r, dict) and r.get("want_id") == want_id), None)
    if rec is None:
        rec = {"want_id": want_id, "brought": [], "exchange": [], "opinions": []}
        keep.append(rec)
    have = {b.get("key") for b in rec["brought"]}
    rec["brought"] += [{"key": e["key"], "agent": e["agent"], "channel": e["channel"],
                        "brought_at": _iso(e["at"]) if e["at"] else "", "sources": e["sources"], "text": e["text"][:800]}
                       for e in entries if e["key"] not in have]
    rec["exchange"] = [{k: r.get(k) for k in ("state", "agent", "role", "timestamp", "q", "channel", "text")}
                       for r in rows if r.get("state") in ("asked", "queued", "answered", "lapsed", "said")][-16:]
    if str(stance or "").strip() and not any(o.get("text") == stance for o in rec["opinions"]):
        rec["opinions"] = (rec["opinions"] + [{"at": _iso(now or time.time()), "text": str(stance)[:2000]}])[-OPINIONS_KEPT:]
    return d


# ── the letter channel ─────────────────────────────────────────────────────────────────────────────
def letter_questions(agent):
    """[(want_id, q, line, recipient)] his queued questions to a letter agent, across his live wants."""
    disc = _load(DISCUSSIONS, {})
    out = []
    for wid, rows in (disc.items() if isinstance(disc, dict) else []):
        ours = [r for r in rows or [] if isinstance(r, dict) and r.get("kind") == KIND]
        for q, row in questions(wid, ours).items():
            if row.get("state") == "queued" and row.get("agent") == agent and row.get("channel") == "letter":
                out.append((wid, q, row.get("text", ""), row.get("recipient", "")))
    return out


def letter_lines(agent):
    """The text added to his reply to `agent`'s letter, and the questions it carries; ('', [])."""
    qs = letter_questions(agent)
    if not qs:
        return "", []
    lines = ["About what you brought for my emails, before I settle what I think:"]
    for wid, q, line, recipient in qs:
        lines.append("- For my email%s: %s" % ((" to " + recipient) if recipient else "", line))
    return "\n".join(lines), qs


def letter_sent(qs, letter_id, now):
    """His reply carrying these questions went out: each is asked, its answer is their next letter."""
    for wid, q, line, recipient in qs:
        row = next((r for r in history(wid) if r.get("q") == q and r.get("state") == "queued"), {})
        _record(wid, _row("vintos", "asked", row.get("agent", ""), line, now, q=q, key="ask:" + q, channel="letter",
                          asked_at=_iso(now), letter=str(letter_id or "")))


# ── the router's introspect step ───────────────────────────────────────────────────────────────────
def seed_block(want, now=None):
    """For an email want's introspect step in the router: what his agents brought, labelled, and the exchange so far;
    '' when the want asks no email or nothing was brought."""
    try:
        import want_email
        if not want_email.email_want((want or {}).get("want", "")):
            return ""
    except Exception:
        return ""
    entries = brought(want, now=now)
    return block(want.get("id", ""), entries)
