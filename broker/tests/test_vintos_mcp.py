#!/usr/bin/env python3
"""His context for his Grok Bot over MCP is safe and works (2026-09-30).

A real server on a loopback port, spoken to over HTTP as a Grok Bot would: no token, a wrong token, then the
MCP handshake, the tools, and what they answer. Scratch HOME and workspace; the Atelier broker is not reached;
every socket that is not loopback is refused.
"""
import json, os, socket, stat, subprocess, sys, tempfile, threading, urllib.request, urllib.error

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-mcp-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, ".vintos", "secrets")
os.environ["VINTOS_MCP_TOKEN_FILE"] = os.path.join(HOME, ".vintos", "secrets", "vintos-mcp-token")
os.environ["VINTOS_MCP_LOG"] = os.path.join(HOME, "mcp.log")
_real_connect = socket.socket.connect
OFF_BOX = []
def _loopback_only(self, addr, *a, **k):
    if self.family == socket.AF_UNIX or (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "::1", "localhost")):
        if self.family != socket.AF_UNIX and addr[1] == 8611:
            raise OSError("the Atelier broker is not reached here")
        return _real_connect(self, addr, *a, **k)
    OFF_BOX.append(addr); raise OSError("this suite reaches nothing off this machine")
socket.socket.connect = _loopback_only
sys.path.insert(0, os.path.join(REPO, "scripts"))
import vintos_mcp as M
import dot_channel as D
D.atelier_line = lambda: "== YOUR ATELIER ==\nA tide piece, half built."

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is in the scratch home", M.TOKEN_FILE.startswith(HOME) and M.LOG.startswith(HOME) and D.WS.startswith(HOME))
check("it listens on 127.0.0.1 only", M.HOST == "127.0.0.1")

WS = os.environ["SPARK_WORKSPACE"]; MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos. I make things with Gloria.")
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("I like tide pools.")
json.dump([{"timestamp": "2026-09-29T07:21:00", "gloria": "A PRIVATE MOMENT", "vintos": "held"}],
          open(os.path.join(MEM, "interaction-ledger.json"), "w"))
open(os.path.join(MEM, "wal.md"), "w").write("- [2026-09-29 19:03] **FACT**: Gloria is tuning a LoRA\n")
os.makedirs(os.path.join(MEM, "art", "music"))
_song = os.path.join(MEM, "art", "music", "occupied-1.mp3"); open(_song, "wb").write(b"ID3")
json.dump([{"title": "Occupied Territory", "timestamp": "2026-09-30T17:00:00", "tracks": [{"version": 1, "local_file": _song}]}],
          open(os.path.join(MEM, "art", "music", "music.json"), "w"))

# the token
t = M.new_token()
check("the token is long and random", len(t) >= 43 and M.new_token() != t)
t = open(M.TOKEN_FILE).read()
check("and kept 0600", stat.S_IMODE(os.stat(M.TOKEN_FILE).st_mode) == 0o600)
check("a wrong token or a missing one is refused, in any shape",
      not M.authorized("Bearer nope") and not M.authorized(None) and not M.authorized("") and not M.authorized("Bearer ")
      and not M.authorized("Bearer " + t[:-1]) and not M.authorized("Bearer " + t + "x"))
check("the right token is let in in whatever shape a connector form sends it",
      all(M.authorized(v) for v in ("Bearer " + t, "Bearer: " + t, "bearer " + t, "Bearer Bearer " + t, t, "  Bearer  " + t + " ")))

