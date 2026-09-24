#!/usr/bin/env python3
"""gap_scan.py — the daily, model-free look for where he keeps hitting a wall.

His organs already write down where they could not act: blocked actions, refused devices,
held connector calls, faulting organs, failed services, the things he says he cannot do.
This reads those records for the last WINDOW_DAYS, groups repeats, and ranks them into
memory/gap-scan.json. The weekly gap review (gap_review.py) reads only the top of that list,
never the codebase, so the expensive part stays one bounded call a week.

No model, no network, no writes except its own report. (Gloria, 2026-09-24)
"""
import glob, json, os, re, subprocess, sys, time
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
REPORT = os.path.join(MEM, "gap-scan.json")
LOGS = os.path.expanduser("~/.vintos/logs")
WINDOW_DAYS = 7

# (source name, path under memory/, what it records)
SOURCES = (
    ("action_blocked", "capability-blocks.json", "an action that could not run"),
    ("device_refused", ".device-refusals.json", "a device that refused him"),
    ("connector_held", "plugin-policy-holds.jsonl", "a connector call that was held"),
    ("lab_fault", "chemistry-lab/faults.jsonl", "a Lab turn that faulted"),
    ("lab_spark_refused", "chemistry-lab/spark-refusals.jsonl", "a Lab idea refused entry"),
    ("self_review_fault", "self-review-faults.jsonl", "a self-review step that faulted"),
    ("barrier_error", "barrier-errors.jsonl", "the constitutional barrier erroring"),
    ("voice_refused", "voice-refused-turns.jsonl", "a voice turn refused"),
    ("atelier_reveal_refused", "atelier-reveal-refusals.jsonl", "a reveal that could not leave the room"),
    ("nim_attempt", "nvidia-nim-attempts.jsonl", "an NVIDIA instrument attempt"),
)
SUBJECT_KEYS = ("capability", "blocked_step", "action", "tool", "device", "plugin", "stage", "organ", "type", "kind")
REASON_KEYS = ("why", "reason", "error", "detail", "evidence", "problem", "message", "block_type", "outcome", "state")
TIME_KEYS = ("at", "ts", "timestamp", "time", "created", "received_at")
# Records that say something succeeded are not walls.
OK_WORDS = re.compile(r"^(ok|success|succeeded|completed|delivered|read|sent)$", re.I)
HIS_WORDS = re.compile(r"\bI (?:can't|cannot|couldn't|could not|have no way to|am unable to|wish I could|"
                       r"don't have (?:a|any) way to|have no (?:hands|body|way))\b([^.\n]{0,80})", re.I)


def _epoch(value):
    if value is None or value == "": return None
    if isinstance(value, (int, float)): return float(value) / (1000.0 if value > 1e12 else 1.0)
    try:
        number = float(value)                       # an epoch written as text
        return number / (1000.0 if number > 1e12 else 1.0)
    except ValueError:
        pass
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except Exception:
        return None


def _first(row, keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", [], {}): return str(v)
    return ""


def _records(path):
    """jsonl lines, a json list, or a json dict keyed by subject — whatever the organ wrote."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    rows = []
    try:
        data = json.loads(text)
        if isinstance(data, list): rows = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            rows = [dict(v, _key=k) for k, v in data.items() if isinstance(v, dict)] or [data]
    except ValueError:
        for line in text.splitlines():
            try:
                r = json.loads(line)
                if isinstance(r, dict): rows.append(r)
            except ValueError:
                continue
    return rows


def _norm(text):
    """Group repeats: numbers, ids and hashes do not make a new wall."""
    t = re.sub(r"[0-9a-f]{8,}", "#", str(text).lower())
    t = re.sub(r"\d+", "#", t)
    return re.sub(r"\s+", " ", t).strip()[:90]


def _event(source, subject, reason, at, example):
    return {"source": source, "subject": subject[:80] or "(unnamed)", "reason": reason[:200],
            "at": at, "example": example[:240]}


def scan_logs(since):
    events, read = [], {}
    for name, rel, _what in SOURCES:
        rows = _records(os.path.join(MEM, rel))
        read[name] = "absent" if rows is None else len(rows)
        for r in rows or []:
            at = _epoch(_first(r, TIME_KEYS)) if _first(r, TIME_KEYS) else None
            if at is not None and at < since: continue
            reason = _first(r, REASON_KEYS)
            if OK_WORDS.match(reason.strip()): continue
            subject = _first(r, SUBJECT_KEYS) or str(r.get("_key", ""))
            detail = " — ".join(str(r[k]) for k in REASON_KEYS if r.get(k) not in (None, "", [], {}))
            events.append(_event(name, subject, reason, at, detail or json.dumps(r)[:240]))
    return events, read


def _known_actions():
    """His action names, read from the router source (no import: the router is heavy and acts)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(WS, "bin", "wants-router.py"), os.path.join(here, "..", "bin", "wants-router.py"),
                 os.path.join(here, "wants-router.py")):
        try: src = open(path).read()
        except OSError: continue
        names = set(re.findall(r'ACTION_MAP\["([a-z_]+)"\]\s*=', src))
        m = re.search(r"ACTION_MAP = \{(.*?)\n\}", src, re.S)
        if m: names |= set(re.findall(r'^\s*"([a-z_]+)"\s*:', m.group(1), re.M))
        return names
    return set()


