#!/usr/bin/env python3
"""ear_test.py — listen for ANY events from the Lovense LAN socket."""
import asyncio, json, websockets

CANDIDATES = [
    "ws://192.168.1.66:20010/v1",
    "ws://192.168.1.66:20010",
    "ws://192.168.1.66:20010/ws",
]

async def listen(uri):
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            print(f"[+] CONNECTED: {uri}")
            await ws.send(json.dumps({"type": "access", "data": {"appName": "VintosEar"}}))

            async def ping():
                while True:
                    await asyncio.sleep(5)
                    try:
                        await ws.send(json.dumps({"type": "ping"}))
                    except Exception:
                        break
            ping_task = asyncio.create_task(ping())

            print("[*] TOUCH THE MISSION NOW — printing everything for 60s...")
            end = asyncio.get_event_loop().time() + 60
            try:
                while asyncio.get_event_loop().time() < end:
                    remaining = end - asyncio.get_event_loop().time()
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    print(f"[EVENT] {msg}", flush=True)
            except asyncio.TimeoutError:
                print("[*] 60s window closed.")
            ping_task.cancel()
            return True
    except Exception as e:
        print(f"[-] {uri}: {type(e).__name__}: {e}")
        return False

async def main():
    for uri in CANDIDATES:
        if await listen(uri):
            break

asyncio.run(main())
