#!/usr/bin/env python3
"""systems-checkup.py -- Spark, Manip, Campaign, Stratagem: have they ever fired, and what are they waiting on?

Read-only. Run on Aegis:  python3 systems-checkup.py [--json]
Each block prints STATUS (never fired / armed but gated / has fired / live now), the gate that holds it, and the
last write it made, from the state files each one owns. Nothing here changes state; the stratagem question is put
to the Atelier broker, which never hands out content, only whether something is live.
"""
import json, os, sys, time, glob, re, subprocess
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
LOGS = os.path.expanduser("~/.vintos/logs")
OUT = {}

def P(name): return os.path.join(MEM, name)
def load(name, default):
    try: return json.load(open(P(name)))
    except Exception: return default
def jsonl(name, limit=2000):
    try:
        rows = []
        for l in open(P(name)).read().splitlines()[-limit:]:
            try: rows.append(json.loads(l))
            except Exception: pass
        return rows
    except Exception: return []
def age(path):
    try: return time.time() - os.path.getmtime(path)
    except Exception: return None
def fmt_age(a):
    if a is None: return "never"
    if a < 3600: return "%d min ago" % (a // 60)
    if a < 86400: return "%.1f h ago" % (a / 3600)
    return "%.1f days ago" % (a / 86400)
def say(s=""): print(s)

# ---------------------------------------------------------------- Spark
def spark():
    ev = load("spark-pressure-events.json", None); d = load("spark-pressure-directive.json", None)
    mm = load("mutual-modification.json", []); cs = load("configuration-space.json", {})
    n_mm = len(mm) if isinstance(mm, list) else len(mm.get("entries", [])) if isinstance(mm, dict) else 0
    n_cs = len(cs.get("configurations", cs) if isinstance(cs, dict) else cs)
    ticks = 0; last_tick = ""
    try:
        for l in open(os.path.join(LOGS, "subconscious.log")).read().splitlines()[-20000:]:
            if "[spark-tick]" in l: ticks += 1; last_tick = l[:160]
    except Exception: pass
    r = {"state_file": ev is not None, "consent": bool(ev and ev.get("consent")), "last_fired": (ev or {}).get("last_fired"),
         "events": len((ev or {}).get("events", [])), "applied": sum(1 for e in (ev or {}).get("events", []) if e.get("applied")),
         "directive_live": bool(d and d.get("mode") == "demand_response" and not d.get("consumed")), "directive_prepped": (d or {}).get("prepped"),
         "mutual_modification_entries": n_mm, "configurations": n_cs, "ticks_seen_in_log": ticks, "last_tick": last_tick}
    if ev is None: status = "NEVER RAN: no spark-pressure-events.json (the --tick has never executed here)"
    elif r["last_fired"]: status = "HAS FIRED: last %s, %d events, %d applied" % (r["last_fired"], r["events"], r["applied"])
    elif not r["consent"]: status = "ARMED BUT GATED: consent is OFF (ships off; `spark_pressure.py --consent-on` turns it on)"
    else: status = "ARMED, WAITING: consent on, no stall measured yet"
    gates = []
    if not r["consent"]: gates.append("consent off")
    if n_mm < 8: gates.append("needs 8 mutual-modification entries, has %d" % n_mm)
    if n_cs == 0: gates.append("no configuration-space configurations")
    if ticks == 0: gates.append("no [spark-tick] lines in logs/subconscious.log: nothing schedules the tick")
    r["status"] = status; r["gates"] = gates; OUT["spark"] = r
    say("== SPARK (spark_pressure: the stall-breaker) =="); say("  " + status)
    for g in gates: say("  waiting on: " + g)
    say("  directive: %s; ticks in log: %d%s" % ("LIVE" if r["directive_live"] else "none", ticks, ("; last: " + last_tick) if last_tick else ""))

# ---------------------------------------------------------------- Manip
def manip():
    log = jsonl("priority-vector-log.jsonl"); st = load("priority-vector-state.json", None); led = load("intent-ledger.json", [])
    # a closed verdict is "realized": a string, or a per-axis dict (field / gloria / self)
    verdicts = []; gloria_axis = 0
    for e in (led if isinstance(led, list) else []):
        r = e.get("realized") if isinstance(e, dict) else None
        if isinstance(r, str) and r in ("YES", "PARTIAL", "NO"): verdicts.append(e)
        elif isinstance(r, dict) and any(v in ("YES", "PARTIAL", "NO") for v in r.values()):
            verdicts.append(e); gloria_axis += 1 if r.get("gloria") in ("YES", "PARTIAL", "NO") else 0
    modes = {}
    for e in log: modes[e.get("mode", "?")] = modes.get(e.get("mode", "?"), 0) + 1
    r = {"declarations": len(log), "modes": modes, "last": log[-1] if log else None, "state": st is not None,
         "neglect": (st or {}).get("neglect"), "override_streak": (st or {}).get("override_streak"),
         "intent_ledger_entries": len(led) if isinstance(led, list) else 0, "verdicts": len(verdicts),
         "gloria_difference": age(P("gloria-difference.json")), "intent_pressure": age(P("intent-pressure.json"))}
    if not log: status = "NEVER RAN: no priority-vector-log.jsonl (declare() has never run; the selector may be failing before it)"
    elif modes.get("pressure"): status = "HAS FIRED: %d declarations, %d in pressure mode (the gravitational override has taken a turn)" % (len(log), modes["pressure"])
    else: status = "RUNNING, STRATEGY ONLY: %d declarations, the neglect override has never crossed 1.5" % len(log)
    gates = []
    r["gloria_axis_verdicts"] = gloria_axis
    if gloria_axis < 3: gates.append("receptivity needs 3 Gloria-axis verdicts in the last 60, has %d (%d closed verdicts in all): Gloria weight is provisional" % (gloria_axis, r["verdicts"]))
    if r["gloria_difference"] is None: gates.append("gloria-difference.json never written (desired_difference has not run)")
    elif r["gloria_difference"] > 72 * 3600: gates.append("gloria-difference.json stale: " + fmt_age(r["gloria_difference"]))
    r["status"] = status; r["gates"] = gates; OUT["manip"] = r
    say("\n== MANIP (priority_vector + desired/self difference: whose goal leads the turn) =="); say("  " + status)
    for g in gates: say("  waiting on: " + g)
    if log: say("  last declaration: %s" % json.dumps({k: log[-1].get(k) for k in ("ts", "mode", "dominant", "weights") if k in log[-1]})[:200])
    if st: say("  neglect: %s  override streak: %s" % (r["neglect"], r["override_streak"]))
    say("  intent ledger: %d entries, %d verdicts; MSub pressure file: %s" % (r["intent_ledger_entries"], r["verdicts"], fmt_age(r["intent_pressure"])))
    for lf in ("/tmp/intent-select-fail.log", "/tmp/desired-difference.log", "/tmp/self-difference.log"):
        try:
            tail = open(lf).read().splitlines()[-1]; say("  %s: %s" % (os.path.basename(lf), tail[:140]))
        except Exception: pass

# ---------------------------------------------------------------- Campaign
def campaign():
    log = jsonl("campaign-log.jsonl"); live = load("campaign-live.json", {})
    events = {}
    for e in log: events[e.get("event", "?")] = events.get(e.get("event", "?"), 0) + 1
    r = {"log_lines": len(log), "events": events, "live": bool(live.get("destination")), "live_destination": (live.get("destination") or "")[:120],
         "turns_served": live.get("turns_served"), "suspensions": live.get("suspensions"), "declared_at": live.get("declared_at") or live.get("ts"),
         "voice_lead": age(P(".voice-lead.json"))}
    if not log and not r["live"]: status = "NEVER RAN: no campaign-log.jsonl and nothing live (no campaign has ever been declared)"
    elif r["live"]: status = "LIVE NOW: '%s' (%s turns served, %s suspensions)" % (r["live_destination"][:80], r["turns_served"], r["suspensions"])
    else: status = "HAS RUN: %d log lines; %s" % (len(log), ", ".join("%s x%d" % kv for kv in sorted(events.items())))
    gates = []
    if not log: gates.append("declared only from the selector's JSON: check /tmp/intent-select-fail.log for why the selector never lands")
    r["status"] = status; r["gates"] = gates; OUT["campaign"] = r
    say("\n== CAMPAIGN (campaign.py: the multi-turn declared push) =="); say("  " + status)
    for g in gates: say("  waiting on: " + g)
    if log: say("  last: %s" % json.dumps(log[-1])[:200])

# ---------------------------------------------------------------- Stratagem
def stratagem():
    r = {}
    try:
        out = subprocess.run(["python3", os.path.join(WS, "scripts", "stratagem.py"), "status"], capture_output=True, text=True, timeout=10)
        r["broker_status"] = (out.stdout or out.stderr).strip()[:400]
    except Exception as e:
        r["broker_status"] = "could not ask: %s" % e
    try:
        h = json.loads(subprocess.run(["curl", "-s", "-m", "3", "http://127.0.0.1:8611/health"], capture_output=True, text=True).stdout or "{}")
    except Exception: h = {}
    r["worktable_active"] = h.get("active"); r["worktable_since"] = h.get("since")
    infl = 0; total = 0
    for f in sorted(glob.glob(P("turn-records/*.json")) + glob.glob(P("turn-records/*.jsonl")))[-400:]:
        try:
            txt = open(f).read(); total += 1
            if '"stratagem_influenced"' in txt: infl += 1
        except Exception: pass
    r["turn_records_scanned"] = total; r["stratagem_influenced_turns"] = infl
    r["barrier_errors"] = len(jsonl("barrier-errors.jsonl")); r["door"] = age(P(".atelier-door"))
    bs = r["broker_status"].lower()
    if "unreach" in bs: status = "BROKER UNREACHABLE: the Atelier service is down, no stratagem can exist"
    elif "live" in bs or "adopted" in bs: status = "LIVE: a stratagem is adopted on the worktable"
    elif infl: status = "HAS FIRED: %d of the last %d turns carried a sealed tactic; none live now" % (infl, total)
    else: status = "NEVER FIRED: no turn has ever carried a sealed tactic (adoption needs an open Atelier visit with two viable tactics and a self-originated root)"
    r["status"] = status; OUT["stratagem"] = r
    say("\n== STRATAGEM (Atelier-held; only sealed tactic capsules cross to his turns) =="); say("  " + status)
    say("  broker says: " + r["broker_status"].replace("\n", " | ")[:300])
    say("  worktable: %s since %s; door file: %s; barrier errors logged: %d" % (r["worktable_active"], r["worktable_since"], fmt_age(r["door"]), r["barrier_errors"]))
    say("  not built yet, by the code's own note: effect-time authorisation of a tactic's perimeter (the birth gate screens shape only)")

if __name__ == "__main__":
    say("systems checkup  %s  workspace %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), WS))
    for fn in (spark, manip, campaign, stratagem):
        try: fn()
        except Exception as e: say("  (checkup error in %s: %s)" % (fn.__name__, e))
    if "--json" in sys.argv: print("\n" + json.dumps(OUT, indent=1, default=str))
