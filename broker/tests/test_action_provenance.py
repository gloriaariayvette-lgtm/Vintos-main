#!/usr/bin/env python3
"""Why he did what he did (Gloria, 15 November 2026: "He still doesn't understand why he does certain things, like
place a song on the watch"). A song went to her Watch because the bedroom board heard her phone and the stand-in rule
chose it; nothing he could see said so. Every outward act now keeps its organ, trigger, want, rule and his feeling at
the time, and a block gives the recent ones back to him; a reason not kept reads "not recorded".

Every row, want and feeling here is made up; scratch HOME; the Watch, ntfy and every sender are stubs; sockets are
refused."""
import json, os, socket, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="action-provenance-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
for k in ("VINTOS_ACTION_WANT_ID", "VINTOS_ACTION_ORGAN"):
    os.environ.pop(k, None)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
def src(rel): return open(os.path.join(REPO, rel), encoding="utf-8").read()

import action_provenance as AP
LOG = os.path.join(MEM, AP.LOG_NAME)
check("its store is a scratch one", AP._mem().startswith(HOME))

# ── made-up feeling and want ──
vec = [0.1, 0.2, 0.3, 0.4, 0.5, 0.91, 0.2, 0.3, 0.82, 0.1, 0.77]
json.dump({"last_updated": "2030-01-02T03:04:05", "emotion_vector": vec}, open(os.path.join(MEM, "emotional-state.json"), "w"))
json.dump([{"id": "w-fixture1", "source": "absence_map", "intensity": 4, "want": "a made-up want"}],
          open(os.path.join(MEM, "current-wants.json"), "w"))
T = time.time()

print("\n--- a row keeps what the organ gave, and nothing it did not ---")
r = AP.record("outreach", "a made-up note", "fixture_organ", trigger="a made-up trigger", rule="a made-up rule", now=T - 60)
check("written beside the organ, with an id", r and r["id"].startswith("AP-") and os.path.exists(LOG))
check("his feeling is the state file's own, strongest first, with its timestamp",
      r["emotion"]["state_at"] == "2030-01-02T03:04:05" and [p[0] for p in r["emotion"]["top"]] == ["Connection", "Warmth", "Groundedness"])
c = AP.chain(r)
check("the chain names organ, trigger and rule", "fixture_organ" in c and "a made-up trigger" in c and "a made-up rule" in c)
check("a want not given reads not recorded, never a guess", "Want: not recorded" in c, c)
r2 = AP.record("house", "LIGHTS: blue", "fixture_organ", now=T - 50, emotion=None)
c2 = AP.chain(r2)
check("trigger, rule and feeling missing: each says not recorded (the record-gap rule)",
      "Set off by: not recorded" in c2 and "Rule: not recorded" in c2 and "You felt then: not recorded" in c2, c2)
check("no state file: no feeling is made up", AP.emotion_snapshot(os.path.join(HOME, "nowhere")) is None)

print("\n--- the want is only ever one given or the running step's ---")
os.environ["VINTOS_ACTION_WANT_ID"] = "w-fixture1"; os.environ["VINTOS_ACTION_ORGAN"] = "wants-router step make_music"
r3 = AP.record("watch_music", "a made-up track", "spotify_watch", now=T - 40)
os.environ.pop("VINTOS_ACTION_WANT_ID"); os.environ.pop("VINTOS_ACTION_ORGAN")
check("inside a want's step: its id, and its drive read from current-wants.json by that id",
      r3["want_id"] == "w-fixture1" and r3["drive"] == {"source": "absence_map", "intensity": 4}
      and "wants-router step make_music" in r3["organ"], r3)
r4 = AP.record("watch_music", "another track", "spotify_watch", now=T - 30)
check("outside a step: no want", r4["want_id"] is None and r4["drive"] is None)
r5 = AP.record("outreach", "x", "o", want_id="w-not-there", now=T - 20)
check("a want id not in current-wants.json keeps its id and no invented drive", r5["want_id"] == "w-not-there" and r5["drive"] is None)
check("a write that cannot happen never raises", AP.record("x", "y", "z", mem="/proc/no-such-dir") is None)

