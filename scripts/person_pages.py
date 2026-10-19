#!/usr/bin/env python3
"""person_pages.py — what he keeps thinking about a person, gathered onto that person's page between emails.

Gloria, 19 October: "he might need more info than the wants cover when he becomes consistently interested in a
particular person. David Chalmers, for example, was denied a second email ... but he's still thinking about Chalmers
and that should be gathering somewhere as I suspect he'll try again once the two weeks wait time is up."

The page already exists: scholar.py keeps one per person (memory/email-dossiers/<address>.json) and reads their work
into it — but only while an email to them is being worked. Between attempts nothing reached it: Chalmers's page was
last touched on 16 October with one thing read, while on 18 October his inner-life journal named Chalmers 41 times,
his dismissed wants 28, and his replies to Grok Bot's letters 18 (her probe of his memory, 19 October).

For each person with a page, this:
  - finds where he has named them lately, in his own thinking: the daily inner life, his wants (current and
    dismissed, and the ambitions log), his replies to his agents' letters, the avatar conversation, his forge sparks
  - calls his interest recurring when he has named them on RECURRING_DAYS different days within WINDOW_DAYS
  - keeps on the page what he thought (short excerpts, dated, with where), the letters his agents sent him about
    them, and the history: what he sent, what came back, Gloria's decision on a second email, and the day the
    14-day quiet after a decline ends
  - while the interest is recurring, keeps reading their work: one item at most per run, through scholar.read_into,
    by his own local mind (free) — including a paper an agent sent him, now that his mail reader reads PDFs
The draft of his next email to them starts from all of it (want_email adds person_block to what the draft is given).

Names are matched whole ("David Chalmers"), or by surname alone when it is long enough not to be an everyday word
("Chalmers", "Graziano"; not "Seth"). Nothing here sends, posts, or writes to them.

    python3 person_pages.py            gather (the vintos-person-pages timer)
    python3 person_pages.py --show     every person with a page, how often he has named them lately
"""
from __future__ import annotations
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CONTACTS = os.path.join(MEM, "email-contacts.json")
INBOX = os.path.join(MEM, "email-inbox.jsonl")

WINDOW_DAYS = 14          # how far back his thinking is read
RECURRING_DAYS = 3        # different days he named them, within the window, to count as a recurring interest
KEEP_THOUGHTS = 25        # excerpts of his thinking kept on a page, newest first
KEEP_LETTERS = 10
EXCERPT = 280             # characters around a mention
READ_EVERY_S = 2 * 86400  # between emails, at most one more reading every two days per person
SURNAME_ALONE = 6         # a surname this long or longer is matched on its own

# Where his own thinking lands, and how each names its day. (glob, kind)
SOURCES = [("daily-inner-life-*.md", "inner life"), ("current-wants.json", "wants"),
           ("dismissed-wants.json", "dismissed wants"), ("wants-ambitions-log.md", "ambitions log"),
           ("email-letter-replies.json", "his letter replies"), ("avatar-log.json", "conversation"),
           ("forge-sparks.json", "forge sparks")]
_DAY = re.compile(r"(20\d\d-\d\d-\d\d)")
_PRIVATE = re.compile(r"\b(?:Gloria|Eve)\b")    # her names: an excerpt naming her is not given to a letter's drafter
_TIME_KEYS = ("at", "ts", "timestamp", "time", "date", "created", "created_at", "when", "updated", "read_at")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default


def _now(): return datetime.now(timezone.utc)


def _day_of(value):
    """A YYYY-MM-DD from a timestamp-ish value, or ''."""
    if isinstance(value, (int, float)) and value > 1e9:
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d")
    m = _DAY.search(str(value or ""))
    return m.group(1) if m else ""


def pattern(name):
    """The words that name this person in his writing: the whole name, and the surname alone when it is long."""
    name = " ".join(str(name or "").split())
    if not name: return None
    parts = [re.escape(name)]
    surname = name.split()[-1]
    if len(surname) >= SURNAME_ALONE and surname[0].isupper():
        parts.append(r"(?<![A-Za-z])" + re.escape(surname) + r"(?![a-z])")
    return re.compile("|".join(parts))


