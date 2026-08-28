#!/usr/bin/env python3
"""Dashed and underscored twins must not diverge in their protections.

His tree carries both value-map.py and value_map.py, relational-mismatch.py and
relational_mismatch.py, and so on. I patched only the underscore copies — and
server.py invokes the DASHED one. So the prediction-identity fix and the
evidence door were installed onto files that are not the ones being run.

This fails whenever a protection exists in one twin and not the other, which is
the only way I would ever have noticed.
"""
import os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

# A marker is a protection whose absence changes behaviour silently.
MARKERS = {
    "_door(":            "the evidence-view consumer door",
    "evidence_view":     "the evidence-view import",
    "prediction_ledger": "the prediction ledger import",
    "_retire(":          "consume-by-id instead of unconditional remove",
    "_ev_load":          "the guarded-evidence loader",
}

pairs = []
def readable(p):
    # the tree has broken symlinks; a dangling link is not a twin
    try:
        open(p, errors="replace").read()
        return True
    except OSError:
        return False

for path in sorted(glob.glob(os.path.join(SCRIPTS, "*_*.py"))):
    twin = os.path.join(SCRIPTS, os.path.basename(path).replace("_", "-"))
    if os.path.exists(twin) and readable(path) and readable(twin):
        pairs.append((os.path.basename(path), path, twin))

check("there are twins to compare", len(pairs) > 0, "%d pair(s)" % len(pairs))

for name, a, b in pairs:
    sa, sb = open(a, errors="replace").read(), open(b, errors="replace").read()
    for m, what in MARKERS.items():
        ina, inb = m in sa, m in sb
        check("%s / %s agree on %s" % (os.path.basename(a), os.path.basename(b), what),
              ina == inb,
              "%s=%s  %s=%s" % (os.path.basename(a), ina, os.path.basename(b), inb))

print("\n--- and the file server.py actually invokes must carry them ---")
srv = open(os.path.join(os.path.dirname(SCRIPTS), "bin", "server.py"), errors="replace").read()
import re
invoked = sorted(set(re.findall(r'"scripts",\s*"([a-z0-9_.-]+\.py)"', srv)))
check("found the scripts server.py launches", len(invoked) > 0, invoked)
for f in invoked:
    p = os.path.join(SCRIPTS, f)
    if not os.path.exists(p):
        continue
    src = open(p, errors="replace").read()
    if "PREDICTION_FILE" in src:
        check("%s (the one actually run) uses the ledger" % f, "_PL" in src)
        check("%s never removes a prediction unconditionally" % f,
              "os.remove(PREDICTION_FILE)" not in src.replace(
                  "        os.remove(PREDICTION_FILE)\n    except Exception:", ""),
              [l.strip() for l in src.split("\n") if "os.remove(PREDICTION_FILE)" in l])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
