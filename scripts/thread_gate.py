#!/usr/bin/env python3
"""thread_gate.py — whether the thread-processing cycles may run (Gloria, 27 October 2026).

Dreams, the mirror and the ghost branches exist to work on unresolved threads. They run only when the
pool holds one; dreams keep a floor of one a night, so a night with an empty pool still has its dream.

An unresolved thread is a pool entry that is
  - open: not consumed and not retired (the same test seed_thread uses for "open"), and
  - judged a tension: the formation door's classification is not "thematic_current" (a settled topic with
    nothing pulling; entries from before the door have no classification and count), and
  - not an imagined possibility: premonition seeds are futures that have not happened.
The mirror and the ghost branches never take dream_only threads, so for them a dream_only thread does not count.

The dream floor is read from the dream log, so it holds across restarts: a night (keyed as dream-trigger.sh keys
it: before 07:00 the night belongs to yesterday) that has no dream logged yet may have one with an empty pool.

Usage (the triggers call this; exit 0 = run, 1 = stay quiet, one line on stdout says why):
  thread_gate.py dream | mirror | ghost
Read-only. No LLM. No network.
"""
import os, sys, json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
DREAM_LOG = os.path.join(WORKSPACE, "memory", "dream-log.json")
QUIET_END = 7                     # should-dream.sh's QUIET_END; dream-trigger.sh's night key turns here
IMAGINED_MARK = "[AN IMAGINED POSSIBILITY"


def _pool(path=None):
    """The pool through its door; None when it cannot be read."""
    import thread_store
    return thread_store.load_pool(path)


def is_unresolved(t):
    if not isinstance(t, dict) or t.get("consumed") or t.get("retired"):
        return False
    if t.get("classification") == "thematic_current":
        return False
    if t.get("source") == "premonition" or str(t.get("thread", "")).lstrip().startswith(IMAGINED_MARK):
        return False
    return bool(str(t.get("thread", "")).strip())


def unresolved_threads(pool, for_cycle="dream"):
    """The unresolved threads a cycle can work on. The mirror and the ghosts skip dream_only threads."""
    out = [t for t in (pool or []) if is_unresolved(t)]
    if for_cycle != "dream":
        out = [t for t in out if not t.get("dream_only")]
    return out


def night_key(now=None):
    now = now or datetime.now()
    return (now - timedelta(days=1)).strftime("%Y-%m-%d") if now.hour < QUIET_END else now.strftime("%Y-%m-%d")


def dreams_logged(night, log_path=None):
    try:
        with open(log_path or DREAM_LOG) as f:
            data = json.load(f)
    except Exception:
        return 0
    return sum(len(n.get("dreams") or []) for n in (data.get("nights") or [])
               if isinstance(n, dict) and n.get("night_of") == night)


def decide(cycle, now=None, pool_path=None, log_path=None):
    """(run, reason) for cycle in dream | mirror | ghost."""
    pool = _pool(pool_path)
    open_n = len(unresolved_threads(pool, cycle)) if pool is not None else 0
    seen = "pool unreadable" if pool is None else "%d unresolved thread(s)" % open_n
    if open_n:
        return True, seen
    if cycle == "dream":
        night = night_key(now)
        had = dreams_logged(night, log_path)
        if had == 0:
            return True, "%s; the night of %s has no dream yet - its one dream" % (seen, night)
        return False, "%s; the night of %s already has %d dream(s)" % (seen, night, had)
    return False, seen


def main(argv):
    cycle = argv[1] if len(argv) > 1 else ""
    if cycle not in ("dream", "mirror", "ghost"):
        print("usage: thread_gate.py dream|mirror|ghost", file=sys.stderr)
        return 2
    try:
        run, why = decide(cycle)
    except Exception as e:
        # The gate failing must not silence a cycle it cannot judge: it runs as it did before the gate.
        print("[thread-gate] %s: gate error (%s) - running as before" % (cycle, e))
        return 0
    print("[thread-gate] %s: %s - %s" % (cycle, "run" if run else "quiet", why))
    return 0 if run else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
