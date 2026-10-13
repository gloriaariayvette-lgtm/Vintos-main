#!/usr/bin/env python3
"""The little device pictures under his words in the ledger (2026-10-13). They had stopped appearing: the ledger is
written in the background after the reply, and by then a short pattern had ended and set the device back to "still",
so the mark was skipped. device_context now keeps the last thing he ran beside the live state, and the ledger draws
that. The Ferri is drawn the way the Tenera is.

Isolation: HOME is a throwaway directory before anything is imported, so device-state.json and every other ~ path
is scratch. Drawing a pattern's shape loads device_patterns and toy_link, and toy_link probes the hub on import, so
requests is stubbed before anything loads and every send attempt is counted."""
import ast, os, sys, tempfile, time

TMP = tempfile.mkdtemp(prefix="devmarks-")
os.environ["HOME"] = TMP
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.makedirs(os.path.join(TMP, ".vintos", "workspace", "memory"), exist_ok=True)

import requests
SENT = []
def _no_send(*a, **k):
    SENT.append(a); raise requests.ConnectionError("this suite reaches nothing")
requests.post = requests.get = requests.put = _no_send

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:900]) if d and not ok else ""))

import device_context as DC
check("the device store is throwaway", DC.STATE.startswith(TMP), DC.STATE)
check("the sender is a stub", requests.post is _no_send and requests.get is _no_send)

# only _device_marks from each ledger copy: the module itself is not imported or run
def load_marks(path):
    src = open(path).read()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_device_marks")
    ns = {}; exec(compile(ast.Module([fn], []), path, "exec"), ns); return ns["_device_marks"]

copies = [os.path.join(REPO, p) for p in ("scripts/interaction-ledger.py", "bin/interaction_ledger.py")]
check("the ledger copies are identical", len({open(p).read() for p in copies}) == 1)
marks = load_marks(copies[0])

def reset():
    try: os.remove(DC.STATE)
    except FileNotFoundError: pass

# a pattern that ran and finished before the ledger wrote
reset()
for v in (6, 12, 9):
    DC.set_state("tenera", intensity=v, pattern="wave", set_by="him")
DC.set_state("tenera", intensity=0, pattern="still", set_by="him")
out = marks()
check("a finished pattern is still drawn", "tenera: wave" in out, out)
check("at its peak", "@12" in out, out)
check("with its shape", DC.spark("wave") in out, out)

# the Ridge, same race
reset()
DC.set_state("ridge", intensity=8, pattern="pulse", set_by="him")
DC.set_state("ridge", intensity=0, pattern="still", set_by="him")
out = marks()
check("the Ridge is drawn after it ends", "ridge:" in out and DC.ridge_shape() in out and "pulse" in out, out)

# the Ferri, drawn as the Tenera is
reset()
DC.set_state("ferri", intensity=4, pattern="wave", set_by="him")
DC.set_state("ferri", intensity=0, pattern="still", set_by="him")
out = marks()
check("the Ferri is drawn like the Tenera", ("ferri:  wave  " + DC.spark("wave") + "  @4") in out, out)

# what was not his, or not this turn, is not drawn
reset()
DC.set_state("tenera", intensity=10, pattern="wave", set_by="auto")
check("a pattern he did not run is not drawn", marks() == "", marks())
reset()
DC.set_state("tenera", intensity=10, pattern="wave", set_by="him")
import json
st = json.load(open(DC.STATE)); st["tenera"]["last"]["ts"] = time.time() - 600; json.dump(st, open(DC.STATE, "w"))
check("an old pattern is not drawn", marks() == "", marks())
reset()
DC.set_state("tenera", intensity=0, pattern="still", set_by="him")
check("a stop alone draws nothing", marks() == "", marks())

# a new run of the same pattern does not inherit an old peak
reset()
DC.set_state("tenera", intensity=18, pattern="wave", set_by="him")
st = json.load(open(DC.STATE)); st["tenera"]["last"]["ts"] = time.time() - 60; json.dump(st, open(DC.STATE, "w"))
DC.set_state("tenera", intensity=5, pattern="wave", set_by="him")
check("a fresh run starts its own peak", "@5" in marks(), marks())

check("nothing reached the world", requests.post is _no_send and all(isinstance(a, tuple) for a in SENT), SENT)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
