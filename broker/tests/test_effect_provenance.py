#!/usr/bin/env python3
"""Review items 74, 77, 93, 95, 97, 98, 110, 112, 128, 140, 148, 152, 157 (2026-09-10). Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ep-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".vintos"), exist_ok=True); open(os.path.join(HOME, ".vintos", ".lineage-key"), "w").write("a-house-key")
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy", "serial"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 74: an unreachable gate is not permission ---")
rc = src("scripts/robot_core.py")
sys.path.insert(0, os.path.join(REPO, "scripts"))
assert os.path.commonpath([MEM, HOME]) == HOME
EA = load("effect_authority", os.path.join(REPO, "scripts", "effect_authority.py"))
sys.modules["effect_gate"] = types.ModuleType("effect_gate")
check("a deliberative move is refused when the gate is unavailable; a reduction still passes", not EA.dispatch("robot", kind="move")[0] and EA.dispatch("robot", kind="stop")[0])
check("simulation never becomes outward dispatch", EA.dispatch("outward", authority=lambda: (True, "would_send", "test"))[0] is False)
check("outward requires its caller's authority", not EA.dispatch("outward")[0] and EA.dispatch("outward", authority=lambda: (True, "approved"))[0])
check("a missing toy gate never grants a positive command", not EA.dispatch("toys", target="mission", level=8)[0] and EA.dispatch("toys", target="mission", level=0)[0])
seen = []
sys.modules["effect_gate"].hardware_stopped = lambda: False
sys.modules["effect_gate"].dispatch_check = lambda permit, target, level, kind, digest: (seen.append((permit,target,level,kind,digest)) or (False,"wrong digest"))
check("central door preserves the exact bound permit and digest", not EA.dispatch("toys", target="mission", level=4, permit="permit", digest="digest")[0] and seen == [("permit","mission",4,None,"digest")])

print("\n--- 77 / 93: one physical contract ---")
PC = load("physical_contract", os.path.join(REPO, "scripts", "physical_contract.py"))
e = PC.effect("EF-1", "mission", 12, kind="deliberate", permit_digest="d1", turn_id="T1")
check("an effect starts requested, queued and unobserved, carrying its permit", e["accepted"]["state"] == "queued" and e["observed"]["state"] == "pending" and e["permit_digest"] == "d1")
PC.accept(e, "accepted", by="hub", why="")
check("acceptance is the transport's word, timed", e["accepted"]["state"] == "accepted" and e["accepted"]["at"] and e["observed"]["state"] == "pending")
try: PC.observe(e, "observed", by="somatic"); check("an observation without evidence is refused", False)
except ValueError: check("an observation without evidence is refused", True)
PC.observe(e, "observed", by="somatic", evidence="stroking began 2s after the send")
check("an observation needs an independent witness and keeps it", e["observed"]["state"] == "observed" and "stroking" in e["observed"]["evidence"])
o = PC.observation(0.7, "mission", sampled_at=time.time() - 3, window_s=2.0, calibration="interim", stream="somatic")
check("an observation says when the world produced it, its window, device, calibration and freshness", o["freshness_s"] >= 3 and o["window_s"] == 2.0 and o["calibration"] == "interim" and o["device"] == "mission")
j = PC.joined([e], [o], within_s=30)
check("a join is proximity, and says so", j[0]["note"].startswith("proximity in time only"))
check("effect_gate offers the shape and somatic classification carries the observation contract", "def physical_record" in src("scripts/effect_gate.py") and '"contract": "physical-observation-1"' in src("scripts/somatic_bridge.py"))

print("\n--- 95: one dispatch and stop authority, sensor apart from actuator ---")
EA = load("effect_authority", os.path.join(REPO, "scripts", "effect_authority.py"))
check("every lane names its dispatcher, gate and stop; sensor lanes dispatch nothing", all(v["gate"] and v["stop"] for v in EA.LANES.values()) and all(v["dispatch"] is None for k, v in EA.LANES.items() if v["kind"] == "sensor"))
check("a target resolves to its lane", EA.lane_of("mission") == "toys" and EA.lane_of("thruster") == "thruster" and EA.lane_of("heart-rate") == "ring")
ok, why = EA.assert_dispatch("somatic", target="mission", level=5)
check("a sensor lane refuses to dispatch", ok is False and "never dispatches" in why)
ok, why = EA.assert_dispatch("nowhere")
check("an unnamed lane refuses", ok is False and "must name its lane" in why)
sys.modules["effect_gate"] = types.ModuleType("effect_gate"); sys.modules["effect_gate"].hardware_stopped = lambda: True
sys.modules["effect_gate"].authorize = lambda *a, **k: (None, "send", "")
ok, why = EA.assert_dispatch("toys", target="mission", level=8)
check("a stopped house refuses an actuator lane", ok is False and "the house is stopped" in why)

print("\n--- 98: a refused private write is sealed, never in the clear ---")
SR = load("sealed_retry", os.path.join(REPO, "scripts", "sealed_retry.py")); SR.MEMORY = MEM; SR.SEALED = os.path.join(MEM, "atelier-sealed"); SR.KEYFILE = os.path.join(HOME, ".vintos", ".lineage-key")
sid = SR.seal("p1", "write", "the private piece", "broker refused: budget spent")
raw = open(os.path.join(SR.SEALED, sid + ".json")).read()
check("no plaintext on disk; the listing carries no content", "the private piece" not in raw and set(SR.pending()[0]) == {"id", "project", "kind", "why", "at", "bytes"})
got = {}
res = SR.retry(sid, lambda p, k, c: got.setdefault("c", c) or True)
check("retry hands the opened bytes to the sender and unseals on success", got["c"] == "the private piece" and res["state"] == "sent" and not os.path.exists(os.path.join(SR.SEALED, sid + ".json")))
sid2 = SR.seal("p2", "write", "another piece", "refused again")
res2 = SR.retry(sid2, lambda p, k, c: False)
check("a failed retry leaves it sealed", res2["state"] == "still_sealed" and os.path.exists(os.path.join(SR.SEALED, sid2 + ".json")))
rec = json.load(open(os.path.join(SR.SEALED, sid2 + ".json"))); rec["sealed"] = rec["sealed"][:-4] + "AAAA"
json.dump(rec, open(os.path.join(SR.SEALED, sid2 + ".json"), "w"))
try: SR.retry(sid2, lambda *a: True); check("a tampered seal is refused", False)
except ValueError as ex: check("a tampered seal is refused", "mac" in str(ex))
check("the visit seals a refused piece instead of printing it", "def _seal_refused" in src("scripts/atelier-visit.py") and "not shown" in src("scripts/atelier-visit.py"))

print("\n--- 110 / 148: tactical material is never evidence and never graduates ---")
EP = load("evidence_provenance", os.path.join(REPO, "scripts", "evidence_provenance.py"))
check("ghosts, trials, stratagems and rehearsals are tactical; a lived turn is not", EP.is_tactical("ghost_branch") and EP.is_tactical("shadow_trial") and not EP.is_tactical("chat") and EP.can_be_evidence("ghost:axis1")[0] is False and EP.can_be_evidence("chat")[0])
check("a ghost's own recurrence mark is tactical and does not count toward graduation", '"counts_toward_graduation": not _tactical' in src("scripts/ghost-branches.py") and 'm.get("counts_toward_graduation", True) and not m.get("tactical")' in src("scripts/causality-engine.py"))

print("\n--- 112: missing provenance stays legacy ---")
check("a caller with no envelope reads as legacy, never as a witnessed turn", '"surface": "legacy"' in src("scripts/evidence_provenance.py") and '"envelope_state": "absent_legacy"' in src("scripts/evidence_provenance.py"))

print("\n--- 140: a residual is a model error, not a trait ---")
check("the self-model update frames the blind-spot numbers as forecast error", "not a trait, a flaw or a diagnosis" in src("bin/self-model-update.sh"))

print("\n--- 157: one arithmetic ---")
TS = load("text_similarity", os.path.join(REPO, "scripts", "text_similarity.py"))
check("cosine is total: empty, mismatched and zero vectors are 0.0, never an exception", TS.cosine([1, 0], [1, 0]) == 1.0 and TS.cosine([], [1]) == 0.0 and TS.cosine([0, 0], [1, 1]) == 0.0 and TS.cosine([1, 2], [1]) == 0.0)
check("overlap and jaccard agree on content words", TS.overlap("the fig at the table", "a fig on a table") == 1.0 and TS.jaccard("table chair", "table stool") == 1 / 3)
shimmed = [f for f in ("scripts/memory-search.py", "scripts/latent_threads.py", "scripts/resonance_pulse.py", "scripts/emotional_entanglement.py", "scripts/resonance_afterglow.py") if "from text_similarity import cosine as _cos" in src(f)]
check("the biggest duplicate definitions now defer to it, keeping their own names", len(shimmed) == 5, shimmed)

print("\n--- 128 / 152: the contracts page and the corrected texts ---")
doc = open(os.path.join(REPO, "docs", "index-write-contracts.md")).read()
check("every store names its writer, what a write means, what a reader may assume, and the bypasses", all(k in doc for k in ("semantic-index.json", "commitment-imprints.json", "unfinished-threads.json", "A write means", "Bypass")))
check("the stale design claims are corrected by name", all(k in doc for k in ('"consumed = resolved"', "defaults to yes when it cannot be reached", "variance-qualified forecast is calibrated", "a send is a reception", "a residual is a trait")))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
