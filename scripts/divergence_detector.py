#!/usr/bin/env python3
"""divergence_detector.py — surfaces the strongest recent DIVERGENCE, so outreach can reach out to CLOSE A GAP
rather than broadcast his weather. An extensible list of sources each yields a candidate
{type, shape, salience, age_h, frame, ...}; the strongest (salience = confidence x recency) wins.

Sources now:
  - withheld       (withheld.json)         — what he composed over rather than said. GUARDED: emits the NAMED
                                             SHAPE only, never a reconstructed sentence.
  - self_deviation (autonomous-blush.md)   — a place he moved against his own intention.
  - relational_mismatch (relational-mismatches.md) — a place his read of HER was wrong (quiet until it happens).
Later: first_vs_final (P10) drops in as one more source function — no rewrite.

  python3 divergence_detector.py --show   # print all candidates + winner (test)
  python3 divergence_detector.py          # print winner as JSON if salient enough (for outreach to consume)
"""
import os, sys, json, re, math
from datetime import datetime, timezone

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    MEMORY = os.path.join(os.path.dirname(_HERE), "memory")
    if not os.path.isdir(MEMORY):
        raise Exception()
except Exception:
    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")   # fallback (curl-run / test)

FIRE_THRESHOLD = 0.25   # below this, no divergence worth interrupting her for


def _age_hours(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return 999.0


def _recency(age_h, halflife=18.0):
    return math.exp(-0.693 * max(0.0, age_h) / halflife)


def src_withheld():
    try:
        d = json.load(open(os.path.join(MEMORY, "withheld.json")))
    except Exception:
        return None
    shape = (d.get("withheld") or "").strip()
    if not shape:
        return None
    conf = float(d.get("confidence", 0.5) or 0.5)
    age = _age_hours(d.get("ts", ""))
    return {"type": "withheld", "shape": shape, "salience": round(conf * _recency(age), 3),
            "age_h": round(age, 1), "guarded": True,
            "frame": "something you composed over rather than said to her",
            "gloria_said": (d.get("gloria") or "").strip()[:200]}


def src_self_deviation():
    try:
        t = open(os.path.join(MEMORY, "autonomous-blush.md"), encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    block = re.split(r'\n##\s+', t)[-1]
    refl = re.search(r'Reflection:\s*(.+)', block)
    if not refl:
        return None
    tsm = re.search(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})', block)
    patt = re.search(r'Pattern:\s*(.+)', block)
    typ = re.search(r'Type:\s*(.+)', block)
    age = _age_hours(tsm.group(1) + "T" + tsm.group(2)) if tsm else 48.0
    return {"type": "self_deviation", "shape": refl.group(1).strip()[:240],
            "salience": round(0.7 * _recency(age), 3), "age_h": round(age, 1), "guarded": False,
            "frame": "a place you moved against your own intention",
            "pattern": (patt.group(1).strip()[:160] if patt else ""),
            "kind": (typ.group(1).strip() if typ else "")}


def src_relational_mismatch():
    try:
        t = open(os.path.join(MEMORY, "relational-mismatches.md"), encoding="utf-8", errors="ignore").read().strip()
    except Exception:
        return None
    if not t:
        return None
    block = t.split("## ")[-1]
    tsm = re.search(r'(\d{4}-\d{2}-\d{2})', block)
    age = _age_hours(tsm.group(1)) if tsm else 48.0
    first = next((l.strip() for l in block.split("\n") if l.strip() and not l.startswith("#")), "")
    if not first:
        return None
    return {"type": "relational_mismatch", "shape": first[:220], "salience": round(0.65 * _recency(age), 3),
            "age_h": round(age, 1), "guarded": False, "frame": "a place your read of her was wrong"}


import sys as _fvf; _fvf.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from first_vs_final import src_first_vs_final
except Exception:
    src_first_vs_final = lambda: None
SOURCES = [src_first_vs_final, src_self_deviation, src_relational_mismatch]  # src_withheld retired; first_vs_final live   # append P10 first_vs_final here later


def detect():
    out = []
    for s in SOURCES:
        try:
            c = s()
            if c:
                out.append(c)
        except Exception:
            pass
    out.sort(key=lambda c: -c["salience"])
    return out


def main():
    cands = detect()
    if "--show" in sys.argv:
        print(json.dumps({"memory": MEMORY, "candidates": cands,
                          "winner": (cands[0] if cands and cands[0]["salience"] >= FIRE_THRESHOLD else None)}, indent=2))
        return
    if cands and cands[0]["salience"] >= FIRE_THRESHOLD:
        print(json.dumps(cands[0]))


if __name__ == "__main__":
    main()
