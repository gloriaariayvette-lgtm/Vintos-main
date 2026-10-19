#!/usr/bin/env python3
"""The avatar toggle holds her choice (Gloria, 19 October: "the toggle reverted to opus 4.8 when I had opus 5.5
selected", and "sol is still on the toggle rather than argon").

The mode file was written in place; a read landing mid-write failed and came back as Opus 4.8, and the next
read-modify-write saved that over her choice. Scratch HOME: the mode file lives only there; nothing is sent."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="toggle-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))
import model_router as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  %r" % (d,)))

check("the mode file is throwaway", M._MODE_FILE.startswith(HOME), M._MODE_FILE)
M.write_mode({"mode": "opus55", "force_grok_turns": 0})
check("her Opus 5.5 is saved and read back", M.current_mode() == "opus55" and M.current_claude_model() == "claude-opus-5-5")
check("the write is atomic: no temp file is left beside it",
      os.listdir(os.path.dirname(M._MODE_FILE)) == ["model-mode.json"], os.listdir(os.path.dirname(M._MODE_FILE)))

open(M._MODE_FILE, "w").write('{"mode": "opu')            # a read landing mid-write
check("a half-written file does not read as Opus 4.8", M.current_mode() == "opus55", M.read_mode())
M.arm_grok_turns(1)                                       # a read-modify-write during that moment
check("and a save during it keeps her choice", json.load(open(M._MODE_FILE))["mode"] == "opus55"
      and json.load(open(M._MODE_FILE))["force_grok_turns"] == 1, open(M._MODE_FILE).read())
M._LAST_GOOD.clear(); os.remove(M._MODE_FILE)
check("with no file ever written, the default is still Opus 4.8", M.current_mode() == "claude")

srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the server's toggle errors answer 'unknown', not Opus 4.8",
      srv.count('return {"mode": "", "error": str(e)}') == 2 and 'return {"mode": "claude", "error": str(e)}' not in srv)
check("the server reports what was saved", 'return {"mode": _mr.current_mode()}   # what was actually saved' in srv)
page = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("the toggle cycles Argon in Sol's place", "var order=['claude','opus55','fable','grok','argon','local'];" in page
      and "argon:'\\u25C7 ARGON'" in page)
check("an unknown answer keeps the label she has", "if(!mode) return;" in page)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
