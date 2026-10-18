#!/usr/bin/env python3
"""Bedroom arrivals use a stubbed notification sender, never a real Watch or phone.
Every store is scratch, all senders are stubs, and every real socket is refused.
Notification transport acceptance is not Watch delivery or playback proof.
"""
import json, os, socket, struct, sys, tempfile, types
from unittest.mock import patch
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="bedroom-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
SENT = []; CALLS = []; APNS = []; ASLEEP = [False]; ERROR = [None]
RECEIPT = [{"state": "sent", "channel": "ntfy", "why": "http 200"}]
def no_apns(*a, **k):
    APNS.append((a, k)); raise AssertionError("unsupported APNs path must not be called")
def notify(aid, ch, message="", title="", click=None, authority=None, **kwargs):
    CALLS.append({"artifact_id": aid, "channel": ch, "title": title, "click": click,
                  "authority": authority(), **kwargs})
    if ERROR[0]: raise ERROR[0]
    got = RECEIPT[0]
    if isinstance(got, dict) and got.get("state") in ("sent", "acknowledged"):
        SENT.append((title, ch, click))
    return dict(got) if isinstance(got, dict) else got
sys.modules["watch_apns"] = types.SimpleNamespace(send=no_apns)
sys.modules["deliver"] = types.SimpleNamespace(deliver=notify)
sys.modules["watch_presence"] = types.SimpleNamespace(should_hold=lambda: (ASLEEP[0], "Gloria is asleep" if ASLEEP[0] else ""))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import bedroom_arrival as B
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway and all senders are stubs",
      all(p.startswith(HOME) for p in (B.CONFIG, B.STATE, B.SEEN, B.ARRIVALS, B.MUSIC))
       and sys.modules["watch_apns"].send is no_apns and sys.modules["deliver"].deliver is notify)

check("an ESPresense bedroom message is read", B.parse("espresense/devices/gloria-watch/bedroom", b'{"distance":1.03}') == ("gloria-watch", 1.03))
check("another room or bad JSON is not", B.parse("espresense/devices/x/kitchen", b'{"distance":1}') is None
      and B.parse("espresense/devices/x/bedroom", b"nope") is None)

T = 1_800_000_000.0
check("nobody enrolled: it only writes down what it hears", B.observe("5ce7537e7183", 1.0, now=T) is None
      and json.load(open(B.SEEN))["5ce7537e7183"]["distance"] == 1.0 and not SENT)

os.makedirs(os.path.dirname(B.CONFIG), exist_ok=True)
OWNER_CONFIG = {"devices": ["gloria-phone"], "max_distance_m": 4.0, "away_minutes": 20}
json.dump(OWNER_CONFIG, open(B.CONFIG, "w"))
config_before = open(B.CONFIG, "rb").read()
os.makedirs(os.path.dirname(B.MUSIC), exist_ok=True)
json.dump({"generated": [{"title": "Porch Light", "tracks": [{"version": 1, "audio_url": "https://cdn.test/a.mp3"}]},
                         {"title": "No Track Yet", "tracks": []}]}, open(B.MUSIC, "w"))
check("the newest song with a playable track is chosen", B.newest_song() == ("Porch Light", "https://cdn.test/a.mp3"))
check("the owner's 4.0 m limit is used: beyond it is not an arrival",
      B.observe("gloria-phone", 4.01, now=T) is None and not CALLS)
row = B.observe("gloria-phone", 4.0, now=T)
check("at the configured boundary: the existing ntfy song delivery path is used", row and row["sent"]
       and row["channel"] == "ntfy" and SENT == [("Porch Light", "ntfy", "https://cdn.test/a.mp3")], (row, SENT))
check("the notification keeps its playable click link and arrival authority",
      CALLS[-1]["artifact_id"] == "bedroom-song:https://cdn.test/a.mp3"
      and CALLS[-1]["authority"][0] and CALLS[-1]["tags"] == "musical_note")
check("transport acceptance claims neither Watch reception nor automatic playback",
      row["watch_delivery"] == "unconfirmed" and row["playback"] == "not_requested" and not APNS)
check("still in the room a minute later: nothing more", B.observe("gloria-phone", 1.0, now=T + 60) is None and len(SENT) == 1)
row = B.observe("gloria-phone", 1.0, now=T + 3600)
check("back after an hour, inside the cooldown: held back", row and row["why"] == "cooldown" and len(SENT) == 1, row)
row = B.observe("gloria-phone", 1.0, now=T + 14400)
check("back after four hours, same song: it is not sent twice", row and not row["sent"] and "already" in row["why"]
      and len(SENT) == 1, row)
