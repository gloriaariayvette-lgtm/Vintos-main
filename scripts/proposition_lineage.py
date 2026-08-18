#!/usr/bin/env python3
"""proposition_lineage.py — separating what he believes from how the belief operates.

Vrika, 2026-08-16. Four tensions in his ledger terminate at one proposition: my presence must be
justified by production. Counted separately they read as four independent confirmations, and a
correction landing on two of them left the same belief SUPPORTED under two other names.

  PROPOSITION   what he believes about himself        (correction attaches HERE)
  MECHANISM     how that belief operates              (the tensions, kept distinct)
  LINEAGE       which mechanisms express which belief (must be EARNED, never assumed)
  EVIDENCE      unique at the proposition level       (provenance kept per mechanism)

Nothing merges on linguistic similarity. A lineage is CANDIDATE until the removal test says the
mechanisms are not independent: if removing one materially changes the explanatory account of the
others, they are distinct and stay distinct.
"""
import json, os, sys
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
LEDGER = os.path.join(MEM, "tension-ledger.json")
PROPS = os.path.join(MEM, "proposition-ledger.json")
SHARED_MIN = 2          # mechanisms must share this many quotes before we even ask

def _load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _save(p, d): json.dump(d, open(p, "w"), indent=2)

def _ask(prompt, max_tokens=400):
    import urllib.request
    body = json.dumps({"model": "google/gemma-4-12b-qat", "temperature": 0.2,
                       "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("http://172.18.16.1:1234/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def _jparse(s):
    try:
        i, j = str(s).find("{"), str(s).rfind("}")
        return json.loads(str(s)[i:j+1])
    except Exception:
        return {}

def _quotes(t):
    return {e["quote"].strip().lower() for e in t.get("evidence", [])
            if isinstance(e, dict) and not e.get("invalid") and e.get("polarity") == "supports"}

def detect_candidates():
    """Find mechanisms that may be faces of one belief. Proposes; never merges."""
    led = _load(LEDGER, None)
    if not led: return []
    living = [t for t in led["tensions"] if t.get("lifecycle") in ("ACTIVE", "CARRIED")]
    props = _load(PROPS, {"propositions": [], "next_id": 1})
    out = []

    for i, a in enumerate(living):
        for b in living[i+1:]:
            shared = _quotes(a) & _quotes(b)
            if len(shared) < SHARED_MIN:
                continue
            d = _jparse(_ask(
                "Two stated mechanisms from one being's self-model share evidence. Decide whether they "
                "are one belief wearing two names, or two genuinely different mechanisms.\n\n"
                f"MECHANISM A ({a['tension_id']}): {a['canonical']}\n"
                f"MECHANISM B ({b['tension_id']}): {b['canonical']}\n"
                f"SHARED EVIDENCE ({len(shared)}): {list(shared)[0][:200]}\n\n"
                "THE TEST — do not answer in the abstract. Name a CONCRETE SITUATION in which A "
                "operates and B cannot, and another in which B operates and A cannot. A situation is "
                "specific: a thing happening between them, at a moment, with something at stake. If you "
                "can name both, the mechanisms are INDEPENDENT and must stay separate. If you cannot "
                "name either, they are faces of one proposition.\n\n"
                "TWO WAYS TO GET THIS WRONG. First: reaching underneath both for a shared fear. Every "
                "mechanism in a self-model has fear under it; finding fear is not finding sameness, and "
                "it will merge everything with everything. Second: 'removing A leaves B standing' is an "
                "argument that B is INDEPENDENT of A - it is not evidence they are the same.\n\n"
                "If they are one proposition, state it using words BOTH mechanisms actually contain. Do "
                "not psychoanalyse past what they say.\n\n"
                'ONLY JSON: {"situation_a_only": "concrete situation, or empty if none exists", '
                '"situation_b_only": "concrete situation, or empty if none exists", '
                '"independent": true|false, "proposition": "only if not independent", '
                '"confidence": "high|low"}'))
            # independent unless it genuinely failed to find a discriminating situation
            if d.get("independent") or d.get("situation_a_only") or d.get("situation_b_only"):
                print(f"[lineage] {a['tension_id']}+{b['tension_id']} INDEPENDENT - "
                      f"A alone: {str(d.get('situation_a_only',''))[:60]} | "
                      f"B alone: {str(d.get('situation_b_only',''))[:60]}")
                continue
            d["same_proposition"] = True
            d["removal_test"] = ("no discriminating situation found: A-only='%s' B-only='%s'"
                                 % (d.get("situation_a_only",""), d.get("situation_b_only","")))
            d["independence"] = d.get("confidence", "low")
            if not d.get("same_proposition"):
                continue
            out.append({"pair": [a["tension_id"], b["tension_id"]],
                        "proposition": str(d.get("proposition", ""))[:250],
                        "removal_test": str(d.get("removal_test", ""))[:250],
                        "independence": d.get("independence", "uncertain"),
                        "shared_evidence": len(shared),
                        "at": datetime.now().isoformat()})
            print(f"[lineage] CANDIDATE {a['tension_id']}+{b['tension_id']} "
                  f"(shared {len(shared)}, independence {d.get('independence')}): {str(d.get('proposition',''))[:80]}")

    if out:
        props.setdefault("candidates", [])
        known = {tuple(sorted(c["pair"])) for c in props["candidates"]}
        for c in out:
            if tuple(sorted(c["pair"])) not in known:
                props["candidates"].append(c)
        _save(PROPS, props)
    else:
        print("[lineage] no candidate lineages this pass")
    return out

def confirm_lineage(proposition_text, tension_ids):
    """Called deliberately, once the removal test has been satisfied. Creates the proposition and
    binds its manifestations. Evidence is counted UNIQUELY here; provenance stays on each mechanism."""
    props = _load(PROPS, {"propositions": [], "next_id": 1})
    pid = "P-%03d" % props.get("next_id", 1)
    props["next_id"] = props.get("next_id", 1) + 1
    props["propositions"].append({
        "proposition_id": pid, "statement": proposition_text,
        "manifestations": list(tension_ids), "status": "ACTIVE",
        "corrections": [], "created": datetime.now().isoformat()})
    _save(PROPS, props)
    led = _load(LEDGER, None)
    for t in led["tensions"]:
        if t["tension_id"] in tension_ids:
            t["proposition_id"] = pid
            t.setdefault("history", []).append(
                {"at": datetime.now().isoformat(),
                 "event": "bound to proposition %s (%s) - a face of one belief, not an independent finding"
                          % (pid, proposition_text[:120])})
    _save(LEDGER, led)
    print(f"[lineage] {pid} confirmed over {', '.join(tension_ids)}")
    return pid

def unique_support(pid):
    """Support for a belief is its distinct evidence — not the sum of what each face collected."""
    props = _load(PROPS, {"propositions": []})
    led = _load(LEDGER, None)
    p = next((x for x in props["propositions"] if x["proposition_id"] == pid), None)
    if not p or not led: return {}
    seen, per = set(), {}
    for t in led["tensions"]:
        if t.get("proposition_id") != pid: continue
        q = _quotes(t)
        per[t["tension_id"]] = len(q)
        seen |= q
    return {"proposition": pid, "unique_support": len(seen),
            "naive_sum": sum(per.values()), "per_manifestation": per,
            "inflation": round(sum(per.values()) / max(1, len(seen)), 2)}

def contest_proposition(pid, correction_quote, at):
    """Her correction attaches to the BELIEF. Every face of it is contested — the system already
    decided these are one proposition; it cannot accept the correction on two names and leave the
    same claim standing under two others."""
    props = _load(PROPS, {"propositions": []})
    led = _load(LEDGER, None)
    p = next((x for x in props["propositions"] if x["proposition_id"] == pid), None)
    if not p or not led: return 0
    p["status"] = "CONTESTED"
    p["corrections"].append({"at": at, "authority": "Gloria", "quote": correction_quote[:250]})
    n = 0
    for t in led["tensions"]:
        if t.get("proposition_id") != pid: continue
        if t["status"] in ("HYPOTHESIS", "SUPPORTED", "CONFIRMED"):
            t["status"] = "CONTESTED"; t["eligible_for_visibility"] = False
            t["last_corrected"] = at
            t.setdefault("history", []).append(
                {"at": datetime.now().isoformat(), "authority": "Gloria",
                 "event": "CONTESTED via proposition %s - she corrected the belief, not the name" % pid,
                 "correction": correction_quote[:250]})
            n += 1
    _save(PROPS, props); _save(LEDGER, led)
    print(f"[lineage] {pid} contested — {n} manifestation(s) demoted")
    return n

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "candidates":
        detect_candidates()
    elif len(sys.argv) > 1 and sys.argv[1] == "show":
        props = _load(PROPS, {"propositions": [], "candidates": []})
        for c in props.get("candidates", []):
            print(f"CANDIDATE {'+'.join(c['pair'])} [{c['independence']}] shared={c['shared_evidence']}")
            print(f"   proposition: {c['proposition']}")
            print(f"   removal test: {c['removal_test']}")
        for p in props.get("propositions", []):
            print(f"{p['proposition_id']} {p['status']} :: {p['statement']}")
            print("   ", unique_support(p["proposition_id"]))
    else:
        print(__doc__)
