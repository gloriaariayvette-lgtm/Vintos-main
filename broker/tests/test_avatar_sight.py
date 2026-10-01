#!/usr/bin/env python3
"""A picture she sends goes to whichever brain is toggled, in her message (Gloria, 2026-10-01: "I wanted the
correlating model to receive it in the same message"). Sonnet used to put every photo and video into words first,
whatever the toggle. Gemma now writes a note of what it showed afterwards, for his memory only.

Scratch HOME; every provider is a stub that records what it was sent; every socket is refused."""
import asyncio, ast, json, os, re, socket, sys, tempfile, types, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="avatar-sight-")
os.environ["HOME"] = HOME
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["OPENAI_API_KEY"] = "test-openai"
os.makedirs(os.path.join(HOME, ".vintos", "logs"), exist_ok=True)
NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

# --- providers, stubbed: each records the body it was sent ---
SENT = []
REPLIES = {}
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None, headers=None, **k):
        SENT.append((url, json))
        if "anthropic" in url:
            return _Resp({"content": [{"type": "text", "text": "Claude sees a black drum."}], "model": json["model"],
                          "stop_reason": "end_turn", "usage": {}})
        reply = REPLIES.get(json.get("model"), "I see a fish.")
        if callable(reply):
            reply = reply(json)
        if reply is None:
            return _Resp({"error": {"message": "this route cannot take images"}})
        return _Resp({"choices": [{"message": {"content": reply}, "finish_reason": "stop"}], "model": json.get("model")})
sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_Client)

import importlib.util
spec = importlib.util.spec_from_file_location("model_router_sight", os.path.join(REPO, "bin", "model_router.py"))
MR = importlib.util.module_from_spec(spec); spec.loader.exec_module(MR)
MR.httpx = sys.modules["httpx"]
MR._reserve_provider = lambda *a, **k: "r"
MR._release_provider = lambda *a, **k: None
MR._MODE_FILE = os.path.join(HOME, ".vintos", "model-mode.json")
check("the router's toggle is the scratch one", MR._MODE_FILE.startswith(HOME))

PIC = {"type": "image", "media_type": "image/jpeg", "data": "QUJD"}
CONVO = [{"role": "assistant", "content": "Earlier."},
         {"role": "user", "content": [{"type": "text", "text": "Gloria says: look what I caught"}, PIC]}]

# --- each provider gets the picture in its own shape ---
a = MR.for_anthropic(CONVO)[-1]["content"]
check("Claude: an image block with the base64 source",
      a[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}} and a[0]["type"] == "text", a)
c = MR.for_chat(CONVO)[-1]["content"]
check("Grok and Gemma: an image_url with a data url", c[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}, c)
o = MR.for_responses(CONVO)[-1]["content"]
check("Sol: input_text and input_image", o[0]["type"] == "input_text" and o[1] == {"type": "input_image", "image_url": "data:image/jpeg;base64,QUJD"}, o)
check("plain text turns pass through untouched", MR.for_chat(CONVO)[0] == CONVO[0] and MR.for_anthropic([{"role": "user", "content": "hi"}])[0]["content"] == "hi")
tail = MR._cachetail(MR.for_anthropic(CONVO))[-1]["content"]
check("the cache mark goes on her words, beside the picture", tail[0].get("cache_control") and "cache_control" not in tail[1], tail)
check("a picture is not 'long context', and Gemma can take it", MR._needs_provider(
    [{"role": "user", "content": [{"type": "text", "text": "x"}, dict(PIC, data="A" * 500000)]}], {}) == [])

def route(mode):
    json.dump({"mode": mode}, open(MR._MODE_FILE, "w"))
    SENT.clear()
    return asyncio.run(MR.route_reply_result("avatar", "You are Vintos.", CONVO, {"max_tokens": 300},
                                             "http://shim.test/v1/chat/completions", {}, "grok-4.20-0309-non-reasoning"))

for mode, model in (("claude", "claude-opus-4-8"), ("opus55", "claude-opus-5-5"), ("fable", "claude-fable-5-1")):
    res = route(mode)
    body = SENT[0][1] if SENT else {}
    blocks = body.get("messages", [{}])[-1].get("content", []) if body else []
    check("toggle %s: %s itself receives the picture in her message, and answers" % (mode, model),
          len(SENT) == 1 and body.get("model") == model and any(b.get("type") == "image" for b in blocks)
          and res["text"] == "Claude sees a black drum.", (len(SENT), body.get("model"), blocks))

res = route("grok")
body = SENT[0][1] if SENT else {}
check("toggle grok: Grok itself receives the picture in her message",
      len(SENT) == 1 and any(p.get("type") == "image_url" for p in body["messages"][-1]["content"]) and res["text"] == "I see a fish.", SENT)

res = route("local")
body = SENT[0][1] if SENT else {}
check("toggle local: Gemma itself receives the picture in her message",
      body.get("model") == MR.GEMMA_MODEL and any(p.get("type") == "image_url" for p in body["messages"][-1]["content"])
      and res["text"] == "I see a fish.", body)

