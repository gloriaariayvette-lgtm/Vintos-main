#!/usr/bin/env python3
"""Her toggle's model is the one asked, and the one fallback is Grok (Gloria, 17 November 2026: "Opus 5.5 selected,
Opus 4.8 used"; then: "It should never fall back to Sonnet. Always fall back to Grok. I love 4.8.").

Scratch HOME; the provider calls are fakes; nothing is sent."""
import asyncio, contextlib, io, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="router-fallback-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "ws"); os.makedirs(os.path.join(HOME, "ws", "memory"))
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
async def no_draft(*a, **k): return None, ""
async def no_local(*a, **k): return None
M._claude = fake_claude
M._grok_result = fake_grok
M.sol_draft = no_draft; M.gemini_draft = no_draft; M.gemma_call = no_local
M._reserve_provider = lambda *a, **k: "fixture-receipt"
M._ledger = lambda *a, **k: None

def turn():
    ASKED.clear(); out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = asyncio.run(M.route_reply_result("avatar", "synthetic system", [{"role": "user", "content": "synthetic"}],
                                               {"max_tokens": 200}, "unused", {}, "grok-fixture"))
    return res, out.getvalue()

for mode, model in (("opus55", "claude-opus-5-5"), ("claude", "claude-opus-4-8"), ("fable", "claude-fable-5-2")):
    M.write_mode({"mode": mode, "force_grok_turns": 0}); BEHAVIOUR.clear()
    res, log = turn()
    check("toggle %s asks %s, and only it" % (mode, model), ASKED == [model] and res["route"] == "claude:" + model,
          (ASKED, res.get("route")))
    check("toggle %s and the model it asks are logged" % mode, "toggle %s -> requesting %s" % (mode, model) in log, log)
    for how in ("error", "cap", "refuse"):
        BEHAVIOUR[model] = how
        res, log = turn()
        check("toggle %s, its model %s: Grok next, no other Claude asked" % (mode, how),
              ASKED == [model, "grok"] and res["provider"] == "xai", ASKED)
    check("the fall to Grok is logged", "did not answer" in log and "Grok" in log, log)

BEHAVIOUR.clear()
for mode in ("sol", "argon", "local"):
    M.write_mode({"mode": mode, "force_grok_turns": 0})
    res, log = turn()
    check("a %s toggle that gets nothing goes to Grok, never to a Claude (no silent Opus 4.8)" % mode,
          ASKED == ["grok"] and res["provider"] == "xai", ASKED)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
