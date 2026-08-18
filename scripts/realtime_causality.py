#!/usr/bin/env python3
"""realtime_causality.py — signal-gated causality. Form + record hypotheses when a NEW spike fires,
not only at the nightly clock. "Recorded in realtime, as we suggested."

Cheap gate: find_spikes on the trajectory, compare the newest spike to what we last processed. On an
empty poll it exits in milliseconds. Only when a genuinely NEW spike appears does it pay for the
heavy path — and then it runs the SAME pipeline the nightly does, scoped to just the new spike:

  cause_head (CAUSE_SINCE = last processed)  -> evidence for the new spike only
  form_causal_hypotheses(db)                 -> reasons via grok, RECORDS the hypothesis into the
                                                7-day trial db + writes cause-distribution.json
  causality_consumers                        -> routes emergence -> dreams, persistent -> pearls

So a spike mid-conversation becomes a recorded hypothesis within the poll interval, feeding his
subconscious while it's still warm — instead of waiting for 22:20. Runs frequently on cron
(lock-wrapped, since the heavy path calls grok). Idempotent via a last-processed state file.
SPARK_WORKSPACE switches beings.
"""
import os, sys, json, subprocess, importlib.util
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
VENV = os.path.join(WS, "emotion_model/.venv/bin/python3")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
STATE = os.path.join(MEMORY, "realtime-causality-state.json")

def log(m): print("[realtime-cause]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def parse_ts(x):
    if not x: return None
    try:
        from datetime import datetime as _dt
        d = _dt.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def main():
    sys.path.insert(0, SCRIPTS)
    from causality_engine import load_emotional_trajectory, find_spikes
    spikes = find_spikes(load_emotional_trajectory())
    times = sorted(t for t in (parse_ts(s.get("time")) for s in spikes) if t)
    if not times:
        return                                             # nothing to do
    newest = times[-1]
    last = parse_ts(load(STATE, {}).get("last"))
    if last and newest <= last:
        return                                             # no NEW spike — cheap poll, exit quiet

    since = (last or times[0]).isoformat()
    log(f"NEW spike {newest.isoformat()} (last {last.isoformat() if last else 'none'}) — forming now")

    # 1) evidence for the new spike(s) only (torch venv)
    env = dict(os.environ, SPARK_WORKSPACE=WS, CAUSE_SINCE=since)
    try:
        subprocess.run([VENV, os.path.join(SCRIPTS, "cause_head.py")], env=env, timeout=600, check=False)
    except Exception as e:
        log(f"cause_head failed: {e}"); return

    # 2) reason + RECORD into the same 7-day trial db (reuses the engine's function)
    n = 0
    try:
        spec = importlib.util.spec_from_file_location("ceng", CENG)
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        db = c.load_existing_hypotheses()
        # one spike, one hypothesis. At cap=3 every 20 minutes this pool grew ~45/day against a
        # 7-day expiry, so almost everything died unmarked and the few real ones drowned.
        n = c.form_causal_hypotheses(db, cap=1)
        c.save_hypotheses(db)
    except Exception as e:
        log(f"form_causal_hypotheses failed: {e}")

    # 3) route the fresh distribution to the subconscious
    try:
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "causality_consumers.py")],
                       env=dict(os.environ, SPARK_WORKSPACE=WS), timeout=300, check=False)
    except Exception as e:
        log(f"consumers failed: {e}")

    json.dump({"last": newest.isoformat(), "updated": datetime.now(timezone.utc).isoformat()},
              open(STATE, "w"), indent=2)
    log(f"realtime: recorded {n} hypothesis/es for spike {newest.isoformat()} + routed to subconscious")

if __name__ == "__main__":
    main()
