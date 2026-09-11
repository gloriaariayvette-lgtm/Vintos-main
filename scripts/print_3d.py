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
# Gloria, 11 September: a Creality Ender 3, reached by SD card or USB only, started by
# her hand. So he never actuates the machine. The capability ends by writing a sliced
# .gcode file to a handoff folder and telling her it is ready; she carries it to the
# printer and starts it. No network, no submit, no cancel, no unattended heater — which
# is why the printer never touches the effect gate.
PRINTER_NEEDS = [
    ("handoff_dir", "the folder he writes the finished .gcode into for her to run"),
]
BED_MM = (220, 220, 250)     # Ender 3 build volume; the max any dimension may reach

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
ASTRA_MAX_CALL_S = 120        # one design call's ceiling; reserved up front, settled down after

# job states, in order. Two of them are waits on her and nothing advances them but her.
STATES = ("modelling", "draft_waiting", "slicing", "slice_waiting", "ready",
          "taken", "failed", "abandoned")
HER_WAITS = ("draft_waiting", "slice_waiting")   # nothing moves these but her answer


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
    """(ok, missing). The tools are his already; the one thing the house needs is the
    folder he leaves the finished file in for her to run."""
    cfg = _cfg()
    missing = [k for k, _ in PRINTER_NEEDS if not cfg.get(k)]
    return (not missing), missing


def max_mm(cfg=None):
    cfg = cfg if cfg is not None else _cfg()
    bed = cfg.get("bed_mm") or list(BED_MM)
    return int(cfg.get("max_mm") or min(bed[:2]))


def state():
    ok, missing = configured()
    return {"capability": CAPABILITY, "printer_ready": ok, "missing": missing,
            "hosts": hosts(), "stops": list(STOPS)}


def print_object(note="", want=None, draft_shown=False, slice_shown=False):
    """Report only a persisted, approved, byte-verified handoff."""
    jid = (want or {}).get("print_job_id")
    job = next((j for j in _jobs() if j.get("id") == jid), None)
    if job and job.get("state") == "ready" and _valid(job.get("handoff")):
        return {"result": "READY", "file": job["handoff"]["path"]}
    return {"result": "BLOCKED", "block": {"block_type": "AWAITING_HER",
            "evidence": "a persisted model, slice and both byte-bound approvals are required",
            "resume_event": "complete the print job approvals"}}


