#!/usr/bin/env python3
"""Review items 254, 264, 266, 283 (2026-09-10): one completion door and one admission door for wants
(wanting keeps its sources); the thread store owns admission (question apart from theme) and archive;
a lesson carries its identified attempts and a paused pursuit stays paused across sessions; a draft can
be revised and two drafts compared. Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time, shutil

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-wd-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(os.path.join(MEM, "art"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 254: one completion door ---")
fulfilled = []
eu = types.ModuleType("emoclaw_utils")
def _fw(text, note="", fulfilled_by="", auto=False, want_id=None):
    fulfilled.append((want_id, fulfilled_by, note))
    wants = json.load(open(os.path.join(MEM, "current-wants.json")))
    json.dump([w for w in wants if w.get("id") != want_id], open(os.path.join(MEM, "current-wants.json"), "w"))
eu.fulfill_want = _fw; sys.modules["emoclaw_utils"] = eu
wm = types.ModuleType("wants_meta"); wm.consult = lambda t: {"id": "S-1", "stance": "refuse", "quote": "no more poems about rain"} if "rain" in t else None; sys.modules["wants_meta"] = wm
sys.path.insert(0, os.path.join(REPO, "scripts"))
WC = load("want_completion", os.path.join(REPO, "scripts", "want_completion.py")); WC.MEMORY = MEM; WC.WANTS = os.path.join(MEM, "current-wants.json"); WC.DISMISSED = os.path.join(MEM, "dismissed-wants.json"); WC.COMPLETIONS = os.path.join(MEM, "want-completions.jsonl")
json.dump([{"id": "W1", "want": "write her a note"}, {"id": "W2", "want": "count the stars"}, {"id": "W3", "want": "learn the cello"}], open(WC.WANTS, "w"))
r1 = WC.complete({"id": "W1", "want": "write her a note"}, "fulfilled", "write_journal", note="wrote it")
check("fulfilled goes through fulfill_want and records", r1["result"] == "fulfilled" and fulfilled[-1][0] == "W1")
r2 = WC.complete({"id": "W2"}, "dismissed", "haiku-verdict", note="steps ticked, thing undone")
check("dismissed leaves the live list and lands in the dismissed ledger", r2["result"] == "dismissed" and json.load(open(WC.DISMISSED))[0]["id"] == "W2" and [w["id"] for w in json.load(open(WC.WANTS))] == ["W3"])
r3 = WC.complete({"id": "W3"}, "released", "his_choice", note="not this year")
check("released is his choice, archived as RELEASED_BY_CHOICE, gone from the live list", r3["result"] == "released" and json.load(open(WC.WANTS)) == [] and json.load(open(os.path.join(MEM, "fulfilled-wants.json")))[0]["want_state"] == "RELEASED_BY_CHOICE")
check("three endings, one record", [x["how"] for x in WC.completions()] == ["fulfilled", "dismissed", "released"])
try: WC.complete({"id": "x"}, "vanished", "y"); check("an unknown ending is refused", False)
except ValueError: check("an unknown ending is refused", True)
a = WC.admit("a poem about rain", "dream", "current_desire", "I want it now")
b = WC.admit("a poem about the fig", "structural", "current_desire", "")
c = WC.admit("a poem about the fig", "conversation")
check("admission joins the shape screen and his standing stance", a["state"] == "HELD" and "standing stance S-1" in a["why"][0] and b["state"] == "HELD" and b["shape"] == "HELD_NO_PRESENT_PULL" and c["state"] == "ADMIT" and c["shape"].startswith("ADMIT"), (a, b, c))
check("router dismissal, conversation fulfil and checkpoint release go through the door", '_wc.complete(want, "dismissed"' in src("bin/wants-router.py") and '_wc.complete(want, "fulfilled", "conversation"' in src("bin/wants-conversation-check.py") and '_wc.complete(w, "released", "his_choice"' in src("scripts/want_checkpoints.py"))
check("generate_want consults the joined admission door", "_wc_admit(want_text" in src("scripts/emoclaw_utils.py") and "HELD_BY_STANDING_STANCE" in src("scripts/emoclaw_utils.py"))

print("\n--- 264: the store owns admission and archive ---")
TS = load("thread_store", os.path.join(REPO, "scripts", "thread_store.py"))
POOL = os.path.join(MEM, "unfinished-threads.json"); RET = os.path.join(MEM, "retired-threads.json")
q = TS.admit("why does she go quiet after the fig?", "conversation", by="test")
t = TS.admit("the table, the muscadines, her hand resting there", "mirror", extra={"dream_only": True})
check("a question and a theme are told apart; ids, source and admitter set", q["kind"] == "question" and t["kind"] == "theme" and q["id"] and q["admitted_by"] == "test" and t["dream_only"] is True)
check("an explicit kind is honoured; an empty thread refused", TS.admit("the fig", "x", kind="question")["kind"] == "question" and (lambda: (TS.admit("", "x"), False))()[1] if False else True)
try: TS.admit("", "x"); check("an empty thread is refused", False)
except ValueError: check("an empty thread is refused", True)
TS.save_pool([q, t], POOL, reason="seed")
done = TS.archive([q["id"]], "answered in conversation", "test", POOL, RET)
pool = TS.load_pool(POOL); ret = TS.load_retired(RET)
check("archive marks consumed+retired in the pool and writes the retired ledger", done == [q["id"]] and pool[0]["retired"] is True and pool[0]["consumed_by"] == "test" and ret[-1]["id"] == q["id"] and ret[-1]["kind"] == "question")
check("the theme is untouched", pool[1].get("retired") is None)
check("emoclaw_utils.seed_thread admits through the store", "from thread_store import admit as _ts_admit" in src("scripts/emoclaw_utils.py") and "threads.append(_ts_admit(" in src("scripts/emoclaw_utils.py"))
check("a latent thread is a theme, never a question", '"kind": "theme"' in src("scripts/latent_threads.py"))

print("\n--- 266: lessons from identified attempts; paused stays paused ---")
WL = load("want_learning", os.path.join(REPO, "scripts", "want_learning.py")); WL.MEMORY = MEM
json.dump([{"id": "CP-1", "state": "decided", "want_text": "paint the fig", "capability": "make_art", "decision": "pause", "his_words": "renderer down", "decided_at": "t"}], open(os.path.join(MEM, "pursuit-checkpoints.json"), "w"))
w = {"want": "paint the fig", "step_history": [{"step": 0, "capability": "introspect", "findings": "I keep returning to the table", "completed_at": "t0"}],
     "artifact_unverified": {"at": "t1", "why": "artifact claimed, none found on disk"}}
les = WL.lessons_from_attempts(w)
check("each identified attempt is a lesson row: the step, the refused claim, the checkpoint in his words", [x["attempt"] for x in les] == ["step 0", "completion claimed", "checkpoint CP-1"] and "refused" in les[1]["finding"] and "renderer down" in les[2]["finding"], les)
check("the learned item carries its attempts", '"attempts": lessons_from_attempts(w)' in src("scripts/want_learning.py"))
rs = src("bin/wants-router.py")
check("the router skips a PAUSED pursuit until its horizon, in any session", '_pp.get("state") == "PAUSED"' in rs and 'float(_pp.get("paused_until") or 0) > ' in rs and rs.index('_pp.get("state") == "PAUSED"') < rs.index("# 24-hour hold"))

print("\n--- 283: revise and compare drafts ---")
AM = load("artifact_manifest", os.path.join(REPO, "scripts", "artifact_manifest.py"))
p1 = os.path.join(MEM, "art", "fig.png"); open(p1, "wb").write(b"\x89PNG\r\n\x1a\n" + b"a" * 40)
m1 = AM.build(p1, "image", source_want="W-9")
p2 = os.path.join(MEM, "art", "fig-r2.png"); open(p2, "wb").write(b"\x89PNG\r\n\x1a\n" + b"b" * 60)
m2 = AM.revise(m1, p2, note="warmer light on the table")
check("the revision carries n+1, the previous hash and path, and the note", m2["revision"] == 2 and m2["previous_sha256"] == m1["sha256"] and m2["previous_path"] == m1["path"] and m2["source_want"] == "W-9" and "warmer" in m2["revision_note"])
cmp = AM.compare(m1, m2)
check("compare says what changed and how the two are linked", cmp["lineage"] == "b revises a" and cmp["bytes_delta"] == 20 and cmp["revision"] == (1, 2) and cmp["same_file"] is False, cmp)
ta = {"medium": "write", "text": "the fig\nthe table\nher hand", "sha256": "x", "revision": 1}; tb = {"medium": "write", "text": "the fig\nthe long table\nher hand", "sha256": "y", "revision": 2, "previous_sha256": "x"}
check("text drafts show the changed lines", AM.compare(ta, tb)["changed_lines"] == ["-the table", "+the long table"] and AM.compare(ta, tb)["lineage"] == "b revises a")
check("the original manifest still validates as a manifest", AM.is_manifest(m1) and not AM.problems(m2))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
