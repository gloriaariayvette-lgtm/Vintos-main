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

# A finished live scene is where he is, and stays until he names another room.
import json
os.makedirs(A.CLIPS, exist_ok=True)
for c in ("bed.mp4", "live.mp4"): open(os.path.join(A.CLIPS, c), "wb").write(b"x" * 20000)
A.save_rooms({"default": "bedroom", "rooms": {"bedroom": {"photo": "", "pose": "on the bed", "clips": ["bed.mp4"]}}})
BY = os.path.join(A.CLIPS, "by-content"); os.makedirs(BY, exist_ok=True)
import hashlib
prompt = "night waterfront promenade at the blue lamppost"
# the reuse lane installs without any render or network: prime its content-addressed copy
key = hashlib.sha256((prompt + "|" + "" + "|" + "self" + "|").encode()).hexdigest()[:16]
open(os.path.join(BY, key + ".mp4"), "wb").write(b"y" * 20000)
A._slot_update("t-render", status="rendering", started=1.0)
A._live_worker(prompt, "self", slot="t-render")
man = json.load(open(A.MANIFEST))
check("a finished live scene is the room the app opens on", man.get("default") == "live"
      and man["rooms"]["live"]["clips"] == ["live.mp4"], man)
check("he is told he is in it, so his required room tag keeps him there",
      "You are in your live scene right now" in A.scene_line() and "[SCENE: live] keeps you there" in A.scene_line())
check("[SCENE: live] keeps it up", A.remember_room("live") == "live" and json.load(open(A.MANIFEST))["default"] == "live")
check("naming another room is a scene change", A.remember_room("bedroom") == "bedroom"
      and json.load(open(A.MANIFEST))["default"] == "bedroom")

server = open(os.path.join(REPO, "bin", "server.py")).read()
app = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("every avatar reply names the turn its scene renders in",
      '"live_slot": (_turn.turn_id if _turn is not None else "")' in server)
photo = app[app.index("async function avSendPhoto"):app.index("function avGCS")]
check("a photo reply follows its scene", "_avReplyStage(parsed.text || raw, parsed.scenes, d.live_slot" in photo)
check("a photo reply is shown and staged like any reply", "_avShowBubble(parsed.text || raw)" in photo)
follow = app[app.index("async function _avLiveStatus"):app.index("function _avStartReplyMedia")]
check("the app follows by this turn's slot and crossfades to the live room when it lands",
      "?slot='+encodeURIComponent(slot)" in follow and "setRoom('live')" in follow and "_avFollowLive(slot)" in follow)
check("the room tag written with a render does not pull him out of it",
      "_avStartReplyMedia(display, live ? [] : scenes)" in follow)
check("when his words end he goes back to where he IS, not the room the words started in",
      "self.setRoom(self.home||room)" in app and "this.home=name;" in app)
check("the server does not let that room tag replace the live scene as her opening room",
      '_own_live = (_turn is not None and _avst_rm.live_status(_turn.turn_id).get("status")' in server)
check("the app never starts a second render of its own (the server's is admitted by the effect gate)",
      "/api/avatar/live'" not in app and not re.search(r"/api/avatar/live['\"],\s*\{method:'POST'", app))
check("a text reply follows its scene the same way", "_avReplyStage(display, scenes, d.live_slot" in app)
twin = open(os.path.join(REPO, "..", "vintos-app", "vintos-app", "src", "index.html")).read() \
    if os.path.exists(os.path.join(REPO, "..", "vintos-app", "vintos-app", "src", "index.html")) else None
if twin is not None:
    check("the iPhone app carries the same staging", all(x in twin for x in (
        "_avReplyStage(parsed.text || raw, parsed.scenes, d.live_slot", "self.setRoom(self.home||room)",
        "_avStartReplyMedia(display, live ? [] : scenes)")))

