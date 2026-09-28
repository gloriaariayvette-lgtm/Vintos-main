#!/usr/bin/env python3
"""His live scenes come out in the shape of his filmed rooms, so they fill her screen the way the rooms do
(2026-09-28: a 16:9 render sat small at the top of a portrait screen). Scratch HOME; the Mac's composer is
a stub that records what it was asked for; real ffmpeg (skipped only if absent) fits real clips."""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-live-shape-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network; urllib.request.urlretrieve = no_network
sys.path.insert(0, os.path.join(REPO, "bin"))
import avatar_stage as A
spec = importlib.util.spec_from_file_location("mac_stage_service", os.path.join(REPO, "bin", "mac_stage_service.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))
check("both stages write only under the scratch HOME", A.CLIPS.startswith(HOME) and M.STAGE.startswith(HOME), (A.CLIPS, M.STAGE))
check("the network is a stub", urllib.request.urlopen is no_network and sys.modules["requests"].post is no_network)

check("a portrait room shape maps to the composer's nearest portrait ratio",
      M.nearest_ratio(720 / 900.0) == "4:5" and M.nearest_ratio(9 / 16.0) == "9:16" and M.nearest_ratio(None) is None)
asked = []
def fake_fal(model, body, timeout=600):
    asked.append((model, dict(body))); raise RuntimeError("stub: nothing is composed in a test")
M._fal = fake_fal
M.live_render("night waterfront", images=["data:image/jpeg;base64,AAAA"], aspect=0.8)
check("the Mac composes his scene in the rooms' shape", asked and asked[0][1].get("aspect_ratio") == "4:5", asked)
asked.clear(); M.live_render("night waterfront", images=["data:image/jpeg;base64,AAAA"])
check("without a shape from Aegis it composes as before", asked and "aspect_ratio" not in asked[0][1], asked)
src = open(os.path.join(REPO, "bin", "avatar_stage.py")).read()
sent = []
class _Resp:
    status_code = 500; text = "stub"; content = b""
A._mac_url = lambda: "http://mac.test"
A._vsv = lambda: types.SimpleNamespace(HER_HAIR_LINE="The woman's hair is a rich dark red, and stays dark red throughout.")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=lambda url, json=None, **k: sent.append(json) or _Resp())
A._slot_update("t-us", status="rendering", started=1.0)
A._live_worker("the two of us at the lakeshore railing", "together", slot="t-us")
A._slot_update("t-me", status="rendering", started=1.0)
A._live_worker("me at the lakeshore railing", "self", slot="t-me")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
check("a scene with her in it says her hair is red, in the still and the motion",
      len(sent) == 2 and "hair is a rich dark red" in sent[0]["prompt"] and "hair is a rich dark red" in sent[0]["motion"], sent[:1])
check("a scene of him alone is not told about her hair", len(sent) == 2 and "hair" not in sent[1]["prompt"], sent[1:])
check("a clip is always revalidated, so a new live scene is never shown as a cached old one",
      'headers={"Cache-Control": "no-cache"}' in open(os.path.join(REPO, "bin", "avatar_stage.py")).read())
check("Aegis sends the rooms' shape with every live render", '"aspect": _aspect}' in src and "_aspect = room_aspect()" in src)

if shutil.which("ffmpeg") and shutil.which("ffprobe"):
    os.makedirs(A.CLIPS, exist_ok=True)
    def clip(path, w, h):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=%dx%d:rate=10" % (w, h),
                        "-t", "1", "-pix_fmt", "yuv420p", path], check=True)
    clip(os.path.join(A.CLIPS, "bed.mp4"), 720, 900)
    A.save_rooms({"default": "bedroom", "rooms": {"bedroom": {"photo": "", "pose": "on the bed", "clips": ["bed.mp4"]},
                                                   "live": {"photo": "", "pose": "x", "clips": ["live.mp4"]}}})
    check("the rooms' shape is read from a filmed room", abs(A.room_aspect() - 0.8) < 0.01, A.room_aspect())
    live = os.path.join(A.CLIPS, "live.mp4"); clip(live, 1280, 720)
    check("a 16:9 render is fitted to the rooms' shape", A.fit_to_rooms(live) and
          abs(A._clip_size(live)[0] / float(A._clip_size(live)[1]) - 0.8) < 0.02, A._clip_size(live))
    check("a clip already in shape is left alone", A.fit_to_rooms(live) is False)
    clip(os.path.join(A.CLIPS, "patio.mp4"), 540, 960); clip(os.path.join(A.CLIPS, "kitchen.mp4"), 540, 960)
    A.save_rooms({"default": "live", "rooms": {"bedroom": {"clips": ["bed.mp4"]}, "patio": {"clips": ["patio.mp4"]},
                                               "kitchen": {"clips": ["kitchen.mp4"]}, "live": {"clips": ["live.mp4"]}}})
    check("the shape most rooms share wins, not whichever room is read first", A.room_aspect() == 0.56, A.room_aspect())
    mac_clip = os.path.join(HOME, "mac-live.mp4"); clip(mac_clip, 1280, 720)
    check("the Mac fits its own copy too (it speaks over it)", M.fit_aspect(mac_clip, 0.8)
          and abs(A._clip_size(mac_clip)[0] / float(A._clip_size(mac_clip)[1]) - 0.8) < 0.02, A._clip_size(mac_clip))
else:
    print("SKIP ffmpeg checks: ffmpeg/ffprobe not installed here")

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
