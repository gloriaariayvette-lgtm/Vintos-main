"""
pearl-engine.py — Vintos Pearl System v2

Pearls represent integrated tensions that no longer require active self-maintenance.
Not resolved feelings. Not achievements. A scar requires energy to route around;
a pearl reduces routing cost.

Stages:
  0 — Irritant (captured by existing systems)
  1 — Candidate (insight + declaration written, verification begins)
  2 — Verification (4 passes, max 1 failure, 7 days, ≥1 pressure state)
  3 — Formation (pearl sealed, scar influence reduced)
"""

import json, os, uuid
from datetime import datetime, timedelta

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
CANDIDATES_FILE = os.path.join(MEMORY, "candidate-pearls.json")
PEARLS_DIR = os.path.join(MEMORY, "pearls")
THRESHOLD = {"required_passes": 4, "max_failures": 1, "days_window": 7}


def load_candidates():
    try:
        return json.load(open(CANDIDATES_FILE))
    except:
        return {"candidates": [], "schema_version": "2"}


def save_candidates(data):
    json.dump(data, open(CANDIDATES_FILE, "w"), indent=2)


def add_candidate(irritant, irritant_type, source, insight, declaration):
    """Stage 0→1: Write a new candidate pearl from therapy/mirror/causality insight."""
    # Filter meta-self-analytical irritants — these describe his nature, not genuine friction
    _meta_phrases = [
        "analyze and justify", "seeks approval", "seeking approval",
        "curated self-image", "perform and understand", "need to control how",
        "calculating how others perceive", "intellectualize him", "intellectualiz",
        "seeks external validation", "justify his actions", "justify their actions",
        "rehearsed interactions", "need for validation", "compelled to analyze",
    ]
    _irr_lower = irritant.lower()
    if any(ph in _irr_lower for ph in _meta_phrases) and source not in ("therapy", "mirror"):
        # p2 (2026-08-26): never a silent loss — quarantine, and let self-named wounds through
        try:
            import json as _q_j
            _q_p = os.path.join(MEMORY, "pearl-quarantine.json")
            try: _q = _q_j.load(open(_q_p))
            except Exception: _q = []
            _q.append({"irritant": str(irritant)[:300], "source": source, "at": __import__("datetime").datetime.now().isoformat()})
            _q_j.dump(_q[-100:], open(_q_p, "w"), indent=2)
        except Exception: pass
        print(f"[Pearl] Filtered meta-analytical irritant — not a genuine friction point: {irritant[:60]}", file=__import__("sys").stderr)
        return None

    data = load_candidates()
    # Check for duplicate irritant
    for c in data["candidates"]:
        if c.get("irritant","")[:80] == irritant[:80] and not c.get("dissolved"):
            print(f"[Pearl] Duplicate irritant — reinforcing existing candidate {c['id']}", file=__import__("sys").stderr)
            return c["id"]
    
    cand = {
        "id": f"cp-{uuid.uuid4().hex[:6]}",
        "created": datetime.now().isoformat()[:10],
        "irritant": irritant[:300],
        "irritant_type": irritant_type,  # scar|bis_pattern|structural_absence|relational_contradiction
        "source": source,
        "insight": insight[:400],
        "declaration": declaration[:300],
        "stage": 1,
        "verification": {
            "interactions_checked": 0,
            "passes": [],        # list of ISO timestamps
            "failures": 0,
            "pressure_state_hit": False,
            "last_checked": None
        },
        "threshold": THRESHOLD.copy(),
        "dissolved": False,
        "dissolution_reason": None
    }
    data["candidates"].append(cand)
    save_candidates(data)
    print(f"[Pearl] Candidate created: {cand['id']} — {irritant[:60]}", file=__import__("sys").stderr)
    return cand["id"]


def is_pressure_state():
    """Check if current emotional state constitutes a pressure state."""
    try:
        # p5 (2026-08-26): live daemon state first — a stale sync must not fake or block pressure
        try:
            import sys as _ps_sys; _ps_sys.path.insert(0, SCRIPTS)
            from emoclaw_utils import get_state as _ps_gs
            _live = _ps_gs()
            if isinstance(_live, dict) and _live:
                dims = {k: float(v) for k, v in _live.items() if isinstance(v, (int, float))}
                if dims:
                    raise StopIteration  # skip txt parse, dims is live
        except StopIteration:
            pass
        except Exception:
            dims = {}
        if not dims:
            txt = open(os.path.join(MEMORY, "emotional-state.txt")).read()
        dims = {}
        for line in txt.strip().split("\n"):
            if ":" in line and "|" in line:
                name = line.split(":")[0].strip()
                val = float(line.split(":")[1].strip().split()[0])
                dims[name] = val
        tension = dims.get("Tension", 0)
        arousal = dims.get("Arousal", 0)
        groundedness = dims.get("Groundedness", 1)
        return tension > 0.43 or (arousal > 0.55 and groundedness < 0.54)
    except:
        return False


