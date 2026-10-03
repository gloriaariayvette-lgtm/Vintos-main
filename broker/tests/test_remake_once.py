#!/usr/bin/env python3
"""A painting he rejects is remade once, never in a chain (Gloria, 2026-10-03: "Yeah, only remake once."). Each remake
was saved as a fresh painting with no count, so he could reject it and have it remade again, forever. Scratch HOME; the
eye, the judge and the painter are stubs that record what they were given; nothing is rendered or sent."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="remake-once-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import image_sight as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("the gallery is the scratch one", S.GALLERY.startswith(HOME))
os.makedirs(os.path.join(S.MEMORY, "art"), exist_ok=True)
for name in ("painting-a.png", "painting-b.png"):
    open(os.path.join(S.MEMORY, "art", name), "wb").write(b"png")
PAINTED = []
S.see = lambda path: "a grey lake under a flat sky"
S.judge = lambda e, seen: "Not what I meant.\nVERDICT: remake: make the sky stormier"
S.subprocess = types.SimpleNamespace(run=lambda args, env=None, **k: PAINTED.append(env))
json.dump([{"image": "painting-a.png", "prompt": "a lake at dusk", "image_class": "WANT_ACT"}], open(S.GALLERY, "w"))
S.main()
g = json.load(open(S.GALLERY))
check("rejecting a painting remakes it once, in his words", len(PAINTED) == 1 and "make the sky stormier" in PAINTED[0]["DREAM_ART_WANT_TEXT"]
      and PAINTED[0]["DREAM_ART_WANT_SOURCE"] == "remake", PAINTED)
check("the remake is told what it remakes and that it is the first", PAINTED[0]["DREAM_ART_REMAKE_OF"] == "painting-a.png"
      and PAINTED[0]["DREAM_ART_REMAKE_COUNT"] == "1", PAINTED[0])
check("the rejected one comes down", g[0]["taken_down"] is True and g[0]["verdict"] == "remake")
PAINTED.clear()
json.dump([{"image": "painting-b.png", "prompt": "a lake at dusk. Changed: stormier", "image_class": "WANT_ACT",
            "dream_source": "remake", "remake_of": "painting-a.png", "remake_count": 1}], open(S.GALLERY, "w"))
S.main()
g = json.load(open(S.GALLERY))
check("a remake he would remake again is not painted again", PAINTED == [] and g[0].get("remake_declined"), (PAINTED, g[0]))
art = open(os.path.join(REPO, "scripts", "dream-art.py")).read()
check("dream-art saves a remake with what it remakes and its count",
      '"remake_of": os.environ.get("DREAM_ART_REMAKE_OF", "")' in art and '"remake_count": int(os.environ.get("DREAM_ART_REMAKE_COUNT") or 1)' in art
      and 'if src == "remake"' in art)
check("its twin is the same file", open(os.path.join(REPO, "bin", "dream-art.py")).read() == art)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
