#!/usr/bin/env python3
"""Every private house route refuses a caller without the credential, whatever its method.

Routes are enumerated two ways and both must agree: from source (bin/server.py, every
bin/server_domains/*.py router, scripts/watch_routes.py) and from the real assembled app, built from
a scratch copy of the server laid out as the deploy lays it out (server.py + website/app.html).
Each private route is then called with no credential, a wrong credential, a read cookie where a
write needs the header, and a stray bearer, and must be refused before its handler runs. The two
house WebSockets must close before accepting. The public routes must be exactly the reviewed list.

It also asserts that no served file and no source file carries a built-in credential, and that a
server with the credential unset still starts, still answers its public routes, and refuses (503)
everything private.

Isolation: HOME is the suite's scratch directory (run_isolated_test.py); the server copy, its
website and its workspace live under it; every outbound path (sockets, urllib, requests, httpx) is
replaced by a stub that records and refuses, and the suite asserts that nothing was attempted.
No startup event runs (TestClient is used without its context manager).
"""
import ast
import glob
import hashlib
import importlib.util
import io
import os
import re
import shutil
import socket
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRET = "isolated-test-house-credential-only-0000"
WRONG = "wrong-house-credential-for-this-test-0000"
HOME = Path(os.environ.get("HOME", "/nonexistent")).resolve()

# --- isolation: nothing leaves this process ---------------------------------------------------
ATTEMPTS = []


def _refuse(*args, **kwargs):
    ATTEMPTS.append(repr(args[:2])[:120])
    raise OSError("outbound connection refused by test_house_route_guard")


def _install_sender_stubs():
    socket.create_connection = _refuse
    socket.socket.connect = lambda self, *a, **k: _refuse(*a)
    socket.socket.connect_ex = lambda self, *a, **k: _refuse(*a)
    import urllib.request
    urllib.request.urlopen = _refuse
    try:
        import requests
        requests.Session.request = lambda self, *a, **k: _refuse(*a)
    except ImportError:
        pass
    try:
        import httpx
        # the network transports only; TestClient's in-process transport stays usable
        httpx.HTTPTransport.handle_request = lambda self, *a, **k: _refuse(*a)
        async def _async_refuse(self, *a, **k): return _refuse(*a)
        httpx.AsyncHTTPTransport.handle_async_request = _async_refuse
    except ImportError:
        pass


def _scratch_server():
    """A copy of bin/ laid out like ~/Vintos: server.py, server_domains/, website/app.html, website/app/*.js."""
    srv = HOME / "house-route-guard" / "Vintos"
    if srv.exists(): shutil.rmtree(srv)
    shutil.copytree(REPO / "bin", srv, ignore=shutil.ignore_patterns("__pycache__"))
    web = srv / "website"; (web / "app").mkdir(parents=True)
    shutil.copy(REPO / "clients/mobile/index.html", web / "app.html")
    for js in glob.glob(str(REPO / "clients/mobile/*.js")):
        shutil.copy(js, web / "app" / os.path.basename(js))
    shutil.copy(REPO / "clients/mobile/index.html", web / "app" / "index.html")
    return srv