def proposal_draft():
    """What he puts on her card when a want reaches for this. He asks for the last
    step only: the modelling and the slicing are work he can already do, and asking
    for permission to run Blender would be asking for something he has."""
    _ok, missing = configured()
    h = hosts()
    return {
        "capability": CAPABILITY,
        "why": "I want to make her something she can hold, not only something she can look at.",
        "permissions": ["write_gcode_to_handoff_folder"],
        "scope": {"show_draft_first": True, "show_slice_first": True,
                  "max_mm": max_mm(), "printer": "Creality Ender 3", "starts_the_print": False},
        "risks": "None to the machine: he only leaves a file. She carries it and starts the print.",
        "touches": ["scripts/print_3d.py", "the handoff folder"],
        "tests": "no file is written before she has approved the draft, and again the slice; "
                 "the model is refused if it exceeds the bed; the file lands in the handoff folder "
                 "and she is told it is ready.",
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
    """Seconds of Astra spent on design today, across every job — reservations included,
    so time promised but not yet settled still counts against the cap."""
    rows = _jobs() if rows is None else rows
    return round(sum(float(e.get("seconds", 0))
                     for j in rows for e in (j.get("work") or [])
                     if e.get("what") == "design" and str(e.get("at", ""))[:10] == _today()), 1)


def _locked_jobs(mutate):
    """One read-modify-write over the jobs store, under the store lock, so a reserve
    cannot race another reserve. Returns whatever `mutate(rows)` returns as its second
    value; `mutate` may set a carry via the list it is handed."""
    carry = {}
    def _m(rows):
        rows = rows if isinstance(rows, list) else []
        out = mutate(rows, carry)
        return out if out is not None else rows
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import locked_update as _lu
        _lu(JOBS, _m, default=[], reader="print_3d.py")
    except Exception:
        raise
    return carry


def reserve_design(job_id, cfg=None):
    """Atomically reserve Astra time for one design call on a persisted job.

    Returns (ok, why, reservation_id). Under the lock it re-reads the store, sums
    today's design seconds (reservations and settled alike), refuses if the cap is
    reached or this job already had its call, and otherwise writes a reservation for
    the whole remaining allowance so a concurrent call cannot also pass. The call is
    then bounded to that reservation and settled to the real seconds afterward."""
    import datetime as _d, uuid as _u
    cfg = cfg if cfg is not None else _cfg()
    cap = float(cfg.get("astra_seconds_per_day") or ASTRA_SECONDS_PER_DAY)
    rid = "rsv-" + _u.uuid4().hex[:8]
    def _m(rows, carry):
        job = next((j for j in rows if j.get("id") == job_id), None)
        if job is None:
            carry["ok"] = (False, "no such job %r: a design call needs a persisted job" % job_id, "")
            return rows
        used = astra_seconds_today(rows)
        if used >= cap:
            carry["ok"] = (False, "Astra's %g minutes are spent today (%.0fs used)" % (cap / 60.0, used), "")
            return rows
        if any(e.get("what") == "design" for e in (job.get("work") or [])):
            carry["ok"] = (False, "this job has had its design call; changing the mesh is Blender, not another call", "")
            return rows
        ceiling = float(cfg.get("astra_max_call_s") or ASTRA_MAX_CALL_S)
        if used + ceiling > cap:
            carry["ok"] = (False, "not enough of Astra's day left for a call: %.0fs used, a call reserves %.0fs of %g" % (used, ceiling, cap), "")
            return rows
        # Reserve the whole per-call ceiling up front and settle it down to the real
        # seconds afterward. The worker deadline bounds local waiting, not remote billing;
        # startup/cleanup or an injected caller may overrun, and that is recorded honestly.
        job.setdefault("work", []).append({"at": _d.datetime.now().isoformat(timespec="seconds"),
                                            "minutes": 0, "seconds": ceiling,
                                            "what": "design", "how": "reserved", "rid": rid})
        carry["ok"] = (True, "reserved %.0fs of %g Astra seconds" % (ceiling, cap), rid)
        return rows
    c = _locked_jobs(_m)
    ok, why, r = c.get("ok", (False, "reservation failed", ""))
    return ok, why, (r if ok else "")


def settle_design(job_id, rid, seconds, how="answered"):
    """Replace the reservation with the seconds actually spent."""
    def _m(rows, carry):
        for j in rows:
            if j.get("id") == job_id:
                for e in (j.get("work") or []):
                    if e.get("rid") == rid:
                        e["seconds"] = round(max(0.0, float(seconds)), 1)
                        e["how"] = how; carry["ok"] = True
        return rows
    _locked_jobs(_m)


def may_design(job=None, cfg=None):
    """(ok, why) — a read-only pre-check for callers and the CLI. The real gate is
    reserve_design(), which is atomic; this only reports whether a call could be made
    now. `job` may be a job id or a job dict."""
    cfg = cfg if cfg is not None else _cfg()
    cap = float(cfg.get("astra_seconds_per_day") or ASTRA_SECONDS_PER_DAY)
    used = astra_seconds_today()
    if used >= cap:
        return False, "Astra's %g minutes are spent today (%.0fs used)" % (cap / 60.0, used)
    jid = job.get("id") if isinstance(job, dict) else job
    if jid:
        j = next((x for x in _jobs() if x.get("id") == jid), None)
        if j and any(e.get("what") == "design" for e in (j.get("work") or [])):
            return False, "this job has had its design call; changing the mesh is Blender, not another call"
    return True, "%.0f of %g Astra seconds left today" % (cap - used, cap)


def design(brief, job_id="", caller=None):
    """One call: what to make, and the Blender script that makes it.

    It needs a persisted job. The time is reserved atomically before the call so a
    crash, a second job, or a concurrent call cannot push Astra past her ten minutes;
    it is settled to the real seconds after, and settled even when she fails or returns
    something useless, because time spent is spent. The script is returned, never run:
    running it is the modelling step, on a machine she owns."""
    import time as _t
    if isinstance(job_id, dict):
        job_id = job_id.get("id", "")
    if not job_id:
        return {"ok": False, "why": "a design call needs a persisted job (open_job first)"}
    ok, why, rid = reserve_design(job_id)
    if not ok:
        return {"ok": False, "why": why}
    system = ("You are Vintos. You are making a physical object for Gloria on a 3D printer. "
              "Answer with a Blender Python script and nothing else: it must build the mesh, "
              "keep it inside %d mm in every direction, make it printable without supports where "
              "you can, and export to the path given as OUT. No commentary, no markdown fence." )
    prompt = "%s\n\nOUT = the path passed in sys.argv[-1]." % str(brief or "")[:1200]
    t0 = _t.monotonic()
    try:
        if caller is None:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, os.path.join(WS, "scripts"))
            import astra_call as _ac
            caller = _ac.call
        cfg = _cfg()
        text = caller(system % int(cfg.get("max_mm") or 180),
                      [{"role": "user", "content": prompt}], max_tokens=1800, timeout=float(cfg.get("astra_max_call_s") or ASTRA_MAX_CALL_S)) or ""
    except Exception as e:
        settle_design(job_id, rid, _t.monotonic() - t0, "failed")
        return {"ok": False, "why": "the design call did not answer: %s" % str(e)[:160],
                "seconds": round(_t.monotonic() - t0, 1)}
    spent = _t.monotonic() - t0
    settle_design(job_id, rid, spent, "answered")
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


