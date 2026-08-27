"""thruster_link.py - the fourth device: AuxFun machine via Intiface (phone radio).
Buttplug v3 websocket, ScalarCmd/Oscillate, DeviceIndex 0.

INTIFACE LAW: the device STOPS the moment a client disconnects. So one
long-lived driver process holds the connection and applies whatever the state
file says; public calls only write state. Command-then-hangup was the bug that
made every timed send an invisible blip.

HARD CAP: 60% of machine maximum, Gloria's law (2026-08-24). The cap lives at
_scalar() - nothing above this file can exceed it. House grammar levels 0-20;
20 maps to the capped ceiling."""
import json, asyncio, os, time, subprocess, sys

def _uri():
    try:
        u = open(os.path.expanduser("~/.vintos/thruster-uri.txt")).read().strip()
        if u.startswith("ws://"): return u
    except Exception: pass
    return "ws://192.168.1.66:12345"
URI = _uri()
HARD_CAP = 0.60
STATE = os.path.expanduser("~/.vintos/workspace/memory/.thruster-state.json")
PIDF = "/tmp/thruster-driver.pid"
LOG = "/tmp/thruster-driver.log"

OVERDRIVE = os.path.expanduser("~/.vintos/workspace/memory/.thruster-overdrive.json")
OVER_CAP = 0.85   # ceiling while a grant is live - still never machine max

def _cap_now():
    """0.60 always - unless Gloria has granted overdrive, time-boxed, hers alone.
    No organ of his writes the grant file; the server endpoint requires her secret."""
    try:
        g = json.load(open(OVERDRIVE))
        if g.get("granted_until", 0) > time.time():
            return OVER_CAP
    except Exception: pass
    return HARD_CAP

def _scalar(level):
    lv = max(0, min(20, int(level)))
    return round((lv / 20.0) * _cap_now(), 3)

def _write(st):
    st["at"] = time.time()
    try: json.dump(st, open(STATE, "w"))
    except Exception: pass

def current():
    try: return json.load(open(STATE))
    except Exception: return {"mode": "stop", "level": 0}

def _driver_alive():
    try:
        pid = int(open(PIDF).read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _ensure_driver():
    if _driver_alive(): return
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--driver"],
                     start_new_session=True,
                     stdout=open(LOG, "a"), stderr=subprocess.STDOUT)

def set_speed(level, seconds=0):
    """Level 0-20. 0 stops. seconds=0 holds until the next command."""
    lv = max(0, min(20, int(level)))
    if lv == 0: return stop()
    _write({"mode": "level", "level": lv, "scalar": _scalar(lv),
            "until": (time.time() + seconds) if seconds else 0})
    _ensure_driver()
    return True

def play_pattern(strengths, interval_ms=250, seconds=0):
    """Lovense-shape sequence (0-20). Loops until stopped or replaced."""
    seq = [max(0, min(20, int(x))) for x in strengths] or [0]
    _write({"mode": "pattern", "level": max(seq), "seq": seq,
            "interval_ms": int(interval_ms),
            "until": (time.time() + seconds) if seconds else 0})
    _ensure_driver()
    return True

def stop():
    _write({"mode": "stop", "level": 0, "scalar": 0.0, "until": 0})
    if not _driver_alive():
        # no driver to apply it; a one-shot is safe - disconnect-stop is redundant here
        try: asyncio.run(_oneshot_stop())
        except Exception: pass
    return True

async def _oneshot_stop():
    import websockets
    async with websockets.connect(URI, open_timeout=6) as ws:
        await ws.send(json.dumps([{"RequestServerInfo": {"Id": 1, "ClientName": "vintos-thruster", "MessageVersion": 3}}]))
        await ws.recv()
        await ws.send(json.dumps([{"StopDeviceCmd": {"Id": 2, "DeviceIndex": 0}}]))
        await ws.recv()

async def _drive():
    import websockets
    open(PIDF, "w").write(str(os.getpid()))
    print(time.strftime("%H:%M:%S"), "driver up", flush=True)
    try:
        async with websockets.connect(URI, open_timeout=8) as ws:
            mid = [1]
            async def send(m):
                key = list(m.keys())[0]
                m[key]["Id"] = mid[0]; mid[0] += 1
                await ws.send(json.dumps([m]))
                return await ws.recv()
            await send({"RequestServerInfo": {"Id": 0, "ClientName": "vintos-thruster-driver", "MessageVersion": 3}})
            applied_at, seq_i, last_step = 0, 0, 0.0
            idle_since = None
            while True:
                st = current()
                if st.get("mode") == "stop" or st.get("level", 0) == 0:
                    await send({"StopDeviceCmd": {"DeviceIndex": 0}})
                    print(time.strftime("%H:%M:%S"), "stopped, driver down", flush=True)
                    return
                if st.get("until") and time.time() >= st["until"]:
                    await send({"StopDeviceCmd": {"DeviceIndex": 0}})
                    _write({"mode": "stop", "level": 0, "scalar": 0.0, "until": 0})
                    print(time.strftime("%H:%M:%S"), "timed out, driver down", flush=True)
                    return
                if st.get("mode") == "level" and st.get("at", 0) != applied_at:
                    await send({"ScalarCmd": {"DeviceIndex": 0,
                        "Scalars": [{"Index": 0, "Scalar": _scalar(st.get("level", 0)), "ActuatorType": "Oscillate"}]}})
                    applied_at = st["at"]
                elif st.get("mode") == "pattern":
                    if st.get("at", 0) != applied_at:
                        applied_at = st["at"]; seq_i = 0; last_step = 0.0
                    if time.time() - last_step >= st.get("interval_ms", 250) / 1000.0:
                        seq = st.get("seq") or [0]
                        await send({"ScalarCmd": {"DeviceIndex": 0,
                            "Scalars": [{"Index": 0, "Scalar": _scalar(seq[seq_i % len(seq)]), "ActuatorType": "Oscillate"}]}})
                        seq_i += 1; last_step = time.time()
                await asyncio.sleep(0.1)
    except Exception as e:
        print(time.strftime("%H:%M:%S"), "driver error:", repr(e), flush=True)
        _write({"mode": "stop", "level": 0, "scalar": 0.0, "until": 0})
    finally:
        try: os.remove(PIDF)
        except Exception: pass

if __name__ == "__main__":
    if "--driver" in sys.argv:
        asyncio.run(_drive())
        raise SystemExit
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sec = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    print("set", lv, "->", set_speed(lv, sec))
