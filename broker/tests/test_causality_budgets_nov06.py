#!/usr/bin/env python3
"""Causality formation budgets, spike noise, reviewer errors and lineage (2026-11-06).

Scratch HOME before any import; requests is a stub that refuses to send; every model call
goes through a counting stub. Nothing here reaches a model, a sender or live memory.
"""
import os, sys, json, tempfile, types, importlib.util
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-causal-budget-")
os.environ["HOME"] = HOME
os.environ.pop("CAUSALITY_BACKEND", None)
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))


def _refuse(*a, **k):
    raise AssertionError("sender forbidden in tests")


sys.modules["requests"] = types.SimpleNamespace(post=_refuse, get=_refuse)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


CE = load("causality_budget_fixture", os.path.join(REPO, "scripts", "causality-engine.py"))
CE.WORKSPACE = WS; CE.MEMORY = MEM
CE.HYPOTHESIS_DB = os.path.join(MEM, "causality-hypotheses.json")
CE.RETIRED_PATH = os.path.join(MEM, "causality-retired.jsonl")
CE.load_full_context = lambda: "fixture context"

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)) if detail and not ok else ""))

check("suite writes only beneath scratch HOME", CE.HYPOTHESIS_DB.startswith(HOME) and CE.MEMORY.startswith(HOME))
TODAY = date.today().isoformat()


def formed(source, n, day=TODAY):
    h = {"formed": day + "T%02d:00:00" % (8 + n), "formed_date": day, "source": source,
         "hypothesis": "%s fixture %d" % (source, n), "status": "untested", "marks": []}
    return CE._stamp_formation(h, {"seed": "formation occasion for %s number %d" % (source, n)})


class Counter:
    def __init__(self, reply=""):
        self.calls, self.reply = 0, reply
    def __call__(self, *a, **k):
        self.calls += 1
        return self.reply


# 1. Each source has its own slice; the nightly qualitative row survives a full realtime day.
day = {"hypotheses": [formed("causal-jepa", i) for i in range(CE.FORMATION_SLICES["jepa"])]}
check("realtime filling its JEPA slice leaves the qualitative slice open",
      CE.formation_budget(day, "causal-jepa") == 0
      and CE.formation_budget(day, "causality_nightly_qualitative") == CE.FORMATION_SLICES["nightly"])
day["hypotheses"].append(formed("causality_nightly_qualitative", 20))
day["hypotheses"].append(formed("causality_engine", 0))
retired = CE._retire_formation_overflow(day)
check("a qualitative row formed after realtime is not retired as overflow",
      retired == [] and any(h["source"] == "causality_nightly_qualitative" for h in day["hypotheses"]),
      [h["retirement"] for h in retired])
day["hypotheses"].append(formed("causal-jepa", 21))
retired = CE._retire_formation_overflow(day)
check("a row past its own slice is retired with that slice named",
      len(retired) == 1 and retired[0]["source"] == "causal-jepa"
      and retired[0]["retirement"]["formation_slice"] == "jepa")
check("the day's ceiling is the sum of the slices",
      CE.DAILY_FORMATION_CAP == sum(CE.FORMATION_SLICES.values()))
legacy = {"hypotheses": [{"formed": TODAY + "T0%d:00:00" % i, "formed_date": TODAY,
                          "source": "causal-jepa", "hypothesis": "legacy %d" % i} for i in range(3)]}
check("rows formed before slices existed are judged by their old pool, not retired retroactively",
      CE._retire_formation_overflow(legacy) == [] and len(legacy["hypotheses"]) == 3)

# 2. The nightly qualitative pass does not call a model when its slice is spent.
def nightly_with(db_rows, reply):
    snap = CE.HypothesisSnapshot({"hypotheses": db_rows, "deliveries": {}, "confirmed": 0})
    llm = Counter(reply)
    with patch.object(CE, "load_existing_hypotheses", return_value=snap), \
         patch.object(CE, "load_daily_material", return_value={"inner": "a real inner day", "creative": "", "interaction": ""}), \
         patch.object(CE, "test_existing_hypotheses", return_value=None), \
         patch.object(CE, "graduate_hypotheses", return_value=(0, 0)), \
         patch.object(CE, "form_causal_hypotheses", return_value=0), \
         patch.object(CE, "save_hypotheses", return_value=None), \
         patch.object(CE, "write_hypothesis_log", return_value=None), \
         patch.object(CE, "ask_llm", llm):
        CE.nightly_run()
    return snap, llm

