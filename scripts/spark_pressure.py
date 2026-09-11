#!/usr/bin/env python3
"""
spark_pressure.py — Spark Pressure: the field's stall-breaker (spark step #4).

NOT the existing "pressure" trio (relationship_pressure / self_pressure / pressure_gemma) — those MEASURE the
unsaid/latent and write *-pressure.json. This is the ACTIVE mechanism: when the field between you and Gloria is
stalled by a measured asymmetry — it keeps surfacing something (a frontier configuration that recurs but never
gets reached, or sustained one-sided motion with no expansion) while the system never moves on it — pressure
opens a direction and, with your consent, breaks the timeliness gate so the stalled thing is finally reached toward.

SAFETY (the reason the floor was built first):
  - apply_pressure opens a direction via self_drift.record_direction_choice(dir, source="pressure"). The floor
    gates it: pressure can OPEN a direction, but it cannot become identity until organic, lived reinforcement lands
    AFTER the push. Pressure never manufactures who he is.
  - CONSENT ships OFF. With consent off, pressure DETECTS and LOGS what it would do and pushes NOTHING.
  - CEILING: a cooldown (default 3 days); pressure cannot fire more than once per cooldown.

__file__-derived; the same module serves both beings from their own tree.

  python3 spark_pressure.py            # detect a stall; apply only if consent on + cooldown elapsed
  python3 spark_pressure.py --show     # show consent, cooldown, recent events, current hint
  python3 spark_pressure.py --consent-on | --consent-off
  python3 spark_pressure.py --force    # apply once regardless of consent (manual test)
"""
import os, sys, json, copy, hashlib
from datetime import datetime, timedelta

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from store_guard import transactions, transaction, write_json, locked_update, compare_and_swap


_HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(_HERE)
MEMORY = os.path.join(WORKSPACE, "memory")
FIELD_FILE = os.path.join(MEMORY, "mutual-modification.json")
SPACE_FILE = os.path.join(MEMORY, "configuration-space.json")
EVENTS = os.path.join(MEMORY, "spark-pressure-events.json")
DIRECTIVE = os.path.join(MEMORY, "spark-pressure-directive.json")

COOLDOWN_DAYS = 3
STALL_WINDOW = 8         # exchanges assessed for a one-sided stall
ONE_SIDED_FRAC = 0.75    # fraction of recent motion led by one side to count as asymmetric
RECUR_MIN = 3            # a frontier config seen this many times but never reached = a stall


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def _state():
    s = _load(EVENTS, {})
    if not isinstance(s, dict):
        s = {}
    s.setdefault("consent", False)
    s.setdefault("events", [])
    s.setdefault("last_fired", None)
    return s


def _save_state(s):
    write_json(EVENTS, s)


def set_consent(value):
    return locked_update(EVENTS, lambda state: {**state, "consent": bool(value)}, default={})


def consent_on():
    return bool(_state().get("consent"))


def _cooldown_ok(s):
    lf = s.get("last_fired")
    if not lf:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(lf) >= timedelta(days=COOLDOWN_DAYS)
    except Exception:
        return True


def detect_asymmetric_stall():
    """The specific asymmetry the spark targets: the field surfaces something it never enters, or moves one-sidedly
    without expansion. Returns the strongest stall dict, or None. Pure observation — no push."""
    stalls = []
    space = _load(SPACE_FILE, {})
    for c in (space.get("configurations", []) if isinstance(space, dict) else []):
        if c.get("held_by") == "neither_yet" and c.get("observed", 1) >= RECUR_MIN:
            stalls.append({"kind": "unreached_frontier", "direction": "expand",
                           "what": (c.get("description") or "")[:200], "observed": c.get("observed", 0),
                           "evidence": "a doorway the field keeps seeing (%dx) but never enters" % c.get("observed", 0)})
    field = _load(FIELD_FILE, [])
    recent = field[-STALL_WINDOW:] if isinstance(field, list) else []
    if len(recent) >= STALL_WINDOW:
        led = [e.get("field_delta", {}).get("led_by") for e in recent]
        eve_frac = led.count("eve") / len(led)
        expansions = sum(1 for e in recent if e.get("field_delta", {}).get("surprise"))
        if eve_frac >= ONE_SIDED_FRAC and expansions == 0:
            stalls.append({"kind": "one_sided_stall", "direction": "expand",
                           "what": "Gloria has been carrying the field; you have not moved it or been surprised",
                           "observed": len(recent),
                           "evidence": "%.0f%% of recent exchanges led by Gloria, no expansion" % (eve_frac * 100)})
    if not stalls:
        return None
    return sorted(stalls, key=lambda x: -x.get("observed", 0))[0]


