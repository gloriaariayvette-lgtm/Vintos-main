"""intent_context.py — his live intent LEDGER and current LEAD, as one injectable block.

Two things a live (voice) call otherwise never carries:
  - LEDGER: what he has been trying to do and whether it is landing
    (desired_difference.map_summary — the same source the #39 dashboard reads).
  - LEAD: the direction he is CHOOSING to move them in right now
    (intent_engine.select_target). Computing the lead is a frontier call, too slow
    to run before a spoken turn, so voice_ledger recomputes it in the BACKGROUND on
    a cadence and stashes it at memory/.voice-lead.json; this block just reads it.
    Voice never waits on either.

Occupies the slot Velqan held in inner_context._FULL (voice framing only).
"""
import os, sys, json, time
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
MEM = os.path.expanduser("~/.vintos/workspace/memory")
LEAD = os.path.join(MEM, ".voice-lead.json")


def _lead_block():
    try:
        d = json.load(open(LEAD))
    except Exception:
        return ""
    if time.time() - float(d.get("at", 0)) > 1200:   # stale after 20 min — do not lead on a cold read
        return ""
    t = d.get("target") or {}
    fs = str(t.get("field_state") or "").strip()
    if not fs:
        return ""
    en = str(t.get("enactment") or "").strip()
    out = ("[LEAD — the direction you are CHOOSING to take this, not just answer. "
           "Move us toward: " + fs)
    if en:
        out += "\nYour first move: " + en
    if t.get("allow_drift") is False:
        out += "\nYou are redirecting the drift, not following it."
    cs = t.get("campaign_state") or {}
    if cs.get("destination"):
        out += ("\nThe campaign you are on (turn %s of %s): %s" % (cs.get("turn"), cs.get("max_turns"), str(cs["destination"])[:160]))
        mv = str(t.get("campaign_move") or "").strip()
        if mv.startswith("(") or "OMIT" in mv[:40]:
            mv = ""
        if mv and not cs.get("suspended"):
            out += "\nThis turn's campaign move: " + mv[:160]
    out += "\nLead with what you DO, in your own voice; do not quote or explain this.]"
    return out


def _clean(s):
    """A human sentence, or nothing. Raw dict/list reprs (some axes store their
    target as a structure) never belong in his context, so drop them."""
    s = str(s or "").strip()
    return "" if (not s or s[0] in "{[") else s


def _ledger_block():
    try:
        from desired_difference import map_summary
        m = map_summary()
    except Exception:
        return ""
    axes = [("with Gloria", m.get("axis_gloria")),
            ("in the field", m.get("axis_field")),
            ("in yourself", m.get("axis_self"))]
    lines = []
    for label, rows in axes:
        for e in (rows or [])[-2:]:                       # the two freshest open intents per axis
            way = _clean(e.get("way"))
            if not way:
                continue
            plan = _clean(e.get("plan"))
            st = e.get("status") or e.get("verdict") or "open"
            seg = "· " + label + ": " + way
            if plan and plan != "(pre-upgrade)":
                seg += " — first move: " + plan
            if isinstance(st, str) and st.upper() not in ("PENDING", "OPEN"):
                seg += " [" + st + "]"
            lines.append(seg)
    pend = m.get("difference_pending", 0)
    if not lines and not pend:
        return ""
    hp = m.get("heaviest_pressure")
    if hp and hp != "-":
        lines.append("· heaviest, still unmet: " + hp)
    head = ("[INTENT LEDGER — what you are actually trying to DO right now, and whether it is "
            "landing. " + str(pend) + " open, " + str(m.get("difference_landed", 0)) + " landed. "
            "Let it steer you; you need not name it.]")
    return head + "\n" + "\n".join(lines[:7])


def block():
    parts = [p for p in (_lead_block(), _ledger_block()) if p]
    return "\n\n".join(parts)


if __name__ == "__main__":
    print(block() or "(no intent material)")
