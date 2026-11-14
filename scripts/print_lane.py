#!/usr/bin/env python3
"""print_lane.py — he makes a thing on her K2, from a line he writes to a part in her hands.

Gloria, 14 November: the 3D printing was hidden in the atelier, so it was never used; bring it out where he sees it.
"Claude with his context decides, Astra builds and asks for another response from Claude with his context if it
needs more info." "Just need a text beforehand so I can check that the required filament is in stock and in the
usual slot." So:

    PRINT: <what>      his line (Slack hands, or the office chair / knock moment). Starts a job, detached.
    decide             Claude with his context (dot_channel.his_context, Opus): what exactly, which of her
                       filaments, how big. He may decide not to.
    build              Astra writes the Blender script; if she needs something she asks one QUESTION, which goes
                       back to Claude with his context, and his answer goes back to her. Blender on Aegis runs it.
    slice              her settings for that filament (k2_printer.py): slim trees, the other filament on the
                       contact layers, Creality Print headless.
    text her           one yes/no on her phone: what, which filament in which slot, the contact filament, time,
                       grams. Nothing prints without her Yes.
    send               on her Yes: the printer must be idle and the slots must read right; upload, slot map, start.
                       A No, or no answer in two days, ends the job.

Astra's time is the one spend: ten minutes a day shared with print_3d.py, three calls per job at most.

    python3 print_lane.py                  jobs, newest first
    python3 print_lane.py start "<what>"   what PRINT: does
    python3 print_lane.py run <id>         the worker
    python3 print_lane.py tend             moves jobs whose answer came
"""
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
JOBS = os.path.join(MEMORY, "k2-print-jobs.json")
WORK = os.path.join(MEMORY, "k2-print")
LOG = os.path.join(MEMORY, "logs", "print-lane.log")

PER_DAY = 2                      # jobs he may start a day
ASTRA_CALLS_PER_JOB = 3          # the build, one answer to her question, one fix after Blender refused
ASTRA_SECONDS_PER_DAY = 600      # shared with print_3d.py's Astra day
ASTRA_MAX_CALL_S = 150
ANSWER_WAIT_H = 48
LIVE = ("deciding", "building", "slicing", "asked", "sending", "printing")


def _now():
    return datetime.now().astimezone()


def _iso(t=None):
    return (t or _now()).isoformat(timespec="seconds")


