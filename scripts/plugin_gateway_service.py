#!/usr/bin/env python3
"""Loopback-only, token-authenticated Forge doorway to Gloria's relay process."""
import hmac
import json
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from plugin_send_guard import PolicyHold

MAX_BODY = 128 * 1024
TOKEN_FILE = Path(os.environ.get("VINTOS_PLUGIN_GATEWAY_TOKEN_FILE",
                                 "~/.config/vintos/plugin-gateway-token")).expanduser()


def secret(path=TOKEN_FILE):
    path = Path(path)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("plugin gateway token requires mode 0600")
    value = path.read_text().strip()
    if len(value) < 32 or any(c in value for c in "\r\n"):
        raise ValueError("plugin gateway token is invalid")
    return value


class API:
    def __init__(self, token, caller=None):
        self.token = token
        if caller is None:
            from plugin_gateway import call
            caller = call
        self.caller = caller

    def __call__(self, env, start):
        status, body = 200, {}
        try:
            if env.get("PATH_INFO") == "/health" and env.get("REQUEST_METHOD") == "GET":
                body = {"active": True, "surface": "forge", "transport": "loopback_policy_gateway"}
            elif env.get("PATH_INFO") == "/call" and env.get("REQUEST_METHOD") == "POST":
                supplied = env.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer ")
                if not hmac.compare_digest(supplied, self.token): raise PermissionError("gateway authority required")
                size = int(env.get("CONTENT_LENGTH") or 0)
                if not 0 < size <= MAX_BODY: raise ValueError("bounded request required")
                data = json.loads(env["wsgi.input"].read(size))
                if set(data) != {"plugin", "tool", "arguments", "purpose"}: raise ValueError("exact call envelope required")
                body = self.caller("forge", data["plugin"], data["tool"], data["arguments"], data["purpose"])
            else:
                status, body = 404, {"error":"unknown route"}
        except PolicyHold as exc:
            status, body = 200, {"ok":False, "held":True, "receipt":exc.receipt,
                                 "summary":"Connected action held by outbound policy; no provider call was made."}
        except PermissionError as exc:
            status, body = 403, {"error":type(exc).__name__, "detail":str(exc)[:160]}
        except (ValueError, KeyError, TypeError) as exc:
            status, body = 400, {"error":type(exc).__name__, "detail":str(exc)[:160]}
        except Exception:
            status, body = 500, {"error":"gateway_call_failed"}
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        labels = {200:"OK",400:"Bad Request",403:"Forbidden",404:"Not Found",500:"Internal Server Error"}
        start(f"{status} {labels[status]}", [("Content-Type","application/json"),
              ("Content-Length",str(len(encoded))),("Cache-Control","no-store")])
        return [encoded]


def main():
    class Server(ThreadingMixIn, WSGIServer): daemon_threads = True
    class Quiet(WSGIRequestHandler):
        def log_message(self, *args): pass
    with make_server("127.0.0.1", 8624, API(secret()), server_class=Server, handler_class=Quiet) as server:
        server.serve_forever()


if __name__ == "__main__": main()
