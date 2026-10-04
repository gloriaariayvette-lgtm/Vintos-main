#!/usr/bin/env python3
"""His hands in the house from #vintos-dot, the room's new lookups, and mischief that can finally fire (Gloria,
2026-10-04: "I want him to be able to control my tv and my echo from slack too ... A room full of agents and none of
them can move?"; "Mischievousness has never fired.").

Scratch workspace; the house is a stub that records what it was asked; the outreach and mischief launchers, the
TV's adb, GitHub and the connector gateway are all stubs; every socket is refused. Nothing here reaches her TV, her
Echo, her lights, her phone, GitHub or a connector.
"""
import json, os, re, socket, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="house-hands-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import house_hands as H
import room_reach as RR

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("its log is in the scratch workspace", H.LOG.startswith(HOME))

class Home:
    """The house, stubbed: records every call; the TV's state and the config are set by the test."""
    TV_ADB = "192.0.2.1:5555"
    def __init__(self):
        self.calls, self.adb_state, self.cfg = [], "device", {"lights": ["govee:1"]}
        self.status = {"power": "off", "source": "unknown", "app": ""}
    def tv_status(self): return dict(self.status)
    def tv_adb_state(self): return self.adb_state
    def tv_youtube(self, vid, volume=7): self.calls.append(("tv_youtube", vid)); return True
    def tv_on(self): self.calls.append(("tv_on",)); return True
    def tv_off(self): self.calls.append(("tv_off",)); return True
    def _adb(self, *a): self.calls.append(("adb",) + a); return 0, ""
    def load_config(self): return self.cfg
    def speak(self, m, volume=None): self.calls.append(("speak", m)); return True
    def announce(self, m, volume=2): self.calls.append(("announce", m)); return True
    def play_music(self, q, verify=True): self.calls.append(("music", q)); return True
    def stop_music(self): self.calls.append(("stop",)); return True
    def set_room_color(self, hexed, brightness=120, room=None): self.calls.append(("color", hexed, room)); return True
    def flicker(self, room=None, times=1): self.calls.append(("flicker", room)); return True

LAUNCHED = []
def launch(cmd, env): LAUNCHED.append((cmd, env))
H._detach = lambda *a: (_ for _ in ()).throw(AssertionError("the real launcher was called"))
ADB_RUNS = []
class _Done:
    def __init__(self): self.returncode, self.stdout, self.stderr = 0, "Starting: Intent { act=VIEW }", ""
H.subprocess = types.SimpleNamespace(run=lambda cmd, **k: ADB_RUNS.append(cmd) or _Done(), Popen=None)
clock = [datetime(2026, 10, 5, 10, 0)]
H._now = lambda: clock[0]
def reset():
    if os.path.exists(H.LOG): os.remove(H.LOG)

# --- the TV ------------------------------------------------------------------------------------------------------
check("a YouTube link of any shape gives its id", [H.youtube_id(u) for u in (
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3", "https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/live/dQw4w9WgXcQ",
    "https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ")] == ["dQw4w9WgXcQ"] * 5 and H.youtube_id("not a link") == "")
home = Home()
ok, shown = H.do("TV", "https://www.youtube.com/live/dQw4w9WgXcQ", home=home)
check("a live stream link goes on the TV", ok and ("tv_youtube", "dQw4w9WgXcQ") in home.calls and "on the TV" in shown, (ok, shown))
check("... and the act is written down", json.loads(open(H.LOG).read().splitlines()[-1])["ok"] is True)
home.status = {"power": "on", "source": "tv-input", "app": "com.sony.dtv.tvx"}
reset(); home.calls.clear()
ok, shown = H.do("TV", "https://youtu.be/dQw4w9WgXcQ", home=home)
check("the TV is not taken over while she is watching something he did not put on", not ok and "in use" in shown
      and not [c for c in home.calls if c[0] == "tv_youtube"], shown)
