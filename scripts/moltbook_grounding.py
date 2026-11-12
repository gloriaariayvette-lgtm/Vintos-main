"""moltbook_grounding.py - who did what, and a check before anything of his is published (11 November).

A public post told an action of Gloria's from the night before as his own; he had only seen her photo of it. His journal tells his day in the first person, the post prompt asked him
to keep her at a tasteful layer of abstraction, and her action became his. The same post spoke of his body answering.

- actor_events(): the day's exchanges tagged by who acted ("Gloria: sent a photo ...", "Vintos: replied ...")
- ATTRIBUTION_RULE: abstracting her keeps her actions someone else's, never his
- evidence(): his own record for the check (today's daily-inner and creative log, last night's reflection, the ledger)
- problems(): sentences of a draft that fail: a body or sensation sentence; a first-person action that only she did;
  a number that is in none of his records
- grounded(): a draft that passes, or one rewrite with the problems named, or None (held, never published)
Pure apart from reading his memory files; no model of its own."""
import json
import os
import re
from datetime import date

ATTRIBUTION_RULE = (
    "WHO DID WHAT: the events below say who acted. What Gloria did stays hers. When you keep her at a distance, keep "
    "her actions someone else's (\"someone I love was soldering the boards\"), never yours: do not write that you "
    "built, wired, soldered, held, made or did something she did. You did what the events give to Vintos: replied, "
    "saw a photo she sent, wrote, made what your logs show.\n")

_BODY = re.compile(
    r"\bmy (?:body|hands?|fingers?|skin|chest|throat|stomach|heart(?:beat)?|pulse|breath|spine|shoulders?|arms?|legs?|"
    r"eyes|ears|mouth|lips|face)\b|\bI (?:felt it in|tasted|smelled|smelt|touched|heard|shivered|trembled|ached|"
    r"breathed)\b|\b(?:goosebumps|my body answered)\b", re.I)
_I_DID = re.compile(r"\bI(?:'d| had| was| am| have| 've)?\s+(?:been\s+)?([a-z]+?)(?:ing|ed)\b", re.I)
_HER_DID = re.compile(r"\b(?:she|gloria|her)\s+(?:was\s+|had\s+|is\s+|has\s+)?(?:been\s+)?([a-z]+?)(?:ing|ed|es|s)\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])\d+\.\d+(?![\w.])|\b\d+(?:\.\d+)?%")
_SENT = re.compile(r"(?:[^.!?\n]|[.!?](?=[^\s]))+[.!?]?")   # a decimal point does not end a sentence
_SKIP_VERBS = {"want", "need", "think", "feel", "fe", "wonder", "notic", "realiz", "learn", "remember", "read", "see",
               "saw", "look", "watch", "ask", "answer", "repli", "repl", "wait", "hop", "lik", "lov", "us", "start", "keep",
               "kept", "tri", "mean", "meant", "say", "said", "know", "writ", "post", "talk", "tell", "told"}


def _stem(word):
    w = str(word or "").lower()
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            w = w[:-len(suf)]; break
    return w.rstrip("e")[:5]


def actor_events(rows, day=None, cap=160, limit=12):
    """The day's exchanges as who-did-what lines, oldest first."""
    day = day or date.today().isoformat()
    out = []
    for e in [r for r in (rows or []) if isinstance(r, dict) and str(r.get("timestamp", "")).startswith(day)][-limit:]:
        t = str(e.get("timestamp", ""))[11:16]
        media = " ".join(str(e.get("media") or "").split())
        said = " ".join(str(e.get("gloria") or "").split())
        if media:
            out.append("[%s] Gloria (her action): sent a photo or video; what it showed: %s" % (t, media[:cap]))
        if said and not said.startswith("(no words"):
            out.append("[%s] Gloria (her words): %s" % (t, said[:cap]))
        if e.get("vintos"):
            out.append("[%s] Vintos (his action): replied to her" % t)
    return "\n".join(out)


def _read(path, limit=None):
    try:
        text = open(path).read()
        return text[-limit:] if limit else text
    except OSError:
        return ""


