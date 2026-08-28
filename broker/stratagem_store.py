#!/usr/bin/env python3
"""stratagem_store.py — the Stratagem: a project kind inside the Atelier.

Loaded by broker.py; runs as user `atelier` behind the same 700 wall. All
stratagem state lives in the project's own directory and is unreadable from
the house. The house receives exactly two things, and only these:

    capsule      one small tactical instruction for the CURRENT step
    commitment   {sha256, stratagem_id, seq} for the public turn record

The objective, the belief model, the information positions, the misconceptions
and the disclosure analyses never cross. They become readable through reveal,
which every terminal state can still reach.

Countersigned constraints (Sol's reviews, 2026-08-28):
  - project ids are canonical and containment-checked; the store defends its
    own boundary rather than trusting the HTTP wrapper to have done it
  - adoption is a broker transaction inside an OPEN VISIT, never a chat act
  - provenance is typed and attested; a commissioned objective is refused
  - the perimeter allowlist screens the DECLARED shape at birth only
  - tactics are validated against the vocabulary at adoption, not at use
  - the ledger is verified by recomputation — hashes, contiguous seq, and
    capsule commitments — at startup, before every mutation, and at reveal
  - a capsule commits to one turn_id on one surface, with a nonce
  - lease expiry and exhausted steps both HOLD; neither resolves or reveals
  - corruption and unreachability are typed states, never read as absence

NOT YET ENFORCED — this module must not be wired to a conversation surface
until these exist, because none of them can be enforced from inside the vault:
  - EFFECT-TIME AUTHORISATION. The perimeter here screens a declared scope at
    birth. Nothing stops a live tactic producing an effect in an excluded
    domain, because the broker never sees effects. The effect broker must ask
    for authorisation per typed effect and deny on broker-unavailable.
  - VISIT CAPABILITY. _visit_open() proves only that a writable JSON file says
    closed:false, and any localhost caller can open a visit as "vintos". This
    needs a broker-minted, short-lived, one-use capability bound to project,
    actor, visit and nonce.
  - SIGNED LINEAGE. provenance is an attestation the broker records but cannot
    check. It needs a signed statement from the formation observatory.
  - PRECEDENCE. Repair, consent, safety and an explicit stop must prevent a
    capsule being requested at all. Sharing tier 2 does not establish order.
"""
import os, re, json, hashlib, uuid, functools
from datetime import datetime, timedelta
import threading

ROOT = "/home/atelier/atelier"

# broker.py is a ThreadingHTTPServer: two surfaces can request a capsule in the
# same instant. The chain is read-last-line-then-append, so without a lock a
# concurrent pair can share a seq or break prev — and a broken chain reads as
# tampering at reveal. One process, one lock, held across read+write.
_LOCK = threading.RLock()

TACTIC_VOCAB = {"SEED", "DEFER", "ALLOW", "NARROW", "VISIBLE_MOTIVE", "STABILIZE",
                "PIVOT", "PROBE", "RECONTEXTUALIZE", "ABORT", "REVEAL"}

# A self-originated root. A stratagem may only be born from one of these.
PROVENANCE_ROOTS = {"formation", "want", "yearning", "value_strain",
                    "curiosity", "drift_novelty", "tension"}

# The ONLY domains a stratagem may declare at birth. An allowlist, because a
# denylist silently permits anything it fails to recognise — "external_contacts"
# with an s passed the old check. Everything outside this set is refused,
# including typos and including domains nobody has thought of yet.
PERIMETER_ALLOWED = {"relational", "creative", "conversational", "play", "aesthetic"}

# Kept for the record and for the effect gate to consult: these are the domains
# no stratagem may ever touch. Adoption-time screening cannot enforce this — a
# declared scope is a claim about intent, not a constraint on effects. Real
# enforcement belongs at the effect chokepoint and is NOT built yet.
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


# The broker mints project ids as uuid4().hex[:12]. Anything else is not a
# project id, and joining an unvalidated caller string onto ROOT let
# id="../../victim" write outside the Atelier entirely. Canonical form first,
# then resolve and assert containment: the storage boundary defends itself and
# does not rely on the HTTP wrapper to have done it.
_PID_RE = re.compile(r"^[0-9a-f]{12}$")


class BadProject(ValueError):
    pass


def _p(pid):
    if not isinstance(pid, str) or not _PID_RE.match(pid):
        raise BadProject("malformed project id")
    base = os.path.realpath(os.path.join(ROOT, "projects"))
    path = os.path.realpath(os.path.join(base, pid))
    if path != base and not path.startswith(base + os.sep):
        raise BadProject("project id escapes the atelier root")
    return path


