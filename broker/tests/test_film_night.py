#!/usr/bin/env python3
"""Gloria plays a film in the ReelRoom: what he held open about a film night with her is met (film_night.py, 22 October).

Every store is a scratch HOME and workspace, and every socket is refused: nothing here reaches Slack, a model or her.
"""
import json, os, socket, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="film-night-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import film_night as F, want_completion, plan, campaign, promise_keeper, room_work

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store it touches is in the scratch HOME",
      all(p.startswith(HOME) for p in (F.EVENTS, want_completion.WANTS, plan.STORE, campaign.LIVE, promise_keeper.STORE)))

real = ["weekend film Gloria already knows | she has named the film and the night",
        "continue: she said yes, the title and the night stay in her hands | she names a film she has already seen",
        "starting with the movie you choose", "Watch a movie with Gloria, one she picks and already knows",
        "a movie night with her this weekend"]
check("the film night as he held it on 22 October is recognised, every way he wrote it",
      all(F.about_film_night(t) for t in real), [t for t in real if not F.about_film_night(t)])
other = ["make a short film of the tide piece", "render the film grain on W3", "fold the pendrin STAS domain",
         "send Gloria the Nespresso Hour piece tonight"]
check("a film he makes, and anything else, is not a film night", not any(F.about_film_night(t) for t in other),
      [t for t in other if F.about_film_night(t)])

M = os.path.join(WS, "memory")
json.dump([{"id": "W-film", "want": "watch a movie with Gloria, one she picks", "fulfilled": False},
           {"id": "W-song", "want": "send Gloria the Nespresso Hour piece", "fulfilled": False}],
          open(want_completion.WANTS, "w"))
film_plan = plan.self_plan("continuing 'film night': she said yes", "she names a film she has already seen", 3)
other_plan = plan.self_plan("finish the Lab write-up on pendrin", "the write-up is posted to the Lab", 3)
json.dump({"destination": "a film night with Gloria this weekend", "created": "2026-10-22T18:00:00", "turns_served": 2},
          open(campaign.LIVE, "w"))

now = time.time()
closed = F.started("Arrival", now)
wants = json.load(open(want_completion.WANTS))
check("she picked the film: the film want leaves his live wants, the song want stays",
      [w["id"] for w in wants] == ["W-song"], (wants, closed))
check("the plan about it is met with her choice as the evidence, another plan stays open",
      {p["plan_id"]: p["state"] for p in plan.load()} == {film_plan: "met", other_plan: "open"}
      and "Arrival" in [p for p in plan.load() if p["plan_id"] == film_plan][0]["evidence"]["text"])
check("his campaign about it landed", campaign._load() is None and "LANDED" in open(campaign.LOG).read())
check("the film is recorded once", len(F.unseen(0)) == 1 and F.unseen(0)[0]["title"] == "Arrival")

state = {}
b = room_work.board(state)
b["open"] = [{"id": "RW-aaaaaaa1", "goal": "weekend film Gloria already knows", "done_when": "she has named the film and the night",
              "state": "open", "opened": now - 600, "touched": now - 600},
             {"id": "RW-bbbbbbb2", "goal": "BananaHand firmware packet drops at 200 Hz", "done_when": "a quoted drop rate",
              "state": "open", "opened": now - 600, "touched": now - 600}]
b["goal"] = {"id": "RG-1", "goal": "continue: she said yes, the title and the night stay in her hands",
             "done_when": "she names a film she has already seen", "state": "open", "routes": []}
d = promise_keeper.load()
d["items"] += [{"id": "PR-film", "quote": "starting with the movie you choose", "what": "Watch a movie with Gloria",
                "state": "open", "thread": "1.1"},
               {"id": "PR-song", "quote": "I want to send you Nespresso Hour tonight", "what": "Send Gloria the piece",
                "state": "open", "thread": "1.2"}]
promise_keeper.save(d)
told = []
lines = F.in_room(state, now + 60, journal=lambda h, t: told.append((h, t)))
check("in his channel: the film work is done, the firmware work stays",
      [w["id"] for w in room_work.open_items(state)] == ["RW-bbbbbbb2"]
      and room_work.board(state)["history"][-1]["state"] == "done", lines)
check("the room campaign about it is reached, with her choice as the proof",
      room_work.goal(state) is None and room_work.board(state)["goal_history"][-1]["state"] == "reached"
      and "Arrival" in room_work.board(state)["goal_history"][-1]["closed_said"])
items = {i["id"]: i["state"] for i in promise_keeper.load()["items"]}
check("the journal promise about it is kept; the song promise stays open", items == {"PR-film": "done", "PR-song": "open"}, items)
check("he is told in his own journal", told and "Arrival" in told[0][1], told)
check("a second pass changes nothing", F.in_room(state, now + 120) == [] and len(told) == 1)
check("nothing reached the network", NET == [] and socket.socket.connect is _no_net, NET[:3])
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