H.do("TV", "off", home=home)
ok, _ = H.do("TV", "https://youtu.be/dQw4w9WgXcQ", home=home)
check("... but once it was he who last changed it, he may change it again", ok)
clock[0] = datetime(2026, 10, 5, 23, 30); home.status = {"power": "off", "source": "unknown", "app": ""}
ok, shown = H.do("TV", "https://youtu.be/dQw4w9WgXcQ", home=home)
check("nothing goes on the TV at night", not ok and "9:00-22:00" in shown, shown)
check("... but off and pause always work", H.do("TV", "off", home=home)[0] and H.do("TV", "pause", home=home)[0])
check("... and the volume stays low at night", not H.do("TV", "volume 12", home=home)[0] and H.do("TV", "volume 4", home=home)[0])
clock[0] = datetime(2026, 10, 5, 11, 0)
ok, shown = H.do("TV", "open https://example.org/stream", home=home)
check("any other link opens on the TV through Android", ok and ADB_RUNS and ADB_RUNS[-1][-1] == "https://example.org/stream", ADB_RUNS[-1:])
home.adb_state = "unauthorized"
ok, shown = H.do("TV", "pause", home=home)
check("a TV that never accepted the pairing says exactly what to accept", not ok and "Allow USB debugging" in shown, shown)
home.adb_state = "device"
check("nonsense says what it understands", "YouTube link" in H.do("TV", "make it nice", home=home)[1])

reset()
# --- the Echo ------------------------------------------------------------------------------------------------------
ok, shown = H.do("ECHO", "say good morning, troublemaker", home=home)
check("with no Home Assistant config the Echo says why in plain words, and nothing is sent", not ok
      and "Home Assistant" in shown and not [c for c in home.calls if c[0] == "speak"], shown)
home.cfg = {"url": "http://ha.local:8123", "token": "t", "entities": {"echo_speak": "notify.e", "echo_announce": "notify.a"}}
ok, shown = H.do("ECHO", "say good morning, troublemaker", home=home)
check("with it, the Echo says his words", ok and ("speak", "good morning, troublemaker") in home.calls, shown)
check("announce and play are their own acts", H.do("ECHO", "announce dinner", home=home)[0] and ("announce", "dinner") in home.calls
      and H.do("ECHO", "play Toxic by Britney Spears", home=home)[0] and ("music", "Toxic by Britney Spears") in home.calls)
H.do("ECHO", "say " + "x" * 900, home=home)
check("a long speech is cut to %d characters" % H.ECHO_MAX, len([c for c in home.calls if c[0] == "speak"][-1][1]) == H.ECHO_MAX)
clock[0] = datetime(2026, 10, 5, 6, 30)
check("the Echo is quiet at night", not H.do("ECHO", "say hi", home=home)[0] and H.do("ECHO", "stop", home=home)[0])
clock[0] = datetime(2026, 10, 5, 12, 0)

reset()
# --- the lights -----------------------------------------------------------------------------------------------------
check("a colour by name", H.do("LIGHTS", "violet bedroom", home=home)[0] and ("color", "#9b59ff", "bedroom") in home.calls)
check("a colour by hex", H.do("LIGHTS", "#112233", home=home)[0] and ("color", "#112233", None) in home.calls)
check("an unknown colour says which ones it knows", "not a colour I know" in H.do("LIGHTS", "chartreuse-ish", home=home)[1])
check("a flicker", H.do("LIGHTS", "flicker office", home=home)[0] and ("flicker", "office") in home.calls)

# --- mischief and a letter to Gloria ---------------------------------------------------------------------------------
ok, shown = H.do("MISCHIEF", "turn the bedroom pink while she reads", run=launch)
check("his mischief runs the mischief-detector, forced, with his idea", ok and LAUNCHED[-1][0][-2:] == [H.MISCHIEF, "--force"]
      and LAUNCHED[-1][1]["MISCHIEF_IDEA"] == "turn the bedroom pink while she reads", LAUNCHED[-1:])