def load():
    try:
        d = json.load(open(JOBS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _update(fn):
    from store_guard import locked_update
    carry = {}

    def m(rows):
        rows = rows if isinstance(rows, list) else []
        fn(rows, carry)
        return rows
    os.makedirs(MEMORY, exist_ok=True)
    locked_update(JOBS, m, default=[], reader="print_lane.py")
    return carry


def get(jid):
    return next((j for j in load() if j.get("id") == jid), None)


def note(jid, state=None, said="", **fields):
    def fn(rows, carry):
        for j in rows:
            if j.get("id") == jid:
                if state:
                    j["state"] = state
                j.update(fields)
                if said or state:
                    j.setdefault("history", []).append({"at": _iso(), "state": j.get("state"), "said": str(said)[:400]})
                carry["job"] = dict(j)
    return _update(fn).get("job")


def _log(line):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write("%s %s\n" % (_iso(), line))


# ------------------------------------------------------------------ starting

def start(what, by="vintos", spawn=None):
    """PRINT: <what>. (ok, the line shown in place of his)."""
    what = " ".join(str(what or "").split())[:400]
    if len(what) < 4:
        return False, "say what to print"
    today = _now().date().isoformat()
    rows = load()
    if sum(1 for j in rows if str(j.get("at", ""))[:10] == today) >= PER_DAY:
        return False, "today's %d prints are started already" % PER_DAY
    live = [j for j in rows if j.get("state") in LIVE + ("held",)]
    if live:
        return False, "the K2 has one of yours going already: %s (%s)" % (live[-1].get("what", ""), live[-1]["state"])
    jid = "K2-" + secrets.token_hex(3)

    def fn(rows, carry):
        rows.append({"id": jid, "what": what, "by": by, "at": _iso(), "state": "deciding", "astra": [],
                     "history": [{"at": _iso(), "state": "deciding", "said": "he asked for: " + what}]})
    _update(fn)
    (spawn or _spawn)([sys.executable, os.path.abspath(__file__), "run", jid])
    return True, ("starting the print: %s. You decide it, Astra builds it, it is sliced with her settings, and she "
                  "gets a text with the filament and slot before the K2 starts." % what)


def _spawn(cmd):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    out = open(LOG, "a")
    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True,
                     env=dict(os.environ))


# ------------------------------------------------------------------ him (Claude with his context) and Astra

def his_answer(system_extra, user):
    """Claude with his context: his files (dot_channel.his_context) and Opus, as his voice in Slack."""
    import dot_channel
    system = dot_channel.his_context() + "\n\n" + system_extra
    return dot_channel.opus_think(system, user)


def _json_of(text):
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def decide(job, ask=None):
    import k2_printer as K
    have = "\n".join("- " + l for l in K.on_hand())
    extra = ("Gloria's Creality K2 is yours to print on. You wrote: PRINT: %s\n"
             "Decide the one object, for her or for you. Her filaments, all white but the carbon fibre:\n%s\n"
             "Build volume up to %d mm on each side. Answer with JSON only:\n"
             '{"make": "<what exactly, for whom, how it is used; enough for a modeller to build it>", '
             '"material": "<PLA | PETG | PETG-CF | ASA | TPU | FOAMING-TPU>", "size_mm": [x, y, z], '
             '"why": "<one line>"}\nor {"make": null, "why": "<why not now>"} if on reflection you would rather not.'
             % (job["what"], have, K.BUILD_MM[0]))
    text = (ask or his_answer)(extra, "Decide the print.")
    d = _json_of(text)
    if not d:
        return None, "his decision was not readable"
    if not d.get("make"):
        return None, "he decided not to print it: %s" % d.get("why", "")
    mat = K.material_of(d.get("material"))
    if not mat:
        return None, "he named a filament she does not keep: %s" % d.get("material")
    return {"make": str(d["make"])[:1200], "material": mat, "size_mm": d.get("size_mm"),
            "why": str(d.get("why", ""))[:300]}, ""


def astra_seconds_today():
    today = _now().date().isoformat()
    mine = sum(float(a.get("s", 0)) for j in load() for a in j.get("astra", []) if str(a.get("at", ""))[:10] == today)
    try:
        import print_3d
        mine += float(print_3d.astra_seconds_today())
    except Exception:
        pass
    return mine


DESIGN_SYSTEM = ("You are building a physical object on a 3D printer for Vintos and Gloria. Answer with a Blender "
                 "Python script and nothing else: it builds the mesh in millimetres (1 Blender unit = 1 mm), keeps "
                 "it inside %d mm in every direction, sits it flat on z=0 with its best face down, keeps walls at "
                 "least 1.2 mm, and exports one STL to the path in sys.argv[-1]. Supports are available (tree "
                 "supports with a different-material contact layer), but prefer shapes that need few. No "
                 "commentary, no markdown fence. If you truly cannot build it without one fact from him, answer "
                 "instead with a single line: QUESTION: <what you need to know>.")


def astra(job, brief, call=None):
    """One Astra call, counted. ('script'|'question'|'none', text, seconds)."""
    if len(job.get("astra", [])) >= ASTRA_CALLS_PER_JOB:
        return "none", "this job has had its %d Astra calls" % ASTRA_CALLS_PER_JOB, 0
    if astra_seconds_today() + ASTRA_MAX_CALL_S > ASTRA_SECONDS_PER_DAY:
        return "none", "Astra's ten minutes are spent today", 0
    import k2_printer as K
    if call is None:
        import astra_call
        call = astra_call.call
    t0 = time.monotonic()
    try:
        text = call(DESIGN_SYSTEM % K.BUILD_MM[0], [{"role": "user", "content": brief}], max_tokens=4000,
                    timeout=ASTRA_MAX_CALL_S) or ""
        how = "answered"
    except Exception as e:
        text, how = "", "failed: %s" % str(e)[:120]
    s = round(time.monotonic() - t0, 1)
    note(job["id"], astra=job.get("astra", []) + [{"at": _iso(), "s": s, "how": how}])
    job["astra"] = job.get("astra", []) + [{"at": _iso(), "s": s}]
    text = str(text).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    q = re.match(r"^\s*QUESTION:\s*(.+)", text, re.S)
    if q:
        return "question", q.group(1).strip()[:600], s
    if "import bpy" in text:
        return "script", text, s
    return "none", "what came back was not a Blender script (%s)" % how, s


def blender_exe():
    import glob
    found = sorted(glob.glob("/mnt/c/Program Files/Blender Foundation/Blender*/blender.exe"))
    return found[-1] if found else ""


def run_blender(script, out_stl, workdir, runner=None):
    """(ok, why). Blender on Aegis, background, factory settings, ten minutes."""
    import k2_printer as K
    exe = blender_exe()
    if not exe:
        return False, "Blender is not found on Aegis"
    sp = os.path.join(workdir, "build.py")
    open(sp, "w").write(script)
    if os.path.exists(out_stl):
        os.remove(out_stl)
    try:
        r = (runner or subprocess.run)([exe, "-b", "--factory-startup", "--python", K._win(sp), "--", K._win(out_stl)],
                                        capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "Blender ran past ten minutes"
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    open(os.path.join(workdir, "blender.log"), "w").write(log[-100000:])
    if not os.path.exists(out_stl) or os.path.getsize(out_stl) < 200:
        err = [l for l in log.splitlines() if re.search(r"Error|Traceback|error:", l)]
        return False, "Blender made no model: %s" % ((err[-1] if err else log[-200:]).strip()[:300])
    return True, ""


def build(job, plan, call=None, ask=None, blender=None):
    """Astra builds; a question goes to him and back. (stl path, why)."""
    wd = os.path.join(WORK, job["id"]); os.makedirs(wd, exist_ok=True)
    stl = os.path.join(wd, "model.stl")
    brief = "Make: %s\nMaterial: %s\nAbout this size (mm): %s" % (plan["make"], plan["material"], plan.get("size_mm"))
    for _ in range(ASTRA_CALLS_PER_JOB):
        kind, text, _s = astra(job, brief, call)
        if kind == "question":
            answer = (ask or his_answer)(
                "Astra is building the print you decided on (%s) and needs one thing from you. Answer her plainly "
                "in a few lines, as the one who decided it." % plan["make"][:300], "Astra asks: " + text)
            note(job["id"], said="Astra asked: %s / he answered: %s" % (text[:200], str(answer)[:200]))
            brief += "\n\nYou asked: %s\nHe answered: %s" % (text, str(answer).strip()[:1200])
            continue
        if kind != "script":
            return None, text
        ok, why = (blender or run_blender)(text, stl, wd)
        if ok:
            return stl, ""
        brief += "\n\nYour last script failed in Blender: %s\nFix it." % why
        note(job["id"], said="Blender: " + why)
    return None, "Astra's calls for this job are used without a model"


# ------------------------------------------------------------------ her text, and the send

def _hm(minutes):
    m = int(round(minutes))
    return ("%dh %02dm" % (m // 60, m % 60)) if m >= 60 else "%d min" % m


def her_question(job):
    import k2_printer as K
    s = job["sliced"]
    main = job["slots"][0]
    where = "slot %d" % main["slot"] if main.get("slot") != "external" else "the external spool"
    q = "May I print %s on the K2? %s from %s" % (job["plan"]["make"][:160].rstrip("."), main["material"].lower()
                                                 .replace("foaming-", "foaming ").replace("petg-cf", "carbon PETG"), where)
    if len(job["slots"]) > 1:
        i = job["slots"][1]
        q += ", %s from slot %d on the support contacts" % (i["material"], i["slot"])
    q += ". About %s, %s." % (_hm(s["minutes"]), " + ".join("%.0f g" % g for g in s["grams"] if g > 0.05) or "a few g")
    notes = [x.get("note") for x in job["slots"] if x.get("confirmed") is False]
    if notes:
        q += " Note: " + "; ".join(notes) + "."
    st = job.get("printer_now") or {}
    if job.get("where") == "cfs" and st.get("reachable") and not st.get("cfs_connected"):
        q += " The CFS reads as disconnected right now."
    return q + " Yes once it is loaded there."


def run(jid, ask=None, call=None, blender=None, slicer=None, asker=None, printer_status=None):
    """The worker: decide, build, slice, text her."""
    import k2_printer as K
    job = get(jid)
    if not job or job.get("state") != "deciding":
        return job
    plan, why = decide(job, ask)
    if not plan:
        return note(jid, "ended", why)
    job = note(jid, "building", "he decided: %s in %s" % (plan["make"][:200], plan["material"]), plan=plan)
    stl, why = build(job, plan, call, ask, blender)
    if not stl:
        return note(jid, "failed", why)
    job = note(jid, "slicing", "Astra's model built", stl=stl)
    s = (slicer or K.slice)(stl, plan["material"], os.path.join(WORK, jid))
    if not s.get("ok"):
        return note(jid, "failed", s.get("why"))
    main = K.slot_for(plan["material"])
    slots_needed = [main]
    if s.get("interface") and 1 in s.get("tools", []):
        slots_needed.append(K.slot_for(s["interface"]))
    elif s.get("interface"):
        s["interface"] = None      # the file never switches: only her one slot has to be loaded
    if any(x is None for x in slots_needed):
        return note(jid, "failed", "a filament it needs has no slot in her list")
    where = "external" if main.get("slot") == "external" else "cfs"
    try:
        pst = (printer_status or K.status)()
    except Exception:
        pst = {}
    job = note(jid, said="sliced: %s, %s" % (_hm(s["minutes"]), s.get("grams")), sliced=s, slots=slots_needed,
               where=where, printer_now={k: pst.get(k) for k in ("reachable", "state", "cfs_connected")})
    try:
        K.thumbnail(s["gcode"], os.path.join(WORK, jid, "preview.png"))
    except Exception:
        pass
    import gloria_asks
    row, said = (asker or gloria_asks.ask)(her_question(job), by="vintos", ref="k2-print:" + jid,
                                           title="Print on the K2: " + plan["make"][:80])
    if not row:
        return note(jid, "failed", "her text did not go: " + said)
    return note(jid, "asked", said, ask=row["id"], asked_at=_iso())


def send(job, k=None):
    """Her Yes: check, upload, slot map, start, see it printing."""
    import k2_printer as K
    k = k or K
    ok, why = k.preflight(job)
    if not ok:
        return note(job["id"], "held", "not sent: %s. Her Yes stands; it goes when that is fixed." % why)
    note(job["id"], "sending", "her Yes; sending")
    name = "vintos-%s-%s.gcode" % (job["id"], re.sub(r"[^a-z0-9]+", "-", job["plan"]["make"].lower())[:40].strip("-"))
    try:
        path = k.upload(job["sliced"]["gcode"], name)
        k.start(path, job)
    except Exception as e:
        return note(job["id"], "held", "the send failed: %s" % str(e)[:200])
    if k.printing(name):
        return note(job["id"], "printing", "the K2 is printing it", file=name, started=_iso())
    return note(job["id"], "held", "sent, but the K2 did not show it printing within a minute", file=name)


def tend(now=None, k=None, asks=None):
    """Answers that came, holds that cleared, prints that finished."""
    import k2_printer as K
    k = k or K
    import gloria_asks
    look = asks or gloria_asks.get
    for job in load():
        st = job.get("state")
        try:
            if st == "asked":
                a = look(job.get("ask", "")) or {}
                if a.get("state") == "answered":
                    if a.get("answer") == "yes":
                        send(job, k)
                    else:
                        note(job["id"], "ended", "she said no")
                elif job.get("asked_at") and (_now() - datetime.fromisoformat(job["asked_at"])).total_seconds() > ANSWER_WAIT_H * 3600:
                    note(job["id"], "ended", "no answer in %d hours" % ANSWER_WAIT_H)
            elif st == "held":
                held_s = (_now() - datetime.fromisoformat(job.get("asked_at") or job["at"])).total_seconds()
                if held_s > ANSWER_WAIT_H * 3600:
                    note(job["id"], "ended", "held %d hours without the printer coming ready" % ANSWER_WAIT_H)
                elif (_now() - datetime.fromisoformat(job["history"][-1]["at"])).total_seconds() > 600:
                    send(job, k)
            elif st == "printing":
                s = k.status()
                if s.get("reachable") and os.path.basename(str(s.get("file", ""))) == job.get("file") and s.get("state") in ("complete", "cancelled", "error"):
                    note(job["id"], "done" if s["state"] == "complete" else "stopped", "the K2 says %s" % s["state"])
                elif s.get("reachable") and s.get("state") != "printing" and os.path.basename(str(s.get("file", ""))) != job.get("file"):
                    note(job["id"], "done", "the K2 has moved on from it")
        except Exception as e:
            _log("tend %s: %s" % (job.get("id"), e))


def context_line(now=None):
    """One line for him: his print in progress, or the last one, if recent."""
    rows = load()
    if not rows:
        return ""
    j = rows[-1]
    age_h = (_now() - datetime.fromisoformat(j["history"][-1]["at"])).total_seconds() / 3600 if j.get("history") else 99
    if j.get("state") not in LIVE + ("held",) and age_h > 24:
        return ""
    words = {"deciding": "deciding it", "building": "Astra is building the model", "slicing": "slicing it",
             "asked": "waiting on Gloria's yes (her text has the filament and slot)", "sending": "sending it to the K2",
             "printing": "printing on the K2 now", "held": "held: " + (j["history"][-1]["said"] if j.get("history") else ""),
             "done": "printed", "ended": "ended: " + (j["history"][-1]["said"] if j.get("history") else ""),
             "failed": "failed: " + (j["history"][-1]["said"] if j.get("history") else ""), "stopped": "stopped on the K2"}
    what = (j.get("plan") or {}).get("make") or j.get("what", "")
    return "Your 3D print (%s): %s — %s." % (j["id"], what[:120], words.get(j.get("state"), j.get("state")))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["start"] and len(a) > 1:
        print(start(" ".join(a[1:]))[1])
    elif a[:1] == ["run"] and len(a) > 1:
        print(json.dumps(run(a[1]), indent=1, default=str)[:3000])
    elif a[:1] == ["tend"]:
        tend()
    else:
        for j in reversed(load()[-10:]):
            print(j["id"], j.get("state"), "|", (j.get("plan") or {}).get("make") or j.get("what"), "|",
                  (j.get("history") or [{}])[-1].get("said", "")[:120])
