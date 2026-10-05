#!/usr/bin/env python3
"""FastAPI routes for the private Vintos watchOS app."""
import os, sys
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import watch_presence


def router(chat_url="http://127.0.0.1:8500", app_secret=""):
    routes = APIRouter()

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
        return {"items": source.sent(days=max(1, min(int(days), 30)))}

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
        text = str(body.get("text") or "").strip()
        if not text:
            return {**receipt, "reply": ""}
        # This is the same private conversation as Avatar chat. The watch token never becomes
        # the app secret; only the local server-to-itself hop carries that existing credential.
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(chat_url.rstrip("/") + "/api/avatar/chat",
                    headers={"X-Vintos-Secret": app_secret}, json={"message": text})
            response.raise_for_status(); answer = response.json()
            return {**receipt, "reply": str(answer.get("reply") or "")[:2000]}
        except Exception as exc:
            return {**receipt, "reply": "", "delivery":"stored_for_him",
                    "delivery_error":"%s: %s" % (type(exc).__name__, str(exc)[:160])}

    @routes.get("/api/watch/latest")
    async def latest(request: Request):
        auth(request); return watch_presence.latest()

    return routes
