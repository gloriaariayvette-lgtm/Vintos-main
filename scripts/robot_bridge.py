#!/usr/bin/env python3
"""robot_bridge.py -- the web face of robot_core: what the Pi client and his server talk to.

Port 8404 (8500 is his server, 8403 is Velaris's bridge). Header X-Vintos-Secret on everything except /health.
Run: python3 robot_bridge.py            (systemd: vintos-robot-bridge.service)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robot_core as rc
from fastapi import FastAPI, Request, HTTPException

APP_SECRET = os.environ.get("VINTOS_SECRET", "vintos-aegis-2026")
PORT = int(os.environ.get("VINTOS_ROBOT_PORT", "8404"))
app = FastAPI(title="Vintos robot bridge", version="1.0")


def _auth(request):
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _context(request):
    """The turn context his server passes along, when it does; the Pi and cron never have one."""
    tid = request.headers.get("X-Vintos-Turn", "")
    if not tid:
        return None
    try:
        from turn_coordinator import effect_context
        return effect_context("robot", turn_id=tid)
    except Exception:
        return None


@app.get("/health")
async def health():
    s = rc.public_state()
    return {"ok": True, "port": PORT, "reporting": bool(s["ts"]), "age_s": s["age_s"],
            "frame_fresh": s["frame_fresh"], "pending": len(rc.pending_snapshot())}


@app.post("/api/robot/sensor")
async def sensor(request: Request):
    _auth(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="json body required")
    try:
        return {"ok": True, "state": rc.ingest_sensor(payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/robot/state")
async def state(request: Request, frame: int = 1):
    _auth(request)
    return rc.public_state(with_frame=bool(frame))


@app.get("/api/robot/context")
async def context(request: Request):
    _auth(request)
    return {"context": rc.context_text(), "state": rc.public_state()}


@app.get("/api/robot/commands/pending")
async def pending(request: Request):
    _auth(request)
    cmds = rc.take_pending()
    # both shapes a client might read: the list under "commands", and the first as "command"
    return {"commands": cmds, "command": cmds[0] if cmds else None, "count": len(cmds)}


@app.post("/api/robot/command")
async def command(request: Request):
    _auth(request)
    body = await request.json()
    return rc.queue_command(body, context=_context(request), source=request.headers.get("X-Vintos-Source", "server"))


@app.post("/api/robot/stop")
async def stop(request: Request):
    _auth(request)
    return rc.stop(context=None, source=request.headers.get("X-Vintos-Source", "server"))


@app.post("/api/robot/intent")
async def intent(request: Request):
    _auth(request)
    return {"ok": True, "row": rc.record_intent(await request.json())}


@app.post("/api/robot/look")
async def look(request: Request):
    _auth(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return rc.look(question=(body or {}).get("question"))


@app.post("/api/robot/chat")
async def chat(request: Request):
    _auth(request)
    body = await request.json()
    msg = str(body.get("message", "")).strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message required")
    speak = body.get("speak", True)
    return rc.chat(msg, history=body.get("history") or [], context=_context(request),
                   speaker=(rc.default_speaker if speak else None))


@app.get("/api/robot/voice/latest")
async def voice_latest(request: Request):
    _auth(request)
    return rc.voice_latest()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
