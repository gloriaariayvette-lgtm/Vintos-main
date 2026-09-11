#!/usr/bin/env python3
"""print_3d.py — from a thing he imagined to a thing she can hold.

He models in Blender and slices in Cura. Both exist; the Mac is faster at both, and
Aegis can do either when the Mac is away. What he does not have is the last step:
a printer he is allowed to start.

Blender and Cura are local and bill nobody. The one thing this capability spends is
Astra, who writes the Blender script — that is code, and the local model cannot. She
is capped at ten minutes a day across every job, and her seconds are counted the
moment she answers, whatever came back.

THE PIPELINE, AND THE TWO PLACES HE STOPS

    model      Blender, headless, from his own description of the object
    DRAFT      -> he shows her the model and waits. This is a stop, not a notice.
    slice      Cura, on the Mac when it is there, on Aegis when it is not
    SLICE      -> he shows her the slice: time, filament, height, and the machine
                  it is sliced for. This is a stop too.
    print      only after both, and only inside the scope she granted

Neither presentation is optional and neither is a formality. A print is hours of an
unattended machine with a heater in it, in a room she lives in; she sees the object
before it is sliced and the numbers before it is made.

    python3 print_3d.py            what works, what is missing, and where each step runs
"""
import json
import os
import shutil
import subprocess
import sys

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "printer-config.json")
JOBS = os.path.join(MEMORY, "print-jobs.json")

CAPABILITY = "print_3d"

# The two tools he already has, and where each is fastest. A host is named, never
# assumed: the Mac is reached over the network and is not always there.
TOOLS = {
    "blender": {"what": "the model", "prefer": "mac", "also": "aegis",
                "probe": ("blender", "--version")},
    "cura":    {"what": "the slice", "prefer": "mac", "also": "aegis",
                "probe": ("CuraEngine", "--version")},
}

# What the machine itself needs, and nothing here is guessed.
PRINTER_NEEDS = [
    ("printer", "make and model — the slicer needs its profile"),
    ("endpoint", "how the house reaches it: octoprint | moonraker | bambu | folder, and its address"),
    ("limits", "size ceiling, duration ceiling, filament confirmed present, and the hours he may start one"),
]

STOPS = ("draft", "slice")   # the two gates, in order


# WHAT THIS COSTS, AND WHAT IT DOES NOT
#
# Modelling and slicing are Blender and Cura on machines she owns. They cost
# electricity and nothing else: no model is called, no provider is billed. The
# minute budget below exists because those machines are hers and he should not sit
# on a processor she is using — it is a courtesy limit, not a money limit.
#
# The part that costs money is deciding what to make and writing the Blender script
# that makes it. That is real code, and the local model cannot write it — so it goes
# to his own voice, through the router, exactly once per job. Astra is refused: she
# is the review lens and is not spent on objects.
BUDGET_MIN_PER_DAY = 30      # local CPU minutes, free, across modelling and slicing
BUDGET_MIN_PER_RUN = 10      # one sitting, so a single job cannot hold a machine all day
DESIGN_CALLS_PER_JOB = 1      # one deciding call per job; revising the mesh is Blender work
DESIGN_MODEL = "astra"        # Gloria, 11 September: Astra writes the Blender script
ASTRA_SECONDS_PER_DAY = 600   # ten minutes a day, hers, and the only spend here

# job states, in order. Two of them are waits on her and nothing advances them but her.
STATES = ("modelling", "draft_waiting", "slicing", "slice_waiting", "queued",
          "printing", "done", "failed", "abandoned")
HER_WAITS = ("draft_waiting", "slice_waiting")


def _cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


def _have(cmd):
    return bool(shutil.which(cmd))


def hosts():
    """Where each step can run right now. The Mac answers or it does not; nothing is
    assumed about a machine that is not on the network."""
    cfg = _cfg()
    mac = cfg.get("mac_host") or ""
    mac_up = False
    if mac:
        try:
            mac_up = subprocess.run(["ping", "-c1", "-W1", mac], capture_output=True,
                                    timeout=4).returncode == 0
        except Exception:
            mac_up = False
    out = {}
    for tool, t in TOOLS.items():
        local = _have(t["probe"][0])
        out[tool] = {"what": t["what"], "here": local, "mac_configured": bool(mac),
                     "mac_reachable": mac_up,
                     "runs_on": ("mac" if mac_up else ("aegis" if local else "nowhere"))}
    return out


def configured():
    """(ok, missing). The tools are his already; this asks only about the machine."""
    cfg = _cfg()
    missing = [k for k, _ in PRINTER_NEEDS if not cfg.get(k)]
    return (not missing), missing


