#!/usr/bin/env python3
"""Review items 62, 63, 101, 162, 224, 330, 358, 376, 390 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p210-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()

print("\n--- 62 / 63: the turn record keeps excerpts, omission reasons, self-model revision, window ---")
TR = load("turn_record", os.path.join(REPO, "scripts", "turn_record.py")); TR.WORKSPACE = WS; TR.MEMORY = MEM
for a in dir(TR):
    v = getattr(TR, a)
    if isinstance(v, str) and a.isupper() and v.startswith(os.path.dirname(os.path.dirname(os.path.abspath(TR.__file__)))) : setattr(TR, a, v.replace(os.path.dirname(os.path.dirname(os.path.abspath(TR.__file__))), WS))
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("# me\n")
json.dump([{"timestamp": "t"}] * 3, open(os.path.join(MEM, "interaction-ledger.json"), "w"))
marker = next(iter(TR.MARKERS)); name = TR.MARKERS[marker]
TR.record("chat", "hello\n\n" + marker + " the first line of this block\nmore\n\nend", "hi")
rec_path = next((os.path.join(MEM, f) for f in os.listdir(MEM) if f.startswith("turn-record")), None)
row = json.loads(open(rec_path).readlines()[-1]) if rec_path else {}
check("the admitted block's excerpt is kept; absent blocks carry a reason", row.get("excerpts", {}).get(name, "").startswith(marker) and row.get("omitted") and all(v for v in row["omitted"].values()), (row.get("excerpts"), list(row.get("omitted", {}).items())[:2]))
check("the self-model revision and the ledger window are on the row", len(str(row.get("self_model_revision"))) == 12 and row.get("window", {}).get("ledger_rows") == 3, (row.get("self_model_revision"), row.get("window")))

print("\n--- 101: consent is three records ---")
cg = src("bin/consent-gate.sh")
check("consented / declined / unavailable each written to consent-decisions.jsonl", cg.count("_cg_log ") >= 3 and "_cg_log unavailable" in cg and "_cg_log declined" in cg and "_cg_log consented" in cg)

print("\n--- 162: unchanged sources are not re-inferred ---")
SC = load("source_cache", os.path.join(REPO, "scripts", "source_cache.py")); SC.MEMORY = MEM; SC.STORE = os.path.join(MEM, "source-cache.json")
check("failed attempts do not commit the cache", not SC.unchanged("job","abc") and not SC.unchanged("job","abc"))
SC.commit("job","abc")
check("only successful input is cached", SC.unchanged("job","abc") and not SC.unchanged("job","abd") and not SC.unchanged("job","abc",force=True) and SC.last("job")["sha"]==SC.sha_of("abc"))
check("the value map skips an unchanged context and says so", '_sc.unchanged("value-map", context)' in src("scripts/value_map.py") and "not re-inferred" in src("scripts/value_map.py"))

print("\n--- 330: the voice session is a state machine ---")
sv = src("bin/server.py")
check("open/active -> closing; a turn during closing is refused and recorded", 'sess["state"] = "active"' in sv and 'sess["state"] = "closing"' in sv and 'if sess.get("state") == "closing":' in sv and "voice-refused-turns.jsonl" in sv)
check("a stale 'closing' from a crash is resumed and finalized, not skipped forever", "resuming a stale" in sv and '"skipped": "already closing"' not in sv and "a finalization is in progress" in sv)

print("\n--- 358: a waiting seat keeps its draft ---")
seat = src("agent-room/seat.mjs")
check("the draft is generated once and held until the floor is his; new words invalidate it", "if (!draft) { heartbeat(true); try { draft = await reply(all); }" in seat and "pending = true; draft = null; }   // new words: any unsent draft is stale" in seat)

print("\n--- 376: health carries receipts ---")
HV = load("health_view", os.path.join(REPO, "scripts", "health_view.py")); HV.MEMORY = MEM; HV.WS = WS
open(os.path.join(MEM, "compute-ledger.jsonl"), "w").write(json.dumps({"organ": "x", "class": "paid", "stage": "reserved"}) + "\n")
v = HV.view()
check("delivery, effect and compute receipts are in the view", set(v["receipts"]) == {"delivery", "effects", "compute"} and v["receipts"]["compute"][0]["stage"] == "reserved")

print("\n--- 390: the proposal ledger as a join ---")
pl = src("agent-room/proposal-ledger.py")
check("each proposal is joined to its change, evidence and remaining work in <day>-proposals.json", '"evidence": _src' in pl and '"remaining": (f.get("and next", "")' in pl and 'f"{day}-proposals.json"' in pl)

print("\n--- 224: the five stages have fields ---")
doc = open(os.path.join(REPO, "docs", "want-lifecycle.md")).read()
check("intention, admission, attempt, outcome, revision each name their fields and writer", all(k in doc for k in ("**Intention**", "**Admission**", "**Actual attempt**", "**Observed outcome**", "**Revision**", "want_completion.complete", "lessons_from_attempts")))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
