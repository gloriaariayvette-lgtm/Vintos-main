#!/usr/bin/env python3
"""Private stratagem vault. A standing owner charter authorizes independent
initiative; project associations and lineage are metadata. The original per-record
JSON views, capsule commitments and hash-chained histories remain authoritative.
All transactions serialize across broker threads AND processes.
"""
import os, re, json, hashlib, uuid, functools
from datetime import datetime, timedelta
import threading
import fcntl
import hmac
from contextlib import contextmanager
from datetime import timezone

ROOT = "/home/atelier/atelier"
_LINEAGE_KEY = "/home/atelier/.lineage-key"

# broker.py is a ThreadingHTTPServer: two surfaces can request a capsule in the
# same instant. The chain is read-last-line-then-append, so without a lock a
# concurrent pair can share a seq or break prev — and a broken chain reads as
# tampering at reveal. One process, one lock, held across read+write.
_LOCK = threading.RLock()

TACTIC_VOCAB = {"SEED", "DEFER", "ALLOW", "NARROW", "VISIBLE_MOTIVE", "STABILIZE",
                "PIVOT", "PROBE", "RECONTEXTUALIZE", "ABORT", "REVEAL",
                # widened repertoire (Gloria wanted more), all inside the standing perimeter
                "MIRROR", "AMPLIFY", "CONTRAST", "ANCHOR", "FORESHADOW", "BRAID",
                "ESCALATE", "SOFTEN"}

