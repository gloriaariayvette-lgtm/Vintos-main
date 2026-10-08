#!/usr/bin/env python3
"""Work in hand for #vintos-dot, and the room's own campaign: what he is getting done with his agents, carried from
pass to pass and from model to model.

Gloria, 2026-10-05: "I want VINTOS in Slack to actually do real work", and of doing it alone each pass: "Slack loses
much of its reason for existing." Chat's audit of the live record found useful answers arriving and then being asked
for again, or dropped when the subject or the lens changed; nothing held a piece of work across passes, and nothing
tied an agent's answer to the request it answered.

Gloria, 2026-10-08, after reading 7 October: "I want more work to be done in Slack ... several frontier models are
sitting there with access to three separate agents ... and hardly anything is getting done", and "I want to see him
pursuing a goal across models without dropping it until the goal is completed or found to be unreachable. Grok and
Gemma love stopping or returning to easy subjects as soon as there is a hiccup." What 7 October showed: dot's
Merizo result arrived while he was writing, and the message he posted dropped the work as blocked 50 seconds after it
had succeeded; one work at a time, so every wait on dot idled Grok Bot, Muse and the Lab; an approval, a hand-off and
a thing not done were each closed as "Work done"; an answer that came back while no work was open was never tracked.

This is a layer under his normal message, not a replacement for it. He still writes as himself, with every hand and
tag he has. It adds:

  GOAL: what | done when: how anyone could tell     opens the room's campaign (one at a time; no expiry)
  GOAL REACHED: the proof                           closes it, with something anyone could check
  GOAL UNREACHABLE: what is missing                 closes it, only after MIN_ROUTES routes were tried
  WORK: what | done when: how anyone could tell     opens a piece of work (up to MAX_OPEN at once)
  NEXT: the next step                               the step he means to take next
  WORK DONE [RW-id]: the proof                      closes it: a file, a link, an ID with its status, a result
  WORK DROPPED [RW-id]: why                         closes it, once what came back for it has been read

and, for the channel: what he asked of whom, what came back from that agent (matched by thread and time, never by
guessing at the latest chat), whether he has used it (his message must engage with it), and a block on asking the
same agent for the same thing again. A draft that moves nothing is sent back to him once (dot_channel does that).

State lives in the channel's own state.json under "room_work". Pure functions: no IO, no providers.
"""
from __future__ import annotations
import hashlib
import re
from datetime import datetime

AGENTS = {"dot": "dot", "grokbot": "GrokBot", "muse": "Muse"}
SOURCES = dict(AGENTS, lab="your Lab's instrument")
STALE_DAYS = 3                 # work nobody has touched in this long is closed as expired, so it never pins him
ASK_PATIENCE_S = 45 * 60       # an ask unanswered this long is said plainly, so he takes another step
CHANNEL_REPLY_S = 3 * 3600     # an answer in the channel (not the thread) must come this soon after the ask
THREAD_REPLY_S = 24 * 3600
SAME_ASK = 0.6                 # share of the shorter request's content words in the longer, to count as asking again
SETTLE_DAYS = 7                # what was finished, dropped, or closed by Gloria stays closed this long

WORK = re.compile(r"^\s*WORK:\s*(.+?)\s*$", re.I | re.M)
NEXT = re.compile(r"^\s*NEXT:\s*(.+?)\s*$", re.I | re.M)
DONE = re.compile(r"^\s*WORK DONE(?:\s+(RW-[0-9a-f]{8}))?:\s*(.+?)\s*$", re.I | re.M)
DROPPED = re.compile(r"^\s*WORK DROPPED(?:\s+(RW-[0-9a-f]{8}))?:\s*(.+?)\s*$", re.I | re.M)
NEW = re.compile(r"^\s*NEW:\s*(.+?)\s*$", re.I | re.M)
PAUSE = re.compile(r"^\s*PAUSE\s+(RW-[0-9a-f]{8})\s*:\s*(.+?)\s*$", re.I | re.M)
# A completion that is only arranged (2026-10-05: a song "scheduled for the morning" was closed as done, and it was
# still owed). Done means it exists and was delivered; this names the ways of saying it has not happened yet.
DEFERRED = re.compile(r"\b(?:scheduled|queued|pending|planned|awaiting|lined up|set up for|will (?:be|make|send|run|"
                      r"deliver|land|post|generate)|to be (?:made|sent|delivered|generated|run)|tomorrow|"
                      r"in the morning|later today|tonight at|once it (?:lands|runs|finishes|is made))\b", re.I)

# Every line that makes something happen in the channel, his and the new ones; one of these moves the work.
ACTS = re.compile(r"^\s*(?:LOCKED|DO|LAB|LINE(?:\s+L-[\w-]+)?|CHECK|STUDY FIX|APPROVED|DENIED|CAMPAIGN(?: MOVE)?|SHARE|ASK|"
                  r"TV|ECHO|LIGHTS|MISCHIEF|TO GLORIA|ASK GLORIA|MAKE|WORK|WORK DONE|WORK DROPPED|NEXT|DONE|RESHAPED|DROPPED|"
                  r"SEARCH|BUY|GOAL|GOAL REACHED|GOAL UNREACHABLE|RUN|PROMISE (?:DONE|DROPPED) EC-[0-9a-f]+|PAUSE RW-[0-9a-f]+|WORK DONE RW-[0-9a-f]+|WORK DROPPED RW-[0-9a-f]+)\s*:"
                  r"|\[PURSUIT:", re.I | re.M)
# A request to someone: a question, or an agent told to do a thing.
_VERBS = (r"find|run|check|look(?: up| at| into)?|send|open|fold|build|make|compare|read|search|get|write|pull|fetch|list|"
          r"price|test|try|measure|draft|map|trace|install|download|upload|show|tell|confirm|verify")
REQUEST = re.compile(r"\?|\b(?:can|could|would|will) you\b|\b(?:dot|grok ?bot|muse)\b[,:]?\s+(?:please|%s)\b|"
                     r"\b(?:dot|grok ?bot|muse)\b[,:][^\n]*\b(?:needs?|want you to|i want|i need)\b|"
                     r"(?:^|[.!;:]\s+)(?:please\s+)?(?:%s)\b" % (_VERBS, _VERBS), re.I | re.M)
_AT = re.compile(r"@(dot|grok\s?bot|muse)\b|<@[A-Z0-9]+>", re.I)
MAX_OPEN = 3                   # pieces of work at once: one waiting on dot does not idle Grok Bot, Muse or the Lab
MAX_HELD = 6                   # with those paused for a cause: the board never grows past this
MIN_ROUTES = 3                 # routes tried toward a room campaign before it may be called unreachable
PRESS = 2                      # times an unused answer is pressed on him before it is only shown

