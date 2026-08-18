#!/usr/bin/env python3
"""Precompute the pattern-signature hint so the chat path never waits on embeddings."""
import json, os, sys, time
MEM = os.path.expanduser("~/.vintos/workspace/memory")
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
try:
    d = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
    lst = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    ctx = " ".join(str(e.get("gloria","")) + " " + str(e.get("vintos","")) for e in lst[-3:])
except Exception:
    ctx = ""
hint = ""
if ctx.strip():
    try:
        from pattern_signatures import get_hint
        hint = get_hint(ctx) or ""
    except Exception as e:
        print("[sig-hint]", e)
json.dump({"hint": hint, "ts": time.time()}, open(os.path.join(MEM, "signature-hint.json"), "w"))
if hint: print("[sig-hint]", hint[:90])
