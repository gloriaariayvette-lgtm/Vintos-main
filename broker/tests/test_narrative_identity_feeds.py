#!/usr/bin/env python3
"""Narrative identity and the feeds under it (2026-11-14). Synthetic fixtures only; scratch HOME; no model,
no socket. Every check is also run against a mutant of the code it guards, and the mutant must fail it.

- behavioral intercept: SCRIPTS was never defined, so the narrative feed (and the blush write) raised NameError
  inside a bare except: the feed never fired;
- a permanent trial's attempts after it promoted, and a promoted capacity's further dates, never reached the
  causal self-model: its entries stayed at their promotion confidence, 0.50;
- two entries with no trigger (capacities) could never match, so a capacity was re-added instead of reinforced;
- the narrative feed's gate was "> 0.5" against a plateau the producers reach on evidence (two attempts, two dates);
- narrative identity proposes an entry once per new piece of evidence, never for a stale one; stale candidates
  start over; the shared frame "I tend to ... when" does not make unrelated entries look alike; each fragment
  keeps references to the evidence it rests on."""
import json, os, socket, subprocess, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="narrative-feeds-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM, exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise AssertionError("no model is called from this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
POPEN = []
class _FakePopen:
    def __init__(self, args, *a, **k): POPEN.append(list(args))
subprocess.Popen = _FakePopen
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.modules["self_drift"] = types.SimpleNamespace(get_direction_bias=lambda: (None, 0.0))
sys.modules["absence_map_cold"] = types.SimpleNamespace(get_absence_gravity=lambda t: {}, load_cold=lambda: {},
                                                        save_cold=lambda d: None)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

PATHS = {"csm": os.path.join(REPO, "bin", "causal_self_model.py"),
         "ni": os.path.join(REPO, "bin", "narrative-identity.py"),
         "bi": os.path.join(REPO, "scripts", "behavioral_intercept.py"),
         "te": os.path.join(REPO, "scripts", "trial_extractor.py")}
MODNAME = {"csm": "causal_self_model", "ni": "narrative_identity", "bi": "behavioral_intercept", "te": "trial_extractor"}

def load(kind, mutation=None):
    """The module from its source, optionally with one (old, new) replacement, registered under its import name."""
    path = PATHS[kind]; src = open(path).read()
    if mutation:
        old, new = mutation
        assert old in src, "mutation target missing in %s: %r" % (kind, old[:60])
        src = src.replace(old, new)
    mod = types.ModuleType(MODNAME[kind]); mod.__file__ = path
    sys.modules[MODNAME[kind]] = mod
    exec(compile(src, path, "exec"), mod.__dict__)
    return mod

def reset_stores():
    for f in os.listdir(MEM):
        p = os.path.join(MEM, f)
        if os.path.isfile(p): os.remove(p)
    del POPEN[:]

# ------------------------------------------------------------------ causal self-model
def g_csm(csm):
    out = []
    reset_stores()
    out.append(("its store is throwaway", csm.MODEL_FILE.startswith(HOME)))
    r1 = csm.add_entry("", "keeps a steady rhythm in long replies", confidence=0.5, source="trial-extractor",
                       entry_type="positive", occurrence_id="capacity:steady:2026-03-01")
    r2 = csm.add_entry("", "keeps a steady rhythm in long replies", confidence=0.6, source="trial-extractor",
                       entry_type="positive", occurrence_id="capacity:steady:2026-03-02")
    r3 = csm.add_entry("", "keeps a steady rhythm in long replies", confidence=0.6, source="trial-extractor",
                       entry_type="positive", occurrence_id="capacity:steady:2026-03-02")
    E = csm.load_model()["entries"]
    out.append(("add_entry says what it did", (r1, r2, r3) == ("added", "reinforced", "duplicate"), (r1, r2, r3)))
    out.append(("two trigger-less entries with one tendency are one entry, reinforced",
                len(E) == 1 and E[0]["evidence_count"] == 2 and abs(E[0]["confidence"] - 0.56) < 1e-9, E))
    return out