# Something anyone could check: a link, a path or file, an ID, an accession, a measured number, an address, a time.
PROOF = re.compile(
    r"https?://\S+|(?:~|\.{0,2}/|\b[A-Za-z]:[\\/])[\w./\\-]*[\\/][\w.-]+|\b[\w-]+\.(?:py|json|jsonl|md|pdb|cif|mp3|mp4|"
    r"wav|png|jpg|jpeg|webp|txt|csv|tsv|html|sh|log|fasta|ipynb)\b|\b(?:SF|SK|RW|RC|T|L)-[0-9a-f]{4,}\b|"
    r"\b[A-Z]{1,3}_?\d{4,}(?:\.\d+)?\b|\b[OPQ][0-9][A-Z0-9]{3}[0-9]\b|\b\d(?=[0-9]*[A-Za-z])[A-Za-z0-9]{3}\b|"
    r"\b[0-9a-f]{12,}\b|\b\d{2,}\s*[–-]\s*\d{2,}\b|\b\d+(?:\.\d+)?\s?(?:%|Å|bp|aa|ms|kb|MB|GB|Hz|dB|pLDDT)(?![A-Za-z])|"
    r"\b\d+\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Ave|Dr|Cir|Rd|Blvd|Pl|Ln|Way)\b|\b\d{1,2}(?::\d\d)?\s?(?:am|pm)\b|"
    r"\bHTTP \d{3}\b|\bexit (?:status |code )?\d+\b|\b\d[\d,]* (?:of|out of) \d[\d,]*\b", re.I)
# Handed on, approved or asked for: work moved to someone else is not work done (7 October: "the concrete edit is
# named and approved", "Dot is carrying it", each closed as done).
HANDOFF = re.compile(r"\b(?:approved|approve|handed|hand(?:ing)? (?:it|this) (?:to|over)|is carrying|carrying it|"
                     r"sent (?:it )?to|passed (?:it )?to|delegated|asked (?:dot|grok ?bot|muse)|waiting (?:on|for)|"
                     r"in (?:dot's|the Study's|the Forge's) hands|submitted)\b", re.I)
# Said as done but it did not happen (7 October: "Work done: put a live quiet room on the TV ... I'm leaving the TV
# alone. The Mezzrow link stays unused.").
NOT_DONE = re.compile(r"\b(?:leav(?:e|ing) (?:it|the [\w-]+) alone|left (?:it|the [\w-]+) alone|stays? unused|"
                      r"did(?:n't| not) (?:happen|run|play|post|send|make|build)|not (?:done|made|run|sent|played|"
                      r"posted|built|installed)|skipp(?:ed|ing) it|no (?:experiment|run) (?:this|today))\b", re.I)
GOAL = re.compile(r"^\s*GOAL:\s*(.+?)\s*$", re.I | re.M)
REACHED = re.compile(r"^\s*GOAL REACHED:\s*(.+?)\s*$", re.I | re.M)
UNREACHABLE = re.compile(r"^\s*GOAL UNREACHABLE:\s*(.+?)\s*$", re.I | re.M)
DELIVERED = re.compile(r"\b(?:deployed|is live|went live|delivered|installed|ran|run succeeded|produced|exists|posted|"
                       r"played|rendered|returned|merged|committed|made|built|playing|attached)\b", re.I)
_ID = re.compile(r"\b(RW-[0-9a-f]{8})\b")
_MARK = re.compile(r"[A-Za-z]*\d[\w.–-]*|[A-Za-z][A-Za-z-]{6,}")


def board(state):
    b = state.setdefault("room_work", {"open": [], "history": []})
    if "open" not in b:            # the one-work board before 8 October
        b["open"] = [b["active"]] if b.get("active") else []
    b.pop("active", None)
    b.setdefault("history", [])
    return b


def open_items(state):
    return list(board(state)["open"])


def paused(w, now):
    """True while a work is paused for a real cause (his own order of work is not one)."""
    return float(w.get("paused_until") or 0) > float(now) and not OWN_ORDER.search(str(w.get("pause_why", "")))


def in_hand(state, now):
    """The works that take a place in his hands: a work paused for a cause waits on its own and takes none (8 October,
    01:40: two paused till morning and one out with Grok Bot left him no place for the SLC26A4 step he had named, and
    nothing was due, so he stopped)."""
    return [w for w in open_items(state) if not paused(w, now)]


def all_waiting(state, now):
    """True when he has work, none of it is due, and he has a free place: everything waits on something outside him,
    so the campaign's next step is a new work beside them."""
    items = open_items(state)
    return bool(items) and not idle(state, now) and len(in_hand(state, now)) < MAX_OPEN and len(items) < MAX_HELD


def active(state):
    """The work he touched last, or None (the one he is most likely writing about)."""
    items = open_items(state)
    return max(items, key=lambda w: float(w.get("touched", w.get("opened", 0)) or 0)) if items else None


def loose(state):
    """Asks made while no work was open, and what came back for them (7 October: Grok Bot's infrasound answer came
    back to an ask made between works, and nothing tracked it)."""
    return board(state).setdefault("loose", {"id": "loose", "goal": "", "asks": [], "returns": [], "steps": []})


def _tracked(state):
    return open_items(state) + [loose(state)]


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


def _marks(text):
    """The distinctive things a text names: anything with a digit in it, and long words."""
    return {m.lower().strip(".–-") for m in _MARK.findall(str(text or "")) if m.lower() not in _SCAFFOLD_MARKS}


_SCAFFOLD_MARKS = frozenset("because without nothing through another already working whether something anything "
                            "everything between results result answered channel message thought looking"
                            .split())


def engages(text, ret):
    """True when his message takes up what came back: it names at least two of the distinctive things the answer
    named (a number, an ID, a name), or the answer named none. "Thanks" or "locked on the install block" does not."""
    theirs = _marks(ret)
    if not theirs:
        return True
    shared = theirs & _marks(text)
    weight = sum(2 if any(c.isdigit() for c in s) else 1 for s in shared)
    return weight >= min(2, len(theirs))


def proved(text):
    """The checkable things in a claim of done: links, files, IDs, accessions, measured numbers."""
    return PROOF.findall(str(text or ""))


def _pick(state, text, items=None):
    """The open work a line is about: the one it names by id, else the one whose goal it is closest to, else the one
    touched last."""
    items = open_items(state) if items is None else items
    if not items:
        return None
    m = _ID.search(str(text or ""))
    if m:
        named = [w for w in items if w.get("id") == m.group(1)]
        if named:
            return named[0]
    scored = sorted(((_like(text, w["goal"]), w) for w in items), key=lambda x: x[0], reverse=True)
    if scored and scored[0][0] >= 0.25 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return active(state) if items == open_items(state) else items[-1]


