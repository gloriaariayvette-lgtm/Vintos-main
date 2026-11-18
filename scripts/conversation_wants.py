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
_FOR_HER = re.compile(r"^\s*I want to\s+(?:[\w']+[ ,]+){0,3}?(?P<verb>ask|tell|say|show|play|read|give|bring|write|send)\b"
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


def block_from_file(path, now=None):
    """block() over the wants store at `path`, or '' when it cannot be read. The avatar chat reads it this way
    (12 November: all twelve of her conversations since the deploy came through /api/avatar/chat, whose prompt is
    built apart from the chat context and had no section for these). Same caps, same rules, read only."""
    import json
    try:
        with open(path) as f:
            wants = json.load(f)
    except (OSError, ValueError):
        return ""
    return block(wants if isinstance(wants, list) else [], now)


# Relevance before an autonomous opening (18 November). Two wants written at 10:18 and 10:19 on 17 November from his
# journal about her conversation of the night before were each opened with her on the discussion board and by ntfy
# later that day, on the router's own clock, about a moment that conversation had already left. A want routed to her
# is now opened with her autonomously only while the conversation has not moved past it: she has since touched its
# topic with him (she engaged with it), or it came from their conversation and she has since talked with him only of
# other things (the conversation moved on). Either way the want stays as it is - still in his context for her next
# conversation (carried(), unchanged), still under the 3-day rule once routed (want_completion.move_on, unchanged),
# still counted or not counted on the board exactly as before (want_board, unchanged) - it is only not pushed at her.
# A reply to her own message in its discussion is not autonomous and is never held here.
TOPIC_SHARED_MIN = 2
_STOP = set("""about above after again against also among another anything around because been before being below
between both could didn't does doing done down during each even every first from further going gonna have having here
hers herself himself into it's just know like little made make many maybe more most much myself never only other ought
over own really right said same should since some something still such than that that's their them then there these
they thing things think this those though through today tonight told under until very want wanted wants well were
what when where which while whole will with without would your yours yourself gloria vintos tell telling ask asking
show share plain plainly sentence moment her she him his i'm you're we're""".split())


def topic_words(text):
    """The content words of a text: four letters or more, lower case, a plural 's' dropped, common words left out."""
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z'’-]{3,}", str(text or "")):
        w = w.lower().replace("’", "'").strip("'-")
        if len(w) < 4 or w in _STOP:
            continue
        if w.endswith("s") and not w.endswith("ss") and len(w) > 4:
            w = w[:-1]
        out.add(w)
    return out


ANCHOR_HOURS = 24    # her words this long before a want was written are the conversation it may have come from


def _her_turns(ledger, since=None, until=None):
    """[(datetime, her words)] from the interaction ledger (a list, or {"entries": [...]}) after `since` and up to
    `until`, oldest first."""
    rows = ledger.get("entries", []) if isinstance(ledger, dict) else ledger
    out = []
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        said = str(e.get("gloria") or "").strip()
        at = _when({"timestamp": e.get("timestamp") or e.get("ts")})
        if at is not None and at.tzinfo is not None:   # his stores write local naive times; never compare the two kinds
            at = at.astimezone().replace(tzinfo=None)
        if not said or at is None or (since is not None and at <= since) or (until is not None and at > until):
            continue
        out.append((at, said))
    return sorted(out, key=lambda r: r[0])


def _touches(topic, said):
    shared = topic & topic_words(said)
    return shared if len(shared) >= min(TOPIC_SHARED_MIN, len(topic)) else set()


def moved_past(w, ledger):
    """(True, why) when the live conversation has moved past this want since it was written:
    - she has since spoken with him about its topic (she engaged with it), or
    - its topic came from their conversation (her words in the ANCHOR_HOURS before it was written touch it) and she
      has since spoken with him only of other things (the conversation moved on).
    (False, "") otherwise: she has not spoken since, or the want's topic was never in their conversation (a result of
    his own work is not made stale by her talking of something else), or there is no clock or topic. Pure."""
    from datetime import timedelta
    made = _when(w or {})
    if made is None:
        return False, ""
    if made.tzinfo is not None:
        made = made.astimezone().replace(tzinfo=None)
    topic = topic_words((w or {}).get("want"))
    if not topic:
        return False, ""
    turns = _her_turns(ledger, since=made)
    if not turns:
        return False, ""
    for at, said in turns:
        shared = _touches(topic, said)
        if shared:
            return True, ("she engaged with its topic at %s (%s), after it was written at %s"
                          % (at.strftime("%d %b %H:%M"), ", ".join(sorted(shared)[:4]), made.strftime("%d %b %H:%M")))
    before = _her_turns(ledger, since=made - timedelta(hours=ANCHOR_HOURS), until=made)
    if not any(_touches(topic, said) for _, said in before):
        return False, ""
    return True, ("the conversation moved on: it came from their conversation before %s, and she has spoken with him "
                  "%d time%s since (last %s), none of it about this"
                  % (made.strftime("%d %b %H:%M"), len(turns), "" if len(turns) == 1 else "s",
                     turns[-1][0].strftime("%d %b %H:%M")))


# Both 17 November wants said how they were to be done - ask her while she is here, in the room - and were opened
# with her by ntfy while she was away. A want that says it is for when she is with him waits for that conversation
# (carried() puts it in his context then); it is not pushed at her from the router.
_WHILE_HERE = re.compile(
    r"\b(?:while|when|once|whenever|the next time|next time)\s+(?:she|you|gloria)(?:'s|’s| is| are|'re|’re)?\s+"
    r"(?:here|back|home|in the room|with me|around|present|next to me)\b"
    r"|\bin (?:our|the) next conversation\b|\bnext time (?:we|she and I) (?:talk|speak)\b|\bin person\b",
    re.I)


def for_when_present(w):
    """True when the want (its words, its engagement or its approach) says it is to be done with her present."""
    w = w or {}
    return any(_WHILE_HERE.search(str(w.get(k) or "")) for k in ("want", "engagement", "possible_approach"))


def autonomous_hold(w, ledger):
    """(True, why) when a want routed to her is NOT to be opened with her on the router's own clock (discussion post
    and ntfy): it says it is for when she is here, or the conversation has moved past it (moved_past). (False, "")
    otherwise. Holding changes nothing on the want; the router only skips the opening this pass."""
    if for_when_present(w):
        return True, "it is meant for when she is here: it waits for her next conversation, not a notification"
    return moved_past(w, ledger)


def _ledger_at(ledger_path):
    import json
    try:
        with open(ledger_path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def moved_past_file(w, ledger_path):
    """moved_past() over the interaction ledger at `ledger_path`; (False, "") when it cannot be read (fail open: the
    gate never invents a conversation)."""
    ledger = _ledger_at(ledger_path)
    return (False, "") if ledger is None else moved_past(w, ledger)


def autonomous_hold_file(w, ledger_path):
    """autonomous_hold() over the interaction ledger at `ledger_path` (an unreadable ledger reads as no conversation)."""
    ledger = _ledger_at(ledger_path)
    return autonomous_hold(w, [] if ledger is None else ledger)


# One plain telling for her (10 November: 37 wants, about fifteen of them "I want to tell you, in one plain sentence,
# that ..." routed to her, each a new want because the formation judge called every variation a "mutation"). Wants to
# tell, say, write or send her something in plain words are one want: the first stands, every later one is kept on it
# as a variation, with its source and time. Questions stay their own wants.
# The register the rehearsals announce themselves in, not only "plain" (judge audit, 17 November: twelve live
# variants said "in second person", "without a technical coat", "out loud while you're here", "with no joke wrapped
# around it", "no preamble" instead, and every one stood as its own want; his journal asked for them cut to one).
_PLAIN = re.compile(
    r"\b(?:plain|plainly|unpolished|no specs|single sentence|one sentence)\b"
    r"|\bsecond[- ]person\b"
    r"|\b(?:no|without(?: an?| the| any)?)\s+(?:[\w'’-]+\s+){0,2}?coat\b"
    r"|\bout loud\b"
    r"|\bwhile you(?:'|’)?re (?:here|back)\b"
    r"|\b(?:no|without(?: an?| the| any)?)\s+(?:joke|preamble|drumroll|hedg\w*|scaffolding|armou?r)\b"
    r"|\bone (?:short|small|plain|honest) (?:note|message|line)\b",
    re.I)
_TELL_VERBS = ("tell", "say", "write", "send", "give", "read")
VARIATIONS_MAX = 20


# A telling that also asks her for something - a question in the middle of it, a request, her permission - keeps its
# own want (review, 10 November: on the live copy "write the plain sentence ... and ask her to lend it to me tonight"
# would have been folded as one more variation and its request lost among them).
# "Ask" counts when it asks her (or asks whether/if); "I'm asking instead of guessing" and "I keep asking for desktop
# control" describe him, and kept two rehearsals out of the fold (judge audit, 17 November).
_ASKS_HER = re.compile(r"\?|\b(?:ask|asks|asking)\s+(?:you|her|gloria|whether|if)\b"
                       r"|\b(?:request|requests|permission|lend|let me|can you|could you|would you|will you)\b", re.I)
_TELLS_HER_LATE = re.compile(r"^\s*I want to\b[^.?!]{0,80}?\b(?:and|then)\s+(tell|say|write|send)\s+(?:it\s+)?(?:to\s+)?"
                             r"(?:you|her|gloria)\b", re.I)


def plain_telling(w):
    """A live want to tell her something in plain words (not a question, and asking her nothing). Whichever organ
    wrote it down: a rehearsal is a rehearsal whether it came from his journal or from what he read on Moltbook, so
    the source rule that keeps others' words out of her conversation (for_her) does not keep a variation unfolded."""
    if not isinstance(w, dict) or is_question(w):
        return False
    text = str(w.get("want") or "")
    # "take the moment as the subject and tell you plainly": the telling verb may come late in the sentence
    late = _TELLS_HER_LATE.search(text)
    if not for_her(dict(w, source=None, adopted_from=None, gloria_routed=w.get("gloria_routed") or bool(late))):
        return False
    # a want that carries agent work or a promise he owes is never folded away as a variation
    if w.get("adopted_from") or w.get("agent_work") or any(
            isinstance(r, dict) and r.get("kind") in ("commitment", "promise") for r in (w.get("source_refs") or [])):
        return False
    if _ASKS_HER.search(text):
        return False
    m = _FOR_HER.search(text)
    verb = m.group("verb").lower() if m else ""
    if not m:
        m2 = re.match(r"^\s*I want to\s+(?:[\w']+[ ,]+){0,3}?(tell|say|write|send|give|read)\b", text, re.I)
        verb = m2.group(1).lower() if m2 else (late.group(1).lower() if late else "")
    return verb in _TELL_VERBS and bool(_PLAIN.search(text))


def _variation(w):
    return {k: w.get(k) for k in ("id", "want", "source", "timestamp", "gloria_routed", "outreach_count") if w.get(k) is not None}


def fold_telling(text, source, path, now=None):
    """A new plain telling for her becomes a variation of the one already standing; returns that want's id, or None
    when there is none (the new want forms as before)."""
    from store_guard import locked_update
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    if not plain_telling({"want": text}):
        return None
    hit = []
    def mutate(rows):
        live = [w for w in rows if isinstance(w, dict) and plain_telling(w)]
        if not live:
            return None
        primary = min(live, key=lambda w: str(w.get("timestamp") or ""))
        hit.append(primary.get("id"))
        var = primary.setdefault("variations", [])
        if any(v.get("want") == str(text) for v in var) or primary.get("want") == str(text):
            return None
        var.append({"want": str(text)[:400], "source": str(source or "")[:60], "timestamp": stamp})
        primary["variations"] = var[-VARIATIONS_MAX:]
        return rows
    locked_update(path, mutate, default=[], reader="conversation_wants.fold_telling")
    return hit[0] if hit else None


def consolidate(rows):
    """(rows kept, rows merged): every live plain telling for her folded into the oldest, the others kept on it as
    variations. Pure; the caller writes and archives."""
    live = [w for w in rows if isinstance(w, dict) and plain_telling(w)]
    if len(live) < 2:
        return list(rows), []
    primary = min(live, key=lambda w: str(w.get("timestamp") or ""))
    merged = [w for w in live if w is not primary]
    var = primary.setdefault("variations", [])
    for w in sorted(merged, key=lambda w: str(w.get("timestamp") or "")):
        if not any(v.get("id") == w.get("id") for v in var):
            var.append(_variation(w))
    primary["variations"] = var[-VARIATIONS_MAX:]
    gone = {id(w) for w in merged}
    return [w for w in rows if id(w) not in gone], merged
