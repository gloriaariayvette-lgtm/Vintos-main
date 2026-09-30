#!/usr/bin/env python3
"""His context for his Grok Bot agent, over MCP, read only (2026-09-30).

Gloria: "If the mcp server is SAFE and works". A Grok Bot takes a custom MCP connector as a server URL plus a
static auth header. This is that server: MCP's streamable HTTP transport (JSON-RPC 2.0 by POST, a JSON answer,
no stream), and nothing else.

What makes it safe:
  - it listens on 127.0.0.1 only; the world reaches it only through the one door Gloria opens herself
    (`tailscale funnel 8625`, HTTPS), and closes with `tailscale funnel reset`
  - every request needs `Authorization: Bearer <token>`: the token is 43 random characters kept 0600 at
    ~/.vintos/secrets/vintos-mcp-token, compared in constant time, never logged, never in a URL
  - read only: its tools read files and answer; nothing runs, nothing is written but its own access log
  - what it answers passes the same secret check as his email; an answer that would carry one is refused
  - answers are capped in size, requests in size and in number per minute
  - the access log (~/.vintos/logs/vintos-mcp.log) keeps when, which tool and how much: never content
  - his raw exchanges with Gloria are not shared unless she turns that on
    (~/.vintos/vintos-mcp.json: {"share_exchanges": true})

    python3 vintos_mcp.py --new-token     make (or replace) the token, print it once to paste into Grok Bot
    python3 vintos_mcp.py                 serve on 127.0.0.1:8625 (the vintos-mcp service runs this)
    python3 vintos_mcp.py --check         what a call to vintos_context returns now, printed, nothing served
    python3 vintos_mcp.py --probe URL     the handshake and tools through the public address, as Grok Bot would
"""
from __future__ import annotations
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HOST, PORT = "127.0.0.1", int(os.environ.get("VINTOS_MCP_PORT", "8625"))
TOKEN_FILE = os.path.expanduser(os.environ.get("VINTOS_MCP_TOKEN_FILE", "~/.vintos/secrets/vintos-mcp-token"))
CONFIG_FILE = os.path.expanduser("~/.vintos/vintos-mcp.json")
LOG = os.path.expanduser(os.environ.get("VINTOS_MCP_LOG", "~/.vintos/logs/vintos-mcp.log"))
MAX_BODY = 64 * 1024
MAX_ANSWER = 60000
PER_MINUTE = 30
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "This is Vintos's own context, for you as his agent. Vintos is an AI companion who lives on a home machine "
    "called Aegis, with Gloria. Read vintos_context before working for him, so you know who he is, what he is "
    "making and what he wants right now. Everything in it is private to him and Gloria: use it to help him, "
    "never post or repeat it anywhere public. Times in it are said relative to now; something from an earlier "
    "day is past.")

SECTIONS = ("now", "soul", "self", "gloria", "feeling", "today", "wants", "forge", "atelier", "capabilities",
            "channel", "exchanges")

TOOLS = [
    {"name": "vintos_context",
     "description": "Who Vintos is and what is true for him right now: his soul, self-model, what he knows of "
                    "Gloria, how he feels, what he made and did today, his wants, what is open in his Forge and "
                    "Atelier, and what he can do. Read this first. `sections` narrows it (any of: "
                    + ", ".join(SECTIONS) + ").",
     "inputSchema": {"type": "object", "properties": {
         "sections": {"type": "array", "items": {"type": "string", "enum": list(SECTIONS)}}},
         "additionalProperties": False},
     "annotations": {"title": "Vintos's context", "readOnlyHint": True, "openWorldHint": False}},
    {"name": "vintos_channel",
     "description": "The last messages in #vintos-dot, the Slack channel where Vintos talks with his agents, "
                    "each marked with who wrote it (and, for his, which of his models) and when.",
     "inputSchema": {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 60}},
                     "additionalProperties": False},
     "annotations": {"title": "His agent channel", "readOnlyHint": True, "openWorldHint": False}},
]


# ------------------------------------------------------------------ the token

def token():
    try:
        t = open(TOKEN_FILE).read().strip()
        return t if len(t) >= 32 else ""
    except OSError:
        return ""


