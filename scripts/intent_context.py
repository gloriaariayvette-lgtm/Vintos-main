"""Intent context for a voice call.

The standing block carries the ledger. Background selection prepares a candidate
without opening an intent; per-event admission supplies its complete lead once.
The reply/voice-ledger callback binds the actual reply to that declaration.
No selector provider call is added to the realtime response path.
"""
import os, sys, json, time
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
MEM = os.path.expanduser("~/.vintos/workspace/memory")
LEAD = os.path.join(MEM, ".voice-lead.json")


def _prepared_target():
    try:
        with open(LEAD) as handle:
            data = json.load(handle)
        # Background preparation happens every two minutes, not every twenty.
        # Its publication timestamp is never refreshed while recomputation runs.
        if not 0 <= time.time() - float(data.get("at", 0)) <= 120:
            return None
        from intent_engine import _valid_target
        target = _valid_target(data.get("target"))
        return target if target.get("intent_id") else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _lead_block():
    """Read-only preview. Actual voice admission is per event, never a standing session instruction."""
    from intent_engine import prompt_block
    return prompt_block(_prepared_target())


def admit_voice_lead(event_id):
    """Consume one prepared candidate at most once without a new provider call."""
    target = _prepared_target()
    if not target:
        return None, ""
    from intent_engine import record_pending, prompt_block
    target["campaign_pending"] = True
    if not record_pending(target, source="voice", event_id=event_id, claim_once=True):
        return None, ""
    return target, prompt_block(target)


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
    # Prepared voice leads are admitted by the per-event adapter; a session-wide
    # block must not replay the same action after she has changed the subject.
    parts = [p for p in (_ledger_block(),) if p]
    return "\n\n".join(parts)


if __name__ == "__main__":
    print(block() or "(no intent material)")
