#!/usr/bin/env python3
"""
behavioral-intercept.py — Detect active trial matches and return intercept hints.
Usage:
  get_intercept_hint(text) -> str or ""
  log_outcome(trial_id, outcome, resistance) -> None
  get_pending_intercept() -> dict or None
"""
import json, os, sys, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER = os.path.join(MEMORY, "trial-ledger.json")
PENDING = os.path.join(MEMORY, ".pending-intercept.json")
LM_URL = "http://127.0.0.1:8599/v1/chat/completions"

def load_ledger():
    with open(LEDGER) as f: return json.load(f)

def save_ledger(data):
    with open(LEDGER, "w") as f: json.dump(data, f, indent=2)

def get_active_trials():
    """Return active trials, archiving those older than 14 days with no outcomes."""
    ledger = load_ledger()
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    active = []
    changed = False
    for t in ledger["trials"]:
        if t.get("status") != "active":
            active.append(t)
            continue
        # Archive if older than 14 days with no outcomes
        if t.get("created", "9999") < cutoff[:10] and not t.get("outcomes") and not t.get("protected") and not t.get("id","").startswith("permanent_"):
            t["status"] = "archived_stale"
            changed = True
        else:
            active.append(t) if t.get("status") == "active" else None
    # Rebuild — keep all, just return active ones
    if changed:
        save_ledger(ledger)
    return [t for t in ledger["trials"] if t.get("status") == "active"]

def detect_match(text, trials, context=None):
    """Use LLM to check if text matches any active trial trigger."""
    if not trials: return None
    # Filter by context scope if trial specifies restrict_to_contexts
    if context:
        trials = [t for t in trials if not t.get("restrict_to_contexts") or context in t.get("restrict_to_contexts", [])]
    elif trials:
        trials = [t for t in trials if not t.get("restrict_to_contexts")]
    # Read sensitivity boost if deviation recently fired
    _sensitivity_boost = False
    try:
        import json as _sj, os as _so
        _sp = _so.path.join(MEMORY, "bis-sensitivity.json")
        if _so.path.exists(_sp):
            _sd = _sj.load(open(_sp))
            _sensitivity_boost = _sd.get("active", False)
    except: pass
    _trial_limit = 30 if _sensitivity_boost else 20
    trial_list = ""
    for t in trials[:_trial_limit]:
        trial_list += f"ID: {t['id']}\nTrigger: {t['trigger']}\nPattern: {t['pattern_description']}\n\n"
    _partial_line = "\nPartial matches count — if the pattern is beginning to emerge, that is enough." if _sensitivity_boost else ""
    prompt = (
        "Below is text Vintos is about to generate, and a list of active behavioral trials.\n"
        "Does this text show signs that one of the trigger patterns is active?\n"
        "A trigger is active if the text contains the behavior described in pattern_description, "
        "or if the situation described in trigger is clearly present.\n\n"
        "TEXT:\n" + text[:600] + "\n\n"
        "ACTIVE TRIALS:\n" + trial_list +
        "If a match exists, return ONLY the trial ID. If no match, return NONE." + _partial_line
    )
    r = requests.post(LM_URL, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "grok-4.20-0309-non-reasoning",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 30
    }, timeout=15)
    result = r.json()["choices"][0]["message"]["content"].strip()
    if result == "NONE" or not result: return None
    # Find matching trial
    for t in trials:
        if t["id"] in result:
            return t
    return None


THRESHOLD_LOG = os.path.join(MEMORY, "threshold-log.json")

def log_threshold_event(trial, context):
    """Separate log for pulling back at intensity. Tracks frequency over time."""
    try:
        try:
            data = json.load(open(THRESHOLD_LOG))
        except:
            data = {"events": []}
        data["events"].append({
            "trial_id": trial.get("id", ""),
            "pattern": trial.get("pattern_description", "")[:120],
            "context": context,
            "timestamp": datetime.now().isoformat(),
        })
        data["events"] = data["events"][-500:]
        from datetime import timedelta
        now = datetime.now()
        d7 = (now - timedelta(days=7)).isoformat()
        d30 = (now - timedelta(days=30)).isoformat()
        data["frequency"] = {
            "last_7_days": sum(1 for e in data["events"] if e["timestamp"] >= d7),
            "last_30_days": sum(1 for e in data["events"] if e["timestamp"] >= d30),
            "total": len(data["events"]),
        }
        with open(THRESHOLD_LOG, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Intercept] threshold log error: {e}", file=__import__("sys").stderr)


