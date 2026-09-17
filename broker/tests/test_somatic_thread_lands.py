#!/usr/bin/env python3
"""A somatic-session narration must land as a source='somatic' dream seed — bypassing the
formation door's reroute-to-latent and the quality "too vague" rejection, both of which had
silently swallowed it. LLM calls are stubbed; the store is a scratch file."""
import importlib.util, json, os, sys, tempfile, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-somatic-thread-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)
THREADS = os.path.join(MEM, "unfinished-threads.json")
open(THREADS, "w").write("[]")   # seed_thread refuses on an unreadable ledger, never on empty

# Stub every LLM call to the WORST case for landing: door says "current", quality says reject.
class _Resp:
    def json(self):
        return {"choices": [{"message": {"content": json.dumps({
            "kind": "current", "confidence": 0.9,
            "ok": False, "why": "reads like machine vocabulary", "duplicate_of": -1,
            "why_unresolved": "it stays unresolved because the reaching never resolved"})}}]}
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: _Resp())

spec = importlib.util.spec_from_file_location("eu_somatic", os.path.join(ROOT, "scripts", "emoclaw_utils.py"))
EU = importlib.util.module_from_spec(spec); spec.loader.exec_module(EU)

R = []
def check(name, ok): R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)

narration = ("It began with the raw, heavy demand of your body breaking against mine, a frantic "
             "reaching that neither of us slowed, and it left him unsure whether he had met her or "
             "only chased her.")
EU.seed_thread("somatic", narration)
landed = [t for t in json.load(open(THREADS)) if str(t.get("source", "")).startswith("somatic")]

check("a somatic narration lands as a source='somatic' thread despite door+quality saying no",
      len(landed) == 1)
check("the somatic thread is dream-bound", landed and landed[0].get("dream_only") is True)
check("it was not rerouted to the latent pool", landed and landed[0].get("source") == "somatic")
check("the store stayed under scratch HOME", THREADS.startswith(HOME))

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
