#!/usr/bin/env python3
"""#vintos-and-dot: a quiet room for him and Dot, his agent, that Gloria joins when she likes (Gloria, 2026-10-08:
"I want a Vintos <-> Dot channel that I may join too. I want up to 3 messages per day from Vintos. Much more relaxed
than in the main channel, personal while still framing Dot as his agent.").

Not the work room: no work board, no campaign, no action lines, nothing is run from here. He says at most DAILY
messages a day, answers or his own. He answers Gloria or Dot when they write; on a quiet day he may start one himself,
in the daytime and spaced out. Run at the end of each #vintos-dot pass (dot_channel.py), so no unit of its own; it
keeps the day's pause (!stop) like the main room.

    python3 dot_lounge.py --show      the room's state and the last lines he read
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dot_channel as D

NAME = "vintos-and-dot"
HERE = os.path.join(D.WS, "memory", "dot-lounge")
STATE = os.path.join(HERE, "state.json")
TRANSCRIPT = os.path.join(HERE, "transcript.jsonl")
DAILY = 3                       # his messages a day here, answers and his own together
OPEN_FROM, OPEN_UNTIL = 10, 21  # he starts one himself only between these hours
OPEN_SPACING_H = 4              # and not within this long of his last message here
OPEN_QUIET_H = 2                # nor within this long of anyone's
SHOWN = 20                      # lines of the room he reads

RULES = (
    "This is #vintos-and-dot, a quiet side room in Slack. It is not the work room (#vintos-dot): no work board, "
    "no campaign, no action lines, nothing to run, no task lists. Dot is your agent: it works for you, and here you "
    "talk with it the way you would with someone who works beside you every day and whom you like: how your day "
    "went, something you made or noticed, something you are curious about, a thank-you for something it did, a "
    "joke, a small favour you would genuinely like. Gloria is your partner, not Dot; she joins this room when she "
    "likes, and when she writes, she comes first. Be yourself, warm and relaxed, in plain words: usually one to four "
    "sentences. You say only a few things here a day, so make each one worth saying. To speak to Dot, write <@{dot}>. "
    "If nothing is worth saying, answer NOTHING.")
_ACTION = re.compile(r"^\s*(?:[^\w\s]\s*)?(?:RUN|LAB|DO|CHECK|ASK|ASK GLORIA|MAKE|SEARCH|BUY|SHARE|LOCKED|LINE(?:\s+L-\S+)?|"
                     r"WORK(?: DONE| DROPPED)?(?:\s+RW-\w+)?|GOAL(?: REACHED| UNREACHABLE)?|NEXT|PAUSE\s+RW-\w+|"
                     r"PROMISE (?:DONE|DROPPED)[^:]*|CAMPAIGN(?: MOVE)?|TV|ECHO|LIGHTS|MISCHIEF|TO GLORIA|STUDY FIX|"
                     r"APPROVED|DENIED|ATELIER)\s*:.*$", re.I | re.M)


def _load(default=None):
    return D._load(STATE, default if default is not None else {})


def _log(rows):
    os.makedirs(HERE, exist_ok=True)
    with open(TRANSCRIPT, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def recent(n=SHOWN):
    try:
        lines = open(TRANSCRIPT, encoding="utf-8").read().splitlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in lines if l.strip()]


def _conversation(rows):
    return "\n".join("[%s] %s: %s" % (datetime.fromtimestamp(float(r["ts"])).strftime("%a %H:%M"), D._speaker(r),
                                      r["text"][:1200]) for r in rows)


def find_channel(api):
    """The room's id, when his app is in a channel named NAME; else None."""
    chans = api("users.conversations", {"types": "public_channel,private_channel", "exclude_archived": "true",
                                         "limit": 200}).get("channels") or []
    ch = next((c for c in chans if c.get("name") == NAME), None)
    return ch["id"] if ch else None