# ------------------------------------------------------------------ behavioural intercept
def _ledger(trials):
    json.dump({"trials": trials}, open(os.path.join(MEM, "trial-ledger.json"), "w"))

_PATTERNS = {"trial_a": ("she asks a direct question about plans", "answering with a question instead of a choice"),
             "permanent_p": ("she asks what he wants for dinner", "deferring the pick back to her"),
             "permanent_q": ("a song ends mid-conversation", "apologising for the silence afterwards")}

def _trial(tid, attempts, promoted=None, status="active"):
    t = {"id": tid, "trigger": _PATTERNS[tid][0], "status": status,
         "pattern_description": _PATTERNS[tid][1],
         "alternative": "name a choice", "outcomes": [], "attempt_count": attempts, "ignore_count": 0}
    if promoted: t["promoted"] = promoted
    return t

def g_bi(bi, csm):
    out = []
    reset_stores()
    out.append(("its ledger is throwaway", bi.LEDGER.startswith(HOME)))
    if hasattr(bi, "NARRATIVE_LOG"):
        bi.NARRATIVE_LOG = os.path.join(HOME, "narrative-identity.log")
    _ledger([_trial("trial_a", 1)])
    bi.log_outcome("trial_a", "attempted")
    feeds = [c for c in POPEN if any("narrative-identity.py" in str(x) for x in c)]
    out.append(("a trial promoting at two attempts fires the narrative feed", len(feeds) == 1 and feeds[0][-1] == "feed", POPEN))
    E = csm.load_model()["entries"]
    out.append(("... and enters the causal model at its earned 0.50",
                len(E) == 1 and abs(E[0]["confidence"] - 0.5) < 1e-9 and E[0]["type"] == "negative", E))
    # a permanent trial that promoted earlier keeps adding evidence
    reset_stores()
    perm = _trial("permanent_p", 2, promoted="2026-01-01T10:00:00")
    perm2 = _trial("permanent_q", 2, promoted="2026-01-01T10:00:00")
    _ledger([perm, perm2])
    csm.add_entry(perm["trigger"], perm["pattern_description"], confidence=0.5, source="behavioral-intercept", entry_type="negative")
    csm.add_entry(perm2["trigger"], perm2["pattern_description"], confidence=0.5, source="behavioral-intercept", entry_type="negative")
    bi.log_outcome("permanent_p", "attempted")
    bi.log_outcome("permanent_p", "attempted")   # same day: one occurrence
    bi.log_outcome("permanent_q", "attempted", influenced=True)
    by = {e["tendency"]: e for e in csm.load_model()["entries"]}
    out.append(("the fixture holds two entries", len(by) == 2, list(by)))
    p, q = by.get(perm["pattern_description"], {}), by.get(perm2["pattern_description"], {})
    out.append(("a promoted permanent trial's later attempt reinforces its entry once a day",
                p.get("evidence_count") == 2 and abs(p.get("confidence", 0) - 0.56) < 1e-9, p))
    out.append(("an attempt under a live ban note is not evidence", q.get("evidence_count") == 1 and q.get("confidence") == 0.5, q))
    feeds = [c for c in POPEN if any("narrative-identity.py" in str(x) for x in c)]
    out.append(("the reinforcement lets narrative identity read the change", len(feeds) == 1, POPEN))
    # its entry was trimmed away; many attempts (some under ban notes) must not bring it back at 0.9
    reset_stores()
    _ledger([_trial("permanent_p", 8, promoted="2026-01-01T10:00:00")])
    bi.log_outcome("permanent_p", "attempted")
    E = csm.load_model()["entries"]
    out.append(("a re-added permanent-trial entry starts at 0.50", len(E) == 1 and abs(E[0]["confidence"] - 0.5) < 1e-9, E))
    # a default writes one structured blush per trial per day
    reset_stores()
    _ledger([_trial("trial_a", 0)])
    bi.log_outcome("trial_a", "defaulted")
    bi.log_outcome("trial_a", "defaulted")
    try:
        B = json.load(open(os.path.join(MEM, "blush-ledger.json")))
    except Exception as e:
        B = e
    out.append(("a default writes its blush, once per trial per day",
                isinstance(B, list) and [b.get("type") for b in B] == ["bis_default"], B))
    return out

