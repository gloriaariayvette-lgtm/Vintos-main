#!/usr/bin/env python3
"""Every visit-script call to a capability-gated route must carry a capability.

The first real visit lost his work: my authorization matrix made /make,
/inspect and /handoff require a visit capability, and atelier-visit.py passed
one only to the stratagem calls. The broker refused the make and his piece
vanished. This is a static guard so a route added to VISIT/EXPORT can never
again be called from a visit without the capability threaded in.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

# 1. the routes that require a capability, read from the live matrix
brk = open(os.path.join(ROOT, "broker", "broker.py"), errors="replace").read()
gated = set(re.findall(r'"(/[a-z/_-]+)":\s*(?:VISIT|EXPORT)\b', brk))
check("the matrix names capability-gated routes", len(gated) >= 4, sorted(gated))

# 2. every POST to one of those in a visit script must include a capability key
for name in ("atelier-visit.py", "atelier-open.py"):
    src = open(os.path.join(ROOT, "scripts", name), errors="replace").read()
    # each requests.post(...) call, spanning lines up to the closing )
    for m in re.finditer(r'requests\.post\(\s*([^\n]*?/[a-z/_-]+)"?[^)]*?\{(.*?)\}', src, re.S):
        head, body = m.group(1), m.group(2)
        route = "/" + head.split("/", 1)[1].strip().strip('"') if "/" in head else ""
        route = route.split('"')[0]
        if route in gated:
            has = "capability" in body
            check("%s: %s carries a capability" % (name, route), has,
                  "" if has else body.strip()[:60])

# 3. and the make refusal must not silently drop his work
vis = open(os.path.join(ROOT, "scripts", "atelier-visit.py"), errors="replace").read()
check("a refused make preserves his piece instead of losing it",
      "atelier-unsaved" in vis and 'r.get("error")' in vis)
check("a refused handoff is surfaced, not swallowed",
      "HANDOFF REFUSED" in vis)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
