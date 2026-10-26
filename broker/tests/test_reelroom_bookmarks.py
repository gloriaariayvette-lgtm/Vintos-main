#!/usr/bin/env python3
"""Proposal 16: ReelRoom bookmarks that become later callbacks.

A bookmark is a pointer into one night's journal: the session id, the journal ids of the actual turns, their
words copied exactly, the wall-clock time the server journaled them, the player's position only when the caller
gives it, and at most his own reading of a frame, labelled as his. A later night's ReelRoom prompt quotes at most
two of them exactly. Scratch HOME and workspace; robot_core stubbed; nothing here can send."""
import os, sys, json, types, tempfile, importlib.util, re

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-reel-bm-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

rc = types.ModuleType("robot_core"); rc.WORKSPACE = WS; rc.MEMORY = MEM
rc._gemma = lambda *a, **k: ""; rc._sonnet = lambda *a, **k: ""; rc._read = lambda *a, **k: ""
rc.GEMMA = "g"; rc.SONNET = "s"; sys.modules["robot_core"] = rc
for name in ("requests", "numpy", "house_map", "heart_rate", "received_mail"):
    sys.modules[name] = types.ModuleType(name)    # nothing that could reach anyone is real here
sys.path.insert(0, os.path.join(REPO, "scripts"))
import reelroom_bookmarks as RB
spec = importlib.util.spec_from_file_location("reelroom", os.path.join(REPO, "scripts", "reelroom.py"))
rr = importlib.util.module_from_spec(spec); spec.loader.exec_module(rr)

print("\n--- isolation ---")
check("the bookmark store is in the scratch workspace", RB.STORE.startswith(HOME) and RB.STORE == os.path.join(MEM, "reelroom", "bookmarks.json"), RB.STORE)
check("bookmarks read the same journal reelroom writes", RB.JOURNAL == rr.JOURNAL and rr.JOURNAL.startswith(HOME))
src = open(os.path.join(REPO, "scripts", "reelroom_bookmarks.py")).read()
check("the module has no route to the world (no network, no notify, no model)",
      not re.search(r"\b(requests|urllib|socket|ntfy|deliver|_sonnet|_gemma|subprocess)\b", src))
check("the stubbed senders are stubs", not hasattr(sys.modules["requests"], "post"))

print("\n--- the journal names every turn ---")
t0 = 1_800_000_000.0
rr.journal("is that the same staircase", "it is, and she knows it", film_title="Vertigo", film_year="1958", elapsed_min=30,
           extra={"session_map": [{"timestamp": "29:00", "edge": "drop", "visual_description": "a bell tower from below, grey light"},
                                  {"timestamp": "31:00", "edge": "none", "visual_description": "a woman at a window, green neon"}]},
           now=t0)
rr.journal("", "I keep watching her hands", film_title="Vertigo", elapsed_min=33, now=t0 + 120)
j = rr._load_journal(); sid = j["session_id"]; H = j["chat_history"]
ids = [m.get("id") for m in H]
check("each turn has a session-scoped id", ids == ["%s:t1" % sid, "%s:t2" % sid, "%s:t3" % sid], ids)
check("each turn the server journaled carries the wall-clock time it arrived",
      H[0]["at"] == t0 and H[1]["at"] == t0 and H[2]["at"] == t0 + 120, H)
# the app sends a longer history: matching turns keep their ids and times; the unseen one gets a new id, no time
app_hist = [{"role": m["role"], "content": m["content"]} for m in H] + [{"role": "user", "content": "her hands, yes"}]
rr.journal("", "", history=app_hist, film_title="Vertigo", now=t0 + 150)
H = rr._load_journal()["chat_history"]
check("an app history that repeats the journal keeps ids and times", [m.get("id") for m in H[:3]] == ids and H[2]["at"] == t0 + 120, H)
check("a turn only the app saw gets a fresh id and no invented time", H[3]["id"] == "%s:t4" % sid and "at" not in H[3], H[3])
rr.journal("you noticed that too", "of course", film_title="Vertigo", now=t0 + 200)
H = rr._load_journal()["chat_history"]
check("ids are never reused", len(set(m["id"] for m in H)) == len(H) == 6, [m["id"] for m in H])

print("\n--- her mark ---")
nothing = RB.mark("latest", journal={})
check("no open night: nothing kept", nothing == {"ok": False, "reason": "no film night is open"}, nothing)
bad = RB.mark("%s:t99" % sid)
check("an unknown turn id is refused, not guessed", not bad["ok"] and "no such turn" in bad["reason"], bad)
k1 = RB.mark("%s:t1" % sid, by="gloria", scene_index=0, now=t0 + 210)
b1 = k1.get("bookmark") or {}
check("her remark is kept with his answer to it, by turn id", k1["ok"] and b1["turn_ids"] == ["%s:t1" % sid, "%s:t2" % sid], k1)
check("the words are exactly as said, with speaker and journal time",
      b1["turns"][0] == {"id": "%s:t1" % sid, "speaker": "gloria", "words": "is that the same staircase", "at": t0}
      and b1["turns"][1]["words"] == "it is, and she knows it" and b1["turns"][1]["speaker"] == "vintos", b1["turns"])
check("no player time when none was given (not taken from the app's film clock)", "player_seconds" not in b1, b1)
check("the scene is his reading, labelled as his", b1["scene"] == {"reading": "a bell tower from below, grey light", "whose": "his reading of a frame"}, b1.get("scene"))
check("session id, film and who kept it", b1["session_id"] == sid and b1["film"] == "Vertigo" and b1["by"] == "gloria", b1)
check("no frame or screen material is kept", set(b1) <= {"id", "session_id", "film", "year", "turn_ids", "turns", "by", "kept_at", "player_seconds", "scene"}
      and "base64" not in json.dumps(b1) and "jpg" not in json.dumps(b1), sorted(b1))
