#!/usr/bin/env python3
"""Review items 211, 233, 240, 252, 253, 265, 278, 287, 301, 321 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time, hashlib

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p58-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "art"), exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 252: the checkpoint carries findings, blocker, next step ---")
CP = load("want_checkpoints", os.path.join(REPO, "scripts", "want_checkpoints.py")); CP.MEM = MEM; CP.STORE = os.path.join(MEM, "pursuit-checkpoints.json"); CP.WANTS = os.path.join(MEM, "current-wants.json")
json.dump([{"id": "W1", "want": "paint the fig", "steps": [{"capability": "introspect", "status": "completed"}, {"capability": "make_art", "note": "warm light", "status": "pending"}], "current_step_index": 1,
            "step_history": [{"step": 0, "capability": "introspect", "findings": "I keep returning to the table"}]}], open(CP.WANTS, "w"))
cid = CP.create("paint the fig", "make_art", "blocked", "renderer offline")
c = json.load(open(CP.STORE))[0]
check("findings, blocker and next step are on the checkpoint", c["findings"].startswith("I keep returning") and c["blocker"] == "renderer offline" and c["next_step"].startswith("make_art: warm light"), c)

print("\n--- 253: pull grows from new occasions only ---")
CD = load("curiosity_debt", os.path.join(REPO, "scripts", "curiosity_debt.py"))
for a in dir(CD):
    v = getattr(CD, a)
    if isinstance(v, str) and a.isupper() and ".vintos" in v: setattr(CD, a, os.path.join(MEM, os.path.basename(v)))
CD.MEM = MEM
CD.record("why does she like the fig?", pull=0.5, source="chat", occasion="T1")
CD.record("why does she like the fig?", pull=0.5, source="chat", occasion="T1"); CD.record("why does she like the fig?", pull=0.5, source="chat", occasion="T1")
d = CD._load()[0]
check("the same occasion three times: pull unchanged, one occasion", abs(d["pull"] - 0.5) < 1e-9 and d["occasions"] == ["T1"], d)
CD.record("why does she like the fig?", pull=0.5, source="chat", occasion="T2")
d = CD._load()[0]
check("a new occasion raises the pull and is kept", abs(d["pull"] - 0.62) < 1e-9 and d["occasions"] == ["T1", "T2"])

print("\n--- 278: a failed validation is not evidence ---")
AG = load("want_artifact_guard", os.path.join(REPO, "scripts", "want_artifact_guard.py")); AG.MEMORY = MEM; AG.LEDGERS = [os.path.join(MEM, "art", "gallery.json")]
json.dump([{"want_id": "W1", "image": "a.png", "validated": {"ok": False, "how": "missing"}}, {"want_id": "W2", "image": "b.png", "validated": {"ok": True, "how": "magic:png"}}, {"want_id": "W3", "image": "c.png"}], open(AG.LEDGERS[0], "w"))
check("validated false is not proof; validated true and legacy entries are", AG._ledger_has("W1") is False and AG._ledger_has("W2") and AG._ledger_has("W3"))

print("\n--- 287: revealed bytes match the prepared digest ---")
av = src("scripts/atelier-visit.py")
check("the reveal hashes the bytes and refuses a mismatch, recording it", "do not match the prepared digest" in av and "atelier-reveal-refusals.jsonl" in av)
check("bytes_verified is the real comparison, not the presence of a digest", '"bytes_verified": _verified' in av and 'bool((manifest or {}).get("sha256"))' not in av)
check("a named digest with no bytes on disk is refused, never 'verified'", "the bytes are not on disk" in av)

print("\n--- 301: a music landing is recorded before the download ---")
DM = load("dream_music", os.path.join(REPO, "bin", "dream-music.py")) if False else None
dm = src("bin/dream-music.py")
check("landing begins before any download, closes after the entry, and pending landings are named", "_landing_begin(tid, d[\"title\"], 0," in dm and "_landing_done(tid, downloaded)" in dm and "def pending_landings" in dm and dm.index("_landing_begin(tid") < dm.index("if dl(t[\"file\"],mp3)"))
check("the twins carry it", dm == src("scripts/dream-music.py"))

print("\n--- 321: a render has an owner and a generation token ---")
AS = load("avatar_stage", os.path.join(REPO, "bin", "avatar_stage.py"))
check("new status carries generation/owner/playback_id; a render starts with a fresh token bound to its slot", set(AS._new_status()) >= {"generation", "owner", "playback_id"} and 'generation=_gen, owner=sid, playback_id=_gen' in src("bin/avatar_stage.py"))

print("\n--- 211: ratings join by identity ---")
HP = load("humor_practice", os.path.join(REPO, "scripts", "humor_practice.py")) if False else None
hp = src("scripts/humor_practice.py")
check("drafts get a joke_id; the rating join prefers the id and falls back to the prefix", '"joke_id": "J-"' in hp and "def _rating_for(joke, ratings, joke_id=None, by_id=None)" in hp and "joke_id=d.get(\"joke_id\"), by_id=by_id" in hp)
check("the rating route accepts joke_id and stores it", 'joke_id = str(body.get("joke_id") or "")' in src("bin/server.py") and '"joke_id": joke_id or None' in src("bin/server.py"))

print("\n--- 233: an ambition completes on its required count ---")
eu = src("scripts/emoclaw_utils.py")
check("fulfilled wants accumulate on the goal; Completed only at wants_required (default 3)", '_need = int(_g.get("wants_required", 3) or 3)' in eu and 'making progress (%d/%d wants fulfilled)' in eu and eu == src("bin/emoclaw_utils.py"))

print("\n--- 240 / 265: a held plan reopens on relevant evidence ---")
PL = load("plan", os.path.join(REPO, "scripts", "plan.py")); PL.MEMORY = MEM; PL.STORE = os.path.join(MEM, "plans.json")
PL._create("gestate", "the fig painting for her birthday", "a finished painting", 30) if hasattr(PL, "_create") else None
rows = PL.load()
if rows and rows[-1].get("kind") == "gestate":
    rows[-1]["root"] = "the fig painting for her birthday"; PL.save(rows)
    out = PL.reopen_on_evidence("she asked about the fig painting again today", source="test")
    rows = PL.load()
    check("evidence naming the root releases the hold as resumed:evidence with the evidence in history", out == ["the fig painting for her birthday"] and rows[-1]["state"] == "resumed" and rows[-1]["history"][-1]["event"] == "resumed:evidence", (out, rows[-1]))
    check("unrelated evidence reopens nothing", PL.reopen_on_evidence("the weather turned") == [])
else:
    check("plan gestate created for the test", False, rows)
check("a fulfilled want reopens the plans it names", "_plan.reopen_on_evidence(text" in src("scripts/want_completion.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
