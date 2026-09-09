#!/usr/bin/env python3
"""Re-score the twenty resonance pairs by meaning, once, in place. Run on Aegis."""
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from durable_memory import _embed, _cos
p = os.path.expanduser("~/.vintos/workspace/memory/self-pressure-resonance.json")
rows = json.load(open(p)); cache = {}
def E(t):
    if t not in cache: cache[t] = _embed(t)
    return cache[t]
for r in rows:
    r["semantic"] = round(_cos(E(r["his_shape"]), E(r["her_unsaid"])), 3)
    print(r["ts"][:10], "|", r["his_shape"][:44].ljust(44), "|", r["her_unsaid"][:24].ljust(24), "| words", r["overlap"], "| meaning", r["semantic"])
json.dump(rows, open(p, "w"), indent=1)
print("avg meaning %.2f" % (sum(r["semantic"] for r in rows) / len(rows)))