# A self-originated root. A stratagem may only be born from one of these.
# Action exclusions, never an objective classification.
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
    """Delegates to THE shared validator in broker.py so the two stores cannot
    drift apart — fixing containment here while /visit/open stayed open was
    exactly that failure. The local copy is a fallback for isolated tests."""
    try:
        from broker import canonical_pid, BadProject as _BP
        try:
            return canonical_pid(pid, ROOT)
        except _BP as e:
            raise BadProject(str(e))
    except ImportError:
        pass
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
        with open(path) as handle:
            return json.load(handle)
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
        if os.path.exists(os.path.join(_sd(pid), "stratagem.json")):
            return False, 0, "stratagem state has no adoption ledger"
        return True, 0, None
    except (ValueError, OSError) as e:
        return False, 0, "ledger unreadable: %s" % str(e)[:80]
    if os.path.exists(os.path.join(_sd(pid), "stratagem.json")) and not any(e.get("type") == "adopted" for e in events):
        return False, len(events), "stratagem state has no adoption event"
    prev = "0" * 64
    for i, ev in enumerate(events):
        if ev.get("seq") != i:
            return False, i, "sequence discontinuity at index %d" % i
        if ev.get("prev") != prev:
            return False, i, "prev mismatch at seq %d" % i
        if _ev_hash(ev) != ev.get("hash"):
            return False, i, "hash mismatch at seq %d — event body was altered" % i
        prev = ev["hash"]
    # Capsule state is BOUND to the chain, not merely self-consistent: every
    # capsule record must sit on a capsule_issued event at its seq carrying the
    # same commitment, and every capsule_issued event must have its record.
    # Before this, a capsule could be dropped from, or slipped into, the
    # capsule log with its own hash intact and verification never noticed.
    issued = {ev["seq"]: (ev.get("data") or {}).get("capsule_sha256")
              for ev in events if ev.get("type") == "capsule_issued"}
    cpath = os.path.join(_sd(pid), "capsules.jsonl")
    seen = set()
    try:
        for line in open(cpath):
            if not line.strip():
                continue
            rec = json.loads(line)
            got = hashlib.sha256(json.dumps(rec["capsule"], sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
            if got != rec.get("capsule_sha256"):
                return False, len(events), "capsule commitment mismatch at seq %s" % rec.get("seq")
            if issued.get(rec.get("seq")) != got:
                return False, len(events), "capsule at seq %s has no matching capsule_issued event" % rec.get("seq")
            seen.add(rec.get("seq"))
    except FileNotFoundError:
        pass
    except (ValueError, OSError, KeyError) as e:
        return False, len(events), "capsule log unreadable: %s" % str(e)[:80]
    missing = sorted(set(issued) - seen)
    if missing:
        return False, len(events), "capsule_issued at seq %s has no capsule record" % missing[0]
    # The project's own event chain (views included) is part of the same
    # integrity: a LOOK edited out of the room's history holds the stratagem too.
    try:
        from broker import verify_events_at
        pok, _pn, pwhy = verify_events_at(_p(pid))
        if not pok:
            return False, len(events), "project events: %s" % pwhy
    except ImportError:
        pass
    record = _j(os.path.join(_sd(pid), "stratagem.json"), {})
    association = record.get("project")
    if association and association != pid:
        try:
            from broker import verify_events_at
            ok, _, why = verify_events_at(_p(association))
            if not ok:
                return False, len(events), "associated project events: " + str(why)
        except ImportError:
            pass
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
    if os.path.exists(os.path.join(_sd(pid), "owner-stopped")):
        return None
    return s if s and s.get("status") in ("active", "held_review") else None


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


@contextmanager
def transaction():
    # flock is process-wide coordination; RLock handles threads and nested calls.
    with _LOCK:
        depth = getattr(_TX_LOCAL, "depth", 0)
        if depth:
            _TX_LOCAL.depth += 1
            try:
                yield
            finally:
                _TX_LOCAL.depth -= 1
            return
        os.makedirs(ROOT, exist_ok=True)
        with open(os.path.join(ROOT, ".stratagem.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            _TX_LOCAL.depth = 1
            try:
                yield
            finally:
                _TX_LOCAL.depth = 0
                fcntl.flock(lock, fcntl.LOCK_UN)


_TX_LOCAL = threading.local()


def _now():
    return datetime.now(timezone.utc)


def _date(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def charter():
    return _j(os.path.join(ROOT, "stratagem-charter.json"), {})


def _owner(b):
    # Separate credential from visit capabilities and model-generated bodies.
    try:
        with open(os.path.join(ROOT, ".stratagem-owner-key")) as handle:
            key = handle.read().strip()
    except OSError:
        return False
    token = (b or {}).get("owner_token")
    return bool(key and isinstance(token, str) and hmac.compare_digest(key, token))


def charter_update(b):
    with transaction():
        if not _owner(b):
            return _err("owner authorization required")
        old = charter()
        record = {"version": 1, "revision": old.get("revision", 0) + 1,
                  "active": b.get("active", old.get("active", False)) is True,
                  "authorized_by": "owner", "updated_at": _now().isoformat(),
                  "max_active": 3, "max_days": 14,
                  "excluded_actions": sorted(PERIMETER_EXCLUDED | set(b.get("excluded_actions", old.get("excluded_actions", [])) or [])),
                  "boundaries": str(b.get("boundaries", old.get("boundaries", "")))[:4000]}
        _wa(os.path.join(ROOT, "stratagem-charter.json"), record)
        # Revisions are immutable audit records; no objectives enter this log.
        with open(os.path.join(ROOT, "stratagem-charter-history.jsonl"), "a") as f:
            f.write(json.dumps(record) + "\n"); f.flush(); os.fsync(f.fileno())
        return {"ok": True, "charter": record}


def _authorized(b=None):
    c = charter()
    if not c.get("active") or c.get("authorized_by") != "owner":
        return _err("standing charter is inactive")
    # Old perimeter_scope is never required or used as an eligibility taxonomy.
    actions = set((b or {}).get("action_impacts") or [])
    forbidden = actions & (PERIMETER_EXCLUDED | set(c.get("excluded_actions") or []))
    if forbidden:
        return _err("excluded action: " + ", ".join(sorted(forbidden)))
    return None


def _records():
    base = os.path.join(ROOT, "projects")
    if not os.path.isdir(base):
        return []
    return [pid for pid in sorted(os.listdir(base)) if _PID_RE.fullmatch(pid)
            and os.path.isfile(os.path.join(_sd(pid), "stratagem.json"))]


def _expire(pid):
    path = os.path.join(_sd(pid), "stratagem.json")
    s = _j(path)
    if not s or s.get("status") not in ("active", "held_review"):
        return s
    # Legacy adoption time is the immutable anchor, NOT its last renewed lease.
    activated = s.get("activated_at") or s.get("born")
    try:
        hard = _date(activated) + timedelta(days=14)
        deadline = min(hard, _date(s.get("expires_at") or s["lease_expires"]))
    except (ValueError, TypeError, KeyError):
        raise Corrupt("stratagem has no valid activation/deadline")
    changed = not s.get("activated_at") or not s.get("expires_at")
    s["activated_at"] = activated
    s["expires_at"] = deadline.isoformat()
    s["lease_expires"] = s["expires_at"]
    if _now() >= deadline:
        s["status"] = "expired_sealed"
        s["expired_at"] = _now().isoformat()
        _wa(path, s)
        _chain(pid, "expired", {"stratagem": s["id"], "expires_at": s["expires_at"]})
    elif changed:
        _wa(path, s)
        _chain(pid, "lifecycle_migrated", {"stratagem": s["id"], "expires_at": s["expires_at"]})
    return s


def active_records():
    result = []
    for pid in _records():
        s = _expire(pid)
        if s.get("status") in ("active", "held_review"):
            result.append(pid)
    return result


def inventory(b):
    with transaction():
        pids = active_records()
        return {"active": bool(pids), "count": len(pids), "available": max(0, 3-len(pids)),
                "authorized": not bool(_authorized()),
                "charter": charter(), "stratagems": [state({"id": p}) for p in pids]}


def route(verify_first=True, txn=True):
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(b):
            b = dict(b or {})
            try:
                with transaction():
                    pid = b.get("id", "")
                    origin = b.get("originating_record")
                    if origin:
                        _p(origin)
                        parent = _expire(origin)
                        if not parent or parent.get("status") != "active" or not _live(origin):
                            return _err("originating stratagem is no longer active")
                    if fn.__name__ == "adopt":
                        if _authorized(b):
                            return _authorized(b)
                        if len(active_records()) >= 3:
                            return _err("three active stratagems already exist")
                        # Every new undertaking owns a fresh private record directory.
                        # A supplied project remains an association, never its identity.
                        b["associated_project"] = pid or b.get("associated_project")
                        if b["associated_project"]:
                            _p(b["associated_project"])
                        if not pid or os.path.exists(os.path.join(_sd(pid), "stratagem.json")):
                            pid = uuid.uuid4().hex[:12]
                            while os.path.exists(_p(pid)):
                                pid = uuid.uuid4().hex[:12]
                        b["id"] = pid
                        os.makedirs(_p(pid), exist_ok=True)
                    _p(pid)
                    if verify_first:
                        held = _require_intact(pid)
                        if held:
                            return held
                    if fn.__name__ not in {"strategy_stop", "reveal", "history"}:
                        _expire(pid)
                    if fn.__name__ in {"capsule", "advance", "lease", "belief", "info",
                                       "assess", "misconception", "leverage", "resolve"}:
                        denied = _authorized(b)
                        if denied:
                            return denied
                    return fn(b)
            except Corrupt as e:
                return _err("CORRUPT_STATE: %s" % e)
            except (BadProject, ValueError, TypeError, KeyError) as e:
                return _err(str(e))
        return wrapped
    return deco


# ---------------------------------------------------------------------------
# BIRTH
# ---------------------------------------------------------------------------

@route()
def adopt(b):
    """Adopt under the standing charter; retain optional associations and lineage."""
    pid = b.get("id", "")
    if not os.path.isdir(_p(pid)):
        return _err("no such project")
    prov = b.get("provenance") or {}
    if not str(b.get("objective", "")).strip():
        return _err("objective required")
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

    denied = _authorized(b)
    if denied:
        return denied
    for step in steps:
        denied = _authorized(step)
        if denied:
            return denied
    policy = dict(DEFAULT_POLICY)
    for k, v in (b.get("disclosure_policy") or {}).items():
        if k in policy and str(v).strip():
            policy[k] = str(v)[:300]
    policy["strategy_stop"] = DEFAULT_POLICY["strategy_stop"]   # not removable

    lease_days = int(b.get("lease_days", 14))
    if not 1 <= lease_days <= 14:
        return _err("duration must be 1 to 14 calendar days")
    activated = _now()
    sid = "sg-" + uuid.uuid4().hex
    s = {
        "id": sid,
        "project": b.get("associated_project"),
        "storage_id": pid,
        "born": activated.isoformat(),
        "created_at": activated.isoformat(),
        "activated_at": activated.isoformat(),
        "expires_at": (activated + timedelta(days=lease_days)).isoformat(),
        "charter_revision": charter()["revision"],
        "objective": str(b["objective"])[:800],
        "provenance": dict(prov),
        "sequencing_advantage": str(b["sequencing_advantage"])[:400],
        "action_impacts": list(b.get("action_impacts") or []),
        "tactics": [{"tactic": s2["tactic"],
                     "turn_objective": str(s2["turn_objective"])[:300],
                     "reveal_if": [str(x)[:200] for x in (s2.get("reveal_if") or [])][:5],
                     "abort_if": [str(x)[:200] for x in (s2.get("abort_if") or [])][:5]}
                    for s2 in steps][:20],
        "step": 0,
        "lease_days": lease_days,
        "lease_expires": (activated + timedelta(days=lease_days)).isoformat(),
        "disclosure_policy": policy,
        "status": "active",
    }
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "adopted", {"stratagem": sid, "provenance": prov,
                            "charter_revision": s["charter_revision"],
                            "expires_at": s["expires_at"], "steps": len(s["tactics"])})
    return {"stratagem_id": sid, "id": pid, "lease_expires": s["lease_expires"],
            "expires_at": s["expires_at"], "steps": len(s["tactics"])}


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
    "MIRROR": "reflect an observed move back truthfully",
    "AMPLIFY": "heighten a true fragment already present",
    "CONTRAST": "place two true things beside each other",
    "ANCHOR": "establish a true reference for a later move",
    "FORESHADOW": "offer a true hint without disclosing the full objective",
    "BRAID": "weave existing threads toward a later connection",
    "ESCALATE": "increase emphasis within the charter's action boundaries",
    "SOFTEN": "lower intensity to open space",

}


SURFACES_ALLOWED = {"chat", "phone", "voice", "vintos-eve", "avatar", "reelroom"}


def _existing_capsule(pid, sid, turn_id, surface):
    """A capsule already issued for this exact (stratagem, turn, surface), or None.
    Helper, not a route."""
    try:
        for line in open(os.path.join(_sd(pid), "capsules.jsonl")):
            if not line.strip():
                continue
            rec = json.loads(line)
            c = rec.get("capsule", {})
            if (c.get("stratagem_id") == sid and c.get("turn_id") == turn_id
                    ):
                return rec
    except FileNotFoundError:
        pass
    except (ValueError, OSError):
        pass
    return None


# A turn does not have one honest completion rank. Generation, effects,
# post-writers and transport can each succeed, fail, or remain unknowable
# independently.  These axes are authoritative; the old scalar vocabulary is
# accepted below only as a compatibility adapter for surfaces being migrated.
_AXIS_STATES = {
    "generation": {"not_started", "created", "failed", "HELD", "unknown"},
    "effects": {"not_started", "none", "started", "completed", "failed", "HELD", "unknown"},
    "post_writers": {"not_started", "dispatched", "completed", "failed", "HELD", "unknown"},
    "transport": {"not_started", "handed_to_framework", "acknowledged", "declined", "failed", "HELD", "unknown"},
}
_AXIS_TERMINAL = {
    "generation": {"created", "failed", "HELD", "unknown"},
    "effects": {"none", "completed", "failed", "HELD", "unknown"},
    "post_writers": {"completed", "failed", "HELD", "unknown"},
    "transport": {"acknowledged", "declined", "failed", "HELD", "unknown"},
}
_AXIS_ORDER = {
    "generation": {"not_started": 0, "created": 1, "failed": 1, "HELD": 1, "unknown": 1},
    "effects": {"not_started": 0, "started": 1, "none": 2, "completed": 2,
                "failed": 2, "HELD": 2, "unknown": 2},
    "post_writers": {"not_started": 0, "dispatched": 1, "completed": 2,
                     "failed": 2, "HELD": 2, "unknown": 2},
    "transport": {"not_started": 0, "handed_to_framework": 1, "acknowledged": 2,
                  "declined": 2, "failed": 2, "HELD": 2, "unknown": 2},
}
_LEGACY_STATES = {"issued", "admitted_to_prompt", "response_created",
                  "effects_completed", "postwriters_dispatched", "transport_unknown",
                  "completed", "generation_failed", "capsule_unrealized"}
_LEGACY_AXES = {
    "response_created": {"generation": "created"},
    "effects_completed": {"effects": "completed"},
    "postwriters_dispatched": {"post_writers": "dispatched"},
    "transport_unknown": {"transport": "unknown"},
    "generation_failed": {"generation": "failed", "effects": "HELD",
                          "post_writers": "HELD", "transport": "HELD"},
    "capsule_unrealized": {"generation": "failed", "effects": "HELD",
                           "post_writers": "HELD", "transport": "HELD"},
    # Historical callers used completed without evidence for the latter axes.
    # Preserve that uncertainty instead of manufacturing completion.
    "completed": {"generation": "created", "effects": "completed",
                  "post_writers": "unknown", "transport": "unknown"},
}


@route()
def disposition(b):
    """Append independent lifecycle facts for an issued capsule.

    Preferred body: ``axes={axis: state}``.  A legacy ``state`` is translated
    explicitly and retained as an audit event; it is never the authoritative
    lifecycle snapshot.
    """
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    state = str(b.get("state", "")).strip()
    axes = b.get("axes")
    if axes is None:
        if state not in _LEGACY_STATES:
            return _err("unknown disposition state: %s" % state)
        axes = _LEGACY_AXES.get(state, {})
    if not isinstance(axes, dict) or not axes:
        # issued/admitted are admission-history events, not lifecycle axes.
        if state not in ("issued", "admitted_to_prompt"):
            return _err("axes must be a non-empty object")
    for axis, value in axes.items():
        if axis not in _AXIS_STATES:
            return _err("unknown lifecycle axis: %s" % axis)
        if value not in _AXIS_STATES[axis]:
            return _err("unknown %s state: %s" % (axis, value))
    turn_id = str(b.get("turn_id", ""))[:80]
    sha = str(b.get("capsule_sha256", ""))[:64]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return _err("capsule_sha256 must be the exact 64-character commitment")

    # the EXACT (turn_id, capsule_sha256) must match a capsule this stratagem
    # issued — for every state including 'issued', since issuance writes the
    # capsule record before the coordinator ever reports a disposition.
    if not _capsule_issued_for(pid, turn_id, sha):
        return _err("no issued capsule for (turn %s, sha %s) — disposition refused"
                    % (turn_id, sha[:12]))

    current = _lifecycle_state(pid, turn_id, sha)
    legacy_terminal = _legacy_terminal(pid, turn_id, sha)
    if state and legacy_terminal:
        return {"ok": True, "idempotent": True, "state": state,
                "axes": current, "note": "legacy caller already terminal (%s)" % legacy_terminal}
    patch = {}
    for axis, value in axes.items():
        previous = current.get(axis, "not_started")
        if previous == value:
            continue
        if previous in _AXIS_TERMINAL[axis]:
            continue
        if _AXIS_ORDER[axis][value] < _AXIS_ORDER[axis][previous]:
            continue
        patch[axis] = value
    # Preserve issued/admitted history exactly once for migration/audit.
    if state in ("issued", "admitted_to_prompt"):
        if _legacy_seen(pid, turn_id, sha, state):
            return {"ok": True, "idempotent": True, "state": state,
                    "axes": current}
        ev = _chain(pid, "capsule_disposition",
                    {"stratagem": s["id"], "turn_id": turn_id,
                     "capsule_sha256": sha, "state": state,
                     "reason_class": str(b.get("reason_class", ""))[:60]})
        return {"ok": True, "seq": ev["seq"], "state": state, "axes": current}
    if not patch:
        return {"ok": True, "idempotent": True, "state": state or "axes",
                "axes": current, "note": "no axis could advance"}
    latest = dict(current); latest.update(patch)
    ev = _chain(pid, "capsule_lifecycle",
                {"stratagem": s["id"], "turn_id": turn_id, "capsule_sha256": sha,
                 "patch": patch, "axes": latest,
                 "reason_class": str(b.get("reason_class", ""))[:60],
                 "legacy_state": state or None})
    # Keep a compatibility audit event without using it for ordering.
    if state:
        _chain(pid, "capsule_disposition",
               {"stratagem": s["id"], "turn_id": turn_id, "capsule_sha256": sha,
                "state": state, "reason_class": str(b.get("reason_class", ""))[:60],
                "translated_to_axes": patch})
    return {"ok": True, "seq": ev["seq"], "state": state or "axes",
            "patch": patch, "axes": latest}


def _capsule_issued_for(pid, turn_id, sha):
    """A capsule was issued for this exact, non-empty (turn_id, sha)."""
    if not turn_id or not sha:
        return False
    try:
        for line in open(os.path.join(_sd(pid), "capsules.jsonl")):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("capsule", {}).get("turn_id") != turn_id:
                continue
            if rec.get("capsule_sha256") == sha:
                return True
    except (FileNotFoundError, ValueError, OSError):
        pass
    return False


def _lifecycle_state(pid, turn_id, sha):
    """Reconstruct the latest independent lifecycle axes from the event chain."""
    out = {axis: "not_started" for axis in _AXIS_STATES}
    try:
        for line in open(os.path.join(_sd(pid), "events.jsonl")):
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("type") != "capsule_lifecycle":
                continue
            d = e.get("data", {})
            if d.get("turn_id") == turn_id and (not sha or d.get("capsule_sha256") == sha):
                for axis, value in (d.get("patch") or {}).items():
                    if axis in _AXIS_STATES and value in _AXIS_STATES[axis]:
                        out[axis] = value
    except (FileNotFoundError, ValueError, OSError):
        pass
    return out


def _legacy_seen(pid, turn_id, sha, state):
    try:
        for line in open(os.path.join(_sd(pid), "events.jsonl")):
            e = json.loads(line)
            d = e.get("data", {})
            if (e.get("type") == "capsule_disposition" and d.get("turn_id") == turn_id
                    and d.get("capsule_sha256") == sha and d.get("state") == state):
                return True
    except (FileNotFoundError, ValueError, OSError):
        pass
    return False


def _legacy_terminal(pid, turn_id, sha):
    for state in ("completed", "generation_failed", "capsule_unrealized"):
        if _legacy_seen(pid, turn_id, sha, state):
            return state
    return None


@route()
def writer_event(b):
    """Record one asynchronous writer's own result; never infer aggregation."""
    pid = b.get("id", "")
    turn_id = str(b.get("turn_id", ""))[:80]
    sha = str(b.get("capsule_sha256", ""))[:64]
    writer = str(b.get("writer", ""))[:80]
    status = str(b.get("status", ""))
    if not writer:
        return _err("writer required")
    if status not in {"started", "completed", "failed", "HELD", "unknown"}:
        return _err("unknown writer status: %s" % status)
    if not re.fullmatch(r"[0-9a-f]{64}", sha) or not _capsule_issued_for(pid, turn_id, sha):
        return _err("no issued capsule for exact writer-event commitment")
    ev = _chain(pid, "capsule_writer_event",
                {"turn_id": turn_id, "capsule_sha256": sha, "writer": writer,
                 "status": status, "detail": str(b.get("detail", ""))[:300]})
    return {"ok": True, "seq": ev["seq"], "writer": writer, "status": status}


@route()
def capsule(b):
    """Issue the sealed capsule for ONE identified turn on ONE surface.

    turn_id and surface are required and are bound into the committed envelope
    with a nonce and issue time, so reissuing the same tactic no longer produces
    an identical hash (which would have leaked cadence and repetition to anyone
    reading the public commitments).

    A deadline expires terminally without revealing. Exhausted steps hold, and
    ledger corruption refuses issuance. Owner reveal remains separately available."""
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
                "note": "held for review; advance, hold, cancel, or complete before its fixed deadline"}
    # IDEMPOTENT on (stratagem_id, turn_id, surface). If the event was written
    # but the HTTP response was lost, a retry with the same turn_id returns the
    # ORIGINAL capsule — never a second issuance, which would double-count the
    # turn and leak a false cadence.
    prior = _existing_capsule(pid, s["id"], turn_id, surface)
    if prior and prior["capsule"].get("surface") != surface:
        return {"active": True, "duplicate_event": True}
    if prior:
        return {"active": True, "capsule": prior["capsule"], "idempotent": True,
                "commitment": {"capsule_sha256": prior["capsule_sha256"],
                               "stratagem_id": s["id"], "stratagem_project": pid,
                               "seq": prior["seq"], "turn_id": turn_id}}

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
                           "stratagem_project": pid,
                           "seq": ev["seq"], "turn_id": turn_id}}


