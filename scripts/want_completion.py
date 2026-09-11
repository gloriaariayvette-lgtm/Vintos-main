#!/usr/bin/env python3
"""want_completion.py - one door for a want ending, one door for a want entering.

Review item 254 (2026-09-10). Wants ended in four places (fulfill_want in emoclaw_utils, the router's
haiku verdict + _dismiss_want_with_reason, wants-conversation-check's direct fulfil, a checkpoint
release writing fulfilled=True by hand) and entered through two screens (want_contract.admission_state,
wants_meta.consult) that never met. Now:

    complete(want, how, by, note="", evidence=None)   how: fulfilled | dismissed | released
        fulfilled -> emoclaw_utils.fulfill_want (the artifact guard and the archive stay its business)
        dismissed -> memory/dismissed-wants.json, the want leaves the live list
        released  -> his choice: the want leaves the live list as RELEASED_BY_CHOICE
      every ending writes one row to memory/want-completions.jsonl
    admit(want_text, source, candidate_kind="", present_pull="")
        the shape screen and his standing stance, together, with the reason

Wanting keeps its many sources (conversation, ambition, dream, structural, third-order); only the
doors are one."""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
WANTS = os.path.join(MEMORY, "current-wants.json")
DISMISSED = os.path.join(MEMORY, "dismissed-wants.json")
COMPLETIONS = os.path.join(MEMORY, "want-completions.jsonl")
HOWS = ("fulfilled", "dismissed", "released")


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def _atomic(p, obj):
    """review 46: a store more than one organ writes goes through store_guard.locked_update; the plain
    atomic write below is the fallback when the guard is unavailable."""
    try:
        sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from store_guard import locked_update as _lu
        _lu(p, lambda _cur: obj, reader="want_completion")
        return
    except Exception:
        pass
    tmp = p + ".tmp"; json.dump(obj, open(tmp, "w"), indent=2); os.replace(tmp, p)


def _log(row):
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(COMPLETIONS, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def _find(want):
    wants = _load(WANTS, [])
    if not isinstance(wants, list):
        return wants, None
    wid = want.get("id") if isinstance(want, dict) else None
    text = want.get("want") if isinstance(want, dict) else str(want)
    for w in wants:
        if isinstance(w, dict) and ((wid and w.get("id") == wid) or (not wid and w.get("want") == text)):
            return wants, w
    return wants, None


def complete(want, how, by, note="", evidence=None):
    if how not in HOWS:
        raise ValueError("how must be one of %s" % (HOWS,))
    wants, w = _find(want)
    wid = (w or want).get("id") if isinstance(w or want, dict) else None
    text = (w or want).get("want") if isinstance(w or want, dict) else str(want)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "want_id": wid, "want": str(text)[:250], "how": how, "by": by,
           "note": str(note)[:300], "evidence": evidence, "turn_id": os.environ.get("VINTOS_TURN_ID", "") or None}
    if how == "fulfilled":
        try:
            sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from emoclaw_utils import fulfill_want as _fw
        except Exception as e:
            row["result"] = "fulfill_want unavailable: %s" % str(e)[:80]; _log(row); return row
        _fw(text, note=note, fulfilled_by=by, want_id=wid)
        try:   # review 240/265: a fulfilled want is evidence; a held plan it names reopens
            import plan as _plan
            row["reopened_plans"] = _plan.reopen_on_evidence(text, source="want:%s" % (wid or ""))
        except Exception:
            pass
        wants2, still = _find({"id": wid, "want": text})
        row["result"] = "fulfilled" if still is None else ("refused: %s" % (still.get("artifact_unverified", {}).get("why") if isinstance(still, dict) and still.get("artifact_unverified") else "still live"))
        _log(row); return row
    if w is None:
        row["result"] = "not live"; _log(row); return row
    if how == "dismissed":
        w["dismissed"] = True; w["dismissed_reason"] = note
        d = _load(DISMISSED, [])
        rec = {k: w.get(k) for k in ("id", "want", "source", "timestamp", "intensity") if k in w}
        rec.update({"dismissed_reason": note, "dismissed_at": row["at"], "dismissed_by": by})
        (d if isinstance(d, list) else d.setdefault("wants", [])).append(rec)
        _atomic(DISMISSED, d)
    else:
        w.setdefault("pursuit", {})["state"] = "ABANDONED_BY_CHOICE"
        w["want_state"] = "RELEASED_BY_CHOICE"; w["fulfilled"] = True; w["satisfaction"] = "RELEASED"; w["fulfilled_by"] = by
        w["fulfilled_at"] = row["at"]; w["fulfillment_note"] = note
        arch = _load(os.path.join(MEMORY, "fulfilled-wants.json"), [])
        (arch if isinstance(arch, list) else arch.setdefault("wants", [])).append(dict(w))
        _atomic(os.path.join(MEMORY, "fulfilled-wants.json"), arch)
    _atomic(WANTS, [x for x in wants if not (isinstance(x, dict) and (x is w or (wid and x.get("id") == wid)))])
    row["result"] = how; _log(row); return row


def admit(want_text, source, candidate_kind="", present_pull="", want_id=""):
    """Both screens at once: the shape screen (want_contract) and his standing stance (wants_meta).

    A want that names a rate rather than a thing — to analyse less, to reach for her
    less often — also opens a stance here, so the house slows where he asked it to
    instead of leaving the want to sit unfulfillable (want_stance)."""
    out = {"want": str(want_text)[:250], "source": source, "shape": "ADMIT_CONTRACT_UNAVAILABLE", "stance": None, "state": "ADMIT", "why": []}
    try:
        sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from want_contract import admission_state as _as
        out["shape"] = _as(source, candidate_kind, present_pull)
    except Exception:
        pass
    try:
        from wants_meta import consult as _consult
        out["stance"] = _consult(want_text)
    except Exception:
        pass
    # Report whether this want reads as a rate-stance, but do NOT open one here: the
    # stance is created by the writer once the want is actually admitted and stored,
    # with its real id (want_stance.admit is called there). A screen that opened a
    # stance for a candidate it was about to hold left a stance behind for a want that
    # never existed.
    try:
        import want_stance as _ws
        _dim, _dir = _ws.read_want(want_text)
        if _dim:
            out["holding"] = {"dimension": _dim, "direction": _dir}
            out["why"].append("reads as a stance: %s %s" % (_dir, _dim))
    except Exception:
        pass
    if out["shape"].startswith("HELD"):
        out["state"] = "HELD"; out["why"].append("shape: " + out["shape"])
    st = out["stance"] or {}
    if st.get("stance") in ("refuse", "never", "decline") and not st.get("advisory"):
        out["state"] = "HELD"; out["why"].append("standing stance %s: %s" % (st.get("id"), str(st.get("quote", ""))[:80]))
    elif st.get("advisory"):
        out["why"].append("stance advisory: " + st["advisory"])
    return out


def completions(limit=50):
    out = []
    try:
        for ln in open(COMPLETIONS):
            try: out.append(json.loads(ln))
            except Exception: pass
    except Exception:
        pass
    return out[-limit:]


if __name__ == "__main__":
    for r in completions(limit=12):
        print("  %s %-9s %-14s %s  (%s)" % (r["at"][:16], r["how"], r["by"], r["want"][:60], r.get("result")))
