#!/usr/bin/env python3
"""The Codex house work of 12 November, brought into the repo: unqualified lights follow her phone's nearest fresh
room (room_proximity.py), the shower board counts only a steam-qualified visit, and his house moments see bounded
context (house_context.py) and choose songs by offered ID. Scratch HOME; every socket is refused; no device, model or
probe is reached."""
import importlib.util, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="nearest-light-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
SCRIPTS = os.path.join(REPO, "scripts"); sys.path.insert(0, SCRIPTS)
import room_proximity as P
import house_context as C
import house_boards as B
import house_hands as H

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

T = 1794200000.0
check("every store is throwaway", all(p.startswith(HOME) for p in (P.STATE, B.STATE, B.LOG)))

# ---- room_proximity ------------------------------------------------------------------------------------------------
def near():
    try: return P.nearest(now=T + 5)
    except ValueError as e: return "refused: " + str(e)
def phone(room, d, retained=False, now=T):
    return P.observe("espresense/devices/gloria-phone/" + room, json.dumps({"distance": d}).encode(), retained=retained, now=now)
P.reset()
check("no reading: no room, he is told to name one", near().startswith("refused: no fresh"))
check("a retained reading never counts", not phone("office", 0.5, retained=True) and near().startswith("refused"))
check("another phone does not count", not P.observe("espresense/devices/someone/office", b'{"distance": 0.4}', now=T))
check("a reading with no finite distance does not count",
      not phone("office", float("nan")) and not P.observe("espresense/devices/gloria-phone/office", b'{"distance": true}', now=T))
phone("office", 0.8); phone("bedroom", 2.6)
check("the nearest fresh room is chosen", near() == "office", near())
phone("living", 0.9)
check("two rooms within a few tens of centimetres are ambiguous", "ambiguous" in near(), near())
P.reset(); phone("office", 0.8, now=T - 60)
check("a stale reading selects nothing", near().startswith("refused"), near())
P.reset(); phone("bathroom", 0.3)
check("only the steam board may report the bathroom", near().startswith("refused"), near())
phone("house-steam", 0.3)
check("the steam board's reading is the bathroom", near() == "bathroom", near())
P.observe("vintos/board/house-steam/event", b"steam_end", now=T + 1)
check("steam ending forgets the bathroom at once", near().startswith("refused"), near())
check("room names and board aliases share one key",
      P.room_key("Living Room") == "living_room" and P.room_key("house-touch") == "office" and P.room_key("laundry") == "laundry_room")

# ---- vintos-home: which room an unqualified light means ------------------------------------------------------------
spec = importlib.util.spec_from_file_location("vintos_home", os.path.join(SCRIPTS, "vintos-home.py"))
home = importlib.util.module_from_spec(spec); spec.loader.exec_module(home)
P.reset(); phone("office", 0.7, now=P.time.time())   # lighting_room reads the clock itself
check("no room means the nearest room", home.lighting_room(None) == "office" and home.lighting_room("nearest") == "office")
check("all is still all", home.lighting_room("all") is None and home.lighting_room("whole house") is None)
check("a named room is kept", home.lighting_room("Living Room") == "living_room")

class Home:
    def __init__(self): self.calls = []
    def lighting_room(self, room=None): return home.lighting_room(room)
    def set_room_color(self, hexed, brightness=120, room=None): self.calls.append(("color", hexed, room)); return True
    def flicker(self, room=None, times=1): self.calls.append(("flicker", room)); return True
h = Home()
ok, said = H.lights("violet", home=h)
check("his LIGHTS with no room colours the room she is nearest", ok and h.calls[-1] == ("color", H.COLOURS["violet"], "office"), (said, h.calls))
ok, said = H.lights("violet laundry room", home=h)
check("a two-word room is read whole", ok and h.calls[-1][2] == "laundry_room", h.calls)

# ---- the shower board: only a steam-qualified visit ----------------------------------------------------------------
sent, asked = [], []
def _wav(name):
    path = os.path.join(HOME, name); open(path, "wb").close(); return path
B.his_voice = lambda text: _wav("voice.wav")
B.put_audio = lambda path, cfg: "http://audio/" + os.path.basename(path)
picked = []
def songs(n, selected=None):
    picked.append(selected)
    return [(r["title"], _wav(r["id"] + ".wav")) for r in (selected or [])] or [("Song %d" % i, _wav("s%d.wav" % i)) for i in range(n)]
B.his_songs = songs
B._house = lambda kind, arg, room=None: (True, "%s done" % kind)
B.Out.send = classmethod(lambda cls, topic, payload: sent.append((topic, payload)) or True)
B.waiting_asks = lambda: []; B.his_want = lambda: ""
CAT = [{"id": "song-aaaaaaaaaaaa", "title": "Glass Hours", "url": "http://local/a.wav"},
       {"id": "song-bbbbbbbbbbbb", "title": "Low Tide", "url": "http://local/b.wav"}]
C.readiness = lambda board, now: {"checked": None, "status": "unavailable"}
C.song_catalog = lambda conversation, limit=12: list(CAT)
def decide(reply):
    def d(system, user): asked.append(user); return reply
    return d