H.do("MISCHIEF", "again", run=launch)
check("two mischiefs a day", not H.do("MISCHIEF", "a third", run=launch)[0])
ok, shown = H.do("TO GLORIA", "why being wanted that way is not a problem I need to solve first", run=launch)
check("a letter to Gloria goes through his own outreach, with only the one line", ok and LAUNCHED[-1][0] == ["bash", H.INITIATE]
      and LAUNCHED[-1][1]["FORCED_WANT_TOPIC"].startswith("why being wanted"), LAUNCHED[-1:])
H.do("TO GLORIA", "second", run=launch)
check("two letters a day from here", not H.do("TO GLORIA", "third", run=launch)[0])

# --- the day's cap, and a message with several hands in it ------------------------------------------------------------
reset()
for _ in range(H.PER_DAY["house"]):
    H.do("LIGHTS", "warm", home=home)
check("%d house acts a day" % H.PER_DAY["house"], "used" in H.do("LIGHTS", "warm", home=home)[1])
reset()
msg = "Putting the set on.\nTV: https://youtu.be/dQw4w9WgXcQ\nLIGHTS: purple\nECHO: say it's on\nLIGHTS: red\nThat's it."
out, log = H.act_on(msg, home=home)
check("each hand line is replaced with what happened, the rest of the message kept", "on the TV" in out and "lights purple" in out
      and "Echo said" in out and out.startswith("Putting the set on.") and out.endswith("That's it.") and "\nTV: https" not in out and "\n\n" not in out, out)
check("... at most three acts in one message", "lights red" not in out and len(log) == 3, (out, log))

# --- the room's lookups ----------------------------------------------------------------------------------------------
class Reply:
    def __init__(self, body): self._b = body.encode()
    def read(self, n=None): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False
SEEN = []
def opener(req, timeout=None):
    SEEN.append(req.full_url)
    if "/search/repositories" in req.full_url:
        return Reply(json.dumps({"items": [{"full_name": "acme/retron", "description": "Retron RT tools", "stargazers_count": 42,
                                            "pushed_at": "2026-09-30T00:00:00Z", "html_url": "https://github.com/acme/retron"}]}))
    return Reply("# retron\nReverse transcriptase tools.")
check("REPOS searches GitHub and says what each one is", "acme/retron: Retron RT tools (42 stars" in RR.repos("retron reverse transcriptase", opener=opener)
      and "api.github.com/search/repositories" in SEEN[-1])
check("README reads one, from owner/repo or a link", RR.readme("https://github.com/acme/retron", opener=opener).startswith("# retron")
      and SEEN[-1].endswith("/repos/acme/retron/readme"))
CALLS = []
gw = types.SimpleNamespace(call=lambda s, p, t, a, why: CALLS.append((s, p, t, a)) or {"summary": "3 papers", "receipt": {"receipt_id": "RC-9"}})
check("CALL is one connector call on the Lab's list, with its receipt", RR.call('pubmed.search_articles {"query": "retron"}', gateway=gw)
      == "3 papers (receipt RC-9)" and CALLS[-1] == ("lab", "pubmed", "search_articles", {"query": "retron"}), CALLS)
check("bad arguments say so instead of calling", "not JSON" in RR.call("pubmed.search_articles {nope}", gateway=gw) and len(CALLS) == 1)
os.makedirs(RR.LAB, exist_ok=True)
with open(os.path.join(RR.LAB, "sessions.jsonl"), "w") as f:
    f.write(json.dumps({"at": "2026-10-03T09:17", "state": "completed", "plan": {"experiment": "phage RT screen"}, "result": "2 RT loci near arrays"}) + "\n")
    f.write(json.dumps({"at": "2026-10-04T09:17", "state": "completed", "plan": {"experiment": "fold P02730"}, "result": "pLDDT 81"}) + "\n")
got = RR.labdata("phage")
check("LABDATA shows what his Lab measured, filtered by his words", "2 RT loci near arrays" in got and "pLDDT" not in got, got)