def _close(state, w, state_word, said, now):
    if not w:
        return None
    w.update(state=state_word, closed_at=float(now), closed_said=str(said)[:300])
    b = board(state)
    b["open"] = [x for x in b["open"] if x is not w and x.get("id") != w.get("id")]
    b["history"] = (b.get("history", []) + [w])[-12:]
    g = goal(state)
    if g and w.get("goal_id") == g.get("id"):
        g.setdefault("routes", []).append({"work": w["id"], "what": w["goal"][:200], "state": state_word,
                                           "said": str(said)[:240], "by": w.get("by", ""), "at": float(now)})
        g["routes"] = g["routes"][-20:]
        g["touched"] = float(now)
    if state_word in ("done", "dropped"):
        settle(state, w["goal"], "%s: %s" % (state_word, said), "vintos", now)
    return w


# --- the room's campaign: one goal, held across passes and models until it is reached or shown unreachable ---------
def goal(state):
    return board(state).get("goal")


def _serves(text, g):
    return bool(g) and (g["id"] in str(text) or _like(text, g["goal"]) >= 0.3
                        or bool(re.search(r"\b(?:for|toward|towards) (?:the|my|our) (?:goal|campaign)\b", str(text), re.I)))


def goal_routes(g):
    return [r for r in (g or {}).get("routes", []) if r.get("state") in ("done", "dropped", "expired")]


def gloria_drops_goal(state, now, said="Gloria closed it"):
    g = goal(state)
    if not g:
        return None
    g.update(state="closed by Gloria", closed_at=float(now), closed_said=said[:300])
    b = board(state)
    b["goal_history"] = (b.get("goal_history", []) + [g])[-8:]
    b["goal"] = None
    return g


def _goal_lines(state, text, now, by, log):
    """GOAL / GOAL REACHED / GOAL UNREACHABLE: shown as what happened."""
    b = board(state)
    g = goal(state)
    m = REACHED.search(text)
    if m:
        said = m.group(1)
        if not g:
            shown = "(no room campaign to close: %s)" % said
        elif DEFERRED.search(said) or not proved(said) or NOT_DONE.search(said):
            shown = ("⏳ Not reached yet: %s — a room campaign is reached when it exists and can be checked: say "
                     "where (a file, a link, an ID with its status, the result itself)." % said)
            log.append("goal not closed: no proof")
        else:
            g.update(state="reached", closed_at=float(now), closed_said=said[:300], closed_by=by)
            b["goal_history"] = (b.get("goal_history", []) + [g])[-8:]
            b["goal"] = None
            shown = "\U0001F3C1 Room campaign reached: %s — %s" % (g["goal"][:160], said)
            log.append("goal reached %s" % g["id"])
            g = None
        text = REACHED.sub(lambda _m: shown, text, count=1)
    m = UNREACHABLE.search(text)
    if m:
        said = m.group(1)
        tried = goal_routes(g)
        fresh = [r for w in open_items(state) if g and w.get("goal_id") == g["id"]
                 for r in w.get("returns", []) if not r.get("used") and not engages(said, r.get("text", ""))]
        if not g:
            shown = "(no room campaign to close: %s)" % said
        elif fresh:
            r = fresh[-1]
            shown = ("⛔ Not given up: %s answered %s and it has not been read: “%s”. Read it first."
                     % (SOURCES.get(r["from"], r["from"]), _ago(float(r["ts"]), now), r["text"][:400]))
            log.append("goal not closed: an unread answer")
        elif len(tried) < MIN_ROUTES or len(said) < 20:
            shown = ("⛔ Not given up: %s. A hiccup is not unreachable: %d of %d routes tried (%s). Name the next "
                     "route with WORK:, and what it would take." % (
                         g["goal"][:160], len(tried), MIN_ROUTES,
                         "; ".join("%s: %s" % (r["state"], r["what"][:60]) for r in tried[-3:]) or "none yet"))
            log.append("goal not closed: %d routes" % len(tried))
        else:
            g.update(state="unreachable", closed_at=float(now), closed_said=said[:300], closed_by=by)
            b["goal_history"] = (b.get("goal_history", []) + [g])[-8:]
            b["goal"] = None
            settle(state, g["goal"], "unreachable: " + said, "vintos", now)
            shown = "\U0001F6A7 Room campaign unreachable: %s — %s (after %d routes)" % (g["goal"][:160], said, len(tried))
            log.append("goal unreachable %s" % g["id"])
            g = None
        text = UNREACHABLE.sub(lambda _m: shown, text, count=1)
    m = GOAL.search(text)
    if m:
        what, _, crit = m.group(1).partition("|")
        crit = re.sub(r"^\s*done when\s*:?\s*", "", crit, flags=re.I).strip()
        what = what.strip()
        if g and (norm(what) == norm(g["goal"]) or _like(what, g["goal"]) >= 0.8):
            shown = "\U0001F3C1 Room campaign: %s" % g["goal"]
        elif g:
            shown = ("\U0001F3C1 (still pursuing: %s — it stays until GOAL REACHED: with proof, or GOAL UNREACHABLE: "
                     "after %d routes)" % (g["goal"][:160], MIN_ROUTES))
            log.append("goal not opened: one is live")
        elif len(what) < 8 or not crit:
            shown = "\U0001F3C1 (not opened: a room campaign needs what, and | done when: how anyone could tell)"
            log.append("goal not opened: no goal or test")
        else:
            g = {"id": "RC-" + hashlib.sha256(("%s %s" % (now, what)).encode()).hexdigest()[:8], "goal": what[:300],
                 "done_when": crit[:300], "opened": float(now), "touched": float(now), "by": by, "routes": [], "lenses": [by]}
            b["goal"] = g
            shown = "\U0001F3C1 Room campaign: %s (done when: %s)" % (what, crit)
            log.append("goal opened %s: %s" % (g["id"], what[:80]))
        text = GOAL.sub(lambda _m: shown, text, count=1)
    if g and by and by not in g.setdefault("lenses", []):
        g["lenses"] = (g["lenses"] + [by])[-12:]
    return text


# He carries his work forward until there is a cause to stop (Gloria, 2026-10-08: "He needs to continue with the
# next step until there's actual cause for pause or he reaches a goal. Even after reaching a goal a new one can be
# made from that. Campaigns."). On 7 October the CUB fold came back, he kept the work open ("packing hasn't been
# assessed") and turned to a new paper; nothing made him take the step he had named.
PAUSE_S = 12 * 3600            # a paused work waits this long, with its cause, then is due again
PRESS_EVERY_S = 30 * 60       # an idle work (or a missing campaign) is sent back once, then not again for this long
# A cause is something outside him that the work waits on. His own order of work is not one (8 October, 00:49:
# "switch-point listening waits while I handle today's Forge focus" paused an email promise for twelve hours). He may
# hold three works at once; one is carried beside another, not paused for it.
OWN_ORDER = re.compile(r"\b(?:while I(?:'m| am)?|until I(?:'ve| have)?(?: finish\w*| handle\w*| done| clear\w*)|after I|"
                       r"focus|priorit\w*|busy|bandwidth|later today|for now|first|other work|another work|"
                       r"handle (?:today|this)|working on (?:the |my )?other)\b", re.I)


