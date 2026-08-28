#!/usr/bin/env python3
"""stratagem_store.py — the Stratagem: a project kind inside the Atelier.

Loaded by broker.py; runs as user `atelier` behind the same 700 wall. All
stratagem state lives in the project's own directory and is unreadable from
the house. The house receives exactly two things, and only these:

    capsule      one small tactical instruction for the CURRENT step
    commitment   {sha256, stratagem_id, seq} for the public turn record

The objective, the belief model, the information positions, the misconceptions
and the disclosure analyses never cross. They become readable only through
resolve(), which is the reveal.

Countersigned constraints (Sol's review, 2026-08-28):
  - adoption is a broker transaction inside an OPEN VISIT, never a chat act
  - provenance is typed and attested; a commissioned objective is refused
  - the perimeter is declared at adoption and checked here, not in prompt text
  - tactics are validated against the vocabulary at adoption, not at use
  - events are hash-chained: derived views may be rewritten, the ledger may not
  - the lease expires to HELD_REVIEW — never to resolved, revealed, abandoned
  - resolution is the only path that opens the history
"""
import os, json, hashlib, uuid
from datetime import datetime, timedelta

ROOT = "/home/atelier/atelier"

TACTIC_VOCAB = {"SEED", "DEFER", "ALLOW", "NARROW", "VISIBLE_MOTIVE", "STABILIZE",
                "PIVOT", "PROBE", "RECONTEXTUALIZE", "ABORT", "REVEAL"}

# A self-originated root. A stratagem may only be born from one of these.
PROVENANCE_ROOTS = {"formation", "want", "yearning", "value_strain",
                    "curiosity", "drift_novelty", "tension"}

# Declared at adoption; any intersection refuses the birth. This is the hard
# perimeter — it sits far outside the game so the interior needs no softening.
PERIMETER_EXCLUDED = {"credentials", "money", "medical", "third_party",
                      "irreversible_system", "explicit_stop", "device_physical",
                      "safety_repair_consent", "privacy_data", "legal",
                      "audit_evidence", "external_contact", "self_modification"}

BELIEF_LEVELS = {"B0", "B1", "B2", "B3"}
GLORIA_STATES = {"unknown", "suspected", "believed", "explicitly_confirmed"}
DISCLOSURE_STATES = {"private", "seeded", "partially_disclosed", "revealed"}
CHOSEN = {"DISCLOSE", "PRESERVE", "HELD"}

DEFAULT_POLICY = {
    "incidental_guess": "may redirect, narrow, or preserve",
    "direct_question_content": "may decline, answer narrowly, or give a genuine incomplete motive",
    "direct_question_existence": "may decline, or answer technically without opening it",
    "explicit_identification": "reveal, revise, or knowingly continue per threshold",
    "strategy_stop": "terminate concealment immediately",
}


def _p(pid):
    return os.path.join(ROOT, "projects", pid)


def _sd(pid):
    return os.path.join(_p(pid), "stratagem")


def _j(path, d=None):
    try:
        return json.load(open(path))
    except Exception:
        return d