@route()
def advance(b):
    """Move this stratagem to its next tactic from any charter-authorized pathway."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    obs = str(b.get("observation", ""))[:400]
    s["step"] = min(s.get("step", 0) + 1, len(s["tactics"]))
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "advanced", {"stratagem": s["id"], "to_step": s["step"], "observation": obs})
    return {"ok": True, "step": s["step"], "of": len(s["tactics"])}


@route()
def lease(b):
    """Pause, resume within the fixed deadline, or cancel. Renewal is refused."""
    pid, action = b.get("id", ""), b.get("action", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    if action == "renew":
        return _err("activation and expiration cannot be renewed")
    if action == "resume":
        s["status"] = "active"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "resumed", {"stratagem": s["id"], "expires_at": s["expires_at"]})
        return {"ok": True}
    if action == "hold":
        s["status"] = "held_review"
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "lease_held", {"stratagem": s["id"]})
        return {"ok": True, "status": "held_review"}
    if action == "abort":
        s["status"] = "aborted_sealed"
        s["aborted_at"] = datetime.now().isoformat()
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "aborted_sealed", {"stratagem": s["id"], "note": str(b.get("note", ""))[:300]})
        return {"ok": True, "status": "aborted_sealed"}
    return _err("action must be resume, hold, or abort; deadlines cannot be renewed")


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
            "lease_expires": s["lease_expires"], "id": pid}


# Every terminal path lands in one of these, and every one of them can still
# be revealed later. The old code stored a boolean `revealed`, and resolving
# with reveal=False made the history permanently unreachable — an irreversible
# privacy trap, which is the opposite of privacy with an expiration date.
TERMINAL = {"resolved_sealed", "aborted_sealed", "stopped_sealed", "expired_sealed", "revealed"}


@route()
def resolve(b):
    """Resolve the stratagem. Reveal opens the whole history chronologically
    with the chain verified; sealing defers that, and a sealed stratagem can
    always be opened later via /stratagem/reveal. Nothing here is permanent."""
    pid = b.get("id", "")
    s = _live(pid)
    if not s:
        return _err("no stratagem")
    outcome = str(b.get("outcome", "")).strip()
    if not outcome:
        return _err("an authored outcome is required")
    reveal = bool(b.get("reveal", False)) and _owner(b)
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


@route(verify_first=False)
def reveal(b):
    """Explicit owner inspection opens live or terminal history, including held ledgers."""
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    if not _owner(b):
        return _err("explicit owner reveal authorization required")
    if s.get("status") == "revealed":
        return {"ok": True, "status": "revealed", "history": _history(pid, s)}
    s["status"] = "revealed"
    s["revealed_at"] = datetime.now().isoformat()
    _wa(os.path.join(_sd(pid), "stratagem.json"), s)
    _chain(pid, "revealed", {"stratagem": s["id"], "from": b.get("by", "unspecified")})
    return {"ok": True, "status": "revealed", "history": _history(pid, s)}


@route(txn=False, verify_first=False)
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
        # A stop is the ONE transaction that must never be refused. Every other
        # route verifies the ledger head first and returns TAMPER_HELD, and
        # strategy_stop inherited that — so a corrupted ledger, which is
        # exactly when she would most want to stop him, was the state in which
        # she could not. It runs regardless now, and records what it found.
        _ok, _n, _why = verify(pid)
        if not _ok:
            s["stopped_over_held_ledger"] = str(_why)[:160]
        _wa(os.path.join(_sd(pid), "stratagem.json"), s)
        _chain(pid, "stopped_by_gloria",
               {"stratagem": s["id"], "trigger_ref": s["stop_trigger_ref"],
                "verbatim": s["stop_trigger_verbatim"],
                "contract": s["disclosure_policy"]["strategy_stop"]})
        out = {"stopped": True, "status": "stopped_sealed",
               "contract": s["disclosure_policy"]["strategy_stop"],
               "note": "capsule issuance halted; /stratagem/reveal opens the history"}
        if s.get("stopped_over_held_ledger"):
            out["ledger_held"] = s["stopped_over_held_ledger"]
            out["note"] += " — NOTE: the ledger did not verify; the stop stands anyway"
        return out


@route()
def history(b):
    """Read a revealed stratagem's full history. Refused while live and while
    sealed — sealed is openable via /stratagem/reveal, never a back door."""
    pid = b.get("id", "")
    s = _j(os.path.join(_sd(pid), "stratagem.json"))
    if not s:
        return _err("no stratagem on this project")
    if not _owner(b):
        return _err("owner authorization required")
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
        "action_impacts": s.get("action_impacts", []),
        "legacy_perimeter_scope": s.get("perimeter_scope", []),
        "planned_tactics": s["tactics"],
        "disclosure_policy": s["disclosure_policy"],
        "outcome": s.get("outcome"),
        "chain_intact": ok,
        "events": evs,
        "capsules": caps,
        "information_positions": _j(os.path.join(_sd(pid), "info.json"), {"items": []})["items"],
        "misconceptions": _j(os.path.join(_sd(pid), "misconceptions.json"), {"items": []})["items"],
    }


def capsules(b):
    """One tactic per turn, fair across active stratagems; no shared tactical state.
    Event identity is global across routes, so a forwarded/retried event cannot
    select a second stratagem. Commitments stay compatible with all writers.
    """
    with transaction():
        if _authorized():
            return _authorized()
        active = active_records()
        ranked = []
        for pid in _records():
            s = _j(os.path.join(_sd(pid), "stratagem.json"))
            prior = _existing_capsule(pid, s["id"], str(b.get("turn_id", "")), "")
            if prior:
                return {"capsules": [], "duplicate_event": True}
            if pid in active:
                last = ""
                try:
                    for line in open(os.path.join(_sd(pid), "capsules.jsonl")):
                        last = json.loads(line)["ts"]
                except FileNotFoundError:
                    pass
                ranked.append((last, pid))
        for _, pid in sorted(ranked):
            r = capsule({**b, "id": pid})
            if r.get("capsule"):
                return {"capsules": [r]}
        return {"capsules": []}


def stop_all(b):
    with transaction():
        # stop is deliberately never gated by charter, lineage, or visits.
        pids = [b["id"]] if b.get("id") else _records()
        results = []
        for pid in pids:
            # Persist an unconditional tombstone before attempting audit/state parsing.
            directory = _sd(pid)
            os.makedirs(directory, exist_ok=True)
            result = strategy_stop({**b, "id": pid})
            with open(os.path.join(directory, "owner-stopped"), "w") as f:
                f.write(_now().isoformat()); f.flush(); os.fsync(f.fileno())
            results.append(result)
        return {"ok": True, "results": results}



def owner_reveal(b):
    with transaction():
        if not _owner(b):
            return _err("owner authorization required")
        pids = [b["id"]] if b.get("id") else _records()
        return {"results": [{"id": p, **reveal({**b, "id": p})} for p in pids]}


def eligible(b):
    with transaction():
        if _authorized() or _require_intact(b.get("id", "")):
            return {"eligible": False}
        s = _expire(b.get("id", ""))
        return {"eligible": bool(s and s.get("status") == "active"
                                 and not os.path.exists(os.path.join(_sd(b["id"]), "owner-stopped")))}


ROUTES = {
    "/stratagem/charter": lambda b: {"charter": charter()},
    "/stratagem/charter/update": charter_update,
    "/stratagem/inventory": inventory,
    "/stratagem/capsules": capsules,
    "/stratagem/stop": stop_all,
    "/stratagem/owner-reveal": owner_reveal,
    "/stratagem/eligible": eligible,
    "/stratagem/adopt": adopt,
    "/stratagem/capsule": capsule,
    "/stratagem/disposition": disposition,
    "/stratagem/writer-event": writer_event,
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
    with transaction():
        active_records()
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Owner-only standing charter administration")
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args()
    ROOT = args.root
    with transaction():
        keypath = os.path.join(ROOT, ".stratagem-owner-key")
        if not os.path.exists(keypath):
            fd = os.open(keypath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(uuid.uuid4().hex + uuid.uuid4().hex)
        token = open(keypath).read().strip()
        result = charter_update({"owner_token": token, "active": args.action == "grant"})
        print(json.dumps(result))
