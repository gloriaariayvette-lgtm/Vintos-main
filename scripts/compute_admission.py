#!/usr/bin/env python3
"""compute_admission.py - bounded admission for the machine's one GPU and the model calls.

Two classes (review 161):
  foreground  a live turn with Gloria: chat, avatar, a voice call, a Kokoro line for a call.
              It NEVER waits. It touches a marker so background work yields to it.
  background  the cron organs: dreams, drift, mirrors, journals, music renders, reviews.
              It waits (bounded) while foreground is live or another background job holds the
              slot, then runs. Nothing here changes what a job does with its files (review 173).

    from compute_admission import admit, touch_foreground, record
    with admit("background", organ="dream-music"):
        ...the model call...

Every admitted call records {organ, class, provider, model, stage, latency_ms, rss_mb, usage}
to memory/compute-ledger.jsonl (review 171). Measurements only; no line here says anything
about quality. Also used by the shell cron scripts:

    compute_admission.py run background --organ tension-field -- python3 tension_field.py
"""
import sys as _guard_sys
from pathlib import Path as _GuardPath
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parent))
import os, sys, json, time, fcntl, contextlib, resource, subprocess, uuid
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
FG_MARKERS = (".voice-live", ".foreground-live")
FG_FRESH_S = float(os.environ.get("VINTOS_FG_FRESH_S", "20"))     # a foreground marker younger than this means "live"
BG_WAIT_S = float(os.environ.get("VINTOS_BG_WAIT_S", "900"))      # a background job waits at most this long
POLL_S = 2.0
LEDGER = None   # resolved lazily so tests can redirect MEMORY

def _p(name):
    return os.path.join(MEMORY, name)

def _ledger():
    return LEDGER or _p("compute-ledger.jsonl")

def touch_foreground():
    """A live turn is happening (called by the chat/avatar/voice doors). Cheap: one utime."""
    try:
        os.makedirs(MEMORY, exist_ok=True)
        p = _p(".foreground-live")
        with open(p, "a"):
            pass
        os.utime(p, None)
        return True
    except Exception:
        return False

def foreground_live(now=None):
    now = now if now is not None else time.time()
    for m in FG_MARKERS:
        try:
            if now - os.path.getmtime(_p(m)) < FG_FRESH_S:
                return True
        except OSError:
            continue
    return False

def rss_mb():
    try:
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(kb / 1024.0, 1)
    except Exception:
        return None

