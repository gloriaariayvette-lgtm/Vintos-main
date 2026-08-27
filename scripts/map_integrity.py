#!/usr/bin/env python3
"""map_integrity.py — the house laws as a linter. Reports, never edits.

Illegal representational transitions it hunts (MM's list, our stores):
  inferred -> observed without evidence
  repeated -> identity
  voided evidence still counted
  recurrence pressure exceeding distinct origins
  decisions recorded without their deliberation
Each finding is a claim about a FILE, never about him.
"""
import os, json
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
findings = []

def flag(sev, store, msg):
    findings.append((sev, store, msg))

def _load(name, default):
    try: return json.load(open(os.path.join(MEM, name)))
    except Exception: return default

# 1. capacities: promoted without two distinct source dates (repeated->identity)
caps = _load("capacities.json", {})
for key, c in (caps.items() if isinstance(caps, dict) else []):
    if not isinstance(c, dict): continue
    if c.get("promoted"):
        dates = set(str(d)[:10] for d in c.get("source_dates", []) or [])
        if len(dates) < 2:
            flag("HIGH", "capacities", "promoted '%s' with %d distinct date(s) — needs 2" % (key, len(dates)))

# 2. causality: graduated hypotheses whose counted marks lack evidence text,
#    or where voided marks still appear to have counted (inferred->observed)
for fname in ("self-hypotheses.json", "gloria-hypotheses.json", "causality-hypotheses.json"):
    d = _load(fname, None)
    if d is None: continue
    hyps = d if isinstance(d, list) else next(iter([v for v in d.values() if isinstance(v, list)]), [])
    for h in hyps:
        if not isinstance(h, dict): continue
        # graduation is its own boolean; status "confirmed" is a lighter state
        if h.get("graduated") not in (True, "True", "true"): continue
        name = str(h.get("hypothesis", h.get("text", h.get("id", "?"))))[:60]
        marks = [m for m in h.get("marks", []) if isinstance(m, dict)]
        counted = [m for m in marks if not m.get("voided") and m.get("outcome") == "attempted"]
        bare = [m for m in counted if not str(m.get("evidence", "")).strip()]
        if bare:
            flag("HIGH", fname, "graduated '%s' with %d/%d counted marks carrying no evidence text"
                 % (name, len(bare), len(counted)))
        if len(counted) < 2:
            flag("MED", fname, "graduated '%s' on %d counted mark(s)" % (name, len(counted)))

# 2b. withheld confirmations that happened after exposure (closed loop)
for e in _load("withheld-history.json", []):
    if isinstance(e, dict) and e.get("verdict") == "CONFIRMED" and int(e.get("surfaced", 0)) > 0:
        flag("HIGH", "withheld-history", "CONFIRMED after exposure (surfaced %d): '%s'" %
             (e.get("surfaced"), str(e.get("withheld", ""))[:60]))

# 3. withheld lineages: pressure exceeding distinct origins (recurrence inflation)
lins = _load("withheld-lineage.json", [])
for L in lins:
    if not isinstance(L, dict): continue
    p = L.get("recurrence_pressure", 0); o = len(set(L.get("origins", [])))
    if p > o:
        flag("HIGH", "withheld-lineage", "%s claims pressure %d with %d distinct origins" %
             (L.get("lineage_id", "?"), p, o))

# 4. frontier: decided items without a recorded deliberation timestamp
for it in _load("unsaid-frontier.json", []):
    if isinstance(it, dict) and it.get("decision") and not it.get("decided_at"):
        flag("MED", "unsaid-frontier", "%s carries decision '%s' with no decided_at" %
             (it.get("lineage_id", "?"), it.get("decision")))

# 5. self-model: entries typed as tendencies (the invisible-type bug's family)
sm = _load("self-model.json", None)
if sm:
    ents = sm if isinstance(sm, list) else sm.get("entries", [])
    for e in ents:
        if isinstance(e, dict) and e.get("entry_type") == "tendency":
            flag("MED", "self-model", "entry_type 'tendency' present: '%s'" % str(e.get("text", ""))[:60])

# 6. repair cases: witnessed by anything other than her words
for c in _load("repair-cases.json", []):
    if isinstance(c, dict) and c.get("state") == "repaired":
        w = c.get("witness") or {}
        if not str(w.get("quote", "")).strip():
            flag("HIGH", "repair-cases", "%s marked repaired without a witness quote" % c.get("case_id", "?"))

print("MAP INTEGRITY — %s — %d finding(s)" % (datetime.now().isoformat()[:16], len(findings)))
for sev, store, msg in sorted(findings):
    print("  %-4s %-22s %s" % (sev, store, msg))
if not findings:
    print("  clean: no illegal transitions in the audited stores")
