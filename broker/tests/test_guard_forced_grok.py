#!/usr/bin/env python3
"""When the toggled mind declines and the guard forces Grok, the reply comes from Grok (Gloria, 2026-10-15: "I SHOULD
have received a Grok turn but I didn't"). The forced turn was checked only after the Sol, Argon and local toggles, so on
Argon the "reroute" asked Argon again, and the notice said Grok had answered.

Isolation: scratch HOME and mode file; httpx is a stub that records what it was sent; the Argon, Sol and Gemma drafts
are stubs that count calls; paid reservation is a stub; every socket is refused."""
import asyncio, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="guard-forced-grok-")
os.environ["HOME"] = HOME
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
def _no_net(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

SENT = []
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None, headers=None, **k):
        SENT.append(url)
        return _Resp({"choices": [{"message": {"content": "Grok here."}, "finish_reason": "stop"}], "model": json.get("model")})
sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_Client)

import importlib.util
spec = importlib.util.spec_from_file_location("model_router_guard", os.path.join(REPO, "bin", "model_router.py"))
MR = importlib.util.module_from_spec(spec); spec.loader.exec_module(MR)
MR.httpx = sys.modules["httpx"]
MR._reserve_provider = lambda *a, **k: "r"
MR._MODE_FILE = os.path.join(HOME, "model-mode.json")
DRAFTS = []
async def _draft(name):
    DRAFTS.append(name); return "%s here." % name, ""
MR.gemini_draft = lambda *a, **k: _draft("argon")
MR.sol_draft = lambda *a, **k: _draft("sol")
async def _gemma(*a, **k):
    DRAFTS.append("local"); return "local here."
MR.gemma_call = _gemma
check("the mode file and the senders are throwaway stubs",
      MR._MODE_FILE.startswith(HOME) and MR.httpx is sys.modules["httpx"] and MR._reserve_provider() == "r")

def route():
    SENT.clear(); DRAFTS.clear()
    return asyncio.run(MR.route_reply_result("avatar", "You are Vintos.", [{"role": "user", "content": "Hi."}],
                                             {"max_tokens": 900}, "http://shim.test/v1/chat/completions", {}, "grok-4"))

for mode in ("argon", "sol", "local"):
    json.dump({"mode": mode, "force_grok_turns": 0}, open(MR._MODE_FILE, "w"))
    MR.arm_grok_turns(1)
    res = route()
    check("on %s, a forced turn is answered by Grok" % mode,
          res["route"] == "grok(forced)" and res["text"] == "Grok here." and not DRAFTS, (res.get("route"), DRAFTS))
    check("on %s, the force is spent by that one turn" % mode, MR.read_mode().get("force_grok_turns") == 0, MR.read_mode())
    check("on %s, the toggle itself is not changed" % mode, MR.read_mode().get("mode") == mode, MR.read_mode())
    res = route()
    check("on %s, the next turn is %s again" % (mode, mode), res["route"] != "grok(forced)" and DRAFTS == [mode],
          (res.get("route"), DRAFTS))

src = open(os.path.join(REPO, "bin", "server.py")).read()
check("the notice names who declined, not always Claude", '"%s declined, so this one reply came from Grok instead."' in src
      and "Toggle was off. Claude declined" not in src)
check("the notice says Grok answered only when it did", 'if "grok" in str(_model_used).lower() else' in src)
check("nothing opened a socket", socket.socket.connect is _no_net)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