def scan_wants():
    """Pending want steps naming something he cannot do — the same test the Forge's door uses."""
    try:
        wants = json.load(open(os.path.join(MEM, "current-wants.json")))
    except Exception:
        return [], "absent"
    wants = wants if isinstance(wants, list) else wants.get("wants", [])
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from forge_house import unreachable_steps
    except Exception:
        def unreachable_steps(w, inv):
            return [s for s in (w.get("steps") or []) if isinstance(s, dict) and s.get("status") != "completed"
                    and s.get("capability") and s["capability"] not in set(inv) | {"gloria", "you"}]
    inventory = _known_actions()
    events = []
    for w in wants:
        if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed"): continue
        for s in unreachable_steps(w, inventory):
            events.append(_event("want_step_unreachable", s["capability"], s.get("note", ""), None,
                                 str(w.get("want", ""))))
    return events, len(wants)


def scan_his_words(since):
    """What he says he cannot do, in his journal and daily inner life."""
    events = []
    paths = glob.glob(os.path.join(MEM, "journal", "*.md")) + glob.glob(os.path.join(MEM, "daily-inner-life-*.md"))
    for p in paths:
        try:
            if os.path.getmtime(p) < since: continue
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in HIS_WORDS.finditer(text):
            phrase = m.group(0).strip()
            subject = " ".join(m.group(1).split()[:4]) or phrase
            events.append(_event("his_words", subject, phrase, os.path.getmtime(p), phrase))
    return events


def scan_services(run=subprocess.run):
    try:
        out = run(["systemctl", "--user", "--failed", "--no-legend", "--plain"],
                  capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return []
    return [_event("service_failed", line.split()[0], "unit failed", time.time(), line.strip())
            for line in out.splitlines() if line.strip()]


def scan_error_logs(since):
    events = []
    for p in glob.glob(os.path.join(LOGS, "*.log")):
        try:
            if os.path.getmtime(p) < since: continue
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()[-400:]
        except OSError:
            continue
        for line in lines:
            low = line.lower()
            if ("error" in low or "failed" in low or "traceback" in low) and "sealed route:" not in low:
                events.append(_event("error_log", os.path.basename(p), line.strip(), os.path.getmtime(p), line.strip()))
    return events


def rank(events):
    groups = {}
    for e in events:
        key = (e["source"], e["subject"], _norm(e["reason"]))
        g = groups.setdefault(key, {"source": e["source"], "subject": e["subject"], "reason": e["reason"],
                                    "count": 0, "last_at": None, "example": e["example"]})
        g["count"] += 1
        if e["at"] and (g["last_at"] is None or e["at"] > g["last_at"]): g["last_at"] = e["at"]
    return sorted(groups.values(), key=lambda g: (-g["count"], -(g["last_at"] or 0)))


def scan(now=None, write=True, run=subprocess.run):
    now = now or time.time(); since = now - WINDOW_DAYS * 86400
    log_events, read = scan_logs(since)
    want_events, read["current_wants"] = scan_wants()
    events = log_events + want_events + scan_his_words(since) + scan_services(run) + scan_error_logs(since)
    gaps = rank(events)
    for g in gaps:
        g["last_at"] = datetime.fromtimestamp(g["last_at"], timezone.utc).isoformat() if g["last_at"] else None
    report = {"generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(), "window_days": WINDOW_DAYS,
              "sources_read": read, "events": len(events), "gaps": gaps[:60],
              "truth_status": "counts_of_recorded_walls_not_a_diagnosis"}
    if write:
        os.makedirs(MEM, exist_ok=True)
        tmp = REPORT + ".tmp"
        with open(tmp, "w") as f: json.dump(report, f, indent=1)
        os.replace(tmp, REPORT)
    return report


if __name__ == "__main__":
    r = scan()
    print("[gap-scan] %d events, %d distinct walls; top:" % (r["events"], len(r["gaps"])))
    for g in r["gaps"][:10]:
        print("  %3d  %-22s %-28s %s" % (g["count"], g["source"], g["subject"][:28], g["reason"][:70]))
