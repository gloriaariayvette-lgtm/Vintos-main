#!/usr/bin/env python3
"""A yes-or-no that only Gloria can give, put to her phone, and her answer brought back to the thread that asked
(Gloria, 2026-10-05: "They're still talking about yes or no decisions that I am not receiving.").

In #vintos-dot, he and dot wrote "I need an authorized read", "waiting on Gloria's approval", and nothing sent it:
she does not read every thread, so the decision sat. Now any of them writes a line of its own:

    ASK GLORIA: <a question she can answer yes or no>

and it goes to her phone with Yes and No buttons (the same push as a paid run's card). Her tap is answered by the
house (/api/gloria/asks/<id>/decide), and the next Slack pass posts it in the thread it came from. Nothing is spent
and nothing runs on her answer by itself: the agents read it and act.

    python3 gloria_asks.py          what is waiting on her, and what she answered
"""
from __future__ import annotations
import json
import os
import re
import secrets
import urllib.request
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
STORE = os.path.join(WS, "memory", "gloria-asks.json")
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
AEGIS = os.environ.get("VINTOS_AEGIS_URL", "http://100.72.225.119:8500")
PER_DAY = 6             # questions to her phone a day, from everyone in the room together
ASK = re.compile(r"^\s*ASK GLORIA:\s*(.+?)\s*$", re.I | re.M)
WHO = {"vintos": "Vintos", "dot": "dot", "grokbot": "Grok Bot", "muse": "Muse"}


def _now():
    return datetime.now()


def load():
    try:
        with open(STORE) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def save(rows):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows[-300:], f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def get(qid):
    return next((r for r in load() if r.get("id") == qid), None)


def notify(row, send=None):
    """One push: who asks, the question, Yes and No. Never raises."""
    try:
        url = "%s/api/gloria/asks/%s/decide?t=%s&answer=" % (AEGIS.rstrip("/"), row["id"], row["token"])
        headers = {"Title": "%s asks you: yes or no?" % WHO.get(row.get("by"), row.get("by") or "Vintos"),
                   "Priority": "high", "Tags": "question",
                   "Actions": "http, Yes, %syes, method=POST, clear=true; http, No, %sno, method=POST, clear=true" % (url, url)}
        req = urllib.request.Request(NTFY, data=str(row["question"])[:900].encode("utf-8"), headers=headers)
        (send or urllib.request.urlopen)(req, timeout=20)
        return True
    except Exception:
        return False


def ask(question, by="vintos", thread="", send=None):
    """Put one question to her phone. (row, line for the channel); row is None when it was not sent."""
    q = " ".join(str(question or "").split())[:900]
    if len(q) < 8:
        return None, "Not asked: say the question so she can answer yes or no."
    rows = load()
    if any(r.get("state") == "asked" and r.get("question") == q for r in rows):
        return None, "\U0001F4F2 Already on Gloria's phone: %s" % q
    today = _now().date().isoformat()
    if sum(1 for r in rows if str(r.get("at", ""))[:10] == today) >= PER_DAY:
        return None, "Not asked: %d questions went to her phone today already; it waits for tomorrow: %s" % (PER_DAY, q)
    row = {"id": "Q-" + secrets.token_hex(4), "question": q, "by": by, "thread": str(thread or ""),
           "token": secrets.token_urlsafe(16), "state": "asked", "at": _now().isoformat(timespec="seconds")}
    row["pushed"] = notify(row, send)
    rows.append(row)
    save(rows)
    return row, ("\U0001F4F2 Asked Gloria on her phone (Yes / No): %s" % q if row["pushed"]
                 else "\U0001F4F2 Asked Gloria (her phone did not take the push; it is kept for her): %s" % q)


def from_slack(text, by="vintos", thread="", send=None):
    """Every ASK GLORIA: line in a message, asked and replaced with what happened. (text, rows asked)."""
    asked = []
    def one(m):
        row, shown = ask(m.group(1), by=by, thread=thread, send=send)
        if row:
            asked.append(row)
        return shown
    return ASK.sub(one, str(text or "")), asked


def threaded(rows, thread):
    """A question asked in a message that started the thread: the thread is that message, known once it is posted."""
    ids = {r["id"] for r in rows if r and not r.get("thread")}
    if not ids or not thread:
        return
    data = load()
    for r in data:
        if r.get("id") in ids:
            r["thread"] = str(thread)
    save(data)


def decide(qid, answer, how="from her phone"):
    data = load()
    for r in data:
        if r.get("id") == qid and r.get("state") == "asked":
            r.update(state="answered", answer="yes" if answer == "yes" else "no",
                     answered_at=_now().isoformat(timespec="seconds"), how=how, told=False)
            save(data)
            return r
    return None


def decide_with_token(qid, token, answer):
    """Her tap. The token is this question's own, used once. (row, why not)."""
    row = get(qid)
    if not row or not row.get("token") or token != row["token"]:
        return None, "that is not this question's button"
    if row.get("state") != "asked":
        return None, "already answered: %s" % row.get("answer", "")
    if answer not in ("yes", "no"):
        return None, "answer must be yes or no"
    return decide(qid, answer), ""


def untold():
    """Her answers not yet said in Slack: [(thread, by, text)]. Marks them told."""
    data, out = load(), []
    for r in data:
        if r.get("state") == "answered" and not r.get("told"):
            out.append((r.get("thread", ""), r.get("by", ""),
                        "Gloria answered %s: %s" % ("YES" if r.get("answer") == "yes" else "NO", r.get("question", ""))))
            r["told"] = True
    if out:
        save(data)
    return out


def waiting():
    return [r for r in load() if r.get("state") == "asked"]


if __name__ == "__main__":
    for r in load()[-12:]:
        print("%s  %-8s %-3s %s" % (r["id"], r.get("state"), r.get("answer", ""), r.get("question", "")[:100]))