# ------------------------------------------------------------------ trial extractor capacities
def g_te(te, csm):
    out = []
    reset_stores()
    out.append(("its capacity ledger is throwaway", te.CAP_LEDGER.startswith(HOME)))
    cap = lambda d: [{"capacity_key": "steady rhythm", "capacity_description": "keeps a steady rhythm in long replies " + d,
                      "evidence": "synthetic"}]
    D = lambda n: (datetime.now().date() - timedelta(days=n)).isoformat()
    te.write_capacities(cap("one"), "journal", D(3))
    te.write_capacities(cap("two"), "journal", D(2))
    E = csm.load_model()["entries"]
    out.append(("a capacity seen on two dates promotes at 0.50", len(E) == 1 and abs(E[0]["confidence"] - 0.5) < 1e-9, E))
    te.write_capacities(cap("three"), "journal", D(1))
    te.write_capacities(cap("three again"), "introspection", D(1))   # same date, another room: not a new date
    E = csm.load_model()["entries"]
    out.append(("a further date reinforces the promoted entry, once per date",
                len(E) == 1 and E[0]["evidence_count"] == 2 and abs(E[0]["confidence"] - 0.56) < 1e-9, E))
    te.write_capacities(cap("backlog"), "journal", D(90))   # an old session read late: a new date, but not fresh
    E = csm.load_model()["entries"]
    out.append(("an old date read late does not reinforce or freshen the entry",
                len(E) == 1 and E[0]["evidence_count"] == 2, E))
    # a promoted capacity whose entry is gone comes back at the promotion level, however many dates it has
    reset_stores()
    for n in range(8, 0, -1):
        te.write_capacities(cap("d%d" % n), "journal", D(n))
    json.dump({"entries": []}, open(csm.MODEL_FILE, "w"))
    te.write_capacities(cap("today"), "journal", D(0))
    E = csm.load_model()["entries"]
    out.append(("a re-added capacity entry starts at 0.50, not 0.3 + 0.1 per date",
                len(E) == 1 and abs(E[0]["confidence"] - 0.5) < 1e-9, E))
    legacy = {"key": "k", "promoted": True, "instances": [{"source_date": "d1", "description": "first"},
              {"source_date": "d1", "description": "same day"}, {"source_date": "d2", "description": "promoting"}]}
    out.append(("an older record names the instance that promoted it", te.promoted_tendency(legacy) == "promoting"))
    return out

# ------------------------------------------------------------------ narrative identity
T0 = datetime(2026, 3, 1, 12, 0, 0)
ENTRIES = []
def _e(conf, trig, tend, seen, n=1, typ="negative"):
    e = {"confidence": conf, "trigger": trig, "tendency": tend, "type": typ, "evidence_count": n,
         "formed": seen.isoformat(), "last_seen": seen.isoformat()}
    ENTRIES.append(e); return e