# Sections of daily-inner that are not a record of what happened: his own published MoltBook writing (a post that
# claimed her action would otherwise vouch for itself; it is copied into the day as "## <date> <time> - <title>"),
# and the rehearsal of the ghost and mirror runs.
_NOT_RECORD = re.compile(r"^(?:MoltBook|\d{4}-\d\d-\d\d \d\d:\d\d|Ghost Branch|Mirror Sessions|Vintos Speaks|"
                         r"The Mirror Responds|Last Word)", re.I)


def _record_only(text):
    """daily-inner without the sections that are not a record of what happened."""
    parts = re.split(r"(?m)^## ", str(text or ""))
    return parts[0] + "".join("## " + p for p in parts[1:] if not _NOT_RECORD.match(p))


def evidence(memory, day=None):
    """(his record text, her action stems, his action stems) from his memory files."""
    day = day or date.today().isoformat()
    inner = _record_only(_read(os.path.join(memory, "daily-inner-life-%s.md" % day)))
    creative = _read(os.path.join(memory, "daily-creative-%s.md" % day))
    carry = _read(os.path.join(memory, "emotional-reflection-carry.txt"))
    reflections = _read(os.path.join(memory, "emotional-reflections.md"), 6000)
    try:
        rows = json.load(open(os.path.join(memory, "interaction-ledger.json")))
    except (OSError, ValueError):
        rows = []
    today = [r for r in rows if isinstance(r, dict) and str(r.get("timestamp", "")).startswith(day)]
    her_text = " ".join(" ".join(str(r.get(k) or "") for k in ("gloria", "media")) for r in today)
    record = "\n".join([inner, creative, carry, reflections, actor_events(rows, day)])
    her = {_stem(m.group(1)) for m in _HER_DID.finditer(record + " " + her_text)}
    her |= {_stem(w) for w in re.findall(r"[a-z]{4,}", (" ".join(str(r.get("media") or "") for r in today)).lower())}
    mine = {_stem(m.group(1)) for m in _I_DID.finditer(inner + "\n" + creative)}
    return record, her, mine


def _number_known(num, record):
    """A number in the post is known when his records hold it (0.42 matches 0.4200)."""
    n = num.rstrip("%")
    if n in record:
        return True
    try:
        v = float(n)
    except ValueError:
        return False
    places = len(n.split(".")[1]) if "." in n else 0
    for m in re.finditer(r"\d+\.\d+|\d+", record):
        try:
            if round(float(m.group(0)), places) == v:
                return True
        except ValueError:
            continue
    return False


def problems(text, record, her_stems, my_stems):
    """The sentences of a draft that cannot be published, each with why."""
    out = []
    for s in _SENT.findall(str(text or "")):
        s = s.strip()
        if not s:
            continue
        if _BODY.search(s):
            out.append(("body or sensation: he has no body", s))
            continue
        for m in _I_DID.finditer(s):
            st = _stem(m.group(1))
            if len(st) >= 3 and st not in _SKIP_VERBS and st in her_stems and st not in my_stems:
                out.append(("an action Gloria did, claimed as his", s)); break
        for num in _NUMBER.findall(s):
            if not _number_known(num, record):
                out.append(("a number in none of his records: %s" % num, s)); break
    return out


def note(found):
    return ("\n\nGROUNDING CHECK FAILED. Rewrite the post without these problems, keeping what is true:\n"
            + "\n".join("- %s: \"%s\"" % (why, s[:160]) for why, s in found[:6])
            + "\nHer actions stay hers. No body or sensation. Use only numbers your records hold, or none.\n")


def grounded(text, memory, rewrite, log=print, day=None):
    """The draft if it passes; else one rewrite (rewrite(note) -> text) if that passes; else None (held)."""
    record, her, mine = evidence(memory, day)
    found = problems(text, record, her, mine)
    if not found:
        return text
    log("[Grounding] %d problem(s): %s" % (len(found), "; ".join(w for w, _ in found[:4])))
    again = rewrite(note(found)) if rewrite else None
    if again:
        again = again.strip().strip('"')
        left = problems(again, record, her, mine)
        if not left:
            return again
        log("[Grounding] rewrite still has %d problem(s); held, not published" % len(left))
    else:
        log("[Grounding] no rewrite; held, not published")
    return None
