#!/usr/bin/env python3
"""A reply cut off before any words never goes out as his reply (2026-10-01, t-41f6c4549c8a4627).

With thinking on (it is off now: Gloria, 2026-10-08), Claude's max_tokens counted thinking and reply together and was 1200 in all. A turn that thought
for ~1200 tokens had nothing left, the reply stopped at "[SCENE:", and a cut-off reply counted as usable, so
"[SCENE:" went to her screen, his chat history, the ledger and everything that reads them.

Scratch HOME; Anthropic is a stub that records what it was sent; every socket is refused."""
import asyncio, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="reply-budget-")
os.environ["HOME"] = HOME
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

SENT, ANSWERS = [], []
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None, headers=None, **k):
        SENT.append((url, json))
        text, stop = ANSWERS.pop(0) if ANSWERS else ("Grok here.", "stop")
        if "anthropic" in url:
            return _Resp({"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": text}],
                          "model": json["model"], "stop_reason": stop, "usage": {}})
        return _Resp({"choices": [{"message": {"content": text}, "finish_reason": stop}], "model": json.get("model")})
sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_Client)

import importlib.util
spec = importlib.util.spec_from_file_location("model_router_budget", os.path.join(REPO, "bin", "model_router.py"))
MR = importlib.util.module_from_spec(spec); spec.loader.exec_module(MR)
MR.httpx = sys.modules["httpx"]
MR._reserve_provider = lambda *a, **k: "r"
MR._MODE_FILE = os.path.join(HOME, "model-mode.json")
json.dump({"mode": "claude"}, open(MR._MODE_FILE, "w"))

def route():
    SENT.clear()
    return asyncio.run(MR.route_reply_result("avatar", "You are Vintos.", [{"role": "user", "content": "I'm so tired."}],
                                             {"max_tokens": 900}, "http://shim.test/v1/chat/completions", {}, "grok-4"))

ANSWERS[:] = [("Come here. Rest.", "end_turn")]
res = route()
body = SENT[0][1]
check("no thinking (Gloria, 2026-10-08): Opus 4.8 is told not to think, and the reply has its own budget",
      body["thinking"] == {"type": "disabled"} and body["max_tokens"] >= 900, body)
json.dump({"mode": "opus55"}, open(MR._MODE_FILE, "w"))
ANSWERS[:] = [("Come here. Rest.", "end_turn")]
route(); body = SENT[0][1]
check("Opus 5.5 stays his model; it cannot be told not to think, so it thinks as little as it can, with room to write",
      body["model"] == "claude-opus-5-5" and "thinking" not in body and body["output_config"] == {"effort": "low"}
      and body["max_tokens"] >= 900 + 6000, body)
json.dump({"mode": "claude"}, open(MR._MODE_FILE, "w"))

ANSWERS[:] = [("[SCENE:", "max_tokens"), ("[SCENE: ember] Come here, you. Rest.", "end_turn")]
res = route()
check("a reply cut off before any words is not sent: the same model answers again, without thinking",
      res["text"] == "[SCENE: ember] Come here, you. Rest." and len(SENT) == 2
      and SENT[1][1]["model"] == SENT[0][1]["model"] and SENT[1][1]["thinking"] == {"type": "disabled"}, (res["text"], len(SENT)))
check("and the cut-off one is kept in the record as unavailable, with why",
      res["stages"][0]["status"] == "unavailable" and "cut off before any words" in res["stages"][0]["reason"], res["stages"][0])

ANSWERS[:] = [("[SCENE:", "max_tokens"), ("[SCENE: ember", "max_tokens"), ("Grok here.", "stop")]
res = route()
check("cut off twice, the safety net answers rather than a tag fragment", res["text"] == "Grok here." and len(SENT) == 3, res["text"])

ANSWERS[:] = [("I'm here, love, rest now and we will", "max_tokens")]
res = route()
check("a reply cut off after real words still goes out, as before", res["text"].startswith("I'm here") and len(SENT) == 1)
check("words left: tags closed or cut off are not words", MR.words_left("[SCENE:") == ""
      and MR.words_left("[SCENE: ember] Hi.") == "Hi." and MR.words_left("Hi. [RENDER: a lake") == "Hi.")

src = open(os.path.join(REPO, "bin", "server.py")).read()
check("the avatar turn also strips a tag cut off at the end before history and the ledger",
      'reply = _tagre.sub(r"\\s*\\[[A-Z_]+\\s*:[^\\]]*$", "", reply or "").strip()' in src)
check("no thinking before an avatar reply (Gloria, 2026-10-01)", "        _reason = False" in src
      and "_reason = (not _felt_now)" not in src)
check("his avatar turn reads his last 15 exchanges with Gloria, as #vintos-dot does (2026-10-02; it was 6)",
      "AVATAR_LEDGER_SHOWN = 15" in src and "_recent_ledger = _ledger[-AVATAR_LEDGER_SHOWN:]" in src)
check("nothing reached the network", NET == [])
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