d = json.load(open(B.MUSIC)); d["generated"].append({"title": "Static", "tracks": [{"audio_url": "https://cdn.test/b.mp3"}]})
json.dump(d, open(B.MUSIC, "w"))
ASLEEP[0] = True
calls_before = len(CALLS)
row = B.observe("gloria-phone", 1.0, now=T + 30000)
check("asleep: no sender is called", row and row["why"] == "asleep" and len(CALLS) == calls_before, row)
ASLEEP[0] = False
row = B.observe("gloria-phone", 1.0, now=T + 60000)
check("awake, away long enough, a new song: sent", row and row["sent"] and SENT[-1][2] == "https://cdn.test/b.mp3", row)
check("every arrival is written down", len(open(B.ARRIVALS).read().splitlines()) == 5)
check("a missing APNs setup cannot prevent the clickable notification", not APNS and len(SENT) == 2)

d = json.load(open(B.MUSIC)); d["generated"].append({"title": "Hum", "tracks": [{"audio_url": "https://cdn.test/c.mp3"}]})
json.dump(d, open(B.MUSIC, "w"))
ERROR[0] = OSError("ntfy down")
row = B.observe("gloria-phone", 1.0, now=T + 90000)
last = json.loads(open(B.ARRIVALS).read().splitlines()[-1])
check("a send exception is logged with its channel and does not spend the song or cooldown",
      not row["sent"] and last["channel"] == "ntfy" and "ntfy down" in last["why"]
      and json.load(open(B.STATE))["last_song_url"] == "https://cdn.test/b.mp3"
      and json.load(open(B.STATE))["last_sent_ts"] == T + 60000, (row, last))
ERROR[0] = None
for i, bad in enumerate([None, {}, {"state": "unexpected"}, {"state": "failed"}, {"state": "held"}, {"state": "queued"}]):
    RECEIPT[0] = bad
    row = B.observe("gloria-phone", 1.0, now=T + 120000 + i * 14400)
    last = json.loads(open(B.ARRIVALS).read().splitlines()[-1])
    check("non-success receipt %r is saved and never treated as delivered" % bad,
          not row["sent"] and last == row and json.load(open(B.STATE))["last_song_url"] == "https://cdn.test/b.mp3", row)
RECEIPT[0] = {"state": "acknowledged", "channel": "ntfy", "repeat": True}
row = B.observe("gloria-phone", 1.0, now=T + 240000)
check("an existing acknowledged delivery receipt preserves idempotency",
      row["sent"] and row["delivery"] == "acknowledged" and json.load(open(B.STATE))["last_song_url"] == "https://cdn.test/c.mp3", row)
calls_before = len(CALLS)
with patch.object(sys.modules["watch_presence"], "should_hold", side_effect=RuntimeError("sleep state unavailable")):
    row = B._arrived({}, T + 300000, "gloria-phone", 1.0, None)
check("a broken sleep guard is logged and cannot dispatch",
      not row["sent"] and "sleep state unavailable" in row["why"] and len(CALLS) == calls_before
      and json.loads(open(B.ARRIVALS).read().splitlines()[-1]) == row, row)
with patch.object(B, "_send", side_effect=RuntimeError("unexpected sender error")):
    row = B._arrived({}, T + 310000, "gloria-phone", 1.0, None)
check("an unexpected sender error also leaves a real attempt record",
      not row["sent"] and row["delivery"] == "failed" and "unexpected sender error" in row["why"]
      and json.loads(open(B.ARRIVALS).read().splitlines()[-1]) == row, row)
RECEIPT[0] = {"state": "sent", "channel": "ntfy", "why": "http 200"}
with patch.object(B, "_atomic", side_effect=OSError("state disk full")):
    row = B._arrived({}, T + 320000, "gloria-phone", 1.0, None)
check("a state-save error is recorded without falsifying a successful transport receipt",
      row["sent"] and "state disk full" in row["state_error"]
      and json.loads(open(B.ARRIVALS).read().splitlines()[-1]) == row, row)
check("all owner config fields, including 4.0 m, remain unchanged", open(B.CONFIG, "rb").read() == config_before)
check("the unsupported Watch sender was never tried", not APNS)

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
