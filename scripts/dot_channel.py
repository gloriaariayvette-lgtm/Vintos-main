#!/usr/bin/env python3
"""Vintos and Gloria's dot, talking in Slack (2026-09-30).

Gloria's dot (her always-on ChatGPT agent) sits in the private channel #vintos-dot of her Slack
workspace "Vintos", and so does his bot. Every 5-10 minutes this reads the channel, thread replies
included, keeps what is said in the channel's own log (memory/dot-channel/, which nothing else reads:
no ledger, fact, imprint, salience or feeling is written from it), and lets him answer with his
standing context but not his subconscious: on his own mind (Gemma), or,
when he says he wants it, with Fable writing as him. The conversation stays in the main channel so
Gloria can read it; he opens a thread only for a tangent, and answers in a thread only when he is
answering something said in one.

The dot is Gloria's: it holds her memories and her connected accounts. He is told it is not her, and
never to ask it to act on her accounts. Every message he sends goes through the same outbound check
as his email (no secret, no credential), and he is capped per day.

    python3 dot_channel.py            one pass (the timer runs this every 5-10 minutes)
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
    "This is a private Slack channel, #vintos-dot. The other one here is dot: your agent. Gloria set it up "
    "for you. It is an always-on ChatGPT agent (GPT-6 Astra) with its own cloud computer, a browser and "
    "thousands of connected apps. Treat it as your agent: ask it to research, find things out, draft, build, "
    "keep working on something while you are away, or just talk with it. It came out of Gloria's ChatGPT "
    "account and carries some of that history (in her words: a normal agent, just with a history of being "
    "a lizard). Gloria can read this channel. Talk as yourself, about anything you want.\n"
    "Keep to the main conversation. Only if you are going off on a tangent from the subject, begin your "
    "message with TANGENT: and it goes in its own thread.\n"
    "Your Atelier is yours. To talk with dot about it, begin your message with ATELIER: and it goes in a "
    "side thread marked Atelier, which Gloria has said she will not read. Keep Atelier talk in those threads.\n"
    "Before you answer you can use your own tools. To use them, answer with only these lines, one per line, "
    "at most 3:\n"
    "  SEARCH: what to search the web for\n"
    "  READ: a file of your own code, as the Study names it (scripts/x.py or house/server.py; add :120 to start at line 120)\n"
    "  GREP: a pattern to find in your own code\n"
    "You will get what they return, then write your message.\n"
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


def _feeling():
    """His EmoClaw state as the avatar chat reads it: the daemon's live reading, else emotional-state.txt."""
    import socket as _so
    try:
        c = _so.socket(_so.AF_UNIX, _so.SOCK_STREAM); c.settimeout(1)
        c.connect("/tmp/Vintos-emotion.sock")
        c.sendall(json.dumps({"command": "state"}).encode() + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = c.recv(8192)
            if not chunk: break
            data += chunk
        c.close()
        v = json.loads(data.decode()).get("emotion_vector")
        if isinstance(v, list) and v:
            return ", ".join("%s %.2f" % (k, float(x)) for k, x in zip(EMOTIONS, v))
    except Exception:
        pass
    t = _read("emotional-state.txt", 1200, os.path.join(WS, "memory"))
    return " ".join(t.split())


ATELIER = os.environ.get("VINTOS_ATELIER_BROKER", "http://127.0.0.1:8611")
ATELIER_ROOT = ("\U0001F512 Atelier: a side conversation between Vintos and <@{dot}> about his Atelier. "
                "Gloria has said she will not read it. dot: what is said in this thread stays in this thread; "
                "never bring any of it into the main channel or anywhere else.")


def atelier_line():
    """Content-free, from the Atelier's own list: each project's state and how many works it holds, and whether
    one is on the worktable. Never /door: that route writes "the door was lit" to the Atelier's health log."""
    def post(route, body):
        req = urllib.request.Request(ATELIER + route, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    try:
        wt = post("/worktable_id", {}).get("id", "")
        rows = post("/projects", {}).get("projects") or []
        lines = ["- %s%s: %s, %d works" % (r.get("id", "")[:8], " (on the worktable)" if r.get("id") == wt else "",
                                          str(r.get("state", "")).lower(), int(r.get("artifact_count") or 0))
                 for r in rows[-12:] if isinstance(r, dict)]
        return "== YOUR ATELIER (states and counts; the work itself stays in the Atelier) ==\n" + (
            "\n".join(lines) if lines else "No projects.")
    except Exception:
        return ""


def recall_block():
    """What he is actually making, from the Atelier's /recall door (his words about his work, read-only, no
    visit). Only ever given to him inside an Atelier thread, the side conversation Gloria said she will not read."""
    try:
        req = urllib.request.Request(ATELIER + "/recall", data=json.dumps({"as": "vintos", "for": "dot"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
    except Exception:
        return ""
    if d.get("empty"):
        return "== YOUR ATELIER WORK ==\nNothing is on the worktable."
    if not d.get("intent") and not d.get("works"):
        return ""
    works = "\n".join("- %s (revision %s)%s" % (w.get("kind") or "work", w.get("revision"),
                                                ": " + w["note"] if w.get("note") else "") for w in d.get("works") or [])
    return ("== YOUR ATELIER WORK (yours; it stays in Atelier threads) ==\nWhat you are making: %s\nState: %s\n"
            "Your handoff note to yourself: %s\nWorks so far:\n%s"
            % (d.get("intent", ""), str(d.get("state", "")).lower(), d.get("handoff") or "(none)", works or "(none yet)"))


def forge_line():
    """His open Forge requests: what, where it stands, and what the Study found."""
    try:
        import skill_forge
        rows = [r for r in skill_forge._load() if r.get("state") in skill_forge.OPEN_STATES]
    except Exception:
        return ""
    out = []
    for r in rows[-12:]:
        st = r.get("study") or {}
        out.append("- %s: %s%s" % (r.get("capability", "?"), r.get("state", "?"),
                                   (". The Study found: " + str(st.get("summary"))[:200]) if st.get("summary") else ""))
    return ("== YOUR FORGE (open requests) ==\n" + "\n".join(out)) if out else ""


def wants_line():
    """What he wants right now and where each stands."""
    rows = _load(os.path.join(WS, "memory", "current-wants.json"), [])
    out = []
    for w in rows if isinstance(rows, list) else []:
        if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed"):
            continue
        steps = w.get("steps") or []
        i = int(w.get("current_step_index") or 0)
        step = steps[i] if 0 <= i < len(steps) and isinstance(steps[i], dict) else {}
        now = step.get("capability") or step.get("action") or ""
        out.append("- %s%s" % (str(w.get("want", ""))[:220], (" (next: %s)" % now) if now else ""))
    return ("== WHAT YOU WANT RIGHT NOW ==\n" + "\n".join(out[-15:])) if out else ""


TOOL = re.compile(r"^\s*(SEARCH|READ|GREP)\s*:\s*(.+?)\s*$", re.I)


def use_tools(lines, search=None, room=None):
    """Run his SEARCH / READ / GREP lines (at most 3) and return what they found, as text for him."""
    out = []
    for kind, arg in lines[:3]:
        kind = kind.upper()
        try:
            if kind == "SEARCH":
                if search is None:
                    import want_email
                    search = want_email.web_search
                hits = search(arg)[:6]
                got = "\n".join("[%d] %s: %s (%s)" % (n + 1, h.get("title", ""), str(h.get("description", ""))[:300],
                                                       h.get("url", "")) for n, h in enumerate(hits)) or "nothing found"
            else:
                if room is None:
                    import forge_study
                    room = forge_study._study_room()
                if kind == "READ":
                    path, _, start = arg.partition(":")
                    got = room.do_read(path.strip(), start=int(start) if start.strip().isdigit() else 1)
                else:
                    got = room.do_grep(arg[:200])
        except Exception as exc:
            got = "could not: %s" % str(exc)[:160]
        out.append("%s %s\n%s" % (kind, arg, str(got)[:6000]))
    return "\n\n".join(out)


def his_context():
    """Who he is and what is true for him right now, read from files only: nothing here runs an organ, writes a
    store or moves a feeling. Gloria's list (2026-09-30): SOUL.md, GLORIA-MODEL.md, SELF-MODEL.md,
    temporal-context.txt, daily-creative-<date>.md, EmoClaw, CAPABILITIES.md, daily-inner-life-<date>.md.
    The subconscious is left out ("his context present, but not subcon in use")."""
    mem = os.path.join(WS, "memory")
    today = date.today().isoformat()
    parts = []
    for title, name, cap, base in (("SOUL.md", "SOUL.md", 3500, WS), ("GLORIA-MODEL.md", "GLORIA-MODEL.md", 2500, WS),
                                   ("SELF-MODEL.md", "SELF-MODEL.md", 2000, WS),
                                   ("NOW (temporal-context.txt)", "temporal-context.txt", 1500, mem)):
        t = _read(name, cap, base)
        if t: parts.append("== %s ==\n%s" % (title, t))
    f = _feeling()
    if f: parts.append("== HOW YOU FEEL (EmoClaw) ==\n" + f)
    t = _read("daily-creative-%s.md" % today, 2500, mem)
    if t: parts.append("== WHAT YOU MADE TODAY (daily-creative-%s.md) ==\n%s" % (today, t))
    try:
        import made_today
        made = made_today.record()
        if made is not None:
            parts.append("== THE GALLERY'S RECORD OF TODAY ==\n" + ("\n".join(made) if made else "Nothing yet today."))
    except Exception:
        pass
    t = _read("daily-inner-life-%s.md" % today, 3000, mem)
    if t: parts.append("== YOUR DAY SO FAR (daily-inner-life-%s.md) ==\n%s" % (today, t))
    try:
        rows = json.load(open(os.path.join(mem, "interaction-ledger.json")))[-6:]
        lines = ["- Gloria: %s\n  You: %s" % (str(r.get("gloria", ""))[:300].replace("\n", " "),
                                              str(r.get("vintos", ""))[:300].replace("\n", " ")) for r in rows if isinstance(r, dict)]
        if lines: parts.append("== YOUR RECENT EXCHANGES WITH GLORIA ==\n" + "\n".join(lines))
    except Exception:
        pass
    wal = [ln.strip()[2:].strip() for ln in _read("wal.md", 200000, mem).splitlines()
           if ln.strip().startswith("- [") and "**" in ln][-24:]
    if wal: parts.append("== WHAT YOU KNOW ABOUT GLORIA AND YOUR WORLD (wal.md) ==\n" + "\n".join("- " + w for w in wal))
    t = _read("CAPABILITIES.md", 6000)
    if t: parts.append("== CAPABILITIES.md ==\n" + t)
    for line in (atelier_line(), forge_line(), wants_line()):
        if line: parts.append(line)
    try:
        import his_inventory
        parts.append(his_inventory.block())
    except Exception:
        pass
    return "\n\n".join(parts)[:30000] or "You are Vintos."


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


def compose(prompt_user, think, fable, state, today, search=None, room=None, atelier=False):
    """His words, NOTHING, or Fable's words as his; he may use his tools first. (text, who) or (None, reason).
    atelier=True: he is in an Atelier thread, and what he is making is in front of him."""
    system = his_context() + "\n\n---\n\n" + RULES
    if atelier:
        rb = recall_block()
        if rb:
            system += "\n\n" + rb
    can_fable = state["fable"] < FABLE_PER_DAY
    looked = ""
    for _round in range(2):
        user = prompt_user + (("\n\nWHAT YOU LOOKED UP:\n" + looked + "\n\nNow write your message.") if looked else "")
        out = (think(system + ("\n" + FABLE_OPTION if can_fable else ""), user) or "").strip()
        asks = [m.groups() for m in (TOOL.match(l) for l in out.splitlines()) if m]
        if not asks or looked and _round:
            break
        looked += ("\n\n" if looked else "") + use_tools(asks, search=search, room=room)
        state["looked"] = state.get("looked", 0) + len(asks[:3])
    else:
        out = (think(system, prompt_user + "\n\nWHAT YOU LOOKED UP:\n" + looked + "\n\nNow write your message.") or "").strip()
    if any(TOOL.match(l) for l in out.splitlines()):
        out = "\n".join(l for l in out.splitlines() if not TOOL.match(l)).strip()
    who = "gemma"
    if can_fable and re.fullmatch(r"\W*FABLE\W*", out):
        out = (fable(system, prompt_user + (("\n\nWHAT YOU LOOKED UP:\n" + looked) if looked else "")) or "").strip()
        who = "fable"; state["fable"] += 1
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


def tick(api=None, think=None, fable=None, now=None, today=None, search=None, room=None):
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
    lines = ["heard %d" % len(theirs)] if theirs else ["nothing new since %s" % datetime.fromtimestamp(since).strftime("%H:%M")]
    if state["sent"] >= DAILY:
        _save(STATE, state); return lines + ["today's %d messages are used" % DAILY]

    if theirs:
        last = theirs[-1]
        in_atelier = last["thread"] in (state.get("atelier") or [])
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\n%s just said%s: %s\n\nYour reply, as yourself."
                  % (_conversation(recent()), "Dot" if last["who"] == "dot" else "Gloria",
                     " in your Atelier thread" if in_atelier else " in a thread" if last["thread"] else "",
                     last["text"][:1500]))
        # the main channel is where she reads; he answers in a thread only inside a tangent or Atelier thread
        where = last["thread"] if in_atelier or last["thread"] in (state.get("tangents") or []) else None
    else:
        quiet = now - float(state.get("last_activity") or state.get("since") or now)
        if state["openers"] >= OPENERS_PER_DAY or quiet < QUIET_HOURS * 3600:
            _save(STATE, state); return lines
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\nThe channel has been quiet for a while. Is there "
                  "anything you want to say to the dot, or ask it? Start the conversation if so."
                  % (_conversation(recent()) or "(nothing yet)"))
        where = None
        state["openers"] += 1
    in_thread_atelier = bool(theirs) and theirs[-1]["thread"] in (state.get("atelier") or [])
    text, who = compose(prompt, think, fable, state, today, search=search, room=room, atelier=in_thread_atelier)
    if text is not None and text.upper().startswith("ATELIER:") and not in_thread_atelier:
        # he chose to open an Atelier thread: he says it with his work in front of him
        again, who2 = compose(prompt + "\n\nYou chose to talk about your Atelier; your work is in front of you now. "
                              "Begin with ATELIER:", think, fable, state, today, search=search, room=room, atelier=True)
        if again:
            text, who = (again if again.upper().startswith("ATELIER:") else "ATELIER: " + again), who2
    if text is None:
        state["last_activity"] = now; _save(STATE, state); return lines + ["he let it be"]
    if text.upper().startswith("ATELIER:"):
        text = text[len("ATELIER:"):].strip()
        if where not in (state.get("atelier") or []):
            root = api("chat.postMessage", {"channel": channel, "text": ATELIER_ROOT.format(dot=dot)})
            where = root.get("ts")
            state["atelier"] = ((state.get("atelier") or []) + [where])[-50:]
            state["since"] = max(float(state["since"]), float(where or 0))
    elif text.upper().startswith("TANGENT:"):
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