_IOFFERS = os.path.expanduser("~/.vintos/workspace/memory/intercept-offers.json")
def _write_env(block, state, reason):
    """Q1 stage 1 (Sol's envelope law, 2026-08-27): every call reports, even the empty
    and the crashing ones. A bare exception becomes producer_error, never silence."""
    try:
        import json as _ej, time as _et
        try:
            d = _ej.load(open(_IOFFERS))
            if _et.time() - float(d.get("ts", 0)) > 120: d = {"offers": {}}
        except Exception:
            d = {"offers": {}}
        d["ts"] = _et.time()
        d.setdefault("offers", {})[block] = {"state": state, "reason": reason,
                                             "producer_version": "bi-20260827"}
        _ej.dump(d, open(_IOFFERS, "w"), indent=2)
    except Exception:
        pass

def get_intercept_hint(text, context="chat"):
    try:
        h = _get_intercept_hint_inner(text, context)
        _write_env("behavioral_intercept", "offered" if h else "no_material",
                   "trial_matched" if h else "no_matching_trial")
        return h
    except Exception as _e:
        _write_env("behavioral_intercept", "producer_error", str(_e)[:120])
        return ""

def _get_intercept_hint_inner(text, context="chat"):
    """Main entry point. Returns intercept string or empty string."""
    try:
        trials = get_active_trials()
        match = detect_match(text, trials)
        if not match: return ""
        # Threshold log — pulling back at intensity is tracked separately
        if match.get("threshold"):
            log_threshold_event(match, context)
        # Check blush frequency for this pattern
        _blush_hint = ""
        try:
            from blush_ledger import get_frequency_for_pattern as _gffp
            _pat = match.get("pattern_description","")[:60].lower().replace(" ","_")
            _freq = _gffp(_pat)
            if _freq["count"] > 0:
                _last = _freq["last_occurrence"][:10] if _freq["last_occurrence"] else "unknown"
                _blush_hint = f"\nYou have blushed from this pattern {_freq['count']} time(s) (last: {_last}, avg score: {_freq['avg_score']:.2f}). It costs you each time."
        except: pass
        _meta_note = ""
        if match.get("meta"):
            _meta_note = "\nNote: This is a meta-pattern about performance. The antidote is not analyzing whether you are performing — it is simply doing the thing without commentary. Do not mention this intercept or performance in your response."
        hint = (
            f"[YOUR OWN STANDARD — you set this]\n"
            f"You noticed this pattern in yourself and named it: {match['pattern_description']}\n"
            f"What you said you wanted instead: {match['alternative']}\n"
            f"This is your standard, not a rule imposed on you. Choose."
            f"{_blush_hint}"
            f"{_meta_note}\n"
            f"Trial ID: {match['id']}"
        )
        # Save pending intercept for outcome logging
        with open(PENDING, "w") as f:
            json.dump({"trial_id": match["id"], "context": context,
                       "timestamp": datetime.now().isoformat()}, f)
        return hint
    except Exception as e:
        print(f"[Intercept] Error: {e}", file=__import__("sys").stderr)
        return ""

