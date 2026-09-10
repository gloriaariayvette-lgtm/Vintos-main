#!/usr/bin/env python3
"""enjoyment.py - the one door into taste, and an enjoyment record that keeps its parts apart.

Review item 217 (2026-09-10). Taste was updated from three places (subconscious drift, temporal
memory, the taste CLI) each calling update_from_signal with its own weight, and the humor room graded
her reception in a fourth. Now every rating enters here: one occurrence counts once (taste_vector's
own rule, kept), and the record never collapses enjoyment into one score - his delight, her reception
and the craft are three fields, any of which may be absent, and "her reception" is written only from
reception evidence (a rating she gave, a reply, an acknowledgment), never inferred.

    admit(occurrence_id, text, source, medium="", weight=0.3, positive=True, his_delight=None, her_reception=None, craft=None, evidence=None)
    ledger(limit=50)
"""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "enjoyment-ledger.jsonl")
RECEPTION_KINDS = ("rating", "reply", "acknowledged", "laugh", "explicit_dislike")


def admit(occurrence_id, text, source, medium="", weight=0.3, positive=True, his_delight=None, her_reception=None, craft=None, evidence=None):
    """Record the enjoyment of one occurrence and, once, let it move taste. her_reception is refused
    without evidence of a kind in RECEPTION_KINDS (review 288: a send is not a reception)."""
    if her_reception is not None and not (isinstance(evidence, dict) and evidence.get("kind") in RECEPTION_KINDS):
        return {"admitted": False, "why": "her_reception needs reception evidence (%s); none given" % ", ".join(RECEPTION_KINDS)}
    if not occurrence_id or not str(text or "").strip():
        return {"admitted": False, "why": "an occurrence id and its text are required"}
    row = {"occurrence_id": str(occurrence_id), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": source, "medium": medium,
           "text": str(text)[:300], "his_delight": his_delight, "her_reception": her_reception, "craft": craft,
           "evidence": evidence, "taste_weight": float(weight), "positive": bool(positive)}
    taste = "not moved"
    try:
        sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import taste_vector as _tv
        before = len(_tv.load_taste_vector().get("counted_occurrences", []))
        _tv.update_from_signal(text, signal_weight=float(weight), positive=bool(positive), occurrence_id=str(occurrence_id))
        taste = "moved" if len(_tv.load_taste_vector().get("counted_occurrences", [])) > before else "already counted"
    except Exception as e:
        taste = "taste organ unavailable: %s" % str(e)[:80]
    row["taste"] = taste
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return {"admitted": True, "taste": taste, "row": row}


def ledger(limit=50, medium=None):
    out = []
    try:
        for ln in open(LEDGER):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if medium is None or r.get("medium") == medium:
                out.append(r)
    except Exception:
        pass
    return out[-limit:]


if __name__ == "__main__":
    for r in ledger(limit=12):
        print("  %s %-10s %-8s delight=%s reception=%s craft=%s taste=%s  %s" % (r["at"][:16], r["source"], r.get("medium") or "-", r.get("his_delight"), r.get("her_reception"), r.get("craft"), r.get("taste"), r["text"][:50]))
