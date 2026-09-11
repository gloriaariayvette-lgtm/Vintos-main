#!/usr/bin/env python3
"""schedule-graph.py - who owns each scheduled job, when it may be quiet, and what happens when two fire at once.

Review item 20 (2026-09-10). The crontab lives on the host, not in the checkout; this reads it there
(`crontab -l`) or from a file, joins every line to the wrapper it launches, and reads the wrapper for its
owner (the python it runs), its organ (the compute-admission name), its lock (llm-lock), its quiet gate
(an hour window the wrapper exits on), and its consent gate. Then it looks for overlap: two jobs that can
fire in the same minute. An overlap is handled when both sides carry admission or the lock; otherwise it
is named.

    python3 schedule-graph.py                     from `crontab -l`, print the report
    python3 schedule-graph.py --crontab FILE      from a saved crontab
    python3 schedule-graph.py --write             also write memory/schedule-graph.json
    python3 schedule-graph.py --static            no crontab: the wrappers alone (what the checkout can answer)
"""
import os, re, sys, json, time, subprocess

HOME = os.path.expanduser("~")
WS = os.path.join(HOME, ".vintos", "workspace")
MEMORY = os.path.join(WS, "memory")
HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = [os.path.join(WS, "scripts"), os.path.join(WS, "bin"), os.path.join(HOME, "Vintos"), HERE,
          os.path.join(os.path.dirname(HERE), "bin")]

QUIET_STATES = {   # what "nothing happened" means for a job, so silence is not mistaken for a fault
    "consent-gated": "he declined; the wrapper exits 0 and writes nothing",
    "hour-gated": "outside its hour window; exits 0",
    "idle-gated": "she was here recently; exits 0",
    "admitted": "a live turn held the slot; compute_admission waited or returned 75 (nothing written)",
    "locked": "llm-lock was held; the run waited for it",
    "stance-gated": "a want of his asked for less of this; want_stance refused the start and the wrapper exits 0",
}


def find_script(name):
    for d in SEARCH:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return ""


def read_wrapper(path):
    """Owner, organ, gates from the wrapper text. Nothing is executed."""
    try:
        s = open(path, errors="replace").read()
    except Exception:
        return {}
    w = {"path": path, "gates": [], "overlap": []}
    m = re.search(r"--organ\s+([A-Za-z0-9_.-]+)", s)
    if m:
        w["organ"] = m.group(1); w["overlap"].append("compute_admission")
    if "llm-lock.sh" in s:
        w["overlap"].append("llm-lock")
    if re.search(r"\bflock\b", s):
        w["overlap"].append("flock")
    py = re.findall(r"python3\s+\"?\$?\{?[A-Z_]*\}?/?([A-Za-z0-9_./-]+\.py)\"?(?:\s+([a-z][a-z_-]*))?", s)
    # A gate consulted BEFORE the work is not the owner of the job. compute_admission and
    # velqan_context were already excluded for this reason; want_stance joins them — it sits
    # on the first line of a wrapper, so taking owners[0] blindly made the journal's owner
    # read as "want_stance.py allow" and turned a gated job into an unowned one.
    GATES_NOT_OWNERS = ("compute_admission", "velqan_context", "want_stance")
    owners = [os.path.basename(p) + ((" " + a) if a else "") for p, a in py
              if not any(g in p for g in GATES_NOT_OWNERS)]
    if any("want_stance" in p for p, _ in py):
        w["gates"].append("stance-gated")
    if owners:
        w["owner"] = owners[0]; w["runs"] = owners
    if "consent-gate.sh" in s:
        w["gates"].append("consent-gated")
    if re.search(r'HOUR.*-lt|HOUR.*-ge|HOUR.*-gt', s):
        w["gates"].append("hour-gated")
    if "IDLE_HOURS" in s or "last-message-time" in s:
        w["gates"].append("idle-gated")
    if "compute_admission" in w["overlap"]:
        w["gates"].append("admitted")
    if "llm-lock" in w["overlap"]:
        w["gates"].append("locked")
    w["quiet_states"] = {g: QUIET_STATES[g] for g in w["gates"]}
    return w


# ------------------------------------------------------------ cron fields

def _field(spec, lo, hi):
    out = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, step = part.split("/", 1); step = int(step)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = [int(x) for x in part.split("-", 1)]
        else:
            a = b = int(part)
        out.update(range(a, b + 1, step))
    return out


def parse_crontab(text):
    jobs = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" in ln.split()[0]:
            continue
        parts = ln.split(None, 5)
        if len(parts) < 6:
            continue
        mi, ho, dom, mon, dow, cmd = parts
        try:
            fire = {(m, h) for m in _field(mi, 0, 59) for h in _field(ho, 0, 23)}
        except ValueError:
            continue
        script = ""
        for tok in re.findall(r"[^\s;&|]+\.(?:sh|py)", cmd):
            script = os.path.basename(tok); break
        jobs.append({"schedule": " ".join([mi, ho, dom, mon, dow]), "command": cmd, "script": script,
                     "fires": fire, "day": f"{dom} {mon} {dow}", "minutes_per_day": len(fire) if dom == "*" and dow == "*" else None})
    return jobs