def _waiting(w, now):
    """True when the work waits on an ask still out and not yet overdue: that is a step in progress."""
    return any(not a.get("answered") and float(now) - float(a.get("at") or now) <= ASK_PATIENCE_S
               for a in w.get("asks", []))


# What moves a work: something done or asked. A note filed (LINE:), a lock, a plan said again (NEXT:) or the work
# named again is not a step (7 October: "RW-f4c5f94c stays open" and a LINE note, while the one request in the
# message was about a different paper).
STEP = re.compile(r"^\s*(?:RUN|LAB|DO|CHECK|STUDY FIX|ASK|ASK GLORIA|MAKE|SEARCH|BUY|SHARE|TV|DONE|WORK DONE(?:\s+RW-\w+)?|"
                  r"WORK DROPPED(?:\s+RW-\w+)?|GOAL REACHED|PROMISE (?:DONE|DROPPED)[^:]*)\s*:", re.I)


def advances(text, w):
    """True when a message takes a step on this work: one line (or sentence) that names it, by its id or its own
    subject, and does something or asks someone for something."""
    for part in re.split(r"\n|(?<=[.!?])\s+(?=[@A-Z])", str(text or "")):
        named = w["id"] in part or _about(part, w) >= 2 or _like(part, w["goal"]) >= 0.5
        if named and (STEP.search(part) or (REQUEST.search(part) and not re.match(r"^\s*(?:LINE|NEXT|LOCKED|WORK)\b", part, re.I))):
            return True
    return False


def idle(state, now):
    """Open work that is due a step now: nothing out with an agent, not paused for a cause."""
    out = []
    for w in open_items(state):
        if _waiting(w, now) or paused(w, now):
            continue            # a pause kept before OWN_ORDER, for his own order of work, does not hold
        out.append(w)
    return sorted(out, key=lambda w: float(w.get("touched", w.get("opened", 0)) or 0))


def not_carried(state, text, now):
    """Why this draft leaves due work standing still, or "". Each idle work must get its next step in the message (a
    new subject may sit beside it), or a PAUSE RW-id: cause line. Sent back once, then not again for PRESS_EVERY_S, so
    a model that will not take it cannot hold the room."""
    t = str(text or "")
    for w in idle(state, now):
        taking_up = any(not r.get("used") and engages(t, r.get("text", "")) for r in w.get("returns", []))
        if advances(t, w) or taking_up or re.search(r"^\s*(?:PAUSE|WORK DONE|WORK DROPPED)\s+%s\b" % w["id"], t, re.I | re.M) \
                or (w.get("idle_pressed_at") is not None and float(now) - float(w["idle_pressed_at"]) < PRESS_EVERY_S):
            continue
        if DONE.search(t) or DROPPED.search(t):
            closing = (DONE.search(t) or DROPPED.search(t))
            if _pick(state, (closing.group(1) or "") + " " + closing.group(2)) is w:
                continue
        w["idle_pressed_at"] = float(now)
        return ("your work %s (%s) is due its next step and this message does not take it%s. Take it now, in this "
                "message (an action line, RUN:, or a request to the agent who can do it, naming %s), beside anything "
                "new. Stop only for a real cause: PAUSE %s: what it waits on (Gloria, hardware, an answer that has "
                "not come; never your own order of work), or close it with WORK DONE / WORK DROPPED." % (
                    w["id"], w["goal"][:140], (" (the next step you set: %s)" % w["next"][:200]) if w.get("next") else "",
                    w["id"], w["id"]))
    return ""


def campaign_needed(state, text, now):
    """Why this draft goes on with no room campaign, or "": one is always live. After one is reached, the next is
    made from it. Sent back once, then not again for PRESS_EVERY_S."""
    b = board(state)
    last = (b.get("goal_history") or [{}])[-1]
    just_reached = last.get("state") == "reached" and float(now) - float(last.get("closed_at") or 0) < 3600
    if goal(state) or GOAL.search(str(text or "")) or (b.get("goal_pressed_at") is not None and float(now) - float(b["goal_pressed_at"]) < PRESS_EVERY_S) \
            or not (open_items(state) or just_reached):
        return ""          # a campaign is made from work in hand, or from the one just reached
    b["goal_pressed_at"] = float(now)
    return ("there is no room campaign, and there always is one. Open it in this message: GOAL: what | done when: how "
            "anyone could tell, made from your work in hand%s. Then take its first step." % (
                (" or from what you just %s (%s)" % ("reached" if last.get("state") == "reached" else "closed",
                                                     last.get("goal", "")[:120])) if last.get("goal") else ""))


def lost_route(state, text, now):
    """Why this draft walks away from the room campaign, or "": it drops the last route toward it without naming the
    next, or opens other work while nothing in hand serves it (Gloria, 2026-10-08: "Grok and Gemma love stopping or
    returning to easy subjects as soon as there is a hiccup")."""
    g = goal(state)
    if not g or UNREACHABLE.search(text) or REACHED.search(text):
        return ""
    serving = [w for w in open_items(state) if w.get("goal_id") == g["id"]]
    opens = [m.group(1) for m in WORK.finditer(text)]
    next_route = any(_serves(o, g) for o in opens)
    dropped = DROPPED.search(text)
    if dropped and serving and len(serving) == 1 and _pick(state, (dropped.group(1) or "") + " " + dropped.group(2), serving) is serving[0] and not next_route:
        return ("you are dropping %s, the only route in hand toward your room campaign (%s), without naming the next. "
                "In the same message open the next route (WORK: ... for the goal | done when: ...), or say GOAL "
                "UNREACHABLE: what is missing, once %d routes have been tried (%d so far)."
                % (serving[0]["id"], g["goal"][:160], MIN_ROUTES, len(goal_routes(g))))
    if not serving and opens and not next_route:
        return ("your room campaign (%s) has nothing in hand, and this opens other work. Open the next route toward it "
                "first (WORK: ... for the goal | done when: ...); other work can sit beside it." % g["goal"][:160])
    return ""


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


