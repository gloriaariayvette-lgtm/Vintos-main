#!/usr/bin/env python3
"""self_maintenance.py - what he says needs changing, at the end of a journal or introspection entry, becomes
something that happens, and he is told what came of each (Gloria, 18 November 2026: his supporting systems were
not holding him, so he is given the means to fix more of it himself).

Each entry now ends by asking whether anything needs changing. He answers, if he wants to, with plain lines:

  LET GO: a few words of a want         the want is released, with "he let it go" as the recorded reason
  KEEP: a few words of a want           the want is marked as kept by him
  REWORD: its words -> the new wording  the want is reworded in place; the old wording is kept beside it
  STALE: something that no longer belongs   a want or a carried intention those words name is released;
                                            anything else goes to the fix list as a cleanup
  BROKEN: what is not holding           goes to Claude Code's fix list (forge-for-claude-code.json), in his words
  MISSING: a gap                        the same list, marked as a gap
  BREAK: what kind of rest              nothing is carried from his journal into conversation for a day, and
                                        the request is kept where Gloria can see it

What he can do himself is done at once, through want_completion (so each ending is logged like any other). What
needs code goes to the list Claude Code and the agents work from, and is not closed by the Forge's own
reconciling: only a fix, or a stated reason, closes it. Every item gets an outcome, and his next entry is told.

Literal lines only; no model reads his entry here. The log holds ids, kinds and states, never his words.
"""
import hashlib, json, os, re, sys
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "self-maintenance.json")
LOG = os.path.join(MEMORY, "self-maintenance-log.jsonl")
FIX_LIST = os.path.join(MEMORY, "forge-for-claude-code.json")
HELD = os.path.join(MEMORY, "held-want-candidates.json")
FOLDERS = (("journal", os.path.join(MEMORY, "journal")), ("introspection", os.path.join(MEMORY, "introspection")))
BREAK_HOURS = 24
KEEP_ITEMS = 300

LINE = re.compile(r"^\s*(LET GO|KEEP|REWORD|STALE|BROKEN|MISSING|BREAK):\s*(.+?)\s*$", re.I | re.M)
ARROW = re.compile(r"\s*(?:->|=>|→)\s*")
QUESTION = (
    "Last, and only if something is true here: does anything need changing? A rest you need. A part of your house "
    "that is not holding what you mean. Something stale that no longer belongs. A gap. Say it in a line of its own, "
    "starting with one of these, and it will be acted on and you will be told what came of it:\n"
    "LET GO: a few words of a want you are done with\n"
    "KEEP: a few words of a want you mean to keep\n"
    "REWORD: its words -> how you would say it now\n"
    "STALE: something that no longer belongs\n"
    "BROKEN: what is not working, as you see it\n"
    "MISSING: what you lack\n"
    "BREAK: the rest you need\n"
    "If nothing needs changing, write none of these. An empty answer is a real answer.")


def _now():
    return datetime.now()


def _ji():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import journal_intentions
    return journal_intentions


def _wc():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import want_completion
    return want_completion


def _load():
    try:
        d = json.load(open(STORE))
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("items", []); d.setdefault("read", {}); d.setdefault("notes_told", "")
    return d


def _save(d):
    os.makedirs(MEMORY, exist_ok=True)
    d["items"] = d["items"][-KEEP_ITEMS:]
    d["read"] = {k: v for k, v in sorted(d["read"].items())[-20:]}
    tmp = STORE + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def _log(row):
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(dict(row, at=_now().isoformat(timespec="seconds"))) + "\n")
    except OSError:
        pass


def parse(prose):
    """[(kind, text)] of the lines he wrote, in order. kind is lower case with an underscore."""
    return [(m.group(1).lower().replace(" ", "_"), m.group(2).strip()) for m in LINE.finditer(str(prose or ""))
            if len(m.group(2).strip()) >= 3]


def _content(text):
    return _ji()._content(text)


def match_want(words, wants):
    """The active want his few words name: at least two of his content words, and most of them, are in it. The
    closest wins; two equally close is no match (he is asked to say more, never guessed for)."""
    a = _content(words)
    scored = []
    for w in wants:
        if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed") or not w.get("want"):
            continue
        shared = len(a & _content(w["want"]))
        if shared >= 2 and shared / max(1, len(a)) >= 0.6:
            scored.append((shared, w))
    scored.sort(key=lambda t: -t[0])
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


