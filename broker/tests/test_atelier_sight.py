#!/usr/bin/env python3
"""He sees his own paintings in the Atelier (2026-10-02). A painting he made came back to him as its byte count,
right after making it and on every return to it; now it is in front of him, in the message itself.

Scratch HOME; the model, the media table and the broker are stubs that record what they were given; every socket
is refused."""
import asyncio, base64, importlib.util, os, socket, sys, tempfile, types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-sight-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("atelier_visit_sight", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("his choices are written in the scratch workspace", AV.CHOICES.startswith(HOME), AV.CHOICES)
os.makedirs(os.path.dirname(AV.CHOICES), exist_ok=True)

# right after he paints: the painting is in the message he reads it in
ASKED = []
def ask(system, user, max_tokens=2000, temp=0.7, images=None):
    ASKED.append((system + "\n" + user, images)); return "<media_reading>the blue is too loud</media_reading><handoff>h</handoff>"
post = lambda url, json=None, timeout=None, **k: types.SimpleNamespace(json=lambda: {"ok": True, "file": "20261002_x_image.png"})
media = types.SimpleNamespace(render_image=lambda p: {"ok": True, "kind": "image", "ext": "png", "mime_type": "image/png",
                                                      "bytes": b"\x89PNGpainting", "size": 12})
with mock.patch.object(AV, "ask", side_effect=ask), mock.patch.object(AV, "_media_module", return_value=media), \
     mock.patch.object(AV.requests, "post", side_effect=post):
    out = AV.media_loop("p", "CTX", '<image prompt="the held pause">III</image>', "cap", creation={})
user, images = ASKED[-1]
check("the painting he just made is in front of him, in the message itself",
      images == [("image/png", base64.b64encode(b"\x89PNGpainting").decode())], images)
check("and he is told to look at it", "your painting is in front of you in this message" in user, user[-300:])
check("what he saw is read back", "the blue is too loud" in out)

# a song is not shown as a picture
ASKED.clear()
media.render_music = lambda *a: {"ok": True, "kind": "music", "ext": "wav", "mime_type": "audio/wav", "bytes": b"RIFFx", "size": 5}
with mock.patch.object(AV, "ask", side_effect=ask), mock.patch.object(AV, "_media_module", return_value=media), \
     mock.patch.object(AV.requests, "post", side_effect=post), mock.patch.object(AV, "listening", return_value=""):
    AV.media_loop("p", "CTX", '<music title="t" style="s">x</music>', "cap", creation={})
check("a song is not handed to him as a picture", ASKED[-1][1] is None)

# when he comes back to it, his last painting is in the visit's first message
png = "data:image/png;base64," + base64.b64encode(b"\x89PNGlast").decode()
resp = {"content": png, "encoding": "base64", "mime_type": "image/png", "size": 9}
AV.LAST_SEEN[:] = []
with mock.patch.object(AV.requests, "post", return_value=types.SimpleNamespace(json=lambda: resp)):
    last = AV._last_piece("p", {"artifacts": {"20261002_x_image.png": {}}}, "cap")
check("returning, his last painting is set before him", AV.LAST_SEEN == [("image/png", base64.b64encode(b"\x89PNGlast").decode())], AV.LAST_SEEN)
check("and the visit says where it is", "It is in front of you in this visit's first message" in last, last)
src = open(os.path.join(REPO, "scripts", "atelier-visit.py")).read()
visit = src[src.index("def visit(pid"):]
check("the visit's first message carries it, and every visit starts with none",
      "images=list(LAST_SEEN) or None)" in visit and visit.index("LAST_SEEN[:] = []") < visit.index("_last_piece(pid, pk, cap)"))

# his voice hands the picture to the model in the provider's own shape
SEEN = []
async def claude_draft(system, convo, max_tokens=1500, model=None):
    SEEN.append(convo); return "I see it.", {}
sys.modules["model_router"] = types.SimpleNamespace(current_claude_model=lambda: "claude-opus-4-8", claude_draft=claude_draft)
import atelier_voice
said = atelier_voice.ask("S", "look", images=[("image/png", "QUJD")])
check("his voice puts the picture beside his words", said == "I see it." and SEEN[-1][0]["content"] ==
      [{"type": "text", "text": "look"}, {"type": "image", "media_type": "image/png", "data": "QUJD"}], SEEN[-1])
atelier_voice.ask("S", "plain")
check("without a picture his words go as plain text, as before", SEEN[-1][0]["content"] == "plain")
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
