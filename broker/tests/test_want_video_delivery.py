#!/usr/bin/env python3
"""A video he makes from a want reaches her phone (16 October: "He made the nicest video, but ntfy didn't send it to
me"). Want videos went only to his gallery; now each is sent once through the shared delivery path, like the videos
vintos-send-video makes. A projector-wall clip is not sent. Scratch HOME; the subscription, the keyframe painter and
the ntfy POST are stubs; nothing leaves the machine."""
import importlib.util, json, os, sys, tempfile, types
HOME = tempfile.mkdtemp(prefix="want-video-"); os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory", "art", "video"))
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
NET = []
def _no(*a, **k): NET.append(a); raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=_no, post=_no, put=_no)
import deliver as D
SENT = []
D.POST = lambda url, data, headers, timeout: (SENT.append((url, data, dict(headers))), 200)[1]
D.SLEEP = lambda s: None
D.RECEIPTS = os.path.join(HOME, "receipts.json")
spec = importlib.util.spec_from_file_location("vintos_video_under_test", os.path.join(REPO, "scripts", "vintos-video.py"))
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
V._gs = types.SimpleNamespace(video=lambda *a, **k: b"\x00\x00\x00\x18ftypmp42fakeclip", Unavailable=Exception)
V.paint_keyframe = lambda text: os.path.join(HOME, "key.png")
open(os.path.join(HOME, "key.png"), "wb").write(b"\x89PNG fake")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the shelf and receipts are scratch, the sender a stub", V.VID_DIR.startswith(HOME) and D.RECEIPTS.startswith(HOME))

ok = V.make_one("the two of us under the balcony light", want_id="w-123")
check("a video from a want is made", ok and len(os.listdir(V.VID_DIR)) >= 1)
check("and sent to her phone once, linked to the clip", len(SENT) == 1 and "/api/video/file/video-" in SENT[0][2].get("Click", "")
      and SENT[0][2].get("Attach") == SENT[0][2].get("Click"), SENT)
fname = SENT[0][2]["Click"].rsplit("/", 1)[-1]
check("its receipt says sent", D.receipt_for(fname, "ntfy").get("state") == "sent")
V._send_to_her(fname, "w-123")
check("the same clip is never sent twice", len(SENT) == 1)
V.make_one("the wall is breathing", want_id="projector")
check("a projector-wall clip is not sent to her phone", len(SENT) == 1)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
