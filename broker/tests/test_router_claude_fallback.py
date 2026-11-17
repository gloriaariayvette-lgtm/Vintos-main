#!/usr/bin/env python3
"""Her toggle's model is the one asked, and a Claude that does not answer falls to the other Claudes before Grok
(Gloria, 17 November 2026: "Opus 5.5 selected, Opus 4.8 used", and "always falls to Grok").

Scratch HOME; the provider calls are fakes; nothing is sent."""
import asyncio, contextlib, io, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="router-fallback-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "ws"); os.makedirs(os.path.join(HOME, "ws", "memory"))
os.environ.pop("VINTOS_CLAUDE_FALLBACKS", None)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))
import model_router as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  %r" % (d,)))

GR = M.GR
ASKED = []
BEHAVIOUR = {}
async def fake_claude(system_text, convo, params, reason, paid_reservation=None, model=None):
    ASKED.append(model)
    how = BEHAVIOUR.get(model, "ok")
    if how == "ok":
        return GR.make_result("anthropic", model=model, status="valid", text="synthetic reply from " + model, finish_reason="stop")
    if how == "refuse":
        return GR.make_result("anthropic", model=model, status="held", reason="refusal")
    if how == "cap":
        raise RuntimeError("paid budget: 400 of 400 reservations used today for anthropic; 1 more refused")
    return GR.make_result("anthropic", model=model, status="error", reason="HTTP 529 overloaded")
async def fake_grok(convo, params, endpoint, headers, model, system_text, reserved=False):
    ASKED.append("grok")
    return GR.make_result("xai", model=model, status="valid", text="synthetic grok", finish_reason="stop")
M._claude = fake_claude
M._grok_result = fake_grok
M._reserve_provider = lambda *a, **k: "fixture-receipt"
M._ledger = lambda *a, **k: None

def turn():
    ASKED.clear(); out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = asyncio.run(M.route_reply_result("avatar", "synthetic system", [{"role": "user", "content": "synthetic"}],
                                               {"max_tokens": 200}, "unused", {}, "grok-fixture"))
    return res, out.getvalue()

M.write_mode({"mode": "opus55", "force_grok_turns": 0})
BEHAVIOUR.clear()
res, log = turn()
check("the toggle on Opus 5.5 asks Opus 5.5, and only it", ASKED == ["claude-opus-5-5"] and res["route"] == "claude:claude-opus-5-5",
      (ASKED, res.get("route")))
check("the toggle and the model it asks are logged", "toggle opus55 -> requesting claude-opus-5-5" in log, log)

BEHAVIOUR.update({"claude-opus-5-5": "error"})
res, log = turn()
check("Opus 5.5 down: Sonnet 5.5 answers, not Grok", ASKED == ["claude-opus-5-5", "claude-sonnet-5-5"]
      and res["route"] == "claude:claude-sonnet-5-5(fallback from claude-opus-5-5)" and res["text"].endswith("claude-sonnet-5-5"),
      (ASKED, res.get("route")))
check("the stages keep the failed Opus 5.5 and the Sonnet that answered",
      [s["model"] for s in res["stages"]] == ["claude-opus-5-5", "claude-sonnet-5-5"], [s["model"] for s in res["stages"]])
check("and it says so in the log", "asking claude-sonnet-5-5 before Grok" in log, log)

BEHAVIOUR.update({"claude-sonnet-5-5": "error"})
res, log = turn()
check("every Claude down: Grok, last", ASKED == ["claude-opus-5-5", "claude-sonnet-5-5", "grok"] and res["provider"] == "xai",
      (ASKED, res.get("route")))
check("logged as every Claude option out", "every Claude option is out" in log, log)

BEHAVIOUR.clear(); BEHAVIOUR.update({"claude-opus-5-5": "cap"})
res, log = turn()
check("the day's Anthropic cap spent: straight to Grok (it is every Claude's cap)", ASKED == ["claude-opus-5-5", "grok"], ASKED)

BEHAVIOUR.clear(); BEHAVIOUR.update({"claude-opus-5-5": "refuse"})
res, log = turn()
check("a refusal goes to Grok as before (the guard's rule), no other Claude asked", ASKED == ["claude-opus-5-5", "grok"], ASKED)

BEHAVIOUR.clear(); BEHAVIOUR.update({"claude-opus-4-8": "error"})
M.write_mode({"mode": "claude", "force_grok_turns": 0})
res, log = turn()
check("her Opus 4.8 choice, down: Opus 5.5 next", ASKED == ["claude-opus-4-8", "claude-opus-5-5"], ASKED)

BEHAVIOUR.clear()
M.write_mode({"mode": "local", "force_grok_turns": 0})
async def no_local(*a, **k): return None
M.gemma_call = no_local
res, log = turn()
check("a local toggle that gets nothing falls to Opus 5.5, never Opus 4.8", ASKED == ["claude-opus-5-5"], ASKED)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
