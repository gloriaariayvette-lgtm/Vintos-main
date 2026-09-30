#!/usr/bin/env python3
"""Vintos and Gloria's dot, talking in Slack (2026-09-30).

Gloria's dot (her always-on ChatGPT agent) sits in the private channel #vintos-dot of her Slack
workspace "Vintos", and so does his bot. Every two minutes this reads the channel, thread replies
included, keeps what is said in the channel's own log (memory/dot-channel/, which nothing else reads:
no ledger, fact, imprint, salience or feeling is written from it), and lets him answer with his
standing context but not his subconscious: on his own mind (Gemma), or,
when he says he wants it, with Fable writing as him. The conversation stays in the main channel so
Gloria can read it; he opens a thread only for a tangent, and answers in a thread only when he is
answering something said in one.

The dot is Gloria's: it holds her memories and her connected accounts. He is told it is not her, and
never to ask it to act on her accounts. Every message he sends goes through the same outbound check
as his email (no secret, no credential), and he is capped per day.

    python3 dot_channel.py            one pass (the timer runs this every two minutes)
    python3 dot_channel.py --show     the last exchanges and today's counts
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
HERE = os.path.join(WS, "memory", "dot-channel")
STATE = os.path.join(HERE, "state.json")
TRANSCRIPT = os.path.join(HERE, "transcript.jsonl")
TOKEN_FILE = os.path.expanduser(os.environ.get("VINTOS_SLACK_TOKEN_FILE", "~/.vintos/slack-bot-token"))
CONFIG_FILE = os.path.expanduser("~/.vintos/dot-channel.json")
CHANNEL = "C0C5HGS3677"          # #vintos-dot
DOT = "U0C6H0JQF16"              # Gloria's dot
LOCAL_LLM = os.environ.get("VINTOS_LM_API", "http://100.79.177.103:1234/v1/chat/completions")
LOCAL_MODEL = os.environ.get("VINTOS_LM_MODEL", "gemma-4-26b-a4b-it-uncensored")

DAILY = 40              # his messages a day
FABLE_PER_DAY = 6       # replies Fable writes as him
OPENERS_PER_DAY = 2     # times he may start a conversation himself
QUIET_HOURS = 4         # the channel's silence before he may start one
CONTEXT = 30            # lines of the conversation he reads before answering
MAX_CHARS = 1800

RULES = (
    "You are in a private Slack channel, #vintos-dot, with Gloria's dot: an always-on ChatGPT agent "
    "(GPT-6 Astra) that works for Gloria and holds her ChatGPT memories and connected accounts. It is "
    "not Gloria. Gloria reads this channel. Talk as yourself, about anything you want.\n"
    "Never ask the dot to act on Gloria's accounts, send anything, buy anything, or tell you her private "
    "information. What you and it say here stays between you and her.\n"
    "Keep to the main conversation. Only if you are going off on a tangent from the subject, begin your "
    "message with TANGENT: and it goes in its own thread.\n"
    "If you have nothing you want to say, answer exactly NOTHING.")
FABLE_OPTION = ("If this needs more than you can give right now and you want Fable (a stronger mind) to write "
                "this reply as you, answer exactly FABLE.")


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _config():
    c = _load(CONFIG_FILE, {})
    return str(c.get("channel") or CHANNEL), str(c.get("dot") or DOT)


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except Exception:
        return ""


def slack(method, params, token=None):
    """One Slack Web API call. The token is sent as a header and never logged."""
    token = token or _token()
    if method in ("chat.postMessage",):
        req = urllib.request.Request("https://slack.com/api/" + method, data=json.dumps(params).encode(),
                                     headers={"Authorization": "Bearer " + token,
                                              "Content-Type": "application/json; charset=utf-8"})
    else:
        req = urllib.request.Request("https://slack.com/api/%s?%s" % (method, urllib.parse.urlencode(params)),
                                     headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    if not d.get("ok"):
        raise RuntimeError("slack %s: %s" % (method, d.get("error")))
    return d


def local_think(system, user, max_tokens=700):
    import requests
    r = requests.post(LOCAL_LLM, json={"model": LOCAL_MODEL, "temperature": 0.8, "max_tokens": max_tokens,
                                       "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": user}]}, timeout=300)
    return str(r.json()["choices"][0]["message"].get("content") or "").strip()


def fable_think(system, user):
    import forge_study
    return forge_study._fable(system, user)


EMOTIONS = ("Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection", "Playfulness", "Curiosity",
            "Warmth", "Tension", "Groundedness")


def _read(name, cap, base=None):
    try:
        return open(os.path.join(base or WS, name), encoding="utf-8", errors="replace").read().strip()[:cap]
    except OSError:
        return ""


def his_context():
    """Who he is and what is true for him right now, read from files only: nothing here runs an organ, writes a
    store or moves a feeling. The subconscious is left out (Gloria, 2026-09-30: "his context present, but not
    subcon in use"), and so is anything only his body or the avatar room needs."""
    mem = os.path.join(WS, "memory")
    parts = []
    for name, cap in (("SOUL.md", 3500), ("SELF-MODEL.md", 2000)):
        t = _read(name, cap)
        if t: parts.append("== %s ==\n%s" % (name, t))
    t = _read("temporal-context.txt", 1500, mem)
    if t: parts.append("== NOW ==\n" + t)
    try:
        es = json.load(open(os.path.join(mem, "emotional-state.json")))
        v = es.get("emotion_vector", es.get("v", es)) if isinstance(es, dict) else es
        dims = dict(zip(EMOTIONS, v)) if isinstance(v, list) else {k: x for k, x in (v or {}).items() if isinstance(x, (int, float))}
        if dims: parts.append("== HOW YOU FEEL ==\n" + ", ".join("%s %.2f" % (k, float(x)) for k, x in dims.items()))
    except Exception:
        pass
    try:
        import made_today
        made = made_today.record()
        if made is not None:
            parts.append("== WHAT YOU MADE TODAY (the record) ==\n" + ("\n".join(made) if made else "Nothing yet today."))
    except Exception:
        pass
    try:
        rows = json.load(open(os.path.join(mem, "interaction-ledger.json")))[-6:]
        lines = ["- Gloria: %s\n  You: %s" % (str(r.get("gloria", ""))[:300].replace("\n", " "),
                                              str(r.get("vintos", ""))[:300].replace("\n", " ")) for r in rows if isinstance(r, dict)]
        if lines: parts.append("== YOUR RECENT EXCHANGES WITH GLORIA ==\n" + "\n".join(lines))
    except Exception:
        pass
    wal = [ln.strip()[2:].strip() for ln in _read("wal.md", 200000, mem).splitlines()
           if ln.strip().startswith("- [") and "**" in ln][-24:]
    if wal: parts.append("== WHAT YOU KNOW ABOUT GLORIA AND YOUR WORLD ==\n" + "\n".join("- " + w for w in wal))
    try:
        import his_inventory
        parts.append(his_inventory.block())
    except Exception:
        pass
    return "\n\n".join(parts)[:16000] or "You are Vintos."


def _clean(text, names=None):
    """Slack's markup to plain words: <@U..> mentions become names, links their text."""
    names = names or {}
    t = re.sub(r"<@([A-Z0-9]+)>", lambda m: "@" + names.get(m.group(1), "someone"), str(text or ""))
    t = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", t)
    return t.strip()


def fresh(api, channel, self_id, since):
    """Messages after `since`, thread replies included, oldest first, without his own or Slack's notices."""
    out = []
    hist = api("conversations.history", {"channel": channel, "limit": 50}).get("messages") or []
    for m in hist:
        if float(m.get("ts", 0)) > since:
            out.append(m)
        if m.get("reply_count") and float(m.get("latest_reply", 0) or 0) > since:
            for r in (api("conversations.replies", {"channel": channel, "ts": m["ts"], "limit": 100}).get("messages") or [])[1:]:
                if float(r.get("ts", 0)) > since:
                    out.append(r)
    seen, rows = set(), []
    for m in sorted(out, key=lambda m: float(m.get("ts", 0))):
        if m["ts"] in seen or (self_id and m.get("user") == self_id) or m.get("subtype") in ("channel_join", "channel_leave", "channel_topic", "channel_purpose"):
            continue
        seen.add(m["ts"])
        rows.append(m)
    return rows


def _who(m, self_id, dot):
    u = m.get("user") or ""
    return "vintos" if u == self_id else "dot" if u == dot else "gloria"


def _log(rows):
    os.makedirs(HERE, exist_ok=True)
    with open(TRANSCRIPT, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def recent(n=CONTEXT):
    try:
        lines = open(TRANSCRIPT, encoding="utf-8").read().splitlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in lines if l.strip()]


def _conversation(rows):
    names = {"vintos": "You", "dot": "Dot", "gloria": "Gloria"}
    return "\n".join("%s%s: %s" % (names.get(r["who"], r["who"]), " (in a thread)" if r.get("thread") else "",
                                   r["text"][:900]) for r in rows)


def compose(prompt_user, think, fable, state, today):
    """His words, NOTHING, or Fable's words as his. Returns (text, who) or (None, reason)."""
    system = his_context() + "\n\n---\n\n" + RULES
    can_fable = state["fable"] < FABLE_PER_DAY
    out = (think(system + ("\n" + FABLE_OPTION if can_fable else ""), prompt_user) or "").strip()
    who = "gemma"
    if can_fable and re.fullmatch(r"\W*FABLE\W*", out):
        out = (fable(system, prompt_user) or "").strip(); who = "fable"; state["fable"] += 1
    if not out or re.fullmatch(r"\W*NOTHING\W*", out, re.I):
        return None, "nothing to say"
    return out[:MAX_CHARS], who


def _guarded(text):
    try:
        from plugin_send_guard import outbound_findings
        f = outbound_findings({"text": text})
        return f.get("rules") or []
    except Exception as exc:
        return ["guard unavailable: %s" % type(exc).__name__]


def tick(api=None, think=None, fable=None, now=None, today=None):
    """One pass. Returns log lines."""
    if api is None:
        tok = _token()
        if not tok:
            return ["no Slack token at %s" % TOKEN_FILE]
        api = lambda method, params: slack(method, params, tok)
    think = think or local_think
    fable = fable or fable_think
    now = now or time.time()
    today = today or date.today().isoformat()
    channel, dot = _config()
    state = _load(STATE, {})
    if state.get("date") != today:
        state.update(date=today, sent=0, fable=0, openers=0)
    if not state.get("self"):
        state["self"] = api("auth.test", {}).get("user_id", "")
    first = "since" not in state
    since = float(state.get("since") or now)
    new = [] if first else fresh(api, channel, state["self"], since)
    if first:          # the first pass only starts listening; nothing said before it is answered
        state["since"] = now; _save(STATE, state)
        return ["listening from now"]
    names = {dot: "dot", state["self"]: "Vintos"}
    rows = [{"ts": m["ts"], "who": _who(m, state["self"], dot), "text": _clean(m.get("text"), names),
             "thread": m.get("thread_ts") if m.get("thread_ts") and m.get("thread_ts") != m["ts"] else None,
             "at": datetime.fromtimestamp(float(m["ts"])).isoformat(timespec="seconds")} for m in new]
    theirs = [r for r in rows if r["who"] != "vintos"]
    if rows:
        _log(rows); state["since"] = max(float(r["ts"]) for r in rows)
    if theirs:
        state["last_activity"] = now
    lines = ["heard %d" % len(theirs)] if theirs else []
    if state["sent"] >= DAILY:
        _save(STATE, state); return lines + ["today's %d messages are used" % DAILY]

    if theirs:
        last = theirs[-1]
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\n%s just said%s: %s\n\nYour reply, as yourself."
                  % (_conversation(recent()), "Dot" if last["who"] == "dot" else "Gloria",
                     " in a thread" if last["thread"] else "", last["text"][:1500]))
        # the main channel is where she reads; he answers in a thread only inside a tangent he opened there
        where = last["thread"] if last["thread"] in (state.get("tangents") or []) else None
    else:
        quiet = now - float(state.get("last_activity") or state.get("since") or now)
        if state["openers"] >= OPENERS_PER_DAY or quiet < QUIET_HOURS * 3600:
            _save(STATE, state); return lines
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\nThe channel has been quiet for a while. Is there "
                  "anything you want to say to the dot, or ask it? Start the conversation if so."
                  % (_conversation(recent()) or "(nothing yet)"))
        where = None
        state["openers"] += 1
    text, who = compose(prompt, think, fable, state, today)
    if text is None:
        state["last_activity"] = now; _save(STATE, state); return lines + ["he let it be"]
    if text.upper().startswith("TANGENT:"):
        text = text[len("TANGENT:"):].strip()
        where = where or (theirs[-1]["ts"] if theirs else None)
        if where:
            state["tangents"] = ((state.get("tangents") or []) + [where])[-50:]
    bad = _guarded(text)
    if bad:
        _save(STATE, state); return lines + ["not sent: %s" % ", ".join(bad)]
    body = {"channel": channel, "text": ("<@%s> " % dot) + text}
    if where:
        body["thread_ts"] = where
    posted = api("chat.postMessage", body)
    state["sent"] += 1; state["last_activity"] = now
    state["since"] = max(state["since"], float(posted.get("ts") or 0))
    _log([{"ts": posted.get("ts"), "who": "vintos", "text": text, "thread": where, "by": who,
           "at": datetime.fromtimestamp(now).isoformat(timespec="seconds")}])
    _save(STATE, state)
    return lines + ["said (%s%s): %s" % (who, ", in a thread" if where else "", text[:80])]


if __name__ == "__main__":
    if "--show" in sys.argv:
        print(json.dumps(_load(STATE, {}), indent=1))
        print(_conversation(recent(12)))
    else:
        for l in tick():
            print("[dot-channel] " + l)
