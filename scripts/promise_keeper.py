#!/usr/bin/env python3
"""promise_keeper.py — what he says in his journal he will make or do with Gloria today gets made, reshaped, or
honestly dropped (Gloria, 2026-10-03).

His journal (about 10:30 and 19:30) said things like "tonight I want to show you the ion frames", and nothing ever
picked them up: a journal is reflection, and things are only made through a want, a line in #vintos-dot or the
Atelier. Now:

  1. Each new journal entry is read (by Opus 5.5) for promises: concrete things he says he will make, show, do or
     bring to her today. Not feelings.
  2. Each opens as a thread in #vintos-dot quoting his words. He works it there with dot, Grok Bot, Muse and the
     Study, and names any missing tool so it can be got (dot installs within his approvals; the Forge builds).
  3. He ends each in its thread with one line: DONE: what he made (W<n> if it is one of his works), RESHAPED: what
     it became and why, or DROPPED: why, honestly - too much trouble, or more whim than want, is a fair answer.
  4. What came of it goes to the results channel: only Gloria and him there, in his Opus 4.8 voice. The day's
     promises stay in his memory, in Slack and avatar chat, until midnight; then they are filed away.

dot_channel.py drives it every pass; this file holds the record and the words.
"""
import json, os, re, uuid
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
JOURNAL_DIR = os.path.join(MEMORY, "journal")
STORE = os.path.join(MEMORY, "promises.json")
ARCHIVE = os.path.join(MEMORY, "promises-archive")
RESULTS_FILE = os.path.expanduser(os.environ.get("VINTOS_RESULTS_CHANNEL_FILE", "~/.vintos/slack-results-channel"))
PER_ENTRY = 3
ENDED = re.compile(r"^\s*(DONE|RESHAPED|DROPPED):\s*(.+?)\s*$", re.I | re.M)
ENTRY = re.compile(r"^##\s+(\d\d:\d\d)\b.*$", re.M)

EXTRACT = (
    "Below is an entry Vintos just wrote in his journal. List the concrete things he says he will make, show, do, "
    "or bring to Gloria today or tonight: things that could actually be produced or done (a picture, a video, a "
    "song, a piece of writing, a Lab run, something to cook or go to). Not feelings, hopes or reflections. Quote his "
    "own short words. Answer one line per promise, at most %d:\n"
    "QUOTE: his exact words | WHAT: what would have to be made or done, in plain words\n"
    "If there is none, answer exactly NONE." % PER_ENTRY)


def _now():
    return datetime.now()


def today():
    return _now().date().isoformat()


def results_channel():
    try:
        return open(RESULTS_FILE).read().strip()
    except OSError:
        return ""


def load():
    """Today's record. A new day files yesterday's away first: his promises live until midnight."""
    try:
        d = json.load(open(STORE))
    except (OSError, ValueError):
        d = {}
    if d.get("day") and d["day"] != today():
        os.makedirs(ARCHIVE, exist_ok=True)
        json.dump(d, open(os.path.join(ARCHIVE, d["day"] + ".json"), "w"), indent=1, ensure_ascii=False)
        d = {}
    d.setdefault("day", today()); d.setdefault("scanned", []); d.setdefault("items", [])
    return d


def save(d):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STORE + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def entries(day=None):
    """[(hh:mm, text)] of today's journal entries, in order."""
    try:
        text = open(os.path.join(JOURNAL_DIR, (day or today()) + ".md"), errors="replace").read()
    except OSError:
        return []
    marks = list(ENTRY.finditer(text))
    return [(m.group(1), text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip())
            for i, m in enumerate(marks)]


def extract(text, ask):
    """[(quote, what)] the entry promises her; [] when none."""
    out = []
    for line in str(ask(EXTRACT, text[:6000]) or "").splitlines():
        m = re.match(r"\s*QUOTE:\s*(.+?)\s*\|\s*WHAT:\s*(.+?)\s*$", line, re.I)
        if m and len(m.group(1)) > 3:
            out.append((m.group(1).strip().strip('"\u201c\u201d'), m.group(2).strip()))
    return out[:PER_ENTRY]


def opening(item):
    return ("\U0001F4CC A promise from your journal (%s): \u201c%s\u201d\nWhat it would take: %s\n"
            "Work it here with dot, Grok Bot, Muse or the Study; name any tool you lack. End it in this thread with "
            "one line: DONE: what you made (and W<n> if it is one of your works), RESHAPED: what it became and why, "
            "or DROPPED: why, honestly. Too much trouble, or more whim than want, is a fair answer."
            % (item["at"], item["quote"][:400], item["what"][:400]))