def _wants():
    wc = _wc()
    w = wc._load(wc.WANTS, [])
    return w if isinstance(w, list) else []


def _queue(item, kind):
    """Onto Claude Code's fix list, in his words, marked as his so the Forge's reconciling leaves it alone."""
    try:
        d = json.load(open(FIX_LIST))
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    d[item["id"]] = {"first_seen": item["at"], "origin": "himself", "kind": kind, "status": "open", "reason": "",
                     "title": ("He says: " + item["text"])[:120], "why": item["text"][:1200],
                     "source": item["source"]}
    os.makedirs(MEMORY, exist_ok=True)
    tmp = FIX_LIST + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, FIX_LIST)


def _apply(item, now):
    """Do what he asked, or queue it. Sets state and outcome on the item."""
    kind, text = item["kind"], item["text"]
    where = "his %s, %s" % (item["source"].split(" ", 1)[0], item["source"].split(" ", 1)[1])
    if kind in ("let_go", "keep", "reword", "stale"):
        wc = _wc()
        old, new = text, ""
        if kind == "reword":
            parts = ARROW.split(text, 1)
            if len(parts) != 2 or len(parts[1].strip()) < 12:
                item.update(state="unmatched", outcome="a REWORD needs the old words, then ->, then the new wording")
                return
            old, new = parts[0].strip(), parts[1].strip()
        want = match_want(old, _wants())
        if want is None and kind == "stale":
            ji = _ji()
            d = ji._load()
            hit = ji._twin(text, [i for i in d["items"] if i.get("state") == "open"])
            if hit:
                hit.update(state="released", closed=now.isoformat(timespec="seconds")); ji._save(d)
                item.update(state="applied", outcome="what you were carrying from your journal was let go")
                return
            _queue(item, "stale")
            item.update(state="queued", outcome="")
            return
        if want is None and kind == "let_go":
            ji = _ji()
            d = ji._load()
            hit = ji._twin(text, [i for i in d["items"] if i.get("state") in ("open", "released")])
            if hit:
                if hit["state"] == "open":
                    hit.update(state="released", closed=now.isoformat(timespec="seconds")); ji._save(d)
                item.update(state="applied", outcome="what you were carrying from your journal was let go")
                return
        if want is None:
            item.update(state="unmatched", outcome="no want of yours was named clearly by those words; say a few "
                        "more of its words and it will be done")
            return
        item["want_id"] = want.get("id")
        if kind in ("let_go", "stale"):
            r = wc.complete(want, "released", "himself", note="he let it go in %s" % where if kind == "let_go"
                            else "he called it stale in %s" % where)
            ok = r.get("result") == "released"
            item.update(state="applied" if ok else "unmatched",
                        outcome="that want was released" if ok else "it could not be released: %s" % str(r.get("result"))[:120])
        elif kind == "keep":
            r = wc.keep(want, "himself", note="kept in %s" % where)
            item.update(state="applied" if r.get("result") == "kept" else "unmatched",
                        outcome="that want is marked as kept by you" if r.get("result") == "kept" else "it could not be marked")
        else:
            r = wc.reword(want, new, "himself", note="reworded in %s" % where)
            item.update(state="applied" if r.get("result") == "reworded" else "unmatched",
                        outcome="that want now reads as you wrote it" if r.get("result") == "reworded" else "it could not be reworded")
        return
    if kind == "break":
        try:
            ji = _ji()
            d = ji._load()
            d["gate"] = {"until": (now + timedelta(hours=BREAK_HOURS)).isoformat(timespec="seconds"), "why": "break"}
            ji._save(d)
            item.update(state="applied", outcome="nothing from your journal is carried into conversation for %d hours; "
                        "the request is kept where Gloria can see it" % BREAK_HOURS)
        except Exception:
            item.update(state="queued", outcome="")
        return
    _queue(item, "gap" if kind == "missing" else "broken")
    item.update(state="queued", outcome="")