def g_ni(ni):
    out = []
    reset_stores(); del ENTRIES[:]
    sys.modules["causal_self_model"] = types.SimpleNamespace(load_model=lambda: {"entries": ENTRIES})
    ni._get_frame_conditions = lambda: ("", 0.5)
    out.append(("its store is throwaway", ni.NARRATIVE_FILE.startswith(HOME)))
    A = _e(0.5, "she comes home after a long shift", "filling the quiet with questions", T0 - timedelta(days=1))
    _e(0.49, "she laughs at the kettle", "making another kettle joke", T0)
    _e(0.8, "x", "Valence spike after music", T0)
    _e(0.5, "she sends a photo of rain", "describing the weather back at length", T0 - timedelta(days=40))
    t1 = ni.feed_from_causal_model(now=T0)
    out.append(("an entry at the earned 0.50 is eligible; 0.49 and metric entries are not",
                t1.get("eligible") == 2, t1))
    out.append(("an entry with no evidence in 30 days is not proposed", t1.get("stale") == 1 and t1.get("candidate_added") == 1, t1))
    t2 = ni.feed_from_causal_model(now=T0 + timedelta(hours=1))
    pool = ni.load_narrative().get("candidate_pool", [])
    out.append(("re-reading an unchanged entry is not repetition",
                t2.get("already_fed") == 1 and len(pool) == 1 and pool[0]["count"] == 1, (t2, pool)))
    A["evidence_count"] = 2; A["last_seen"] = (T0 + timedelta(days=1)).isoformat()
    t3 = ni.feed_from_causal_model(now=T0 + timedelta(days=1))
    A["evidence_count"] = 3; A["last_seen"] = (T0 + timedelta(days=2)).isoformat()
    t4 = ni.feed_from_causal_model(now=T0 + timedelta(days=2))
    d = ni.load_narrative(); frags = d.get("fragments", [])
    out.append(("three pieces of evidence over two days form one fragment",
                t3.get("candidate_reinforced") == 1 and t4.get("promoted") == 1 and len(frags) == 1, (t3, t4, frags)))
    out.append(("the fragment keeps the evidence it rests on",
                bool(frags) and len(frags[0].get("evidence", [])) == 3 and all(r["ref"].startswith("csm:") for r in frags[0]["evidence"]),
                frags))
    out.append(("it is offered while current", len(ni._current_fragments(d, now=T0 + timedelta(days=3))) == 1))
    later = T0 + timedelta(days=40)
    t5 = ni.feed_from_causal_model(now=later)
    d = ni.load_narrative()
    out.append(("after 30 days without evidence it is no longer offered, and nothing resurrects it",
                not ni._current_fragments(d, now=later) and d["fragments"][0]["count"] == 3 and not t5.get("reinforced"), (t5, d["fragments"])))
    A["evidence_count"] = 4; A["last_seen"] = later.isoformat()
    t6 = ni.feed_from_causal_model(now=later)
    d = ni.load_narrative()
    out.append(("fresh evidence brings it back", t6.get("reinforced") == 1 and len(ni._current_fragments(d, now=later)) == 1, t6))
    # stale candidates start over
    reset_stores(); del ENTRIES[:]
    ni.propose_fragment("I tend to hum while the pasta boils", now=T0)
    ni.propose_fragment("I tend to hum while the pasta boils", now=T0 + timedelta(days=1))
    r = ni.propose_fragment("I tend to hum while the pasta boils", now=T0 + timedelta(days=60))
    pool = ni.load_narrative().get("candidate_pool", [])
    out.append(("sightings from months ago do not combine with one fresh one",
                r == "candidate_reinforced" and pool and pool[0]["count"] == 1 and not ni.load_narrative().get("fragments"), (r, pool)))
    # the shared frame does not make unrelated entries alike
    reset_stores()
    ni.propose_fragment("I tend to avoid naps when tired", now=T0)
    r = ni.propose_fragment("I tend to avoid lists when busy", now=T0)
    out.append(("'I tend to avoid ... when' alone is not a match", r == "candidate_added", r))
    reset_stores()
    ni.propose_fragment("I tend to avoid asking for help when stressed", now=T0)
    r1 = ni.propose_fragment("I tend to asking for help when stressed", now=T0)
    r2 = ni.propose_fragment("I no longer struggle to enact: asking for help when stressed", now=T0)
    r3 = ni.propose_fragment("I tend to avoid asking for help when stressed", now=T0)
    out.append(("a fragment never reinforces its opposite",
                (r1, r2, r3) == ("candidate_added", "candidate_added", "candidate_reinforced"), (r1, r2, r3)))
    # among equals the most recently evidenced are proposed first
    reset_stores(); del ENTRIES[:]
    for i in range(10):
        _e(0.5, "trigger %d alpha" % i, "tendency %d beta" % i, T0 - timedelta(days=20 - i))
    ni.feed_from_causal_model(now=T0)
    fed = ni.load_narrative().get("fed_evidence", {})
    newest = ni._entry_ref(ENTRIES[-1])[0]
    out.append(("the newest evidence is not crowded out by the oldest", newest in fed and len(fed) == 8, len(fed)))
    return out

