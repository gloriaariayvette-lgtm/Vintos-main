#!/usr/bin/env python3
"""Room awareness keeps its sources distinct (proposal 18): four rows, each fresh or unknown on its own terms,
nothing fused, nothing written, nothing sent, no device moved.

Scratch HOME and workspace; every store the organs write is repointed there and asserted to be; the song sender is
a stub that fails the suite if reached; sockets are refused. An entry and an exit are walked through the organs' own
writers (bedroom_arrival.observe, mmwave_presence.intake, watch_presence.record, a home-presence state file)."""
import json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-sources-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import subprocess
subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no probe runs in this suite"))
import home_presence as H, bedroom_arrival as B, watch_presence as W, mmwave_presence as M
import room_sources as S
B._send = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no song is sent in this suite"))
MEM = os.path.join(HOME, "workspace", "memory"); os.makedirs(MEM, exist_ok=True)
W.MEMORY = MEM
W.LATEST = os.path.join(MEM, "watch-presence.json"); W.HISTORY = os.path.join(MEM, "watch-presence-history.jsonl")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))

stores = [H.STATE, H.CONFIG, B.STATE, B.CONFIG, B.SEEN, B.ARRIVALS, B.MUSIC, W.LATEST, W.HISTORY, S.MMWAVE_STATE]
check("every store is scratch and the sender is a stub", all(p.startswith(HOME) for p in stores), stores)
check("the mmWave freshness here is the module's own", S.MMWAVE_FRESH_S == M.FRESH_S)
check("the Watch freshness is should_hold's two hours", S.WATCH_FRESH_S == 7200)


def tree():
    out = {}
    for root, _, fs in os.walk(HOME):
        for f in fs:
            p = os.path.join(root, f)
            try: out[p] = (os.path.getsize(p), os.path.getmtime(p))
            except OSError: pass
    return out


def by(rows): return {r["source"]: r for r in rows}


T = time.time()   # home_presence.context_line reads the real clock
rows = S.sources(T)
check("four rows, in a fixed order", [r["source"] for r in rows] == list(S.ORDER), rows)
check("nothing set up: every source is unknown, with its reason",
      all(r["state"] == "unknown" for r in rows)
      and by(rows)["house_wifi"]["why"] == "not configured"
      and by(rows)["bedroom_board"]["why"] == "no device enrolled"
      and by(rows)["room_sensor"]["why"] == "not commissioned", rows)
check("unknown permits nothing", all(r["permits"] == "nothing while unknown" for r in rows))

# --- set up as on Aegis: her phone configured, a device enrolled on the board, the Watch checking in -------------
json.dump({"phone_ip": "192.0.2.10"}, open(H.CONFIG, "w"))
json.dump({"devices": ["enrolled-device"], "max_distance_m": 3.0}, open(B.CONFIG, "w"))
S_MM = S.MMWAVE_STATE


def watch_checkin(at, motion="walking", asleep=False):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(at))
    ok, got = W.record({"samples": [{"kind": "heart_rate", "value": 70, "unit": "bpm", "observed_at": ts},
                                    {"kind": "motion", "value": motion, "observed_at": ts}], "asleep": asleep}, now=at)
    return ok


# --- entry: the phone is on the Wi-Fi, she walks into the bedroom, the sensor sees someone, the Watch checks in ----
json.dump({"home": True, "misses": 0, "last_seen": T - 30, "checked": T - 30, "home_since": T - 3600}, open(H.STATE, "w"))
B.observe("enrolled-device", 1.4, now=T - 20)          # an arrival: no song with a track, so nothing is sent
M.intake({"occupied": True, "observed_at": T - 12}, state_path=S_MM, now=T - 12)
M.intake({"occupied": True, "observed_at": T - 5}, state_path=S_MM, now=T - 5)   # past the debounce: settled
check("the Watch accepted a check-in", watch_checkin(T - 60))
check("nothing was sent on that arrival", "no song" in (json.loads(open(B.ARRIVALS).read().splitlines()[-1]).get("why") or ""))

rows = S.sources(T); b = by(rows)
check("entry: the phone on the Wi-Fi is 'detected', its age beside it",
      b["house_wifi"]["state"] == "detected" and 25 <= b["house_wifi"]["age_s"] <= 35, b["house_wifi"])
check("entry: the bedroom board heard an enrolled device in range",
      b["bedroom_board"]["state"] == "detected" and "1.4 m" in b["bedroom_board"]["says"], b["bedroom_board"])
check("entry: the room sensor detects occupancy, and says it is not who",
      b["room_sensor"]["state"] == "occupied" and "not who" in b["room_sensor"]["says"], b["room_sensor"])
check("entry: the Watch reported wearing, not asleep, walking",
      b["watch"]["state"] == "reported" and "wearing probably" in b["watch"]["says"]
      and "asleep no" in b["watch"]["says"] and "motion walking" in b["watch"]["says"], b["watch"])
check("each known row names what it already permits and what it never does",
      all(r["permits"] == S.PERMITS[r["source"]][0] and r["never"] == S.PERMITS[r["source"]][1] for r in rows))

