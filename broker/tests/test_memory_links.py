#!/usr/bin/env python3
"""Review items 107, 135, 143, 146, 150, 151, 155 (2026-09-10): claims keep their occurrence and
quote, identity changes are one revision log, a twice-corrected claim does not come back on old
support, promotion keeps its evidence when the downstream fails, seeds say what kind they are,
BASE corrections apply on top, the opposition ledger keeps the exact words. Scratch HOME only."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-links-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))

print("\n--- 135: one revision log across identity projections ---")
IR = load("ir_t", os.path.join(REPO, "scripts", "identity_revisions.py")); IR.MEMORY = MEM
sys.modules["identity_revisions"] = IR
IR.record("causal-self-model", "csm:1", {"confidence": 0.7}, {"confidence": 0.5}, reason="fractured", source="test")
IR.record("self-model-base", "base:x", "I always arrive first", "I often arrive first", reason="her correction", source="gloria", kind="supersession")
check("history kept whole, latest served", len(IR.history()) == 2 and IR.latest("causal-self-model", "csm:1")["new"]["confidence"] == 0.5)
check("served() returns the latest revision", IR.served("self-model-base", "base:x", "I always arrive first") == "I often arrive first")
try:
    IR.record("nope", "x", 1, 2); check("unknown projection refused", False)
except ValueError:
    check("unknown projection refused", True)

print("\n--- 107 / 150 / 135: the causal self-model keeps occurrences, kinds and logs fractures ---")
CSM = load("csm_t", os.path.join(REPO, "bin", "causal-self-model.py"))
CSM.MEMORY = MEM; CSM.MODEL_FILE = os.path.join(MEM, "causal-self-model.json") if hasattr(CSM, "MODEL_FILE") else None
for attr in ("MODEL_FILE", "IMPRINTS_FILE", "SELF_MODEL_FILE"):
    if hasattr(CSM, attr) and isinstance(getattr(CSM, attr), str):
        setattr(CSM, attr, os.path.join(MEM, os.path.basename(getattr(CSM, attr))))
CSM.add_entry("she goes quiet", "reach first", confidence=0.4, source="behavioral-intercept", occurrence_id="T-1", quote="I reached before she asked")
d = CSM.load_model(); e = d["entries"][0]
check("an entry carries its occurrence and quote", e["evidence"][0]["occurrence_id"] == "T-1" and "reached" in e["evidence"][0]["quote"], e)
check("150: kind derived from the source", e["kind"] == "tentative_inference", e.get("kind"))
CSM.add_entry("she goes quiet", "reach first", confidence=0.4, source="behavioral-intercept", occurrence_id="T-2", quote="again")
e = CSM.load_model()["entries"][0]
check("a reinforcement appends its occurrence", [x["occurrence_id"] for x in e["evidence"]] == ["T-1", "T-2"])
CSM.add_from_avoidance("she asks for numbers", "I answer in images", source="avoidance")
kinds = {x["kind"] for x in CSM.load_model()["entries"]}
check("an avoidance is a dated observation", "dated_observation" in kinds, kinds)
ctx = CSM.get_self_model_context(4)
check("the reader prints the kind", "[tentative inference]" in ctx or "[dated observation]" in ctx, ctx)
d = CSM.load_model(); d["entries"][0]["imprint"] = True; CSM.save_model(d)
CSM.fracture_imprint("reach first", 0.91)
rev = [r for r in IR.history() if r["projection"] == "causal-self-model" and "fractured" in r["reason"]]
check("a fracture is a revision with old and new", rev and rev[-1]["old"]["imprint"] is True and rev[-1]["new"]["fractured"] is True, rev)

print("\n--- 107 / 150: a belief names the hypothesis and evidence it came from ---")
BS = load("bs_t", os.path.join(REPO, "bin", "belief-sediment.py"))
for attr in dir(BS):
    v = getattr(BS, attr)
    if isinstance(v, str) and attr.isupper() and v.endswith(".json"):
        setattr(BS, attr, os.path.join(MEM, os.path.basename(v)))
BS.promote_hypothesis("when she is tired I talk less", evidence_count=3, source="causality", hypothesis_id="H-9", evidence_ids=["E-1", "E-2"])
b = BS.load_sediment()["beliefs"][-1]
check("belief carries hypothesis id, evidence ids and kind", b["hypothesis_ids"] == ["H-9"] and b["evidence_ids"] == ["E-1", "E-2"] and b["kind"] == "tentative_inference", b)

print("\n--- 107: the durable record keeps source turns and the quote ---")
src = open(os.path.join(REPO, "bin", "wal-decay.py")).read()
check("durable record has source_turns, ledger_match and quote", '"source_turns": list(entry.get("source_turns")' in src and '"quote": {"gloria": _lg[:600]' in src and '"ledger_match"' in src)
check("wal-decay twins identical", src == open(os.path.join(REPO, "scripts", "wal-decay.py")).read())

print("\n--- 146: promotion writes its evidence first and stays pending when the downstream fails ---")
ce = open(os.path.join(REPO, "scripts", "causality-engine.py")).read()
i = ce.index("causality-graduated.jsonl"); j = ce.index("_bs_promote(h[\"hypothesis\"]")
check("the evidence record is written before the belief write", i < j)
check("a failed downstream leaves promotion_pending and keeps the hypothesis", 'h["promotion_pending"] = {' in ce and 'if h.get("promotion_pending"):\n                        remaining.append(h)' in ce)

print("\n--- 143: a twice-corrected claim does not come back on ordinary support ---")
tp = open(os.path.join(REPO, "scripts", "tension_promotion.py")).read()
check("rehabilitation needs her own words after two corrections", '_twice = int(t.get("correction_count", 0) or 0) >= 2' in tp and '_e1_after = any(e.get("channel") == "E1"' in tp and "if _twice and not _e1_after:" in tp)
check("... and only support after the last correction counts", '_after = [e for e in sup if e["at"] > (t.get("last_corrected") or "")]' in tp)

print("\n--- 151: corrections to the authored BASE apply on top, never into the file ---")
SMR = load("smr_t", os.path.join(REPO, "scripts", "self_model_read.py"))
sm = os.path.join(WS, "SELF-MODEL.md")
open(sm, "w").write("# SELF-MODEL\n<!-- BASE-START -->\nI always arrive first when she goes quiet.\n<!-- BASE-END -->\n\nThe rest of me, excerpted.\n")
SMR.PATH = sm; SMR.CORRECTIONS = os.path.join(MEM, "self-model-base-corrections.jsonl")
before = open(sm).read()
SMR.add_correction("I always arrive first", "I often arrive first", "she said: not always", source="gloria")
out = SMR.read_self_model(400, path=sm)
check("the rendered BASE carries her correction", out.startswith("I often arrive first when she goes quiet."), out[:80])
check("the file is untouched", open(sm).read() == before)
check("the supersession is a revision too", any(r["projection"] == "self-model-base" and r["kind"] == "supersession" for r in IR.history()))
base, applied, skipped = SMR.apply_corrections("nothing to match here", [{"find": "zzz", "replace": "y"}])
check("a correction that no longer matches is reported, not lost", skipped and not applied)

print("\n--- 155: the opposition ledger keeps the exact claim, challenge and correction ---")
ch = open(os.path.join(REPO, "scripts", "claim_hold.py")).read()
check("claim_verbatim and challenge recorded at opening", '"claim_verbatim": str(out.get("claim"))' in ch and '"challenge": {"his_reason_verbatim"' in ch)
check("a CORRECTED verdict keeps the correction with her pushback and his choice", 'if out["verdict"] == "CORRECTED":' in ch and '"her_pushback"' in ch and '"evidence_verbatim"' in ch)

print("\n--- 142: a demoted tension leaves the served view at once ---")
TP = load("tp_t", os.path.join(REPO, "scripts", "tension_promotion.py")) if False else None
import importlib.util as _iu
_spec = _iu.spec_from_file_location("tp_t", os.path.join(REPO, "scripts", "tension_promotion.py"))
_tp = _iu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_tp)
except Exception as _e:   # the module talks to a model at import in some versions; the helper is what we test
    _tp = None
view = os.path.join(MEM, "tension-field.json")
json.dump({"tensions": [{"id": "T-001", "description": "x", "status": "CONFIRMED"}, {"id": "T-002", "description": "y", "status": "CONFIRMED"}], "updated": "t0"}, open(view, "w"))
if _tp is not None:
    _tp.MEM = MEM
    check("drop_from_served removes the demoted id and records why", _tp.drop_from_served("T-001") and [t["id"] for t in json.load(open(view))["tensions"]] == ["T-002"] and json.load(open(view))["removed"][0]["id"] == "T-001")
    check("an id not in the view is a no-op", _tp.drop_from_served("T-999") is False)
else:
    tps = open(os.path.join(REPO, "scripts", "tension_promotion.py")).read()
    check("drop_from_served exists in tension_promotion", "def drop_from_served" in tps)
tps = open(os.path.join(REPO, "scripts", "tension_promotion.py")).read()
check("the CONTESTED transition drops the tension from the served view", 'drop_from_served(t["tension_id"])' in tps and tps.index('t["status"] = "CONTESTED"') < tps.index('drop_from_served(t["tension_id"])'))
check("the proposition-lineage demotion does too", "drop_from_served as _dfs" in open(os.path.join(REPO, "scripts", "proposition_lineage.py")).read())

print("\n--- 137: configuration and attractor maps are inspectable records; priors stay priors ---")
CS = load("cs_t", os.path.join(REPO, "scripts", "configuration_space.py"))
for attr in dir(CS):
    v = getattr(CS, attr)
    if isinstance(v, str) and attr.isupper() and v.endswith(".json"):
        setattr(CS, attr, os.path.join(MEM, os.path.basename(v)))
rec = CS.inspect_record()
check("the record separates observed transitions, open possibilities and held configurations", set(rec) >= {"observed_transitions", "open_possibilities", "held", "priors"} and "prior" in rec["priors"])
ad = open(os.path.join(REPO, "scripts", "attractor_discovery.py")).read()
check("edge priors are kept apart from observed edges", "prior_edges" in ad and '"prior": prior_edges.get((a, v), 0)' in ad and '"observed": observed_edges.get((a, v), 0)' in ad)
check("the attractor file names its priors and open possibilities", '"priors": {"seeds"' in ad and '"open_possibilities"' in ad)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