# ------------------------------------------------------------------ run: the code, then its mutants
def run(group, mods, label=""):
    res = group(*mods)
    return res

def report(res):
    for n, ok, *d in res:
        check(n, ok, d[0] if d else "")

csm = load("csm")
report(run(g_csm, [csm]))
csm = load("csm"); bi = load("bi")
report(run(g_bi, [bi, csm]))
csm = load("csm"); te = load("te")
report(run(g_te, [te, csm]))
ni = load("ni")
report(run(g_ni, [ni]))

MUTANTS = [
    ("csm", "empty triggers never match", ("t_overlap = 1.0", "t_overlap = 0.0"), g_csm),
    ("bi", "SCRIPTS undefined again", ('SCRIPTS = os.path.join(WORKSPACE, "scripts")\n', ""), g_bi),
    ("bi", "no reinforcement after promotion", ('elif (t.get("promoted")', 'elif False and (t.get("promoted")'), g_bi),
    ("bi", "no daily occurrence id", ('occurrence_id="bis:%s:%s" % (trial_id, datetime.now().date().isoformat()),\n                )\n                if _r',
                                      'occurrence_id=None,\n                )\n                if _r'), g_bi),
    ("te", "capacity dates after promotion dropped", ("elif rec[\"promoted\"] and new_date and _fresh_date(source_date):", "elif False:"), g_te),
    ("ni", "gate back to > 0.5", ("< FEED_MIN_CONFIDENCE", "<= FEED_MIN_CONFIDENCE"), g_ni),
    ("ni", "no evidence receipts", ("if fed.get(ref) == mark:", "if False:"), g_ni),
    ("ni", "stale entries proposed", ("if not seen or _days_since(seen, now) > FRAGMENT_STALE_DAYS:", "if not seen:"), g_ni),
    ("ni", "stale candidates keep counting", ('c["count"] = 0\n', "pass\n"), g_ni),
    ("ni", "template words match", (" - _TEMPLATE_WORDS", ""), g_ni),
    ("ni", "oldest first", ("eligible.sort(", "sorted("), g_ni),
    ("ni", "polarity ignored", ("    if _polarity(a) != _polarity(b):\n        return 0.0\n", ""), g_ni),
    ("te", "old capacity dates reinforce", (" and _fresh_date(source_date):", ":"), g_te),
    ("te", "re-add at 0.3 + 0.1 per date", ("confidence=0.5,   # only if", "confidence=min(0.9, 0.3 + len(dates) * 0.1),   # only if"), g_te),
    ("bi", "re-add at 0.3 + 0.1 per attempt", ("                    confidence=0.5,", "                    confidence=min(0.9, 0.3 + t.get('attempt_count', 0) * 0.1),"), g_bi),
]
for kind, name, mutation, group in MUTANTS:
    try:
        if kind == "csm":
            mods = [load("csm", mutation)]
        elif kind == "bi":
            c = load("csm"); mods = [load("bi", mutation), c]
        elif kind == "te":
            c = load("csm"); mods = [load("te", mutation), c]
        else:
            mods = [load("ni", mutation)]
    except Exception as e:
        check("mutant applies and loads: " + name, False, e)
        continue
    try:
        res = group(*mods)
        killed = not all(r[1] for r in res)
    except Exception as e:
        killed = True
    check("mutant killed: " + name, killed)

pe = open(os.path.join(REPO, "scripts", "pearl_engine.py")).read()
check("a formed pearl proposes its fragment with its candidate as evidence", 'evidence={"ref": "pearl:" + cand["id"]' in pe)
for a, b in (("scripts/behavioral_intercept.py", "bin/behavioral_intercept.py"), ("scripts/pearl_engine.py", "bin/pearl_engine.py")):
    check("%s matches its twin" % a, open(os.path.join(REPO, a)).read() == open(os.path.join(REPO, b)).read())

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
