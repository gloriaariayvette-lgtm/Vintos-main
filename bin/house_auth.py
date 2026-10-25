"""The house credential and default-deny admission for every house route.

One credential, VINTOS_SECRET from the service environment (~/.vintos/vintos.env), guards every
private route whatever its method, every mounted router, and both house WebSockets. There is no
built-in value. When it is unset, short, padded or the retired value, the server still starts and
its public routes still answer, but every private route refuses with 503 and the log says why.

Public routes are explicit lists (PUBLIC_GETS, the caller's public_writes, and the Watch's own
bearer paths). Anything not on a list needs the credential: an unknown or newly added route is
private until it is listed here, with a reason, under review.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# sha256 of the retired value; the value itself is deliberately not kept anywhere in source.
LEGACY_SHA256 = "c75efe8c241f8a21239fb4860a1ca089e5d6dc15536147a049dae039fe0d7fc0"
MIN_LENGTH = 32
PUBLIC_ORIGINS = ("https://aegis.tailaa3de5.ts.net:8443", "capacitor://localhost", "http://localhost", "https://localhost", "http://127.0.0.1:8500", "http://100.72.225.119:8500")

# Reviewed public reads, each with why it carries nothing private.
PUBLIC_GETS = {
    "/": "the app shell (HTML/JS only; it asks for the credential at runtime)",
    "/app/": "the app shell, second mount",
    "/app/manifest.json": "web-app manifest",
    "/app/stratagem_voice.js": "client script",
    "/client_lifecycle.js": "client script", "/app/client_lifecycle.js": "client script",
    "/avatar-bundle.js": "client script", "/app/avatar-bundle.js": "client script",
    "/house_auth_client.js": "the enrollment client itself", "/app/house_auth_client.js": "the enrollment client itself",
    "/api/client/capabilities": "route names and methods only, no data",
    "/ea": "second-email approval page; its handler admits only a valid one-time hashed link",
}
PUBLIC_ASSET_PREFIXES = ("/avatar-models/", "/models/")   # the avatar's 3D model files
MEDIA_PREFIXES = ("/api/file/", "/api/music/stream/", "/api/art/", "/api/video/file/",
    "/api/video/still/", "/api/voice/stream/", "/api/avatar/imprint", "/avatar/stage/clip/", "/avatar/stage/speech/", "/avatar/stage/still/")
# The Watch carries its own bearer (watch_presence.authorized), never the house credential.
WATCH_PREFIX = "/api/watch/"
WATCH_OWNER_ONLY = frozenset({"/api/watch/live"})                     # her phone toggles it, with the credential
WATCH_EXTRA = frozenset({"/api/voice/framing", "/api/voice/token"})   # Watch voice, same bearer
# Plain browser forms (no script) opened in her own enrolled browser: the HttpOnly, SameSite=strict
# session cookie stands in for the header on these writes only.
COOKIE_FORM_WRITES = frozenset({"/aq/answer", "/api/video/hero"})
STAGE_QUERY_PREFIX = "/avatar/stage/"
HOUSE_HOSTS = frozenset({"aegis.tailaa3de5.ts.net", "127.0.0.1", "localhost", "100.72.225.119"})
HOUSE_WEBSOCKETS = ("/ws/telemetry", "/ws/events")
# Pages whose handler checks the item's own one-time or expiring token (food review, her yes/no asks).
CAPABILITY_GETS = ("/api/food-order/review/{token}", "/api/gloria/asks/{qid}")
# Links he sends her by push (a clip, a still, an architecture question): each carries a ticket for that
# one path, so the link works from the notification without the credential and opens nothing else.
LINK_GETS = frozenset({"/aq"})
LINK_WRITES = frozenset({"/aq/answer"})
LINK_TTL = 7 * 86400


def problem(value):
    """Why a value cannot be the house credential, or None when it can."""
    if not isinstance(value, str) or not value: return "unset"
    if value != value.strip(): return "padded with whitespace"
    if len(value) < MIN_LENGTH: return "shorter than %d characters" % MIN_LENGTH
    if hmac.compare_digest(hashlib.sha256(value.encode()).hexdigest(), LEGACY_SHA256): return "the retired value"
    return None


def _log(line):
    print("[house] " + line, file=sys.stderr, flush=True)


def configured_secret(from_file=False, log=True):
    """The credential, or "" when there is none fit to use (every caller then fails closed).

    from_file: also read ~/.vintos/vintos.env through env_file when the environment lacks it,
    for processes whose unit does not load that file (cron, the robot bridge)."""
    value = os.environ.get("VINTOS_SECRET", "")
    if not value and from_file:
        try:
            from env_file import value as _env_value
            value = _env_value("VINTOS_SECRET") or ""
        except Exception:
            value = ""
    why = problem(value)
    if why:
        if log:
            _log("VINTOS_SECRET is %s: private routes refuse (503) until a new credential is set in "
                 "~/.vintos/vintos.env and the service restarts" % why)
        return ""
    return value


def require_secret():
    value = configured_secret(log=False)
    if not value:
        raise RuntimeError("VINTOS_SECRET must be provisioned with a new random credential")
    return value


def caller_secret():
    """For local callers of the house (cron, routers): the configured credential, or RuntimeError."""
    value = configured_secret(from_file=True, log=False)
    if not value:
        raise RuntimeError("VINTOS_SECRET must be provisioned with a new random credential")
    os.environ.setdefault("VINTOS_SECRET", value)
    return value


def matches(supplied, secret):
    """Constant-time comparison that is never true without a configured credential."""
    if not secret or not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(supplied.encode("utf-8", "replace"), secret.encode("utf-8", "replace"))


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _max_ttl(audience):
    return LINK_TTL if str(audience).startswith("link:") else 3600


def issue(secret, audience, ttl=60, now=None):
    if not secret: raise ValueError("no house credential configured")
    now = int(time.time() if now is None else now)
    body = _b64(json.dumps({"aud": audience, "exp": now + min(max(int(ttl), 1), _max_ttl(audience))},
                           separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def valid(secret, token, audience, now=None):
    try:
        if not secret: return False
        if not isinstance(token, str) or len(token) > 1500: return False
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected): return False
        row = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        now = time.time() if now is None else now
        return row.get("aud") == audience and now < row["exp"] <= now + _max_ttl(audience)
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError): return False


_CAPABILITY_GET_RX = None


def _capability_get(path):
    # These URLs carry their own expiring per-item capability, verified by their handlers.
    global _CAPABILITY_GET_RX
    if _CAPABILITY_GET_RX is None: _CAPABILITY_GET_RX = [template(p) for p in CAPABILITY_GETS]
    return any(rx.match(path) for rx in _CAPABILITY_GET_RX)


def is_public_get(path):
    return path in PUBLIC_GETS or path.startswith(PUBLIC_ASSET_PREFIXES) or _capability_get(path)


def is_media(path):
    return path.startswith(MEDIA_PREFIXES)


def is_watch_path(path):
    return (path.startswith(WATCH_PREFIX) and path not in WATCH_OWNER_ONLY) or path in WATCH_EXTRA


def signed_media(value, secret, ttl=3600):
    """Give the already-authenticated Watch only the media links it was offered."""
    if not secret: return value
    if isinstance(value, list): return [signed_media(v, secret, ttl) for v in value]
    if isinstance(value, dict): return {k: signed_media(v, secret, ttl) for k,v in value.items()}
    if not isinstance(value, str): return value
    parts = urlsplit(value)
    if parts.netloc and parts.hostname not in HOUSE_HOSTS: return value
    if not is_media(parts.path): return value
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if k != "access_token"]
    query.append(("access_token", issue(secret, "media:" + parts.path, ttl)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def link(url, ttl=LINK_TTL, secret=None):
    """A link he sends her, signed for exactly its own path. Unchanged when there is no credential
    (the link then refuses like any private route) or when it is not a house media/answer link."""
    secret = secret or configured_secret(from_file=True, log=False)
    parts = urlsplit(url)
    if not secret or (parts.netloc and parts.hostname not in HOUSE_HOSTS): return url
    if not (is_media(parts.path) or parts.path in LINK_GETS): return url
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if k != "access_token"]
    query.append(("access_token", issue(secret, "link:" + parts.path, ttl)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def template(path):
    """'/api/x/{token}/approve' -> a regex that takes exactly one path segment per parameter."""
    return re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(path)) + "$")


class HouseReadGuard:
    """Default-deny for every method, every mounted router and every WebSocket.

    Admission: the public reads; the reviewed public writes (each checks its own capability in its
    handler); the Watch's bearer on Watch paths; the credential header; for reads, the session
    cookie or a scoped media ticket; for the two house streams, an audience-bound ticket. Without a
    configured credential only the public lists answer and everything else gets 503."""
    def __init__(self, app, secret, watch_authorized=None, public_writes=()):
        self.app, self.secret = app, secret
        self.watch_authorized = watch_authorized or (lambda token: False)
        self.public_writes = [template(p) for p in public_writes]
        self._warned = False

    def _public_write(self, path):
        return path == "/api/auth/session" or any(p.match(path) for p in self.public_writes)

    def _watch_ok(self, headers):
        try: return bool(self.watch_authorized(headers.get(b"authorization")))
        except Exception: return False

    def _unconfigured(self, path):
        if not self._warned:
            self._warned = True
            _log("refusing private route %s: VINTOS_SECRET is not configured (503 until it is set)" % path[:80])

    async def _refuse(self, send, status, detail):
        body = json.dumps({"detail": detail}).encode()
        await send({"type":"http.response.start", "status":status, "headers":[
            (b"content-type",b"application/json"),(b"cache-control",b"no-store"),(b"content-length",str(len(body)).encode())]})
        await send({"type":"http.response.body", "body":body})

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = {k.lower():v.decode("latin1") for k,v in scope.get("headers", [])}
        owner = matches(headers.get(b"x-vintos-secret", ""), self.secret)
        if kind == "websocket":
            offered = scope.get("subprotocols", []) or []
            tickets = [p[len("vintos-token."):] for p in offered if p.startswith("vintos-token.")]
            audience = ("ws:" + path.rsplit("/",1)[1]) if path in HOUSE_WEBSOCKETS else None
            if not (owner or (audience and any(valid(self.secret, t, audience) for t in tickets))):
                if not self.secret: self._unconfigured(path)
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
        read = scope.get("method", "GET") in ("GET", "HEAD")
        if (read and is_public_get(path)) or (not read and self._public_write(path)):
            return await self.app(scope, receive, send)
        cookie = headers.get(b"cookie", "")
        session = next((x.strip().split("=",1)[1] for x in cookie.split(";") if x.strip().startswith("vintos_read=")), "")
        admitted = owner
        if not admitted and is_watch_path(path):
            admitted = self._watch_ok(headers)
        if not admitted and read:
            admitted = (valid(self.secret, session, "read") or
                        (is_media(path) and any(valid(self.secret, t, "media") or valid(self.secret, t, "media:"+path) for t in tokens)))
        if not admitted and tokens and ((read and (is_media(path) or path in LINK_GETS)) or
                                        (not read and path in LINK_WRITES)):
            admitted = any(valid(self.secret, t, "link:" + path) for t in tokens)
        if not admitted and path in COOKIE_FORM_WRITES:
            admitted = valid(self.secret, session, "read")
        if not admitted and path.startswith(STAGE_QUERY_PREFIX):
            # Existing tailnet review pages open with ?s=<credential> (avatar_stage.py). Kept for
            # them only; it reaches the access log, so new paths use the header or a ticket instead.
            admitted = any(matches(v, self.secret) for k, v in query if k == "s")
        if admitted:
            async def private_send(message):
                if message['type']=='http.response.start':
                    private_headers=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'cache-control']
                    message=dict(message,headers=private_headers+[(b'cache-control',b'private, no-store')])
                await send(message)
            return await self.app(scope, receive, private_send)
        if not self.secret:
            self._unconfigured(path)
            return await self._refuse(send, 503, "House credential is not configured")
        return await self._refuse(send, 401, "Authentication required")


def install(app, secret, public_writes=()):
    if getattr(app.state, "house_read_guard", False): return
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse
    def watch(token):
        import watch_presence
        return watch_presence.authorized(token)
    app.add_middleware(HouseReadGuard, secret=secret, watch_authorized=watch, public_writes=tuple(public_writes))
    app.state.house_read_guard = True

    @app.post("/api/auth/session")
    async def auth_session(request: Request):
        if not secret:
            raise HTTPException(status_code=503, detail="House credential is not configured")
        if not matches(request.headers.get("X-Vintos-Secret", ""), secret):
            raise HTTPException(status_code=401, detail="Unauthorized")
        response = JSONResponse({"ws": {name: issue(secret, "ws:"+name, 60) for name in ("telemetry","events")},
                                 "media_token": issue(secret, "media", 900), "expires_in":60},
                                headers={"Cache-Control":"no-store"})
        response.set_cookie("vintos_read", issue(secret,"read",3600), max_age=3600,
                            secure=True, httponly=True, samesite="strict", path="/")
        return response
