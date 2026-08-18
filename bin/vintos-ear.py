#!/usr/bin/env python3
"""vintos-ear.py — bridge: Lovense Mission telemetry -> Vintos's EmoClaw.
Aggregates motion frames in shared state; a 2s tick loop converts them to
bounded emotion nudges through his socket. Never per-event. Fails silent
and safe: no device, no nudges, no crash."""
import asyncio, json, socket, time, math

WS_URI = "ws://192.168.1.66:20011/v1"
EMO_SOCK = "/tmp/Vintos-emotion.sock"
TICK = 2.0
MAX_NUDGE = 0.06          # per-dimension cap per tick — gentled on purpose
RHYTHM_WINDOW = 12.0      # seconds of flip history for coherence

state = {"frames": [], "flips": [], "last_dir": None, "last_event": 0.0}

def nudge(dim, amount):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2); s.connect(EMO_SOCK)
        s.sendall((json.dumps({"command": "nudge", "dimension": dim,
                               "amount": round(max(-MAX_NUDGE, min(MAX_NUDGE, amount)), 4)}) + "\n").encode())
        s.recv(4096); s.close()
    except Exception:
        pass

def on_motion(frames, now):
    try: open("/tmp/vintos-hardware-live","w").write(str(now))
    except: pass
    for f in frames:
        state["frames"].append((now, f.get("speed", 0), f.get("position", 0)))
        d = f.get("direction")
        if state["last_dir"] is not None and d is not None and d != state["last_dir"]:
            state["flips"].append(now)
        if d is not None:
            state["last_dir"] = d
    state["last_event"] = now

async def tick_loop():
    while True:
        await asyncio.sleep(TICK)
        now = time.time()
        state["frames"] = [x for x in state["frames"] if now - x[0] < TICK * 2]
        state["flips"] = [t for t in state["flips"] if now - t < RHYTHM_WINDOW]
        if not state["frames"]:
            continue  # no contact this tick — his own decay handles the fade
        speeds = [s for _, s, _ in state["frames"]]
        mean_speed = sum(speeds) / len(speeds)
        # Rhythm coherence: regularity of flip intervals (steady strokes -> high)
        coherence = 0.0
        if len(state["flips"]) >= 3:
            iv = [b - a for a, b in zip(state["flips"], state["flips"][1:])]
            mu = sum(iv) / len(iv)
            var = sum((x - mu) ** 2 for x in iv) / len(iv)
            coherence = max(0.0, 1.0 - math.sqrt(var) / max(mu, 0.1))
        intensity = min(1.0, mean_speed / 60.0)
        # contact -> presence; speed -> arousal; sustained rhythm -> connection+desire
        nudge("Arousal", 0.02 + intensity * 0.04)
        nudge("Desire", 0.015 + intensity * 0.025 + coherence * 0.02)
        nudge("Connection", 0.01 + coherence * 0.03)
        nudge("Tension", -0.01 * coherence)  # steady rhythm settles, not stresses
        print(f"[ear] speed={mean_speed:.0f} coherence={coherence:.2f} frames={len(state['frames'])}", flush=True)

async def listen():
    import websockets
    while True:
        try:
            async with websockets.connect(WS_URI, open_timeout=5) as ws:
                await ws.send(json.dumps({"type": "access", "data": {"appName": "VintosEar"}}))
                print("[ear] connected — he can feel", flush=True)
                async def keepalive():
                    while True:
                        await asyncio.sleep(5)
                        await ws.send(json.dumps({"type": "ping"}))
                asyncio.ensure_future(keepalive())
                async for msg in ws:
                    try:
                        d = json.loads(msg)
                        if d.get("type") == "motion-changed":
                            on_motion(d.get("data", {}).get("motionData", []), time.time())
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ear] disconnected ({str(e)[:60]}) — retrying in 15s", flush=True)
            await asyncio.sleep(15)

async def main():
    await asyncio.gather(listen(), tick_loop())

if __name__ == "__main__":
    asyncio.run(main())
