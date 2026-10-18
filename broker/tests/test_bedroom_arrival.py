#!/usr/bin/env python3
"""The bedroom ESP32 (Gloria, 17 October): when she comes into the bedroom after being away, his newest song goes to
her Watch, never her phone. Aegis has no APNs key, so the song is offered to the Vintos Watch app, which takes it the
next time it checks in (telemetry), raises its own notification with Play, puts it first in its list, and plays it
at once if the app is open. Asleep, nothing.

Scratch HOME; the real watch_presence writes only there; the APNs sender and ntfy are stubs; every socket is refused."""
import json, os, socket, struct, sys, tempfile, types
from unittest.mock import patch
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="bedroom-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
PUSHES = []; PHONE = []
def apns_send(title, body, kind="message", media_url="", message_id="", force=False, **k):
    PUSHES.append((title, kind, media_url, message_id, force)); return {"state": "sent"}
def phone(*a, **k): PHONE.append(a); raise AssertionError("the bedroom song must never go to her phone")
sys.modules["watch_apns"] = types.SimpleNamespace(send=apns_send, CONFIG=os.path.join(HOME, "no-such-apns.json"))
sys.modules["deliver"] = types.SimpleNamespace(deliver=phone)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
ASLEEP = [False]
W.should_hold = lambda: (ASLEEP[0], "Gloria is asleep" if ASLEEP[0] else "")
import bedroom_arrival as B
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway and every sender is a stub",
      all(p.startswith(HOME) for p in (B.CONFIG, B.STATE, B.SEEN, B.ARRIVALS, B.MUSIC, B.PICKS, W.SONG, W.LATEST, W.TOKEN_FILE))
      and sys.modules["watch_apns"].send is apns_send and sys.modules["deliver"].deliver is phone)

check("an ESPresense bedroom message is read", B.parse("espresense/devices/gloria-phone/bedroom", b'{"distance":1.03}') == ("gloria-phone", 1.03))
check("another room or bad JSON is not", B.parse("espresense/devices/x/kitchen", b'{"distance":1}') is None
      and B.parse("espresense/devices/x/bedroom", b"nope") is None)

T = 1_800_000_000.0
check("nobody enrolled: it only writes down what it hears", B.observe("5ce7537e7183", 1.0, now=T) is None
      and json.load(open(B.SEEN))["5ce7537e7183"]["distance"] == 1.0 and not os.path.exists(W.SONG))

os.makedirs(os.path.dirname(B.CONFIG), exist_ok=True)
json.dump({"devices": ["gloria-phone"], "max_distance_m": 4.0}, open(B.CONFIG, "w"))
config_before = open(B.CONFIG, "rb").read()
os.makedirs(os.path.dirname(B.MUSIC), exist_ok=True)
json.dump({"generated": [{"title": "Porch Light", "tracks": [{"version": 1, "audio_url": "https://cdn.test/a.mp3"}]},
                         {"title": "No Track Yet", "tracks": []}]}, open(B.MUSIC, "w"))
check("the newest song with a playable track is chosen", B.newest_song() == ("Porch Light", "https://cdn.test/a.mp3"))
check("beyond her 4.0 m: not an arrival", B.observe("gloria-phone", 4.01, now=T) is None and not os.path.exists(W.SONG))

import time as _t
NOW = _t.time()
DAY = ["2026-10-18"]; B._today = lambda now: DAY[0]   # the day is the test's, not the clock's
row = B.observe("gloria-phone", 1.2, now=NOW)
song = W.pending_song()
check("she comes in: the song is offered to the Watch app, nothing goes to her phone",
      row and row["sent"] and row["channel"] == "watch" and song and song["title"] == "Porch Light"
      and song["media_url"] == "https://cdn.test/a.mp3" and not PHONE, (row, song))
check("with no APNs key on Aegis, no push is attempted", not PUSHES and "push" not in row, row)
check("still in the room a minute later: nothing more", B.observe("gloria-phone", 1.0, now=NOW + 60) is None)