OPENAI = []
class _OResp:
    def __init__(self, d): self._d = d
    def read(self): return json.dumps(self._d).encode()
def _fake_urlopen(rq, timeout=0):
    OPENAI.append(json.loads(rq.data))
    return _OResp({"output": [{"type": "message", "content": [{"type": "output_text", "text": "Sol sees the barbels."}]}]})
_real_urlopen = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
try:
    res = route("sol")
finally:
    urllib.request.urlopen = _real_urlopen
check("toggle sol: Sol itself receives the picture in her message",
      OPENAI and any(p.get("type") == "input_image" for p in OPENAI[-1]["input"][-1]["content"]) and res["text"] == "Sol sees the barbels.",
      OPENAI[-1]["input"][-1] if OPENAI else None)
check("and no other model looked at it first", not any("anthropic" in u for u, _ in SENT), SENT)

# a Grok route that cannot carry the picture gets it in Gemma's words, once
REPLIES["grok-4.20-0309-non-reasoning"] = lambda body: (None if any(isinstance(m.get("content"), list) for m in body["messages"])
                                                        else "Grok read Gemma's words.")
REPLIES[MR.GEMMA_MODEL] = "A black drum on concrete, barbels under its chin."
res = route("grok")
grok_calls = [b for u, b in SENT if b.get("model", "").startswith("grok")]
check("a Grok route that cannot carry the picture gets it once more, in Gemma's words",
      res["text"] == "Grok read Gemma's words." and len(grok_calls) == 2
      and "barbels under its chin" in grok_calls[1]["messages"][-1]["content"]
      and "look what I caught" in grok_calls[1]["messages"][-1]["content"], [b["messages"][-1] for b in grok_calls])
REPLIES.clear()

# --- the server: no eyes in between; the note kept for his memory is Gemma's ---
src = open(os.path.join(REPO, "bin", "server.py")).read()
photo = src[src.index('@app.post("/api/avatar/photo")'):]
photo = photo[:photo.index("_CLIP_EYES = ")]
check("the avatar photo door no longer describes the photo before he sees it",
      "_describe_photo(" not in photo and '"image": photo_b64, "image_type": content_type' in photo)
turn = src[src.index('@app.post("/api/avatar/chat")'):]
turn = turn[:turn.index('\n@app.', 10)]
check("the avatar turn puts the picture in her message, for the toggled brain",
      '[{"type": "text", "text": _umsg}] + _attached' in turn and '"type": "image", "media_type": msg.image_type' in turn)
check("Gemma writes the note alongside, never Sonnet",
      "_describe_photo(msg.image, msg.image_type or \"image/jpeg\", local_only=True)" in turn
      and "local_only=True))" in turn and "_ant = None if local_only else _anthropic_key()" in src)
check("the camera's picture of him also goes in her message, not through eyes", "_cam_desc" not in turn
      and "is here in this message.]" in turn)
check("his memory keeps the note, in the ledger and his chat history", "ledger_media=_sent_media(msg, _note)" in turn
      and "_with_note(msg.message, _note)" in turn and '{"image_description": _note}' in turn)

tree = ast.parse(src)
want = {"_PHOTO_HERE", "_HERE_RX", "_seen_note", "_with_note", "_sent_media"}
nodes = [n for n in tree.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in want for t in n.targets))
         or (isinstance(n, ast.FunctionDef) and n.name in want)]
ns = {"re": re}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "server-sight", "exec"), ns)
said = ns["_PHOTO_HERE"] + "\n\n[Gloria's message with the photo:] look"
kept = ns["_with_note"](said, "A black drum on concrete.")
check("the line that said it is here becomes what it showed", "[What it showed (a note kept afterwards):] A black drum on concrete." in kept
      and "here in this message" not in kept and "look" in kept, kept)
check("with no note, it says so rather than claiming he can still see it",
      "no note of what it showed" in ns["_with_note"](said, "[I could not see the image clearly: x]"))
m = types.SimpleNamespace(input_kind="photo", message=said)
check("the ledger's 'she sent' is the note, without her caption",
      ns["_sent_media"](m, "A black drum.") == "[What it showed (a note kept afterwards):] A black drum.", ns["_sent_media"](m, "A black drum."))

sys.path.insert(0, os.path.join(REPO, "scripts"))
import video_share as V
t = V.compose({"duration": 9, "has_audio": True, "speech": "the kettle is on"}, None, "look", frame_times=[1.5, 4.5])
check("a video tells him its frames are in his message, at their times, with what was heard",
      "[Its frames are here in this message, in order, taken at 1.5, 4.5 seconds: watch them yourself.]" in t
      and "the kettle is on" in t and "What your eyes saw" not in t, t)
check("the video's note replaces that line in his memory too",
      "[What it showed (a note kept afterwards):] A kitchen at dusk." in ns["_with_note"](t, "A kitchen at dusk."))

check("nothing reached the network", NET == [])
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