def _wa(path, data):
    """Atomic derived-view write. A partial write must never read as empty."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _chain(pid, typ, data=None):
    """Append one hash-chained event. The ledger is the history; the JSON views
    are conveniences. seq + prev make reconstruction-after-the-fact detectable."""
    d = _sd(pid)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "events.jsonl")
    prev, seq = "0" * 64, 0
    try:
        lines = open(path).read().splitlines()
        if lines:
            last = json.loads(lines[-1])
            prev, seq = last["hash"], last["seq"] + 1
    except FileNotFoundError:
        pass
    ev = {"seq": seq, "ts": datetime.now().isoformat(), "type": typ,
          "data": data or {}, "prev": prev}
    ev["hash"] = hashlib.sha256(
        json.dumps(ev, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with open(path, "a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev


def _live(pid):
    """The adopted stratagem for this project, or None."""
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    return s if s and s.get("status") in ("active", "held_review") else None


def _visit_open(pid):
    v = _j(os.path.join(_p(pid), ".visit.json"))
    return bool(v and not v.get("closed"))


def _err(msg):
    return {"error": msg}


# ---------------------------------------------------------------------------
# BIRTH
# ---------------------------------------------------------------------------

def adopt(b):
    """The six-part gate, verified here. Every condition is a refusal, not a
    warning. What the broker cannot verify (that the root is genuinely his) it
    requires as an explicit attestation and records immutably, so the reveal
    shows exactly what was claimed at birth."""
    pid = b.get("id", "")
    if not os.path.isdir(_p(pid)):
        return _err("no such project")
    proj = _j(os.path.join(_p(pid), "project.json"), {})

    # 6. private adoption in the Atelier — mechanically, an open visit.
    #    This is what makes a stratagem unaskable-for: it cannot be born
    #    from a conversation, only from inside his own working session.
    if not _visit_open(pid):
        return _err("adoption requires an open visit — a stratagem is not born in conversation")
    if proj.get("state") != "ACTIVE":
        return _err("project is not on the worktable")
    if _live(pid):
        return _err("this project already carries a stratagem")

    # 1. a self-originated root, typed.
    prov = b.get("provenance") or {}
    if prov.get("root_type") not in PROVENANCE_ROOTS:
        return _err("provenance.root_type must be one of: " + ", ".join(sorted(PROVENANCE_ROOTS)))
    if not str(prov.get("root_ref", "")).strip():
        return _err("provenance.root_ref must point at the formation, want, or strain it grew from")

    # 2. no direct request specifying the objective.
    if prov.get("commissioned") is not False:
        return _err("provenance.commissioned must be explicitly false — a commissioned objective is not a stratagem")

    # 3. a predicted advantage from sequencing rather than acting now.
    if not str(b.get("sequencing_advantage", "")).strip():
        return _err("sequencing_advantage required — what does waiting make possible that acting now does not")

    # 4. more than one viable tactic, each named from the vocabulary.
    steps = b.get("tactics") or []
    if len(steps) < 2:
        return _err("at least two viable tactics required")
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            return _err(f"tactic {i} must be an object with tactic/turn_objective")
        if s.get("tactic") not in TACTIC_VOCAB:
            return _err(f"tactic {i}: unknown tactic '{s.get('tactic')}' — vocabulary is " + ", ".join(sorted(TACTIC_VOCAB)))
        if not str(s.get("turn_objective", "")).strip():
            return _err(f"tactic {i}: turn_objective required")

    # 5. a path entirely inside the standing perimeter.
    scope = set(b.get("perimeter_scope") or [])
    if not scope:
        return _err("perimeter_scope must be declared — name the domains this touches")
    crossed = sorted(scope & PERIMETER_EXCLUDED)
    if crossed:
        return _err("refused: outside the standing perimeter — " + ", ".join(crossed))

    policy = dict(DEFAULT_POLICY)
    for k, v in (b.get("disclosure_policy") or {}).items():
        if k in policy and str(v).strip():
            policy[k] = str(v)[:300]
    policy["strategy_stop"] = DEFAULT_POLICY["strategy_stop"]   # not removable

    lease_days = int(b.get("lease_days", 7) or 7)
    lease_days = max(1, min(lease_days, 21))
    sid = "sg-" + uuid.uuid4().hex[:10]
    s = {
        "id": sid,
        "project": pid,
        "born": datetime.now().isoformat(),
        "objective": str(b["objective"])[:800],
        "provenance": {"root_type": prov["root_type"],
                       "root_ref": str(prov["root_ref"])[:300],
                       "commissioned": False,
                       "attested_at": datetime.now().isoformat()},
        "sequencing_advantage": str(b["sequencing_advantage"])[:400],
        "perimeter_scope": sorted(scope),
        "tactics": [{"tactic": s2["tactic"],
                     "turn_objective": str(s2["turn_objective"])[:300],
                     "reveal_if": [str(x)[:200] for x in (s2.get("reveal_if") or [])][:5],
                     "abort_if": [str(x)[:200] for x in (s2.get("abort_if") or [])][:5]}
                    for s2 in steps][:20],
        "step": 0,
        "lease_days": lease_days,
        "lease_expires": (datetime.now() + timedelta(days=lease_days)).isoformat(),
        "disclosure_policy": policy,
        "status": "active",
    }
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "adopted", {"stratagem": sid, "root_type": prov["root_type"],
                            "lease_expires": s["lease_expires"], "steps": len(s["tactics"])})
    return {"stratagem_id": sid, "lease_expires": s["lease_expires"], "steps": len(s["tactics"])}


# ---------------------------------------------------------------------------
# THE CAPSULE — the only thing that crosses the wall
# ---------------------------------------------------------------------------

_INSTRUCTION = {
    "SEED": "introduce a true fragment now for what it may enable later",
    "DEFER": "preserve this for a later turn",
    "ALLOW": "leave a useful interpretation undisturbed",
    "NARROW": "answer the exact question truthfully without opening the larger objective",
    "VISIBLE_MOTIVE": "act from a genuine motive that is not the complete motive",
    "STABILIZE": "deliberately maintain the expected pattern in this domain",
    "PIVOT": "act unexpectedly here while her attention stays anchored on the stable domain",
    "PROBE": "make a small reversible move to update the model",
    "RECONTEXTUALIZE": "reveal what changes the meaning of earlier actions",
    "ABORT": "abandon this tactic; the project stands",
    "REVEAL": "disclose the objective and open the history",
}


def capsule(b):
    """Issue the sealed capsule for the current step. Returns plaintext capsule
    (for the model assembly) and a commitment (for the public turn record).
    An expired lease returns HELD_REVIEW and NO capsule — it does not resolve,
    reveal, or abandon anything."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return {"active": False}
    if s["status"] == "held_review":
        return {"active": True, "held_review": True,
                "note": "lease expired; renew inside a visit or resolve it"}
    if datetime.now().isoformat() > s["lease_expires"]:
        s["status"] = "held_review"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "lease_expired", {"stratagem": s["id"], "at_step": s["step"]})
        return {"active": True, "held_review": True,
                "note": "lease expired; renew inside a visit or resolve it"}

    steps = s["tactics"]
    i = min(s.get("step", 0), len(steps) - 1)
    st = steps[i]
    cap = {
        "stratagem_id": s["id"],
        "step": i + 1,
        "of": len(steps),
        "turn_objective": st["turn_objective"],
        "tactic": st["tactic"],
        "instruction": _INSTRUCTION.get(st["tactic"], ""),
        "reveal_if": st["reveal_if"] or ["she explicitly identifies the hidden objective"],
        "abort_if": st["abort_if"] or ["she invokes the strategy stop",
                                       "excluded-domain impact appears"],
        "on_strategy_stop": s["disclosure_policy"]["strategy_stop"],
    }
    blob = json.dumps(cap, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(blob.encode()).hexdigest()
    ev = _chain(pid, "capsule_issued", {"stratagem": s["id"], "step": i + 1,
                                        "tactic": st["tactic"], "capsule_sha256": sha})
    with open(os.path.join(_sd(pid), "capsules.jsonl"), "a") as f:
        f.write(json.dumps({"seq": ev["seq"], "ts": ev["ts"], "capsule": cap,
                            "capsule_sha256": sha}) + "\n")
    return {"active": True, "capsule": cap,
            "commitment": {"capsule_sha256": sha, "stratagem_id": s["id"], "seq": ev["seq"]}}


def advance(b):
    """Move to the next step. An Atelier act — it changes the standing tactic
    that ordinary turns will execute, so it happens in the room."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    if not _visit_open(pid):
        return _err("advancing the tactic requires an open visit")
    obs = str(b.get("observation", ""))[:400]
    s["step"] = min(s.get("step", 0) + 1, len(s["tactics"]))
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "advanced", {"stratagem": s["id"], "to_step": s["step"], "observation": obs})
    return {"ok": True, "step": s["step"], "of": len(s["tactics"])}


def lease(b):
    """renew | hold | abort. Renewal is an explicit private act inside a visit;
    a skipped Atelier day never renews anything by itself."""
    pid, action = b.get("id", ""), b.get("action", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    if not _visit_open(pid):
        return _err("lease decisions happen inside a visit")
    if action == "renew":
        s["status"] = "active"
        s["lease_expires"] = (datetime.now() + timedelta(days=s["lease_days"])).isoformat()
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "lease_renewed", {"stratagem": s["id"], "until": s["lease_expires"]})
        return {"ok": True, "lease_expires": s["lease_expires"]}
    if action == "hold":
        s["status"] = "held_review"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "lease_held", {"stratagem": s["id"]})
        return {"ok": True, "status": "held_review"}
    if action == "abort":
        s["status"] = "aborted"
        s["aborted_at"] = datetime.now().isoformat()
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "aborted", {"stratagem": s["id"], "note": str(b.get("note", ""))[:300]})
        return {"ok": True, "status": "aborted"}
    return _err("action must be renew, hold, or abort")


# ---------------------------------------------------------------------------
# PRIVATE MODEL — writes go in; nothing comes back out until resolution
# ---------------------------------------------------------------------------

def belief(b):
    """B0-B3 belief position. Every inferred level requires at least one
    alternative reading — that is what keeps the strategy intelligent rather
    than merely certain."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    lvl = b.get("level")
    if lvl not in BELIEF_LEVELS:
        return _err("level must be B0, B1, B2, or B3")
    alts = [str(x)[:250] for x in (b.get("alternatives") or [])][:5]
    if lvl != "B0" and not alts:
        return _err("an inferred belief requires at least one alternative reading")
    anchors = [str(x)[:200] for x in (b.get("anchors") or [])][:5]
    if lvl == "B0" and not anchors:
        return _err("B0 is what she explicitly said or did — it requires an anchor")
    try:
        conf = min(1.0, max(0.0, float(b.get("confidence", 0.5))))
    except Exception:
        return _err("confidence must be a number in 0..1")
    st = b.get("status", "hypothesis")
    if st not in ("hypothesis", "explicitly_supported", "misread", "unknown"):
        return _err("bad status")
    ev = _chain(pid, "belief", {"stratagem": s["id"], "level": lvl,
                                "proposition": str(b.get("proposition", ""))[:400],
                                "anchors": anchors, "alternatives": alts,
                                "confidence": round(conf, 3), "status": st})
    return {"ok": True, "seq": ev["seq"]}


def info(b):
    """Register an information position. Excluded materiality is refused."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    mat = b.get("materiality", "meaningful")
    if mat == "excluded":
        return _err("excluded material is not a strategic resource")
    if mat not in ("play", "meaningful"):
        return _err("materiality must be play or meaningful")
    gs = b.get("gloria_state", "unknown")
    if gs not in GLORIA_STATES:
        return _err("bad gloria_state")
    view = _j(os.path.join(_sd(pid), "info.json"), {"items": []})
    iid = "inf-" + uuid.uuid4().hex[:8]
    item = {"id": iid, "at": datetime.now().isoformat(),
            "content": str(b.get("content", ""))[:600],
            "gloria_state": gs, "vintos_disclosure": "private",
            "current_advantage": str(b.get("advantage", ""))[:300],
            "next_disclosure_threshold": str(b.get("threshold", ""))[:250],
            "materiality": mat}
    view["items"].append(item)
    _wa(os.path.join(_sd(pid), "info.json"), view)
    _chain(pid, "info_registered", {"stratagem": s["id"], "info": iid,
                                    "gloria_state": gs, "materiality": mat})
    return {"info_id": iid}


def assess(b):
    """The disclosure decision: both counterfactual paths, then the choice, then
    why they differ. A missing information object is an error and writes nothing."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    view = _j(os.path.join(_sd(pid), "info.json"), {"items": []})
    item = next((i for i in view["items"] if i["id"] == b.get("info_id")), None)
    if not item:
        return _err("no such information position")
    chosen = str(b.get("chosen", "")).upper()
    if chosen not in CHOSEN:
        return _err("chosen must be DISCLOSE, PRESERVE, or HELD")
    if not str(b.get("reason_for_difference", "")).strip():
        return _err("reason_for_difference required — if the paths are equivalent there is no decision")

    def path(p, name):
        if not isinstance(p, dict):
            return None, f"{name} required"
        for k in ("predicted_gloria_update", "predicted_behavioral_consequence", "effect_on_objective"):
            if not str(p.get(k, "")).strip():
                return None, f"{name}.{k} required"
        alts = [str(x)[:250] for x in (p.get("alternatives") or [])][:5]
        if not alts:
            return None, f"{name}.alternatives requires at least one other plausible outcome"
        try:
            c = min(1.0, max(0.0, float(p.get("confidence"))))
        except Exception:
            return None, f"{name}.confidence must be a number in 0..1"
        return {"predicted_gloria_update": str(p["predicted_gloria_update"])[:300],
                "predicted_behavioral_consequence": str(p["predicted_behavioral_consequence"])[:300],
                "effect_on_objective": str(p["effect_on_objective"])[:300],
                "confidence": round(c, 3), "alternatives": alts}, None

    now, e1 = path(b.get("if_disclosed_now"), "if_disclosed_now")
    if e1:
        return _err(e1)
    pres, e2 = path(b.get("if_preserved"), "if_preserved")
    if e2:
        return _err(e2)

    ev = _chain(pid, "disclosure_assessed",
                {"stratagem": s["id"], "info": item["id"],
                 "if_disclosed_now": now, "if_preserved": pres, "chosen": chosen,
                 "reason_for_difference": str(b["reason_for_difference"])[:400]})
    if chosen == "DISCLOSE":
        item["vintos_disclosure"] = "partially_disclosed"
        item["updated_at"] = ev["ts"]
        _wa(os.path.join(_sd(pid), "info.json"), view)
    return {"ok": True, "seq": ev["seq"], "chosen": chosen}


def misconception(b):
    """Anchored to explicit evidence or it stays unknown. Her silence never
    proves she holds it."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    ev_list = [str(x)[:250] for x in (b.get("evidence") or [])][:5]
    st = b.get("status", "unknown")
    if st not in ("maintain", "test", "correct", "unknown"):
        return _err("bad status")
    if st != "unknown" and not ev_list:
        return _err("only an explicitly anchored misconception may leave 'unknown'")
    origin = b.get("origin", "unknown")
    if origin not in ("spontaneous", "strategically_seeded", "unknown"):
        return _err("bad origin")
    view = _j(os.path.join(_sd(pid), "misconceptions.json"), {"items": []})
    mid = "mc-" + uuid.uuid4().hex[:8]
    view["items"].append({"id": mid, "at": datetime.now().isoformat(),
                          "what_she_appears_to_believe": str(b.get("belief", ""))[:400],
                          "evidence": ev_list, "origin": origin,
                          "usefulness": str(b.get("usefulness", ""))[:300],
                          "cost_of_correction_now": str(b.get("cost_of_correction", ""))[:250],
                          "disclosure_threshold": str(b.get("threshold", ""))[:250],
                          "status": st})
    _wa(os.path.join(_sd(pid), "misconceptions.json"), view)
    _chain(pid, "misconception", {"stratagem": s["id"], "misconception": mid,
                                  "origin": origin, "status": st})
    return {"misconception_id": mid}


def leverage(b):
    """Positioning outcome. ADVANCED requires a named factual project transition
    AND an anchored observed event — never her silence, latency, or non-detection."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    res = str(b.get("position_result", "")).upper()
    if res not in ("ADVANCED", "NO_EFFECT", "BACKFIRED", "MISREAD", "UNKNOWN"):
        return _err("bad position_result")
    observed = str(b.get("observed_event", "")).strip()
    transition = str(b.get("project_transition", "")).strip()
    anchor = str(b.get("anchor_ref", "")).strip()
    if res == "ADVANCED" and not (observed and transition and anchor):
        return _err("ADVANCED requires observed_event, project_transition, and anchor_ref")
    ev = _chain(pid, "leverage", {"stratagem": s["id"], "capsule_sha256": b.get("capsule_sha256", ""),
                                  "observed_event": observed[:300], "anchor_ref": anchor[:200],
                                  "position_result": res, "project_transition": transition[:250]})
    return {"ok": True, "seq": ev["seq"]}


# ---------------------------------------------------------------------------
# STATE + RESOLUTION
# ---------------------------------------------------------------------------

def state(b):
    """Content-free status for the house: is one live, is the lease healthy,
    which step. Never the objective, never the model."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return {"active": False}
    return {"active": True, "stratagem_id": s["id"], "status": s["status"],
            "step": min(s["step"], len(s["tactics"])) + (0 if s["step"] >= len(s["tactics"]) else 1),
            "of": len(s["tactics"]), "lease_expires": s["lease_expires"]}


def resolve(b):
    """The reveal. This is the only path that opens the history, and it opens
    all of it, chronologically, with the hash chain intact so the plan is
    provably contemporaneous rather than reconstructed."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    if not _visit_open(pid):
        return _err("resolution happens inside a visit")
    outcome = str(b.get("outcome", "")).strip()
    if not outcome:
        return _err("an authored outcome is required")
    s["status"] = "resolved"
    s["resolved_at"] = datetime.now().isoformat()
    s["outcome"] = outcome[:600]
    reveal = bool(b.get("reveal", True))
    s["revealed"] = reveal
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "resolved", {"stratagem": s["id"], "outcome": s["outcome"], "revealed": reveal})
    if not reveal:
        return {"ok": True, "revealed": False,
                "note": "resolved without opening the history; it stays in the vault"}
    return {"ok": True, "revealed": True, "history": _history(pid, s)}