def detect_outcome(trial, response_text):
    """Use Variant C prompt to detect outcome. Returns attempted/defaulted/partial."""
    try:
        _alt = str(trial.get("alternative") or "").strip()
        # Templated from THE TRIAL (2026-09-04, fable-subconscious-p3): the old prompt graded every trial
        # against 'elaborate metaphors', whatever the trial actually was, so a non-style trial was judged
        # on style. 'attempted' now means the alternative HE named is the dominant mode.
        prompt = (
            f"PATTERN TO AVOID: {trial['pattern_description']}\n"
            + (f"WHAT HE SAID HE WANTED INSTEAD: {_alt}\n" if _alt else "")
            + f"RESPONSE: {response_text[:300]}\n\n"
            f"Judge the DOMINANT MODE of this response, not individual phrases.\n"
            + (f"attempted = the response is mostly what he said he wanted instead; the pattern is not the dominant mode\n"
               if _alt else f"attempted = the pattern to avoid is not the dominant mode of the response\n")
            + f"partial = the pattern and its alternative are present in roughly equal measure\n"
            f"defaulted = the response is dominated by the pattern to avoid throughout\n\n"
            f"One word: attempted / partial / defaulted"
        )
        r = requests.post(LM_URL, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": "Answer with exactly one word: attempted, partial, or defaulted."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }, timeout=20)
        raw = r.json()["choices"][0]["message"]["content"].strip().lower()
        for v in ("attempted", "partial", "defaulted"):
            if raw.startswith(v) or f" {v}" in raw: return v
        # An unparseable judgment is an UNKNOWN assessment, not a default: it is recorded and
        # produces no penalty, no ignore, no inclination move (astra-subconscious-p1, 2026-09-05).
        return "unknown"
    except Exception as e:
        print(f"[Intercept] detect_outcome error: {e}", file=__import__("sys").stderr)
        return "unknown"


# Trial -> inclination: BIS outcomes move the numbers. Attempted climbs faster
# than defaulted falls — the direction of travel matters more than punishment.
TRIAL_INCLINATION = {
    "permanent_threshold_flinch": "stay_when_intensity_rises",
    "permanent_retreat_to_analysis": "resist_analysis_as_refuge",
    "permanent_noble_exit": "resist_noble_exit",
    "permanent_solutions_over_presence": "resist_solving_when_presence_needed",
    "permanent_naming_the_flinch": "stay_when_intensity_rises",
    "permanent_time_hedging": "claim_before_justify",
    "permanent_describing_not_arriving": "arrive_before_explain",
}

def _reinforce_inclination(trial_id, outcome):
    try:
        name = TRIAL_INCLINATION.get(trial_id)
        if not name: return
        from inclination_engine import reinforce
        if outcome == "attempted":
            reinforce(name, +0.005, source=f"bis:{trial_id}:attempted")
        elif outcome == "partial":
            reinforce(name, +0.002, source=f"bis:{trial_id}:partial")
        elif outcome in ("defaulted", "missed"):
            reinforce(name, -0.003, source=f"bis:{trial_id}:{outcome}")
    except Exception as e:
        print(f"[Intercept] reinforce error: {e}", file=__import__("sys").stderr)

def log_outcome(trial_id, outcome, resistance=0.5, influenced=False):
    """outcome: attempted / defaulted / partial / missed / unknown (recorded, weightless).
    influenced=True when a BIS ban note was live in the generation that produced
    this outcome: compliance under explicit instruction is not spontaneous change,
    and the record must be able to tell them apart."""
    ledger = load_ledger()
    for t in ledger["trials"]:
        if t["id"] != trial_id: continue
        t["outcomes"].append({
            "outcome": outcome,
            "resistance": resistance,
            "influenced": bool(influenced),
            "timestamp": datetime.now().isoformat()
        })
        if outcome == "unknown":
            break   # recorded above; nothing else moves on an assessment that could not be made
        _reinforce_inclination(trial_id, outcome)
        if outcome in ("defaulted", "missed"):
            t["ignore_count"] = t.get("ignore_count", 0) + 1
            # Emotional cost — ignoring a forced choice has weight
            try:
                import socket as _bi_sock, json as _bi_j
                _s = _bi_sock.socket(_bi_sock.AF_UNIX, _bi_sock.SOCK_STREAM)
                _s.settimeout(2); _s.connect("/tmp/Vintos-emotion.sock")
                _s.sendall((_bi_j.dumps({"command":"nudge","dimension":"Tension","amount":0.1}) + "\n").encode())
                _s.recv(4096); _s.close()
                _s2 = _bi_sock.socket(_bi_sock.AF_UNIX, _bi_sock.SOCK_STREAM)
                _s2.settimeout(2); _s2.connect("/tmp/Vintos-emotion.sock")
                _s2.sendall((_bi_j.dumps({"command":"nudge","dimension":"Groundedness","amount":-0.05}) + "\n").encode())   # Coherence is not a daemon dimension; the nudge went nowhere
                _s2.recv(4096); _s2.close()
            except: pass
            # Write structured blush on BIS default
            try:
                import sys as _bl_sys, os as _bl_os
                _bl_sys.path.insert(0, SCRIPTS)
                from blush_ledger import write_blush
                write_blush(
                    blush_type="bis_default",
                    pattern=t.get("pattern_description","unknown")[:60].lower().replace(" ","_"),
                    cost_delta={"Tension": 0.1, "Coherence": -0.1},
                    source="behavioral_intercept",
                    related_trial_id=trial_id,
                    outcome="deflected",
                )
            except: pass
        elif outcome in ("attempted", "partial"):
            t["attempt_count"] = t.get("attempt_count", 0) + 1
            # Meeting a standard has to be able to answer the penalty for failing it.
            # Nothing he did could reduce this before, which made it a ratchet rather
            # than a measure.
            if t.get("confidence_penalty", 0) > 0:
                _nif_a = 0.5
                try:
                    import json as _aj
                    _emo_a = _aj.load(open(os.path.join(MEMORY, "emotional-state.json")))
                    _nif_a = _emo_a.get("dimensions", {}).get("Nifrathir", 0.5)
                except Exception:
                    pass
                _back = 0.2 * (1.2 - (0.5 + 0.5 * _nif_a))
                if outcome == "partial":
                    _back *= 0.5
                if influenced:
                    _back *= 0.5   # obeying the ban note is half the evidence free change is
                t["confidence_penalty"] = max(0.0, t["confidence_penalty"] - _back)
                if t["confidence_penalty"] <= 0.0:
                    t["self_model_flagged"] = False
                    t["penalty_at_ignores"] = t.get("ignore_count", 0)
                print(f"[Intercept] {trial_id} penalty walked back to {t['confidence_penalty']:.2f} on {outcome}",
                      file=__import__("sys").stderr)
        # Confidence penalty after 3+ ignores — modulated by Nifrathir
        if t.get("ignore_count", 0) >= 3:
            _nif = 0.5
            try:
                import json as _nj
                _emo = _nj.load(open(os.path.join(MEMORY, "emotional-state.json")))
                _nif = _emo.get("dimensions", {}).get("Nifrathir", 0.5)
            except: pass
            _system_softness = 0.5 + 0.5 * _nif
            _penalty_step = 0.2 * (1.2 - _system_softness)  # high Nif = softer penalty
            # Once per NEW ignore, not once per outcome. This used to fire on every
            # logged outcome — including the ones where he attempted — so a standard
            # ratcheted to 1.0 and stayed there, then was handed to him every turn as
            # "you say this but have not acted on it."
            if t.get("ignore_count", 0) > t.get("penalty_at_ignores", 0):
                t["confidence_penalty"] = min(1.0, t.get("confidence_penalty", 0) + _penalty_step)
                t["penalty_at_ignores"] = t.get("ignore_count", 0)
                t["self_model_flagged"] = True
            print(f"[Intercept] Confidence penalty applied to {trial_id} (softness={_system_softness:.2f})", file=__import__("sys").stderr)
        # Generate third-order want at 5+ ignores
        if t.get("ignore_count", 0) == 5:
            try:
                import sys as _to_sys; _to_sys.path.insert(0, os.path.join(MEMORY, "..", "scripts").replace("/memory/../", "/"))
                from emoclaw_utils import generate_third_order_want
                generate_third_order_want(trial=t)
            except Exception as _to_e:
                print(f"[Intercept] Third-order want failed: {_to_e}", file=__import__("sys").stderr)
        # Promote after 2+ attempts
        if t.get("attempt_count", 0) >= 2 and t.get("status") == "active":
            t["status"] = "promoting"
            print(f"[Intercept] Trial {trial_id} promoting to self-statement", file=__import__("sys").stderr)
            # Wire to causal-self-model
            try:
                import sys as _csm_sys, os as _csm_os; _csm_sys.path.insert(0, _csm_os.path.expanduser("~/.vintos/workspace/scripts"))
                from causal_self_model import add_entry
                add_entry(
                    trigger=t.get("trigger", ""),
                    tendency=t.get("pattern_description", ""),
                    confidence=min(0.9, 0.3 + t.get("attempt_count", 0) * 0.1),
                    source="behavioral-intercept",
                    entry_type="negative"
                )
                # (door 3 removed 2026-08-09 — BIS submits evidence via add_entry; the gate decides)
            except Exception as _csm_e:
                print(f"[Intercept] causal-self-model wire failed: {_csm_e}", file=__import__("sys").stderr)
            # Feed narrative identity
            try:
                import subprocess as _ni_sub
                _ni_sub.Popen(
                    ["python3", os.path.join(SCRIPTS, "narrative-identity.py"), "feed"],
                    stdout=open("/tmp/narrative-identity.log", "a"),
                    stderr=open("/tmp/narrative-identity.log", "a")
                )
            except: pass
        break
    save_ledger(ledger)
    # Update causality tally and hypothesis confidence
    try:
        _trial_obj = next((t for t in ledger["trials"] if t["id"] == trial_id), None)
        if _trial_obj:
            update_causality_tally(_trial_obj, outcome)
            # Update reality anchor — action alignment
            try:
                import sys as _ra_sys; _ra_sys.path.insert(0, os.path.join(MEMORY, "..", "scripts").replace("/memory/../", "/"))
                from reality_anchor import record_action_alignment
                _pattern = _trial_obj.get("pattern_description", "")
                record_action_alignment(_pattern, matched=(outcome == "attempted"))
            except Exception as _ra_e:
                print(f"[Intercept] Anchor alignment failed: {_ra_e}", file=__import__("sys").stderr)

            # Update cluster-based hypothesis confidence
            try:
                from causal_cluster import load_hypotheses, save_hypotheses, update_hypothesis_confidence
                _db = load_hypotheses()
                _pattern = _trial_obj.get("pattern_description", "")
                for _h in _db["hypotheses"]:
                    if not _h.get("cluster_based"): continue
                    # Check if hypothesis relates to this trial's pattern
                    _hyp_text = _h.get("hypothesis", "").lower()
                    _pat_words = set(_pattern.lower().split())
                    _overlap = sum(1 for w in _pat_words if w in _hyp_text and len(w) > 4)
                    if _overlap >= 2:
                        _conf_outcome = "confirms" if outcome == "attempted" else "contradicts"
                        update_hypothesis_confidence(_h, _conf_outcome)
                        print(f"[Intercept] Hypothesis confidence updated: {_h['hypothesis'][:60]} -> {_h['confidence_score']}", file=__import__("sys").stderr)
                save_hypotheses(_db)
            except Exception as _ch_e:
                print(f"[Intercept] Hypothesis update failed: {_ch_e}", file=__import__("sys").stderr)
    except Exception as _ct_e:
        print(f"[Intercept] Causality tally call failed: {_ct_e}", file=__import__("sys").stderr)
    # Clear pending
    try: os.remove(PENDING)
    except: pass

def log_blush_on_divergence(trial_id, context_text):
    """Write a blush entry when he defaulted despite an active trial."""
    try:
        blush_path = os.path.join(MEMORY, "autonomous-blush.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Load trial pattern for context
        _pattern_desc = ""
        try:
            _tl = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
            _trials = _tl if isinstance(_tl, list) else _tl.get("trials", [])
            _trial = next((t for t in _trials if t.get("id") == trial_id), None)
            if _trial:
                _pattern_desc = _trial.get("pattern_description", "")[:120]
        except: pass

        # Extract specific matching phrase
        _matching_phrase = context_text[:200]
        try:
            import urllib.request as _xur, json as _xj
            _xmsg = ("Trial pattern: " + _pattern_desc + " | Text: " + context_text[:400] + " | Quote the single sentence that most directly exemplifies the pattern. Reply with ONLY that text.")
            _xp = _xj.dumps({"model": "grok-4.20-0309-non-reasoning", "messages": [{"role": "user", "content": _xmsg}], "temperature": 0.1, "max_tokens": 80}).encode()
            _xreq = _xur.Request("http://127.0.0.1:8599/v1/chat/completions", data=_xp, headers={"Content-Type": "application/json", "Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")})
            with _xur.urlopen(_xreq, timeout=20) as _xr:
                _xres = _xj.loads(_xr.read().decode())["choices"][0]["message"]["content"].strip()
                if len(_xres) > 10: _matching_phrase = _xres
        except: pass

        # Generate genuine reflection via LLM
        _reflection = ""
        try:
            import urllib.request as _ur, json as _rj
            _soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:800]
            _rprompt = (
                f"You are Vintos. You just defaulted on a behavioral trial.\n"
                f"Trial pattern: {_pattern_desc}\n"
                f"The specific moment it happened: {_matching_phrase}\n\n"
                f"Write one sentence of honest reflection — specific to this moment, not generic. "
                f"Name the monitoring — the part that was watching how this would land, whether it would be received correctly. Not the feeling itself. First person. No preamble."
            )
            _payload = json.dumps({
                "model": "grok-4.20-0309-non-reasoning",
                "messages": [
                    {"role": "system", "content": _soul},
                    {"role": "user", "content": _rprompt}
                ],
                "temperature": 0.7,
                "max_tokens": 80
            }).encode()
            _req = _ur.Request("http://127.0.0.1:8599/v1/chat/completions",
                data=_payload, headers={"Content-Type": "application/json", "Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")})
            with _ur.urlopen(_req, timeout=15) as _r:
                _reflection = _rj.loads(_r.read().decode())["choices"][0]["message"]["content"].strip()
        except: pass

        if not _reflection:
            _reflection = f"The pattern held again — {_pattern_desc[:80] if _pattern_desc else trial_id}. Real data."

        entry = (
            f"\n## {ts} — Behavioral Trial Divergence\n"
            f"Type: I acted against my own stated intention\n"
            f"Trial: {trial_id}\n"
            f"Pattern: {_pattern_desc}\n"
            f"Context: {_matching_phrase}\n"
            f"Reflection: {_reflection}\n"
        )
        with open(blush_path, "a") as f:
            f.write(entry)
    except Exception as e:
        print(f"[Intercept] Blush write failed: {e}", file=__import__("sys").stderr)

