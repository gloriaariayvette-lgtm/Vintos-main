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
        before = str(occurrence_id) in _tv.load_taste_vector().get("counted_occurrences", [])
        try:
            _tv.update_from_signal(text, signal_weight=float(weight), positive=bool(positive), occurrence_id=str(occurrence_id), context=(medium or None))
        except TypeError:   # an older taste organ without clusters
            _tv.update_from_signal(text, signal_weight=float(weight), positive=bool(positive), occurrence_id=str(occurrence_id))
        counted = str(occurrence_id) in _tv.load_taste_vector().get("counted_occurrences", [])
        taste = ("already counted" if before else "moved") if counted else "taste update failed; retry permitted"
    except Exception as e:
        taste = "taste organ unavailable: %s" % str(e)[:80]
    if taste in ("moved", "already counted"):
        import learning_occasion as _lo
        row["occasion"] = _lo.teach("taste", occurrence_id, detail={"source":source,"medium":medium})
    row["taste"] = taste
    if taste == "moved":   # review 215: admission through this door is the candidate's promotion
        try: candidate(occurrence_id, text, medium, "promoted", rating=her_reception or his_delight, why="admitted to taste")
        except Exception: pass
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return {"admitted": True, "taste": taste, "row": row}


CANDIDATE_STATES = ("proposed", "used", "rated", "promoted", "dropped")


def candidate(occurrence_id, text, medium="", state="proposed", rating=None, why=""):
    """review 215: a preference candidate moves through named states - proposed (he made it), used (it
    was actually put in front of her), rated (she or he graded it), promoted (it became taste: admitted
    through the door above) or dropped (with a reason). Every move is appended; nothing is overwritten,
    so a revised rating is a new row, not a rewrite."""
    if state not in CANDIDATE_STATES:
        raise ValueError("state %r not in %s" % (state, CANDIDATE_STATES))
    row = {"occurrence_id": str(occurrence_id), "text": str(text)[:300], "medium": medium, "state": state,
           "rating": rating, "why": str(why)[:200], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(os.path.join(MEMORY, "taste-candidates.jsonl"), "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return row


def candidate_history(occurrence_id=None):
    """Every move of every candidate, or of one; the last row is its current state."""
    out = []
    try:
        for ln in open(os.path.join(MEMORY, "taste-candidates.jsonl")):
            try: r = json.loads(ln)
            except Exception: continue
            if occurrence_id is None or r.get("occurrence_id") == str(occurrence_id): out.append(r)
    except Exception:
        pass
    return out


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
