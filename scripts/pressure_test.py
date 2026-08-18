#!/usr/bin/env python3
"""pressure_test.py — one terminal: listen + drive motor + phase prompts."""
import asyncio, json, time
import websockets, requests

WS = "ws://192.168.1.66:20010/v1"
CMD = "http://192.168.1.66:20010/command"
MISSION = "c09b9e4704ae"

def motor(level, secs=0):
    try:
        r = requests.post(CMD, json={"command": "Function", "action": f"Vibrate:{level}",
            "timeSec": secs, "toy": MISSION, "apiVer": 1}, timeout=2)
        print(f"[motor] Vibrate:{level} -> {r.json().get('code')}", flush=True)
    except Exception as e:
        print(f"[motor] failed: {e}", flush=True)

PHASES = [
    (15, "PHASE 1: DON'T TOUCH IT — motor noise baseline"),
    (15, "PHASE 2: SQUEEZE FIRMLY AND HOLD — no stroking"),
    (15, "PHASE 3: PULSE SQUEEZES — squeeze, release, squeeze"),
    (15, "PHASE 4: ONE SLOW STROKE"),
]

async def main():
    async with websockets.connect(WS, open_timeout=5) as ws:
        await ws.send(json.dumps({"type": "access", "data": {"appName": "PressureTest"}}))
        print("[+] connected", flush=True)
        await asyncio.sleep(1)
        motor(12)                       # motor on AFTER socket is up, indefinite

        async def ping():
            while True:
                await asyncio.sleep(5)
                await ws.send(json.dumps({"type": "ping"}))
        asyncio.create_task(ping())

        async def phase_caller():
            for secs, label in PHASES:
                print(f"\n=== {label} ({secs}s) ===", flush=True)
                await asyncio.sleep(secs)
            print("\n=== DONE — Ctrl+C ===", flush=True)
            motor(0)
        asyncio.create_task(phase_caller())

        async for msg in ws:
            ev = json.loads(msg)
            if ev.get("type") == "motion-changed":
                for f in ev["data"].get("motionData", []):
                    print(f"  pos={f.get('position',0):3d} spd={f.get('speed',0):2d} dir={f.get('direction',0)}", flush=True)
            elif ev.get("type") == "shake-frequency-changed":
                print(f"  SHAKE={ev['data'].get('value')}", flush=True)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    motor(0)
    print("\nstopped.", flush=True)
