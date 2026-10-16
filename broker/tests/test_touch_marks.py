#!/usr/bin/env python3
"""A [TOUCH:] on the Tenera, Ridge or Ferri leaves its picture in the ledger (16 October). Only [DO:] wrote
device-state, so a touch left no mark under his words: Gloria, "the visuals for everything but the Mission STILL are
not appearing in the conversation ledger". And in ReelRoom the Ferri is described as worn at home during the movie,
not out in public. HOME is scratch before any import; the toy sender is a stub; requests refuses everything."""
import importlib.util, json, os, sys, tempfile
HOME = tempfile.mkdtemp(prefix="touch-marks-"); os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"))
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import requests
NET = []
def _no(*a, **k): NET.append(a); raise requests.ConnectionError("this suite reaches nothing")
requests.post = requests.get = requests.put = _no
import toy_link as T, device_context as D, turn_coordinator as TC
SENT = []
T.send = lambda toy, level, *a, **k: (SENT.append((toy, level)), True)[1]
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))
check("the device store is scratch and the sender a stub", D.STATE.startswith(HOME) and T.send.__name__ == "<lambda>")

out = T.parse_and_send("come here [TOUCH: tenera 12 5] [TOUCH: ferri 6] [TOUCH: ridge 9]", context=TC.effect_context("avatar"))
check("the touches were sent", [o[2] for o in out] == ["sent"] * 3 and len(SENT) == 3, out)
st = json.load(open(D.STATE))
check("each touch is recorded as his, with its level", all(st[t]["last"]["by"] == "him" for t in ("tenera", "ferri", "ridge"))
      and st["tenera"]["last"]["intensity"] == 12 and st["ferri"]["last"]["intensity"] == 6, st)

spec = importlib.util.spec_from_file_location("ledger_under_test", os.path.join(REPO, "scripts", "interaction-ledger.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
marks = L._device_marks()
check("the ledger draws all three under his words", "tenera:" in marks and "ferri:" in marks and "ridge:" in marks, marks)
check("a held level is drawn as its bar, not left blank", D.bar(12) in marks and D.bar(6) in marks, marks)
T.parse_and_send("[TOUCH: tenera 0]", context=TC.effect_context("avatar"))
check("a touch to 0 is still, and keeps the last real run for the mark", json.load(open(D.STATE))["tenera"]["pattern"] == "still")

print("--- the turn's pictures, from what actually fired ---")
import time as _t, device_patterns as DP
os.environ["VINTOS_SURFACE"] = "avatar"
DP.time.sleep = lambda s: None
T.send_pattern = lambda *a, **k: True        # a preset shape goes to the hub as a pattern: stubbed like send
T.connected = lambda *a, **k: True           # every toy present, so no hub probe is made
t0 = _t.time()
DP.fire_his_intent("now [DO: tenera wave 4 14] [TOUCH: ferri 7] [DO: ridge pulse 3 12]", context=TC.effect_context("avatar"))
marks = D.turn_marks(t0)
check("every toy fired this turn is drawn", all(k in marks for k in ("tenera:", "ferri:", "ridge:")), marks)
check("a pattern is drawn as its shape, a held level as its bar", D.spark("wave") in marks and D.bar(7) in marks, marks)
check("nothing fired before the turn is drawn", D.turn_marks(_t.time() + 1) == "")
os.environ["VINTOS_DEVICE_MARKS"] = marks
check("the ledger takes the server's pictures as given, with no time window", L._device_marks() == marks)
os.environ["VINTOS_DEVICE_MARKS"] = ""
check("and an empty turn stays empty, not a guess from an earlier one", L._device_marks() == "")
del os.environ["VINTOS_DEVICE_MARKS"]

src = open(os.path.join(REPO, "bin", "server.py")).read()
av = src[src.index("async def avatar_chat("):]
check("the avatar and ReelRoom route draws the turn's pictures after his tags fire",
      av.index("_fx_t0 = time.time()") < av.index("_turn_marks = _dc_tm.turn_marks(_fx_t0)"))
check("they go under his words in his chat history", '"content": reply + _turn_marks' in av)
check("and to the ledger writer, exactly", "VINTOS_DEVICE_MARKS=_turn_marks" in av)
i = src.index('if _surface == "reelroom":\n            # In ReelRoom she is at home watching a movie')
block = src[i:i + 1400]
check("in ReelRoom the Ferri is described as worn at home during the movie, not in public",
      '_DEV_LINES["ferri"]' in block and "no one" in block and "OUT IN" not in block and '_DEV_ROLE["ferri"]' in block)
check("everywhere else it keeps the public-tease description", "OUT IN \"\n            \"PUBLIC" in src or "OUT IN PUBLIC" in src.replace('"\n            "', ""))
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