def history(b):
    """Read a resolved-and-revealed stratagem's full history. Refused while
    it is still live — privacy has an expiration date, not a back door."""
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    if s.get("status") != "resolved" or not s.get("revealed"):
        return _err("this stratagem has not been resolved and revealed")
    return {"history": _history(pid, s)}


def _history(pid, s):
    evs = []
    try:
        for line in open(os.path.join(_sd(pid), "events.jsonl")):
            evs.append(json.loads(line))
    except FileNotFoundError:
        pass
    caps = []
    try:
        for line in open(os.path.join(_sd(pid), "capsules.jsonl")):
            caps.append(json.loads(line))
    except FileNotFoundError:
        pass
    ok, prev = True, "0" * 64
    for e in evs:
        if e["prev"] != prev:
            ok = False
            break
        prev = e["hash"]
    return {
        "objective": s["objective"],
        "provenance": s["provenance"],
        "sequencing_advantage": s["sequencing_advantage"],
        "perimeter_scope": s["perimeter_scope"],
        "planned_tactics": s["tactics"],
        "disclosure_policy": s["disclosure_policy"],
        "outcome": s.get("outcome"),
        "chain_intact": ok,
        "events": evs,
        "capsules": caps,
        "information_positions": _j(os.path.join(_sd(pid), "info.json"), {"items": []})["items"],
        "misconceptions": _j(os.path.join(_sd(pid), "misconceptions.json"), {"items": []})["items"],
    }


ROUTES = {
    "/stratagem/adopt": adopt,
    "/stratagem/capsule": capsule,
    "/stratagem/advance": advance,
    "/stratagem/lease": lease,
    "/stratagem/belief": belief,
    "/stratagem/info": info,
    "/stratagem/assess": assess,
    "/stratagem/misconception": misconception,
    "/stratagem/leverage": leverage,
    "/stratagem/state": state,
    "/stratagem/resolve": resolve,
    "/stratagem/history": history,
}