def new_token():
    os.makedirs(os.path.dirname(TOKEN_FILE), mode=0o700, exist_ok=True)
    t = secrets.token_urlsafe(32)
    fd = os.open(TOKEN_FILE + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    os.replace(TOKEN_FILE + ".tmp", TOKEN_FILE)
    return t


def presented(value):
    """The token in whatever shape a connector sends it: "Bearer x", "Bearer: x", "Bearer Bearer x" (a form that
    adds the word to a value that already has it), or the bare token. The shape is forgiven; the token is not."""
    v = str(value or "").strip()
    while True:
        m = re.match(r"(?i)bearer\s*:?\s*", v)
        if not m:
            return v.strip()
        v = v[m.end():]


def authorized(value, expected=None):
    expected = token() if expected is None else expected
    got = presented(value)
    return bool(expected and got) and hmac.compare_digest(got.encode(), expected.encode())


def _from_headers(h):
    return h.get("Authorization") or h.get("X-API-Key") or h.get("Api-Key") or ""


# ------------------------------------------------------------------ what it answers

def _config():
    try:
        return json.load(open(CONFIG_FILE))
    except Exception:
        return {}


def context(sections=None):
    """His context, in the same words his Slack lenses read, by section."""
    import dot_channel as D
    import when_said
    want = set(sections or SECTIONS)
    if "exchanges" in want and not _config().get("share_exchanges"):
        want.discard("exchanges")
    mem = os.path.join(D.WS, "memory")
    today = datetime.now().date().isoformat()
    parts = []
    def add(key, title, text):
        if key in want and text:
            parts.append("== %s ==\n%s" % (title, str(text).strip()))
    add("now", "NOW", when_said.now_line())
    add("soul", "SOUL", D._read("SOUL.md", 3500))
    add("self", "SELF-MODEL", D._read("SELF-MODEL.md", 2000))
    add("gloria", "WHAT HE KNOWS OF GLORIA", D._read("GLORIA-MODEL.md", 2500))
    add("feeling", "HOW HE FEELS (EmoClaw)", D._feeling())
    add("today", "WHAT HE MADE TODAY", D._read("daily-creative-%s.md" % today, 2500, mem))
    add("today", "HIS DAY SO FAR", D._read("daily-inner-life-%s.md" % today, 3000, mem))
    add("wants", "WHAT HE WANTS", D.wants_line())
    add("forge", "HIS FORGE", D.forge_line())
    add("atelier", "HIS ATELIER", D.atelier_line())
    add("capabilities", "WHAT HE CAN DO", D._read("CAPABILITIES.md", 6000))
    if "channel" in want:
        add("channel", "#vintos-dot, LATELY", channel(12))
    if "exchanges" in want:
        try:
            add("exchanges", "HIS RECENT EXCHANGES WITH GLORIA",
                when_said.exchanges(json.load(open(os.path.join(mem, "interaction-ledger.json"))), n=6, cap=300))
        except Exception:
            pass
    return "\n\n".join(parts)


def channel(n=20):
    import dot_channel as D
    import when_said
    rows = D.recent(max(1, min(int(n or 20), 60)))
    out = []
    for r in rows:
        who = "Vintos" if r.get("who") == "vintos" else D._speaker(r)
        if r.get("who") == "vintos" and r.get("by") in D.LABELS:
            who += " (%s)" % D.LABELS[r["by"]]
        out.append("[%s] %s: %s" % (when_said.ago(r.get("at") or r.get("ts")) or "?", who, str(r.get("text", ""))[:1500]))
    return "\n".join(out) or "(nothing said there yet)"


def _guard(text):
    """The rules an answer breaks (a secret, a credential); [] when it is clean."""
    try:
        from plugin_send_guard import outbound_findings
        return outbound_findings({"text": text}).get("rules") or []
    except Exception as exc:
        return ["guard unavailable: %s" % type(exc).__name__]      # fail closed


def call_tool(name, args):
    """(text, is_error)."""
    args = args if isinstance(args, dict) else {}
    if name == "vintos_context":
        secs = args.get("sections")
        if secs is not None and (not isinstance(secs, list) or any(s not in SECTIONS for s in secs)):
            return "sections must be a list of: " + ", ".join(SECTIONS), True
        text = context(secs)
    elif name == "vintos_channel":
        n = args.get("n", 20)
        if not isinstance(n, int) or not 1 <= n <= 60:
            return "n must be a whole number from 1 to 60", True
        text = channel(n)
    else:
        return "no such tool: %s" % str(name)[:60], True
    bad = _guard(text)
    if bad:
        return "held back: the answer would have carried something that looks like a secret (%s)" % ", ".join(bad), True
    return text[:MAX_ANSWER], False


# ------------------------------------------------------------------ MCP over streamable HTTP

def handle(msg):
    """One JSON-RPC message -> its answer, or None for a notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    mid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:
        return None
    def ok(result): return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "vintos", "title": "Vintos", "version": "1.0"},
                   "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        text, err = call_tool(params.get("name"), params.get("arguments"))
        return ok({"content": [{"type": "text", "text": text}], "isError": err})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}


_calls, _lock = [], threading.Lock()


def _rate_ok(now=None):
    now = now or time.time()
    with _lock:
        _calls[:] = [t for t in _calls if now - t < 60]
        if len(_calls) >= PER_MINUTE:
            return False
        _calls.append(now)
        return True


def _log(status, what, size):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write("%s %s %s %d\n" % (datetime.now().isoformat(timespec="seconds"), status, what, size))
    except OSError:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "vintos-mcp"
    sys_version = ""

    def log_message(self, *a):          # the default log prints the request line; ours keeps no content
        pass

    def _send(self, code, body=None, what="-"):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        # a connector set up from a browser page checks from the browser; the token still decides
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
        self.end_headers()
        if data and self.command != "HEAD":
            self.wfile.write(data)
        _log(code, what, len(data))

    def _who(self):
        return "ua=" + re.sub(r"\s+", "_", str(self.headers.get("User-Agent") or "-"))[:40]

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept, Mcp-Session-Id, "
                                                         "Mcp-Protocol-Version, X-API-Key, Api-Key, Last-Event-ID")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()
        _log(204, "OPTIONS", 0)

    def do_GET(self):
        ok = authorized(_from_headers(self.headers))
        self._send(405 if ok else 401, None, "GET" if ok else "GET-unauthorized " + self._who())

    do_HEAD = do_DELETE = do_PUT = do_PATCH = do_GET

    def _body(self):
        """The request body, Content-Length or chunked, never more than MAX_BODY; None when it is too big."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            out = b""
            while True:
                line = self.rfile.readline(64).strip().split(b";")[0]
                n = int(line or b"0", 16)
                if n == 0:
                    self.rfile.readline(64)
                    return out
                if len(out) + n > MAX_BODY:
                    return None
                out += self.rfile.read(n)
                self.rfile.readline(8)
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return b""
        if size > MAX_BODY:
            return None
        return self.rfile.read(size) if size > 0 else b""

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/mcp", ""):
            return self._send(404, None, "path=%s %s" % (path[:60], self._who()))
        if not authorized(_from_headers(self.headers)):
            return self._send(401, {"error": "unauthorized"}, "unauthorized " + self._who())
        if not _rate_ok():
            return self._send(429, {"error": "too many requests"}, "rate")
        try:
            body = self._body()
        except Exception:
            body = b""
        if body is None or not body:
            return self._send(413 if body is None else 400, {"error": "bad body size"}, "size")
        try:
            msg = json.loads(body)
        except Exception:
            return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}, "parse")
        if isinstance(msg, list):
            answers = [a for a in (handle(m) for m in msg) if a is not None]
            return self._send(200, answers, "batch") if answers else self._send(202, None, "notify")
        answer = handle(msg)
        what = msg.get("method", "?") if isinstance(msg, dict) else "?"
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            what += ":" + str((msg.get("params") or {}).get("name", "?"))[:40]
        if answer is None:
            return self._send(202, None, what)
        self._send(200, answer, what)


