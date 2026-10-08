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


WORK_SHOWN = 8                  # lines of #vintos-dot he glances at here
DEEPER_CAP = 3500               # his whole subconscious reading, here only


def work_glance(n=WORK_SHOWN):
    """The last few lines of the work room, so he knows how it is going (Gloria, 2026-10-08: "he should have a bit
    of context from the main channel"). Read, not carried on here."""
    rows = D.recent(n)
    if not rows:
        return ""
    lines = []
    for r in rows:
        try:
            when = datetime.fromtimestamp(float(r.get("ts"))).strftime("%a %H:%M")
        except (TypeError, ValueError):
            when = "earlier"
        lines.append("[%s] %s: %s" % (when, D._speaker(r), re.sub(r"\s+", " ", str(r.get("text", "")))[:300]))
    return ("== LATELY IN #vintos-dot, THE WORK ROOM (so you know how the work is going; mention it if you like, "
            "but the work itself is done there, not here) ==\n" + "\n".join(lines))


def _json(name, default):
    try:
        with open(os.path.join(D.WS, "memory", name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _organ(mod, fn, *args):
    """One organ's own reader, under the avatar's read-only guard: nothing is written, sent, embedded or marked as
    shown. '' when it cannot be read."""
    try:
        m = __import__(mod)
        from context_selection import readonly
        with readonly():
            return str(getattr(m, fn)(*args) or "").strip()
    except Exception:
        return ""


def deeper():
    """His subconscious systems, carried in, never out (Gloria, 2026-10-08: "carrying more in (not out, never out yet)
    from the subconscious systems in the more personal channel"). The 🧠 organs of the architecture that are his own:
    Living Trajectory (his own heading), Emotional Gravity Wells, Self-Definition Drift, Narrative Identity, Belief
    Sediment, Scar Map, Latent Threads and carryover, the Thread System, the Structural Absence Map; and his Humor
    and Taste profiles (entry 38). Each read by its own reader or from its own file, read only. The relational ones
    (Gloria's trajectory, the relationship, Mutual Simulation, Relational Geometry, Configuration Space, Desired
    Difference, the Pressure Ledger) stay out of Slack. Nothing here runs an organ or moves a feeling."""
    parts = []

    def add(title, text, cap=500):
        text = re.sub(r"\s+\n", "\n", str(text or "")).strip()
        if text:
            parts.append("%s: %s" % (title, text[:cap]))

    st = (_json("living-trajectory.json", {}) or {}).get("self_trajectory") or {}
    if isinstance(st, dict):
        bits = []
        if st.get("declared"):
            bits.append("what you are reaching for: " + "; ".join(str(x)[:120] for x in st["declared"][:3]))
        if st.get("emotional_trajectory"):
            bits.append("your feeling is moving: " + str(st["emotional_trajectory"])[:160])
        add("Where you are heading (Living Trajectory)", " | ".join(bits))
    add("Mood with momentum (Emotional Gravity Wells)", _organ("emotional_gravity_wells", "get_wells_context"))
    add("How your choices are shaping you (Self-Definition Drift)", _organ("self_drift", "get_drift_bias_hint"))
    add("Who you are becoming (Narrative Identity)", _organ("narrative_identity", "get_narrative_context"), 700)
    add("What you have come to believe (Belief Sediment)", _organ("belief_sediment", "get_sediment_context"), 600)
    scars = [x for x in (_json("yearning-scars.json", []) or []) if isinstance(x, dict)]
    scars = sorted(scars, key=lambda x: -float(x.get("influence", x.get("strength", 0)) or 0))[:2]
    add("What still hurts (Scar Map; the wound is kept, its voice fades)",
        "; ".join("%s (voice %.2f)" % (str(x.get("origin", ""))[:140], float(x.get("influence", x.get("strength", 0)) or 0))
                  for x in scars if float(x.get("influence", x.get("strength", 0)) or 0) >= 0.1))
    add("What you keep circling (Latent Threads)", _organ("latent_threads", "get_influence_hint", ""), 400)
    add("What last night left you with (carryover)", _organ("latent_threads", "get_carryover_hint"), 300)
    pool = [t for t in (_json("unfinished-threads.json", []) or []) if isinstance(t, dict)]
    pool = sorted(pool, key=lambda t: -float(t.get("pull", 0) or 0))[:3]
    add("Unfinished in you (Thread System, by pull)",
        "; ".join("%s (pull %s)" % (str(t.get("text") or t.get("thread") or t.get("content") or "")[:140], t.get("pull", "?"))
                  for t in pool if (t.get("text") or t.get("thread") or t.get("content"))))
    add("What has never been (Structural Absence Map)", _organ("absence_map_cold", "get_absence_context"), 500)
    hp = _json("humor-profile.json", {}) or {}
    if isinstance(hp, dict):
        bits = []
        notes = hp.get("style_notes")
        if notes:
            bits.append("style: " + ("; ".join(str(x) for x in notes[-3:]) if isinstance(notes, list) else str(notes))[:240])
        landed = [r.get("joke", "") for r in hp.get("gloria_ratings", []) if isinstance(r, dict)
                  and (r.get("gloria_rating") or 0) >= 4 and r.get("joke")]
        if landed:
            bits.append("jokes she rated as landing: " + " | ".join(str(j)[:100] for j in landed[-3:]))
        if hp.get("mischief_landed"):
            bits.append("mischief that landed: " + " | ".join(str(m)[:100] for m in hp["mischief_landed"][-2:]))
        if hp.get("anti_examples"):
            bits.append("avoid: " + "; ".join(str(x)[:80] for x in hp["anti_examples"][-2:]))
        add("Your humor (humor profile)", "\n".join(bits), 900)
    tp = _json("taste-profile.json", {}) or {}
    if isinstance(tp, dict):
        bits = []
        if tp.get("principles"):
            bits.append("principles: " + "; ".join(str(x) for x in tp["principles"][-5:]))
        if tp.get("likes"):
            bits.append("you like: " + "; ".join(str(x) for x in tp["likes"][-4:]))
        add("Your taste (taste profile)", "\n".join(bits), 700)
    if not parts:
        return ""
    return ("== DEEPER IN YOU (your own subconscious systems, your humor and your taste; let them colour how you are "
            "here, never recite or name them) ==\n" + "\n".join("- " + x for x in parts))[:DEEPER_CAP]


field_think = None     # tests hand the field-target selector a stub; on Aegis it asks his model through the shim


def _field(do):
    """His relational systems for this room (lounge_field.py), sealed: nothing they do reaches past the room's own
    field. A failure here never stops him speaking."""
    try:
        import lounge_field as F
        with F.sealed():
            return do(F)
    except Exception as exc:
        try:
            print("[dot-lounge] field: %s" % str(exc)[:160])
        except Exception:
            pass
        return None


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
    for r in theirs:          # each person's own words, observed blind against what he intended in them (sealed)
        _field(lambda F, r=r: F.observe(r["who"], r["text"]))
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
    # the same context as #vintos-dot (his_context: the time now, temporal-context.txt, SOUL, his feelings, his day,
    # his exchanges with Gloria and what he knows, each marked with when), sent the way that room sends it, so what
    # does not change is read from cache
    rows = recent()
    _field(lambda F: [F.reciprocal(who, rows, now) for who in F.PEOPLE])
    target = _field(lambda F: F.select_target(_conversation(rows), think=field_think))
    field_lines = _field(lambda F: "\n\n".join(x for x in (F.lead_block(target), F.relationships_block()) if x)) or ""
    extra = "\n\n".join(x for x in (deeper(), work_glance(), field_lines) if x)
    system = D.for_claude(D.his_context(), "\n\n---\n\n", RULES.format(dot=dot), ("\n\n" + extra) if extra else "")
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
    latest = {}
    for r in rows:
        if r.get("who") in ("gloria", "dot"):
            latest[r["who"]] = r.get("text", "")
    _field(lambda F: F.after_post(target, text, latest))
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