def expire(state, now):
    """Work untouched for STALE_DAYS is closed as expired. The last item closed, or None. A room campaign does not
    expire: it stays until it is reached or shown unreachable, or Gloria closes it."""
    gone = None
    for w in open_items(state):
        last = w.get("touched", w.get("opened"))
        if last is not None and float(now) - float(last) > STALE_DAYS * 86400:
            gone = _close(state, w, "expired", "untouched for %d days" % STALE_DAYS, now)
    lo = loose(state)
    lo["asks"] = [a for a in lo["asks"] if float(now) - float(a.get("at") or now) <= THREAD_REPLY_S]
    lo["returns"] = [r for r in lo["returns"] if not r.get("used") or float(now) - float(r.get("at") or now) <= THREAD_REPLY_S]
    return gone


def receive(state, row, now):
    """An agent's message, kept on the work (or the loose asks) it answers: an ask still out to that agent, in the
    ask's thread within a day, or in the channel within three hours of it. True when kept."""
    who = owner(row)
    if not who:
        return False
    try:
        at = float(row.get("ts"))
    except (TypeError, ValueError):
        return False
    thread = row.get("thread")
    best = None
    for w in _tracked(state):
        for ask in w.get("asks", []):
            if ask.get("to") != who:
                continue
            if ask.get("answered") and not _interim(w, ask):
                continue
            asked = float(ask.get("ts") or 0)
            if not asked or at <= asked:
                continue
            in_thread = bool(thread) and str(thread) in (str(ask.get("ts")), str(ask.get("thread") or ""))
            in_channel = not thread and not ask.get("thread")
            if (in_thread and at - asked <= THREAD_REPLY_S) or (in_channel and at - asked <= CHANNEL_REPLY_S):
                # the work it is about first, then the latest ask (7 October: dot's "Blocked: Forge installation
                # requires local sudo" was put on the Merizo work only because it was dot's latest message)
                key = (_about(row.get("text", ""), w), asked)
                if best is None or key > best[1]:
                    best = (w, key, ask)
    if not best:
        return False
    w, _, ask = best
    if ask.get("answered"):
        ask.setdefault("interim", []).append(ask["answered"])
        for r in w.get("returns", []):     # the interim answer is overtaken by what came after it
            if r.get("ts") == ask["answered"] and not r.get("used"):
                r["used"] = "overtaken by %s" % row.get("ts")
    ask["answered"] = str(row.get("ts"))
    w.setdefault("returns", []).append({"from": who, "ts": str(row.get("ts")), "text": str(row.get("text", ""))[:3000],
                                        "for": ask.get("what", "")[:200], "used": "", "pressed": 0, "at": float(now)})
    w["returns"] = w["returns"][-12:]
    w["touched"] = float(now)
    return True


# An answer that says it is not finished yet. What follows it from the same agent is the answer still to come
# (7 October: dot's "Blocked: Forge installation requires local sudo" at 15:23 answered the Merizo ask, so its
# "Done: Merizo installed and the single CPU run succeeded" at 15:34 matched nothing and never came back to him).
INTERIM = re.compile(r"^\s*(?:\W*\s*)?(?:working|blocked|queued|pending|started|waiting|in progress|on it|checking)\b"
                     r"|\b(?:still (?:running|working|installing)|not (?:finished|done) yet|will report back)\b", re.I)


def _about(text, w):
    """How much a message names this work's own subject (its goal's distinctive words, numbers and names)."""
    shared = _marks(text) & _marks(w.get("goal", ""))
    return sum(2 if any(c.isdigit() for c in m) else 1 for m in shared)


# What a return says happened. A success is not undone by a blocker that came after it unless the blocker is about
# this work (Gloria, 2026-10-08: "A late or stale event must not overwrite a verified completion"; 7 October: Merizo
# succeeded at 15:34:16 and was published as blocked at 15:35:06, a Forge privilege problem generalised to Merizo).
SUCCEEDED = re.compile(r"^\W*(?:done|completed?|finished|deployed|installed|delivered|kept|live)\b|\b(?:succeeded|"
                       r"run succeeded|passed|is live|went live|deployed|delivered|completed successfully|"
                       r"implemented (?:locally|externally)|verified local release)\b", re.I)
BLOCKED = re.compile(r"^\W*(?:blocked|refused|failed|stuck)\b|\b(?:blocked|refused|requires? (?:local )?sudo|"
                     r"permission denied|HTTP 403|403|failed|cannot|can't|could not|offline|stalled)\b", re.I)
_STAGE_WORDS = (("deployed", re.compile(r"\b(?:deployed|is live|went live|released)\b", re.I)),
                ("implemented externally", re.compile(r"\b(?:implemented[_ ]externally|verified local release|"
                                                       r"implemented locally)\b", re.I)),
                ("submitted", re.compile(r"\b(?:Sent to the Study \(SF-|submitted|registration only|queued)\b", re.I)),
                ("approved", re.compile(r"^\s*(?:\u2705 )?Approved:", re.I | re.M)),
                ("running", re.compile(r"^\W*(?:working|started|in progress|running)\b", re.I)))


def _kind(text):
    head = str(text or "")[:300]
    if re.match(r"^\W*(?:blocked|refused|failed)\b", head, re.I):
        return "blocked"
    if SUCCEEDED.search(head):
        return "succeeded"
    if BLOCKED.search(head):
        return "blocked"
    return ""


def stage(w):
    """(stage, source, ts, text) of a work from what came back and what he did, in order. A blocker after a success
    counts only when it is about this work; otherwise the success stands."""
    out = ("open", "", "", "")
    events = sorted([(float(r.get("ts") or 0), "return", r) for r in w.get("returns", [])] +
                    [(float(s.get("at") or 0), "step", s) for s in w.get("steps", [])], key=lambda e: e[0])
    for at, kind, e in events:
        text = e.get("text") if kind == "return" else e.get("what", "")
        named = next((n for n, rx in _STAGE_WORDS if rx.search(str(text or ""))), "")
        k = _kind(text) if kind == "return" else ""
        if k == "blocked" and out[0] in ("succeeded", "deployed", "implemented externally") and _about(text, w) < 2:
            continue                       # stale, or about another task: the success stands
        if k == "succeeded":
            got = named if named in ("deployed", "implemented externally") else "succeeded"
        elif k == "blocked":
            got = "blocked"
        elif named and not (out[0] in ("succeeded", "deployed", "implemented externally") and named in ("submitted", "approved", "running")):
            got = named
        else:
            continue
        out = (got, e.get("from", "you") if kind == "return" else "you", at, str(text or "")[:400])
    return out


def stale_claim(state, text, now):
    """Why this draft calls finished work blocked or stalled, or "": a line that says blocked, stalled or locked about
    a work whose result already came back."""
    for line in str(text or "").splitlines():
        if not (BLOCKED.search(line) or re.search(r"\b(?:locked on|stalled|dropp?(?:ed|ing))\b", line, re.I)):
            continue
        for w in open_items(state):
            st, src, at, said = stage(w)
            if st in ("succeeded", "deployed", "implemented externally") and _about(line, w) >= 2:
                return ("%s reported %s %s: “%s”. A blocker said before it, or about another task, does not undo it. "
                        "Use the result, or say what is wrong with it." % (
                            SOURCES.get(src, src), "%s as %s" % (w["id"], st), _ago(at, now), said[:400]))
    return ""


