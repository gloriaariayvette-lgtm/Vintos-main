#!/usr/bin/env python3
"""print_3d.py — from a thing he imagined to a thing she can hold.

He models in Blender and slices in Cura. Both exist; the Mac is faster at both, and
Aegis can do either when the Mac is away. What he does not have is the last step:
a printer he is allowed to start.

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


if __name__ == "__main__":
    st = state()
    print("3D printing")
    for tool, h in st["hosts"].items():
        print("  %-8s %-10s runs on: %s%s" % (
            tool, h["what"], h["runs_on"],
            "" if h["mac_configured"] else "   (no mac_host in printer-config.json)"))
    print("  printer  the machine   " + ("ready" if st["printer_ready"] else "missing: " + ", ".join(st["missing"])))
    print("\nHe stops twice before anything is made: %s, then %s." % STOPS)