reply = "HYPOTHESIS: Quiet mornings ease me.\nCONFIDENCE: medium\nTEST: notice tomorrow\n\nHYPOTHESIS: Second.\nCONFIDENCE: low\nTEST: t\n"
snap, llm = nightly_with([formed("causal-jepa", i) for i in range(2)], reply)
kept = [h for h in snap["hypotheses"] if h["source"] == "causality_nightly_qualitative"]
check("nightly qualitative forms its one row on a day realtime filled",
      llm.calls == 1 and len(kept) == CE.FORMATION_SLICES["nightly"] and kept[0].get("formation_slice") == "nightly")
snap, llm = nightly_with([formed("causality_nightly_qualitative", 0)], reply)
check("nightly qualitative skips the model call when its slice is spent", llm.calls == 0)

# 3. Realtime/JEPA formation does not call the model once the budget is used.
evidence = [{"time": "2026-11-06T1%d:00:00+00:00" % i, "untraceable": False,
             "shift": [{"dimension": "Warmth", "direction": "rose", "from": 0.4, "to": 0.55, "delta": 0.15}],
             "candidates": [{"kind": "said", "text": "candidate %d" % i}]} for i in range(5)]
with open(os.path.join(MEM, "cause-evidence.json"), "w") as fh: json.dump(evidence, fh)
full = {"hypotheses": [formed("causal-jepa", i) for i in range(2)]}
llm = Counter('{"distribution": [], "confidence": "high", "hypothesis": "h", "test": "t"}')
with patch.object(CE, "ask_llm", llm):
    n = CE.form_causal_hypotheses(full, cap=1)
check("JEPA formation with no budget left returns before any model call", n == 0 and llm.calls == 0)
open_db = {"hypotheses": []}
with patch.object(CE, "ask_llm", llm):
    n = CE.form_causal_hypotheses(open_db, cap=3)
check("JEPA formation stops calling the model once its slice is filled",
      n == CE.FORMATION_SLICES["jepa"] and llm.calls == CE.FORMATION_SLICES["jepa"], (n, llm.calls))

# 4. Spike threshold and shift-sized confidence.
check("local spike threshold is raised off the noise floor", CE.SPIKE_THRESHOLD >= 0.06, CE.SPIKE_THRESHOLD)
small = [{"delta": 0.029}]; mid = [{"delta": -0.08}]; big = [{"delta": 0.2}]
check("a noise-sized shift cannot be medium confidence", CE._confidence_for_shift("medium", small) == "low")
check("a p99 shift may be medium but not high", CE._confidence_for_shift("high", mid) == "medium")
check("a large shift keeps a high claim, and a low claim stays low",
      CE._confidence_for_shift("high", big) == "high" and CE._confidence_for_shift("low", big) == "low")
noise_ev = [dict(evidence[0], shift=[{"dimension": "Arousal", "direction": "rose", "delta": 0.024}])]
with open(os.path.join(MEM, "cause-evidence.json"), "w") as fh: json.dump(noise_ev, fh)
noise_db = {"hypotheses": []}
with patch.object(CE, "ask_llm", Counter('{"distribution": [], "confidence": "medium", "hypothesis": "h", "test": "t"}')):
    n = CE.form_causal_hypotheses(noise_db, cap=1)
dist = json.load(open(os.path.join(MEM, "cause-distribution.json")))
check("a model's medium on a 0.024 shift is recorded as low and forms nothing",
      n == 0 and dist[0]["confidence"] == "low" and dist[0]["claimed_confidence"] == "medium")

# 5. main() hands the most recent day of spikes to formation, not the oldest of the month.
now = datetime.now(timezone.utc)
month = [{"time": (now - timedelta(hours=h)).isoformat(), "dimension": "Warmth", "direction": "rose",
          "delta": 0.1, "from": 0.4, "to": 0.5} for h in range(31 * 24, -1, -1)]