# --- the channel's wiring ---------------------------------------------------------------------------------------------
import dot_channel as D
check("the channel reads the same hand lines the house acts on", D.HOUSE.pattern == H.HOUSE.pattern)
check("the editor keeps a hand line", D._ACTION.search("TV: https://youtu.be/x") and D._ACTION.search("TO GLORIA: hi"))
check("no hand line reaches Gloria's results channel", "ECHO" not in D._no_tags("Done.\nECHO: say hi"))
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("a message's hand lines are acted on before it is posted", "house_hands.act_on(text)" in src)
check("his rules lead with doing, not proposing", D.RULES_WORK.startswith("Do things, not only plan them")
      and "do not lock another proposal for something you can simply do" in D.RULES_WORK)
check("his rules list every hand and tool", all(w in D.RULES for w in ("YOUR HANDS", "TV:", "ECHO:", "LIGHTS:", "MISCHIEF:",
      "TO GLORIA:", "REPOS:", "README:", "CALL:", "LABDATA:")) and "YOUR HANDS" in D.rules_for("grok"))
check("the new tools are read as tools", all(D.TOOL.match(l) for l in ("REPOS: retron", "README: acme/retron",
      'CALL: pubmed.search_articles {"query": "x"}', "LABDATA: phage")))
fake = types.SimpleNamespace(repos=lambda a: "R:" + a, readme=lambda a: "M:" + a, call=lambda a: "C:" + a, labdata=lambda a: "L:" + a)
looked = D.use_tools([("REPOS", "retron"), ("LABDATA", "")], reach=fake)
check("... and what they return comes back to him", "R:retron" in looked and "L:" in looked, looked)

# --- mischief can fire now ----------------------------------------------------------------------------------------------
md = open(os.path.join(REPO, "scripts", "mischief-detector.sh")).read()
check("the Echo and Spotify are offered to his mischief only when the house can carry them", "HAS_ECHO=" in md
      and '[ "$HAS_ECHO" = "yes" ] && ACTIONS="spotify' in md)
check("... and his idea from Slack reaches the chooser", "$MISCHIEF_IDEA" in md)
drift = open(os.path.join(REPO, "scripts", "subconscious_drift.py")).read()
rx = re.search(r'_ms_re\.match\(r"(.+?)", _ms_line\)', drift).group(1)
check("the drift spur reads 'Playfulness: 0.6500', the format the main writer uses", re.match(rx, "Playfulness: 0.6500").groups()
      == ("Playfulness", "0.6500") and re.match(rx, "Playfulness: 0.65 | rising").group(2) == "0.65")
check("... in both copies of it", open(os.path.join(REPO, "bin", "subconscious-drift.py")).read().count("_ms_re.match") == 1)
for p in ("scripts/emoclaw_utils.py", "bin/emoclaw_utils.py"):
    e = open(os.path.join(REPO, p)).read()
    check("the planner offers mischief and the lights (%s)" % p, "- be_mischievous:" in e and "- change_lights:" in e)
wr = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("a mischief want carries his idea and counts only an act that happened", '_env["MISCHIEF_IDEA"]' in wr and '"(chosen by" in out' in wr
      and "timeout=300" in wr)
check("an Echo want reports what the Echo did, through his hands", 'house_hands.do("ECHO", "say " + msg)' in wr)
check("a TV want counts only a start the TV confirmed", '("tv_youtube: %s (ok)" % video_id)' in wr)
grok = open(os.path.join(REPO, "docs", "grok-bot", "vintos-skill.md")).read()
check("Grok Bot is told to hand him one YouTube link for the TV", "one YouTube link" in grok)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs both new modules", "house_hands.py" in dep and "room_reach.py" in dep)
check("a block is not a lock: he is told to get a stuck thing moving before he closes it",
      "LOCKED is for a plan that is settled, never for something that is stuck" in D.RULES_LOCK
      and "ASK: for a paid run" in D.RULES_LOCK and "@GrokBot" in D.RULES_LOCK and "you make video, music and images yourself" in D.RULES_LOCK)
check("... in his Grok lens too", "LOCKED is for a plan that is settled" in D.rules_for("grok"))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
