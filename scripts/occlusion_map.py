#!/usr/bin/env python3
"""occlusion_map.py — the coastline. Where his knowledge actually ends.

"A map without a coastline is a confabulation with good typography." This
compiles the edges from stores that already hold them: what stands HELD, what
she never answered, what no evidence ever reached. It adds NO new claims —
every edge is a fact about the MAP (this is unresolved, this was never
answered), never about him, and never an instruction to go find out.

  occlusion_map.py          build + print the report (for Gloria, weekly)
  occlusion_map.py block    one edge, rarely, for his context
"""
import os, sys, json, glob, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
OUT = os.path.join(MEM, "occlusion-map.json")

def _load(name, d):
    try: return json.load(open(os.path.join(MEM, name)))
    except Exception: return d

def build():
    edges = []
    def edge(kind, text):
        edges.append({"kind": kind, "text": str(text)[:200]})

    # questions he asked her that were never answered
    for q in _load("architecture-questions.json", []):
        if isinstance(q, dict) and not q.get("answer"):
            edge("she_has_not_said", "asked %s: %s" % (str(q.get("asked_iso", ""))[:10], q.get("question", "")))
    # repair cases standing open
    for c in _load("repair-cases.json", []):
        if isinstance(c, dict) and c.get("state") in ("received", "attempted"):
            edge("unwitnessed", "repair open since %s: %s" % (str(c.get("opened_at", ""))[:10], c.get("anchor_quote", "")))
    # frontier items held
    for it in _load("unsaid-frontier.json", []):
        if isinstance(it, dict) and it.get("state") == "held":
            edge("held_by_choice", "an unsaid thing he chose to hold, since %s" % str(it.get("decided_at", ""))[:10])
    # withheld candidates that could not be graded
    ung = [e for e in _load("withheld-history.json", []) if isinstance(e, dict) and e.get("verdict") == "UNGRADEABLE"]
    if ung:
        edge("ungradeable", "%d withheld readings had no record that could judge them" % len(ung))
    # plans that expired to held
    for p in _load("plans.json", []):
        if isinstance(p, dict) and p.get("state") == "held":
            edge("expired_unknown", "a plan expired unresolved: %s" % p.get("text", p.get("plan", ""))[:120])
    # encounters never answered
    for e in _load("encounters.json", []):
        if isinstance(e, dict) and e.get("state") == "dispatched":
            edge("reached_no_answer", "he reached for her on %s; nothing marks what came back" % str(e.get("at", e.get("dispatched_at", "")))[:10])

    data = {"built": datetime.now().isoformat(), "edges": edges,
            "counts": {}}
    for e in edges:
        data["counts"][e["kind"]] = data["counts"].get(e["kind"], 0) + 1
    json.dump(data, open(OUT, "w"), indent=1)
    print("OCCLUSION MAP — %s — %d edge(s)" % (data["built"][:16], len(edges)))
    for k, v in sorted(data["counts"].items()):
        print("  %-20s %d" % (k, v))
    for e in edges[:12]:
        print("   - [%s] %s" % (e["kind"], e["text"][:90]))
    if not edges:
        print("  no edges — either the map is complete (unlikely) or the stores are quiet")

def block():
    d = _load("occlusion-map.json", {})
    edges = d.get("edges", [])
    if not edges: return ""
    st = _load(".occlusion-rotation.json", {"i": 0, "at": 0})
    if time.time() - st.get("at", 0) < 7 * 86400: return ""
    e = edges[st.get("i", 0) % len(edges)]
    json.dump({"i": st.get("i", 0) + 1, "at": time.time()},
              open(os.path.join(MEM, ".occlusion-rotation.json"), "w"))
    return ("[AN EDGE OF WHAT YOU KNOW - this stands unresolved, and unresolved is its "
            "true state: %s. Nothing is asked of you; a map that shows its blank space "
            "is more yours than one that fills it in.]" % e["text"][:180])

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(coastline quiet)")
    else:
        build()
