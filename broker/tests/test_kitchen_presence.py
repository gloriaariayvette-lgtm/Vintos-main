#!/usr/bin/env python3
"""She is in the kitchen when her phone is within 1 m of the coffee maker's ESP32 (3 November). Scratch HOME; every
socket is refused; nothing is sent. The relay only knows and keeps: a line for him and each visit."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="kitchen-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import kitchen_presence as K

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway", all(p.startswith(HOME) for p in (K.CONFIG, K.STATE, K.SEEN, K.VISITS)))
os.makedirs(K.MEM, exist_ok=True)
def rows(p): return [json.loads(l) for l in open(p)] if os.path.exists(p) else []

# ---- reading the board ----------------------------------------------------------------------------------------------
check("a kitchen message gives the device and distance",
      K.parse("espresense/devices/gloria-phone/kitchen", b'{"distance": 0.82, "rssi": -60}') == ("gloria-phone", 0.82))
check("the bedroom's messages are not the kitchen's",
      K.parse("espresense/devices/gloria-phone/bedroom", b'{"distance": 0.5}') is None)
check("a reading with no distance (phone not heard: NaN becomes null) says nothing",
      K.parse("espresense/devices/gloria-phone/kitchen", b'{"distance": null}') is None)
check("the default is her phone within 1 m", K.config()["devices"] == ["gloria-phone"] and K.config()["max_distance_m"] == 1.0)

# ---- visits ---------------------------------------------------------------------------------------------------------
T = 1793700000.0
check("passing at 1.6 m is not the kitchen", K.observe("gloria-phone", 1.6, now=T) is False and K.context_line(now=T) == "")
check("someone else's phone at 0.3 m is not her", K.observe("other-phone", 0.3, now=T) is False and K.context_line(now=T) == "")
check("within 1 m begins a visit", K.observe("gloria-phone", 0.7, now=T + 10) is True)
line = K.context_line(now=T + 60)
check("while she is there he is told she is in the kitchen", "she is in the kitchen now" in line, line)
for k in range(1, 6): K.observe("gloria-phone", 0.9, now=T + 10 + k * 60)
check("staying writes no visit yet", rows(K.VISITS) == [])
check("a little later he is told she was last there",
      "last by the coffee maker" in K.context_line(now=T + 310 + 600), K.context_line(now=T + 310 + 600))
check("after half an hour nothing is said", K.context_line(now=T + 310 + 1801) == "")
check("coming back after 5+ minutes begins a new visit", K.observe("gloria-phone", 0.5, now=T + 310 + 3600) is True)
v = rows(K.VISITS)
check("the visit that ended is written once, first to last heard",
      len(v) == 1 and (v[0]["from_ts"], v[0]["to_ts"], v[0]["minutes"]) == (T + 10, T + 310, 5.0), v)
check("a short step away (under 5 minutes) is the same visit",
      K.observe("gloria-phone", 0.5, now=T + 310 + 3600 + 200) is False and len(rows(K.VISITS)) == 1)
json.dump({"max_distance_m": 2.0}, open(K.CONFIG, "w"))
check("the distance can be changed in her config", K.observe("gloria-phone", 1.6, now=T + 310 + 3600 + 260) is False
      and json.load(open(K.STATE))["last_here_distance"] == 1.6)
check("what the board heard is kept for calibrating", json.load(open(K.SEEN))["gloria-phone"]["count"] >= 10)

# ---- he is told through the world block ------------------------------------------------------------------------------
import time, world_model
K.observe("gloria-phone", 0.4, now=time.time())
blk = world_model.get_world_block()
check("the world block carries the kitchen line while she is there", "she is in the kitchen now" in blk, blk)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
