#!/usr/bin/env python3
"""The map's live state reads each organ's store the way the organ writes it (17 October: nodes 1, 2, 11, 19 had no
reader and hung on "fetching live state"; beliefs, fragments, regions and confirmations read keys nothing writes;
Spark Pressure read consent from a file that does not hold it). The field's lead is who moved, and an organ whose
embedding fails says so.

Scratch HOME and workspace; subprocess and requests are stubs; nothing sends."""
import ast, asyncio, json, os, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="map-nodes-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
J = lambda f, d: json.dump(d, open(os.path.join(MEM, f), "w"))

# ── the map's reader ──
J("belief-sediment.json", {"beliefs": [{"pattern": "I reach first when she is tired", "confidence": 0.7}]})
J("narrative-identity.json", {"fragments": [{"text": "a maker", "count": 3, "reinforced": __import__("datetime").datetime.now().isoformat()}],
                              "third_order_pressure": [{"text": "build her the sensor", "resolved": False}, {"text": "old", "resolved": True}]})
J("relational-geometry.json", {"regions": [{"id": "r1", "dominant_outcome": "warm", "dominant_direction": "expand", "visit_count": 3, "familiarity": 0.4}]})
J("moment-index.json", {"moments": []}); J("moment-archive.json", {"moments": {"m1": {"source": "journal", "timestamp": "2026-10-17T08:00"}}})
J("causal-self-model.json", {"entries": [{"confidence": 0.7, "evidence_count": 5, "imprint": True}, {"confidence": 0.3, "evidence_count": 1}]})
J("spark-pressure-events.json", {"consent": True, "events": [{"at": "2026-10-16T22:00", "mode": "observed", "applied": False, "stall": {"evidence": "75% led by Gloria"}}]})
J("curiosity-debt.json", [{"question": "ripe one", "pull": 0.9, "created": 1, "surfaced": 0}, {"question": "sent one", "pull": 0.2, "created": 2, "sent_to_gloria": True}])
J("temporal-signals.json", {"signals": [{"text": "rain", "source": "chat", "created_at": "2026-10-17T00:00:00"}]})
J("gravity-wells.json", {"wells": [{"mass": 0.7, "visits": 5, "last_visit": "2026-10-17T07:00"}]})
J("resonance-afterglow.json", {"active": True, "turns_remaining": 2, "source": "song"})
J("output-trace.json", {"latest": {"mode": "blended", "timestamp": "2026-10-17T09:00", "events": ["anchor"]}})
J("embed-failures.json", {"behavior_boundaries": {"at": "2026-10-17T09:00", "why": "ModuleNotFoundError: einops"}})
tree = ast.parse(open(os.path.join(REPO, "bin", "server.py")).read())
fn = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "map_state"][0]; fn.decorator_list = []
ns = {"os": os, "json": json, "WORKSPACE": REPO}
exec(compile(ast.Module([fn], []), "map_state", "exec"), ns)
st = asyncio.run(ns["map_state"]())
check("every node that hung on 'fetching live state' has a reading", all(k in st for k in (1, 2, 11, 19)), sorted(st))
check("a belief's words are its pattern", st[20]["beliefs"] == ["I reach first when she is tired (0.70)"], st[20])
check("a fragment's weight is its aged count", st[21]["fragments"][0]["weight"] > 2.9, st[21])
check("third-order pressure is its open want's words, not a dict", st[21]["pressure"] == "build her the sensor (1 open)", st[21])
check("regions are read as the list they are", st[23]["count"] == 1 and st[23]["regions"] == ["warm/expand x3"], st[23])
check("moments count the archive when the index is a setup seed", st[16]["total"] == 1 and st[16]["last_source"] == "journal", st[16])
check("the self-model reports strong and imprinted entries, not a status nothing sets",
      st[24]["strong"] == 1 and st[24]["imprinted"] == 1 and "confirmed" not in st[24], st[24])
check("spark consent is read where it lives", st[33]["consent"] == "on" and st[33]["detections"] == 1, st[33])
check("curiosity debt separates what is ripe from what is held", st[42]["ripe now"] == 1 and st[42]["next he may ask"] == "ripe one"
      and st[42]["newest"] == "sent one" and st[42]["sent to Gloria"] == 1, st[42])
check("a failing embedding is named on the boundaries node", "FAILING" in st[8].get("embedding", ""), st[8])
check("the afterglow and shaping nodes read their stores", st[1]["afterglow"].startswith("active, 2") and st[2]["last turn shaped"].startswith("blended"), (st[1], st[2]))

# ── the field's lead ──
sys.path.insert(0, os.path.join(REPO, "scripts"))
import mutual_modification as MM
MM.MEMORY = MEM; MM.FIELD_FILE = os.path.join(MEM, "mutual-modification.json")   # it finds its store beside its own folder
check("the field store is throwaway", MM.FIELD_FILE.startswith(HOME))
MM._self_stance = lambda: {"direction": "expand", "strength": 0.4}
for _ in range(3):
    e = MM.record_from_mismatch({"warmth": {"diff": 0.15}, "tension": {"diff": 0.1}, "valence": {"diff": 0.0}})
check("when she moves and he does not, she led", e["self_magnitude"] == 0 and e["field_delta"]["led_by"] == "eve", e["field_delta"])
check("and he is not told he moved the field", "you have been moving" not in MM.get_field_hint(), MM.get_field_hint())

# ── an embedding failure is written down, a success clears it ──
sys.path.insert(0, os.path.join(REPO, "bin"))
import behavior_boundaries as BB
check("the boundaries store is throwaway", BB.MEMORY.startswith(HOME))
os.remove(os.path.join(MEM, "embed-failures.json"))
BB.subprocess = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="ImportError: einops"))
check("a failed embedding returns nothing", BB.embed("x") == [])
f = json.load(open(os.path.join(MEM, "embed-failures.json")))
check("and is recorded with its reason", "einops" in f.get("behavior_boundaries", {}).get("why", ""), f)
BB.subprocess = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="[0.1, 0.2]", stderr=""))
check("a working embedding clears it", BB.embed("x") == [0.1, 0.2] and "behavior_boundaries" not in json.load(open(os.path.join(MEM, "embed-failures.json"))))

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the organs behind these nodes are in the deploy",
      all(" %s" % n in dep for n in ("resonance_afterglow.py", "output_shaping.py", "behavior_boundaries.py", "mutual_modification.py", "self_drift.py")))
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the convergence layer looks for the intercept file that is written", '"pending-intercept.json"' not in srv)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