def build(crontab_text=None):
    jobs = parse_crontab(crontab_text or "")
    for j in jobs:
        w = read_wrapper(find_script(j["script"])) if j["script"] else {}
        j.update({k: v for k, v in w.items() if k != "path"}); j["wrapper"] = w.get("path", "")
        j.setdefault("owner", j["script"] or "?"); j.setdefault("organ", ""); j.setdefault("gates", []); j.setdefault("overlap", [])
        j.setdefault("quiet_states", {})
        if not j["wrapper"] and j["script"]:
            j["note"] = "wrapper not found in the checkout or the workspace"
    overlaps = []
    for i in range(len(jobs)):
        for k in range(i + 1, len(jobs)):
            a, b = jobs[i], jobs[k]
            shared = a["fires"] & b["fires"]
            if not shared or (a["day"] != b["day"] and "*" not in (a["day"], b["day"]) and a["day"].split()[2] != b["day"].split()[2] and a["day"].split()[2] != "*" and b["day"].split()[2] != "*"):
                continue
            handled = bool(a["overlap"]) and bool(b["overlap"])
            overlaps.append({"a": a["owner"], "b": b["owner"], "same_minute_count": len(shared),
                             "first": "%02d:%02d" % (sorted(shared, key=lambda x: (x[1], x[0]))[0][1], sorted(shared, key=lambda x: (x[1], x[0]))[0][0]),
                             "handled": handled,
                             "how": (", ".join(sorted(set(a["overlap"]) & set(b["overlap"])) or set(a["overlap"]) | set(b["overlap"]))) if handled
                                    else "UNHANDLED: %s carries %s; %s carries %s" % (a["owner"], a["overlap"] or "nothing", b["owner"], b["overlap"] or "nothing")})
    for j in jobs:
        j["fires"] = sorted("%02d:%02d" % (h, m) for m, h in j["fires"])[:48]
    return {"contract": "schedule-graph", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "jobs": jobs,
            "overlaps": overlaps, "unhandled": [o for o in overlaps if not o["handled"]],
            "owners": sorted({j["owner"] for j in jobs}), "organs": sorted({j["organ"] for j in jobs if j["organ"]})}


def static_graph():
    """Without a crontab: every wrapper the checkout knows, with its owner, organ and gates."""
    rows = []
    seen = set()
    for d in SEARCH:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".sh") or f in seen:
                continue
            w = read_wrapper(os.path.join(d, f))
            if w.get("owner") or w.get("organ"):
                seen.add(f); rows.append({"script": f, **{k: v for k, v in w.items() if k != "path"}})
    return {"contract": "schedule-graph", "static": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "wrappers": rows,
            "note": "the crontab is on the host: `python3 schedule-graph.py --write` there joins these to their minutes"}


def report(g):
    if g.get("static"):
        print("schedule graph (static; %d wrappers)" % len(g["wrappers"]))
        for r in g["wrappers"]:
            print("  %-32s owner %-32s organ %-20s gates %s" % (r["script"], r.get("owner", "?"), r.get("organ", "-"), ",".join(r["gates"]) or "-"))
        return
    print("schedule graph: %d jobs, %d owners, %d organs, %d overlapping pairs, %d unhandled" % (
        len(g["jobs"]), len(g["owners"]), len(g["organs"]), len(g["overlaps"]), len(g["unhandled"])))
    for j in g["jobs"]:
        print("  %-22s %-32s organ %-20s gates %-40s %s" % (j["schedule"], j["owner"], j["organ"] or "-", ",".join(j["gates"]) or "-", j.get("note", "")))
    for o in g["overlaps"]:
        print("  overlap %s + %s at %s (%d minutes/day): %s" % (o["a"], o["b"], o["first"], o["same_minute_count"], o["how"]))


def main(argv):
    if "--static" in argv:
        g = static_graph()
    else:
        if "--crontab" in argv:
            text = open(argv[argv.index("--crontab") + 1]).read()
        else:
            try:
                text = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
            except Exception:
                text = ""
        if not text.strip():
            print("no crontab readable here; --static for the wrappers alone", file=sys.stderr)
            g = static_graph()
        else:
            g = build(text)
    report(g)
    if "--write" in argv:
        os.makedirs(MEMORY, exist_ok=True)
        out = os.path.join(MEMORY, "schedule-graph.json")
        json.dump(g, open(out, "w"), indent=1)
        print("written", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
