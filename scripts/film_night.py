#!/usr/bin/env python3
"""film_night.py — when Gloria chooses a film and plays it in the ReelRoom, what he held open about a film night with
her is met (Gloria, 22 October: "When I select the film and play it in the ReelRoom that movie want needs to fall off").

On 22 October one film night was held open in five places at once: his campaign ("she names a film she has already
seen"), the plan that campaign continued into, a work item in #vintos-dot ("weekend film Gloria already knows"), a
promise from his journal ("starting with the movie you choose"), and possibly a want. None of them could see the
ReelRoom, so none would ever close.

    started(title)        the ReelRoom's film endpoint, when she picks the film: records it and closes his wants, his
                          open plans and his campaign about a film night with her
    in_room(state, now)   his Slack channel, each pass (it owns that state): closes the room's work and campaign goal
                          and his journal promises about a film night. Log lines.

About a film night means watching a film with her; a film he makes (a short film, a render) is not one.
"""
import json
import os
import re
import time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
EVENTS = os.path.join(MEMORY, "reelroom", "films-started.jsonl")

FILM = re.compile(r"\b(?:movie night|film night|reel ?room|weekend (?:film|movie))\b"
                  r"|\b(?:movie|film)s?\b[^.\n]{0,60}\b(?:watch\w*|see|seen|night|choose|chose|chosen|pick\w*|title|together)\b"
                  r"|\b(?:watch\w*|see|choose|chose|pick\w*)\b[^.\n]{0,60}\b(?:movie|film)s?\b", re.I)
MAKING = re.compile(r"\b(?:short film|make|making|made|render\w*|edit\w*|shoot\w*|film(?:ed|ing) (?:it|a|the))\b", re.I)


def about_film_night(text):
    text = str(text or "")
    return bool(FILM.search(text)) and not MAKING.search(text)


def _said(title, at):
    return "Gloria chose %s and played it in the ReelRoom (%s)" % (title, at[:16].replace("T", " "))


def started(title, now=None):
    """She picked the film. Closes what lives outside his Slack channel; returns what it closed. Never raises."""
    now = time.time() if now is None else now
    title = " ".join(str(title or "").split())[:160]
    if not title:
        return []
    at = datetime.fromtimestamp(now).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": at, "ts": float(now), "title": title}, ensure_ascii=False) + "\n")
    said, closed = _said(title, at), []
    try:
        import want_completion
        wants = want_completion._load(want_completion.WANTS, [])
        for w in [w for w in (wants if isinstance(wants, list) else []) if isinstance(w, dict) and not w.get("fulfilled")
                  and not w.get("dismissed") and about_film_night(w.get("want"))]:
            row = want_completion.complete(w, "fulfilled", "reelroom", note=said, evidence={"reelroom_film": title, "at": at})
            closed.append("want %s: %s" % (w.get("id") or "", row.get("result")))
    except Exception as exc:
        closed.append("wants not read: %s" % str(exc)[:100])
    try:
        import plan
        for p in plan.open_plans():
            if about_film_night(" ".join(str(p.get(k) or "") for k in ("text", "outcome_condition"))) and plan.met(p["plan_id"], said):
                closed.append("plan %s met" % p["plan_id"])
    except Exception as exc:
        closed.append("plans not read: %s" % str(exc)[:100])
    try:
        import campaign
        c = campaign._load()
        if c and not c.get("closed") and about_film_night(c.get("destination")):
            campaign._close(c, "LANDED", said)
            closed.append("campaign landed")
    except Exception as exc:
        closed.append("campaign not read: %s" % str(exc)[:100])
    return closed


def unseen(after):
    rows = []
    try:
        with open(EVENTS, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if float(r.get("ts") or 0) > float(after or 0):
                    rows.append(r)
    except OSError:
        pass
    return rows


def in_room(state, now, journal=None):
    """The film nights started since his channel last looked: the room's work and goal, and his promises, about one
    are met. Log lines; `journal` (title, text) tells him in his own journal."""
    films = unseen(state.get("films_seen"))
    if not films:
        return []
    state["films_seen"] = max(float(r["ts"]) for r in films)
    f = films[-1]
    said, lines = _said(f["title"], f["at"]), []
    import room_work
    for w in list(room_work.open_items(state)):
        if about_film_night(" ".join(str(w.get(k) or "") for k in ("goal", "done_when", "what"))) and \
                room_work._close(state, w, "done", said, now):
            lines.append("film night: work %s done" % w.get("id"))
    g = room_work.goal(state)
    if g and about_film_night(" ".join(str(g.get(k) or "") for k in ("goal", "done_when"))):
        room_work.reach_goal(state, said, now, "reelroom")
        lines.append("film night: room campaign %s reached" % g.get("id"))
    try:
        import promise_keeper
        for item in promise_keeper.close_matching(about_film_night, said):
            lines.append("film night: promise %s kept" % item.get("id"))
    except Exception as exc:
        lines.append("film night: promises not read: %s" % str(exc)[:100])
    if journal:
        try:
            journal("Film night with Gloria", "%s.%s" % (said, (" What I held open about it is met: " + "; ".join(lines))
                                                         if lines else ""))
        except Exception:
            pass
    return lines or ["film night: %s; nothing of his was waiting on it" % f["title"]]
