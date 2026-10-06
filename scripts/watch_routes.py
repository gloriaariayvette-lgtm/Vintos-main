#!/usr/bin/env python3
"""FastAPI routes for the private Vintos watchOS app."""
import os, sys
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import watch_presence


def router(chat_url="http://127.0.0.1:8500", app_secret="", voice_module=None,
           foreground=None, voice_live_path=""):
    routes = APIRouter()
    voice_live_path = voice_live_path or os.path.expanduser("~/.vintos/workspace/memory/.voice-live")

    def local_voice():
        if voice_module is not None: return voice_module
        import voice_local
        return voice_local

    def touch_voice():
        if foreground is not None: return foreground()
        from compute_admission import touch_foreground
        return touch_foreground()

    def auth(request):
        if not watch_presence.authorized(request.headers.get("Authorization")):
            raise HTTPException(status_code=401, detail="bad watch token")

    @routes.post("/api/watch/telemetry")
    async def telemetry(request: Request, background_tasks: BackgroundTasks):
        auth(request)
        try: body = await request.json()
        except Exception: raise HTTPException(status_code=400, detail="invalid json")
        ok, result = watch_presence.record(body)
        if not ok: raise HTTPException(status_code=422, detail=result)
        if not body.get("asleep"):
            import watch_apns
            background_tasks.add_task(watch_apns.flush_held)
        return result

    @routes.post("/api/watch/register")
    async def register(request: Request):
        auth(request)
        ok, result = watch_presence.register_apns(await request.json())
        if not ok: raise HTTPException(status_code=422, detail=result)
        return result

    @routes.get("/api/watch/landings")
    async def landings(request: Request, days: int = 7):
        auth(request)
        import landings as source
        return {"items": source.sent(days=max(1, min(int(days), 30)))[:5]}

    @routes.post("/api/watch/landing")
    async def landing(request: Request):
        auth(request); body = await request.json()
        import landings as source
        try:
            row = source.record(body.get("surface"), body.get("ref"), body.get("rating"),
                                body.get("why"), body.get("before", ""))
        except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))
        except LookupError as exc: raise HTTPException(status_code=404, detail=str(exc))
        return {"ok": True, "id": row["id"]}

    @routes.post("/api/watch/reply")
    async def reply(request: Request):
        auth(request); body = await request.json()
        ok, receipt = watch_presence.record_reply(body)
        if not ok: raise HTTPException(status_code=422, detail=receipt)
        # Wrist words have their own private inbox and temporal path. They must not
        # create an Avatar-chat turn or appear in that conversation's history.
        return {**receipt, "reply": "Saved for Vintos."}

    @routes.post("/api/watch/moment")
    async def moment(request: Request):
        auth(request)
        ok, receipt = watch_presence.record_moment(await request.json())
        if not ok: raise HTTPException(status_code=422, detail=receipt)
        return receipt

    @routes.get("/api/watch/latest")
    async def latest(request: Request):
        auth(request); return watch_presence.latest()

    @routes.post("/api/watch/voice/local/turn")
    async def local_voice_turn(request: Request):
        auth(request); body = await request.json()
        try:
            voice_local = local_voice()
            touch_voice()
            return await __import__("asyncio").to_thread(
                voice_local.turn, str(body.get("audio") or ""),
                int(body.get("sample_rate") or 24000),
                str(body.get("instructions") or ""), str(body.get("framing") or ""))
        except Exception as exc:
            return {"ok": False, "stage": "transport", "error": str(exc)[:300]}

    @routes.post("/api/watch/voice/local/heartbeat")
    async def local_voice_heartbeat(request: Request):
        auth(request)
        touch_voice()
        try: open(voice_live_path, "a").close(); os.utime(voice_live_path, None)
        except OSError: pass
        return {"ok": True}

    @routes.post("/api/watch/voice/local/end")
    async def local_voice_end(request: Request):
        auth(request)
        try:
            voice_local = local_voice()
            result = await __import__("asyncio").to_thread(voice_local.models, False)
            try: os.unlink(voice_live_path)
            except OSError: pass
            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240]}

    return routes
