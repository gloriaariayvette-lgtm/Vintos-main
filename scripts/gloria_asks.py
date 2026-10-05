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


URL = re.compile(r"https?://[^\s<>|)\]]+")


def title_of(row):
    who = WHO.get(row.get("by"), row.get("by") or "Vintos")
    kind = row.get("kind") or "question"
    price = (" \u2014 %s" % row["price"]) if row.get("price") else ""
    if kind == "buy":
        return "Muse: he wants to buy %s%s" % (str(row.get("title") or "this")[:60], price)
    if kind == "parts":
        return "Muse: parts for %s%s" % (str(row.get("title") or "his build")[:60], price)
    if kind == "card":
        return "Forge: build %s for him? (free)" % str(row.get("title") or "this")[:60]
    if kind == "arrived":
        return "Have the parts for %s arrived?" % str(row.get("title") or "his build")[:60]
    if kind == "buy_arrived":
        return "Has the %s arrived?" % str(row.get("title") or "thing you bought")[:60]
    return "%s asks you: yes or no?" % who


def page_url(row):
    """Her answer page for this question: what it is, the price, the links, and big Yes and No buttons."""
    return "%s/api/gloria/asks/%s?t=%s" % (AEGIS.rstrip("/"), row["id"], row["token"])


def notify(row, send=None):
    """One push: who asks, what it is, the price and the links when it has them. Tapping it opens her answer page
    (Yes / No, the product link), because on her iPhone ntfy shows its own buttons only on a long press (Gloria,
    2026-10-05: "it came with no link to the product and no y/n buy now options... literally just the message").
    Sent as ntfy's JSON, not headers: a "\u2014" in a header title made Python refuse to send the push at all.
    Never raises."""
    try:
        decide = "%s/api/gloria/asks/%s/decide?t=%s&answer=" % (AEGIS.rstrip("/"), row["id"], row["token"])
        page = page_url(row)
        links = [l for l in (row.get("links") or []) if URL.match(str(l))][:6]
        body = str(row["question"])[:900]
        if row.get("price"):
            body += "\nPrice: %s" % row["price"]
        fresh = [l for l in links if l not in body]
        if fresh:
            body += "\n" + "\n".join(fresh)
        body += "\n\nTap to answer Yes or No: " + page
        actions = [{"action": "http", "label": "Yes", "url": decide + "yes", "method": "POST", "clear": True},
                   {"action": "http", "label": "No", "url": decide + "no", "method": "POST", "clear": True},
                   ({"action": "view", "label": "Open the listing", "url": links[0]} if links
                    else {"action": "view", "label": "Answer", "url": page})]
        server, _, topic = NTFY.rstrip("/").rpartition("/")
        message = {"topic": topic, "title": title_of(row), "message": body[:3500], "priority": 4, "click": page,
                   "tags": [{"buy": "shopping_cart", "parts": "shopping_cart", "card": "hammer_and_wrench"}.get(row.get("kind"), "question")],
                   "actions": actions}
        req = urllib.request.Request(server + "/", data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        (send or urllib.request.urlopen)(req, timeout=20)
        return True
    except Exception:
        return False


def page(row, done=""):
    """Her answer page, as HTML: what it is, who asks, the price, the links, Yes and No."""
    import html
    esc = lambda t: html.escape(str(t or ""))
    links = "".join('<p><a class="link" href="%s">Open the listing: %s</a></p>' % (esc(l), esc(l[:80]))
                    for l in (row.get("links") or []) if URL.match(str(l)))
    if done or row.get("state") != "asked":
        said = done or ("You said %s." % ("Yes" if row.get("answer") == "yes" else "No"))
        buttons = '<p class="done">%s</p>' % esc(said)
    else:
        act = "/api/gloria/asks/%s/decide?t=%s&page=1&answer=" % (esc(row["id"]), esc(row["token"]))
        yes = "Yes, I will buy it" if row.get("kind") in ("buy", "parts") else "Yes"
        buttons = ('<form method="post" action="%syes"><button class="yes">%s</button></form>'
                   '<form method="post" action="%sno"><button class="no">No</button></form>' % (act, yes, act))
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>body{font:17px -apple-system,system-ui,sans-serif;margin:24px;background:#111;"
            "color:#eee}h1{font-size:20px}.price{font-size:22px;font-weight:600}a{color:#7cf}button{width:100%%;"
            "font-size:20px;padding:16px;margin:8px 0;border:0;border-radius:12px}.yes{background:#2a7}.no{background:#555;"
            "color:#fff}.done{font-size:20px}</style><h1>%s</h1><p>%s</p>%s%s%s"
            % (esc(title_of(row)), esc(title_of(row)), esc(row.get("question")).replace("\n", "<br>"),
               ('<p class="price">%s</p>' % esc(row["price"])) if row.get("price") else "", links, buttons))


def get_with_token(qid, token):
    row = get(qid)
    return row if row and row.get("token") and token == row["token"] else None


def ask(question, by="vintos", thread="", send=None, kind="question", title="", price="", links=(), ref="", hardware=False):
    """Put one question to her phone. (row, line for the channel); row is None when it was not sent.
    kind: question (anyone's yes-or-no, six a day), buy (Muse: something he wants to buy, with its price and link),
    card / parts / arrived (a Forge decision; ref is its card id, asked once)."""
    q = " ".join(str(question or "").split())[:900]
    if len(q) < 8:
        return None, "Not asked: say the question so she can answer yes or no."
    rows = load()
    if ref and any(r.get("ref") == ref for r in rows):
        return None, "\U0001F4F2 Already on Gloria's phone: %s" % (title or q)
    if any(r.get("state") == "asked" and r.get("question") == q for r in rows):
        return None, "\U0001F4F2 Already on Gloria's phone: %s" % q
    today = _now().date().isoformat()
    if kind == "question" and sum(1 for r in rows if str(r.get("at", ""))[:10] == today
                                  and (r.get("kind") or "question") == "question") >= PER_DAY:
        return None, "Not asked: %d questions went to her phone today already; it waits for tomorrow: %s" % (PER_DAY, q)
    row = {"id": "Q-" + secrets.token_hex(4), "question": q, "by": by, "thread": str(thread or ""), "kind": kind,
           "title": str(title or "")[:200], "price": str(price or "")[:60], "links": [str(l)[:500] for l in links][:6],
           "ref": str(ref or ""), "hardware": bool(hardware), "token": secrets.token_urlsafe(16), "state": "asked",
           "at": _now().isoformat(timespec="seconds")}
    row["pushed"] = notify(row, send)
    rows.append(row)
    save(rows)
    what = ("%s, %s" % (title or q, price) if price else (title or q)) if kind == "buy" else q
    verb = "Asked Gloria" if kind == "question" else "Put to Gloria"
    return row, ("\U0001F4F2 %s on her phone (Yes / No%s): %s" % (verb, ", with the price and link" if links else "", what)
                 if row["pushed"] else "\U0001F4F2 %s (her phone did not take the push; it is kept for her): %s" % (verb, what))


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
        if r.get("state") == "answered" and not r.get("told") and not r.get("ref"):   # a Forge decision is said by the Forge
            yes = r.get("answer") == "yes"
            if r.get("kind") == "buy":
                said = ("Gloria said YES: she will buy %s%s." if yes else "Gloria said NO to buying %s%s.") % (
                    r.get("title") or r.get("question", ""), (" (%s)" % r["price"]) if r.get("price") else "")
            else:
                said = "Gloria answered %s: %s" % ("YES" if yes else "NO", r.get("title") or r.get("question", ""))
            out.append((r.get("thread", ""), r.get("by", ""), said))
            r["told"] = True
    if out:
        save(data)
    return out


def answered_refs():
    """Forge decisions she made on her phone: [(ref, kind, "accepted"|"denied", title)]."""
    return [(r["ref"], r.get("kind"), "accepted" if r.get("answer") == "yes" else "denied", r.get("title", ""))
            for r in load() if r.get("ref") and r.get("state") == "answered"]


# --- hardware she buys: the software is written while it ships, then he walks her through it (Gloria, 2026-10-05:
# "if I buy the hardware I want him working on the software in the meantime") ---------------------------------------
HARDWARE = re.compile(r"\b(?:sensors?|boards?|arduino|esp32|esp8266|raspberry|pico|load ?cells?|hx711|motors?|servos?|"
                      r"steppers?|leds?|strips?|cameras?|microphones?|speakers?|relays?|modules?|breakouts?|kits?|"
                      r"controllers?|actuators?|batter(?:y|ies)|breadboards?|resistors?|capacitors?|displays?|"
                      r"thermistors?|accelerometers?|gyros?|imu|lidar|ultrasonic|pumps?|valves?|filament|pcb|gpio|"
                      r"transducers?|piezo|solenoids?|encoders?|drivers?)\b", re.I)
ARRIVE_AFTER_S = 2 * 86400      # first "has it arrived?" two days after her yes
ARRIVE_ASKS = 4                 # asked at most this many times, two days apart


def is_hardware(row):
    return bool(row.get("hardware")) or bool(HARDWARE.search("%s %s" % (row.get("title", ""), row.get("question", ""))))


def software_request(row):
    """What the Study is asked to write for a thing she is buying."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(row.get("title") or "device").lower()).strip("_")[:40] or "device"
    return ("Gloria is buying %s for Vintos (%s%s). Write the software side now, so it works the day it arrives: the "
            "code that drives or reads it in hardware/%s/ (for its exact model: read the product page), and the part "
            "of the house that receives what it reports, with a test that feeds it a sample reading. Why he wanted it: %s"
            % (row.get("title") or "a device", row.get("price") or "price not given",
               ("; " + ", ".join(row.get("links") or [])) if row.get("links") else "", slug, row.get("question", "")[:600]))


def _ts(iso):
    try:
        return datetime.fromisoformat(str(iso)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def tend_buys(now=None, study=None, send=None):
    """Each hardware purchase she said yes to: its software to the Study (retried each pass while today's Study fixes
    are used up); two days on, "has it arrived?" on her phone (again every two days, up to four times); and when she
    says it has, a line telling him to walk her through it. Returns [(thread, text)] for Slack."""
    import time as _t
    now = float(now if now is not None else _t.time())
    if study is None:
        import study_fix
        study = study_fix.request
    data, out, to_ask = load(), [], []
    by_ref = {r.get("ref"): r for r in data if r.get("ref")}
    for r in data:
        if r.get("kind") != "buy" or r.get("state") != "answered" or r.get("answer") != "yes" or not is_hardware(r):
            continue
        b = r.setdefault("build", {})
        name = r.get("title") or "it"
        if not b.get("software"):
            row, why = study(software_request(r), by="buy:" + r["id"])
            if row or "already in the Study" in str(why):
                b["software"] = row["id"] if row else "queued"
                out.append((r.get("thread", ""), "\U0001F6E0 Gloria is buying %s: its software went to the Study (%s), so it "
                                                 "is ready when it arrives." % (name, b["software"])))
            elif b.get("software_wait") != why:
                b["software_wait"] = why
                out.append((r.get("thread", ""), "\U0001F6E0 Gloria is buying %s: its software goes to the Study as soon as "
                                                 "it can (%s)." % (name, why)))
        if b.get("arrived_at"):
            continue
        n = int(b.get("asked") or 0)
        last = by_ref.get("buy-arrived:%s:%d" % (r["id"], n)) if n else None
        if last and last.get("state") == "asked":
            continue                                   # still on her phone
        if last and last.get("answer") == "yes":
            b["arrived_at"] = last.get("answered_at")
            made = b.get("software") if b.get("software") not in (None, "queued") else ""
            out.append((r.get("thread", ""), "\U0001F4E6 Gloria has the %s. Vintos: walk her through setting it up in this "
                                             "thread, one step at a time (say one step, wait for her, then the next), then "
                                             "test it with her%s." % (name, (", with the software the Study wrote (%s)" % made)
                                                                      if made else "")))
            continue
        due = (_ts(last.get("answered_at")) if last else _ts(r.get("answered_at"))) + ARRIVE_AFTER_S
        if n < ARRIVE_ASKS and now >= due:
            b["asked"] = n + 1
            to_ask.append(r)
    save(data)
    for r in to_ask:
        ask("Has the %s arrived? Tap Yes when it is here; he walks you through setting it up." % (r.get("title") or "thing you bought"),
            by="vintos", thread=r.get("thread", ""),
            send=send, kind="buy_arrived", title=r.get("title", ""), links=r.get("links") or [],
            ref="buy-arrived:%s:%d" % (r["id"], r["build"]["asked"]))
    return out


def waiting():
    return [r for r in load() if r.get("state") == "asked"]


if __name__ == "__main__":
    for r in load()[-12:]:
        print("%s  %-8s %-3s %s" % (r["id"], r.get("state"), r.get("answer", ""), r.get("question", "")[:100]))