def record(organ, cls="background", provider="", model="", stage="", latency_ms=None, usage=None, extra=None, strict=False):
    """One measured line. Never a quality claim."""
    row = {"at": datetime.now().isoformat(), "organ": str(organ)[:60], "class": cls,
           "provider": provider or "", "model": model or "", "stage": stage or "",
           "latency_ms": (int(latency_ms) if latency_ms is not None else None),
           "rss_mb": rss_mb(), "usage": usage if isinstance(usage, dict) else None}
    from request_trace import current as _request_trace
    row["request_id"] = _request_trace.get()
    if extra:
        row.update({k: v for k, v in extra.items() if k not in row})
    try:
        os.makedirs(os.path.dirname(_ledger()), exist_ok=True)
        with open(_ledger(), "a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
            if strict: f.flush(); os.fsync(f.fileno())
    except Exception:
        if strict: raise
    return row

class Admission:
    def __init__(self, cls, organ="", wait_s=None, provider="", model="", stage=""):
        if cls not in ("foreground", "background"):
            raise ValueError("class must be foreground or background")
        self.cls, self.organ, self.wait_s = cls, organ, (BG_WAIT_S if wait_s is None else wait_s)
        self.provider, self.model, self.stage = provider, model, stage
        self.waited = 0.0; self.t0 = None; self._lock = None; self.admitted = False; self.usage = None

    def __enter__(self):
        os.makedirs(MEMORY, exist_ok=True)
        if self.cls == "foreground":
            touch_foreground(); self.admitted = True; self.t0 = time.time(); return self
        start = time.time()
        self._lock = open(_p(".compute.lock"), "a+")
        while True:
            if not foreground_live():
                try:
                    fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.admitted = True; break
                except OSError:
                    pass
            self.waited = time.time() - start
            if self.waited >= self.wait_s:
                raise TimeoutError("background admission: waited %.0fs (foreground live or slot held)" % self.waited)
            time.sleep(POLL_S)
        self.t0 = time.time(); return self

    def __exit__(self, et, ev, tb):
        ms = int((time.time() - self.t0) * 1000) if self.t0 else None
        record(self.organ or "?", self.cls, self.provider, self.model, self.stage, ms, self.usage,
               extra={"waited_s": round(self.waited, 1), "error": (ev.__class__.__name__ if ev else "")})
        if self._lock:
            try: fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
            except OSError: pass
            self._lock.close(); self._lock = None
        return False

PAID_PER_DAY = int(os.environ.get("VINTOS_PAID_PER_DAY", "400"))

def _paid_rows():
    try:
        with open(_ledger()) as stream:
            for line in stream:
                try: row = json.loads(line)
                except (ValueError, TypeError): continue
                if isinstance(row, dict) and row.get("class") == "paid": yield row
    except FileNotFoundError:
        return


def paid_today(provider=None):
    """Count reservations; only a matching, single-use receipt can cancel one.

    Historical releases without IDs are ambiguous and do not reduce the cap.
    A release on a later day belongs to its original reservation's day.
    """
    day = datetime.now().strftime("%Y-%m-%d")
    reservations, released = {}, set()
    legacy = 0
    for row in _paid_rows():
        rid = row.get("reservation_id")
        if row.get("stage") == "reserved":
            if rid: reservations.setdefault(rid, row)
            elif str(row.get("at", "")).startswith(day) and (provider is None or row.get("provider") == provider):
                legacy += max(0, int(row.get("units", 1)))
        elif row.get("stage") == "released" and rid in reservations:
            original = reservations[rid]
            if (row.get("provider"), row.get("organ"), row.get("model"), row.get("units")) == (original.get("provider"), original.get("organ"), original.get("model"), original.get("units")):
                released.add(rid)
    return legacy + sum(max(0, int(row.get("units", 1))) for rid, row in reservations.items()
        if rid not in released and str(row.get("at", "")).startswith(day)
        and (provider is None or row.get("provider") == provider))

def reserve_paid(organ, provider, model="", units=1, cap=None, reservation_id=None):
    from store_guard import transaction
    if type(units) is not int or units < 1: return False,"positive integer reservation required"
    try:
        with transaction(_ledger()):
            return _reserve_paid(organ,provider,model,units,cap,reservation_id)
    except (OSError, ValueError) as exc:
        return False, "reservation could not be persisted: " + str(exc)


def _reserve_paid(organ, provider, model="", units=1, cap=None, reservation_id=None):
    """review 79: before paid or remote work, a reservation against the day's cap. (ok, why). A refused
    reservation is recorded (stage=refused) and the caller holds; a granted one is the ledger row the
    later usage line joins to. Foreground callers still never wait here - the cap is the only refusal."""
    reservation_id = reservation_id or uuid.uuid4().hex
    if any(row.get("reservation_id") == reservation_id for row in _paid_rows()):
        return False, "reservation ID already used"
    cap = PAID_PER_DAY if cap is None else int(cap)
    used = paid_today(provider)
    if used + int(units) > cap:
        record(organ, cls="paid", provider=provider, model=model, stage="refused", extra={"units": int(units), "used_today": used, "cap": cap})
        return False, "paid budget: %d of %d reservations used today for %s; %d more refused" % (used, cap, provider, int(units))
    record(organ, cls="paid", provider=provider, model=model, stage="reserved", extra={"reservation_id": reservation_id, "units": int(units), "used_today": used + int(units), "cap": cap}, strict=True)
    return True, "reserved %d (%d/%d today)" % (int(units), used + int(units), cap)

def release_paid(organ, provider, model="", units=1, why="", *, reservation_id=None):
    """Cancel exactly one reservation after a structured provider auth rejection.

    Missing, mismatched and already-used receipts never reduce other spending.
    Callers must retain the reservation on ambiguous errors or timeouts.
    """
    if not reservation_id: return False
    try:
        from store_guard import transaction
        with transaction(_ledger()):
            rows = [r for r in _paid_rows() if r.get("reservation_id") == reservation_id]
            reserved = [r for r in rows if r.get("stage") == "reserved"]
            if len(reserved) != 1: return False
            original = reserved[0]
            if (original.get("organ"), original.get("provider"), original.get("model"), original.get("units")) != (organ, provider, model, units): return False
            if any(r.get("stage") == "released" for r in rows): return True
            record(organ, cls="paid", provider=provider, model=model, stage="released",
                   extra={"reservation_id": reservation_id, "units": units, "why": str(why or "")[:120]}, strict=True)
        return True
    except Exception:
        return False


def admit(cls, organ="", wait_s=None, provider="", model="", stage=""):
    return Admission(cls, organ, wait_s, provider, model, stage)

def _cli(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "touch":
        return 0 if touch_foreground() else 1
    if argv[0] == "status":
        print(json.dumps({"foreground_live": foreground_live(), "ledger": _ledger(),
                          "lines": sum(1 for _ in open(_ledger())) if os.path.exists(_ledger()) else 0}))
        return 0
    if argv[0] == "run":
        cls = argv[1] if len(argv) > 1 else "background"
        organ = ""; i = 2
        while i < len(argv) and argv[i] != "--":
            if argv[i] == "--organ" and i + 1 < len(argv):
                organ = argv[i + 1]; i += 2; continue
            i += 1
        cmd = argv[i + 1:] if i < len(argv) else []
        if not cmd:
            print("run: nothing to run after --", file=sys.stderr); return 2
        try:
            with admit(cls, organ=organ or os.path.basename(cmd[-1])[:40]) as a:
                rc = subprocess.call(cmd)
                a.stage = "exit:%d" % rc
                return rc
        except TimeoutError as e:
            print("[compute-admission] %s; not run: %s" % (e, " ".join(cmd)[:120]), file=sys.stderr)
            return 75   # EX_TEMPFAIL: the cron slot passed, nothing was started
    print("unknown command %r" % argv[0], file=sys.stderr); return 2

if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