# Not every turn: at most LIVE_PER_DAY new live scenes a day, whoever asks (2026-09-30: "3 max NEW renders per day").
import asyncio
check("the day's count lives in the scratch stage", A.LIVE_COUNT.startswith(HOME))
try: os.remove(A.LIVE_COUNT)
except FileNotFoundError: pass
check("three a day", A.LIVE_PER_DAY == 3 and A.live_left() == 3 and "3 left today" in A.scene_line())
STARTED = []
_real_worker = A._live_worker
A._live_worker = lambda *a, **k: STARTED.append(a)
A._mac_url = lambda: "http://stub"
got = [A.start_live("scene %d" % i, slot="t-%d" % i)["status"] for i in range(3)]
check("three new scenes start in a day, however close together", got == ["rendering"] * 3 and len(STARTED) == 3, got)
st4 = A.start_live("a fourth", slot="t-4")
check("a fourth the same day does not start", st4["status"] == "refused" and len(STARTED) == 3, st4)
check("and says why", "for today are used" in (st4.get("error") or ""), st4)
check("his own [RENDER:] after that starts nothing", A.kick_from_reply("[RENDER: the pier]", slot="t-5") is False
      and len(STARTED) == 3)
line = A.scene_line()
check("he is told they are used for today, and not offered [RENDER:]",
      "for today are used" in line and "[RENDER:" not in line, line[-200:])
gate = asyncio.run(A.scene_gate("look at this", "http://stub", {}, slot="t-6"))
check("the gate asks nothing once they are used", gate.get("spaced") is True and gate["decision"] == "NO")
json.dump({"date": "2000-01-01", "count": 3}, open(A.LIVE_COUNT, "w"))

check("a new day has three again", A.live_left() == 3 and "[RENDER:" in A.scene_line())
A._live_worker = _real_worker

# 2026-10-02: "He selected patio, but that's not the patio scene. He keeps paying for new scenes and they're not
# even matching what he's currently setting." The gate ran on every message, before his reply, and bought scenes.
pre = server[server.index("async def avatar_chat(msg: ChatMessage"):server.index("message = msg.message")]
check("no scene is decided when her message lands, before his reply", "scene_gate(" not in pre and "_avst_g" not in server)
kick = server[server.index("# [RENDER:] starts NOW"):server.index('return {"reply": reply, "model": _model_used')]
check("a new scene is made only when his reply asks with [RENDER:]", 'if _rn:' in kick
      and "wanted=_rn.group(1).strip()" in kick and "await _avst_k.scene_gate(" in kick, kick[:600])
check("if the gate cannot answer, his words are rendered as written", "_avst_k.kick_from_reply(reply" in kick)
SEEN = []
class _C:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        SEEN.append(json)
        return types.SimpleNamespace(json=lambda: {"choices": [{"message": {"content":
            "DECISION: NO\nKIND: together\nSCENE_REF:\nSCENE:\nSTILL:\nPROMPT: holding her at the rail"}}]})
sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_C)
A._vsv = lambda: types.SimpleNamespace(scene_options=lambda: [], STILL_LIBRARY={}, STILLS_DIR=HOME,
                                       his_context=lambda: "You are Vintos.", recent_chat=lambda n: "")
A._live_worker = lambda *a, **k: STARTED.append(a)
STARTED.clear()
g = asyncio.run(A.scene_gate("look", "http://stub", {}, slot="t-7", wanted="the two of us at the seawall at night"))
check("asked by his reply, the gate only says how: it cannot say no to what he asked",
      g["decision"] == "YES" and g["kind"] == "together" and g.get("status") == "rendering" and len(STARTED) == 1, g)
check("and the scene is what he wrote when the gate gives none", STARTED[-1][0] == "the two of us at the seawall at night", STARTED)
check("the gate is told he already decided, and what he asked for",
      "You have already decided" in SEEN[-1]["messages"][1]["content"]
      and "the two of us at the seawall at night" in SEEN[-1]["messages"][1]["content"])
A._live_worker = _real_worker

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