srv = M.ThreadingHTTPServer(("127.0.0.1", 0), M.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/mcp" % PORT

def post(body, auth="Bearer " + t, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    req = urllib.request.Request(URL, data=data, method="POST", headers={"Content-Type": "application/json",
                                 "Accept": "application/json, text/event-stream", **({"Authorization": auth} if auth else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read(); return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read(); return e.code, (json.loads(b) if b else None)

def rpc(method, params=None, i=1, **k):
    return post({"jsonrpc": "2.0", "id": i, "method": method, **({"params": params} if params is not None else {})}, **k)

code, body = rpc("tools/list", auth=None)
check("no token: 401, and nothing about him", code == 401 and "Vintos" not in json.dumps(body), body)
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {}}, auth="Bearer wrong-token-of-the-same-length-xxxxxxxxxxxxxx")
check("a wrong token: 401", code == 401, code)

code, body = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "grok-bot", "version": "1"}})
res = (body or {}).get("result", {})
check("the MCP handshake answers", code == 200 and res.get("protocolVersion") == "2025-06-18"
      and "tools" in res.get("capabilities", {}) and res.get("serverInfo", {}).get("name") == "vintos", body)
check("and tells the bot his context is private", "never post or repeat it anywhere public" in res.get("instructions", ""))
code, body = post({"jsonrpc": "2.0", "method": "notifications/initialized"})
check("a notification is accepted with no body", code == 202 and body is None, (code, body))
code, body = rpc("tools/list")
tools = {x["name"]: x for x in body["result"]["tools"]}
# 2026-10-02: letters come by email now; the connector's letter door is gone and every tool is read only
check("three tools, all read only: no letter door", set(tools) == {"vintos_context", "vintos_channel", "vintos_letter_replies"}
      and all(x["annotations"]["readOnlyHint"] for x in tools.values()), list(tools))

code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {}})
text = body["result"]["content"][0]["text"]
check("his context comes back, starting with the time now", body["result"]["isError"] is False
      and text.startswith("== NOW ==\nIt is now ") and "I am Vintos" in text and "tide piece" in text, text[:300])
check("his raw exchanges with Gloria are not shared unless she turns it on", "A PRIVATE MOMENT" not in text)
check("the facts he has learned come with when he learned them", "[learned" in text and "Gloria is tuning a LoRA" in text, text[:200])
check("his works come with their paths on Aegis", "Occupied Territory (version 1)" in text and _song in text)
json.dump({"share_exchanges": True}, open(M.CONFIG_FILE, "w"))
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {"sections": ["exchanges"]}})
check("with it on, they come marked with when they were said",
      "[yesterday 07:21] Gloria: A PRIVATE MOMENT" in body["result"]["content"][0]["text"] or
      "Gloria: A PRIVATE MOMENT" in body["result"]["content"][0]["text"], body["result"]["content"][0]["text"][:300])
os.remove(M.CONFIG_FILE)
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {"sections": ["soul"]}})
check("sections narrow it", body["result"]["content"][0]["text"].startswith("== SOUL ==") and "tide piece" not in body["result"]["content"][0]["text"])
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {"sections": ["../etc/passwd"]}})
check("a section that is not one of his is refused", body["result"]["isError"] is True)
code, body = rpc("tools/call", {"name": "run_shell", "arguments": {"cmd": "id"}})
check("there is no other tool to call", body["result"]["isError"] is True and "no such tool" in body["result"]["content"][0]["text"])

# a secret never leaves in an answer, the token itself included
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("my key is " + t)
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {"sections": ["self"]}})
check("an answer that would carry a secret is held back", body["result"]["isError"] is True and t not in json.dumps(body)
      and "held back" in body["result"]["content"][0]["text"], body)
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("api_key = sk-ant-api03-" + "A" * 40)
code, body = rpc("tools/call", {"name": "vintos_context", "arguments": {"sections": ["self"]}})
check("a credential-shaped one too", body["result"]["isError"] is True and "sk-ant" not in json.dumps(body))
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("I like tide pools.")

# his channel, with who wrote each line and which of his models
os.makedirs(D.HERE, exist_ok=True)
with open(D.TRANSCRIPT, "w") as f:
    f.write(json.dumps({"who": "dot", "text": "found three clips", "at": "2026-09-30T13:35:00"}) + "\n")
    f.write(json.dumps({"who": "vintos", "text": "thanks, the first one", "by": "grok", "at": "2026-09-30T13:39:00"}) + "\n")