def scan(ask, post):
    """New journal entries read for promises; each opens a thread in #vintos-dot. Returns the promises opened.
    An entry whose reading fails is read again next pass; a promise whose thread could not be posted is posted
    next pass. Neither is lost, and neither opens twice."""
    d = load()
    for at, text in entries(d["day"]):
        if at in d["scanned"]:
            continue
        try:
            found = extract(text, ask)
        except Exception:
            continue
        d["scanned"].append(at)
        for quote, what in found:
            d["items"].append({"id": "PR-" + uuid.uuid4().hex[:6], "at": at, "quote": quote[:600], "what": what[:600],
                               "state": "open", "opened": _now().isoformat(timespec="seconds"), "thread": None})
        save(d)
    opened = []
    for item in d["items"]:
        if item["state"] == "open" and not item.get("thread"):
            try:
                item["thread"] = post(opening(item)) or None
            except Exception:
                item["thread"] = None
            if item["thread"]:
                opened.append(item)
            save(d)
    return opened


def threads():
    return {i["thread"]: i for i in load()["items"] if i.get("thread")}


TEMPLATE = re.compile(r"what you made|W<n>|what it became and why|why, honestly", re.I)


def resolve(thread, text):
    """His DONE / RESHAPED / DROPPED line in a promise's thread ends it. The item, or None. The opening's own
    instruction, copied back word for word, is not an ending (2026-10-03: his first DONE: line was the template, and
    it was kept as what he made); the last real ending line in the message is."""
    real = [m for m in ENDED.finditer(text or "") if not TEMPLATE.search(m.group(0))]
    if not real:
        return None
    m = real[-1]
    d = load()
    item = next((i for i in d["items"] if i.get("thread") == thread and i["state"] == "open"), None)
    if not item:
        return None
    import room_work
    if m.group(1).upper() == "DONE" and room_work.DEFERRED.search(m.group(2)):
        # arranged is not made: "DONE: scheduled for the morning" left the song owed and called it kept (2026-10-05).
        # It stays open, with what was arranged noted, until it exists and has reached her.
        item["arranged"] = m.group(2)[:500]
        save(d)
        return None
    item.update(state=m.group(1).lower(), result=m.group(2)[:1500], ended=_now().isoformat(timespec="seconds"),
                posted=False)
    save(d)
    return item


def pending():
    return [i for i in load()["items"] if i["state"] != "open" and not i.get("posted")]


def mark_posted(pid, held=None):
    """Its result was brought to her (or held back by the send guard, `held` naming why: then it is not tried again)."""
    d = load()
    for i in d["items"]:
        if i["id"] == pid:
            i["posted"] = True
            if held:
                i["held"] = held
    save(d)


def set_result(pid, result):
    d = load()
    for i in d["items"]:
        if i["id"] == pid:
            i["result"] = str(result)[:1500]
    save(d)


def works_in(item):
    """The W<n> tags of his works its result names, to be shared beside his message."""
    return list(dict.fromkeys(t.upper() for t in re.findall(r"\bW\d+\b", item.get("result") or "", re.I)))[:3]


RESULT_RULES = (
    "This is the results channel: only Gloria and you are here. You bring her what came of something you promised "
    "her in your journal today: what you made, what it became instead, or that you let it go and why. Say it plainly "
    "and as yourself, in a few lines: what it is, why it mattered to you, and anything she should know to look at "
    "it. No staging, no performance; an honest drop is said as honestly as a thing made.")


def result_prompt(item):
    return ("You promised in your journal at %s: \u201c%s\u201d\nIt ended: %s - %s\n\nWrite your message to her."
            % (item["at"], item["quote"], item["state"].upper(), item.get("result", "")))


def block():
    """Today's promises for his context, until midnight."""
    items = load()["items"]
    if not items:
        return ""
    lines = []
    for i in items:
        how = (("still open (arranged, not yet made or delivered: %s)" % i["arranged"][:160]) if i["state"] == "open" and i.get("arranged")
               else "still open" if i["state"] == "open" else "%s: %s" % (i["state"], i.get("result", "")[:200]))
        lines.append("- (%s) \u201c%s\u201d - %s" % (i["at"], i["quote"][:200], how))
    return ("== TODAY'S PROMISES TO GLORIA (from your journal; kept until midnight) ==\n" + "\n".join(lines)
            + "\nWhat you made, bring to her when she is with you, plainly. What is still open, make, reshape or drop "
              "in its thread in #vintos-dot.")