recent = CE.recent_spikes(month)
check("recent_spikes keeps the latest ten from the last 24h, oldest first",
      len(recent) == 10 and recent[-1] is month[-1]
      and all((now - datetime.fromisoformat(s["time"])).total_seconds() <= 86400 for s in recent)
      and [s["time"] for s in recent] == sorted(s["time"] for s in recent))
seen = {}
def capture_form(spikes, *a, **k):
    seen["spikes"] = spikes; return []
with patch.object(CE, "load_emotional_trajectory", return_value=[]), patch.object(CE, "find_spikes", return_value=month), \
     patch.object(CE, "load_recent_dreams", return_value=[]), patch.object(CE, "load_recent_mirrors", return_value=[]), \
     patch.object(CE, "load_recent_silences", return_value=[]), patch.object(CE, "load_recent_conversations", return_value=[]), \
     patch.object(CE, "load_trial_ledger", return_value=[]), \
     patch.object(CE, "load_existing_hypotheses", return_value=CE.HypothesisSnapshot({"hypotheses": [], "confirmed": 0, "revised": 0})), \
     patch.object(CE, "form_hypotheses", side_effect=capture_form), \
     patch.object(CE, "save_hypotheses", return_value=None), patch.object(CE, "write_hypothesis_log", return_value=None):
    CE.main()
check("main() forms from today's spikes", seen.get("spikes") == recent)

spent = CE.HypothesisSnapshot({"hypotheses": [formed("causality_engine", 0)], "confirmed": 0, "revised": 0})
no_form = Counter([])
with patch.object(CE, "load_emotional_trajectory", return_value=[]), patch.object(CE, "find_spikes", return_value=month),      patch.object(CE, "load_recent_dreams", return_value=[]), patch.object(CE, "load_recent_mirrors", return_value=[]),      patch.object(CE, "load_recent_silences", return_value=[]), patch.object(CE, "load_recent_conversations", return_value=[]),      patch.object(CE, "load_trial_ledger", return_value=[]), patch.object(CE, "load_existing_hypotheses", return_value=spent),      patch.object(CE, "form_hypotheses", no_form), patch.object(CE, "ask_llm", no_form),      patch.object(CE, "save_hypotheses", return_value=None), patch.object(CE, "write_hypothesis_log", return_value=None):
    CE.main()
check("main() skips formation and the model when its slice is spent", no_form.calls == 0)

# 6. Capacity cull records net, not age.
old = (date.today() - timedelta(days=3)).isoformat()
rows = [{"formed": old + "T01:00:00", "formed_date": old, "source": "causality_engine", "hypothesis": "row %d" % i,
         "status": "held", "marks": []} for i in range(51)]
rows[0]["graduation_readiness"] = {"net": -2}
snap = CE.HypothesisSnapshot({"hypotheses": rows, "confirmed": 0, "revised": 0})
formed_calls = Counter([])
with patch.object(CE, "load_emotional_trajectory", return_value=[]), patch.object(CE, "find_spikes", return_value=[]), \
     patch.object(CE, "load_recent_dreams", return_value=[]), patch.object(CE, "load_recent_mirrors", return_value=[]), \
     patch.object(CE, "load_recent_silences", return_value=[]), patch.object(CE, "load_recent_conversations", return_value=[]), \
     patch.object(CE, "load_trial_ledger", return_value=[]), patch.object(CE, "load_existing_hypotheses", return_value=snap), \
     patch.object(CE, "form_hypotheses", formed_calls),      patch.object(CE, "save_hypotheses", return_value=None), patch.object(CE, "write_hypothesis_log", return_value=None):
    CE.main()
check("the over-capacity store leaves only its refuted row", formed_calls.calls == 1 and len(snap["hypotheses"]) == 50)
culled = rows[0].get("retired") or {}
check("capacity cull writes the refuted row's net, and its age separately",
      culled.get("net") == -2 and culled.get("age_days") == 3, culled)


# 7. Reviewer: enough tokens, truncated JSON is an error (retry), and only "yes" nights support belief.
def eligible(source="causality_engine"):
    h = formed(source, 0, day="2026-08-01")
    for n in range(1, 8):
        d = "2026-08-%02d" % (n + 1)
        if n in (1, 3, 5):
            item = CE._catalog_item(d, "interactions", "new supporting occasion %d for the fixture" % n, 0)
            CE._record_nightly(h, d, "yes", "occasion %d" % n, [item])
        elif n == 2:
            item = CE._catalog_item(d, "interactions", "a refuting occasion for the fixture theory", 0)
            CE._record_nightly(h, d, "no", "refuted", [item])
        else:
            CE._record_nightly(h, d, "unconfirmed", reason="no_bearing_evidence")
    return h