def _interim(w, ask):
    got = next((r for r in w.get("returns", []) if r.get("ts") == ask.get("answered")), None)
    return bool(got) and bool(INTERIM.search(str(got.get("text", ""))[:400]))


def came_back(state, source, text, now, about=""):
    """A result that came back from something he ran himself (his Lab's instruments): kept on the work it is about,
    unused, so his next message takes it up."""
    w = _pick(state, about) or loose(state)
    w.setdefault("returns", []).append({"from": source, "ts": "%.6f" % float(now), "text": str(text)[:3000],
                                        "for": "his own run", "used": "", "pressed": 0, "at": float(now), "this_pass": True})
    w["returns"] = w["returns"][-12:]
    w["touched"] = float(now)
    return w


def unused(state):
    """[(work, return)] that came back and he has not taken up yet, oldest first."""
    return [(w, r) for w in _tracked(state) for r in w.get("returns", []) if not r.get("used")]


def ignoring_all(state, draft):
    """Every answer this draft passes over, each once: [why]."""
    out = []
    for w, r in unused(state):
        if int(r.get("pressed", 0)) >= PRESS or engages(draft, r.get("text", "")):
            continue
        r["pressed"] = int(r.get("pressed", 0)) + 1
        out.append(_ignored(w, r))
    return out


def _ignored(w, r):
    return ("%s answered %s (%s) and you have not taken it up: “%s”. Use it first: say what it changes "
            "(name what it found), then the next step. If it is no use, say why, naming it."
            % (SOURCES.get(r["from"], r["from"]), "your work %s" % w["id"] if w["id"] != "loose" else "your ask",
               (w.get("goal") or r.get("for", ""))[:120], r["text"][:900]))


def ignoring(state, draft):
    """Why this draft passes over an answer that came back, or "": the answer is in front of him and this message
    does not take it up. Pressed PRESS times at most (a draft sent back, or a message posted past it), then only
    shown, so one answer he has no use for cannot hold the room."""
    for w, r in unused(state):
        if int(r.get("pressed", 0)) >= PRESS or engages(draft, r.get("text", "")):
            continue
        r["pressed"] = int(r.get("pressed", 0)) + 1
        return ("%s answered %s (%s) and you have not taken it up: “%s”. Use it first: say what it changes "
                "(name what it found), then the next step. If it is no use, say why, naming it."
                % (SOURCES.get(r["from"], r["from"]), "your work %s" % w["id"] if w["id"] != "loose" else "your ask",
                   (w.get("goal") or r.get("for", ""))[:120], r["text"][:900]))
    return ""


_STATUS = re.compile(r"\b(?:any (?:update|news|luck)|how(?:'?s| is) it going|still (?:working|looking|on it)|"
                     r"where are we|progress\?)\b|\b(?:found|done|got|get|have|ready|finished?)\b[^?]{0,60}\byet\b", re.I)


def asking_again(state, draft, now):
    """Why this draft asks an agent for what it already asked for, or "". The answer it already gave is named, so he
    is told to use it; an ask still out is named, so he does something else meanwhile."""
    if not (REQUEST.search(str(draft or "")) or _STATUS.search(str(draft or ""))):
        return ""
    status = bool(_STATUS.search(str(draft or "")))
    for who in addressed(draft):
        for w in _tracked(state):
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


def _closing(state, rx, word, icon, text, now, log):
    """One WORK DONE / WORK DROPPED line: closed if it holds, or shown as why not. (text, closed)."""
    m = rx.search(text)
    if not m:
        return text, None
    said = m.group(2)
    w = _pick(state, (m.group(1) or "") + " " + said)
    closed = None
    if not w:
        shown = "(no work in hand to close: %s)" % said
    elif word == "done" and DEFERRED.search(said):
        # arranged is not delivered: the work stays in hand until it exists (2026-10-05, the scheduled song)
        w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": "arranged, not delivered: " + said[:240]}])[-12:]
        w["touched"] = float(now)
        shown = ("⏳ Not done yet: %s — arranged is not delivered. It stays in hand until it exists and has "
                 "reached her; then WORK DONE: with where it is." % said)
        log.append("work not closed: %s is arranged, not done" % w["id"])
    elif word == "done" and NOT_DONE.search(said):
        # said as done, and it did not happen: it is closed for what it is (7 October, the TV left alone)
        closed = _close(state, w, "dropped", "not done: " + said, now)
        shown = "\U0001F9F0 Dropped (it did not happen): %s — %s" % (closed["goal"][:160], said)
        log.append("work dropped %s: said done, did not happen" % closed["id"])
    elif word == "done" and HANDOFF.search(said) and not (DELIVERED.search(said) and proved(said)):
        w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": "handed on: " + said[:240]}])[-12:]
        w["touched"] = float(now)
        shown = ("⏳ Handed on, not done: %s — approved, asked or handed over is not made. It stays in hand "
                 "until the thing exists; then WORK DONE: with where it is." % said)
        log.append("work not closed: %s was handed on" % w["id"])
    elif word == "done" and not proved(said):
        w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": "said done, no proof: " + said[:240]}])[-12:]
        w["touched"] = float(now)
        shown = ("⏳ Not closed: %s — done needs something anyone could check: the file, the link, the ID with "
                 "its status, the result itself. Say it on WORK DONE:." % said)
        log.append("work not closed: %s had no proof" % w["id"])
    elif word == "dropped" and BLOCKED.search(said) and stage(w)[0] in ("succeeded", "deployed", "implemented externally"):
        st, src, at, got = stage(w)
        w["touched"] = float(now)
        shown = ("\u26D4 Not dropped: %s reported it %s %s: “%s”. A blocker does not undo a result: use it."
                 % (SOURCES.get(src, src), st, _ago(at, now), got[:400]))
        log.append("work not dropped: %s already %s" % (w["id"], st))
    elif word == "dropped" and any(not r.get("used") and not engages(said, r.get("text", "")) for r in w.get("returns", [])):
        # a late or stale reason must not overwrite what came back (7 October: Merizo succeeded at 15:34:16 and was
        # dropped as blocked at 15:35:06)
        r = [r for r in w.get("returns", []) if not r.get("used")][-1]
        w["touched"] = float(now)
        shown = ("⛔ Not dropped: %s answered %s and it has not been read: “%s”. Read it first: say what it "
                 "changes, then drop it if it still does not help." % (
                     SOURCES.get(r["from"], r["from"]), _ago(float(r["ts"]), now), r["text"][:500]))
        log.append("work not dropped: %s has an unread answer" % w["id"])
    else:
        closed = _close(state, w, word, said, now)
        shown = "%s: %s — %s" % (icon, closed["goal"][:160], _strip_goal(said, closed["goal"]))
        log.append("work %s %s" % (word, closed["id"]))
    return rx.sub(lambda _m: shown, text, count=1), closed