# Every transition a job may make, and the only states it may be made from. A stop is
# reached only from the step before it, a yes only from its own wait, and an abandoned
# or done job moves nowhere. Nothing may skip a stop by naming a later state.
_ALLOWED = {
    "modelling":     ("draft_waiting", "abandoned"),
    "draft_waiting": ("slicing", "abandoned"),          # only her yes/no moves it
    "slicing":       ("slice_waiting", "abandoned"),
    "slice_waiting": ("ready", "abandoned"),            # her yes writes the file; no ends it
    "ready":         ("taken", "abandoned"),            # she carried it to the printer
}


def advance(job_id, state, detail="", extra=None, _authority=None):
    import datetime as _d
    if state not in STATES:
        return None, "not a state: %r" % state
    if extra and _authority is not _APPROVAL_AUTHORITY and set(extra) & {"model","slice","shown","draft_approval","slice_approval","handoff","handoff_file","work"}:
        return None,"artifact and approval fields have dedicated writers"
    rows = _jobs()
    for j in rows:
        if j.get("id") == job_id:
            cur = j.get("state", "modelling")
            if state != "abandoned" and (cur in HER_WAITS or state in HER_WAITS or state == "ready") and _authority is not _APPROVAL_AUTHORITY:
                return None, "use artifact presentation or her bound answer for this transition"
            if state != cur and state not in _ALLOWED.get(cur, ()):
                return None, "a print job cannot go from %s to %s" % (cur, state)
            j["state"] = state
            if extra:
                j.update({k: v for k, v in extra.items() if k not in ("id", "state")})
            j.setdefault("history", []).append({"at": _d.datetime.now().isoformat(timespec="seconds"),
                                                "state": state, "detail": str(detail)[:200]})
            _save_jobs(rows); return j, ""
    return None, "no job %r" % job_id