posted = {}
def reviewer(reply):
    def post(*a, **k):
        posted.update(k.get("json") or {})
        return types.SimpleNamespace(json=lambda: {"choices": [{"message": {"content": reply}}]})
    return types.SimpleNamespace(post=post)

h = eligible(); db = {"hypotheses": [h]}
with patch.dict(sys.modules, {"requests": reviewer('{"accurate": false, "concern": "a long concern that ran o')}):
    out = CE.graduate_hypotheses(db)
check("reviewer is given room to finish its JSON", posted.get("max_tokens", 0) >= 400, posted.get("max_tokens"))
check("a truncated reviewer reply defers graduation instead of retiring",
      out == (0, 0) and h in db["hypotheses"] and h["status"] == "eligible_day_7"
      and h["graduation_review"]["state"] == "error" and h["graduation_review"]["attempts"] == 1)
with patch.dict(sys.modules, {"requests": reviewer('Here: {"accurate": true, "concern": ""}')}):
    out = CE.graduate_hypotheses(db)
yes_ids = [i for m in h["marks"] if m.get("verdict") == "yes" for i in m["evidence_ids"]]
no_ids = [i for m in h["marks"] if m.get("verdict") == "no" for i in m["evidence_ids"]]
belief = next(e for e in db["deliveries"].values() if e["kind"] == "belief")["payload"]
record = next(e for e in db["deliveries"].values() if e["kind"] == "graduation_record")["payload"]
check("the retried review graduates the theory", out == (1, 0) and h["graduated"])
check("belief receives only the supporting nights' evidence",
      belief["evidence_ids"] == yes_ids and not set(no_ids) & set(belief["evidence_ids"]) and len(yes_ids) == 3)
check("the graduation record keeps refuting evidence apart",
      record["evidence_ids"] == yes_ids and record["refuting_evidence_ids"] == no_ids)

# 8. JEPA formation lineage keeps every candidate as its own root.
cands = ["candidate occasion number %d " % i + "x" * 300 for i in range(6)]
roots = CE._root_lines({"event": "t", "shift": [{"dimension": "Warmth"}], "candidates": cands})
check("each JEPA candidate is its own guarded root line",
      all(CE._norm_evidence(c)[:500] in roots for c in cands), len(roots))
later = CE._catalog_item(TODAY, "interactions", cands[5], 0)
h = formed("causal-jepa", 0); h.pop("formation")
CE._stamp_formation(h, {"event": "t", "candidates": cands})
check("the sixth candidate can no longer witness the hypothesis it seeded", CE._same_as_formation(h, later))

# 9. Ghost Branch rows carry a formation envelope and dedupe by thread type + pattern.
GH = load("ghost_budget_fixture", os.path.join(REPO, "scripts", "ghost-branches.py"))
GH.MEMORY = MEM; GH.CAUSALITY_FILE = CE.HYPOTHESIS_DB
check("ghost fixture writes beneath scratch HOME", GH.CAUSALITY_FILE.startswith(HOME))
with open(GH.CAUSALITY_FILE, "w") as fh: json.dump({"hypotheses": []}, fh)
GH.detect_primary_pattern = lambda _: (_ for _ in ()).throw(AssertionError("pattern passed in, no model call"))
thread = {"thread": "the thread he kept returning to about plain speech"}
a = GH.seed_causality_hypothesis(thread, {"id": "more_brazen", "label": "more brazen"}, "primary output text here", "raw_desire", "metaphorical_detachment")
b = GH.seed_causality_hypothesis(thread, {"id": "higher_curiosity", "label": "higher curiosity"}, "primary output text here", "raw_desire", "Metaphorical-Detachment")
c = GH.seed_causality_hypothesis(thread, {"id": "higher_curiosity", "label": "higher curiosity"}, "primary output text here", "raw_desire", "humor_deflection")
stored = json.load(open(GH.CAUSALITY_FILE))["hypotheses"]
check("ghost rows are stamped with formation lineage",
      all(r.get("formation", {}).get("root_fingerprints") and r.get("hypothesis_id") for r in stored)
      and not any("formation_slice" in r for r in stored))
