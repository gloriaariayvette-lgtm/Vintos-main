#!/usr/bin/env python3
"""prediction_ledger.py — predictions with identity, and a consume that cannot
delete something it never compared.

Sol reproduced the race. Relational and self predictions were singleton JSON
files shared by avatar, chat and voice. Avatar starts the comparison
asynchronously and writes the NEXT prediction immediately, so the comparison
finishes, calls os.remove() on the singleton, and deletes a prediction it never
looked at. The evidence is gone before it can be graded, and consecutive turns
on the same surface overwrite each other the same way.

The fix is identity, not ordering luck:

  - every prediction carries an immutable id bound to the turn and surface that
    produced it
  - a comparison consumes BY ID. If the file now holds a different prediction,
    the consume is refused and the newer prediction survives
  - the singleton is written under an exclusive lock, so a read-modify-write
    from two surfaces cannot interleave
  - nothing is ever silently lost: every create and every consume, refused or
    not, appends to the kind's history

Callers should still compare-then-create within a turn. This makes the failure
of that discipline visible and non-destructive rather than silent.
"""
import os, json, uuid, time
from datetime import datetime

try:
    import fcntl
except ImportError:                                   # non-POSIX; degrade, don't fail
    fcntl = None

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

# kind -> singleton file holding the CURRENT, unconsumed prediction
KINDS = {
    "relational": ".relational-prediction.json",
    "self": ".self-prediction.json",
    "gloria": "gloria-prediction.json",
}


def _path(kind):
    return os.path.join(MEMORY, KINDS.get(kind, ".%s-prediction.json" % kind))


def _hist(kind):
    return os.path.join(MEMORY, "%s-prediction-ledger.jsonl" % kind)


class _Lock:
    """Exclusive lock on a sibling file. The lock is never the data, so a
    crashed holder cannot corrupt the prediction itself."""
    def __init__(self, kind):
        self.p = _path(kind) + ".lock"
        self.f = None

    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(self.p), exist_ok=True)
            self.f = open(self.p, "a+")
            if fcntl:
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
        except Exception:
            self.f = None
        return self

    def __exit__(self, *a):
        try:
            if self.f:
                if fcntl:
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
                self.f.close()
        except Exception:
            pass
        return False


def _read(kind):
    try:
        with open(_path(kind)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _note(kind, event, rec):
    try:
        with open(_hist(kind), "a") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(), "event": event,
                                **{k: v for k, v in (rec or {}).items()
                                   if k in ("prediction_id", "turn_id", "surface",
                                            "reason", "outcome", "held_id")}}) + "\n")
    except Exception:
        pass


def new_id():
    return "p-" + uuid.uuid4().hex[:16]


def create(kind, payload, turn_id="", surface="", replace=True):
    """Write the current prediction for ``kind``. Returns the stored record.

    ``replace=False`` refuses to overwrite an unconsumed prediction, which is
    what a caller wants when it has NOT yet graded the previous one.
    """
    rec = dict(payload or {})
    rec["prediction_id"] = rec.get("prediction_id") or new_id()
    rec["turn_id"] = str(turn_id)[:80]
    rec["surface"] = str(surface)[:40]
    rec["created_at"] = datetime.now().isoformat()
    rec["created_ts"] = time.time()
    with _Lock(kind):
        cur = _read(kind)
        if cur and not replace:
            _note(kind, "create_refused", {**rec, "held_id": cur.get("prediction_id", ""),
                                           "reason": "an ungraded prediction is still open"})
            return None
        if cur:
            _note(kind, "superseded", {"prediction_id": cur.get("prediction_id", ""),
                                       "turn_id": cur.get("turn_id", ""),
                                       "surface": cur.get("surface", ""),
                                       "reason": "replaced before it was graded"})
        os.makedirs(os.path.dirname(_path(kind)), exist_ok=True)
        tmp = _path(kind) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(rec, f, indent=2)
        os.replace(tmp, _path(kind))                   # atomic; no torn read
    _note(kind, "created", rec)
    return rec


def current(kind):
    """The open prediction, or None."""
    with _Lock(kind):
        return _read(kind)


def consume(kind, prediction_id, outcome=None):
    """Retire the prediction with THIS id. Returns (ok, reason).

    A comparison that started before a newer prediction was written must not
    delete the newer one — that is the exact race Sol reproduced. If the id no
    longer matches, the consume is refused and the newer prediction stands.
    """
    if not prediction_id:
        _note(kind, "consume_refused", {"reason": "no prediction id"})
        return False, "a comparison without a prediction id cannot consume one"
    with _Lock(kind):
        cur = _read(kind)
        if not cur:
            _note(kind, "consume_refused", {"prediction_id": prediction_id,
                                            "reason": "nothing open"})
            return False, "no open prediction"
        if cur.get("prediction_id") != prediction_id:
            _note(kind, "consume_refused", {"prediction_id": prediction_id,
                                            "held_id": cur.get("prediction_id", ""),
                                            "reason": "a newer prediction is open"})
            return False, "a newer prediction is open; refusing to delete it"
        try:
            os.remove(_path(kind))
        except OSError:
            pass
    _note(kind, "consumed", {"prediction_id": prediction_id,
                             "turn_id": cur.get("turn_id", ""),
                             "surface": cur.get("surface", ""),
                             "outcome": str(outcome)[:80] if outcome is not None else ""})
    return True, None


def take(kind):
    """Read the open prediction for grading WITHOUT retiring it. The caller
    grades, then consumes by the id it read — never by whatever is there later.
    """
    cur = current(kind)
    return (cur, cur.get("prediction_id")) if cur else (None, None)