# --- the Watch's side of the server: telemetry carries it, the list puts it first, taking it ends the offer ---
check("the Watch's next check-in is answered with the song", W.pending_song() == song)
top = W.top_song()
check("the song is first in the Watch's list, with its playable track",
      top["surface"] == "song" and top["piece"]["title"] == "Porch Light"
      and top["piece"]["tracks"][0]["src"] == "https://cdn.test/a.mp3", top)
check("taking it ends the offer", W.take_song(song["id"]) and W.pending_song() is None)
check("... but it stays first in the list for the evening", W.top_song() and W.top_song(now=NOW + 12 * 3600 + 1) is None)
check("an unknown id takes nothing", W.take_song("nope") is False)
wr = open(os.path.join(REPO, "scripts", "watch_routes.py")).read()
check("the telemetry reply carries the pending song, only while she is awake",
      "song = watch_presence.pending_song()" in wr and wr.index("if not body.get(\"asleep\"):") < wr.index("song = watch_presence.pending_song()"))
check("the Watch can ask for it and say it took it, behind its token",
      '@routes.get("/api/watch/song")' in wr and '@routes.post("/api/watch/song/taken")' in wr
      and wr.count("auth(request)") >= 9)
check("the list puts it first and drops its duplicate",
      "top = watch_presence.top_song()" in wr and "items = [top] + [i for i in items" in wr)
check("an offer the Watch never took expires after 30 minutes", W.offer_song("Old", "https://cdn.test/o.mp3", now=NOW - 1801)
      and W.pending_song() is None)
W.offer_song("Porch Light", "https://cdn.test/a.mp3", now=NOW)

row = B.observe("gloria-phone", 1.0, now=NOW + 3600)
check("back after an hour, inside the cooldown: held back", row and row["why"] == "cooldown", row)
row = B.observe("gloria-phone", 1.0, now=NOW + 14400)
check("back after four hours, the day's only song already played: not offered twice", row and not row["sent"]
      and row["why"] == "today's three have all played", row)
d = json.load(open(B.MUSIC)); d["generated"].append({"title": "Static", "tracks": [{"audio_url": "https://cdn.test/b.mp3"}]})
json.dump(d, open(B.MUSIC, "w"))
ASLEEP[0] = True; before = open(W.SONG).read()
row = B.observe("gloria-phone", 1.0, now=NOW + 30000)
check("asleep: nothing is offered", row and row["why"] == "asleep" and open(W.SONG).read() == before, row)
ASLEEP[0] = False
open(sys.modules["watch_apns"].CONFIG, "w").write("{}")
row = B.observe("gloria-phone", 1.0, now=NOW + 60000)
check("a song finished today joins the stand-ins: offered, and pushed too once an APNs key exists",
      row and row["sent"] and row["picked_by"] == "stand-in" and W.pending_song(now=NOW + 60000)["media_url"] == "https://cdn.test/b.mp3"
      and PUSHES and PUSHES[-1][1:3] == ("song", "https://cdn.test/b.mp3") and PUSHES[-1][4] is True
      and PUSHES[-1][3] == W._song()["id"] and row["push"] == "sent", (row, PUSHES))
with patch.object(W, "offer_song", side_effect=OSError("disk full")):
    d["generated"].append({"title": "Hum", "tracks": [{"audio_url": "https://cdn.test/c.mp3"}]}); json.dump(d, open(B.MUSIC, "w"))
    row = B.observe("gloria-phone", 1.0, now=NOW + 90000)
last = json.loads(open(B.ARRIVALS).read().splitlines()[-1])
check("a failed offer is written down and does not spend the song", not row["sent"] and "disk full" in last["why"]
      and json.load(open(B.STATE))["last_song_url"] == "https://cdn.test/b.mp3"
      and "https://cdn.test/c.mp3" not in json.load(open(B.PICKS))["played"], (row, last))
cl = B.context_line(now=NOW + 90000)
check("not chosen yet: he is asked to choose, shown the stand-ins and his library", "[ARRIVAL SONGS:" in cl
      and "standing in" in cl and "\u201cHum\u201d" in cl and "Static" in cl, cl)