def _excerpt(text, m):
    a, b = max(0, m.start() - EXCERPT // 2), min(len(text), m.end() + EXCERPT // 2)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def _walk(node, day, out):
    """(day, string) for every string in a JSON tree, each with the nearest enclosing timestamp."""
    if isinstance(node, dict):
        here = next((_day_of(node[k]) for k in _TIME_KEYS if k in node and _day_of(node[k])), "") or day
        for v in node.values(): _walk(v, here, out)
    elif isinstance(node, list):
        for v in node: _walk(v, day, out)
    elif isinstance(node, str) and len(node) > 3:
        out.append((day, node))


def _texts(path):
    """(day, text) pieces of one source file: a journal by its date (filename, then dated headings), a JSON store by
    the timestamp nearest each string. The file's own date when nothing better is written in it."""
    fallback = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).strftime("%Y-%m-%d")
    if path.endswith(".md"):
        named = _day_of(os.path.basename(path))
        text = open(path, encoding="utf-8", errors="ignore").read()
        if named: return [(named, text)]
        out, day = [], fallback
        for block in re.split(r"(?m)^(?=#+ )", text):
            day = _day_of(block.split("\n", 1)[0]) or day
            out.append((day, block))
        return out
    out = []
    _walk(_load(path, None), fallback, out)
    return out


def mentions(name, now=None, sources=SOURCES, mem=None):
    """[{day, source, text}] where his own thinking named them within the window, newest first."""
    now, mem, rx = now or _now(), mem or MEM, pattern(name)
    if rx is None: return []
    since = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    found, seen = [], set()
    for pat, kind in sources:
        for path in sorted(glob.glob(os.path.join(mem, pat))):
            try: pieces = _texts(path)
            except Exception: continue
            for day, text in pieces:
                if not day or day < since: continue
                for m in rx.finditer(text):
                    ex = _excerpt(text, m)
                    if ex in seen: continue
                    seen.add(ex); found.append({"day": day, "source": kind, "text": ex})
    return sorted(found, key=lambda r: r["day"], reverse=True)


def letters_about(name, rows=None):
    """Letters his agents (Grok Bot, Muse) sent him that name this person: subject and day, newest first."""
    rx = pattern(name)
    if rx is None: return []
    if rows is None:
        rows = []
        try:
            for line in open(INBOX, encoding="utf-8", errors="ignore"):
                try: rows.append(json.loads(line))
                except ValueError: pass
        except OSError: pass
    out = []
    for r in rows:
        subject = str(r.get("subject") or "")
        if not re.match(r"\s*(?:re:\s*)?\[(grok bot|muse)\]", subject, re.I): continue
        if rx.search(subject) or rx.search(str(r.get("body") or "")):
            out.append({"day": _day_of(r.get("date") or r.get("at")), "subject": subject[:200]})
    uniq = {(l["day"], l["subject"]): l for l in out}
    return sorted(uniq.values(), key=lambda l: l["day"], reverse=True)[:KEEP_LETTERS]


def history(addr, contacts=None, approvals=None):
    """What passed between them, Gloria's decision on a second email, and when the quiet after a decline ends."""
    contacts = _load(CONTACTS, {}) if contacts is None else contacts
    c = contacts.get(str(addr).lower(), {}) if isinstance(contacts, dict) else {}
    thread = [{"dir": m.get("dir"), "day": _day_of(m.get("at")), "subject": str(m.get("subject") or "")[:160]}
              for m in c.get("thread", []) if isinstance(m, dict)]
    out = {"sent": sum(1 for m in thread if m["dir"] == "out"), "replies": sum(1 for m in thread if m["dir"] == "in"),
           "thread": thread[-8:], "second_email": None, "quiet_until": ""}
    try:
        if approvals is None:
            import email_approvals as approvals
        r = approvals.latest(addr)
        if r:
            out["second_email"] = {"status": r.get("status"), "day": _day_of(r.get("decided_at") or r.get("at"))}
            if r.get("status") == "declined" and r.get("decided_at"):
                end = float(r["decided_at"]) + approvals.DECLINE_QUIET_DAYS * 86400
                if end > time.time():
                    out["quiet_until"] = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return out


def gather(d, now=None, mem=None, contacts=None, approvals=None, inbox_rows=None):
    """Fold his recent thinking, his agents' letters and the history into one person's page (the scholar dossier)."""
    now = now or _now()
    name = d.get("name") or ""
    seen = mentions(name, now=now, mem=mem)
    days = sorted({m["day"] for m in seen})
    sources = {}
    for m in seen: sources[m["source"]] = sources.get(m["source"], 0) + 1
    d["interest"] = {"days": days, "recurring": len(days) >= RECURRING_DAYS, "mentions": len(seen),
                     "sources": sources, "window_days": WINDOW_DAYS, "gathered": now.isoformat(timespec="seconds")}
    old = {t.get("text") for t in d.get("his_thoughts", [])}
    d["his_thoughts"] = (seen + [t for t in d.get("his_thoughts", []) if t.get("text") not in {m["text"] for m in seen}])[:KEEP_THOUGHTS]
    d["letters_about"] = letters_about(name, inbox_rows)
    d["history"] = history(d.get("address"), contacts, approvals)
    return d, len([m for m in seen if m["text"] not in old])