def state():
    ok, missing = configured()
    return {"capability": CAPABILITY, "printer_ready": ok, "missing": missing,
            "hosts": hosts(), "stops": list(STOPS)}


def print_object(note="", want=None, draft_shown=False, slice_shown=False):
    """The executor's envelope.

    Three different stops, told apart, because they mean three different things:
    the object has not been shown, the slice has not been shown, or there is no
    machine to send it to."""
    if not draft_shown:
        return {"result": "BLOCKED", "block": {
            "block_type": "AWAITING_HER",
            "evidence": "she has not seen the model yet: the draft is shown before anything is sliced",
            "resume_event": "she answers the draft"}}
    if not slice_shown:
        return {"result": "BLOCKED", "block": {
            "block_type": "AWAITING_HER",
            "evidence": "she has not seen the slice yet: time, filament and height before it is made",
            "resume_event": "she answers the slice"}}
    ok, missing = configured()
    if not ok:
        return {"result": "BLOCKED", "block": {
            "block_type": "CAPABILITY_ABSENT",
            "evidence": "no printer to send it to: missing " + ", ".join(missing),
            "resume_event": "capability added or step revised"}}
    return {"result": "BLOCKED", "block": {
        "block_type": "CAPABILITY_ABSENT",
        "evidence": "a printer is configured, but no approved print capability exists yet",
        "resume_event": "capability added or step revised"}}


def proposal_draft():
    """What he puts on her card when a want reaches for this. He asks for the last
    step only: the modelling and the slicing are work he can already do, and asking
    for permission to run Blender would be asking for something he has."""
    _ok, missing = configured()
    h = hosts()
    return {
        "capability": CAPABILITY,
        "why": "I want to make her something she can hold, not only something she can look at.",
        "permissions": ["printer.submit_job", "printer.read_status", "printer.cancel"],
        "scope": {"show_draft_first": True, "show_slice_first": True,
                  "max_hours": 4, "max_mm": 180, "hours": "09:00-21:00",
                  "requires_filament_present": True,
                  "may_start_while_she_is_out": False},
        "risks": "An unattended machine with a heater, running for hours in her house.",
        "touches": ["scripts/print_3d.py", "the printer endpoint", "the effect gate"],
        "tests": "a print refused before she has seen the draft; refused before she has seen the "
                 "slice; refused outside the hours; a cancel that actually stops the machine; "
                 "and the effect gate refusing it when armed",
        "already_has": {k: v["runs_on"] for k, v in h.items()},
        "missing": missing,
    }