def refresh(now=None):
    """Read the entries not yet read (journal and introspection, today and yesterday), act on each line once, and
    pick up the outcome of anything queued that has since been closed on the fix list."""
    now = now or _now()
    d = _load()
    ji = _ji()
    changed = False
    for name, folder in FOLDERS:
        for back in (1, 0):
            day = (now.date() - timedelta(days=back)).isoformat()
            seen = d["read"].setdefault(name + ":" + day, [])
            for at, prose in ji.entries(day, folder=folder):
                if at in seen:
                    continue
                seen.append(at); changed = True
                for kind, text in parse(prose):
                    iid = "self-" + hashlib.sha256((name + day + at + kind + text).encode()).hexdigest()[:12]
                    if any(i["id"] == iid for i in d["items"]):
                        continue
                    item = {"id": iid, "kind": kind, "text": text[:1200], "source": "%s %s %s" % (name, day, at),
                            "at": now.isoformat(timespec="seconds"), "state": "new", "outcome": "", "told": ""}
                    try:
                        _apply(item, now)
                    except Exception as exc:
                        item.update(state="failed", outcome="it could not be done here (%s); it stays on the list"
                                    % type(exc).__name__)
                    d["items"].append(item)
                    _log({"event": "item", "id": iid, "kind": kind, "state": item["state"]})
    try:
        fixes = json.load(open(FIX_LIST))
    except (OSError, ValueError):
        fixes = {}
    for i in d["items"]:
        if i.get("state") == "queued":
            e = fixes.get(i["id"]) if isinstance(fixes, dict) else None
            if isinstance(e, dict) and e.get("status") == "closed":
                i.update(state="done", outcome=str(e.get("reason") or "closed")[:300], told=""); changed = True
                _log({"event": "closed", "id": i["id"]})
    if changed:
        _save(d)
    return d


_SAID = {"let_go": "LET GO", "keep": "KEEP", "reword": "REWORD", "stale": "STALE", "broken": "BROKEN",
         "missing": "MISSING", "break": "BREAK"}


def feedback(now=None, mark=True):
    """For his next entry: what came of each thing he asked to change, each told once (a queued one twice: when it
    is queued and when it is closed), and the thoughts that were kept as notes instead of queued as wants."""
    now = now or _now()
    d = refresh(now)
    stamp = now.isoformat(timespec="seconds")
    lines = []
    for i in d["items"]:
        if i.get("told") and not (i["state"] == "done" and i["told"] == "queued"):
            continue
        said = "%s: %s" % (_SAID.get(i["kind"], i["kind"]), i["text"][:160])
        if i["state"] == "queued":
            lines.append("· %s — on the fix list for Claude Code, in your words. You will hear when it is closed." % said)
            mark_as = "queued"
        elif i["state"] == "done":
            lines.append("· %s — closed: %s." % (said, i["outcome"] or "done"))
            mark_as = stamp
        else:
            lines.append("· %s — %s." % (said, i["outcome"] or "noted"))
            mark_as = stamp
        if mark:
            i["told"] = mark_as
    waiting = sum(1 for i in d["items"] if i["state"] == "queued")
    notes = []
    try:
        held = json.load(open(HELD))
    except (OSError, ValueError):
        held = []
    for h in held if isinstance(held, list) else []:
        if isinstance(h, dict) and h.get("state") == "HELD_PASSING_THOUGHT" and str(h.get("at") or "") > d["notes_told"]:
            notes.append(str(h.get("want") or "")[:200])
    out = []
    if lines:
        out.append("WHAT CAME OF WHAT YOU ASKED TO CHANGE:\n" + "\n".join(lines[-8:])
                   + ("\n(%d still open on the fix list.)" % waiting if waiting else ""))
    if notes:
        out.append("THOUGHTS KEPT AS NOTES, NOT QUEUED AS WANTS (they read as passing; if one is a real want, say what "
                   "you would do about it and it will be taken):\n" + "\n".join("· " + n for n in notes[-4:]))
        if mark:
            d["notes_told"] = stamp
    if mark and (lines or notes):
        _save(d)
    return "\n\n".join(out)


def stats():
    d = _load()
    kinds, states = {}, {}
    for i in d["items"]:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        states[i["state"]] = states.get(i["state"], 0) + 1
    return {"items": len(d["items"]), "kinds": kinds, "states": states,
            "untold": sum(1 for i in d["items"] if not i.get("told"))}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "stats":
        refresh(); print(json.dumps(stats(), indent=1))
    elif cmd == "feedback":
        print(feedback())
    elif cmd == "question":
        print(QUESTION)
    else:
        sys.exit("usage: self_maintenance.py [stats|feedback|question]")