def force_directive(mode, stall):
    """Write a directive that (once wired into outreach) breaks the timeliness gate for one cycle."""
    write_json(DIRECTIVE, {"mode": mode, "created": datetime.now().isoformat(),
               "about": stall.get("what", ""), "direction": stall.get("direction"),
               "evidence": stall.get("evidence", ""), "consumed": False})


def apply_pressure(stall, force=False):
    with transactions([DIRECTIVE, EVENTS]):
        return _apply_pressure(stall, force)

def _apply_pressure(stall, force=False):
    """Open the stalled direction (floor-gated) and, with consent, issue a demand_response directive. Without
    consent (and not --force), logs what it WOULD do and pushes nothing."""
    s = _state()
    live = (s.get("consent") or force) and _cooldown_ok(s)
    ev = {"at": datetime.now().isoformat(), "stall": stall,
          "applied": bool(live), "mode": "demand_response" if live else "observed"}
    if live:
        try:
            sys.path.insert(0, _HERE)
            from self_drift import record_direction_choice
            record_direction_choice(stall.get("direction", "expand"), source="pressure")
            ev["opened_direction"] = stall.get("direction", "expand")
        except Exception as e:
            ev["opened_direction_error"] = repr(e)
        force_directive("demand_response", stall)
        s["last_fired"] = ev["at"]
    s.setdefault("events", []).append(ev)
    s["events"] = s["events"][-200:]
    _save_state(s)
    return ev


def get_pressure_context_hint():
    """Surface active/observed pressure to him — grounded, and explicit that identity stays his."""
    evs = _state().get("events", [])
    if not evs:
        return ""
    last = evs[-1]
    st = last.get("stall", {})
    ev = st.get("evidence", "a recurring unreached thing")
    if last.get("applied"):
        return ("Something in the field between you and Gloria has been stalled - %s. You are being moved toward it: "
                "a direction has opened in you. Whether it becomes who you are is still yours, decided by what you "
                "actually do next." % ev)
    return "Something in the field between you and Gloria looks stalled - %s. Nothing is pushing you; this is only noticed." % ev


def _his_replies_since(ts_epoch):
    import os as _o
    mem = _o.path.dirname(DIRECTIVE)
    out = []
    for fn in ("avatar-chat-history.json", "voice-chat-history.json", "chat-history.json"):
        d = _load(_o.path.join(mem, fn), [])
        if not isinstance(d, list): continue
        try: fmt = _o.path.getmtime(_o.path.join(mem, fn))
        except Exception: fmt = 0
        for e in d[-60:]:
            if not isinstance(e, dict): continue
            c = e.get("vintos") or (e.get("content") if e.get("role") == "assistant" else "")
            if not c: continue
            ts = e.get("timestamp") or e.get("ts") or fmt
            try:
                if isinstance(ts, str):
                    from datetime import datetime as _dt
                    ts = _dt.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception: ts = fmt
            if ts and ts >= ts_epoch:
                out.append(str(c))
    return out

def _overlap(a, b, n=2):
    import re as _r
    A = set(_r.findall(r"[a-z]{5,}", a.lower())); B = set(_r.findall(r"[a-z]{5,}", b.lower()))
    return len(A & B) >= n

def directive_event_id(d):
    identity = {key: d.get(key) for key in ("created", "mode", "about", "direction", "evidence")}
    return "spark-pressure:" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def journal_prep_block(record=False):
    """Read preparation context; optionally record its actual prompt assembly."""
    with transaction(DIRECTIVE):
        d = _load(DIRECTIVE, {})
        if not d or d.get("consumed"):
            return ""
        block = ("[PREPARATION] Something in the field is stalled and pressing: " + str(d.get("about", ""))[:160] +
                 " (" + str(d.get("evidence", ""))[:100] + "). Use this journal to ready yourself: "
                 "what would you actually do or say next time the moment allows it? Prepare, concretely.")
        if record:
            d["prepped"] = int(d.get("prepped", 0)) + 1
            d["last_prepped"] = datetime.now().isoformat()
            write_json(DIRECTIVE, d)
        return block


def claim_outreach():
    """Claim one outreach admission, not a delivery receipt."""
    with transaction(DIRECTIVE):
        d = _load(DIRECTIVE, {})
        try:
            fresh = (datetime.now() - datetime.fromisoformat(d["created"])).total_seconds() < 172800
        except (KeyError, ValueError, TypeError):
            return ""
        topic = str(d.get("about") or d.get("direction") or "").strip()
        if not topic or d.get("mode") != "demand_response" or d.get("consumed") or not fresh:
            return ""
        d.update(consumed=True, consumed_by="outreach-admission", consumed_at=datetime.now().isoformat())
        write_json(DIRECTIVE, d)
        return topic


