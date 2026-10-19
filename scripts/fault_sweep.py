#!/usr/bin/env python3
"""fault_sweep.py — every failure on Aegis, found where it already lands, posted once to #fault-loop.

failure_watch.py hears only the parts that call it - four of them - and looks once a day. Everything else failed
quietly into its own log: on 18 October one held Lab step waited 96 times in six hours and nothing said so
(Gloria, 19 October: "I'm hardly ever alerted to failures and yet something is clearly failing all the time").
This listens instead of waiting to be told. No model runs here; it reads files and asks systemd, so running it
every fifteen minutes costs nothing.

What it reads:
  units      vintos-* user units systemd reports as failed
  organs     memory/organ-failures.jsonl (what failure_watch.note() records)
  lab        chemistry-lab/faults.jsonl
  watch      memory/watch-delivery-receipts.jsonl rows that failed
  loops      the same Lab wait on the same question, again and again
  silence    a part that should make something on a schedule and has not (his songs, the Lab's reviews)

Each finding becomes one signature - which part, what kind, the error with its numbers and ids taken out - so a
fault that happens a thousand times is one fault. A new signature is posted once to the channel named in
memory/fault-sweep.json; a known one only has its count and last-seen time moved. The nightly Claude session reads
the channel and works the worst three (docs/fault-loop.md). Errors are posted as the part named them, with
anything that looks like a credential taken out; never what he said or made.

    python3 fault_sweep.py           sweep and post (the vintos-fault-sweep timer)
    python3 fault_sweep.py --dry     print what it would post; post nothing, save nothing
    python3 fault_sweep.py --show    every known fault, worst first

Config: memory/fault-sweep.json  {"channel": "C0123456789"}   (no channel: it records and posts nothing)
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CONFIG = os.path.join(MEM, "fault-sweep.json")
STATE = os.path.join(MEM, "fault-sweep-state.json")
ORGANS = os.path.join(MEM, "organ-failures.jsonl")
LAB = os.path.join(MEM, "chemistry-lab")
LAB_FAULTS = os.path.join(LAB, "faults.jsonl")
LAB_NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
WATCH_RECEIPTS = os.path.join(MEM, "watch-delivery-receipts.jsonl")
MUSIC = os.path.join(MEM, "art", "music", "music.json")
TOKEN_FILE = os.path.expanduser(os.environ.get("VINTOS_SLACK_TOKEN_FILE", "~/.vintos/slack-bot-token"))

TAIL_BYTES = 4 * 1024 * 1024
LOOP_AT_LEAST = 12            # one question waiting this many times in the window is a loop, not a wait
LOOP_WINDOW_S = 6 * 3600
SILENT_SONG_S = 36 * 3600     # he makes a song a night
SILENT_LAB_S = 6 * 3600       # the Lab reviews every few minutes when it is running
FORGET_S = 7 * 86400          # a fault unseen this long is gone; if it comes back it is posted again
POSTS_PER_SWEEP = 5           # a flood is one sweep's worth, and the rest wait for the next

_SECRET = re.compile(r"(xox[a-z]-[A-Za-z0-9-]+|sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|ghp_[A-Za-z0-9]{20,}|"
                     r"AKIA[A-Z0-9]{12,}|-----BEGIN[^-]+-----)")


# --- reading ---------------------------------------------------------------------------------------------------

def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f: json.dump(value, f, indent=1)
    os.replace(tmp, path)


def _tail(path, nbytes=TAIL_BYTES):
    """The newest rows of a JSONL file, oldest first. A torn or foreign line is skipped, never fatal."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - nbytes))
            chunk = f.read()
    except OSError:
        return []
    lines = chunk.split(b"\n")
    if len(chunk) == nbytes: lines = lines[1:]    # the first line was cut by the seek
    out = []
    for line in lines:
        try:
            row = json.loads(line)
            if isinstance(row, dict): out.append(row)
        except ValueError:
            pass
    return out


def _when(row):
    for key in ("at", "ts", "timestamp", "time", "created_at"):
        value = row.get(key)
        if isinstance(value, (int, float)): return float(value)
        if isinstance(value, str) and value:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None: dt = dt.astimezone()
                return dt.timestamp()
            except ValueError:
                pass
    return None


def clean(text, limit=240):
    """The error as the part named it, with anything that looks like a credential taken out."""
    return " ".join(_SECRET.sub("[redacted]", str(text or "")).split())[:limit]