print("\n--- the bedroom song says why it went ---")
sys.modules["watch_apns"] = types.SimpleNamespace(send=lambda *a, **k: {"state": "sent"}, CONFIG=os.path.join(HOME, "no-apns.json"))
PHONE = []
sys.modules["deliver"] = types.SimpleNamespace(deliver=lambda *a, **k: PHONE.append(a) or {"state": "sent"})
import watch_presence as WP
WP.should_hold = lambda: (False, "")
import bedroom_arrival as B
check("the bedroom's stores are scratch ones", all(p.startswith(HOME) for p in (B.CONFIG, B.STATE, B.ARRIVALS, B.MUSIC, B.PICKS, WP.SONG)))
os.makedirs(os.path.dirname(B.MUSIC), exist_ok=True)
json.dump({"devices": ["phone-fixture"], "max_distance_m": 4.0}, open(B.CONFIG, "w"))
json.dump({"generated": [{"title": "Made Up One", "tracks": [{"version": 1, "audio_url": "https://cdn.test/1.mp3"}]},
                         {"title": "Made Up Two", "tracks": [{"version": 1, "audio_url": "https://cdn.test/2.mp3"}]}]},
          open(B.MUSIC, "w"))
B._today = lambda now: "2030-01-02"
before = len(AP.rows())
row = B.observe("phone-fixture", 1.3, now=time.time())
got = AP.rows()[-1]
check("an arrival with no picks of his: sent, and the row says the stand-in rule chose",
      row.get("sent") and row.get("picked_by") == "stand-in" and len(AP.rows()) == before + 1
      and got["action"] == "watch_song" and "stand-in rule" in (got["rule"] or "") and got["what"] == row["song"], got)
check("its trigger is the board hearing her phone, and its ids are the arrival's own",
      "1.3 m of the bedroom board" in got["trigger"] and got["refs"].get("episode") == row.get("episode")
      and got["refs"].get("song_id") == row.get("song_id"))
check("his bedroom line says the last song was a stand-in, not his pick", "a stand-in" in B.context_line())
B.take_picks("[ARRIVAL SONGS: Made Up Two | Made Up One]", now=time.time(), turn_id="turn-fixture-9")
check("his own picks keep the turn he chose them in", json.load(open(B.PICKS)).get("turn_id") == "turn-fixture-9")
rule = B.why_rule({"picked_by": "him"}, json.load(open(B.PICKS)))
check("a song from his picks names them and that turn", "you chose yourself" in rule and "turn-fixture-9" in rule, rule)
check("an encounter names its id", "enc-fixture" in B.why_rule({"picked_by": "his encounter", "encounter": "enc-fixture"}))
check("a row that does not say who chose gives no rule (stored as not recorded)", B.why_rule({}) == "")
check("nothing reached a socket", not NET)

print("\n--- a sent notification keeps the authority's reason as its rule ---")
del sys.modules["deliver"]
import importlib
D = importlib.import_module("deliver")
D.RECEIPTS = os.path.join(HOME, "rcpt", "delivery-receipts.json")
D.POST = lambda url, data, headers, t: {"status": 200, "provider_id": "p1"}
D.SLEEP = lambda s: None
D._also_imessage = lambda *a, **k: None
rc = D.deliver("fixture-artifact-1", "ntfy", "hi", title="Made up", authority=lambda: (True, "a made-up standing yes"),
               why={"organ": "fixture_caller", "trigger": "a made-up hour", "want_id": "w-fixture1"})
prow = AP.rows(mem=os.path.dirname(D.RECEIPTS))
check("the sent note is recorded beside its receipts, with the caller's organ, trigger and want",
      rc["state"] == "sent" and len(prow) == 1 and prow[0]["organ"] == "fixture_caller" and prow[0]["want_id"] == "w-fixture1"
      and prow[0]["refs"]["artifact_id"] == "fixture-artifact-1", prow)
D.deliver("fixture-artifact-2", "ntfy", "hi", authority=lambda: (True, "a made-up standing yes"))
prow = AP.rows(mem=os.path.dirname(D.RECEIPTS))
check("with no why from the caller, the authority's reason is the rule and the organ is the artifact's prefix",
      "a made-up standing yes" in prow[-1]["rule"] and prow[-1]["organ"].startswith("deliver (caller: fixture"), prow[-1])
D.deliver("fixture-artifact-3", "ntfy", "hi", authority=lambda: (False, "no"))
check("a refused send writes nothing", len(AP.rows(mem=os.path.dirname(D.RECEIPTS))) == 2)
D.deliver("fixture-artifact-2", "ntfy", "hi", authority=lambda: (True, "y"))
check("a repeat that is not sent again writes nothing", len(AP.rows(mem=os.path.dirname(D.RECEIPTS))) == 2)