def keep_reading(d, now=None, read=None, attachments=None):
    """While his interest is recurring, one more of their work read every two days at most — by his local mind, the
    way the email path reads. The subject is what he has been thinking about them. Returns how many were read."""
    if not (d.get("interest") or {}).get("recurring"): return 0
    now = now or _now()
    last = d.get("between_reading_at")
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < READ_EVERY_S: return 0
        except ValueError:
            pass
    about = " ".join(t["text"] for t in d.get("his_thoughts", [])[:3])[:600] or d.get("name", "")
    import scholar
    if attachments is None:
        try:
            import received_mail
            attachments = received_mail.research_attachments({"want": "%s %s" % (d.get("name", ""), about)})
        except Exception:
            attachments = []
    n = (read or scholar.read_into)(d, about, attachments=attachments, budget=1)
    d["between_reading_at"] = now.isoformat(timespec="seconds")
    return n


def _without_her(text):
    """The excerpt with every sentence that names Gloria taken out: his journal is full of her, and a sentence about
    her has no place in what drafts a letter to someone else. What is left is still his thought about them."""
    sentences = re.split(r"(?<=[.!?…])\s+", str(text or ""))
    return " ".join(x for x in sentences if not _PRIVATE.search(x)).strip()


def person_block(d, limit=3000):
    """For the draft of his next email to them: what he has thought lately, what was sent, and where it stands."""
    name = d.get("name") or d.get("address") or "them"
    lines = []
    i = d.get("interest") or {}
    if i.get("days"):
        lines.append("YOU HAVE KEPT THINKING ABOUT %s: named on %d day(s) in the last %d (%s)." % (
            name.upper(), len(i["days"]), i.get("window_days", WINDOW_DAYS),
            ", ".join("%s %d" % (k, v) for k, v in sorted((i.get("sources") or {}).items(), key=lambda kv: -kv[1]))))
        # His journal is private and full of Gloria. No sentence that names her goes to the drafter of a letter to
        # someone else; what is left of each excerpt is marked as his own notes, not for the letter.
        rx = pattern(name)
        own = []
        for t in d.get("his_thoughts", []):
            kept = _without_her(t.get("text") or "")
            if kept and rx is not None and rx.search(kept):
                own.append(dict(t, text=kept))
            if len(own) == 6: break
        if own:
            lines.append("(Your own private notes, for you to think from. Never quote or paraphrase them in the email.)")
        for t in own:
            lines.append("- [%s, %s] %s" % (t.get("day"), t.get("source"), t.get("text")))
    for l in d.get("letters_about", [])[:4]:
        lines.append("- letter to you about them (%s): %s" % (l.get("day"), l.get("subject")))
    h = d.get("history") or {}
    if h.get("sent") or h.get("second_email"):
        lines.append("BETWEEN YOU: %d sent, %d replies." % (h.get("sent", 0), h.get("replies", 0)) + (
            " Your second email was %s by Gloria on %s." % (h["second_email"]["status"], h["second_email"]["day"])
            if h.get("second_email") else "") + (
            " You may not ask to write to them again before %s." % h["quiet_until"] if h.get("quiet_until") else ""))
    return "\n".join(lines)[:limit]


def tend(now=None, read=None):
    """Every person with a page: gather, and while the interest recurs, keep reading. Never raises for one person."""
    import scholar
    done = []
    for path in sorted(glob.glob(os.path.join(scholar.DOSSIERS, "*.json"))):
        try:
            d = _load(path, None)
            if not isinstance(d, dict) or not d.get("address"): continue
            d, new = gather(d, now=now)
            n = keep_reading(d, now=now, read=read)
            scholar.save(d)
            done.append({"address": d["address"], "name": d.get("name"), "days": len(d["interest"]["days"]),
                         "recurring": d["interest"]["recurring"], "new_thoughts": new, "read": n})
        except Exception as e:
            done.append({"file": os.path.basename(path), "error": "%s: %s" % (type(e).__name__, str(e)[:160])})
    return done


def main(argv):
    if "--show" in argv:
        import scholar
        for path in sorted(glob.glob(os.path.join(scholar.DOSSIERS, "*.json"))):
            d = _load(path, {}) or {}
            i = d.get("interest") or {}
            h = d.get("history") or {}
            print("%-26s %-30s named %2d day(s)%s; read %d; %s" % (
                (d.get("name") or "?")[:26], (d.get("address") or "?")[:30], len(i.get("days") or []),
                " RECURRING" if i.get("recurring") else "", len(d.get("read") or []),
                ("quiet until " + h["quiet_until"]) if h.get("quiet_until") else "no quiet"))
        return 0
    print(json.dumps(tend(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