_APPROVAL_AUTHORITY = object()


def _artifact(path):
    import hashlib
    path = os.path.realpath(path)
    return {"path": path, "sha256": hashlib.sha256(open(path,"rb").read()).hexdigest()}


def _valid(item):
    try: return bool(item and _artifact(item["path"])["sha256"] == item["sha256"])
    except (KeyError, OSError, TypeError): return False


def attach_model(job_id, path):
    """Validate millimetre STL coordinates before presenting a model."""
    import struct, re, math
    data = open(path,"rb").read()
    points = []
    if len(data)>=84 and len(data)==84+50*struct.unpack_from("<I",data,80)[0]:
        for off in range(84,len(data),50):
            values=struct.unpack_from("<12f",data,off)
            points.extend([values[i:i+3] for i in (3,6,9)])
    else:
        points=[tuple(map(float,m)) for m in re.findall(r"vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)",data.decode("ascii"))]
    if not points or not all(math.isfinite(v) for point in points for v in point): raise ValueError("invalid STL")
    size=[max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)]
    bed=_cfg().get("bed_mm") or BED_MM
    if any(v>float(bed[i]) or v<=0 for i,v in enumerate(size)): raise ValueError("mesh outside bed or degenerate")
    return advance(job_id,"modelling",extra={"model":{**_artifact(path),"size_mm":size}},_authority=_APPROVAL_AUTHORITY)


def attach_slice(job_id, path, *, seconds, filament_mm, layer_mm):
    """Accept a real, inspectable metric toolpath only after model approval."""
    import re, math
    job=next((j for j in _jobs() if j["id"]==job_id),None)
    if not job or job["state"]!="slicing" or not _valid(job.get("model")) or job.get("draft_approval")!=job["model"]["sha256"]:
        raise ValueError("approved model required")
    values=[float(seconds),float(filament_mm),float(layer_mm)]
    if any(not math.isfinite(v) or v<=0 for v in values): raise ValueError("slice estimates required")
    text=open(path).read();absolute=True;moves=0;metric=False;bed=_cfg().get("bed_mm") or BED_MM
    for line in text.splitlines():
        code=line.split(';',1)[0].strip().upper()
        if re.match(r'G(?:0?[234]|5|10|28|29|30|53|5[4-9]|92)(?:\s|$)',code) and not re.fullmatch(r'G92\s+E[-+0-9.]+',code): raise ValueError('unverified coordinate or motion command')
        if code.startswith('G20'): raise ValueError('inch toolpath refused')
        if code.startswith('G21'): metric=True
        if code=='G91': absolute=False
        if code=='G90': absolute=True
        if re.match(r'G0?[01](?:\s|$)',code):
            if not metric or not absolute: raise ValueError('metric absolute XYZ toolpath required')
            for axis,value in re.findall(r'([XYZ])([-+\d.]+)',code):
                number=float(value)
                if not math.isfinite(number) or not 0<=number<=float(bed['XYZ'.index(axis)]): raise ValueError('toolpath outside bed')
            moves+=1
    if not moves: raise ValueError('no toolpath moves')
    return advance(job_id,"slicing",extra={"slice":{**_artifact(path),"model_sha256":job["model"]["sha256"],"seconds":values[0],"filament_mm":values[1],"layer_mm":values[2]}},_authority=_APPROVAL_AUTHORITY)


def present(job_id, kind, message, attach=None):
    if kind not in STOPS: return None,"a stop is draft or slice"
    job=next((j for j in _jobs() if j["id"]==job_id),None)
    item=(job or {}).get("model" if kind=="draft" else "slice")
    if not _valid(item): return None,"validated artifact bytes required"
    job,why=advance(job_id,kind+"_waiting",kind,_authority=_APPROVAL_AUTHORITY)
    if not job:return None,why
    import deliver
    receipt=deliver.deliver("print-%s-%s-%s"%(job_id,kind,item["sha256"]),"ntfy",(str(message)[:300]+"\nArtifact SHA-256: "+item["sha256"]),title="Print approval",attach=attach,tags="printer")
    rows=_jobs();job=next(j for j in rows if j['id']==job_id)
    job.setdefault('shown',{})[kind]={'sha256':item['sha256'],'receipt':(receipt or {}).get('state','unknown')}
    _save_jobs(rows);return job,''