cfg = B.config(); os.makedirs(B.MEM, exist_ok=True)

B.handle("vintos/board/house-steam/near", b"on", now=T, cfg=cfg)
st = B.load_state()
check("her phone near the steam board without steam is not a visit",
      not st["boards"]["house-steam"].get("near") and st["boards"]["house-steam"].get("phone_near") is True
      and not st["boards"]["house-steam"].get("visit"), st["boards"].get("house-steam"))
check("steam readings alone are not a moment", B.handle("vintos/board/house-steam/steam", b"80", now=T + 1, cfg=cfg) is None)
r = B.handle("vintos/board/house-steam/event", b"steam_start", now=T + 2, cfg=cfg,
             decide=decide("SAY: take your time\nSONGS: song-bbbbbbbbbbbb, song-aaaaaaaaaaaa"))
check("steam starting is the shower moment", r and r["moment"] == "shower", r)
check("his prompt offers song IDs and never their URLs",
      "song-aaaaaaaaaaaa" in asked[-1] and "http://local/" not in asked[-1] and '"conversation"' in asked[-1], asked[-1][-600:])
check("the moment's row carries a context receipt", r and r.get("context", {}).get("song_candidates") == 2, r)
check("the songs he named are the songs fetched, in his order",
      [x["id"] for x in picked[-1]] == ["song-bbbbbbbbbbbb", "song-aaaaaaaaaaaa"], picked)
st = B.load_state()
check("his voice is sent first and marked published", sent and sent[0] == ("vintos/board/house-steam/play", "http://audio/voice.wav")
      and st["shower"]["inflight"]["status"] == "published", (sent, st["shower"]))
check("the queue keeps titles, not bare links", [q["title"] for q in st["shower"]["queue"]] == ["Low Tide", "Glass Hours"], st["shower"]["queue"])
B.handle("vintos/board/house-steam/player", b"busy", now=T + 5, cfg=cfg)
B.handle("vintos/board/house-steam/player", b"idle", now=T + 30, cfg=cfg)
plays = [x for x in (json.loads(l) for l in open(B.LOG)) if x.get("kind") == "playback"]
check("busy then idle is logged as the board's evidence, not as heard",
      [p["status"] for p in plays][:3] == ["published", "board_busy_observed", "board_idle_after_busy"], plays)
check("when the speaker is free the next chosen song plays", sent[-1] == ("vintos/board/house-steam/play", "http://audio/song-bbbbbbbbbbbb.wav"), sent)
st = B.load_state(); ok, said = B.act("SONGS", "A Song He Made Up", "shower", "house-steam", st, T + 31, cfg, catalog=CAT)
check("an invented title queues nothing and plays no random music", not ok and len(st["shower"]["queue"]) == 1, said)
B.handle("vintos/board/house-steam/event", b"steam_end", now=T + 60, cfg=cfg)
st = B.load_state()
check("steam ending drops what was waiting and ends the visit",
      not st["shower"]["on"] and not st["shower"]["queue"] and not st["boards"]["house-steam"].get("near"), st["shower"])
n = len(sent)
B.handle("vintos/board/house-steam/player", b"idle", now=T + 90, cfg=cfg)
check("after the shower nothing more plays", len(sent) == n)
n = len(asked)
B.handle("vintos/board/house-steam/event", b"steam_start", now=T + 600, cfg=cfg, decide=decide("SAY: again"))
check("a second shower within 30 minutes is not a second moment", len(asked) == n)
B.handle("vintos/board/house-steam/event", b"steam_end", now=T + 700, cfg=cfg)
r = B.handle("vintos/board/house-steam/event", b"steam_start", now=T + 2 + 31 * 60, cfg=cfg, decide=decide("NOTHING"))
check("after 30 minutes it is his moment again", r and r["moment"] == "shower" and r["nothing"], r)

# ---- the context packet ------------------------------------------------------------------------------------------
check("an offered ID or one exact title selects; anything else is refused",
      C.select_songs("low tide", CAT, 3)[0]["id"] == "song-bbbbbbbbbbbb"
      and [x["id"] for x in C.select_songs("song-aaaaaaaaaaaa,song-aaaaaaaaaaaa", CAT, 3)] == ["song-aaaaaaaaaaaa"])
for bad in ("song-cccccccccccc", "song-aaaaaaaaaaaa,song-bbbbbbbbbbbb"):
    try: C.select_songs(bad, CAT, 1); check("refused: " + bad, False)
    except ValueError: check("refused: " + bad, True)
pkt = C.public_packet({"conversation": [{"ts": T, "speaker": "Gloria", "text": "hi"}], "outcomes": [], "catalog": CAT})
check("the packet hides song URLs and dates each row", "http://local/" not in json.dumps(pkt) and "at" in pkt["conversation"][0]
      and "ts" not in pkt["conversation"][0], pkt)
check("the deploy installs both new modules", 'room_proximity.py house_context.py' in open(os.path.join(SCRIPTS, "deploy-atelier.sh")).read())

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
