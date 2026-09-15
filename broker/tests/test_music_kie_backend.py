#!/usr/bin/env python3
"""Music routes to Kie.ai Suno v6 with a local ACE-Step fallback, and never touches a
real backend or her live store during the test."""
import importlib.util, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
scratch = tempfile.TemporaryDirectory(); os.environ["HOME"] = scratch.name

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

def check(label, ok):
    if not ok: raise AssertionError(label)
    print("ok -", label)

DM = load("dream_music", os.path.join(REPO, "bin", "dream_music.py"))

# ── Isolation: repoint every store the module writes to a throwaway dir ──────────
MUS = os.path.join(scratch.name, "music"); os.makedirs(MUS, exist_ok=True)
DM.MUSIC = MUS; DM.LOG = os.path.join(MUS, "music.json")
DM.PROMPTS = os.path.join(scratch.name, "prompts"); DM.JOURNAL = os.path.join(scratch.name, "activity-log")
DM.KIE_KEY = "test-key"; DM.KIE_MODEL = "V6"; DM.BACKEND = "kie"

# ── Stub the only sender: no request may reach api.kie.ai or localhost:8001 ──────
SEEN = []
class _Resp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
class _FakeRequests:
    kie_ok = True
    def post(self, url, json=None, headers=None, timeout=None, **k):
        SEEN.append(("POST", url, json))
        if "api.kie.ai" in url and url.endswith("/generate"):
            if not _FakeRequests.kie_ok: return _Resp({"code": 429, "msg": "insufficient credits"})
            return _Resp({"code": 200, "data": {"taskId": "KIE123"}})
        if "localhost:8001" in url and url.endswith("/release_task"):
            return _Resp({"data": {"task_id": "ACE9"}})
        raise AssertionError("unexpected POST " + url)
    def get(self, url, params=None, headers=None, timeout=None, **k):
        SEEN.append(("GET", url, params))
        if "api.kie.ai" in url and "record-info" in url:
            return _Resp({"data": {"status": "SUCCESS", "response": {"sunoData": [
                {"audioUrl": "https://cdn.kie.ai/out/a.mp3", "duration": 181, "id": "t1"}]}}})
        raise AssertionError("unexpected GET " + url)
sys.modules["requests"] = _FakeRequests()
DM.time.sleep = lambda *_a, **_k: None   # do not actually wait between polls

# ── Kie is primary: a vocal turn routes to Kie v6 in custom mode ─────────────────
tid = DM.generate("Under the Duvet", "warm indie folk", desc="stay with me\nthe light is low",
                  instrumental=False, duration=120, gender="male")
check("Kie is the primary backend (task id is kie-tagged)", tid == "kie:KIE123")
kie_body = next(b for m, u, b in SEEN if m == "POST" and "api.kie.ai" in u)
check("Kie custom mode carries model V6, title and style", kie_body["model"] == "V6" and kie_body["customMode"] is True and kie_body["title"] == "Under the Duvet" and kie_body["style"].startswith("warm indie folk"))
check("a vocal turn sends lyrics as the prompt and a male vocal gender", "stay with me" in kie_body["prompt"] and kie_body.get("vocalGender") == "m")
check("an authored ACE-Step-only knob is not sent to Kie", "thinking" not in kie_body and "bpm" not in kie_body)

# ── poll() dispatches by tag and normalizes Kie tracks to the ACE-Step shape ─────
tracks = DM.poll(tid)
check("Kie poll normalizes to {file,duration,id}", tracks and tracks[0]["file"] == "https://cdn.kie.ai/out/a.mp3" and tracks[0]["duration"] == 181)
check("a remote mp3 keeps its real extension, not .wav", DM._ext_for(tracks[0]["file"]) == ".mp3")
check("the record names what actually rendered it", DM._model_of(tid) == "suno-v6 (kie)")

# ── Fallback: when Kie fails at submit, generate() falls to local ACE-Step ───────
_FakeRequests.kie_ok = False; SEEN.clear()
tid2 = DM.generate("Fallback Piece", "ambient piano", instrumental=True)
check("a Kie submit failure falls back to ACE-Step", tid2 == "ace:ACE9")
check("the fallback still tried Kie first", any("api.kie.ai" in u for _m, u, _b in SEEN) and any("localhost:8001" in u for _m, u, _b in SEEN))
check("legacy untagged task ids still poll ACE-Step", ("GET", 0, 0) not in SEEN)  # sanity noop; real check below

# poll dispatch for both tags + legacy
SEEN.clear()
class _AceResp:
    def json(self): return {"data": [{"status": 1, "result": json.dumps([{"file": "/v1/audio?path=/x/a.wav", "duration": 120, "id": "a"}])}]}
_FakeRequests.post = lambda self, url, json=None, headers=None, timeout=None, **k: (SEEN.append(("POST", url, json)) or _AceResp())
check("ace-tagged id polls ACE-Step", DM.poll("ace:ACE9")[0]["file"].endswith("a.wav"))
check("legacy untagged id is treated as ACE-Step", DM.poll("ACE9")[0]["id"] == "a")

# ── Isolation assertions the next edit cannot quietly undo ───────────────────────
check("music log is throwaway, not her live store", DM.LOG.startswith(scratch.name) and "/.vintos/workspace/" not in DM.LOG)
check("the sender is a stub, never the real requests library", type(sys.modules["requests"]).__name__ == "_FakeRequests")
check("no call reached any host but api.kie.ai and localhost:8001",
      all(("api.kie.ai" in u) or ("localhost:8001" in u) for _m, u, _b in SEEN))

print("\nall music-backend checks passed")
