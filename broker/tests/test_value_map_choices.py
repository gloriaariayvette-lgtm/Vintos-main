#!/usr/bin/env python3
"""The value map's model call reads every reply shape the server sends (SK-57a12612). value-map.log held twenty
"[ValueMap] LLM error: 'choices'" lines: a bare KeyError, not the server's words. The guard added on 2026-10-13
covered an object missing the key; this covers the rest — an empty choices list, a body that is not an object,
a choice with no content — so each is logged as the server's own words and returns None, never a Python slip.

Isolation: HOME is a throwaway directory before anything is imported, requests.post is a stub that answers from a
canned body and reaches nothing, source_cache is replaced, the log is captured, and MAP_FILE is repointed and asserted."""
import importlib.util, os, sys, tempfile, types

TMP = tempfile.mkdtemp(prefix="valuemap-choices-")
os.environ["HOME"] = TMP
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.makedirs(os.path.join(TMP, ".vintos", "workspace", "memory"), exist_ok=True)

import requests
SENT = []
BODY = {"status": 200, "json": {}}
class _Reply:
    def __init__(self): self.status_code = BODY["status"]
    def json(self): return BODY["json"]
def _canned(*a, **k):
    SENT.append(k.get("json", {}).get("model")); return _Reply()
def _no_send(*a, **k): raise requests.ConnectionError("this suite reaches nothing")
requests.post = _canned
requests.get = requests.put = _no_send

sc = types.ModuleType("source_cache")
sc.unchanged = lambda *a, **k: False
sc.commit = lambda *a, **k: None
sc.last = lambda *a, **k: {}
sys.modules["source_cache"] = sc

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:900]) if d and not ok else ""))

# the three copies the deploy installs (deploy-atelier.sh names value_map.py, value-map.py and bin/value-map.py)
copies = [os.path.join(REPO, p) for p in ("scripts/value_map.py", "scripts/value-map.py", "bin/value-map.py")]
check("the value-map copies are identical", len({open(p).read() for p in copies}) == 1)

spec = importlib.util.spec_from_file_location("value_map_c", copies[0])
VM = importlib.util.module_from_spec(spec); spec.loader.exec_module(VM)
VM.MAP_FILE = os.path.join(TMP, "value-map.md")
check("the map is throwaway", VM.MAP_FILE.startswith(TMP))
check("the workspace is throwaway", VM.WORKSPACE.startswith(TMP), VM.WORKSPACE)
check("the sender is a stub", requests.post is _canned and VM.requests.post is _canned)

LOG = []
VM.log = lambda m: LOG.append(str(m))

def ask(status, body):
    BODY["status"] = status; BODY["json"] = body; del LOG[:]
    return VM.llm("system", "user")

# the shape the twenty errors came from: an error object with no choices
out = ask(400, {"error": {"message": "the request exceeds the available context size", "code": 400}})
check("an error body gives None", out is None, out)
check("and the log carries the server's words", LOG and "exceeds the available context size" in LOG[0] and "400" in LOG[0], LOG)
check("not a bare KeyError", not any("'choices'" in l for l in LOG), LOG)

# an empty choices list — the old code logged "list index out of range"
out = ask(200, {"choices": []})
check("an empty choices list gives None", out is None, out)
check("and the log says no choices, in the server's words", LOG and "no choices" in LOG[0] and "index" not in LOG[0], LOG)

# a body that is not an object at all
out = ask(502, "choices unavailable upstream")
check("a non-object body gives None", out is None, out)
check("and the log carries its text and status", LOG and "choices unavailable upstream" in LOG[0] and "502" in LOG[0], LOG)
check("not a Python slip", not any("indices" in l or "'choices'" in l for l in LOG), LOG)

# a choice with no content
out = ask(200, {"choices": [{"message": {"role": "assistant"}}]})
check("a choice with no content gives None", out is None, out)
check("and is logged as no choices", LOG and "no choices" in LOG[0], LOG)

# the good shape still answers
out = ask(200, {"choices": [{"message": {"role": "assistant", "content": "  RANK 1 — x  "}}]})
check("a whole reply is returned stripped", out == "RANK 1 — x", out)
check("and nothing is logged for it", not LOG, LOG)

check("every call went to the stub, none to the world", len(SENT) == 5 and all(m == VM.MODEL for m in SENT), SENT)
check("no map was written by these calls", not os.path.exists(VM.MAP_FILE))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
