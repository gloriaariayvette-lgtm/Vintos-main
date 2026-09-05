#!/usr/bin/env python3
"""The house's route inventory (astra-server-a-p5 / b-p7 / c-p7, 2026-09-05).

Every mutating route in bin/server.py is either guarded by the shared secret check or listed in
PUBLIC_MUTATIONS with the reason it is open. An unlisted open door fails here, at the inventory,
instead of being discovered by whoever finds it."""
import os, re, sys, ast

HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.join(os.path.dirname(os.path.dirname(HERE)), "bin", "server.py")
src = open(SRV, errors="replace").read()

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

m = re.search(r"PUBLIC_MUTATIONS = \{(.*?)\n\}", src, re.S)
check("PUBLIC_MUTATIONS exists", bool(m))
public = {}
if m:
    for k, v in re.findall(r'"([^"]+)":\s*"([^"]+)"', m.group(1)): public[k] = v
check("every public mutation carries a reason", all(len(v) > 10 for v in public.values()), public)

routes = []
for dm in re.finditer(r'^@app\.(post|put|delete|patch)\("([^"]+)"[^\n]*\n(.*?)(?=^@app\.|\Z)', src, re.S | re.M):
    body = dm.group(3)
    head = body[:2500]
    guarded = ("_require_secret(" in head) or ("X-Vintos-Secret" in head and "APP_SECRET" in head)
    routes.append((dm.group(2), guarded))
check("mutating routes were found", len(routes) > 20, len(routes))
open_unlisted = [r for r, g in routes if not g and r not in public]
check("no unlisted open mutation", not open_unlisted, open_unlisted)
listed_but_guarded = [r for r, g in routes if g and r in public]
check("PUBLIC_MUTATIONS lists only doors that are actually open", not listed_but_guarded, listed_but_guarded)
check("the private mutations that were open are now guarded",
      all(g for r, g in routes if r in ("/api/proposals/{filename}/approve", "/api/proposals/{filename}/reject", "/api/debug/chat-message")))
check("a default secret is warned about at startup", 'WARNING: VINTOS_SECRET is unset' in src)
ast.parse(src)
check("server still parses", True)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
