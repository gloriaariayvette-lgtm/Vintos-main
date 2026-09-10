#!/usr/bin/env python3
"""Review items 75, 79, 81, 91, 103, 147 (2026-09-10): permits are payload-bound by digest; paid or
remote work reserves against the day's budget first; an unavailable broker is never "no project"; a
device receipt names the permit it executed under; a failed embedding marks its chunk; a correction
after graduation reaches the pearls. Scratch HOME; no network."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-pc-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "pearls"), exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()

print("\n--- 75: a permit is bound to its payload digest ---")
EG = load("effect_gate", os.path.join(REPO, "scripts", "effect_gate.py"))
for a in dir(EG):
    v = getattr(EG, a)
    if isinstance(v, str) and a.isupper() and v.startswith("/") and ".vintos" in v: setattr(EG, a, os.path.join(MEM, os.path.basename(v)))
P = EG.Permit if hasattr(EG, "Permit") else None
eg = src("scripts/effect_gate.py")
check("a permit carries a digest and dispatch refuses a mismatch by name", 'return "permit_digest_mismatch"' in eg and "digest-bound permit is unusable unless the executor carries the" in eg)
check("the gate tests exercise the digest", "digest" in src("broker/tests/test_effect_gate.py") and "digest" in src("broker/tests/test_p03_device_execution.py"))

print("\n--- 79: paid work reserves first ---")
CA = load("compute_admission", os.path.join(REPO, "scripts", "compute_admission.py")); CA.MEMORY = MEM if hasattr(CA, "MEMORY") else None
CA._ledger = lambda: os.path.join(MEM, "compute-ledger.jsonl")
ok1, w1 = CA.reserve_paid("router", "xai", "grok-4", cap=2); ok2, w2 = CA.reserve_paid("router", "xai", "grok-4", cap=2); ok3, w3 = CA.reserve_paid("router", "xai", "grok-4", cap=2)
check("two reservations fit a cap of two; the third is refused by name and recorded", ok1 and ok2 and not ok3 and w3.startswith("paid budget: 2 of 2") and CA.paid_today("xai") == 2, (w1, w2, w3))
rows = [json.loads(l) for l in open(CA._ledger())]
check("reserved and refused are both in the ledger as class paid", [r["stage"] for r in rows if r["class"] == "paid"] == ["reserved", "reserved", "refused"])
check("a different provider has its own count", CA.reserve_paid("router", "anthropic", "x", cap=2)[0])
mr = src("bin/model_router.py")
check("the router reserves before every provider stage and holds when refused", '_ca.reserve_paid("model_router:%s" % surface, "xai", grok_model)' in mr and 'status="held", reason=_why' in mr)

print("\n--- 81: unavailable broker is not no project ---")
AL = load("atelier_ledger", os.path.join(REPO, "scripts", "atelier_ledger.py"))
st = AL.broker_state(base="http://127.0.0.1:1", timeout=1)
check("a dead socket says unavailable, project None, with the reason", st["broker"] == "unavailable" and st["project"] is None and st.get("why"), st)
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def _w(self, b): self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._w(b'{"active": false}')
    def do_POST(self): self._w(b'{"id": null}' if self.path == "/worktable" else b'{}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
st2 = AL.broker_state(base="http://127.0.0.1:%d" % srv.server_port, timeout=2); srv.shutdown()
check("a live broker with nothing tabled says up, project None", st2["broker"] == "up" and st2["project"] is None, st2)

print("\n--- 91: the receipt names the permit ---")
logged = []
EG._log = lambda **row: logged.append(row)
class Ctx: turn_id = "T-91"
class Pm: effect_id = "EF-1"; digest = "d1"
EG.send_result(Ctx(), "lush", True, "", permit=Pm()); EG.send_result(Ctx(), "lush", False, "not connected")
check("a receipt under a permit carries the effect id and digest; a bare one carries None", logged[0]["effect_id"] == "EF-1" and logged[0]["permit_digest"] == "d1" and logged[1]["effect_id"] is None and logged[1]["turn_id"] == "T-91", logged)
check("toy_link passes the permit into every receipt", src("scripts/toy_link.py").count(", permit=permit)") >= 5)

print("\n--- 103: a failed embedding marks its chunk ---")
mi = src("scripts/memory-index.py")
check("the indexer keeps the chunk with embed_failed and no vector and counts it", '"embed_failed": _fail or None' in mi and 'stats["embed_failed"]' in mi)
check("the reader never serves a chunk without a vector", 'not e.get("embedding") or e.get("tombstone")' in src("scripts/memory-search.py"))

print("\n--- 147: a correction after graduation reaches the pearl ---")
CP = load("correction_propagate", os.path.join(REPO, "scripts", "correction_propagate.py")); CP.MEMORY = MEM
pf = os.path.join(MEM, "pearls", "pearl_20260901_120000.md"); open(pf, "w").write("# Pearl\n\nshe grew up beside the lighthouse at Cape Hatteras\n\n---\n**Source:** wal-graduation\n")
open(os.path.join(MEM, "pearls", "pearl_20260902_120000.md"), "w").write("# Pearl\n\nshe likes muscadines\n\n---\n**Source:** x\n")
out = CP.propagate("HC-9", "she grew up beside the lighthouse at Cape Hatteras", "she grew up in Raleigh", at="t")
check("the matching pearl gets a correction footer, the other is untouched, and the record names it", [t["projection"] for t in out["touched"]] == ["pearl"] and "**Corrected:** HC-9" in open(pf).read() and "Corrected" not in open(os.path.join(MEM, "pearls", "pearl_20260902_120000.md")).read())
CP.propagate("HC-9", "she grew up beside the lighthouse at Cape Hatteras", "she grew up in Raleigh", at="t")
check("a second propagation does not stack footers", open(pf).read().count("**Corrected:** HC-9") == 1)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