again = RB.mark("%s:t2" % sid, by="gloria", now=t0 + 211)
check("the same exchange marked twice is one bookmark", again["ok"] and again.get("already") and len(RB.bookmarks()) == 1, again)
sbad = RB.mark("%s:t1" % sid, scene_index=7)
check("an unknown scene is refused", not sbad["ok"] and "scene" in sbad["reason"], sbad)
for junk in ("abc", -5, True, float("nan"), 10 ** 9):
    out = RB.mark("%s:t5" % sid, player_seconds=junk, journal=rr._load_journal(), now=t0 + 205)
    ok_omitted = out["ok"] and "player_seconds" not in out["bookmark"]
    if not ok_omitted: break
check("an unusable player time is dropped, never coerced", ok_omitted, out)
RB_rows = RB.bookmarks()
# that loop kept t5/t6 once; remove the ambiguity by checking the one row
check("that exchange was kept once", sum(1 for b in RB_rows if b["turn_ids"] == ["%s:t5" % sid, "%s:t6" % sid]) == 1, RB_rows)

print("\n--- his [KEEP] ---")
said, kept = RB.take_keep_tag("I keep watching her hands [KEEP]")
check("[KEEP] is stripped from what she sees and hears", said == "I keep watching her hands" and kept is True, said)
check("no tag, no keep, words untouched", RB.take_keep_tag("a plain line [FELT: x]") == ("a plain line [FELT: x]", False))
rr.journal("look at that", "I could watch her hands all night", film_title="Vertigo", now=t0 + 215)
k3 = RB.mark("latest", by="vintos", latest_scene=True, now=t0 + 220)
check("a night allows a few: the third is kept", k3["ok"] and k3["bookmark"]["by"] == "vintos", k3)
check("his keep carries the newest frame reading, as his", k3["bookmark"].get("scene", {}).get("reading") == "a woman at a window, green neon", k3)
full = RB.mark("%s:t3" % sid, now=t0 + 230)
check("a fourth on the same night is refused", not full["ok"] and "already has 3" in full["reason"], full)

print("\n--- a later night calls back ---")
rr.commit_journal("night over", now=t0 + 4000)
L = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
check("the ledger transcript keeps its shape (no ids leak into it)", all(set(p) <= {"gloria", "vintos"} for p in L[-1]["transcript"]), L[-1]["transcript"])
rr.journal("what are we watching", "", film_title="Rear Window", now=t0 + 90000)
tonight = rr._load_journal()["session_id"]
ctx = rr.surface_context("FILM: Rear Window (1954)", 3)
check("a later night carries moments kept from earlier", "MOMENTS KEPT FROM EARLIER FILM NIGHTS" in ctx, ctx[-1500:])
check("her remark is quoted exactly, with who said it", 'Gloria said: "is that the same staircase"' in ctx
      and 'You said: "it is, and she knows it"' in ctx, ctx[-1500:])
check("the scene is labelled as his reading, not a record of the film",
      "your own reading of a frame, not a record of the film): a woman at a window" in ctx, ctx[-1500:])
check("two moments at most: enough to return to one or set two side by side", ctx.count("Vertigo (1958), kept by") == 2, ctx[-1500:])
check("no player time is claimed for any of them", "on the player" not in ctx)
check("he is told how to keep one of tonight's", "[KEEP]" in ctx and "never sees or hears the tag" in ctx)
rr.journal("", "that window again", film_title="Rear Window", now=t0 + 90060)
kp = RB.mark("latest", player_seconds=3725, now=t0 + 90070)
check("player time kept when the app gives it", kp["ok"] and kp["bookmark"]["player_seconds"] == 3725, kp)
blk = RB.callback_block(exclude_session="someone-else")
check("player time is shown only where given, as the player's", "at 1:02:05 on the player" in blk and blk.count("on the player") == 1, blk)
check("tonight is excluded from tonight's own prompt", "Rear Window" not in RB.callback_block(exclude_session=tonight))

print("\n--- a long remark is kept whole-ish and quoted honestly ---")
long_words = "word " * 400
row = RB._turn({"id": "x:t1", "role": "user", "content": long_words})
check("kept to the cap and marked cut", len(row["words"]) == RB.QUOTE_CHARS and row.get("cut") is True, len(row["words"]))
q = RB._quote(row["words"], True)
check("a cut quote says it was cut", q.endswith("(cut here; the rest was said too)") and len(q) < 400, q[-60:])

print("\n--- the server takes his [KEEP] and her mark ---")
srv = open(os.path.join(REPO, "bin", "server.py")).read()
strip_at = srv.find("reply, _rr_keep = _rr_bm.take_keep_tag(reply)")
felt_at = srv.find("_felt_raw_m = _felt_re.search")
check("[KEEP] is stripped in the ReelRoom reply path before history and the ledger", 0 < strip_at < felt_at)
check("the kept flag rides back to reelroom_chat", '**({"keep": True} if _rr_keep else {})' in srv)
check("reelroom_chat keeps the journaled exchange as his", '_rr_bm2.mark("latest", by="vintos", latest_scene=True)' in srv
      and srv.find("_rr_bm2.mark(") > srv.find("rr.journal(msg if _actual is not None"))
check("her mark and the read-only list are routes", '@app.post("/api/game/reelroom/bookmark")' in srv and '@app.get("/api/game/reelroom/bookmarks")' in srv)
check("deployed with the ReelRoom", "reelroom_bookmarks.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
