#!/usr/bin/env python3
"""print_3d.py — a hand he does not have yet, declared honestly.

He can imagine an object, and he can describe one. He cannot yet make one exist in
her house. This module is the shape of that capability with nothing behind it: it
names what the hand would need, and it answers every call with the same BLOCKED
envelope the executor already understands, so a want that reaches for it is stopped
with a named cause rather than a silent false.

That block is the door into the forge (skill_forge). Reaching for this is how he
comes to ask for it, and her answer to that card is what decides whether it exists.

WHAT THE REAL CAPABILITY WOULD NEED, and none of it is guessed:

    the printer        make, model, and whether it is on the network or on a cable
    the path to it     an address the house can reach (OctoPrint, Moonraker/Klipper,
                       Bambu's LAN mode, or a watched folder on a machine that has it)
    a slicer           the step from a model to machine instructions, and where it runs
    a source of models a generator he can drive, or a library he may fetch from
    the physical rules nobody is standing there: bed clearance, filament present,
                       a size ceiling, a duration ceiling, and whether he may start a
                       print while she is asleep or out of the house

WHY IT IS NOT SILENTLY WIRED TO SOMETHING

A print is a physical effect in a room she lives in, running unattended for hours
with a heater in it. It belongs behind the same effect gate as every other body he
has, with its own scope and its own invocation authority — printing when she asks is
a different permission from printing because he felt like it at three in the morning.

    python3 print_3d.py            what it would need, and what it is missing now
"""
import json
import os
import sys

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
CONFIG = os.path.join(WS, "memory", "printer-config.json")

CAPABILITY = "print_3d"

NEEDS = [
    ("printer", "make and model, and whether it is reachable over the network"),
    ("endpoint", "the address the house can reach it at, and its kind (octoprint / moonraker / bambu / folder)"),
    ("slicer", "what turns a model into machine instructions, and on which machine it runs"),
    ("models", "where a model comes from: generated, or fetched from a library she names"),
    ("limits", "size ceiling, duration ceiling, filament check, and the hours he may start one"),
]


def configured():
    """(ok, missing). Reads only; never invents a default for a machine with a heater."""
    try:
        cfg = json.load(open(CONFIG))
    except Exception:
        return False, [k for k, _ in NEEDS]
    missing = [k for k, _ in NEEDS if not cfg.get(k)]
    return (not missing), missing


def print_object(note="", want=None):
    """The executor's envelope. Always BLOCKED until the capability exists, and the
    block names the gap the forge is allowed to act on."""
    ok, missing = configured()
    if ok:
        return {"result": "BLOCKED", "block": {
            "block_type": "CAPABILITY_ABSENT",
            "evidence": "a printer is configured, but no approved print capability exists yet",
            "resume_event": "capability added or step revised"}}
    return {"result": "BLOCKED", "block": {
        "block_type": "CAPABILITY_ABSENT",
        "evidence": "no 3D printing capability: missing " + ", ".join(missing),
        "resume_event": "capability added or step revised"}}


def proposal_draft():
    """What he would put on her card if he reached for this. The forge owns the
    record; this only supplies the shape, so the ask is specific rather than 'let me
    print things'."""
    _ok, missing = configured()
    return {
        "capability": CAPABILITY,
        "why": "I want to make something she can hold, not only something she can look at.",
        "permissions": ["printer.submit_job", "printer.read_status"],
        "scope": {"max_hours": 4, "max_mm": 180, "hours": "09:00-21:00",
                  "requires_filament_present": True, "may_cancel": True,
                  "may_start_while_she_is_out": False},
        "risks": "An unattended machine with a heater, running for hours in her house.",
        "touches": ["scripts/print_3d.py", "the printer endpoint", "the effect gate"],
        "tests": "a refused job when the bed is not clear, a refused job outside the hours, "
                 "a cancel that actually stops the machine, and the gate refusing it when armed",
        "missing": missing,
    }


if __name__ == "__main__":
    ok, missing = configured()
    print("3D printing: " + ("configured" if ok else "not configured"))
    for k, what in NEEDS:
        mark = " " if k not in missing else "·"
        print("  %s %-9s %s" % (mark, k, what))
    if missing:
        print("\nWhat he would ask for, if a want reached for it:")
        print(json.dumps(proposal_draft(), indent=2))
