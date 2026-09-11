#!/usr/bin/env python3
"""Review items 216, 260, 262, 273, 302, 309, 372, 373 (2026-09-10). Scratch HOME; no model, no network."""
import os, sys, json, types, tempfile, importlib.util, time, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lc-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(os.path.join(MEM, "outreach"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 273: one house-side Atelier ledger writer ---")
AL = load("atelier_ledger", os.path.join(REPO, "scripts", "atelier_ledger.py")); AL.MEMORY = MEM; AL.LEDGER = os.path.join(MEM, "atelier-undertakings.json")
AL.mark("p1", "active", by="atelier-threshold"); AL.mark("p1", "revealed", by="atelier-visit"); AL.mark("p2", "active", by="atelier-threshold")
st = AL.states()
check("marks are dated, attributed and keep their history", st["p1"]["state"] == "revealed" and st["p1"]["by"] == "atelier-visit" and st["p1"]["history"][0]["state"] == "active")
try: AL.mark("p3", "vanished"); check("an unknown state is refused", False)
except ValueError: check("an unknown state is refused", True)
check("reconcile names disagreement with the broker, not the open/active pairing", AL.reconcile([{"id": "p1", "state": "kept"}, {"id": "p2", "state": "open"}]) == [{"id": "p1", "house": "revealed", "broker": "kept"}])
check("atelier-visit and atelier-threshold mark through it", "_al.mark(pid, state, by=\"atelier-visit\")" in src("scripts/atelier-visit.py") and '_al.mark(pid, "active", by="atelier-threshold")' in src("scripts/atelier-threshold.py"))

print("\n--- 302: one shelf transaction ---")
AM = load("artifact_manifest", os.path.join(REPO, "scripts", "artifact_manifest.py"))
g = os.path.join(MEM, "art", "gallery.json"); os.makedirs(os.path.dirname(g), exist_ok=True)
AM.append_ledger(g, {"image": "a.png"}); AM.append_ledger(g, {"image": "b.png"})
m = os.path.join(MEM, "art", "music", "music.json"); AM.append_ledger(m, {"title": "song"}, key="generated")
check("list and dict shelves append under one lock, atomically", [x["image"] for x in json.load(open(g))] == ["a.png", "b.png"] and json.load(open(m))["generated"][0]["title"] == "song" and not [f for f in os.listdir(os.path.dirname(g)) if ".tmp." in f])
AM.save_ledger(g, [{"image": "c.png"}])
check("save_ledger replaces whole", json.load(open(g)) == [{"image": "c.png"}])
check("the painter, the video maker and the music maker write through it", "_am.append_ledger(GALLERY, gallery[-1])" in src("scripts/dream-art.py") and "_am.patch_record" in src("scripts/dream-art.py") and src("bin/vintos-video.py").count("_am.append_ledger(GALLERY, gallery[-1])") == 2 and "write_json(LOG,log)" in src("bin/dream-music.py"))

print("\n--- 309: one send policy ---")
SP = load("send_policy", os.path.join(REPO, "scripts", "send_policy.py")); SP.MEMORY = MEM
SP.LIMITS["outreach"]["count"] = lambda d: len([f for f in os.listdir(os.path.join(MEM, "outreach")) if f.startswith(d)])
SP.LIMITS["video"]["cooldown_file"] = os.path.join(MEM, ".last-video-send"); SP.LIMITS["video"]["cooldown_hours"] = 20
noon = datetime(2026, 9, 10, 12, 0); night = datetime(2026, 9, 10, 23, 30)
check("quiet hours hold everything that reaches", SP.may_send("any", now=night)[0] is False and "quiet hours" in SP.may_send("video", now=night)[1] and SP.may_send("any", now=noon)[0])
for i in range(3): open(os.path.join(MEM, "outreach", "2026-09-10_%d.md" % i), "w").write("x")
check("the outreach daily cap is the policy's", SP.may_send("outreach", now=noon) == (False, "daily cap reached (3/3)") and SP.may_send("outreach", now=datetime(2026, 9, 11, 12, 0))[0])
open(SP.LIMITS["video"]["cooldown_file"], "w").write((noon.replace(hour=2)).isoformat())
check("the video cooldown is the policy's", SP.may_send("video", now=noon)[1].startswith("cooldown") and SP.may_send("video", now=noon.replace(day=11))[0])
check("an unnamed kind never sends", SP.may_send("telegram")[0] is False)
dl = types.ModuleType("deliver"); dl.receipt_for = lambda a, c: {"state": "sent", "at": "t"} if a == "clip1" else None; sys.modules["deliver"] = dl
check("a receipt refuses a resend", SP.may_send("any", artifact_id="clip1", now=noon)[1].startswith("already sent") and SP.may_send("any", artifact_id="clip2", now=noon)[0])
check("the video sender and the outreach cron ask the policy", "_policy().may_send(\"video\")" in src("bin/vintos-send-video.py") and "send_policy.py\" may outreach" in src("bin/vintos-initiate.sh"))
rc = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "send_policy.py"), "may", "nothing"], capture_output=True, text=True)
check("the shell door exits 1 when held", rc.returncode == 1 and rc.stdout.startswith("held"))