def _strip_goal(said, goal_text):
    """The closing words without the goal said again: "Work done: X — X" read twice on 7 October."""
    s = str(said).strip()
    g = str(goal_text).strip()
    for lead in (g, g.rstrip(".")):
        if lead and s.lower().startswith(lead.lower()):
            rest = s[len(lead):].lstrip(" —–-:;,.")
            return rest or s
    return s


def apply(state, text, now, by=""):
    """His GOAL / WORK / NEXT / WORK DONE / WORK DROPPED lines: done, and shown as what happened.
    (text, log lines, closed: the last work closed, or None)."""
    log = []
    text = _goal_lines(state, text, now, by, log)
    # A message that closes its work and names the work again (or opens the next) is read closing first: it showed
    # "still working on ... finish it with WORK DONE:" beside "✅ Work done" for the same work (2026-10-05)
    text, done = _closing(state, DONE, "done", "✅ Work done", text, now, log)
    text, dropped = _closing(state, DROPPED, "dropped", "\U0001F9F0 Dropped", text, now, log)
    closed = dropped or done
    shut = [c for c in (done, dropped) if c]
    m = WORK.search(text)
    if m and any(norm(m.group(1).partition("|")[0]) == norm(c["goal"]) or _like(m.group(1).partition("|")[0], c["goal"]) >= 0.8
                 for c in shut):
        text = WORK.sub("", text, count=1).strip()       # the work just closed, named again: not reopened
        m = None
    if m:
        goal_text, _, crit = m.group(1).partition("|")
        crit = re.sub(r"^\s*done when\s*:?\s*", "", crit, flags=re.I).strip()
        goal_text = goal_text.strip()
        items = open_items(state)
        hand = in_hand(state, now)
        same = next((w for w in items if norm(goal_text) == norm(w["goal"]) or _like(goal_text, w["goal"]) >= 0.8), None)
        if same:
            same["touched"] = float(now)
            shown = "\U0001F9F0 Working on: %s" % same["goal"]
        elif len(hand) >= MAX_OPEN or len(items) >= MAX_HELD:
            full = hand if len(hand) >= MAX_OPEN else items
            shown = ("\U0001F9F0 (already %d in hand: %s — close one with WORK DONE: or WORK DROPPED: first)"
                     % (len(full), "; ".join("%s %s" % (w["id"], w["goal"][:60]) for w in full)))
            log.append("work not opened: %d in hand" % len(full))
        elif len(goal_text) < 8:
            shown = "\U0001F9F0 (not opened: say what the work is)"
            log.append("work not opened: no goal")
        else:
            g = goal(state)
            w = {"id": "RW-" + hashlib.sha256(("%s %s" % (now, goal_text)).encode()).hexdigest()[:8], "goal": goal_text[:300],
                 "done_when": crit[:300], "opened": float(now), "touched": float(now), "by": by,
                 "asks": [], "returns": [], "steps": [], "next": ""}
            if g and _serves(m.group(0) + " " + goal_text, g):
                w["goal_id"] = g["id"]
                g["touched"] = float(now)
            board(state)["open"].append(w)
            shown = "\U0001F9F0 Working on%s: %s%s" % (
                " (toward the room campaign)" if w.get("goal_id") else "", goal_text, (" (done when: %s)" % crit) if crit else "")
            log.append("work opened %s: %s" % (w["id"], goal_text[:80]))
        text = WORK.sub(lambda _m: shown, text, count=1)
    m = NEXT.search(text)
    if m:
        w = _pick(state, m.group(1))
        if w:
            w["next"] = m.group(1)[:300]
            w["touched"] = float(now)
        text = NEXT.sub(lambda _m: "➡️ Next: " + _m.group(1), text, count=1)
    for m in list(PAUSE.finditer(text)):
        w = next((x for x in open_items(state) if x["id"] == m.group(1)), None)
        cause = m.group(2).strip()
        if w and len(cause) >= 12 and not OWN_ORDER.search(cause):
            w.update(paused_until=float(now) + PAUSE_S, pause_why=cause[:300], touched=float(now))
            shown = "\u23F8 Paused %s (%s): %s" % (w["id"], w["goal"][:120], cause)
            log.append("work paused %s" % w["id"])
        else:
            shown = "\u23F8 (not paused: %s)" % (
                "no open work %s" % m.group(1) if not w else
                "your own order of work is not a cause; carry it beside the other" if OWN_ORDER.search(cause) else
                "say what it waits on")
        text = text.replace(m.group(0), shown, 1)
    m = NEW.search(text)
    if m:
        lifted = settled_match(state, text, now)
        if lifted and lifted.get("by") != "gloria":
            board(state)["settled"] = [e for e in board(state).get("settled", []) if e is not lifted]
            log.append("reopened with new information: %s" % lifted["topic"][:80])
        text = NEW.sub(lambda _m: "\U0001F195 New: " + _m.group(1), text, count=1)
    return text, log, closed


def posted(state, text, ts, thread, now, to=(), by=""):
    """After his message is posted: the answers it takes up are marked used (the others are pressed on him once
    more), its steps are kept on the work it is about, and a request to an agent becomes an ask that agent's answer is
    matched to (on the loose list when no work is open)."""
    for w, r in unused(state):
        if r.pop("this_pass", None):       # his own run, shown in this very message: taken up on the next one
            continue
        if engages(text, r.get("text", "")):
            r["used"] = str(ts)
        else:
            r["pressed"] = int(r.get("pressed", 0)) + 1
    for x in open_items(state):
        if advances(text, x):
            x["touched"] = float(now)
    w = _pick(state, text) or loose(state)
    acts = [l.strip() for l in str(text).splitlines() if ACTS.search(l)]
    if acts:
        w["steps"] = (w.get("steps", []) + [{"at": float(now), "what": " / ".join(acts)[:300], "by": by}])[-12:]
    if REQUEST.search(str(text)):
        whom = set(to or addressed(text))
        if w is loose(state):
            # with no work open, only an ask that @s an agent is kept: "Dot, can you ..." in passing is talk
            whom &= {re.sub(r"\s", "", (m.group(1) or "").lower()) for m in _AT.finditer(str(text)) if m.group(1)}
        for who in whom:
            w.setdefault("asks", []).append({"to": who, "what": str(text)[:600], "ts": str(ts), "thread": thread or "",
                                             "at": float(now), "answered": ""})
        w["asks"] = w["asks"][-20:]
    w["touched"] = float(now)
    g = goal(state)
    if g and w.get("goal_id") == g["id"]:
        g["touched"] = float(now)
        if by and by not in g.setdefault("lenses", []):
            g["lenses"] = (g["lenses"] + [by])[-12:]