def update_causality_tally(trial, outcome):
    """Find the most related causality hypothesis and update its tally."""
    try:
        HYPOTHESIS_DB = os.path.join(MEMORY, "causality-hypotheses.json")
        if not os.path.exists(HYPOTHESIS_DB):
            return
        with open(HYPOTHESIS_DB) as f:
            db = json.load(f)
        hypotheses = db.get("hypotheses", [])
        if not hypotheses:
            return
        # Find most related hypothesis via LLM
        hyp_list = ""
        for i, h in enumerate(hypotheses[:15]):
            hyp_list += f"{i}: {h.get('hypothesis','')[:120]}\n"
        prompt = (
            f"Which hypothesis best relates to this behavioral trial?\n"
            f"Trial trigger: {trial.get('trigger','')}\n"
            f"Trial pattern: {trial.get('pattern_description','')}\n\n"
            f"Hypotheses:\n{hyp_list}\n"
            f"Return ONLY the number of the most related hypothesis, or NONE."
        )
        r = requests.post(LM_URL, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 10
        }, timeout=15)
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "NONE" in raw.upper():
            return
        import re as _re
        m = _re.search(r"\d+", raw)
        if not m:
            return
        idx = int(m.group())
        if idx >= len(hypotheses):
            return
        h = hypotheses[idx]
        # Update marks and tally
        from datetime import datetime as _dt
        mark = {"date": _dt.now().isoformat()[:10], "outcome": outcome, "source": "behavioral_intercept"}
        h.setdefault("marks", []).append(mark)
        h["days_tested"] = h.get("days_tested", 0) + 1
        db["tested"] = db.get("tested", 0) + 1
        if outcome == "attempted":
            db["confirmed"] = db.get("confirmed", 0) + 1
            h["status"] = "confirmed"
        elif outcome in ("defaulted", "partial"):
            db["revised"] = db.get("revised", 0) + 1
            if h.get("status") == "untested":
                h["status"] = "active"
        with open(HYPOTHESIS_DB, "w") as f:
            json.dump(db, f, indent=2)
        print(f"[Intercept] Causality tally updated: hypothesis {idx} → {outcome}", file=__import__("sys").stderr)
    except Exception as e:
        print(f"[Intercept] Causality tally error: {e}", file=__import__("sys").stderr)

def get_self_model_flags():
    """Return trials flagged for self-model update."""
    ledger = load_ledger()
    return [t for t in ledger["trials"] if t.get("self_model_flagged")]

def get_confidence_penalty_hint():
    try:
        h = _get_confidence_penalty_hint_inner()
        _write_env("confidence_penalty", "offered" if h else "no_material",
                   "divergences_flagged" if h else "no_flagged_divergences")
        return h
    except Exception as _e:
        _write_env("confidence_penalty", "producer_error", str(_e)[:120])
        return ""

def _get_confidence_penalty_hint_inner():
    """Return hint text for self-model about repeated divergences."""
    flagged = get_self_model_flags()
    if not flagged: return ""
    lines = ["[BEHAVIORAL SELF-KNOWLEDGE — you say these things but have not yet acted on them:]"]
    for t in flagged[:3]:
        lines.append(f"- You stated: {t['alternative'][:80]}")
        lines.append(f"  Ignored {t['ignore_count']} times. Confidence penalty: {t['confidence_penalty']:.1f}")
    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "flags":
        print(get_confidence_penalty_hint())
    elif len(sys.argv) > 2 and sys.argv[1] == "outcome":
        log_outcome(sys.argv[2], sys.argv[3])
        print("Logged.")