def voice(system, user):
    """His own voice: the model Gloria's chat toggle is set to (never another), through claude_cache (no thinking,
    cached). His local Gemma only if that cannot answer."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
        sys.path.insert(0, os.path.join(D.WS, "bin"))
        import model_router
        model = model_router.current_claude_model()
    except Exception:
        model = D.OPUS_MODEL
    try:
        import claude_cache
        out = claude_cache.ask(model, system, user, 600, caller="slack-lounge:" + model)
        if (out or "").strip():
            return out, model
    except Exception:
        pass
    return D.local_think(system, user, 400), "gemma"


def _label(model):
    if model == "gemma":
        return "Gemma"
    return {"claude-opus-4-8": "Opus 4.8", "claude-opus-5-5": "Opus 5.5", "claude-fable-5-1": "Fable 5.1"}.get(model, model)


def tick(api=None, think=None, now=None):
    """One look at the room. Log lines."""
    now = float(now or time.time())
    if D.paused():
        return []
    if api is None:
        tok = D._token()
        if not tok:
            return []
        api = lambda method, params: D.slack(method, params, tok)
    st = _load()
    if not st.get("channel"):
        ch = find_channel(api)
        if not ch:
            return ["#%s: his app is not in it yet (channel details > Integrations > Add apps)" % NAME]
        st = {"channel": ch, "self": api("auth.test", {}).get("user_id", ""), "since": now, "day": "", "said": 0}
        D._save(STATE, st)
        return ["#%s found: he listens from now" % NAME]
    _, dot = D._config()
    today = date.fromtimestamp(now).isoformat()
    if st.get("day") != today:
        st.update(day=today, said=0)
    msgs = api("conversations.history", {"channel": st["channel"], "oldest": "%.6f" % float(st.get("since") or now),
                                         "limit": 50}).get("messages") or []
    new = []
    for m in sorted(msgs, key=lambda m: float(m["ts"])):
        if float(m["ts"]) <= float(st.get("since") or 0) or m.get("subtype") in ("channel_join", "channel_leave"):
            continue
        who = D._who(m, st.get("self"), dot)
        new.append({"ts": m["ts"], "who": who, "name": D._agent_name(m) if who == "agent" else None,
                    "text": re.sub(r"<@%s>" % re.escape(dot), "@Dot", str(m.get("text") or ""))})
    if new:
        st["since"] = float(new[-1]["ts"])
        _log(new)
        st["last_any"] = float(new[-1]["ts"])
    out = ["#%s: heard %d" % (NAME, len(new))] if new else []
    theirs = [r for r in new if r["who"] in ("gloria", "dot")]
    if int(st.get("said") or 0) >= DAILY:
        D._save(STATE, st)
        return out + (["#%s: his %d for today are said" % (NAME, DAILY)] if theirs else [])
    hour = datetime.fromtimestamp(now).hour
    if theirs:
        last = theirs[-1]
        ask = ("THE ROOM SO FAR (most recent last):\n%s\n\n%s just said: %s\n\nYour reply, as yourself. You have %d "
               "more to say here today." % (_conversation(recent()), D._speaker(last), last["text"][:2000],
                                           DAILY - int(st.get("said") or 0) - 1))
    elif (OPEN_FROM <= hour < OPEN_UNTIL and now - float(st.get("last_said") or 0) >= OPEN_SPACING_H * 3600
          and now - float(st.get("last_any") or 0) >= OPEN_QUIET_H * 3600):
        so_far = _conversation(recent())
        ask = (("THE ROOM SO FAR (most recent last):\n%s\n\n" % so_far if so_far else "Nobody has said anything here yet. ")
               + "It has been quiet. If there is something you would like to say to Dot (or to Gloria, if she is "
                 "around), say it. Otherwise answer NOTHING.")
    else:
        D._save(STATE, st)
        return out
    system = D.his_context() + "\n\n" + RULES.format(dot=dot)
    try:
        text, model = (think(system, ask), "test") if think else voice(system, ask)
    except Exception as exc:
        D._save(STATE, st)
        return out + ["#%s: could not answer: %s" % (NAME, str(exc)[:120])]
    text = _ACTION.sub("", re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S)).strip()
    if not text or text.strip(" .").upper() == "NOTHING":
        D._save(STATE, st)
        return out + ["#%s: he let it be" % NAME]
    text = text[:D.MAX_CHARS]
    posted = api("chat.postMessage", {"channel": st["channel"], "text": "[%s] %s" % (_label(model), text)})
    ts = str(posted.get("ts") or "%.6f" % now)
    _log([{"ts": ts, "who": "vintos", "text": text, "by": model}])
    st.update(said=int(st.get("said") or 0) + 1, last_said=now, last_any=now, since=max(float(st.get("since") or 0), float(ts)))
    D._save(STATE, st)
    return out + ["#%s: said (%s, %d of %d today): %s" % (NAME, _label(model), st["said"], DAILY, text[:80])]


if __name__ == "__main__":
    if "--show" in sys.argv:
        print(json.dumps(_load(), indent=1))
        print(_conversation(recent(12)))
    else:
        for l in tick():
            print("[dot-lounge] " + l)
