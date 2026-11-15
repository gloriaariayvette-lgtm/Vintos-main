#!/usr/bin/env python3
"""14 November: her phone was within 1 m of the office chair for 46 minutes and the chair counted 0.0 seated, so the
office moment (and his DESKTOP act) never came. A flicker of the 1 m reading threw her sitting away, and the board
never says press_start again while she stays down. Here: a flicker keeps her seat; a real absence does not; the boards
re-send the strip's state when she comes near; and the TV takes his words, not only a link he does not have."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="chair-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import house_boards as B
import house_hands as H

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

os.makedirs(B.MEM, exist_ok=True)
cfg = B.config(); T = 1794700000.0
st = B.load_state()
def ev(board, kind, text, t):
    return B.observe(st, board, kind, text, t, cfg)

# she comes near, sits, and her phone's reading flickers twice while she stays down
ev("house-touch", "near", "on", T)
ev("house-touch", "event", "press_start", T + 5)
ev("house-touch", "near", "off", T + 40)
ev("house-touch", "near", "on", T + 55)
ev("house-touch", "near", "off", T + 120)
ev("house-touch", "near", "on", T + 130)
due = B.due(st, T + 5 + 60 * cfg["sit_minutes"] + 1, cfg)
check("a flicker of her phone does not lose her sitting: the chair is a moment after sit_minutes", due == ("office", "house-touch"), due)
check("her sitting is still counted from when she sat", st["boards"]["house-touch"]["sit_since"] == T + 5, st["boards"]["house-touch"])

# the board's re-sent state on coming near is idempotent: it does not restart the clock
ev("house-touch", "event", "press_start", T + 131)
check("a re-sent press_start keeps the original sit time", st["boards"]["house-touch"]["sit_since"] == T + 5)

# she gets up: the board's press_end (sent now that she is near) clears it
ev("house-touch", "event", "press_end", T + 400)
check("press_end clears her sit", st["boards"]["house-touch"].get("sit_since") is None and st["boards"]["house-touch"].get("pressed_since") is None)
check("and no moment comes from an empty chair", B.due(st, T + 1000, cfg) is None)

# a real absence: phone away longer than AWAY_S, then back, with no press report -> not taken as seated
T2 = T + 20000
ev("house-touch", "near", "on", T2)
ev("house-touch", "event", "press_start", T2 + 1)
ev("house-touch", "near", "off", T2 + 10)
ev("house-touch", "near", "on", T2 + 10 + B.AWAY_S + 5)
check("after a real absence she is not assumed to be seated", st["boards"]["house-touch"].get("sit_since") is None
      and st["boards"]["house-touch"].get("pressed_since") is None, st["boards"]["house-touch"])

# the menu he is shown at the sofa offers TV by his own words
check("the TV line offers find <what to put on>", B.HOW["TV"].startswith("TV: find "))

# the TV: his words become a YouTube search, the top match plays
class Home:
    played = []
    def tv_status(self): return {"power": "off"}
    def tv_youtube(self, vid): self.played.append(vid); return True
H._quiet = lambda present: False
H.youtube_find = lambda q: ("JavK3uFay0I", "Rainy Lofi Ambience") if q == "rain on a window, lofi" else ("", "nothing")
ok, said = H.tv("find rain on a window, lofi", home=Home())
check("TV: find <words> plays the top YouTube match", ok and Home.played == ["JavK3uFay0I"] and "Rainy Lofi Ambience" in said, said)
ok, said = H.tv("watch rain on a window, lofi", home=Home())
check("watch <words> is a search too", ok and Home.played[-1] == "JavK3uFay0I", said)
ok, said = H.tv("make it nice", home=Home())
check("words without find/watch are not guessed at; he is told what works", not ok and said.startswith("say find <what"), said)
ok, said = H.tv("find something that does not exist", home=Home())
check("a search with no match plays nothing and says so", not ok and said == "nothing", said)
ok, said = H.tv("https://youtu.be/vYIYIVmOo3Q", home=Home())
check("a link still plays as before", ok and Home.played[-1] == "vYIYIVmOo3Q", said)

# the firmware re-sends the strip's state when her phone comes near, on both pressure boards
for board in ("house-touch", "house-press-mic"):
    y = open(os.path.join(REPO, "home", "esphome", board + ".yaml")).read()
    check("%s re-sends press_start/press_end on coming near" % board,
          "lambda: 'return x && id(pressed).has_state();'" in y
          and 'return id(pressed).state ? "press_start" : "press_end";' in y)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