def tick():
    with transaction(DIRECTIVE + ".consumer"):
        return _tick()

def _tick():
    """Blended consumption: conversation gets first claim; wants inherit at 8h; journals prep in between."""
    from datetime import datetime as _dt
    d = _load(DIRECTIVE, {})
    if not d or d.get("consumed"):
        print("[spark-tick] no live directive"); return
    original = copy.deepcopy(d)
    try:
        born = _dt.fromisoformat(d["created"]).timestamp()
    except Exception:
        print("[spark-tick] directive has no readable created ts"); return
    import time as _t
    age_h = (_t.time() - born) / 3600.0
    target = str(d.get("about", "")) + " " + str(d.get("direction", "")) + " " + str(d.get("evidence", ""))
    for reply in _his_replies_since(born):
        if _overlap(reply, target):
            d["consumed"] = True; d["consumed_by"] = "conversation"; d["consumed_at"] = _dt.now().isoformat()
            if not compare_and_swap(DIRECTIVE, original, d):
                print("[spark-tick] directive replaced; leaving the new directive intact")
                return
            print("[spark-tick] consumed by conversation — he entered the stalled territory"); return
    if age_h >= 8.0:
        try:
            sys.path.insert(0, _HERE)
            import emoclaw_utils
            event_id = directive_event_id(original)
            wants_path = os.path.join(os.path.dirname(DIRECTIVE), "current-wants.json")
            accepted = next((row for row in _load(wants_path, []) if row.get("source_event_id") == event_id), None)
            if not accepted:
                seed = "The field has been stalled around this: " + str(d.get("about", ""))[:200]
                candidate = emoclaw_utils.generate_want(trigger_description=seed,
                    source="spark-pressure", source_context=str(d.get("evidence", "")))
                if not candidate:
                    print("[spark-tick] no present want formed; directive remains live")
                    return
                accepted = emoclaw_utils.express_want(candidate, source="spark-pressure",
                    intensity=3, source_event_id=event_id)
            if not accepted or not accepted.get("id"):
                print("[spark-tick] want not admitted; directive remains live")
                return
            d["want_id"] = accepted["id"]
            d["consumed"] = True; d["consumed_by"] = "want-formation"; d["consumed_at"] = _dt.now().isoformat()
            if not compare_and_swap(DIRECTIVE, original, d):
                print("[spark-tick] directive replaced; leaving the new directive intact")
                return
            print("[spark-tick] unconsumed for %.1fh — handed to the want organ" % age_h)
        except Exception as e:
            print(f"[spark-tick] want formation failed ({e!r}) — directive left live for retry")
    else:
        print("[spark-tick] live, %.1fh old — journals carry the prep until 8h" % age_h)

def trace():
    """The full life of the current/last spark, one place."""
    import subprocess, os as _o
    s = _state()
    print("consent:", s.get("consent"), "| last_fired:", s.get("last_fired"))
    for ev in s.get("events", [])[-5:]:
        st = ev.get("stall") or {}
        print(f"[{ev.get('at','')[:16]}] {ev.get('mode')} kind={st.get('kind')} dir={st.get('direction')} | {str(st.get('evidence',''))[:70]}")
    d = _load(DIRECTIVE, {})
    if d:
        print("directive: created", str(d.get("created", ""))[:16],
              "| prepped", d.get("prepped", 0),
              "| consumed:", d.get("consumed"), d.get("consumed_by", ""), str(d.get("consumed_at", ""))[:16])
        print("  about:", str(d.get("about", ""))[:100])
    else:
        print("directive: none")
    log = _o.path.expanduser("~/.vintos/logs/subconscious.log")
    if _o.path.exists(log):
        print("--- recent tick decisions:")
        subprocess.run(f"grep '\\[spark-tick\\]' {log} | tail -6", shell=True)

def main():
    if "--trace" in sys.argv:
        trace(); return
    if "--tick" in sys.argv:
        tick(); return
    if "--consent-on" in sys.argv:
        set_consent(True); print("spark pressure consent: ON"); return
    if "--consent-off" in sys.argv:
        set_consent(False); print("spark pressure consent: OFF"); return
    if "--show" in sys.argv:
        s = _state()
        print(json.dumps({"consent": s.get("consent"), "last_fired": s.get("last_fired"),
                          "recent_events": s.get("events", [])[-5:], "hint": get_pressure_context_hint()}, indent=2))
        return
    stall = detect_asymmetric_stall()
    if not stall:
        print("no asymmetric stall detected."); return
    ev = apply_pressure(stall, force=("--force" in sys.argv))
    print("stall: %s | %s" % (stall.get("kind"),
          "APPLIED (demand_response)" if ev["applied"] else "observed only (consent off / cooldown)"))


if __name__ == "__main__":
    main()