# Nothing is fused: no row, key, or rendered line says where Gloria is.
text = S.render(rows)
low = " ".join(r["says"] + " " + r["why"] for r in rows).lower()
check("no row claims where she is", not any(w in low for w in ("she is in", "gloria is", "she is home", "she is out",
                                                                 "is away", "in the bedroom now")), text)
check("the room sensor never names anyone", "her " not in b["room_sensor"]["says"].lower()
      and "gloria" not in b["room_sensor"]["says"].lower())
check("no combined field", all(set(r) == {"source", "label", "state", "says", "age_s", "fresh_s", "why", "permits", "never"}
                               for r in rows))
check("the display says it is read-only", "Read-only" in text)

# --- exit: she leaves; the sensor says no one; the board stops hearing her; the Wi-Fi reading ages ---------------
M.intake({"occupied": False, "observed_at": T + 40}, state_path=S_MM, now=T + 40)
M.intake({"occupied": False, "observed_at": T + 42}, state_path=S_MM, now=T + 42)
rows = S.sources(T + 45); b = by(rows)
check("exit: the room sensor reports no occupancy", b["room_sensor"]["state"] == "not occupied", b["room_sensor"])
check("exit: the board still heard the device 65 s ago: shown as detected, beside the sensor",
      b["bedroom_board"]["state"] == "detected", b["bedroom_board"])
check("the disagreement is named, not resolved", "neither wins" in S.disagreement(rows), S.disagreement(rows))

later = T + 15 * 60
rows = S.sources(later); b = by(rows)
check("fifteen minutes on: the board's reading is past its limit and becomes unknown, not 'gone'",
      b["bedroom_board"]["state"] == "unknown" and "not 'gone'" in b["bedroom_board"]["why"], b["bedroom_board"])
check("the room sensor's last reading is stale: unknown, not 'not occupied'",
      b["room_sensor"]["state"] == "unknown" and "past its" in b["room_sensor"]["why"], b["room_sensor"])
check("the Watch's motion reading is old: 'not known', the snapshot itself still within two hours",
      b["watch"]["state"] == "reported" and "motion not known" in b["watch"]["says"], b["watch"])
check("no disagreement once one side is unknown", S.disagreement(rows) == "")

# Wi-Fi: a stale positive is unknown (home_presence reads the real clock, so age the state instead)
json.dump({"home": True, "misses": 0, "last_seen": T - 16 * 60, "checked": T - 60}, open(H.STATE, "w"))
r = S.house_wifi(time.time())
check("a phone not seen for sixteen minutes is unknown, never 'away'",
      r["state"] == "unknown" and "may only be asleep" in r["why"] and "away" not in json.dumps(r).replace("never", ""), r)
json.dump({"home": False, "misses": 9, "last_seen": T - 3 * 3600, "checked": T - 60}, open(H.STATE, "w"))
check("even home=false is unknown here", S.house_wifi(time.time())["state"] == "unknown")

# Watch: asleep shows as reported; past two hours it is unknown
watch_checkin(T + 100, motion="stationary", asleep=True)
check("a fresh asleep snapshot is reported as such", "asleep yes" in S.watch(T + 120)["says"])
check("past two hours the Watch is unknown", S.watch(T + 100 + 7201)["state"] == "unknown")

# Odd stores never break the view
open(S_MM, "w").write("{not json")
check("an unreadable sensor store is that source unknown", S.room_sensor(T)["why"] == "state unreadable")
json.dump({"occupied": None, "observed_at": T, "status": "unknown"}, open(S_MM, "w"))
check("the sensor's own explicit unknown stays unknown", S.room_sensor(T + 1)["state"] == "unknown")
json.dump({"occupied": True, "observed_at": T + 500, "status": "fresh"}, open(S_MM, "w"))
check("a reading from the future is unknown", S.room_sensor(T)["state"] == "unknown")
orig = S.watch
S.watch = lambda now: 1 / 0
check("a reader that raises leaves that row unknown and the others standing",
      by(S.sources(T))["watch"]["state"] == "unknown" and len(S.sources(T)) == 4)
S.watch = orig

# The view and follow() write nothing.
mid = tree()
S.render(S.sources(T))
check("reading the sources writes nothing", tree() == mid)
clock = [T]
outs = []
def tick(s): clock[0] += s
json.dump({"occupied": True, "observed_at": T, "status": "fresh"}, open(S_MM, "w"))
mid = tree()
n = S.follow(minutes=1, every=20, clock=lambda: clock[0], sleep=tick, out=outs.append)
check("follow prints each change (the sensor going stale) and writes nothing",
      n >= 1 and any("room sensor" in o and "occupied -> unknown" in o for o in outs) and tree() == mid, outs)
check("follow stops after its minutes", clock[0] >= T + 60 and clock[0] < T + 100)

src = open(os.path.join(REPO, "scripts", "room_sources.py")).read()
check("the module imports nothing that sends or actuates",
      not any(w in src for w in ("import socket", "import requests", "import deliver", "ntfy", "subprocess",
                                 "urllib", "watch_apns", "offer_song", "robot", "open(path, \"w\"", "json.dump(")), src[:0])
man = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy manifest names it", "room_sources.py" in man)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
