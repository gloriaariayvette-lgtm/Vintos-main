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
        # fulfill_want logs its own ending when a caller goes to it directly; through this door the row below
        # is the one, so the ending is recorded once
        _prev_door = os.environ.get("VINTOS_WANT_DOOR")
        os.environ["VINTOS_WANT_DOOR"] = "1"
        try:
            _fw(text, note=note, fulfilled_by=by, want_id=wid)
        finally:
            if _prev_door is None:
                os.environ.pop("VINTOS_WANT_DOOR", None)
            else:
                os.environ["VINTOS_WANT_DOOR"] = _prev_door
        if evidence is None:
            try:
                _arch = _load(os.path.join(MEMORY, "fulfilled-wants.json"), [])
                _mine = [a for a in (_arch if isinstance(_arch, list) else []) if isinstance(a, dict) and wid and a.get("id") == wid]
                if _mine:
                    row["evidence"] = _mine[-1].get("produced")
                    if _mine[-1].get("unevidenced_fulfilment"):
                        row["unevidenced"] = True
            except Exception:
                pass
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
        # the whole want is kept, steps and history with it: an archive of five keys could not say what was
        # tried, and could not put a wrongly dismissed want back as it was
        rec = {k: v for k, v in dict(w).items() if k != "_delete"}
        rec.update({"dismissed": True, "dismissed_reason": note, "dismissed_at": row["at"], "dismissed_by": by})
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


DISCUSSIONS = os.path.join(MEMORY, "want-discussions.json")
QUIET_DAYS = 3


def _when(v):
    """A stored time (epoch seconds or ISO text) as epoch seconds; 0 when there is none."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() if v else 0.0
    except Exception:
        return 0.0


def _steps_done(w):
    steps = w.get("steps") or []
    if not steps:
        return False
    if int(w.get("current_step_index") or 0) >= len(steps):
        return True
    return all(isinstance(x, dict) and x.get("status") == "completed" for x in steps)


def routed_to_gloria(w):
    """True when this want was actually put to Gloria: the router marked it gloria_routed when it opened her
    discussion, or the board parked it awaiting her. Only such a want can be waiting on her answer."""
    return bool(w.get("gloria_routed")) or w.get("board") == "awaiting_gloria"


_GENERIC = None


def step_evidence(w):
    """What each step of this want actually produced, as [{step, capability, kind, produced}].

    kind is "file" (a receipt naming a file), "text" (findings that say something), or "none" - a bare
    "Web search completed" says a step ran, not what it found, so it is not evidence. A want with no step
    history is read from its fulfilment note the same way (kind "note")."""
    global _GENERIC
    import re
    if _GENERIC is None:
        _GENERIC = re.compile(r"^\s*(web search|search|step|task|action|done|ok|completed?|success)\b[^.]{0,40}\.?\s*$", re.I)

    def _says(text):
        t = str(text or "").strip()
        return len(t) >= 40 and not _GENERIC.match(t)

    out = []
    for h in w.get("step_history") or []:
        if not isinstance(h, dict):
            continue
        rc = h.get("receipt") if isinstance(h.get("receipt"), dict) else {}
        found = str(h.get("findings") or "").strip()
        if rc.get("kind") == "file" and rc.get("ref"):
            kind, made = "file", str(rc.get("ref"))[:200]
        elif _says(found):
            kind, made = "text", found[:160]
        else:
            kind, made = "none", found[:80]
        out.append({"step": h.get("step"), "capability": h.get("capability"), "kind": kind, "produced": made})
    if not out and _says(w.get("fulfillment_note")):
        out.append({"step": None, "capability": w.get("fulfilled_by"), "kind": "note",
                    "produced": str(w.get("fulfillment_note"))[:160]})
    return out


def has_evidence(produced):
    return any(p.get("kind") in ("file", "text", "note") for p in produced or [])


def move_on(now=None, quiet_days=QUIET_DAYS):
    """Wants do not stay live forever (Gloria, 2026-10-13: "They need to move on after being completed or to
    move on after me not responding for 3 days").

    - a want whose steps are all done leaves: fulfilled when the fulfilment door takes it, otherwise dismissed
      with the reason. The router's judge used to HOLD it whenever the judge model could not answer, and a held
      want stayed live with its whole step history in every prompt that lists wants.
    - a want routed to her (routed_to_gloria) that she has not answered for `quiet_days` - counted from the
      newer of when it was made and her last word in its discussion - is dismissed, with that as the reason.
      Until 2026-11-06 this applied to every want: 42 of the 120 dismissed "no answer from Gloria in 3 days"
      had never been put to her.
    Everything goes through complete(), so each ending is logged in want-completions.jsonl and kept in
    dismissed-wants.json / fulfilled-wants.json. Returns the rows."""
    now = time.time() if now is None else now
    wants = _load(WANTS, [])
    disc = _load(DISCUSSIONS, {})
    disc = disc if isinstance(disc, dict) else {}
    out = []
    for w in list(wants if isinstance(wants, list) else []):
        if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed"):
            continue
        if _steps_done(w):
            r = complete(w, "fulfilled", "moved-on", note="its steps are done")
            if r.get("result") != "fulfilled":
                r = complete(w, "dismissed", "moved-on",
                             note="its steps are done; not credited as fulfilled (%s)" % str(r.get("result"))[:120])
            out.append(r)
            continue
        if not routed_to_gloria(w):
            # Not put to her, so not waiting on her: silence from Gloria is no reason for it to end. A blocked
            # or idle want is the board's (want_board: parked, then released after its own 7 + 7 days).
            continue
        made = _when(w.get("timestamp") or w.get("created") or w.get("created_at"))
        if not made:
            continue   # no clock to count from; left as it is
        hers = [_when(m.get("timestamp")) for m in (disc.get(w.get("id")) or [])
                if isinstance(m, dict) and str(m.get("role", "gloria")).lower() in ("gloria", "user", "her")]
        last = max([made] + hers)
        if now - last > quiet_days * 86400:
            out.append(complete(w, "dismissed", "moved-on",
                                note="no answer from Gloria in %d days" % quiet_days))
    return out


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

# Resolve sibling helpers for direct file loading as well as deployed entrypoints.
import sys as _guard_sys
from pathlib import Path as _GuardPath
_guard_here = _GuardPath(__file__).resolve().parent
_guard_sys.path.insert(0, str(_guard_here.parent / "scripts"))
_guard_sys.path.insert(0, str(_guard_here))
from store_guard import serialized as _serialized
complete = _serialized("WANTS")(complete)