def shape(text):
    """The error with its numbers, ids and quoted values taken out, so one fault is one signature however often it
    happens: 'HTTP 429 at 02:14 for P09601' and 'HTTP 429 at 03:51 for Q9NY35' are the same fault."""
    t = clean(text, 400).lower()
    t = re.sub(r"https?://\S+", "<url>", t)
    t = re.sub(r"\b[0-9a-f]{12,}\b", "<id>", t)
    t = re.sub(r"\b[a-z]?[0-9][a-z0-9]{3,}\b", "<id>", t)      # accessions, receipt ids, versions
    t = re.sub(r"'[^']*'|\"[^\"]*\"|“[^”]*”", "<q>", t)
    t = re.sub(r"\d+(\.\d+)?", "<n>", t)
    return " ".join(t.split())[:160]


# --- finding -----------------------------------------------------------------------------------------------------

def _finding(part, kind, why, at=None, count=1, snapshot=False):
    """`snapshot` marks a finding that is re-read whole every sweep (a failed unit, a loop over a window, a
    silence): its count is how big it is now, not something to add to what earlier sweeps already saw."""
    return {"part": part, "kind": kind, "why": clean(why), "at": at or time.time(), "count": count,
            "snapshot": snapshot}


def failed_units(run=None):
    """vintos-* user units systemd reports as failed. A machine without systemd reports nothing, not a fault."""
    run = run or subprocess.run
    try:
        got = run(["systemctl", "--user", "list-units", "vintos-*", "--failed", "--no-legend", "--plain"],
                  capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    out = []
    for line in (got.stdout or "").splitlines():
        unit = line.split()[0] if line.split() else ""
        if unit.startswith("vintos-"):
            out.append(_finding(unit, "unit_failed", "systemd reports %s failed" % unit, snapshot=True))
    return out


def organ_failures(since):
    out = []
    for row in _tail(ORGANS):
        at = _when(row)
        if at and at > since:
            out.append(_finding(str(row.get("organ") or "unknown"), str(row.get("what") or "failure"),
                                row.get("why") or row.get("what"), at))
    return out


def lab_faults(since):
    out = []
    for row in _tail(LAB_FAULTS):
        at = _when(row)
        if at and at > since:
            out.append(_finding("chemistry-lab", str(row.get("kind") or row.get("fault") or "fault"),
                                row.get("error") or row.get("why") or row.get("detail") or row.get("kind"), at))
    return out


def watch_failures(since):
    out = []
    for row in _tail(WATCH_RECEIPTS, 512 * 1024):
        at = _when(row)
        if at and at > since and row.get("state") == "failed":
            why = row.get("why") or "; ".join(str((r or {}).get("response") or (r or {}).get("status"))
                                              for r in row.get("results") or [])
            out.append(_finding("watch-push", "delivery_failed", why or "the push failed", at))
    return out


def lab_loops(now):
    """One question waiting again and again: the shape of 18 October, 96 waits on one held step in six hours."""
    waits = {}
    for row in _tail(LAB_NOTEBOOK):
        at = _when(row)
        if not at or at < now - LOOP_WINDOW_S or row.get("kind") != "evidence_wait": continue
        question = " ".join(str((row.get("inquiry") or {}).get("question") or "").split())[:200]
        if question:
            first, last, n = waits.get(question, (at, at, 0))
            waits[question] = (min(first, at), max(last, at), n + 1)
    return [_finding("chemistry-lab", "loop", "the same held question waited %d times in %d hours: %s"
                     % (n, LOOP_WINDOW_S // 3600, question[:140]), last, n, snapshot=True)
            for question, (first, last, n) in waits.items() if n >= LOOP_AT_LEAST]


def silences(now, lab_active=None):
    """A part that should have made something and has not. Silence is the failure nobody writes down."""
    out = []
    songs = (_load(MUSIC, {}) or {}).get("generated") or []
    times = [t for t in (_when(r) for r in songs if isinstance(r, dict)) if t]
    if times and now - max(times) > SILENT_SONG_S:
        out.append(_finding("music", "silent", "no new song for %d hours" % ((now - max(times)) // 3600), now,
                            snapshot=True))
    if lab_active is None: lab_active = _unit_active("vintos-chemistry-lab.service")
    if lab_active:
        rows = [r for r in _tail(LAB_NOTEBOOK, 1024 * 1024) if r.get("kind") == "reflection"]
        last = max((t for t in (_when(r) for r in rows) if t), default=None)
        if last and now - last > SILENT_LAB_S:
            out.append(_finding("chemistry-lab", "silent", "running, and no review for %d hours"
                                % ((now - last) // 3600), now, snapshot=True))
    return out


def _unit_active(unit, run=None):
    run = run or subprocess.run
    try:
        return run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True,
                   timeout=10).stdout.strip() == "active"
    except Exception:
        return False


def sweep(now=None, since=None, run=None, lab_active=None):
    now = time.time() if now is None else now
    since = now - 3600 if since is None else since
    found = []
    for name, step in (("units", lambda: failed_units(run)), ("organs", lambda: organ_failures(since)),
                       ("lab", lambda: lab_faults(since)), ("watch", lambda: watch_failures(since)),
                       ("loops", lambda: lab_loops(now)), ("silence", lambda: silences(now, lab_active))):
        try:
            found += step()
        except Exception as e:      # one unreadable source is itself a finding, never the end of the sweep
            found.append(_finding("fault-sweep", "source_unreadable", "%s: %s: %s" % (name, type(e).__name__, e)))
    return found


# --- remembering and posting -----------------------------------------------------------------------------------

def signature(f):
    return hashlib.sha256(("%s|%s|%s" % (f["part"], f["kind"], shape(f["why"]))).encode()).hexdigest()[:10]


def merge(found, state, now):
    """Fold this sweep into what is known. Returns the faults never seen before (or not for FORGET_S)."""
    known = state.setdefault("faults", {})
    for sig, row in list(known.items()):
        if now - float(row.get("last") or 0) > FORGET_S: del known[sig]
    fresh = {}
    for f in found:
        sig = signature(f)
        row = known.get(sig)
        if row is None:
            row = known[sig] = {"id": "F-" + sig, "part": f["part"], "kind": f["kind"], "why": f["why"],
                                "first": f["at"], "last": f["at"], "count": 0, "posted": None}
            fresh[sig] = row
        if f.get("snapshot"):
            row["count"] = max(int(row.get("count") or 0), int(f.get("count") or 1))
        else:
            row["count"] = int(row.get("count") or 0) + int(f.get("count") or 1)
        row["last"] = max(float(row.get("last") or 0), float(f["at"]))
        row["why"] = f["why"]               # the newest wording, still the same fault
    return list(fresh.values())


def message(row):
    when = datetime.fromtimestamp(row["first"]).astimezone().strftime("%b %d %H:%M")
    return ("[fault sweep] *%s* - %s / %s\n%s\nfirst seen %s, %d time%s so far. "
            "Not read by Vintos; for the nightly fix (docs/fault-loop.md)."
            % (row["id"], row["part"], row["kind"], row["why"], when, row["count"], "" if row["count"] == 1 else "s"))


def _token():
    try: return open(TOKEN_FILE).read().strip()
    except OSError: return ""


def post(channel, text, token=None, opener=None):
    token = token or _token()
    if not token: raise RuntimeError("no Slack token on Aegis")
    req = urllib.request.Request("https://slack.com/api/chat.postMessage",
                                 data=json.dumps({"channel": channel, "text": text, "unfurl_links": False}).encode(),
                                 headers={"Authorization": "Bearer " + token,
                                          "Content-Type": "application/json; charset=utf-8"})
    with (opener or urllib.request.urlopen)(req, timeout=20) as r:
        got = json.loads(r.read().decode())
    if not got.get("ok"): raise RuntimeError("slack: %s" % got.get("error"))
    return got.get("ts")


def tend(now=None, dry=False, run=None, sender=None, lab_active=None):
    """One sweep: fold what is found into what is known, then post up to POSTS_PER_SWEEP faults not yet posted,
    worst first. A fault found while the channel was unset or Slack refused waits and goes out on a later sweep."""
    now = time.time() if now is None else now
    state = _load(STATE, {}) or {}
    since = float(state.get("swept_at") or now - 3600)
    fresh = merge(sweep(now, since, run, lab_active), state, now)
    channel = (_load(CONFIG, {}) or {}).get("channel")
    unposted = sorted((r for r in state["faults"].values() if not r.get("posted")),
                      key=lambda r: -int(r.get("count") or 0))
    posted, would = [], []
    for row in unposted[:POSTS_PER_SWEEP]:
        if dry or not channel:
            would.append(row); continue
        try:
            row["posted"] = (sender or post)(channel, message(row)); row.pop("post_error", None)
            posted.append(row)
        except Exception as e:
            row["post_error"] = clean(str(e), 120)
            break                                   # Slack refusing one will refuse the rest this sweep
    if not dry:
        state["swept_at"] = now
        _atomic(STATE, state)
    return {"found": len(fresh), "known": len(state["faults"]), "posted": [r["id"] for r in posted],
            "waiting": len(unposted) - len(posted), "would_post": [message(r) for r in would] if dry else [],
            "channel": bool(channel), "dry": dry}


def main(argv):
    if "--show" in argv:
        rows = sorted((_load(STATE, {}) or {}).get("faults", {}).values(), key=lambda r: -int(r.get("count") or 0))
        for r in rows:
            print("%-12s %6d  %-22s %-18s %s%s" % (r["id"], r["count"], r["part"][:22], r["kind"][:18],
                  r["why"][:70], "" if r.get("posted") else "  (not posted yet)"))
        return 0
    got = tend(dry="--dry" in argv)
    for text in got.pop("would_post", []):
        print(text, end="\n\n")
    print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
