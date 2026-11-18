#!/usr/bin/env python3
"""His subconscious on the MacBook's AEON answers directly, and his journal survives a slow local call (18 November).

The MacBook's LM Studio serves AEON with reasoning on unless told otherwise: calls came back empty (all reasoning) or
minutes late, and the journal's audit-2 call timed out at 180 s and lost the whole entry, two runs running.
  - the shim's MacBook lane always sends reasoning_effort "none" (the switch that works there) and enable_thinking
    false, whatever the caller asked; it keeps content only, and waits long enough for the reply it asked for;
  - the journal's local calls get time for the slowest lane, one retry, and a clear ERROR when they still fail;
    audit-2 failing keeps the synthesis instead of killing the entry.

Synthetic fixtures only; scratch HOME; urllib and requests are faked; every socket refused."""
import io, json, os, re, socket, sys, tempfile, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "bin"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="subcon-thinking-off-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

import vintos_claude_shim as S
S.LOG = os.path.join(TMP, "shim.log"); S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")

print("--- the MacBook lane: thinking off ---")
b = S.gemma_body({"model": "grok-x", "messages": [{"role": "user", "content": "x"}], "max_tokens": 50,
                  "reasoning_effort": "low", "route": "grok", "stream": True, "chat_template_kwargs": {"foo": 1}})
check("AEON is forced and reasoning_effort is 'none' even when the caller asked for 'low'",
      b["model"] == S.GEMMA_MODEL and b["reasoning_effort"] == "none", b)
check("enable_thinking is false and the caller's other template switches are kept",
      b["chat_template_kwargs"] == {"foo": 1, "enable_thinking": False}, b)
check("route and stream are not sent on", "route" not in b and "stream" not in b, b)
b2 = S.gemma_body({"messages": [], "max_completion_tokens": 300})
check("a max_completion_tokens budget becomes the answer's max_tokens (no reasoning room)",
      b2.get("max_tokens") == 300 and "max_completion_tokens" not in b2, b2)

check("time for a long answer: 4000 tokens waits well past 180 s", S.gemma_timeout({"max_tokens": 4000}) >= 400)
check("a short verdict still has a floor of 120 s", S.gemma_timeout({"max_tokens": 20}) == 120)
check("never more than 480 s", S.gemma_timeout({"max_tokens": 100000}) == 480)
check("an unreadable max_tokens does not raise", S.gemma_timeout({"max_tokens": "lots"}) >= 120)

class _FakeHTTP:
    def __init__(self, body): self.status, self._b = 200, json.dumps(body).encode()
    def read(self): return self._b
SENT = []
def fake(reply):
    def _open(req, timeout=None):
        SENT.append((req.full_url, json.loads(req.data), timeout))
        return _FakeHTTP(reply)
    return _open
def reply(content, reasoning=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None: msg["reasoning_content"] = reasoning
    return {"id": "c1", "model": S.GEMMA_MODEL, "choices": [{"message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}

S.urllib.request.urlopen = fake(reply("Red"))
SENT.clear()
res = S.gemma_complete({"model": "x", "messages": [{"role": "user", "content": "colour?"}], "max_tokens": 4000})
url, sent, tmo = SENT[0]
check("the request that reaches the MacBook carries reasoning_effort none and enable_thinking false",
      url == S.GEMMA_URL and sent["reasoning_effort"] == "none" and sent["chat_template_kwargs"]["enable_thinking"] is False, sent)
check("and is waited on for the answer it asked for", tmo == S.gemma_timeout({"max_tokens": 4000}), tmo)
check("a direct answer comes back as the text", res["text"] == "Red" and S.GR.usable(res), res)

S.urllib.request.urlopen = fake(reply("Blue", reasoning="some private-looking reasoning text"))
res = S.gemma_complete({"model": "x", "messages": [{"role": "user", "content": "colour?"}], "max_tokens": 40})
check("reasoning the server still returned is stripped: content only", res["text"] == "Blue"
      and "private-looking" not in json.dumps(res), res)
log = open(S.LOG).read() if os.path.exists(S.LOG) else ""
check("and the shim log says thinking-off was not honoured (a count, never the text)",
      "thinking-off not honoured" in log and "private-looking" not in log, log[-200:])

S.urllib.request.urlopen = fake(reply("", reasoning="all of it was thinking", finish="length"))
res = S.gemma_complete({"model": "x", "messages": [{"role": "user", "content": "colour?"}], "max_tokens": 20})
check("a reply that was all reasoning is not usable, so the next lane answers", not S.GR.usable(res) and res["text"] == "", res)

print("--- the journal: time, one retry, a clear error ---")
src = open(os.path.join(REPO, "scripts", "idle-journal.sh"), encoding="utf-8").read()
check("bin/ and scripts/ copies of idle-journal.sh are the same file",
      src == open(os.path.join(REPO, "bin", "idle-journal.sh"), encoding="utf-8").read())
py_start = src.index("python3 << 'PYEOF'")
py = src[src.index("\n", py_start) + 1: src.index("\nPYEOF\n", py_start)]
check("no local call in the entry's python goes out without the retry helper",
      'requests.post("http://127.0.0.1:8599/gemma-aegis/' not in py and py.count('_local_post("http://127.0.0.1:8599/gemma-aegis/') >= 9)
m = re.search(r"\n_LOCAL_TIMEOUT = .*?\n    return _FailedReply\(why\)\n", py, re.S)
check("the helper is found", m is not None)

class _Timeout(Exception): pass
class _Conn(Exception): pass
class _Exc: Timeout = _Timeout; ConnectionError = _Conn
class FakeRequests:
    exceptions = _Exc
    def __init__(self, outcomes): self.outcomes, self.calls = list(outcomes), []
    def post(self, url, *a, **kw):
        self.calls.append(kw.get("timeout")); o = self.outcomes.pop(0)
        if isinstance(o, Exception): raise o
        return o
def helper(outcomes):
    fr = FakeRequests(outcomes); ns = {"requests": fr}
    exec(m.group(0), ns); return ns, fr

ns, fr = helper([_Timeout(), _Timeout()])
err = io.StringIO()
with contextlib.redirect_stderr(err):
    r = ns["_local_post"]("http://127.0.0.1:8599/gemma-aegis/v1/chat/completions", json={}, timeout=180)
check("a timed-out call is tried exactly twice, each with the long timeout", fr.calls == [720, 720], fr.calls)
check("then a stand-in reply that reads as an error (so nothing is invented)", isinstance(r, ns["_FailedReply"])
      and "error" in r.json() and r.why == "_Timeout", getattr(r, "__dict__", r))
check("and an ERROR line says the step was skipped", "ERROR: local call failed twice" in err.getvalue(), err.getvalue())

ns, fr = helper([_Conn(), "OK-REPLY"])
with contextlib.redirect_stderr(io.StringIO()):
    r = ns["_local_post"]("u", json={}, timeout=900)
check("one retry recovers a dropped connection, and a longer timeout asked for is kept",
      r == "OK-REPLY" and fr.calls == [900, 900], fr.calls)

ns, fr = helper(["FIRST"])
r = ns["_local_post"]("u", json={})
check("a call that answers is sent once", r == "FIRST" and fr.calls == [720])

a2 = py[py.index("audit2_r = _local_post("):]
check("audit-2 failing keeps the synthesis with an ERROR, not a false CLEAN",
      a2.index("isinstance(audit2_r, _FailedReply)") < a2.index("audit-2: CLEAN"))
check("an empty audit leaves no empty 'leave these details out' block",
      'audit_result.strip().upper() in ("CLEAN", "")' in py)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
