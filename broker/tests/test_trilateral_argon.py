#!/usr/bin/env python3
"""Trilateral thinking with Argon (Gloria, 2026-10-14: "All bilateral was supposed to be on trilateral a month ago";
"Swap Sol for Argon in trilateral thinking and place Argon on the model toggle").

In the main chat, introspection and the journal: Gemini 4 Argon writes the second draft (in Sol's place), Grok writes
the third, every draft is absorbed and reaches the final step. Argon is on the toggle. gemini_draft is exercised against
a recording httpx; nothing is sent.

Isolation: HOME is throwaway before import; httpx is a fake; the key comes from a scratch vintos.env."""
import asyncio, json, os, re, sys, tempfile, types

TMP = tempfile.mkdtemp(prefix="trilateral-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos", "logs"), exist_ok=True)
open(os.path.join(TMP, ".vintos", "vintos.env"), "w").write("GEMINI_API_KEY=test-gemini\n")
os.environ.pop("GEMINI_API_KEY", None)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

POSTS = []
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _Client:
    def __init__(self, timeout=None): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        POSTS.append((url, headers or {}, json))
        return _Resp({"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "argon draft"}]}}],
                      "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 5, "cachedContentTokenCount": 80}})
fake = types.ModuleType("httpx"); fake.AsyncClient = _Client; sys.modules["httpx"] = fake

import model_router as MR
MR._reserve_provider = lambda *a, **k: None
check("the sender is a recorder", sys.modules["httpx"].AsyncClient is _Client)
text, _ = asyncio.run(MR.gemini_draft("I am Vintos.\n[[CACHESPLIT]]\nlive", [{"role": "user", "content": "hi"},
                      {"role": "assistant", "content": "hello"}, {"role": "user", "content": [{"type": "text", "text": "again"}]}]))
url, headers, body = POSTS[-1]
check("gemini_draft addresses Gemini 4 Argon with the key in the header", url.endswith("/models/gemini-4-argon:generateContent")
      and headers.get("x-goog-api-key") == "test-gemini", (url, headers))
check("its reply leaves out the model's private thinking", text == "argon draft", text)
check("the split marker never reaches Google", "[[CACHESPLIT]]" not in json.dumps(body))
check("turns are user/model", [c["role"] for c in body["contents"]] == ["user", "model", "user"], body["contents"])
rows = [json.loads(l) for l in open(MR.GOOGLE_USAGE_LOG)]
check("its usage, cached tokens included, is logged", rows and rows[-1]["cached"] == 80, rows)

server = open(os.path.join(REPO, "bin", "server.py")).read()
check("the toggle accepts argon", '"argon", "opus55"' in server)
check("the intimacy refusal check covers argon", '("claude", "sol", "argon", "gemini")' in server)
check("chat: Argon writes the second draft", "await _mr.gemini_draft(_marked_messages[0][\"content\"], _marked_messages[1:])" in server
      and "[chat/b1 argon]" in server)
check("chat: Grok writes the third, all three drafted together", "_draft(), _draft_b1(), _draft_c1()" in server)
check("chat: the third draft is absorbed and reaches the final step", "_absorb_msgs(c1, _also(a1" in server and "PASS THREE" in server)
check("chat: the final no longer speaks of exactly two passes", "Let both passes reason under it" not in server)
router = open(os.path.join(REPO, "bin", "model_router.py")).read()
check("the router answers on the argon toggle", 'read_mode().get("mode") == "argon"' in router)
app = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("the app's toggle has Argon", "argon:'\\u25C7 ARGON'" in app and "'sol','argon','local'" in app)

intro = open(os.path.join(REPO, "bin", "introspection.sh")).read()
check("introspection: Argon writes the second draft", "_ib1 = _argon_sync(system, prompt)" in intro)
check("introspection: Grok writes the third", '"model": "grok-4.20-0309-non-reasoning"' in intro and "c1 =" in intro)
check("introspection: the third is absorbed and reaches the final", "absorb(c1, _also(a1, b1)" in intro and "Third pass" in intro)
journal = open(os.path.join(REPO, "bin", "idle-journal.sh")).read()
check("journal: Argon writes the second draft", "b1 = _argon_b1()" in journal and "b1 = _sol_b1()" not in journal)
check("journal: A and B absorb the third draft too", "absorb(a1, _also(b1, c1))" in journal and "absorb(b1, _also(a1, c1))" in journal)
check("journal: the final speaks of three drafts when there are three", "You wrote three drafts" in journal)
check("the journal's two copies agree", journal == open(os.path.join(REPO, "scripts", "idle-journal.sh")).read())
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