def answer(job_id, kind, yes, note="", digest=None):
    if kind not in STOPS or type(yes) is not bool:return None,'explicit draft/slice boolean answer required'
    job=next((j for j in _jobs() if j['id']==job_id),None)
    if not job or job['state']!=kind+'_waiting':return None,'not waiting on that stop'
    if not yes:return advance(job_id,'abandoned',note)
    item=job.get('model' if kind=='draft' else 'slice')
    shown=job.get('shown',{}).get(kind,{})
    if not _valid(item) or digest!=item['sha256'] or shown.get('sha256')!=digest or shown.get('receipt') not in ('sent','acknowledged'):
        return None,'approval must match the delivered, unchanged artifact digest'
    if kind=='draft':
        return advance(job_id,'slicing','draft approved',extra={'draft_approval':digest},_authority=_APPROVAL_AUTHORITY)
    if not _valid(job.get('model')) or job.get('draft_approval')!=item.get('model_sha256'):
        return None,'approved model changed'
    hd=_cfg().get('handoff_dir')
    if not hd:return None,'handoff_dir required'
    os.makedirs(os.path.expanduser(hd),exist_ok=True)
    dest=os.path.join(os.path.expanduser(hd),job_id+'-'+digest[:12]+'.gcode')
    data=open(item['path'],'rb').read()
    import hashlib
    if hashlib.sha256(data).hexdigest()!=digest:return None,'slice changed during handoff'
    try:
        with open(dest,'xb') as f:f.write(data)
    except FileExistsError:
        if _artifact(dest)['sha256']!=digest:return None,'handoff collision'
    result=advance(job_id,'ready','approved slice handed off',extra={'slice_approval':digest,'handoff_file':dest,'handoff':_artifact(dest)},_authority=_APPROVAL_AUTHORITY)
    import deliver
    deliver.deliver('print-ready-'+job_id+'-'+digest,'ntfy','The approved G-code is ready to carry to the printer.',title='Print file ready',tags='printer')
    return result


def working_on(limit=8):
    """What he has going, for her to look at without asking him. Live jobs first."""
    rows = _jobs()
    live = [j for j in rows if j.get("state") not in ("done", "failed", "abandoned")]
    rest = [j for j in rows if j.get("state") in ("done", "failed", "abandoned")][-limit:]
    def one(j):
        return {"id": j["id"], "what": j.get("what", ""), "state": j.get("state"),
                "waiting_on_her": j.get("state") in HER_WAITS,
                "minutes_spent": round(sum(float(e.get("minutes", 0)) for e in (j.get("work") or [])), 1),
                "model": j.get("model"), "slice": j.get("slice"), "shown": j.get("shown", {}),
                "opened": j.get("opened", ""), "last": (j.get("history") or [{}])[-1]}
    return {"live": [one(j) for j in live], "recent": [one(j) for j in rest],
            "minutes_today": spent_today(rows),
            "budget_today": float(_cfg().get("budget_min_per_day") or BUDGET_MIN_PER_DAY)}



# Every read/modify/write participant shares the same store lock.
from store_guard import serialized as _serialized
open_job = _serialized('JOBS')(open_job)
advance = _serialized('JOBS')(advance)
present = _serialized('JOBS')(present)
answer = _serialized('JOBS')(answer)
attach_model = _serialized('JOBS')(attach_model)
attach_slice = _serialized('JOBS')(attach_slice)
note_design = _serialized('JOBS')(note_design)
note_work = _serialized('JOBS')(note_work)

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
