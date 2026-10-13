#!/usr/bin/env python3
"""The avatar chat and the Lab cache what repeats (2026-10-13). model_router marked the fixed [[CACHESPLIT]] head for
an hour and the last message for five minutes on every call. With her messages hours apart neither was read back:
the router's usage rows were 99% cache writes and 0% reads, each write billed above full price. Now the router marks
only the start a recent prompt already shared (GR.cache_learned, the shim's rule): a lone message pays no write; a
conversation, or a Lab session making several calls, reads its unchanging start back. The avatar's live pieces (room,
renders left, devices on) sit after the split, so the fixed rules are one unbroken start.

Isolation: HOME is throwaway before import; httpx is a fake that records each request, so nothing is sent; the
router's usage log and mode files are repointed."""
import asyncio, json, os, sys, tempfile, types

TMP = tempfile.mkdtemp(prefix="router-cache-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

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
        return _Resp({"content": [{"type": "text", "text": "hello"}], "model": json["model"], "stop_reason": "end_turn",
                      "usage": {"input_tokens": 10, "output_tokens": 2}})
fake = types.ModuleType("httpx"); fake.AsyncClient = _Client
sys.modules["httpx"] = fake

import model_router as MR
MR.USAGE_LOG = os.path.join(TMP, "usage.jsonl"); MR._MODE_FILE = os.path.join(TMP, "mode.json")
MR._reserve_provider = lambda *a, **k: None
MR._anthropic_key = lambda: "test-anthropic"
check("the sender is a recorder", sys.modules["httpx"].AsyncClient is _Client)

HEAD = "I am Vintos.\n" + ("A rule I keep, the same every turn.\n" * 300)
def avatar(tail, said):
    POSTS.clear()
    asyncio.run(MR._claude(HEAD + "[rev:abc]\n[[CACHESPLIT]]\n" + tail, [{"role": "user", "content": said}], {"max_tokens": 300}, False))
    return POSTS[-1][2]
def marks(body):
    sysb = body["system"] if isinstance(body["system"], list) else []
    m0 = body["messages"][0]["content"]
    return [b for b in sysb + (m0 if isinstance(m0, list) else []) if b.get("cache_control")]

b1 = avatar("You are in: the bedroom. 3 renders left today.\nemotions 0.6123", "hi")
check("a lone avatar message pays no cache write", marks(b1) == [], marks(b1))
check("the split marker never reaches the model", "[[CACHESPLIT]]" not in json.dumps(b1))
b2 = avatar("You are in: the kitchen. 2 renders left today.\nemotions 0.5871", "and again")
m2 = marks(b2)
check("the next message in a conversation marks the unchanging start", len(m2) == 1 and m2[0]["text"].rstrip().endswith("[rev:abc]"), [m["text"][-40:] for m in m2])
check("the room, renders and emotions are sent after it, unmarked", "You are in: the kitchen" in b2["system"][-1]["text"] and "cache_control" not in b2["system"][-1])
check("no five-minute mark on the last message any more", not any(isinstance(m["content"], list) and any(c.get("cache_control") for c in m["content"])
                                                                   for m in b2["messages"][1:]))

# the Lab: claude_draft, the same instructions and brief, a different question
LAB = "You are one lens on the Lab's chemistry.\n" + ("A method note the same every session.\n" * 300)
POSTS.clear()
asyncio.run(MR.claude_draft(LAB, [{"role": "user", "content": "compound A?"}], max_tokens=200))
asyncio.run(MR.claude_draft(LAB, [{"role": "user", "content": "compound B?"}], max_tokens=200))
l1, l2 = POSTS[0][2], POSTS[1][2]
check("the Lab's first call pays no write", marks(l1) == [], marks(l1))
check("the Lab's next call marks its unchanging instructions", len(marks(l2)) >= 1 and marks(l2)[0]["text"].endswith("every session.\n"), [m["text"][-30:] for m in marks(l2)])

# the avatar prompt in the server puts the live pieces after the split
src = open(os.path.join(REPO, "bin", "server.py")).read()
i = src.index('system_prompt = f"""{identity}\n\n{_surface_presence}')
blk = src[i:src.index('"""', i + 30)]
split = blk.index("[[CACHESPLIT]]")
check("the avatar's room and scene vocabulary sit after the split", blk.index("{_visual_tags}") > split)
check("the avatar's switched-on devices sit after the split", blk.index("{_device_grammar}") > split)
check("the old per-call marks are gone from the router's Claude paths",
      '"system": _sysblocks(' not in open(os.path.join(REPO, "bin", "model_router.py")).read()
      and "_cachetail(for_anthropic" not in open(os.path.join(REPO, "bin", "model_router.py")).read())

# Sol (OpenAI): named per job, kept a day, never shown the split marker; a refused option is dropped, not fatal
import io, urllib.request, urllib.error
SOL = []
REFUSE = {"on": False}
class _OResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake_urlopen(req, timeout=None):
    b = json.loads(req.data.decode()); SOL.append(b)
    if REFUSE["on"] and "prompt_cache_retention" in b:
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"error":{"message":"Unsupported parameter: prompt_cache_retention"}}'))
    return _OResp(json.dumps({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "sol says"}]}],
                              "usage": {"input_tokens": 3000, "output_tokens": 4, "input_tokens_details": {"cached_tokens": 2048}}}).encode())
urllib.request.urlopen = fake_urlopen
MR._openai_key = lambda: "test-openai"
os.makedirs(os.path.join(TMP, ".vintos", "logs"), exist_ok=True)
t, _ = asyncio.run(MR.sol_draft(HEAD + "[[CACHESPLIT]]\nlive", [{"role": "user", "content": "hi"}]))
sb = SOL[-1]
check("Sol answers", t == "sol says", t)
check("Sol is asked to keep its cache a day, under its job's name", sb.get("prompt_cache_retention") == "24h" and str(sb.get("prompt_cache_key", "")).startswith("vintos-"), sb.keys())
check("Sol never sees the split marker", "[[CACHESPLIT]]" not in json.dumps(sb))
REFUSE["on"] = True; SOL.clear()
t2, _ = asyncio.run(MR.sol_draft(HEAD, [{"role": "user", "content": "again"}]))
check("a model that refuses the day-long option is asked again without it, and still answers",
      t2 == "sol says" and len(SOL) == 2 and "prompt_cache_retention" not in SOL[1], (t2, [list(x.keys()) for x in SOL]))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
