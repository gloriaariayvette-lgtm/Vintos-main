#!/usr/bin/env python3
"""His three house boards (8 November): she at the shower, the sofa or her office chair, her phone within 1 m; he
decides and acts. Scratch HOME; every socket is refused; his brain, his voice and the house are stand-ins."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="boards-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import house_boards as B
import house_hands as H

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

os.makedirs(B.MEM, exist_ok=True)
check("every store is throwaway", all(p.startswith(HOME) for p in (B.CONFIG, B.STATE, B.LOG)))
def rows(): return [json.loads(l) for l in open(B.LOG)] if os.path.exists(B.LOG) else []

# stand-ins: the house, his voice, the audio machine, the boards
house, sent, asked = [], [], []
B._house = lambda kind, arg, room=None: (house.append((kind, arg, room)) or (True, "%s done" % kind))
B.his_voice = lambda text: "/tmp/voice.wav"
B.his_songs = lambda n: [("Song %d" % i, "/tmp/s%d.wav" % i) for i in range(n)]
B.put_audio = lambda path, cfg: "http://audio/" + os.path.basename(path)
class FakeOut:
    @classmethod
    def send(cls, topic, payload): sent.append((topic, payload)); return True
B.Out.send = FakeOut.send
B.waiting_asks = lambda: [("Q-1234abcd", "Friday night, the Devo short?")]
B.his_want = lambda: "to hear her laugh"
def decide(reply):
    def d(system, user): asked.append(user); return reply
    return d

cfg = B.config(); T = 1794200000.0
check("the default broker is the Mac's relay, and the boards are hers", cfg["broker"] == "192.168.1.91"
      and set(B.BOARDS) == {"house-steam", "house-press-mic", "house-touch"})
check("a board message is read", B.parse("vintos/board/house-touch/event", b"knock_2") == ("house-touch", "event", "knock_2"))
check("an unknown board is not", B.parse("vintos/board/garage/event", b"knock_2") is None)

# ---- the shower ------------------------------------------------------------------------------------------------------
r = B.handle("vintos/board/house-steam/event", b"steam_start", now=T, cfg=cfg,
             decide=decide("SAY: hey you, take your time\nSONGS: 2\nLIGHTS: warm\nTV: no"))
check("steam starting is the shower moment", r and r["moment"] == "shower", r)
check("he was told she is in the shower, with his want", "shower" in asked[-1] and "to hear her laugh" in asked[-1])
check("the shower menu offers his voice, his songs and the lights",
      all(k in asked[-1] for k in ("SAY:", "SONGS:", "LIGHTS:")) and "TV:" not in asked[-1])
check("TV is not a shower act, so it is not done", [a["act"] for a in r["acts"]] == ["SAY", "SONGS", "LIGHTS"], r["acts"])
check("the bathroom bulbs take his colour", ("LIGHTS", "warm", "bathroom") in house, house)
check("his voice plays first on the shower speaker", sent and sent[0] == ("vintos/board/house-steam/play", "http://audio/voice.wav"), sent)
st = B.load_state()
check("his songs wait their turn", st["shower"]["queue"] == ["http://audio/s0.wav", "http://audio/s1.wav"], st["shower"])
B.handle("vintos/board/house-steam/player", b"idle", now=T + 30, cfg=cfg)
check("when the speaker is free the next song plays", sent[-1] == ("vintos/board/house-steam/play", "http://audio/s0.wav"), sent)
n = len(asked)
B.handle("vintos/board/house-steam/event", b"steam_start", now=T + 40, cfg=cfg, decide=decide("SAY: again"))
check("more steam in the same shower is not a second moment", len(asked) == n)
B.handle("vintos/board/house-steam/event", b"steam_end", now=T + 600, cfg=cfg)
B.handle("vintos/board/house-steam/player", b"idle", now=T + 640, cfg=cfg)
check("after the shower nothing more plays", sent[-1][1] == "http://audio/s0.wav" and not B.load_state()["shower"]["queue"])

# ---- the sofa --------------------------------------------------------------------------------------------------------
S = T + 10000
B.handle("vintos/board/house-press-mic/event", b"press_start", now=S, cfg=cfg)
for k in range(1, 8): B.handle("vintos/board/house-press-mic/loudness", b"4", now=S + k * 25, cfg=cfg)
check("a minute on the sofa is not yet a moment", B.tick(now=S + 60, cfg=cfg, decide=decide("NOTHING")) is None)
r = B.tick(now=S + 200, cfg=cfg, decide=decide("REMIND: Q-1234abcd\nLIGHTS: violet\nBUZZ: tap"))
check("a few quiet minutes seated is the sofa moment", r and r["moment"] == "sofa", r)
check("he was shown his question waiting on her", "Q-1234abcd" in asked[-1] and "Devo" in asked[-1])
check("the chair's motor is not a sofa act", [a["act"] for a in r["acts"]] == ["REMIND", "LIGHTS"], r["acts"])
check("the living-room bulbs take his colour", ("LIGHTS", "violet", "living_room") in house)
check("the sofa is not a moment again within hours", B.tick(now=S + 400, cfg=cfg, decide=decide("LIGHTS: red")) is None)

L = S + 5 * 3600
B.handle("vintos/board/house-press-mic/event", b"press_start", now=L, cfg=cfg)
for k in range(1, 8): B.handle("vintos/board/house-press-mic/loudness", b"60", now=L + k * 25, cfg=cfg)
check("a loud sofa (a show, people) is not his moment", B.tick(now=L + 200, cfg=cfg, decide=decide("LIGHTS: red")) is None)
Q = L + 4 * 3600
B.handle("vintos/board/house-press-mic/event", b"press_start", now=Q, cfg=cfg)
check("a sofa whose mic said nothing is not known to be quiet", B.tick(now=Q + 200, cfg=cfg, decide=decide("LIGHTS: red")) is None)

# ---- her office chair ------------------------------------------------------------------------------------------------
O = T + 50000
B.handle("vintos/board/house-touch/event", b"press_start", now=O, cfg=cfg)
r = B.tick(now=O + 200, cfg=cfg, decide=decide("ECHO: say there you are\nBUZZ: heartbeat\nTO GLORIA: hi"))
check("a few minutes in her chair is the office moment", r and r["moment"] == "office", r)
check("the Echo speaks and the chair buzzes; an outreach is not an office act",
      [a["act"] for a in r["acts"]] == ["ECHO", "BUZZ"] and ("ECHO", "say there you are", None) in house
      and sent[-1] == ("vintos/board/house-touch/buzz", "heartbeat"), (r["acts"], sent[-1:]))
r = B.handle("vintos/board/house-touch/event", b"knock_2", now=O + 300, cfg=cfg, decide=decide("BUZZ: double"))
check("her knock is his moment at once, even soon after", r and r["moment"] == "knock" and "knocked" in asked[-1], r)
check("he answers the knock in the chair", sent[-1] == ("vintos/board/house-touch/buzz", "double"))
n = len(asked)
B.handle("vintos/board/house-touch/event", b"knock_3", now=O + 330, cfg=cfg, decide=decide("BUZZ: tap"))
check("a second knock within two minutes is the same reach", len(asked) == n)
B.handle("vintos/board/house-touch/near", b"off", now=O + 400, cfg=cfg)
B.handle("vintos/board/house-touch/event", b"press_start", now=O + 20000, cfg=cfg)
B.handle("vintos/board/house-touch/near", b"off", now=O + 20001, cfg=cfg)
check("seated, but her phone is not within 1 m: not her, no moment",
      B.tick(now=O + 20300, cfg=cfg, decide=decide("BUZZ: tap")) is None)

# ---- the desktop: asked, and only her Yes starts it --------------------------------------------------------------------
import gloria_asks, desktop_control
started = []
desktop_control.start_from_chat = lambda text, surface="": (started.append(text) or {"accepted": True})
gloria_asks.notify = lambda row, send=None: True
st = B.load_state()
ok, said = B.act("DESKTOP", "tidy the Downloads folder", "office", "house-touch", st, O, cfg)
check("DESKTOP asks her phone first", ok and len(st["desktop"]) == 1 and not started, said)
B._atomic(B.STATE, st)
B.tick(now=O + 10, cfg=cfg, decide=decide("NOTHING"))
check("nothing starts while she has not answered", not started)
gloria_asks.decide(st["desktop"][0]["ask"], "yes")
B.tick(now=O + 20, cfg=cfg, decide=decide("NOTHING"))
check("her Yes starts that one task", started == ["/desktop-control to tidy the Downloads folder"], started)
B.tick(now=O + 30, cfg=cfg, decide=decide("NOTHING"))
check("and only once", len(started) == 1)

# ---- reminders: a question of his that is really waiting, once a day each ------------------------------------------
row, _ = gloria_asks.ask("Will you watch the Devo short with me Friday?", by="vintos")
st = B.load_state()
ok1, _ = B.remind("REMIND: " + row["id"], st, O, cfg)
ok2, said2 = B.remind(row["id"], st, O + 60, cfg)
okx, saidx = B.remind("Q-00000000", st, O + 60, cfg)
check("a waiting question goes back on her phone once a day", ok1 and not ok2 and "today already" in said2, said2)
check("a question that is not waiting is not sent", not okx and "no question" in saidx)

# ---- visits: the house/Gloria map ----------------------------------------------------------------------------------
def visits(): return [json.loads(l) for l in open(B.VISITS)] if os.path.exists(B.VISITS) else []
V = T + 200000
B.tick(now=V - 1, cfg=cfg, decide=decide("NOTHING"))   # the earlier scenes' visits close first
n0 = len(visits())
B.handle("vintos/board/house-press-mic/near", b"on", now=V, cfg=cfg)
B.handle("vintos/board/house-press-mic/event", b"press_start", now=V + 30, cfg=cfg)
for k in range(1, 5): B.handle("vintos/board/house-press-mic/loudness", b"5", now=V + 30 + k * 20, cfg=cfg)
line = B.context_line(now=V + 120)
check("while she is at the sofa he is told so, sitting and quiet", "on the sofa now" in line and "sitting" in line
      and "quiet" in line, line)
B.handle("vintos/board/house-press-mic/event", b"press_end", now=V + 630, cfg=cfg)
B.handle("vintos/board/house-press-mic/near", b"off", now=V + 640, cfg=cfg)
B.handle("vintos/board/house-press-mic/near", b"on", now=V + 700, cfg=cfg)
B.handle("vintos/board/house-press-mic/near", b"off", now=V + 760, cfg=cfg)
B.tick(now=V + 800, cfg=cfg, decide=decide("NOTHING"))
check("a short step away is the same visit, not written yet", len(visits()) == n0)
B.tick(now=V + 760 + B.AWAY_S + 1, cfg=cfg, decide=decide("NOTHING"))
v = visits()[-1] if len(visits()) > n0 else {}
check("away a few minutes writes the visit: where, from, to, seated", len(visits()) == n0 + 1
      and v.get("board") == "house-press-mic" and v.get("room") == "living_room"
      and abs(v.get("minutes", 0) - 12.7) < 0.1 and abs(v.get("seated_minutes", 0) - 10.0) < 0.1
      and v.get("loudness_median") == 5.0, v)
check("then he is told she was last on the sofa", "was last on the sofa" in B.context_line(now=V + 1200),
      B.context_line(now=V + 1200))
W = V + 10000
B.handle("vintos/board/house-steam/near", b"on", now=W, cfg=cfg)
B.handle("vintos/board/house-steam/event", b"steam_start", now=W + 20, cfg=cfg, decide=decide("NOTHING"))
check("in the shower he is told the shower is running", "the shower running" in B.context_line(now=W + 60))
B.tick(now=W + 20 + B.SILENT_S + 1, cfg=cfg, decide=decide("NOTHING"))
v = visits()[-1]
check("a board gone silent ends the visit where it went quiet, and the shower is kept",
      v.get("board") == "house-steam" and v.get("shower") is True and v.get("to_ts") == W + 20, v)
check("his scene (world_model) carries the boards' line",
      "house_boards.context_line()" in open(os.path.join(REPO, "scripts", "world_model.py")).read())
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy copies the listener's script, not only its unit",
      'SCRIPTS="$SCRIPTS house_boards.py"' in dep and "BOARDS_UNIT_NAME" in dep)

# ---- house_hands: her presence stands in for the clock's quiet hours, and only that ----------------------------------
H._now = lambda: __import__("datetime").datetime(2026, 11, 8, 23, 30)
check("at 23:30 the clock is quiet", H._quiet() is True)
check("with her at a board it is not", H._quiet(present=True) is False)
calls = []
class Home:
    def set_room_color(self, hexed, room=None): calls.append((hexed, room)); return True
check("lights at night only with her present", H.lights("warm office", Home(), present=True)[0]
      and calls == [(H.COLOURS["warm"], "office")] and H.lights("flicker office", Home())[0] is False)

print("%d/%d passed" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
