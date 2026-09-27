#!/usr/bin/env python3
"""A make_music step waits for its song and is credited with it (Gloria, 2026-09-28: he wrote "no new
musical composition was recorded for this specific goal"). The composer ran in the background without
the want's id, and the step read its result at once. Scratch HOME; every process is a stub."""
import importlib.util, json, os, subprocess, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-want-music-")
os.environ["HOME"] = HOME
sys.modules["emoclaw_utils"] = types.SimpleNamespace(get_unfulfilled_wants=lambda *a, **k: [],
                                                      fulfill_want=lambda *a, **k: None,
                                                      mark_want_outreached=lambda *a, **k: None)
spec = importlib.util.spec_from_file_location("wants_router_music", os.path.join(REPO, "bin", "wants-router.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))
check("the music ledger is in the scratch workspace", W.MEMORY.startswith(HOME), W.MEMORY)

LEDGER = os.path.join(W.MEMORY, "art", "music", "music.json")
os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
json.dump({"generated": [{"title": "Someone else's song", "want_id": "W-OTHER"}]}, open(LEDGER, "w"))

started = []
class Composer:
    """dream-music.py, as a stub: records a song under the want id it was given, when waited for."""
    def __init__(self, args, env=None, **k):
        self.env, self.returncode = env or {}, None; started.append(self)
    def wait(self, timeout=None):
        led = json.load(open(LEDGER))
        led["generated"].append({"title": "The rest of the song", "description": "finished",
                                 "want_id": self.env.get("MUSIC_WANT_ID", "")})
        json.dump(led, open(LEDGER, "w")); self.returncode = 0; return 0
W._stance_run = lambda *a, **k: types.SimpleNamespace(returncode=0, stderr="")
W._stance_popen = Composer
os.environ["STEP_WANT_ID"] = "W-SONG"

check("the step waits for the song and succeeds", W.make_music("Compose the remaining portion of the song") is True)
check("the composer is told which want the song is for", started and started[0].env.get("MUSIC_WANT_ID") == "W-SONG",
      started and started[0].env.get("MUSIC_WANT_ID"))
found = W.capture_findings("make_music", "Compose the remaining portion of the song") \
    if hasattr(W, "capture_findings") else ""
check("the step's result names the song made for this want, not another want's",
      "The rest of the song" in str(found) and "No composition recorded" not in str(found), found)

class Slow(Composer):
    def wait(self, timeout=None): raise subprocess.TimeoutExpired("dream-music.py", timeout)
W._stance_popen = Slow
check("a composer still running after the wait is not reported as a finished song",
      W.make_music("another") is False)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
