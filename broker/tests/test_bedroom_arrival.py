#!/usr/bin/env python3
"""The bedroom ESP32 (Gloria, 17 October): when she walks into the bedroom after being away, his newest song goes to
her Watch with its Play button; asleep, nothing. Scratch workspace; the Watch sender and sleep are stubs; the relay is
a fake socket; every real socket is refused."""
import json, os, socket, struct, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="bedroom-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
SENT = []; ASLEEP = [False]
sys.modules["watch_apns"] = types.SimpleNamespace(send=lambda title, body, kind="message", media_url="", **k:
                                                  (SENT.append((title, kind, media_url)), {"state": "sent"})[1])
PHONE = []
sys.modules["deliver"] = types.SimpleNamespace(deliver=lambda aid, ch, message="", title="", click=None, authority=None, **k:
                                               (PHONE.append((aid, ch, title, click, authority()[0])), {"state": "sent", "channel": ch})[1])
sys.modules["watch_presence"] = types.SimpleNamespace(should_hold=lambda: (ASLEEP[0], "Gloria is asleep" if ASLEEP[0] else ""))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import bedroom_arrival as B
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway and the Watch sender is a stub",
      all(p.startswith(HOME) for p in (B.CONFIG, B.STATE, B.SEEN, B.ARRIVALS, B.MUSIC))
      and B.__dict__.get("watch_apns") is None and sys.modules["watch_apns"].__class__ is types.SimpleNamespace)

check("an ESPresense bedroom message is read", B.parse("espresense/devices/gloria-watch/bedroom", b'{"distance":1.03}') == ("gloria-watch", 1.03))
check("another room or bad JSON is not", B.parse("espresense/devices/x/kitchen", b'{"distance":1}') is None
      and B.parse("espresense/devices/x/bedroom", b"nope") is None)

T = 1_800_000_000.0
check("nobody enrolled: it only writes down what it hears", B.observe("5ce7537e7183", 1.0, now=T) is None
      and json.load(open(B.SEEN))["5ce7537e7183"]["distance"] == 1.0 and not SENT)

os.makedirs(os.path.dirname(B.CONFIG), exist_ok=True)
json.dump({"devices": ["gloria-watch"]}, open(B.CONFIG, "w"))
os.makedirs(os.path.dirname(B.MUSIC), exist_ok=True)
json.dump({"generated": [{"title": "Porch Light", "tracks": [{"version": 1, "audio_url": "https://cdn.test/a.mp3"}]},
                         {"title": "No Track Yet", "tracks": []}]}, open(B.MUSIC, "w"))
check("the newest song with a playable track is chosen", B.newest_song() == ("Porch Light", "https://cdn.test/a.mp3"))
check("too far away is not an arrival", B.observe("gloria-watch", 6.0, now=T) is None and not SENT)
row = B.observe("gloria-watch", 1.2, now=T)
check("she comes in: his newest song goes to her Watch as a song", row and row["sent"]
      and SENT == [("Porch Light", "song", "https://cdn.test/a.mp3")], (row, SENT))
check("still in the room a minute later: nothing more", B.observe("gloria-watch", 1.0, now=T + 60) is None and len(SENT) == 1)
row = B.observe("gloria-watch", 1.0, now=T + 3600)
check("back after an hour, inside the cooldown: held back", row and row["why"] == "cooldown" and len(SENT) == 1, row)
row = B.observe("gloria-watch", 1.0, now=T + 14400)
check("back after four hours, same song: it is not sent twice", row and not row["sent"] and "already" in row["why"]
      and len(SENT) == 1, row)
d = json.load(open(B.MUSIC)); d["generated"].append({"title": "Static", "tracks": [{"audio_url": "https://cdn.test/b.mp3"}]})
json.dump(d, open(B.MUSIC, "w"))
ASLEEP[0] = True
row = B.observe("gloria-watch", 1.0, now=T + 30000)
check("asleep: nothing is sent", row and row["why"] == "asleep" and len(SENT) == 1, row)
ASLEEP[0] = False
row = B.observe("gloria-watch", 1.0, now=T + 60000)
check("awake, away long enough, a new song: sent", row and row["sent"] and SENT[-1][2] == "https://cdn.test/b.mp3", row)
check("every arrival is written down", len(open(B.ARRIVALS).read().splitlines()) == 5)
check("while the Watch push works, the phone is not used", not PHONE)

def no_key(*a, **k): raise FileNotFoundError("apns-watch.json")
sys.modules["watch_apns"].send = no_key
d = json.load(open(B.MUSIC)); d["generated"].append({"title": "Hum", "tracks": [{"audio_url": "https://cdn.test/c.mp3"}]})
json.dump(d, open(B.MUSIC, "w"))
row = B.observe("gloria-watch", 1.0, now=T + 90000)
check("no Watch push set up (17 October): it goes to her phone, tap opens the song, and is written down as sent",
      row and row["sent"] and row["channel"] == "phone" and PHONE[-1][:4] == ("bedroom-song:https://cdn.test/c.mp3", "ntfy", "Hum", "https://cdn.test/c.mp3")
      and "apns-watch.json" in row["why"] and json.loads(open(B.ARRIVALS).read().splitlines()[-1])["song"] == "Hum", (row, PHONE))
sys.modules["deliver"].deliver = lambda *a, **k: (_ for _ in ()).throw(OSError("ntfy down"))
d["generated"].append({"title": "Late", "tracks": [{"audio_url": "https://cdn.test/d.mp3"}]}); json.dump(d, open(B.MUSIC, "w"))
row = B.observe("gloria-watch", 1.0, now=T + 120000)
last = json.loads(open(B.ARRIVALS).read().splitlines()[-1])
check("both fail: nothing raised, the failed arrival is written down, and the song is not spent",
      row and not row["sent"] and "ntfy down" in last["why"] and json.load(open(B.STATE))["last_song_url"] == "https://cdn.test/c.mp3", (row, last))

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