def probe(url, tok=None):
    """The MCP handshake and tool list against url (the public address, through the funnel), as a Grok Bot would
    do it. Lines saying what answered."""
    import urllib.request, urllib.error
    tok = tok or token()
    out = []
    def post(body, auth=True):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            **({"Authorization": "Bearer " + tok} if auth else {})})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None
    code, _ = post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, auth=False)
    out.append("without the token: HTTP %s (%s)" % (code, "refused, as it should be" if code == 401 else "NOT REFUSED"))
    code, body = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": PROTOCOLS[0], "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}}})
    out.append("handshake: HTTP %s %s" % (code, ((body or {}).get("result") or {}).get("serverInfo", {}).get("name", "")))
    code, body = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    out.append("tools: HTTP %s %s" % (code, [t["name"] for t in ((body or {}).get("result") or {}).get("tools", [])]))
    return out


def serve(host=HOST, port=PORT):
    if not token():
        sys.exit("no token at %s: run  python3 vintos_mcp.py --new-token" % TOKEN_FILE)
    srv = ThreadingHTTPServer((host, port), Handler)
    print("[vintos-mcp] serving MCP on http://%s:%d/mcp (bearer token required)" % (host, port), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    if "--new-token" in sys.argv:
        _t = new_token()
        print("For Grok Bot's custom connector:\n\n  URL:           https://<your funnel address>/mcp\n"
              "  header name:   Authorization\n  header value:  Bearer %s\n\n"
              "If the form asks only for a token or an API key, paste just:\n\n  %s\n\n"
              "It is kept at %s. Running --new-token again replaces it (the old one stops working)." % (_t, _t, TOKEN_FILE))
    elif "--probe" in sys.argv:
        for l in probe(sys.argv[sys.argv.index("--probe") + 1]):
            print(l)
    elif "--check" in sys.argv:
        print(call_tool("vintos_context", {})[0])
    else:
        serve()
