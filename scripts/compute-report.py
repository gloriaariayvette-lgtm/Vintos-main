#!/usr/bin/env python3
"""compute-report.py - medians of what the compute ledger measured (review 171).

Reads memory/compute-ledger.jsonl and prints, per organ and per provider, the count, the median
latency, the median resident memory and the summed usage where a provider reported it. It
reports measurements. It does not rank models, and it says nothing about quality."""
import os, sys, json, statistics
from collections import defaultdict

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

def load(path=None):
    p = path or os.path.join(MEMORY, "compute-ledger.jsonl")
    rows = []
    try:
        for l in open(p):
            if l.strip():
                try: rows.append(json.loads(l))
                except Exception: continue
    except FileNotFoundError:
        pass
    return rows

def summarise(rows, key):
    out = {}
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key) or "?"].append(r)
    for k, rs in sorted(groups.items()):
        lat = [r["latency_ms"] for r in rs if isinstance(r.get("latency_ms"), (int, float))]
        mem = [r["rss_mb"] for r in rs if isinstance(r.get("rss_mb"), (int, float))]
        tok_in = sum((r.get("usage") or {}).get("input_tokens", 0) or (r.get("usage") or {}).get("prompt_tokens", 0) or 0 for r in rs)
        tok_out = sum((r.get("usage") or {}).get("output_tokens", 0) or (r.get("usage") or {}).get("completion_tokens", 0) or 0 for r in rs)
        out[k] = {"calls": len(rs),
                  "median_latency_ms": (int(statistics.median(lat)) if lat else None),
                  "median_rss_mb": (round(statistics.median(mem), 1) if mem else None),
                  "waited_s_total": round(sum(float(r.get("waited_s") or 0) for r in rs), 1),
                  "tokens_in": tok_in, "tokens_out": tok_out,
                  "usage_reported_calls": sum(1 for r in rs if r.get("usage"))}
    return out

def main(argv):
    rows = load(argv[1] if len(argv) > 1 else None)
    if not rows:
        print("no compute ledger lines yet"); return 0
    for key in ("organ", "provider"):
        print("== by %s ==" % key)
        for k, v in summarise(rows, key).items():
            print("  %-28s calls %4d  median %6s ms  rss %7s MB  waited %6ss  tokens in/out %d/%d (%d calls reported usage)"
                  % (k, v["calls"], v["median_latency_ms"], v["median_rss_mb"], v["waited_s_total"], v["tokens_in"], v["tokens_out"], v["usage_reported_calls"]))
    print("(measurements only; nothing here is a quality claim)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