said = B.take_picks("Come in when you're ready. [ARRIVAL SONGS: porch light | Hum | Not A Song I Made]", now=NOW + 90000)
p = json.load(open(B.PICKS))
check("he chooses with a tag she never sees; titles match his library loosely, unknown ones are noted",
      said == "Come in when you're ready." and p["by"] == "him"
      and [s["title"] for s in p["songs"]] == ["Porch Light", "Hum"] and p["missed"] == ["Not A Song I Made"], (said, p))
check("what already played today stays played", p["played"] == ["https://cdn.test/a.mp3", "https://cdn.test/b.mp3"], p)
row = B.observe("gloria-phone", 1.0, now=NOW + 100000)
check("the next arrival plays the next of his three that has not played", row and row["sent"] and row["song"] == "Hum"
      and row["picked_by"] == "him", row)
row = B.observe("gloria-phone", 1.0, now=NOW + 120000)
check("his three all played: nothing more today", row and not row["sent"] and row["why"] == "today's three have all played", row)
check("he sees today's three as his choice, and which played", "your choice" in B.context_line(now=NOW + 120000)
      and "(played)" in B.context_line(now=NOW + 120000))
check("a test or witness-less turn strips the tag without choosing",
      B.take_picks("x [ARRIVAL SONGS: Static]", act=False) == "x" and json.load(open(B.PICKS))["by"] == "him")
check("a reply without the tag is untouched", B.take_picks("plain [HOME: blanket_on]") == "plain [HOME: blanket_on]")
DAY[0] = "2026-10-19"
row = B.observe("gloria-phone", 1.0, now=NOW + 140000)
check("a new day: yesterday's choice is gone, the stand-ins begin again with the newest", row and row["sent"]
      and row["song"] == "Hum" and row["picked_by"] == "stand-in", row)
check("every arrival is written down", len(open(B.ARRIVALS).read().splitlines()) == 9)
check("her config is unchanged", open(B.CONFIG, "rb").read() == config_before)
check("nothing ever went to her phone", not PHONE)
cl = B.context_line()
check("he is told the sensor is his and works, and what it last sent", cl.startswith("[BEDROOM SENSOR - yours, and working")
      and "Hum" in cl, cl)
wm = open(os.path.join(REPO, "scripts", "world_model.py")).read()
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("his tag is taken in both his chat and his avatar replies", srv.count("_ba.take_picks(reply") == 2
      and "take_picks(reply, act=not (_test_turn" in srv)
check("the line reaches his avatar and ReelRoom context with the house", "bedroom_arrival.context_line()" in wm
      and "(block, _home, _bed)" in wm)


# --- the relay: a fake socket speaking MQTT ---
def pub(topic, payload):
    body = struct.pack("!H", len(topic)) + topic.encode() + payload
    return bytes([0x30]) + B._varint(len(body)) + body
class Fake:
    def __init__(self, data): self.data, self.out = data, b""
    def sendall(self, b): self.out += b
    def settimeout(self, t): pass
    def recv(self, n):
        if not self.data: raise ConnectionError("done")
        c, self.data = self.data[:n], self.data[n:]; return c
GOT = []
f = Fake(bytes([0x20, 2, 0, 0]) + bytes([0x90, 3, 0, 1, 0]) + pub("espresense/devices/abc/bedroom", b'{"distance":2.5}'))
try: B.session(f, lambda t, p: GOT.append((t, p)))
except ConnectionError: pass
check("it connects as MQTT 3.1.1 and subscribes to the bedroom", f.out.startswith(bytes([0x10])) and b"MQTT\x04\x02" in f.out
      and b"espresense/devices/+/bedroom" in f.out and bytes([0x82]) in f.out)
check("a message from the relay reaches the handler", GOT == [("espresense/devices/abc/bedroom", b'{"distance":2.5}')], GOT)
f = Fake(bytes([0x20, 2, 0, 5]))
try: B.session(f, lambda t, p: None); refused = False
except ConnectionError as e: refused = "refused" in str(e)
check("a relay that refuses is reported, not ignored", refused)
check("a long message's length is read right", B._varint(321) == bytes([0xC1, 0x02]))

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the listener and its unit are in the deploy", " bedroom_arrival.py" in dep and 'BEDROOM_UNIT_NAME="vintos-bedroom-arrival"' in dep
      and "== bedroom arrival ==" in dep)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