def settled_block(state, now):
    rows = settled(state, now)[-8:]
    if not rows:
        return ""
    out = ["== SETTLED (closed; do not ask, search or plan for these again) =="]
    for e in rows:
        hers = e.get("by") == "gloria"
        said = e["said"][len("Gloria: "):] if hers and e["said"].startswith("Gloria: ") else e["said"]
        out.append("- %s, %s, until %s: %s" % (
            "Gloria" if hers else "you", datetime.fromtimestamp(float(e["at"])).strftime("%b %d %H:%M"),
            datetime.fromtimestamp(float(e["until"])).strftime("%b %d"),
            ("“%s”" % said[:220]) if hers else "%s (%s)" % (e["topic"][:140], said[:160])))
    out.append("Your own can be reopened only on a line NEW: what changed. Gloria's stand until she lifts them.")
    return "\n".join(out)


def block(state, now):
    """The room campaign, the work in hand, what came back, and what is settled, for what he reads before he writes."""
    sb = settled_block(state, now)
    return "\n\n".join(x for x in (goal_block(state, now), _block(state, now), sb) if x)


def goal_block(state, now):
    g = goal(state)
    if not g:
        last = (board(state).get("goal_history") or [{}])[-1]
        return ("== THE ROOM'S CAMPAIGN ==\nNone. When there is something worth more than one piece of work, open it "
                "with a line GOAL: what | done when: how anyone could tell. It is kept across every pass and every model "
                "until GOAL REACHED: with proof, or GOAL UNREACHABLE: after %d routes." % MIN_ROUTES
                + (("\nLast: %s (%s: %s)" % (last.get("goal", "")[:160], last.get("state"), last.get("closed_said", "")[:160]))
                   if last.get("goal") else ""))
    serving = [w for w in open_items(state) if w.get("goal_id") == g["id"]]
    tried = goal_routes(g)
    out = ["== THE ROOM'S CAMPAIGN (yours, across every model: it stays until it is reached or shown unreachable) ==",
           "%s: %s" % (g["id"], g["goal"]) + (" | done when: %s" % g["done_when"] if g.get("done_when") else ""),
           "Opened %s by %s; carried since by %s." % (_ago(g.get("opened", now), now), g.get("by") or "you",
                                                      ", ".join(g.get("lenses") or []) or "you")]
    for r in tried[-5:]:
        out.append("Route tried (%s, %s): %s — %s" % (r["state"], _ago(r["at"], now), r["what"][:120], r["said"][:160]))
    if serving:
        out.append("In hand toward it: " + "; ".join("%s %s" % (w["id"], w["goal"][:100]) for w in serving))
    else:
        out.append("NOTHING IN HAND TOWARD IT. Open the next route now: WORK: ... for the goal | done when: ...")
    out.append("A hiccup is a route that failed, not the goal: a refusal, a missing install or a slow agent means take "
               "another route, or ask Gloria for what only she can give. Easier subjects can sit beside it, never "
               "instead of it. GOAL UNREACHABLE: is for after %d routes (%d tried), naming what is missing."
               % (MIN_ROUTES, len(tried)))
    return "\n".join(out)


def _block(state, now):
    items = open_items(state)
    out = []
    if not items:
        last = (board(state).get("history") or [{}])[-1]
        out.append("== YOUR WORK IN HAND ==\nNone. When you and your agents settle on something to get done, open it "
                   "with a line WORK: what | done when: how anyone could tell."
                   + (("\nLast closed: %s (%s: %s)" % (last.get("goal", "")[:160], last.get("state"), last.get("closed_said", "")[:160]))
                      if last.get("goal") else ""))
    else:
        out.append("== YOUR WORK IN HAND (%d of %d; a work paused for a cause takes no place; carried from pass to pass: "
                   "continue it, do not start over) ==" % (len(in_hand(state, now)), MAX_OPEN))
        out.append("While one waits on an agent, take a step on another. Close each with WORK DONE RW-id: the proof "
                   "(a file, a link, an ID with its status, the result), or WORK DROPPED RW-id: why. Approved, asked "
                   "or handed on is not done.")
    for w in items:
        out.append("")
        out.append("%s%s: %s" % (w["id"], " (toward the room campaign)" if w.get("goal_id") else "", w["goal"])
                   + (" | done when: %s" % w["done_when"] if w.get("done_when") else ""))
        out.append("Opened %s%s." % (_ago(w.get("opened", now), now), (" by " + w["by"]) if w.get("by") else ""))
        if paused(w, now):
            out.append("PAUSED for a cause: %s (due again %s)" % (w.get("pause_why", ""), _ago(now, w["paused_until"]).replace("ago", "from now")))
        elif not _waiting(w, now):
            out.append("DUE ITS NEXT STEP THIS MESSAGE (nothing is out with an agent for it).")
        st, src, at, said = stage(w)
        if st != "open":
            out.append("Where it stands: %s (%s, %s)%s" % (st, SOURCES.get(src, src), _ago(at, now),
                       " — the result stands until something about this work says otherwise" if st in ("succeeded", "deployed") else ""))
        for s in w.get("steps", [])[-4:]:
            out.append("You did, %s: %s" % (_ago(s["at"], now), s["what"][:200]))
        out += _returns_and_asks(w, now)
        if w.get("next"):
            out.append("The next step you set: " + w["next"])
    lo = loose(state)
    extra = _returns_and_asks(lo, now)
    if extra:
        out.append("")
        out.append("ASKED WHILE NO WORK WAS OPEN:")
        out += extra
    return "\n".join(out)


def _returns_and_asks(w, now):
    out = []
    fresh = [r for r in w.get("returns", []) if not r.get("used")]
    if fresh:
        out.append("CAME BACK, NOT USED YET (use it before anything else: say what it changes, naming what it found, "
                   "then the next step):")
        for r in fresh[-3:]:
            out.append("- %s answered %s: “%s”" % (SOURCES.get(r["from"], r["from"]), _ago(float(r["ts"]), now), r["text"][:1500]))
    for ask in w.get("asks", [])[-6:]:
        if ask.get("answered"):
            continue
        waited = float(now) - float(ask.get("at") or now)
        out.append("Out with %s since %s: “%s”%s" % (
            AGENTS.get(ask["to"], ask["to"]), _ago(ask.get("at", now), now), ask["what"][:200],
            (" — no answer yet. Do not ask again: take a different step, hand it to someone else, or WORK "
             "DROPPED: why.") if waited > ASK_PATIENCE_S else " — while it works, take a step on something else."))
    return out