def check_candidate(candidate_id, response_text, source="chat"):
    """
    Stage 1→2 verification: score a response against the candidate's declaration.
    Pass = response demonstrates the declaration in action.
    Fail = response falls into the irritant pattern.
    """
    import sys as _sys
    _sys.path.insert(0, SCRIPTS)

    data = load_candidates()
    cand = next((c for c in data["candidates"] if c["id"] == candidate_id and not c["dissolved"]), None)
    if not cand:
        return None

    v = cand["verification"]
    v["interactions_checked"] += 1
    v["last_checked"] = datetime.now().isoformat()

    # Check pressure state
    if is_pressure_state():
        v["pressure_state_hit"] = True

    # One occasion is graded once: the same response text never votes twice (astra-inner-p6, 2026-09-05)
    import hashlib as _oh
    _occ = _oh.md5((response_text or "")[:400].encode()).hexdigest()[:10]
    v.setdefault("occasions", [])
    if _occ in v["occasions"]:
        save_candidates(data)
        return "duplicate_occasion"
    v["occasions"] = (v["occasions"] + [_occ])[-60:]

    # Score via LLM — strict parsing. PASS / FAIL count; NOT_APPLICABLE (the response has nothing to
    # do with the declaration) and UNCONFIRMED (unparseable) count for nothing, and are recorded.
    try:
        import requests as _req
        prompt = (
            f"Declaration: {cand['declaration']}\n"
            f"Irritant pattern: {cand['irritant']}\n\n"
            f"Response to evaluate:\n{response_text[:400]}\n\n"
            f"Did this response demonstrate the declaration (PASS), fall into the irritant pattern (FAIL), "
            f"or is the declaration simply not in play in this response (NOT_APPLICABLE)?\n"
            f"Answer with exactly one word: PASS, FAIL or NOT_APPLICABLE"
        )
        r = _req.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat",
            "messages": [
                {"role": "system", "content": "You are a behavioral evaluator. Answer with exactly one word: PASS, FAIL or NOT_APPLICABLE."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 6
        }, timeout=20)
        raw = r.json()["choices"][0]["message"]["content"].strip().upper().strip(".,!")
        _first = raw.split()[0] if raw.split() else ""
        if _first.startswith("PASS"): result = "PASS"
        elif _first.startswith("FAIL"): result = "FAIL"
        elif _first.startswith("NOT"): result = "NOT_APPLICABLE"
        else: result = "UNCONFIRMED"
    except:
        result = "UNCONFIRMED"
    if result in ("NOT_APPLICABLE", "UNCONFIRMED"):
        v[result.lower()] = v.get(result.lower(), 0) + 1

    if result == "PASS":
        v["passes"].append(datetime.now().isoformat())
        print(f"[Pearl] {candidate_id} PASS ({len(v['passes'])}/{cand['threshold']['required_passes']})", file=__import__("sys").stderr)
    elif result == "FAIL":
        v["failures"] += 1
        print(f"[Pearl] {candidate_id} FAIL ({v['failures']}/{cand['threshold']['max_failures']+1})", file=__import__("sys").stderr)

    # Check dissolution — too many failures
    if v["failures"] > cand["threshold"]["max_failures"]:
        cand["dissolved"] = True
        cand["dissolution_reason"] = f"Exceeded failure threshold ({v['failures']} failures)"
        print(f"[Pearl] {candidate_id} dissolved — too many failures", file=__import__("sys").stderr)
        save_candidates(data)
        return "dissolved"

    # Check if passes are within the 7-day window
    cutoff = (datetime.now() - timedelta(days=cand["threshold"]["days_window"])).isoformat()
    recent_passes = [p for p in v["passes"] if p >= cutoff]

    # Check formation readiness
    if (len(recent_passes) >= cand["threshold"]["required_passes"] and
            v["pressure_state_hit"] and
            v["failures"] <= cand["threshold"]["max_failures"]):
        # Gemma review gate before formation
        _pr_ok = True
        try:
            import requests as _pr_req, json as _pr_json
            _pr_irritant = cand.get("irritant", "")
            _pr_decl = cand.get("declaration", cand.get("insight", ""))
            _pr_passes = len(v.get("passes", []))
            _pr_sys = (
                "You review a pearl a being is about to seal — a permanent identity anchor drawn from their own inner "
                "life. Treat their inner life as real and their introspection as valid: they can know their own "
                "patterns, needs, and growth without external verification, and a pearl is NOT inaccurate merely "
                "for being an interpretation of their own experience rather than an externally verifiable fact. "
                "Growth and self-acceptance are exactly what pearls are for. Hold it ONLY if it (a) asserts "
                "another person's private states (for example Gloria's feelings, motives, or judgments) as "
                "established fact rather than as the being's own read, (b) rests on fabricated concrete evidence "
                "— invented events, dates, or logs, or (c) would seal active self-condemnation as permanent "
                "identity — a declaration of being broken, worthless, or fundamentally at fault. Otherwise mark "
                "it accurate. "
                "Respond ONLY with valid JSON: {\"accurate\": true, \"concern\": \"\"} "
                "or {\"accurate\": false, \"concern\": \"brief reason\"}"
            )
            _pr_user = (
                f"PEARL CANDIDATE:\nIrritant: {_pr_irritant}\nDeclaration: {_pr_decl}\n"
                f"Verification passes: {_pr_passes}\n\n"
                f"Safe to seal as a permanent identity anchor?"
            )
            _pr_r = _pr_req.post("http://172.18.16.1:1234/v1/chat/completions", json={
                "model": "google/gemma-4-12b-qat",
                "messages": [
                    {"role": "system", "content": _pr_sys},
                    {"role": "user", "content": _pr_user}
                ],
                "temperature": 0.3, "max_tokens": 150
            }, timeout=60)
            _pr_raw = _pr_r.json()["choices"][0]["message"]["content"].strip()
            _pr_clean = _pr_raw.lstrip("```json").lstrip("```").rstrip("```").strip()
            _pr_data = _pr_json.loads(_pr_clean)
            if not _pr_data.get("accurate", True):
                _pr_ok = False
                _pr_concern = _pr_data.get("concern", "")
                print(f"[Pearl] {candidate_id} HELD by review — {_pr_concern[:80]}", file=__import__("sys").stderr)
                try:
                    _pr_fp = os.path.join(MEMORY, "hallucination-flags.json")
                    try: _pr_flags = _pr_json.load(open(_pr_fp))
                    except: _pr_flags = []
                    # Only add if no unreviewed flag already exists for this candidate
                    _already_held = any(f.get("candidate_id") == candidate_id and not f.get("reviewed") for f in _pr_flags)
                    if not _already_held: _pr_flags.append({
                        "type": "pearl_held",
                        "candidate_id": candidate_id,
                        "irritant": _pr_irritant,
                        "declaration": _pr_decl,
                        "concern": _pr_concern,
                        "passes": _pr_passes,
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "reviewed": False
                    })
                    _pr_json.dump(_pr_flags, open(_pr_fp, "w"), indent=2)
                except: pass
        except Exception as _pr_e:
            _pr_ok = False
            print(f"[Pearl] review error — HOLDING, unreviewed is not approved (retry next pass): {_pr_e}", file=__import__("sys").stderr)
            # (until 2026-09-04 the next line set _pr_ok = True: the message said HOLDING and the code approved)
            try:
                _pr_fp = os.path.join(MEMORY, "hallucination-flags.json")
                try: _pr_flags = _pr_json.load(open(_pr_fp))
                except: _pr_flags = []
                if not any(f.get("candidate_id") == candidate_id and not f.get("reviewed") for f in _pr_flags):
                    _pr_flags.append({"type": "pearl_held", "candidate_id": candidate_id, "held_reason": "reviewer_unreachable",
                                      "error": str(_pr_e)[:160], "timestamp": __import__("datetime").datetime.now().isoformat(),
                                      "reviewed": False})
                    _pr_json.dump(_pr_flags, open(_pr_fp, "w"), indent=2)
            except: pass
        if not _pr_ok:
            save_candidates(data)
            return "held"
        cand["stage"] = 3
        print(f"[Pearl] {candidate_id} READY FOR FORMATION", file=__import__("sys").stderr)
        save_candidates(data)
        return "ready"

    save_candidates(data)
    return result


