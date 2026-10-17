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
rr = src[src.index('@app.post("/api/game/reelroom/chat")'):]
rr = rr[:rr.index("\n@app.")]
check("his unprompted ReelRoom line is cued privately, never as if she asked why",
      "A private cue only you can see - Gloria did not say this" in rr and "talk TO Gloria" in rr
      and "You chose to speak during the film because" not in rr)
print("--- ReelRoom: the evening's toys, on her turns and his own ---")
seg = src[src.index("_REELROOM_EVENING = {"):src.index("_SHAPE_WORDS = (")]
ns = {}; exec(seg, ns)
cue = ns["_reelroom_device_cue"](["mission", "tenera", "thruster"])
check("an unprompted line is told which toys are on, with their tags, and only those",
      "[TOUCH: mission" in cue and "[DO: tenera" in cue and "thruster" in cue and "ferri" not in cue and "ridge" not in cue, cue)
check("with no toy on, nothing is said about toys", ns["_reelroom_device_cue"]([]) == "")
check("every toy has its evening line", all(k in ns["_REELROOM_EVENING"] for k in ("mission", "tenera", "ridge", "thruster", "ferri")))
av = src[src.index("async def avatar_chat("):]
check("on her ReelRoom turns the Mission, Tenera, Ridge and thruster keep their wording, with the evening added",
      'for _rr_d in ("mission", "tenera", "ridge", "thruster"):' in av and '_DEV_LINES[_rr_d] + " " + _REELROOM_EVENING[_rr_d]' in av)
check("his own moments get the toys that are on", "_reelroom_device_cue(_devices_on())" in rr)
check("and what he reaches for fires, is stripped from what she sees, and its pictures go into the night's journal",
      "_rr_fhi(_line, context=_rr_tc.effect_context(\"reelroom\"))" in rr and 'str(_line or "") + _rr_marks' in rr)
seg2 = src[src.index("_MAP_PHONE = "):src.index('@app.get("/map")')]
ns2 = {}; exec(seg2, ns2)
_m = ns2["_map_for_phone"]("<html><head><style>body{height:100vh}</style></head><body><div id=panel></div></body></html>")
check("the map page gets its phone layout before </head>, once", _m.count('id="map-phone"') == 1
      and _m.index('id="map-phone"') < _m.index("</head>") and ns2["_map_for_phone"](_m) == _m)
check("its inspector fits above Safari's toolbar and scrolls on its own", "100dvh" in _m and "overscroll-behavior:contain" in _m)
check("the map route serves the file through it", "_map_for_phone(open(fpath).read())" in src)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