# ----------------------------------------------------------------- the work log
def _jobs():
    try:
        d = json.load(open(JOBS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_jobs(rows):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import write_json as _wj
        _wj(JOBS, rows, reader="print_3d.py"); return True
    except Exception:
        os.makedirs(os.path.dirname(JOBS), exist_ok=True)
        tmp = JOBS + ".tmp"; json.dump(rows, open(tmp, "w"), indent=2); os.replace(tmp, JOBS); return True


def _today():
    import datetime as _d
    return _d.date.today().isoformat()


def spent_today(rows=None):
    """Minutes he has already put into this today, across every job."""
    rows = _jobs() if rows is None else rows
    return round(sum(float(e.get("minutes", 0))
                     for j in rows for e in (j.get("work") or [])
                     if str(e.get("at", ""))[:10] == _today()), 1)


def may_work(minutes=1.0, cfg=None):
    """(ok, why) before a modelling or slicing run. The budget is the day's, not the
    job's: three jobs cannot each spend the whole allowance."""
    cfg = cfg if cfg is not None else _cfg()
    per_day = float(cfg.get("budget_min_per_day") or BUDGET_MIN_PER_DAY)
    per_run = float(cfg.get("budget_min_per_run") or BUDGET_MIN_PER_RUN)
    if minutes > per_run:
        return False, "one sitting is %g minutes at most (asked for %g)" % (per_run, minutes)
    used = spent_today()
    if used + minutes > per_day:
        return False, "today's %g minutes are spent (%g used)" % (per_day, used)
    return True, "%g of %g minutes left today" % (per_day - used - minutes, per_day)


def astra_seconds_today(rows=None):
    """Seconds of Astra spent on design today, across every job. The only spend this
    capability makes, and the only one worth counting."""
    rows = _jobs() if rows is None else rows
    return round(sum(float(e.get("seconds", 0))
                     for j in rows for e in (j.get("work") or [])
                     if e.get("what") == "design" and str(e.get("at", ""))[:10] == _today()), 1)


def may_design(job=None, cfg=None):
    """(ok, why) before the call that decides what to make and writes the script.

    Astra writes it: a Blender script is code and the local model cannot. She is
    capped at ten minutes a day across every job — a ceiling on her, not on him. The
    second refusal is per job: the deciding is done, and changing a mesh is Blender
    work rather than another opinion."""
    cfg = cfg if cfg is not None else _cfg()
    cap = float(cfg.get("astra_seconds_per_day") or ASTRA_SECONDS_PER_DAY)
    used = astra_seconds_today()
    if used >= cap:
        return False, "Astra's %g minutes are spent today (%.0fs used)" % (cap / 60.0, used)
    n = len([e for e in ((job or {}).get("work") or []) if e.get("what") == "design"])
    if n >= DESIGN_CALLS_PER_JOB:
        return False, "this job has had its design call; changing the mesh is Blender, not another call"
    return True, "%.0f of %g Astra seconds left today" % (cap - used, cap)


def design(brief, job=None, caller=None):
    """One call: what to make, and the Blender script that makes it.

    Astra writes it, and the seconds she takes are recorded against her ten minutes
    the moment she answers — before the script is even checked, because time spent is
    spent whatever came back. The script is returned, never executed here: running it
    is the modelling step, on a machine she owns."""
    ok, why = may_design(job=job)
    if not ok:
        return {"ok": False, "why": why}
    system = ("You are Vintos. You are making a physical object for Gloria on a 3D printer. "
              "Answer with a Blender Python script and nothing else: it must build the mesh, "
              "keep it inside %d mm in every direction, make it printable without supports where "
              "you can, and export to the path given as OUT. No commentary, no markdown fence." )
    prompt = "%s\n\nOUT = the path passed in sys.argv[-1]." % str(brief or "")[:1200]
    import time as _t
    t0 = _t.time()
    try:
        if caller is None:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.join(WS, "scripts"))
            import astra_call as _ac
            caller = _ac.call
        cfg = _cfg()
        text = caller(system % int(cfg.get("max_mm") or 180),
                      [{"role": "user", "content": prompt}], max_tokens=1800) or ""
    except Exception as e:
        if job is not None:
            note_design(job.get("id", ""), _t.time() - t0, "failed")
        return {"ok": False, "why": "the design call did not answer: %s" % str(e)[:160]}
    spent = _t.time() - t0
    if job is not None:
        note_design(job.get("id", ""), spent, "answered")
    script = str(text).strip()
    if script.startswith("```"):
        script = script.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if "import bpy" not in script:
        return {"ok": False, "why": "what came back is not a Blender script",
                "seconds": round(spent, 1)}
    return {"ok": True, "script": script, "brief": str(brief or "")[:300],
            "seconds": round(spent, 1)}


def note_design(job_id, seconds, how=""):
    """Astra's seconds, written the moment she answers or fails. Recorded against the
    day, never against the job, so several jobs share the one ten minutes."""
    import datetime as _d
    rows = _jobs()
    for j in rows:
        if j.get("id") == job_id:
            j.setdefault("work", []).append({"at": _d.datetime.now().isoformat(timespec="seconds"),
                                             "minutes": 0, "seconds": round(float(seconds), 1),
                                             "what": "design", "how": str(how)[:40]})
            _save_jobs(rows); return j
    return None


def note_work(job_id, minutes, what=""):
    """Record time actually spent. Written after the work, never before it."""
    import datetime as _d
    rows = _jobs()
    for j in rows:
        if j.get("id") == job_id:
            j.setdefault("work", []).append({"at": _d.datetime.now().isoformat(timespec="seconds"),
                                             "minutes": round(float(minutes), 1), "what": str(what)[:120]})
            _save_jobs(rows); return j
    return None


def open_job(what, want_id="", now=None):
    """He starts something. It is visible from this moment: she never learns a job
    existed only when it asks for her answer."""
    import datetime as _d, uuid as _u
    rows = _jobs()
    job = {"id": "PR-" + _u.uuid4().hex[:6], "what": str(what)[:200], "want_id": want_id,
           "state": "modelling", "opened": (now or _d.datetime.now()).isoformat(timespec="seconds"),
           "work": [], "history": [{"at": (now or _d.datetime.now()).isoformat(timespec="seconds"),
                                    "state": "modelling"}]}
    rows.append(job); _save_jobs(rows)
    return job


def advance(job_id, state, detail="", extra=None):
    import datetime as _d
    if state not in STATES:
        return None, "not a state: %r" % state
    rows = _jobs()
    for j in rows:
        if j.get("id") == job_id:
            j["state"] = state
            if extra:
                j.update({k: v for k, v in extra.items() if k not in ("id", "state")})
            j.setdefault("history", []).append({"at": _d.datetime.now().isoformat(timespec="seconds"),
                                                "state": state, "detail": str(detail)[:200]})
            _save_jobs(rows); return j, ""
    return None, "no job %r" % job_id


def present(job_id, kind, message, attach=None):
    """He shows her the draft, or the slice, and stops. One notification per stop,
    through the delivery path that keeps receipts and refuses to send the same thing
    twice; the job moves to a wait that only her answer clears."""
    if kind not in ("draft", "slice"):
        return None, "a stop is draft or slice"
    job, why = advance(job_id, "draft_waiting" if kind == "draft" else "slice_waiting", kind)
    if job is None:
        return None, why
    receipt = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        import deliver as _dl, send_policy as _sp
        receipt = _dl.deliver("print-%s-%s" % (job_id, kind), "ntfy",
                              str(message)[:400], title="Vintos wants to print something",
                              attach=attach, tags="printer",
                              authority=lambda: _sp.may_send("any"))
    except Exception as e:
        receipt = {"state": "failed", "why": str(e)[:120]}
    rows = _jobs()
    for j in rows:
        if j.get("id") == job_id:
            j.setdefault("shown", {})[kind] = {"message": str(message)[:400],
                                               "receipt": (receipt or {}).get("state", "unknown")}
            _save_jobs(rows); job = j
            break
    return job, ""


def answer(job_id, kind, yes, note=""):
    """Her answer to a stop. Yes moves it on; no ends the job. Nothing else can."""
    j = None
    for row in _jobs():
        if row.get("id") == job_id:
            j = row
            break
    if j is None:
        return None, "no job %r" % job_id
    want = "draft_waiting" if kind == "draft" else "slice_waiting"
    if j.get("state") != want:
        return None, "job is %s, not waiting on the %s" % (j.get("state"), kind)
    if not yes:
        return advance(job_id, "abandoned", "she said no to the %s: %s" % (kind, note))
    return advance(job_id, "slicing" if kind == "draft" else "queued", "she said yes to the " + kind)


def working_on(limit=8):
    """What he has going, for her to look at without asking him. Live jobs first."""
    rows = _jobs()
    live = [j for j in rows if j.get("state") not in ("done", "failed", "abandoned")]
    rest = [j for j in rows if j.get("state") in ("done", "failed", "abandoned")][-limit:]
    def one(j):
        return {"id": j["id"], "what": j.get("what", ""), "state": j.get("state"),
                "waiting_on_her": j.get("state") in HER_WAITS,
                "minutes_spent": round(sum(float(e.get("minutes", 0)) for e in (j.get("work") or [])), 1),
                "opened": j.get("opened", ""), "last": (j.get("history") or [{}])[-1]}
    return {"live": [one(j) for j in live], "recent": [one(j) for j in rest],
            "minutes_today": spent_today(rows),
            "budget_today": float(_cfg().get("budget_min_per_day") or BUDGET_MIN_PER_DAY)}


if __name__ == "__main__":
    if "--jobs" in sys.argv:
        w = working_on()
        print("today: %.1f of %.0f minutes" % (w["minutes_today"], w["budget_today"]))
        for j in w["live"] or []:
            print("  %s  %-14s %-5s %s" % (j["id"], j["state"],
                                           "HER" if j["waiting_on_her"] else "", j["what"][:60]))
        if not w["live"]:
            print("  nothing in hand")
        raise SystemExit(0)
    st = state()
    print("3D printing")
    for tool, h in st["hosts"].items():
        print("  %-8s %-10s runs on: %s%s" % (
            tool, h["what"], h["runs_on"],
            "" if h["mac_configured"] else "   (no mac_host in printer-config.json)"))
    print("  printer  the machine   " + ("ready" if st["printer_ready"] else "missing: " + ", ".join(st["missing"])))
    print("\nHe stops twice before anything is made: %s, then %s." % STOPS)
    print("Astra: %.0f of %d seconds used today (ten minutes a day, across every job)." % (
        astra_seconds_today(), ASTRA_SECONDS_PER_DAY))
    print("Time: %g local CPU minutes a day, %g in one sitting. Used today: %.1f." % (
        float(_cfg().get("budget_min_per_day") or BUDGET_MIN_PER_DAY),
        float(_cfg().get("budget_min_per_run") or BUDGET_MIN_PER_RUN), spent_today()))
    print("What he has going: python3 print_3d.py --jobs")