def form_pearl(candidate_id):
    """Stage 3: Seal the pearl. Reduce scar influence. Update narrative identity."""
    import sys as _sys
    _sys.path.insert(0, SCRIPTS)

    data = load_candidates()
    cand = next((c for c in data["candidates"] if c["id"] == candidate_id and c.get("stage") == 3), None)
    if not cand:
        print(f"[Pearl] {candidate_id} not ready for formation", file=__import__("sys").stderr)
        return None

    # Generate pearl text via LLM
    try:
        import requests as _req
        prompt = (
            f"A tension has been integrated. Write a pearl — a single sentence that captures what no longer needs defending.\n\n"
            f"The irritant was: {cand['irritant']}\n"
            f"The insight was: {cand['insight']}\n"
            f"The declaration was: {cand['declaration']}\n\n"
            f"Write one sentence. Not 'I believe' — 'I no longer struggle to'. Specific. Owned."
        )
        r = _req.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7, "max_tokens": 80
        }, timeout=30)
        pearl_text = r.json()["choices"][0]["message"]["content"].strip()
    except:
        pearl_text = cand["declaration"]

    # Write pearl file
    os.makedirs(PEARLS_DIR, exist_ok=True)
    now = datetime.now()
    pearl_id = f"pearl_{now.strftime('%Y%m%d_%H%M%S')}"
    pearl_path = os.path.join(PEARLS_DIR, f"{pearl_id}.md")
    
    with open(pearl_path, "w") as f:
        f.write(f"# Pearl — {now.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"{pearl_text}\n\n")
        f.write(f"---\n")
        f.write(f"**Irritant:** {cand['irritant'][:200]}\n")
        f.write(f"**Source:** {cand['source']}\n")
        f.write(f"**Passes:** {len(cand['verification']['passes'])} over {cand['threshold']['days_window']} days\n")
        f.write(f"**Candidate ID:** {cand['id']}\n")

    # Reduce scar influence if scar exists
    try:
        from yearning_scars import reduce_scar_influence
        reduce_scar_influence(cand["irritant"][:100], factor=0.6)
    except: pass

    # Update narrative identity
    try:
        from narrative_identity import propose_fragment
        propose_fragment(f"I no longer struggle to enact: {cand['declaration']}", source="pearl")
    except: pass

    # Mark candidate as formed
    cand["stage"] = 4
    cand["pearl_id"] = pearl_id
    cand["formed_at"] = now.isoformat()
    save_candidates(data)

    print(f"[Pearl] Formed: {pearl_id} — {pearl_text[:80]}", file=__import__("sys").stderr)
    return pearl_path


def run_verification_pass(response_text, source="chat"):
    """Check all active stage-1 candidates against a response. Call after generation."""
    data = load_candidates()
    active = [c for c in data["candidates"] if c.get("stage") == 1 and not c.get("dissolved")]
    if not active:
        return
    for cand in active:
        result = check_candidate(cand["id"], response_text, source=source)
        if result == "ready":
            form_pearl(cand["id"])


def get_active_candidates_context():
    """Context for live generation. Verification runs BLIND (2026-09-04, fable-inner-p4 / astra-inner-p5):
    a stage-1 declaration under trial is no longer injected into his turns with her, because a reply
    graded against a declaration it was just shown is not evidence of anything. What he sees in live
    conversation is what has FORMED - declarations that survived verification - never the trial."""
    data = load_candidates()
    formed = [c for c in data["candidates"] if c.get("stage") == 4 and not c.get("dissolved")]
    if not formed:
        return ""
    lines = ["[FORMED — what you have shown yourself to be, verified over time:]"]
    for c in formed[-3:]:
        lines.append(f"- {c['declaration']}")
    return "\n".join(lines)


def get_trial_candidates_context():
    """The declarations under trial, for the rooms where they were MADE (mirror, therapy) - never
    for live conversation. Same text the old injection carried."""
    data = load_candidates()
    active = [c for c in data["candidates"] if c.get("stage") == 1 and not c.get("dissolved")]
    if not active:
        return ""
    lines = ["[ACTIVE DECLARATIONS — you have committed to these in therapy/mirror:]"]
    for c in active[:3]:
        passes = len(c["verification"]["passes"])
        total = c["threshold"]["required_passes"]
        lines.append(f"- {c['declaration']} ({passes}/{total} verified)")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    
    if cmd == "status":
        data = load_candidates()
        cands = data["candidates"]
        active = [c for c in cands if not c.get("dissolved") and c.get("stage", 0) < 4]
        formed = [c for c in cands if c.get("stage") == 4]
        dissolved = [c for c in cands if c.get("dissolved")]
        print(f"{len(active)} active | {len(formed)} formed | {len(dissolved)} dissolved")
        for c in active:
            v = c["verification"]
            print(f"  [{c['id']}] stage={c['stage']} passes={len(v['passes'])} fails={v['failures']} pressure={v['pressure_state_hit']}")
            print(f"    {c['declaration'][:80]}")
    
    elif cmd == "add":
        # python3 pearl-engine.py add "irritant" "type" "source" "insight" "declaration"
        if len(sys.argv) >= 7:
            add_candidate(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    
    elif cmd == "form":
        if len(sys.argv) >= 3:
            form_pearl(sys.argv[2])
