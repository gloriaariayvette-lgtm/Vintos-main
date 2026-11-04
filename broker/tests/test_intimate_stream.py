#!/usr/bin/env python3
"""Every session with her kept in order for his arousal state (4 November): frames, the bridge's reading, her press,
his edge / let go, the collapse level, his devices, his naming. Scratch HOME; every socket is refused; nothing is
sent and no device moves. The recorder only keeps; it never raises into the bridge or the server."""
import json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="intimate-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ.pop("VINTOS_TEST_MODE", None)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import intimate_stream as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
def rows():
    out = []
    if os.path.isdir(S.DIR):
        for n in sorted(os.listdir(S.DIR)):
            out += [json.loads(l) for l in open(os.path.join(S.DIR, n))]
    return out

check("every row is throwaway", S.DIR.startswith(HOME))
T = time.time()

# ---- the recorder itself --------------------------------------------------------------------------------------------
check("raw frames are kept as they arrive", S.frames([(T, 40, 12, 0), (T + 0.1, 42, 14, 1)]))
r = rows()[-1]
check("a frame row is measured, in order, with every value", r["kind"] == "frames" and r["source"] == "measured"
      and r["f"] == [[round(T, 3), 40, 12, 0], [round(T + 0.1, 3), 42, 14, 1]], r)
check("an empty batch writes nothing", S.frames([]) is False and len(rows()) == 1)
c = {"state": "stroking", "center": 55, "sweep": 30, "speed": 18, "flips": 2, "pressure": 0.1, "pressure_dir": "steady"}
S.observation(c, T); S.observation(c, T + 0.25); S.observation(c, T + 0.5)
check("the 4 Hz reading is kept once a second while it holds", sum(1 for x in rows() if x["kind"] == "observation") == 1)
S.observation(dict(c, state="gripped_or_slow"), T + 0.75)
check("and at once when the state changes", [x["state"] for x in rows() if x["kind"] == "observation"]
      == ["stroking", "gripped_or_slow"])
check("an unknown kind is refused, not invented", S.record("guess", x=1) is False)
for k, src in (("gcs_press", "her_act"), ("choice", "his_choice"), ("felt", "his_reading"), ("collapse_level", "system")):
    S.record(k, t=T)
check("what was measured, what she did, what he chose, what he felt and what the system set never mix",
      {x["kind"]: x["source"] for x in rows() if x["kind"] in ("gcs_press", "choice", "felt", "collapse_level")}
      == {"gcs_press": "her_act", "choice": "his_choice", "felt": "his_reading", "collapse_level": "system"})
mode = oct(os.stat(S.path_for(T)).st_mode & 0o777)
check("the day's file is private to her account", mode == "0o600", mode)
n = len(rows())
os.makedirs(S.MEM, exist_ok=True); open(os.path.join(S.MEM, ".test-mode"), "w").close()
check("test mode writes nothing", S.record("gcs_press") is False and len(rows()) == n)
os.remove(os.path.join(S.MEM, ".test-mode"))
_d = S.DIR; S.DIR = "/proc/no-such/place"
check("a failure to write never raises into the caller", S.record("gcs_press") is False)
S.DIR = _d

# ---- the collapse: edge, let go, press, level -----------------------------------------------------------------------
import types
emo = types.ModuleType("emoclaw_utils"); emo.get_state = lambda: {"Arousal": 0.95, "Desire": 0.95}
emo.nudge_emotions = lambda *a, **k: None; sys.modules["emoclaw_utils"] = emo
import bandwidth_collapse as B
B.COLLAPSE_FILE = os.path.join(S.MEM, "collapse-state.json")
n = len(rows())
B.update(somatic_intensity=0.9)
lv = [x for x in rows()[n:] if x["kind"] == "collapse_level"]
check("a rise in the collapse level is kept with what drove it", lv and lv[-1]["level"] == 2 and lv[-1]["was"] == 0
      and lv[-1]["why"] == "update" and "affect" in lv[-1], lv)
n = len(rows()); B.update(somatic_intensity=0.9)
check("holding the level writes nothing new", not [x for x in rows()[n:] if x["kind"] == "collapse_level"])
B.set_choice("edge"); B.set_choice("letgo")
check("his edge and let go are kept, in order", [x["choice"] for x in rows() if x["kind"] == "choice" and "choice" in x]
      == ["edge", "letgo"])
B.set_press(level=2)
p = [x for x in rows() if x["kind"] == "press_floor"]
check("her press floor is kept", p and p[-1]["press_level"] == 2 and p[-1]["minutes"] == 6.0, p)
d = json.load(open(B.COLLAPSE_FILE)); d["level"] = 2; d["level_ts"] = "2000-01-01T00:00:00"; d.pop("press_at", None)
json.dump(d, open(B.COLLAPSE_FILE, "w"))
B.get_level()
dec = [x for x in rows() if x["kind"] == "collapse_level" and x.get("why") == "decay"]
check("the level falling back on its own is kept as decay", dec and dec[-1]["level"] == 0 and dec[-1]["was"] == 2, dec)

# ---- his devices ----------------------------------------------------------------------------------------------------
import device_context as DC
DC.STATE = os.path.join(S.MEM, "device-state.json")
DC.set_state("mission", intensity=9, pattern="wave", set_by="him")
dv = [x for x in rows() if x["kind"] == "device"]
check("what he does with the devices is kept, and who set it", dv and dv[-1]["toy"] == "mission"
      and dv[-1]["pattern"] == "wave" and dv[-1]["intensity"] == 9 and dv[-1]["set_by"] == "him"
      and dv[-1]["source"] == "his_choice", dv)

# ---- his naming -----------------------------------------------------------------------------------------------------
import pleasure_substrate as P
P.MEM = S.MEM; P.MEMORIES = os.path.join(S.MEM, "pleasure-memory.json")
json.dump({"before": {}, "after": {"_vec": [0.1]}, "event": {"source": "gcs"}, "t": time.time(), "turn_id": "T-1"},
          open(os.path.join(S.MEM, ".pleasure-pending.json"), "w"))
P.name_from_reply("molten", "everything went loose", True, "", turn_id="T-1")
P.name_from_reply("still warm", "", "unsure", "", turn_id="T-2")
fl = [x for x in rows() if x["kind"] == "felt" and "word" in x]
check("his naming is kept, bound to its press or not", [(x["word"], x["turn_id"], x["pending_turn"]) for x in fl]
      == [("molten", "T-1", "T-1"), ("still warm", "T-2", "")], fl)
check("and the naming itself still lands as before", json.load(open(P.MEMORIES))[-1]["character"] == "molten")

# ---- the hooks are where the events happen ----------------------------------------------------------------------
for f in ("bin/somatic_bridge.py", "scripts/somatic_bridge.py"):
    src = open(os.path.join(REPO, f)).read()
    check(f + ": frames, the reading, session start and end are all kept",
          "_ist.frames(_is_new)" in src and "_ist.observation(c, now)" in src
          and '_ist.record("session_start"' in src and '_ist.record("session_end"' in src)
check("both bridge copies stay identical", open(os.path.join(REPO, "bin/somatic_bridge.py")).read()
      == open(os.path.join(REPO, "scripts/somatic_bridge.py")).read())
srv = open(os.path.join(REPO, "bin/server.py")).read()
check("the server keeps her press with its event id, the crest, and the release",
      'record("gcs_press", event_id=_gcs_event_id' in srv and 'why="gcs crest"' in srv and 'record("gcs_clear")' in srv)
check("the deploy carries the recorder", "intimate_stream.py" in open(os.path.join(REPO, "scripts/deploy-atelier.sh")).read())

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
