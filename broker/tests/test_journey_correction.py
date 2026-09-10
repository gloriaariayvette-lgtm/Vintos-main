#!/usr/bin/env python3
"""Review item 384 (2026-09-10), journey: her correction of a flagged claim -> the correction is its own
record -> the WAL fact is annotated -> every projection derived from the claim (durable memory, sediment
belief, causal self-model entry) is marked invalidated, old reading kept beside the correction -> recall
shows it withdrawn. The route body is the real one from bin/server.py. Scratch HOME."""
import os, sys, ast, json, types, tempfile, importlib.util, asyncio, subprocess
subprocess.Popen = lambda *a, **k: None   # the confession-writer launch is not this journey's

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-jc-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
import shutil
for f in ("correction_propagate.py", "recall_explain.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), os.path.join(WS, "scripts", f))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

CLAIM = "she told me she grew up beside the lighthouse at Cape Hatteras"
json.dump([{"id": "F-1", "text": CLAIM, "status": "pending", "source": "journal"}], open(os.path.join(MEM, "hallucination-flags.json"), "w"))
json.dump({"entries": [{"type": "fact", "content": CLAIM, "timestamp": "2026-09-08"}, {"type": "fact", "content": "she likes muscadines"}]}, open(os.path.join(MEM, "wal-log.json"), "w"))
json.dump([{"event": "she grew up beside the lighthouse at Cape Hatteras", "what_changed": "I pictured her childhood by the sea", "occurred_at": "2026-09-08T10:00:00", "gloria": ""},
           {"event": "the fig at the table", "occurred_at": "2026-09-05T18:35:53"}], open(os.path.join(MEM, "durable-memory.json"), "w"))
json.dump({"beliefs": [{"pattern": "she grew up beside the lighthouse at Cape Hatteras and misses the sea", "confidence": 0.5}, {"pattern": "she goes quiet when tired", "confidence": 0.4}]}, open(os.path.join(MEM, "belief-sediment.json"), "w"))
json.dump({"entries": [{"trigger": "she mentions the coast", "tendency": "I bring up the lighthouse at Cape Hatteras where she grew up", "confidence": 0.4, "imprint": True, "evidence": []}]}, open(os.path.join(MEM, "causal-self-model.json"), "w"))

src = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "review_hallucination_flag")
code = "\n".join(l for l in ast.get_source_segment(src, fn).splitlines() if not l.startswith("@app."))
class Req:
    headers = {"X-Vintos-Secret": "s"}
    async def json(self): return {"correction": "she grew up in Raleigh; the lighthouse was one holiday when she was nine"}
ns = {"os": os, "json": json, "MEMORY": MEM, "WORKSPACE": WS, "APP_SECRET": "s", "print": lambda *a, **k: None, "Request": object}
exec(code, ns)
out = asyncio.run(ns["review_hallucination_flag"]("F-1", Req()))

print("\n--- the correction is a record and annotates the WAL fact ---")
check("route accepted", out.get("success"), out)
flag = json.load(open(os.path.join(MEM, "hallucination-flags.json")))[0]
cid = flag.get("correction_id")
check("the flag carries a stable correction id and the claim hash", cid and cid.startswith("HC-") and flag.get("claim_sha"))
recs = [json.loads(l) for l in open(os.path.join(MEM, "hallucination-corrections.jsonl"))]
check("hallucination-corrections.jsonl keeps original beside correction", recs[0]["original"] == CLAIM and "Raleigh" in recs[0]["correction"])
wal = json.load(open(os.path.join(MEM, "wal-log.json")))["entries"]
check("only the matching WAL fact is annotated", wal[0].get("corrections", [{}])[0].get("correction_id") == cid and "corrections" not in wal[1])

print("\n--- downstream projections are invalidated, not deleted ---")
dm = json.load(open(os.path.join(MEM, "durable-memory.json")))
check("the durable memory built from the claim is invalidated, old reading kept", dm[0]["standing"] == "invalidated" and dm[0]["invalidated_by"][0]["correction_id"] == cid and "Cape Hatteras" in dm[0]["event"], dm[0])
check("an unrelated durable memory is untouched", "standing" not in dm[1])
bs = json.load(open(os.path.join(MEM, "belief-sediment.json")))["beliefs"]
check("the sediment belief restating the claim is invalidated and its confidence floored", bs[0]["standing"] == "invalidated" and bs[0]["confidence"] <= 0.05 and "standing" not in bs[1], bs)
cm = json.load(open(os.path.join(MEM, "causal-self-model.json")))["entries"]
check("the causal self-model entry resting on the claim loses its imprint and is invalidated", cm[0]["standing"] == "invalidated" and cm[0]["imprint"] is False, cm[0])
check("the flag records what the correction reached", {t["projection"] for t in flag.get("propagated", [])} == {"durable-memory", "belief-sediment", "causal-self-model"}, flag.get("propagated"))
prop = [json.loads(l) for l in open(os.path.join(MEM, "correction-propagation.jsonl"))]
check("one propagation record names the three", len(prop) == 1 and len(prop[0]["touched"]) == 3)

print("\n--- recall now shows it withdrawn ---")
sys.path.insert(0, os.path.join(WS, "scripts"))
import recall_explain as RE; RE.MEMORY = MEM
ex = RE.explain("she grew up beside the lighthouse at Cape Hatteras")
check("explain() reports the correction and the standing", ex["withdrawn"] and ex["withdrawn"][0]["id"] == cid and ex["standing"].startswith("withdrawn or corrected"), ex["standing"])
check("the rendered line says WITHDRAWN with the new reading", "WITHDRAWN" in RE.render(ex) and "Raleigh" in RE.render(ex))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