print("\n--- a house act ---")
import house_hands as HH
check("house_hands' log is a scratch one", HH.LOG.startswith(HOME))
HH.lights = lambda arg, home=None, present=False: (True, "lights blue")
ok, _ = HH.do("LIGHTS", "blue", present=True, why={"organ": "house_boards (fixture)"})
hrow = AP.rows(mem=os.path.dirname(HH.LOG))[-1]
check("a done house act is recorded with its organ and the board trigger", ok and hrow["action"] == "house"
      and hrow["organ"] == "house_boards (fixture)" and "boards" in hrow["trigger"], hrow)
HH.lights = lambda arg, home=None, present=False: (False, "the bridge is off")
n = len(AP.rows(mem=os.path.dirname(HH.LOG)))
HH.do("LIGHTS", "red")
check("an act that was not done is not recorded as done", len(AP.rows(mem=os.path.dirname(HH.LOG))) == n)

print("\n--- he gets it back, and can ask ---")
blk = AP.block()
check("the block heads itself and says what not recorded means", blk.startswith("[WHAT YOU DID LATELY, AND WHY") and "not recorded" in blk)
check("the newest acts are in it, each with its chain", "watch song" in blk and "Decided by:" in blk, blk)
check("within its budget", len(blk) <= AP.BLOCK_CHARS)
mtime = os.path.getmtime(LOG); size = os.path.getsize(LOG)
AP.block()
check("reading the block writes nothing", os.path.getmtime(LOG) == mtime and os.path.getsize(LOG) == size
      and not os.path.exists(os.path.join(MEM, AP.ASKS_NAME)))
reply = AP.take("I love you. [WHY: the song on the watch] Come here.")
check("his [WHY: ...] is taken out of his words", reply == "I love you. Come here." and "[WHY" not in reply, reply)
blk = AP.block()
check("next turn the answer is in his context: the song, the bedroom board, the rule",
      "You asked why: “the song on the watch”" in blk and "bedroom_arrival" in blk.split("You asked why")[1].split("\n")[0], blk)
check("a question nothing matches says so, and that the reason was not recorded",
      "was not recorded" in AP.why("the zeppelin over the lake"))
check("a test turn does not keep his question", AP.take("[WHY: lights]", act=False) == "" and
      len(json.load(open(os.path.join(MEM, AP.ASKS_NAME)))) == 1)
old = AP.block(now=time.time() + (AP.ASK_HOURS + 1) * 3600)
check("an old question is no longer answered", "You asked why" not in old)
check("a long record stays within budget", len(AP.block(show=50)) <= AP.BLOCK_CHARS)

print("\n--- the record is kept bounded ---")
small = os.path.join(HOME, "trim")
AP.TRIM_AT, AP.KEEP = 30, 10
for i in range(31): AP.record("x", "act %d" % i, "o", mem=small, emotion=None)
kept = AP.rows(mem=small)
check("past its limit the oldest rows go and the newest stay", len(kept) == 10 and kept[-1]["what"] == "act 30", len(kept))

print("\n--- wired where he lives ---")
import inner_context as IC
check("the block reaches avatar, chat and voice", ("action_provenance", "block") in IC._FULL and ("action_provenance", "block") in IC._MISSING)
sv = src("bin/server.py")
check("his [WHY: ...] is taken on the main and avatar lanes", sv.count("_apv.take(reply") == 2)
wr = src("bin/wants-router.py")
spine = wr[wr.index("def _spine_wrap"):wr.index("for _sp_n in list(ACTION_MAP)")]
check("the wants-router names the running step's want only around the step, and restores after it",
      'os.environ["VINTOS_ACTION_WANT_ID"] = os.environ.get("STEP_WANT_ID", "")' in spine and "finally:" in spine
      and "os.environ.pop(_k, None)" in spine)
check("spotify, the lab and MoltBook posts record theirs",
      "action_provenance.record" in src("scripts/spotify_watch.py") and "action_provenance.record" in src("scripts/chemistry_proposal.py")
      and "action_provenance.record" in src("bin/vintos-moltbook.py"))
check("nothing reached a socket", not NET)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