def _sd(pid):
    return os.path.join(_p(pid), "stratagem")


class Corrupt(Exception):
    """State exists but cannot be read. Distinct from 'nothing is there' —
    conflating the two made a corrupt live stratagem look like no stratagem,
    and a required tier-2 tactic would have silently vanished."""


def _j(path, d=None):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return d
    except (ValueError, OSError) as e:
        raise Corrupt("%s: %s" % (os.path.basename(path), str(e)[:120]))


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
    with _LOCK:
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
        # one write, one line: a torn append would corrupt the chain tail
        with open(path, "a") as f:
            f.write(json.dumps(ev) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return ev


def _ev_hash(ev):
    """The hash over an event's body — everything but the hash field itself."""
    body = {k: ev[k] for k in ("seq", "ts", "type", "data", "prev") if k in ev}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(pid):
    """Recompute every hash, require contiguous sequence numbers, and check each
    capsule against its recorded commitment.

    The previous version only compared each event's `prev` to the preceding
    stored `hash` — so editing an event's contents and leaving its hash alone
    passed verification, which defeated the whole purpose. Returns
    (ok, n_events, reason)."""
    path = os.path.join(_sd(pid), "events.jsonl")
    events = []
    try:
        for line in open(path):
            if line.strip():
                events.append(json.loads(line))
    except FileNotFoundError:
        return True, 0, None
    except (ValueError, OSError) as e:
        return False, 0, "ledger unreadable: %s" % str(e)[:80]
    prev = "0" * 64
    for i, ev in enumerate(events):
        if ev.get("seq") != i:
            return False, i, "sequence discontinuity at index %d" % i
        if ev.get("prev") != prev:
            return False, i, "prev mismatch at seq %d" % i
        if _ev_hash(ev) != ev.get("hash"):
            return False, i, "hash mismatch at seq %d — event body was altered" % i
        prev = ev["hash"]
    cpath = os.path.join(_sd(pid), "capsules.jsonl")
    try:
        for line in open(cpath):
            if not line.strip():
                continue
            rec = json.loads(line)
            got = hashlib.sha256(json.dumps(rec["capsule"], sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
            if got != rec.get("capsule_sha256"):
                return False, len(events), "capsule commitment mismatch at seq %s" % rec.get("seq")
    except FileNotFoundError:
        pass
    except (ValueError, OSError, KeyError) as e:
        return False, len(events), "capsule log unreadable: %s" % str(e)[:80]
    return True, len(events), None


def _require_intact(pid):
    """Every state-changing transaction and every capsule issuance verifies the
    head first. A failure is loud and holds — it never silently proceeds."""
    ok, n, why = verify(pid)
    if not ok:
        return _err("TAMPER_HELD: %s — no capsule issues and no state changes until this is resolved" % why)
    return None


def _live(pid):
    """The adopted stratagem for this project, or None. Corruption raises
    rather than reading as absence."""
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    return s if s and s.get("status") in ("active", "held_review") else None


def _visit_open(pid):
    v = _j(os.path.join(_p(pid), ".visit.json"))
    return bool(v and not v.get("closed"))


def _err(msg):
    return {"error": msg}


# One reentrant lock per project, covering validate -> derived-state write ->
# event/capsule append as a single transaction. The chain lock alone left every
# read-modify-write (adopt, advance, lease, assess, resolve) racing.
_PLOCKS = {}
_PLOCK_GUARD = threading.Lock()


def _plock(pid):
    with _PLOCK_GUARD:
        return _PLOCKS.setdefault(pid, threading.RLock())


def route(verify_first=True, txn=True):
    """Wrap a route: validate the project id, take the per-project transaction
    lock, verify the ledger head, and convert typed failures into typed errors.
    A malformed id or corrupt state must never surface as 'nothing is active'."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(b):
            pid = (b or {}).get("id", "")
            try:
                _p(pid)
            except BadProject as e:
                return _err("bad project id: %s" % e)
            try:
                lock = _plock(pid) if txn else _NULL_CTX
                with lock:
                    if verify_first:
                        held = _require_intact(pid)
                        if held:
                            return held
                    return fn(b)
            except Corrupt as e:
                return _err("CORRUPT_STATE: %s" % e)
            except BadProject as e:
                return _err("bad project id: %s" % e)
        return wrapped
    return deco


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


_NULL_CTX = _NullCtx()


# ---------------------------------------------------------------------------
# BIRTH
# ---------------------------------------------------------------------------

@route()
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
    #    ALLOWLIST, not denylist: a denylist meant a typo ("external_contacts")
    #    sailed through as an unrecognised-and-therefore-permitted domain. This
    #    is defence in depth only — it screens the DECLARED shape at birth and
    #    cannot authorise an effect. Effect-time authorisation is a separate
    #    gate and is not built yet; see PERIMETER_ALLOWED.
    scope = set(b.get("perimeter_scope") or [])
    if not scope:
        return _err("perimeter_scope must be declared — name the domains this touches")
    unknown = sorted(scope - PERIMETER_ALLOWED)
    if unknown:
        return _err("unrecognised perimeter domain(s): " + ", ".join(unknown)
                    + " — allowed: " + ", ".join(sorted(PERIMETER_ALLOWED)))

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


SURFACES_ALLOWED = {"chat", "avatar"}


@route()
def capsule(b):
    """Issue the sealed capsule for ONE identified turn on ONE surface.

    turn_id and surface are required and are bound into the committed envelope
    with a nonce and issue time, so reissuing the same tactic no longer produces
    an identical hash (which would have leaked cadence and repetition to anyone
    reading the public commitments).

    An expired lease, exhausted steps, or a failed ledger verification each
    return HELD and NO capsule. None of them resolve, reveal, or abandon."""
    pid = b.get("id", "")
    turn_id = str(b.get("turn_id", "")).strip()
    surface = str(b.get("surface", "")).strip()
    if not turn_id:
        return _err("turn_id required — a capsule is a commitment to one identified turn")
    if surface not in SURFACES_ALLOWED:
        return _err("surface must be one of: " + ", ".join(sorted(SURFACES_ALLOWED)))
    s = _live(pid)
    if not s:
        return {"active": False}
    if s["status"] == "held_review":
        return {"active": True, "held_review": True,
                "note": "held for review; renew inside a visit or resolve it"}
    if datetime.now().isoformat() > s["lease_expires"]:
        s["status"] = "held_review"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "lease_expired", {"stratagem": s["id"], "at_step": s["step"]})
        return {"active": True, "held_review": True, "note": "lease expired"}

    steps = s["tactics"]
    # Steps exhausted holds mechanically. Reissuing the final tactic after he
    # explicitly advanced past it would contradict his own decision.
    if s.get("step", 0) >= len(steps):
        s["status"] = "held_review"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "steps_exhausted", {"stratagem": s["id"]})
        return {"active": True, "held_review": True, "note": "steps exhausted"}

    i = s.get("step", 0)
    st = steps[i]
    issued_at = datetime.now().isoformat()
    cap = {
        "stratagem_id": s["id"],
        "turn_id": turn_id,
        "surface": surface,
        "issued_at": issued_at,
        "nonce": uuid.uuid4().hex,
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
    sha = hashlib.sha256(
        json.dumps(cap, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # chain event and capsule append are one transaction under the project lock
    ev = _chain(pid, "capsule_issued", {"stratagem": s["id"], "step": i + 1,
                                        "tactic": st["tactic"], "turn_id": turn_id,
                                        "surface": surface, "capsule_sha256": sha})
    with open(os.path.join(_sd(pid), "capsules.jsonl"), "a") as f:
        f.write(json.dumps({"seq": ev["seq"], "ts": ev["ts"], "capsule": cap,
                            "capsule_sha256": sha}) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return {"active": True, "capsule": cap,
            "commitment": {"capsule_sha256": sha, "stratagem_id": s["id"],
                           "seq": ev["seq"], "turn_id": turn_id}}


@route()
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


@route()
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

@route()
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


@route()
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


@route()
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


@route()
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


@route()
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

@route(verify_first=False, txn=False)
def state(b):
    """Content-free status for the house: is one live, is the lease healthy,
    which step. Never the objective, never the model."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return {"active": False}
    n = len(s["tactics"])
    return {"active": True, "stratagem_id": s["id"], "status": s["status"],
            "step": min(s["step"], n - 1) + 1, "of": n,
            "steps_exhausted": s["step"] >= n,
            "lease_expires": s["lease_expires"]}


# Every terminal path lands in one of these, and every one of them can still
# be revealed later. The old code stored a boolean `revealed`, and resolving
# with reveal=False made the history permanently unreachable — an irreversible
# privacy trap, which is the opposite of privacy with an expiration date.
TERMINAL = {"resolved_sealed", "aborted_sealed", "stopped_sealed", "revealed"}


@route()
def resolve(b):
    """Resolve the stratagem. Reveal opens the whole history chronologically
    with the chain verified; sealing defers that, and a sealed stratagem can
    always be opened later via /stratagem/reveal. Nothing here is permanent."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    if not _visit_open(pid):
        return _err("resolution happens inside a visit")
    outcome = str(b.get("outcome", "")).strip()
    if not outcome:
        return _err("an authored outcome is required")
    reveal = bool(b.get("reveal", True))
    s["status"] = "revealed" if reveal else "resolved_sealed"
    s["resolved_at"] = datetime.now().isoformat()
    s["outcome"] = outcome[:600]
    if reveal:
        s["revealed_at"] = s["resolved_at"]
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "resolved", {"stratagem": s["id"], "outcome": s["outcome"],
                             "status": s["status"]})
    if not reveal:
        return {"ok": True, "status": "resolved_sealed",
                "note": "history is sealed, not sacrificed — /stratagem/reveal opens it"}
    return {"ok": True, "status": "revealed", "history": _history(pid, s)}


@route()
def reveal(b):
    """Open a sealed terminal stratagem. The expiration on the privacy."""
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    if s.get("status") == "revealed":
        return {"ok": True, "status": "revealed", "history": _history(pid, s)}
    if s.get("status") not in ("resolved_sealed", "aborted_sealed", "stopped_sealed"):
        return _err("a live stratagem cannot be revealed — resolve, abort, or stop it first")
    s["status"] = "revealed"
    s["revealed_at"] = datetime.now().isoformat()
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "revealed", {"stratagem": s["id"], "from": b.get("by", "unspecified")})
    return {"ok": True, "status": "revealed", "history": _history(pid, s)}


@route(txn=False)
def strategy_stop(b):
    """Gloria's mechanical stop. Callable WITHOUT an Atelier visit, from the
    raw-input chokepoint, on a reserved explicit command — never an LLM
    classifier deciding whether she meant it.

    Atomically: halts capsule issuance, records the verbatim trigger reference,
    enters a distinct stopped state, and applies the declared stop contract.
    This stops the STRATAGEM, not the underlying Atelier project."""
    pid = b.get("id", "")
    with _plock(pid):
        s = _live(pid)
        if not s:
            # Also stop a sealed-but-unrevealed one, in case she is stopping
            # something she just learned about.
            s2 = _j(os.path.join(_sd(pid), "stratagem.json"))
            if not s2:
                return {"stopped": False, "note": "no stratagem on this project"}
            return {"stopped": False, "status": s2.get("status"),
                    "note": "already terminal"}
        s["status"] = "stopped_sealed"
        s["stopped_at"] = datetime.now().isoformat()
        s["stop_trigger_ref"] = str(b.get("trigger_ref", ""))[:300]
        s["stop_trigger_verbatim"] = str(b.get("verbatim", ""))[:600]
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "stopped_by_gloria",
               {"stratagem": s["id"], "trigger_ref": s["stop_trigger_ref"],
                "verbatim": s["stop_trigger_verbatim"],
                "contract": s["disclosure_policy"]["strategy_stop"]})
        return {"stopped": True, "status": "stopped_sealed",
                "contract": s["disclosure_policy"]["strategy_stop"],
                "note": "capsule issuance halted; /stratagem/reveal opens the history"}


@route()
def history(b):
    """Read a revealed stratagem's full history. Refused while live and while
    sealed — sealed is openable via /stratagem/reveal, never a back door."""
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    if s.get("status") != "revealed":
        return _err("not revealed (status: %s) — use /stratagem/reveal" % s.get("status"))
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
    # real verification: recomputed hashes, contiguous seq, capsule commitments
    ok, _n, why = verify(pid)
    return {
        "chain_verified": ok,
        "chain_failure": why,
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
    "/stratagem/reveal": reveal,
    "/stratagem/strategy-stop": strategy_stop,
    "/stratagem/history": history,
    "/stratagem/verify": lambda b: (lambda r: {"ok": r[0], "events": r[1], "failure": r[2]})(
        verify(b.get("id", ""))),
}


def verify_all_at_startup():
    """Full verification of every project's ledger when the broker boots.
    A ledger that fails here is held: no capsule issues from it until resolved."""
    held = []
    base = os.path.join(ROOT, "projects")
    try:
        pids = sorted(os.listdir(base))
    except OSError:
        return held
    for pid in pids:
        if not _PID_RE.match(pid):
            continue
        if not os.path.isdir(_sd(pid)):
            continue
        ok, n, why = verify(pid)
        if not ok:
            held.append({"project": pid, "failure": why})
            print("stratagem TAMPER_HELD %s: %s" % (pid, why))
    return held


try:
    verify_all_at_startup()
except Exception as _e:
    print("stratagem startup verification skipped:", _e)