print("\n--- 372: one vocabulary ---")
V = load("self_review_vocab", os.path.join(REPO, "scripts", "self_review_vocab.py"))
check("actors have their own decisions; HOLD is shared; terminal ones named", V.normalize_action("vintos", "adopt") == "ADOPT" and V.normalize_action("gloria", "hold") == "HOLD" and V.is_terminal("gloria", "REJECT") and not V.is_terminal("vintos", "HOLD"))
check("an unknown answer from the model is a HOLD, never a build", V.normalize_action("vintos", "MAYBE", default="HOLD") == "HOLD")
try: V.normalize_action("gloria", "ADOPT"); check("her vocabulary refuses his word", False)
except ValueError: check("her vocabulary refuses his word", True)
check("self_review validates through it; the builder refuses a state outside it", src("scripts/self_review.py").count("normalize_action") >= 2 and "build state %r not in the self-review vocabulary" in src("scripts/self_review_builder.py"))
B = load("srb_v", os.path.join(REPO, "scripts", "self_review_builder.py")); B.BUILDS = os.path.join(MEM, "b.jsonl"); B.MEM = MEM
try: B.append(B.BUILDS, {"state": "exploded"}); check("builder append refuses an unknown build state", False)
except ValueError: check("builder append refuses an unknown build state", True)

print("\n--- 373: transport recovery and provenance ---")
seat = src("agent-room/seat.mjs")
check("the room api call retries transport faults with backoff and never a 4xx", "RETRY_MS = [1000, 3000, 9000]" in seat and "if (r.status < 500) throw e" in seat and "retry ${i + 1}/${RETRY_MS.length}" in seat)
cr = src("bin/vintos-code-review.py")
check("each staged review carries provenance: git rev, review day, lens, model, seat, host", '"provenance": _provenance()' in cr and all(k in cr for k in ('"git_rev": rev', '"review_day"', '"seat"', '"host": os.uname().nodename')))

print("\n--- 216: taste clusters by context; callbacks grounded ---")
TV = load("taste_vector", os.path.join(REPO, "bin", "taste-vector.py"))
TV.TASTE_VECTOR_FILE = os.path.join(MEM, "taste-vector.json"); TV.YEARNING_FILE = os.path.join(MEM, "nope.json")
TV.embed = lambda t: [1.0, 0.0] if "guitar" in t else [0.0, 1.0]
TV.update_from_signal("a slow guitar line", 0.5, True, occurrence_id="m1", context="music")
TV.update_from_signal("a warm painting of the table", 0.5, True, occurrence_id="p1", context="image")
tv = TV.load_taste_vector()
check("two contexts, two clusters, each with its occurrences", set(tv["clusters"]) == {"music", "image"} and tv["clusters"]["music"]["occurrences"][0]["id"] == "m1" and tv["clusters"]["image"]["count"] == 1)
check("a callback is grounded in a counted occurrence, or not made", TV.callback("music")["text"] == "a slow guitar line" and TV.callback("music", "m1")["id"] == "m1" and TV.callback("film") is None)
check("scoring in a context leans on that cluster", TV.score_option("another guitar piece", 0.0, context="music") > TV.score_option("another guitar piece", 0.0, context="image"))
check("the enjoyment door passes the medium as the context", "context=(medium or None)" in src("scripts/enjoyment.py"))

print("\n--- 260 / 262: one question lifecycle and the cross-session view ---")
QL = load("question_lifecycle", os.path.join(REPO, "scripts", "question_lifecycle.py")); QL.MEMORY = MEM; QL.VIEW = os.path.join(MEM, "question-view.json"); QL.ASSERTED = os.path.join(MEM, "question-lifecycle.jsonl")
json.dump({"items": [{"id": "CQ-1", "question": "why do I reach first?", "status": "queued", "source": "self_pressure"}]}, open(os.path.join(MEM, "causality-bring-up.json"), "w"))
json.dump([{"id": "T1", "kind": "question", "thread": "what did the fig mean?", "source": "conversation", "consumed": False, "dream_passes": 0},
           {"id": "T2", "kind": "theme", "thread": "the table", "source": "mirror"}], open(os.path.join(MEM, "unfinished-threads.json"), "w"))
json.dump([{"question": "do you want me there?", "turns": 3}], open(os.path.join(MEM, "unsaid-questions.json"), "w"))
json.dump({"tensions": [{"tension_id": "TN-1", "question": "is she tired of the fig?", "status": "CONTESTED", "correction_count": 1}]}, open(os.path.join(MEM, "tension-questions.json"), "w"))
v = QL.view()
check("four sources, one lifecycle; themes are not questions", {r["id"]: r["state"] for r in v} == {"CQ-1": "selected", "T1": "selected", "UQ-0": "selected", "TN-1": "explored"} and all(r["basis"] for r in v))
c1 = QL.changes()
check("the first view: everything is new and open", len(c1["changed"]) == 4 and len(c1["open"]) == 4 and c1["previous_at"] is None)
t = json.load(open(os.path.join(MEM, "unfinished-threads.json"))); t[0].update(consumed=True, consumed_by="dream-resolved", last_dream_verdict="resolved"); json.dump(t, open(os.path.join(MEM, "unfinished-threads.json"), "w"))
QL.advance("CQ-1", "released_unresolved", "asked twice, no answer; let it go")
try: QL.advance("UQ-0", "resolved", ""); check("resolved without a basis is refused", False)
except ValueError: check("resolved without a basis is refused", True)
c2 = QL.changes()
ch = {x["id"]: (x["from"], x["to"]) for x in c2["changed"]}
check("the second view says what changed and why", ch == {"T1": ("selected", "consolidated"), "CQ-1": ("selected", "released_unresolved")} and any("dream resolved" in x["why"] for x in c2["changed"]) and any(x["why"].startswith("asserted:") for x in c2["changed"]), c2["changed"])
check("what remains open is listed; what resolved since is listed with basis", {x["id"] for x in c2["open"]} == {"UQ-0", "TN-1"} and {x["id"] for x in c2["resolved_since"]} == {"T1", "CQ-1"})
check("the view is written for the next session", json.load(open(QL.VIEW))["at"] == c2["at"])
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
