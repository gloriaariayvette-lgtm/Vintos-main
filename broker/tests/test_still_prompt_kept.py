#!/usr/bin/env python3
"""Every still asked of Atlas is kept with its whole prompt and Atlas's answer (2026-10-08: a together still was
refused PROHIBITED_CONTENT and its prompt could be read only on an Atlas page that would not scroll). Atlas is a stub
that refuses the way it did; scratch HOME; nothing reaches the network."""
import importlib.util, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="still-kept-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["ATLASCLOUD_API_KEY"] = "test-key-not-real"
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
class Resp:
    def __init__(self, code, body): self.status_code, self._b, self.text = code, body, json.dumps(body)
    def json(self): return self._b
SENT = []
def post(url, **k): SENT.append(url); return Resp(200, {"data": {"id": "04b983bbf8be4e2197b3972204b6748f"}})
def get(url, **k):
    return Resp(200, {"data": {"id": "04b983bbf8be4e2197b3972204b6748f", "status": "failed",
                               "error": "no parts found for the request: PROHIBITED_CONTENT"}})
sys.modules["requests"] = types.SimpleNamespace(post=post, get=get)
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))
spec = importlib.util.spec_from_file_location("send_video", os.path.join(REPO, "bin", "vintos-send-video.py"))
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
V.time = types.SimpleNamespace(sleep=lambda s: None)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the still log is a scratch one", V.STILLS_LOG.startswith(HOME), V.STILLS_LOG)
PROMPT = "A photo of two REAL, specific people together. ... They are in that place: on the patio at dusk."
got = V._atlas_image({"model": "google/nano-banana-2/reference-to-image", "prompt": PROMPT, "images": ["a", "b", "c"]})
rows = [json.loads(l) for l in open(V.STILLS_LOG)] if os.path.exists(V.STILLS_LOG) else []
check("a refused still returns nothing", got is None)
check("and is kept: the whole prompt, the model, the prediction id, Atlas's refusal, the image count (not the images)",
      rows and rows[-1]["prompt"] == PROMPT and rows[-1]["outcome"] == "failed" and "PROHIBITED_CONTENT" in rows[-1]["detail"]
      and rows[-1]["prediction_id"] == "04b983bbf8be4e2197b3972204b6748f" and rows[-1]["images"] == 3
      and "test-key-not-real" not in open(V.STILLS_LOG).read(), rows)
import inspect
compose = inspect.getsource(V.compose_us) + inspect.getsource(V.make_scene_still)
check("the image prompts no longer shout that they are REAL people or a REAL place (Gloria, 2026-10-08)",
      "REAL" not in compose.replace('No "two REAL, specific people"', "")
      and "two REAL" not in open(os.path.join(REPO, "bin", "gen_hero_stills.py")).read(), compose[:200])
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