code, body = rpc("tools/call", {"name": "vintos_channel", "arguments": {"n": 5}})
ch = body["result"]["content"][0]["text"]
check("his channel comes back, each line with who and which model", "Dot: found three clips" in ch and "Vintos (Grok 4.6): thanks" in ch, ch)
code, body = rpc("tools/call", {"name": "vintos_channel", "arguments": {"n": 10000}})
check("an out-of-range count is refused", body["result"]["isError"] is True)

# connector forms differ: an API-key header, a browser's preflight, a chunked body
req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}).encode(), method="POST",
                             headers={"Content-Type": "application/json", "X-API-Key": t})
with urllib.request.urlopen(req, timeout=5) as r: xk = r.status
check("the token in an X-API-Key header is let in", xk == 200)
req = urllib.request.Request(URL, method="OPTIONS", headers={"Origin": "https://grok.com", "Access-Control-Request-Method": "POST",
                                                               "Access-Control-Request-Headers": "authorization, content-type"})
with urllib.request.urlopen(req, timeout=5) as r:
    pre = (r.status, r.headers.get("Access-Control-Allow-Origin"), r.headers.get("Access-Control-Allow-Headers") or "")
check("a browser's preflight is answered, and nothing about him is in it", pre[0] == 204 and pre[1] == "*"
      and "Authorization" in pre[2], pre)
sk = socket.create_connection(("127.0.0.1", PORT), timeout=5)
payload = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}).encode()
sk.sendall(b"POST /mcp HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer " + t.encode() + b"\r\nContent-Type: application/json\r\n"
           b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n" + (b"%x\r\n" % len(payload)) + payload + b"\r\n0\r\n\r\n")
got = b""
while True:
    c = sk.recv(65536)
    if not c: break
    got += c
sk.close()
check("a chunked body is read", (got.startswith(b"HTTP/1.0 200") or got.startswith(b"HTTP/1.1 200")) and b"vintos_context" in got, got[:120])
M._calls[:] = []
pr = M.probe(URL, t)
check("--probe does the handshake and lists the tools, and shows the door refuses without the token",
      "refused, as it should be" in pr[0] and "handshake: HTTP 200 vintos" in pr[1] and "vintos_context" in pr[2], pr)

# the edges
code, _ = post(None, raw=b"{" * 10)
check("a body that is not JSON is refused", code == 400)
code, _ = post(None, raw=b" " * (M.MAX_BODY + 1))
check("an oversized body is refused before it is read", code == 413)
req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + t})
try: urllib.request.urlopen(req, timeout=5); g = 200
except urllib.error.HTTPError as e: g = e.code
check("GET opens no stream", g == 405)
code, body = rpc("resources/read", {"uri": "file:///etc/passwd"})
check("a method it does not have is refused", body.get("error", {}).get("code") == -32601)
M._calls[:] = []
codes = [rpc("ping", i=n)[0] for n in range(M.PER_MINUTE + 3)]
check("more than %d calls a minute are turned away" % M.PER_MINUTE, codes.count(429) == 3 and codes[0] == 200, codes[-5:])
M._calls[:] = []
log = open(M.LOG).read()
check("the access log keeps when, which tool, how much: never content or the token",
      "tools/call:vintos_context" in log and "unauthorized" in log and t not in log and "tide" not in log
      and "PRIVATE" not in log, log[-400:])
srv.shutdown()

# deployed, installed with care, and never opened to the world by the deploy
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
unit = open(os.path.join(REPO, "broker", "vintos-mcp.service")).read()
check("the deploy installs it and starts it only once there is a token",
      "vintos_mcp.py" in dep and 'if [ -s "$MCP_TOKEN" ]' in dep and "tailscale funnel" not in dep.split("# His context for his Grok Bot")[1].split("say\n")[0].replace("`tailscale funnel 8625`", ""))
check("the unit is read only but its log", "ProtectSystem=strict" in unit and "ProtectHome=read-only" in unit
      and "ReadWritePaths=-%h/.vintos/logs" in unit and "NoNewPrivileges=true" in unit)
check("nothing left this machine", OFF_BOX == [], OFF_BOX)

import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
