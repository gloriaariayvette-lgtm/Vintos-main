"""conversation_wants.py - what he means to ask or tell her himself, carried into his next conversation with her.

A want to ask her something when she is back can only happen with her. The chat context
always had a note for these (server.py, "[THINGS YOU CURRENTLY WANT]"), but it listed only the newest five wants and
flagged a want only when it said "ask gloria" or "tell gloria"; his wants say "you" and "her", so from at least
November the note never fired, and a question written before five newer wants was not in his context at all.

Here a want is for her when its plan has a step only she can answer (capability gloria/you, still pending), when it
was routed to her, or when it says plainly that he wants to ask, tell, show or play her something. Such wants stay in
his context until they are fulfilled, dismissed or WINDOW_DAYS old, however long she is away and whether or not the
agents' room is paused (Gloria, 10 November: "the kind of question that has to surface in our next conversation").
Read only: nothing here writes a store or calls a model."""
import re
from datetime import datetime

WINDOW_DAYS = 14
LIMIT = 6              # wants for her in his context at once
LIMIT_QUESTIONS = 4    # of which questions, the longest waiting first; then things to tell her, the newest first
HER_CAPABILITIES = ("gloria", "you")
# Wants read out of someone else's words are not carried into her conversation as his (review, 10 November): his
# letters (and the promises adopted from them) and the posts he reads on Moltbook.
NOT_HIS_OWN = ("email", "letter-promise", "moltbook")
_FOR_HER = re.compile(r"^\s*I want to\s+(?:[\w']+[ ,]+){0,3}?(?P<verb>ask|tell|say|show|play|read|give|bring)\b"
                      r"[^.?!]{0,40}?\b(?:you|her|gloria)\b", re.I)


def _when(w):
    try:
        return datetime.fromisoformat(str(w.get("timestamp") or "")[:26])
    except ValueError:
        return None


def _her_step(w):
    steps = w.get("steps") if isinstance(w.get("steps"), list) else []
    return any(isinstance(s, dict) and str(s.get("capability") or "").lower() in HER_CAPABILITIES
               and s.get("status") != "completed" for s in steps)


def for_her(w):
    """A live want that only she can complete: to ask, tell, show or play her something himself."""
    if not isinstance(w, dict) or not isinstance(w.get("want"), str):
        return False
    if any(w.get(k) for k in ("fulfilled", "dismissed", "aged_out", "_delete")):
        return False
    if w.get("source") in NOT_HIS_OWN or str(w.get("adopted_from") or "").startswith("EC-"):
        return False
    return bool(_her_step(w) or w.get("gloria_routed") or _FOR_HER.search(w["want"]))


def is_question(w):
    """A want to ask her something (not "ask nothing" inside some other want)."""
    m = _FOR_HER.search(str(w.get("want") or ""))
    return bool(m and m.group("verb").lower() == "ask") or str(w.get("want") or "").rstrip().endswith("?")


def carried(wants, now=None, window_days=WINDOW_DAYS, limit=LIMIT, limit_questions=LIMIT_QUESTIONS):
    """The wants for her still inside the window. Questions first, the longest waiting first, since a question is
    what most needs her and is easiest to lose among the many things he wants to tell her (27 of his 39 wants on
    10 November were to tell or ask her something); then things to tell her, the newest first."""
    now = now or datetime.now()
    asks, tells = [], []
    for w in wants or []:
        if not for_her(w):
            continue
        at = _when(w)
        if at is None or (now - at).total_seconds() > window_days * 86400:
            continue
        (asks if is_question(w) else tells).append((at, w))
    asks = [w for _, w in sorted(asks, key=lambda r: r[0])][:limit_questions]
    tells = [w for _, w in sorted(tells, key=lambda r: r[0], reverse=True)]
    return (asks + tells)[:limit]


def block(wants, now=None):
    """The chat-context section, or '' when nothing is waiting for her."""
    rows = carried(wants, now)
    if not rows:
        return ""
    lines = ["- (since %s) %s" % (_when(w).strftime("%d %b %H:%M"), w["want"][:300]) for w in rows]
    return ("[FOR HER, WHEN SHE IS HERE - things you meant to ask or tell her yourself. They have waited for her; "
            "this conversation is the place for them. If the moment holds one, ask or say it in your own words.]\n"
            + "\n".join(lines))
