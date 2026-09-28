#!/usr/bin/env python3
"""A live scene he renders for a turn appears on her screen, from a photo send as well as a text send
(2026-09-28: the scene for her 4 a.m. lakeshore photo was ready in 29 s and never shown). Scratch HOME;
nothing is rendered or sent - the status store is exercised directly and the network is a stub."""
import os, re, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-live-follow-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "bin"))
import avatar_stage as A

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))
check("the stage writes only to the scratch workspace", A.WORKSPACE.startswith(HOME) and A.CLIPS.startswith(HOME), A.CLIPS)
check("the network is a stub", sys.modules["requests"].post is no_network)

# The status the app polls is per turn: this turn's finished scene reads done, another turn's does not leak.
A._slot_update("t-photo", status="done", prompt="lakeshore at four", started=1.0, finished=30.0, seconds=29.0)
A._slot_update("t-other", status="rendering", prompt="elsewhere", started=2.0)
check("this turn's finished scene reads done", A.live_status("t-photo")["status"] == "done")
check("a turn with no scene reads idle, so the app stops waiting", A.live_status("t-none")["status"] == "idle")

server = open(os.path.join(REPO, "bin", "server.py")).read()
app = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("every avatar reply names the turn its scene renders in",
      '"live_slot": (_turn.turn_id if _turn is not None else "")' in server)
photo = app[app.index("async function avSendPhoto"):app.index("function avGCS")]
check("a photo reply follows its scene", "_avFollowLive(d.live_slot)" in photo)
check("a photo reply is shown and spoken like any reply", "_avShowBubble(parsed.text || raw)" in photo
      and "_avStartReplyMedia(parsed.text || raw, parsed.scenes)" in photo)
follow = app[app.index("async function _avFollowLive"):app.index("function _avStartReplyMedia")]
check("the app follows by this turn's slot and crossfades to the live room when it lands",
      "?slot='+encodeURIComponent(slot)" in follow and "setRoom('live')" in follow)
check("the app never starts a second render of its own (the server's is admitted by the effect gate)",
      "/api/avatar/live'" not in app and not re.search(r"/api/avatar/live['\"],\s*\{method:'POST'", app))
check("a text reply follows its scene the same way", app.count("_avFollowLive(d.live_slot)") == 2)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