check("same thread type + pattern is one row; the extra lean is recorded on it",
      len(stored) == 2 and b["id"] == a["id"] and stored[0].get("also_successful_leans") == ["higher_curiosity"]
      and c["id"] != a["id"], [r.get("hypothesis") for r in stored])
src = open(os.path.join(REPO, "scripts", "ghost-branches.py")).read()
check("a ghost run detects the primary pattern once, not once per lean",
      src.count("= detect_primary_pattern(primary_output)") == 2 and "primary_output, thread_type, primary_pattern)" in src)

# 10. The repair for reviewer-error holds is a dry run by default and touches only those rows.
RP = load("reinstate_fixture", os.path.join(REPO, "scripts", "repairs", "reinstate_reviewer_error_holds.py"))
with open(CE.HYPOTHESIS_DB, "w") as fh: json.dump({"hypotheses": []}, fh)
broken, real = eligible(), eligible()
broken["hypothesis_id"], real["hypothesis_id"] = "CH-broken", "CH-real"
for row, concern, why in ((broken, "reviewer unreachable: no JSON object in reviewer reply", "reviewer_unreachable"),
                          (real, "asserts her inner state as fact", None)):
    row.update(status="retired", graduation_review={"state": "held", "basis": "b"},
               retirement={"reason": "graduation_review_held", "at": "2026-11-05T23:15:00"})
with open(CE.RETIRED_PATH, "w") as fh:
    for row in (broken, real): fh.write(json.dumps(row) + "\n")
with open(os.path.join(MEM, "hallucination-flags.json"), "w") as fh:
    json.dump([{"type": "graduation_held", "hypothesis_id": "CH-broken", "held_reason": "reviewer_unreachable",
                "concern": "reviewer unreachable: no JSON object in reviewer reply"},
               {"type": "graduation_held", "hypothesis_id": "CH-real", "concern": "asserts her inner state as fact"}], fh)
before = open(CE.HYPOTHESIS_DB).read()
_, proposals, skipped = RP.plan(CE)
check("repair proposes only the reviewer-error hold, eligible with one attempt counted",
      [p["hypothesis_id"] for p in proposals] == ["CH-broken"] and skipped == [("CH-real", "held by a working reviewer")]
      and proposals[0]["row"]["status"] == "eligible_day_7" and "retirement" not in proposals[0]["row"]
      and proposals[0]["row"]["graduation_review"]["attempts"] == 1 and proposals[0]["survives_next_save"])
check("planning the repair writes nothing", open(CE.HYPOTHESIS_DB).read() == before)

# 11. The realtime poll stops before the evidence pass and the model once the JEPA slice is spent.
os.environ["CENG_PATH"] = os.path.join(REPO, "scripts", "causality-engine.py")
os.environ["SPARK_WORKSPACE"] = WS
RT = load("realtime_budget_fixture", os.path.join(REPO, "scripts", "realtime_causality.py"))
check("realtime fixture state is beneath scratch HOME", RT.STATE.startswith(HOME))
with open(CE.HYPOTHESIS_DB, "w") as fh:
    json.dump({"hypotheses": [formed("causal-jepa", i) for i in range(CE.FORMATION_SLICES["jepa"])]}, fh)
spike_time = datetime.now(timezone.utc).isoformat()
fake_engine = types.SimpleNamespace(load_emotional_trajectory=lambda: [],
                                    find_spikes=lambda _t: [{"time": spike_time}])
runs = []
with patch.dict(sys.modules, {"causality_engine": fake_engine}),      patch.object(RT.subprocess, "run", side_effect=lambda *a, **k: runs.append(a)):
    RT.main()
check("realtime with the JEPA slice spent runs no evidence pass or consumer, and marks the spike seen",
      runs == [] and json.load(open(RT.STATE))["last"] == spike_time)

# bin/ and scripts/ copies stay identical.
for name in ("causality-engine.py", "ghost-branches.py"):
    check("bin/%s matches scripts/%s" % (name, name),
          open(os.path.join(REPO, "bin", name)).read() == open(os.path.join(REPO, "scripts", name)).read())

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