def _load(name, server_py, secret):
    if secret is None: os.environ.pop("VINTOS_SECRET", None)
    else: os.environ["VINTOS_SECRET"] = secret
    for p in (str(server_py.parent), str(REPO / "scripts")):
        if p not in sys.path: sys.path.insert(0, p)
    for cached in [m for m in sys.modules if m == "house_auth" or m.startswith("server_domains")]:
        del sys.modules[cached]          # each instance reads its own credential at import
    spec = importlib.util.spec_from_file_location(name, server_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    err = io.StringIO()
    with redirect_stderr(err):
        spec.loader.exec_module(module)
    return module, err.getvalue()


def setUpModule():
    global GUARDED, UNCONFIGURED, UNCONFIGURED_LOG, SRV, house_auth
    assert str(HOME).startswith(("/tmp/", "/private/", "/var/folders/")) or "vs-" in str(HOME), \
        "refusing: HOME is not a scratch directory (%s); run through scripts/run_isolated_test.py" % HOME
    assert not (HOME / ".vintos" / "vintos.env").exists(), "scratch HOME must not hold a credential file"
    _install_sender_stubs()
    SRV = _scratch_server()
    assert str(SRV).startswith(str(HOME))
    UNCONFIGURED, UNCONFIGURED_LOG = _load("server_unconfigured", SRV / "server.py", None)
    GUARDED, _ = _load("server_guarded", SRV / "server.py", SECRET)
    import house_auth as _ha
    house_auth = _ha
    assert str(Path(GUARDED.WORKSPACE).resolve()).startswith(str(HOME)), "his workspace must be the scratch one"


def tearDownModule():
    assert not ATTEMPTS, "a test reached for the network: %s" % ATTEMPTS[:3]


# --- route enumeration --------------------------------------------------------------------------
SOURCES = [REPO / "bin/server.py", REPO / "scripts/watch_routes.py"] + sorted(
    p for p in (REPO / "bin/server_domains").glob("*.py") if p.name != "patch_humor_wants.py")
VERBS = {"get", "post", "put", "patch", "delete", "websocket", "api_route"}


def source_routes():
    out = set()
    for f in SOURCES:
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            for d in node.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in VERBS
                        and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
                    out.add((d.func.attr.upper(), d.args[0].value, f.name))
    return out


def runtime_routes(app):
    from starlette.routing import Mount, WebSocketRoute
    rows = []
    for r in app.routes:
        if isinstance(r, WebSocketRoute) or type(r).__name__ == "APIWebSocketRoute":
            rows.append(("WEBSOCKET", r.path))
        elif isinstance(r, Mount):
            rows.append(("GET", r.path + "/probe.html"))
        else:
            for m in sorted(getattr(r, "methods", None) or ["GET"]):
                if m != "HEAD": rows.append((m, r.path))
    return rows


def concrete(path):
    return re.sub(r"\{[^}]+\}", "probe", path)


def client(module):
    from fastapi.testclient import TestClient
    return TestClient(module.app, base_url="https://house.invalid", raise_server_exceptions=False)


def anonymous_admits(module, method, path, headers=()):
    """Whether the real guard (as installed) would let this request reach the app; nothing runs."""
    import asyncio
    opts = _guard_options(module)
    reached = []
    async def app(scope, receive, send): reached.append(True)
    async def receive(): return {"type": "http.request", "body": b""}
    async def send(message): pass
    scope = {"type": "http", "path": path, "method": method, "headers": list(headers), "query_string": b""}
    asyncio.run(house_auth.HouseReadGuard(app, **opts)(scope, receive, send))
    return bool(reached)


def _guard_options(module):
    """The options the server installed its guard with (the real secret, Watch check and public writes)."""
    for mw in module.app.user_middleware:
        if getattr(mw.cls, "__name__", "") == "HouseReadGuard":
            return dict(getattr(mw, "kwargs", None) or getattr(mw, "options", {}))
    raise AssertionError("the house guard is not installed on the app")


# The reviewed public surface. Adding a route here is a security review decision.
REVIEWED_PUBLIC = {
    ("GET", "/"): "site shell (index.html or a redirect to /app/)",
    ("GET", "/app/"): "app shell; asks for the credential at runtime",
    ("GET", "/app/manifest.json"): "web-app manifest",
    ("GET", "/app/stratagem_voice.js"): "client script",
    ("GET", "/client_lifecycle.js"): "client script", ("GET", "/app/client_lifecycle.js"): "client script",
    ("GET", "/avatar-bundle.js"): "client script", ("GET", "/app/avatar-bundle.js"): "client script",
    ("GET", "/house_auth_client.js"): "enrollment client", ("GET", "/app/house_auth_client.js"): "enrollment client",
    ("GET", "/api/client/capabilities"): "route names only",
    ("GET", "/ea"): "one-time hashed link, checked by its handler",
    ("POST", "/ea/decide"): "one-time hashed link, checked by its handler",
    ("GET", "/api/food-order/review/{token}"): "expiring one-proposal capability",
    ("POST", "/api/food-order/review/{token}/approve"): "expiring one-proposal capability, single use",
    ("POST", "/api/guestbook/witness"): "presence only, no message",
    ("POST", "/api/gcs"): "hardware button, no header on the device",
    ("POST", "/api/gcs/clear"): "hardware button release",
    ("POST", "/api/hardware/button"): "physical stop button",
    ("POST", "/api/ring/live"): "ring bridge; its own optional bearer",
    ("POST", "/api/ring/sleep"): "ring bridge; its own optional bearer",
    ("POST", "/api/auth/session"): "checks the credential itself and issues the session",
    ("GET", "/api/gloria/asks/{qid}"): "her yes/no page; the question's own token, checked by its handler",
    ("POST", "/api/gloria/asks/{qid}/decide"): "her yes/no buttons; the question's own token",
    ("POST", "/api/lab/asks/{ask_id}/decide"): "her yes/no buttons; the card's own token",
}
MUST_BE_PRIVATE = [
    ("GET", "/api/chat/history"), ("GET", "/api/outreach/history"), ("GET", "/api/inner-life"),
    ("GET", "/api/journal/days"), ("GET", "/api/journal/probe"), ("GET", "/api/memory/search"),
    ("GET", "/api/memory/semantic"), ("GET", "/api/debug/context"), ("GET", "/api/file/mirror/probe"),
    ("GET", "/api/file/therapy/probe"), ("GET", "/api/thread-detail/probe"), ("GET", "/api/want-detail/probe"),
    ("GET", "/api/voice/latest"), ("GET", "/api/voice/stream/probe"), ("GET", "/api/voice/pending-speech"),
    ("GET", "/api/art"), ("GET", "/api/art/gallery"), ("GET", "/api/landings"), ("POST", "/api/landings"),
    ("GET", "/openapi.json"), ("GET", "/docs"), ("GET", "/static/app.html"), ("GET", "/aq"),
    ("POST", "/aq/answer"), ("POST", "/api/video/hero"), ("POST", "/api/music/share"),
    ("POST", "/api/voice/session-end"), ("POST", "/api/voice/call-log"), ("POST", "/api/voice/token"),
    ("POST", "/api/stratagem/owner/stop"), ("POST", "/api/stratagem/owner/reveal"),
    ("POST", "/api/watch/telemetry"), ("GET", "/api/watch/live"), ("PATCH", "/api/wants/probe"),
    ("DELETE", "/api/wants/probe"), ("POST", "/api/chat"), ("POST", "/api/desktop/share/start"),
    ("GET", "/api/gloria/asks"), ("GET", "/api/lab/asks"), ("GET", "/api/video/file/probe"),
]


class RouteInventory(unittest.TestCase):
    def test_every_source_route_is_in_the_assembled_app(self):
        src = source_routes()
        files = {f for _, _, f in src}
        for name in ("server.py", "watch_routes.py", "landings.py", "journal.py", "galleries.py", "music.py", "humor_wants.py"):
            self.assertIn(name, files, "no routes found in %s" % name)
        live = set(runtime_routes(GUARDED.app))
        live_paths = {p for _, p in live}
        missing = sorted((m, p, f) for m, p, f in src
                         if (m if m != "API_ROUTE" else "GET", p) not in live and p not in live_paths)
        self.assertFalse(missing, "routes in source that the assembled app does not have: %s" % missing[:10])
        self.assertGreater(len(live), 250)

    def test_public_surface_is_exactly_the_reviewed_list(self):
        admitted = set()
        for method, path in runtime_routes(GUARDED.app):
            if method == "WEBSOCKET": continue
            if anonymous_admits(GUARDED, method, concrete(path)):
                admitted.add((method, path))
        self.assertEqual(admitted - set(REVIEWED_PUBLIC), set(), "unreviewed public routes")
        self.assertEqual({k for k in REVIEWED_PUBLIC if k in set(runtime_routes(GUARDED.app))} - admitted, set(),
                         "a reviewed public route is refused")
        self.assertTrue(all(len(v) > 8 for v in REVIEWED_PUBLIC.values()))


class PrivateRoutesRefuse(unittest.TestCase):
    def setUp(self):
        self.c = client(GUARDED)

    def _send(self, method, path, headers=None):
        return self.c.request(method, path, headers=headers or {}, content=b"{}" if method != "GET" else None)

    def test_every_private_route_refuses_missing_and_wrong_credentials(self):
        checked = 0
        cookie = "vintos_read=" + house_auth.issue(SECRET, "read")
        for method, path in runtime_routes(GUARDED.app):
            if method == "WEBSOCKET" or (method, path) in REVIEWED_PUBLIC: continue
            url = concrete(path)
            for headers in ({}, {"X-Vintos-Secret": WRONG}, {"X-Vintos-Secret": ""},
                            {"Authorization": "Bearer " + SECRET}):
                r = self._send(method, url, headers)
                self.assertEqual(r.status_code, 401, (method, url, headers.keys(), r.status_code))
                self.assertEqual(r.headers.get("cache-control"), "no-store")
            if method not in ("GET",) and path not in house_auth.COOKIE_FORM_WRITES:
                r = self._send(method, url, {"Cookie": cookie})
                self.assertEqual(r.status_code, 401, ("a read session is not a write credential", method, url))
            checked += 1
        self.assertGreater(checked, 250)

    def test_the_named_routes_are_private(self):
        for method, path in MUST_BE_PRIVATE:
            self.assertFalse(anonymous_admits(GUARDED, method, path), (method, path))
            self.assertEqual(self._send(method, path).status_code, 401, (method, path))

    def test_both_house_websockets_close_before_accepting(self):
        from starlette.websockets import WebSocketDisconnect
        for name in ("telemetry", "events"):
            for headers, protocols in (({}, []), ({"X-Vintos-Secret": WRONG}, []),
                                       ({}, ["vintos-v1", "vintos-token.forged.ticket"]),
                                       ({}, ["vintos-token." + house_auth.issue(SECRET, "read")])):
                with self.assertRaises(WebSocketDisconnect) as caught:
                    with self.c.websocket_connect("/ws/" + name, headers=headers, subprotocols=protocols):
                        pass
                self.assertEqual(caught.exception.code, 4401)

    def test_stratagem_owner_controls_need_the_real_credential(self):
        import stratagem
        calls = []
        original = getattr(stratagem, "owner_token", None)
        stratagem.owner_token = lambda: calls.append("token") or "fixture"
        try:
            cookie = "vintos_read=" + house_auth.issue(SECRET, "read")
            for headers in ({}, {"Cookie": cookie}, {"X-Vintos-Secret": WRONG},
                            {"Authorization": "Bearer " + SECRET}):
                for action in ("charter", "stop", "reveal"):
                    self.assertEqual(self._send("POST", "/api/stratagem/owner/" + action, headers).status_code, 401)
        finally:
            if original is not None: stratagem.owner_token = original
        self.assertEqual(calls, [], "the owner token was produced for a caller without the credential")

    def test_the_session_endpoint_issues_only_for_the_credential(self):
        self.assertEqual(self._send("POST", "/api/auth/session").status_code, 401)
        self.assertEqual(self._send("POST", "/api/auth/session", {"X-Vintos-Secret": WRONG}).status_code, 401)
        r = self._send("POST", "/api/auth/session", {"X-Vintos-Secret": SECRET})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(SECRET, r.text)
        self.assertIn("HttpOnly", r.headers["set-cookie"])


class FailClosedWhenUnset(unittest.TestCase):
    def test_unset_credential_starts_answers_public_and_refuses_private(self):
        self.assertEqual(UNCONFIGURED.APP_SECRET, "")
        self.assertIn("[house] VINTOS_SECRET is unset", UNCONFIGURED_LOG)
        c = client(UNCONFIGURED)
        self.assertEqual(c.get("/api/client/capabilities").status_code, 200)
        self.assertEqual(c.get("/app/house_auth_client.js").status_code, 200)
        for method, path in MUST_BE_PRIVATE:
            for headers in ({}, {"X-Vintos-Secret": ""}, {"X-Vintos-Secret": SECRET}):
                r = c.request(method, path, headers=headers, content=b"{}" if method != "GET" else None)
                self.assertEqual(r.status_code, 503, (method, path, r.status_code))
        self.assertEqual(c.post("/api/auth/session", headers={"X-Vintos-Secret": ""}).status_code, 503)
        from starlette.websockets import WebSocketDisconnect
        for name in ("telemetry", "events"):
            with self.assertRaises(WebSocketDisconnect):
                with c.websocket_connect("/ws/" + name, headers={"X-Vintos-Secret": ""}): pass

    def test_weak_or_retired_values_are_unset(self):
        for value in ("", "short-value", " " + SECRET, SECRET + "\n"):
            self.assertIsNotNone(house_auth.problem(value), value)
        self.assertIsNone(house_auth.problem(SECRET))

    def test_robot_bridge_fails_closed_without_a_credential(self):
        from fastapi.testclient import TestClient
        saved = os.environ.pop("VINTOS_SECRET", None)
        try:
            for cached in ("robot_bridge", "house_auth"): sys.modules.pop(cached, None)
            with redirect_stderr(io.StringIO()):
                import robot_bridge
            self.assertEqual(robot_bridge.APP_SECRET, "")
            c = TestClient(robot_bridge.app)
            self.assertEqual(c.get("/health").status_code, 200)
            for headers in ({}, {"X-Vintos-Secret": ""}):
                self.assertEqual(c.get("/api/robot/state", headers=headers).status_code, 503)
                self.assertEqual(c.post("/api/robot/stop", headers=headers, json={}).status_code, 503)
            os.environ["VINTOS_SECRET"] = SECRET
            for cached in ("robot_bridge", "house_auth"): sys.modules.pop(cached, None)
            import robot_bridge as rb2
            self.assertEqual(TestClient(rb2.app).get("/api/robot/state", headers={"X-Vintos-Secret": WRONG}).status_code, 401)
        finally:
            if saved is not None: os.environ["VINTOS_SECRET"] = saved
            sys.modules.pop("robot_bridge", None)


# --- no built-in credential anywhere ------------------------------------------------------------
TOKEN = re.compile(rb"[A-Za-z0-9._~+/-]{8,80}")
DEFAULTED = [
    re.compile(r"""environ\.get\(\s*["']VINTOS_SECRET["']\s*,\s*["'][^"']+["']"""),   # an environment read with a fallback value
    re.compile(r"""getenv\(\s*["']VINTOS_SECRET["']\s*,\s*["'][^"']+["']"""),
    re.compile(r"""\$\{VINTOS_SECRET:-[^}]+\}"""),                                  # a shell fallback value
    re.compile(r"""\bsecret\s*:\s*['"][^'"]{6,}['"]"""),                           # a JS object literal value
]


def _retired(blob):
    return any(hashlib.sha256(t).hexdigest() == house_auth.LEGACY_SHA256 for t in set(TOKEN.findall(blob)))


class NoBuiltInCredential(unittest.TestCase):
    def test_served_pages_and_scripts_carry_no_credential(self):
        c = client(GUARDED)
        served = ["/", "/app/", "/app/house_auth_client.js", "/app/client_lifecycle.js",
                  "/app/stratagem_voice.js", "/app/avatar-bundle.js", "/app/manifest.json"]
        for path in served:
            r = c.get(path, follow_redirects=True)
            self.assertFalse(_retired(r.content), path)
            self.assertNotIn(SECRET.encode(), r.content, path)
            self.assertFalse(DEFAULTED[3].search(r.text), path)
        for f in (SRV / "website").rglob("*"):
            if f.is_file():
                self.assertFalse(_retired(f.read_bytes()), f)

    def test_no_source_file_has_a_default_or_the_retired_value(self):
        offenders = []
        for f in REPO.rglob("*"):
            if ".git" in f.parts or not f.is_file() or f.stat().st_size > 4_000_000: continue
            blob = f.read_bytes()
            if b"\0" in blob[:4096]: continue
            text = blob.decode("utf-8", "replace")
            if _retired(blob): offenders.append(("retired value", str(f.relative_to(REPO))))
            if f.suffix in (".py", ".sh", ".js", ".html", ".cjs", ".service", ".conf"):
                for rx in DEFAULTED[:3]:
                    if rx.search(text): offenders.append(("default", str(f.relative_to(REPO))))
        self.assertEqual(offenders, [])

    def test_handlers_compare_in_constant_time(self):
        files = [REPO / "bin/server.py", REPO / "scripts/watch_routes.py", REPO / "scripts/robot_bridge.py",
                 REPO / "bin/avatar_stage.py", REPO / "bin/study_chat.py", REPO / "scripts/desktop_agent.py",
                 REPO / "bin/merged_full_route.py"] + list((REPO / "bin/server_domains").glob("*.py"))
        rx = re.compile(r"(==|!=)\s*(APP_SECRET|app_secret|secret)\b|\b(APP_SECRET|app_secret)\s*(==|!=)")
        found = [(f.name, i + 1) for f in files for i, line in enumerate(f.read_text().splitlines())
                 if rx.search(line) and not line.lstrip().startswith("#")]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
