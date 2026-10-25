"""Environment-backed house identity and audience-bound read/WebSocket admission."""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LEGACY_SHA256 = "c75efe8c241f8a21239fb4860a1ca089e5d6dc15536147a049dae039fe0d7fc0"
PUBLIC_ORIGINS = ("https://aegis.tailaa3de5.ts.net:8443", "capacitor://localhost", "http://localhost", "https://localhost", "http://127.0.0.1:8500", "http://100.72.225.119:8500")
PUBLIC_GETS = frozenset({"/", "/app/", "/app/manifest.json", "/app/stratagem_voice.js",
    "/client_lifecycle.js", "/app/client_lifecycle.js", "/avatar-bundle.js", "/app/avatar-bundle.js",
    "/house_auth_client.js", "/app/house_auth_client.js", "/api/client/capabilities"})
PUBLIC_ASSET_PREFIXES = ("/avatar-models/", "/models/")
MEDIA_PREFIXES = ("/api/file/", "/api/music/stream/", "/api/art/", "/api/video/file/",
    "/api/video/still/", "/api/voice/stream/", "/api/avatar/imprint", "/avatar/stage/clip/", "/avatar/stage/speech/", "/avatar/stage/still/")
WATCH_READS = frozenset({"/api/watch/song", "/api/watch/landings", "/api/watch/latest", "/api/voice/framing"})
HOUSE_HOSTS = frozenset({"aegis.tailaa3de5.ts.net", "127.0.0.1", "localhost", "100.72.225.119"})


def require_secret():
    value = os.environ.get("VINTOS_SECRET", "")
    if (len(value) < 32 or value != value.strip() or
            hmac.compare_digest(hashlib.sha256(value.encode()).hexdigest(), LEGACY_SHA256)):
        raise RuntimeError("VINTOS_SECRET must be provisioned with a new random credential before startup")
    return value


def caller_secret():
    # Cron callers load the same environment configuration as the service units.
    if not os.environ.get("VINTOS_SECRET"):
        from env_file import value
        configured = value("VINTOS_SECRET")
        if configured: os.environ["VINTOS_SECRET"] = configured
    return require_secret()


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def issue(secret, audience, ttl=60, now=None):
    now = int(time.time() if now is None else now)
    body = _b64(json.dumps({"aud": audience, "exp": now + min(max(int(ttl), 1), 3600)},
                           separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def valid(secret, token, audience, now=None):
    try:
        if not isinstance(token, str) or len(token) > 1500: return False
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected): return False
        row = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        now = time.time() if now is None else now
        return row.get("aud") == audience and now < row["exp"] <= now + 3600
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError): return False


def is_public_get(path):
    return path in PUBLIC_GETS or path.startswith(PUBLIC_ASSET_PREFIXES)


def is_media(path):
    return path.startswith(MEDIA_PREFIXES)


def signed_media(value, secret, ttl=3600):
    """Give the already-authenticated Watch only the media links it was offered."""
    if isinstance(value, list): return [signed_media(v, secret, ttl) for v in value]
    if isinstance(value, dict): return {k: signed_media(v, secret, ttl) for k,v in value.items()}
    if not isinstance(value, str): return value
    parts = urlsplit(value)
    if parts.netloc and parts.hostname not in HOUSE_HOSTS: return value
    if not is_media(parts.path): return value
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if k != "access_token"]
    query.append(("access_token", issue(secret, "media:" + parts.path, ttl)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class HouseReadGuard:
    """Default-deny reads and both house WebSockets, including mounted/dynamic routes."""
    def __init__(self, app, secret, watch_authorized=None):
        self.app, self.secret = app, secret
        self.watch_authorized = watch_authorized or (lambda token: False)

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = {k.lower():v.decode("latin1") for k,v in scope.get("headers", [])}
        supplied = headers.get(b"x-vintos-secret", "")
        owner = bool(supplied) and hmac.compare_digest(supplied.encode(), self.secret.encode())
        if kind == "websocket":
            if path not in ("/ws/telemetry", "/ws/events"):
                return await self.app(scope, receive, send)
            audience = "ws:" + path.rsplit("/",1)[1]
            offered = scope.get("subprotocols", [])
            tokens = [p[len("vintos-token."):] for p in offered if p.startswith("vintos-token.")]
            if not (owner or any(valid(self.secret, token, audience) for token in tokens)):
                return await send({"type":"websocket.close", "code":4401})
            async def accepted(message):
                if message["type"] == "websocket.accept" and "vintos-v1" in offered:
                    message = dict(message, subprotocol="vintos-v1")
                await send(message)
            return await self.app(scope, receive, accepted)
        query = parse_qsl(scope.get("query_string", b"").decode("latin1"), keep_blank_values=True)
        tokens = [v for k,v in query if k == "access_token"]
        if tokens:
            # Uvicorn's access record must not retain a bearer URL, even on denial.
            scope["query_string"] = urlencode([(k,v) for k,v in query if k != "access_token"]).encode()
        if scope.get("method") not in ("GET", "HEAD") or is_public_get(path):
            return await self.app(scope, receive, send)
        cookie = headers.get(b"cookie", "")
        session = next((x.strip().split("=",1)[1] for x in cookie.split(";") if x.strip().startswith("vintos_read=")), "")
        media_ok = is_media(path) and any(valid(self.secret, token, "media") or valid(self.secret, token, "media:"+path) for token in tokens)
        watch_ok = False
        if path in WATCH_READS:
            try: watch_ok = bool(self.watch_authorized(headers.get(b"authorization")))
            except Exception: pass
        # A proposal URL carries its own expiring one-proposal capability, verified by its handler.
        capability = path.startswith("/api/food-order/review/") and len(path.split("/")) == 5
        if owner or valid(self.secret, session, "read") or media_ok or watch_ok or capability:
            async def private_send(message):
                if message['type']=='http.response.start':
                    private_headers=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'cache-control']
                    message=dict(message,headers=private_headers+[(b'cache-control',b'private, no-store')])
                await send(message)
            return await self.app(scope, receive, private_send)
        body = b'{"detail":"Authentication required"}'
        await send({"type":"http.response.start", "status":401, "headers":[
            (b"content-type",b"application/json"),(b"cache-control",b"no-store"),(b"content-length",str(len(body)).encode())]})
        await send({"type":"http.response.body", "body":body})


def install(app, secret):
    if getattr(app.state, "house_read_guard", False): return
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse
    def watch(token):
        import watch_presence
        return watch_presence.authorized(token)
    app.add_middleware(HouseReadGuard, secret=secret, watch_authorized=watch)
    app.state.house_read_guard = True

    @app.post("/api/auth/session")
    async def auth_session(request: Request):
        supplied = request.headers.get("X-Vintos-Secret", "")
        if not supplied or not hmac.compare_digest(supplied.encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="Unauthorized")
        response = JSONResponse({"ws": {name: issue(secret, "ws:"+name, 60) for name in ("telemetry","events")},
                                 "media_token": issue(secret, "media", 900), "expires_in":60},
                                headers={"Cache-Control":"no-store"})
        response.set_cookie("vintos_read", issue(secret,"read",3600), max_age=3600,
                            secure=True, httponly=True, samesite="strict", path="/")
        return response
