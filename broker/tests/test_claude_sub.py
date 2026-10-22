#!/usr/bin/env python3
"""The Study and the Forge answered on Gloria's Claude subscription first (claude_sub.py, 22 October).

Every store is a scratch workspace, the subscription's venv child is a stub, the paid API is a stub, and every
socket is refused: nothing here reaches Claude, the subscription or the network.
"""
import json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="claude-sub-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
os.environ.pop("VINTOS_SUBSCRIPTION", None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
PAID = []
class _Resp:
    def json(self): return {"content": [{"type": "text", "text": "paid answer"}], "usage": {}, "stop_reason": "end_turn"}
sys.modules["requests"] = types.SimpleNamespace(post=lambda url, **kw: (PAID.append(kw.get("json")), _Resp())[1])

import claude_sub as S
import claude_cache as C
import forge_build as FB

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

check("its stores are in the scratch workspace, and its venv child is not the real one",
      S.USAGE.startswith(HOME) and S.SDK_PY.startswith(HOME) and not os.path.exists(S.SDK_PY))
check("the Study and the Forge go to the subscription; Slack and the rest do not",
      S.subscribed("study-fix") and S.subscribed("forge-study") and S.subscribed("forge-review")
      and not S.subscribed("slack:claude-opus-5-5") and not S.subscribed(""))
os.environ["VINTOS_SUBSCRIPTION"] = "0"
check("VINTOS_SUBSCRIPTION=0 turns it off", not S.subscribed("study-fix"))
os.environ.pop("VINTOS_SUBSCRIPTION")

seen = []
check("an answer comes back as text, with the same model and effort asked",
      S.ask("claude-opus-5-5", "sys", "q", caller="study-fix", effort="low",
            run=lambda r: (seen.append(r), {"ok": True, "text": "fixed"})[1]) == "fixed"
      and seen[0]["model"] == "claude-opus-5-5" and seen[0]["effort"] == "low")
try:
    S.ask("claude-opus-5-5", "s", "q", caller="study-fix", run=lambda r: {"ok": False, "error": "usage limit"}); raised = ""
except RuntimeError as e:
    raised = str(e)
check("a refusal or limit raises, saying why", "usage limit" in raised, raised)
rows = [json.loads(l) for l in open(S.USAGE)]
check("what it answered is kept in subscription-usage.jsonl, never the paid ledger",
      [r["ok"] for r in rows] == [True, False] and not os.path.exists(C.USAGE))
check("the venv child signs in only with the stored login", all(k in S.AUTH_ENV for k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")))

_real = S.ask
S.ask = lambda *a, **k: "from the subscription"
out = C.ask("claude-opus-5-5", "s", "u", 100, caller="study-fix")
check("claude_cache: a Study call is answered by the subscription and nothing is paid", out == "from the subscription" and PAID == [], PAID)
C.ask("claude-haiku-5-5", "s", "u", 100, caller="slack:claude-haiku-5-5")
check("claude_cache: a Slack call still goes to the API (not moved)", len(PAID) == 1)
def _fail(*a, **k): raise RuntimeError("subscription: usage limit")
S.ask = _fail
out = C.ask("claude-sonnet-5-5", "s", "u", 100, caller="forge-study")
check("claude_cache: when the subscription cannot answer, that call goes to the API", out == "paid answer" and len(PAID) == 2)
S.ask = lambda *a, **k: "PASS"
check("the Forge's review is answered by the subscription first",
      FB._fable("review", [{"role": "user", "content": "code"}]) == "PASS" and len(PAID) == 2)
S.ask = _real

check("nothing reached the network", NET == [] and socket.socket.connect is _no_net, NET[:3])
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
