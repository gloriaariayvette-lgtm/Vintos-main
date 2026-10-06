#!/usr/bin/env python3
"""A clip whose video will not render costs one still, not one per tick, and she gets the still (Gloria, 2026-10-06:
"he's been making a BUNCH of nanobanana images in atlas cloud but I haven't been receiving videos for them").

A staged YES was replayed every tick for six hours, and each replay composed a new nano-banana image on Atlas before
the video failed again. Scratch HOME; the network, the image model, the video model and delivery are stubs.
"""
import importlib.util, os, sys, tempfile, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-video-retry-")
os.environ["HOME"] = HOME

def _no_network(*a, **k):
    raise AssertionError("this suite must never reach the network")

SENT = []
STAGES = {}
stage = types.SimpleNamespace(
    key_for=lambda *p: "k%d" % len(STAGES),
    save=lambda organ, key, payload, note="": STAGES.__setitem__(key, {"payload": dict(payload), "state": "pending"}),
    done=lambda organ, key, outcome="": STAGES[key].update(state="done", outcome=outcome),
    pending=lambda organ, max_age_hours=None: [(k, dict(v["payload"]), "earlier") for k, v in STAGES.items() if v["state"] == "pending"])
sys.modules["requests"] = types.SimpleNamespace(post=_no_network, get=_no_network)
sys.modules["deliver"] = types.SimpleNamespace(CHANNELS={}, deliver=lambda *a, **k: SENT.append((a, k)) or {"state": "sent"})
sys.modules["artifact_manifest"] = types.SimpleNamespace(unique_path=lambda d, stem, ext, data: (os.path.join(d, stem + ext), 1))
sys.modules["reflection_stage"] = stage
spec = importlib.util.spec_from_file_location("send_video_retry_test", os.path.join(ROOT, "bin", "vintos-send-video.py"))
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every path is a scratch one", V.MEMORY.startswith(HOME) and V.SCENE_DIR.startswith(HOME))
os.makedirs(V.SCENE_DIR, exist_ok=True)
COMPOSED = []
def compose_us(scene, verbose=False, place=None):
    p = os.path.join(V.SCENE_DIR, "us-%d.jpg" % len(COMPOSED)); open(p, "wb").write(b"jpg"); COMPOSED.append(p); return p
V.compose_us = compose_us
V.atlas_generate = lambda *a, **k: None                    # the video will not render
V.autonomous_presence_allows = lambda: True
V.in_quiet_hours = lambda: False
V.cooldown_active = lambda: False
V.decide = lambda force=False: {"decision": "YES", "kind": "together", "scene": "the two of us on the patio",
                                "scene_ref": "", "prompt": "I pull her closer", "say": "Come here."}

V.main()                                                   # tick 1: composes once, the video fails
V.main()                                                   # tick 2: the staged YES again
check("a replayed decision reuses the still it already made", len(COMPOSED) == 1, COMPOSED)
check("after two failed renders it is not tried again", all(v["state"] == "done" for v in STAGES.values())
      and "did not render after 2 tries" in list(STAGES.values())[0].get("outcome", ""), STAGES)
check("... and she is sent the still, with his words", len(SENT) == 1 and SENT[0][0][0] == "us-0.jpg"
      and "Come here." in SENT[0][0][2] and "/api/video/still/us-0.jpg" in SENT[0][1]["click"], SENT)
V.main()                                                   # tick 3: a fresh decision, not the old one replayed
check("the next tick starts fresh rather than replaying it", len(COMPOSED) == 2)
srv = open(os.path.join(ROOT, "bin", "server.py")).read()
check("the server serves those stills, and only those", '@app.get("/api/video/still/{filename}")' in srv
      and '(?:us|scene)-' in srv)
check("Atlas's model can be named in a file, for when one is retired", "~/.vintos/atlas-model" in open(
      os.path.join(ROOT, "bin", "vintos-send-video.py")).read())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
