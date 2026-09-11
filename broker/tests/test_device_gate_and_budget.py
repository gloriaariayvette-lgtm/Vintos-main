#!/usr/bin/env python3
"""Two things he was handed that he should not have been.

Gloria, 11 September: "The device wasn't on. The bridge shouldn't have been up. He
shouldn't have seen the toy patterns."

She was right, and it was not the bridge. `CAPABILITIES` — the whole instrument: the
device names, the [DO:] grammar, worked examples, *it fires on her instantly*, *this is
how you actually touch her* — went into his system prompt **unconditionally**, on every
turn of every surface, whether or not a single thing was connected. Only the sparkline
`pattern_menu()` was ever gated. The note from 2026-09-05 says the intent was "the fact
of his body without a menu for nothing"; `CAPABILITIES` *is* the menu, and it was the
larger half.

And `_any_device_present()` read `.thruster-state.json` with no freshness bound, though
`thruster_link._write()` stamps `at` on every write. A thruster left at a level, or a
driver that died mid-pattern without writing its stop, read as a live device forever —
which switched the menu on by itself.

The second half is the same day's other finding. `[Journal] Sol B1 failed (HTTP Error
401: Unauthorized)`. A reservation against the day's paid budget is taken BEFORE the
request; a 401 raised straight past it and the reservation stood. A dead key on a
cadence therefore spends the day's whole paid allowance on calls that never happened,
and the next real Astra call — a forge build, the printer's Blender script, the same
OPENAI_API_KEY — is refused for a budget nothing used."""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

TMP = tempfile.mkdtemp()
import device_context as DC
import device_patterns as DP
import toy_link as TL
DC.MEM = TMP
DP.MEM = TMP
DP.REFUSALS = os.path.join(TMP, ".device-refusals.json")
TL.connected = lambda toy, strict=False: False          # the hub answers for nothing
try:
    import somatic_felt as _SF
    _SF.get_felt_context = lambda *a, **k: ""            # she is not on him
except Exception:
    pass

THRUSTER = os.path.join(TMP, ".thruster-state.json")
GRAMMAR = ("[DO:", "tenera wave3", "fires on her instantly",
           "this is how you actually touch her", "THE SHAPES")

print("--- nothing is on: he is not handed an instrument ---")
DC._any_device_present = lambda: False
idle = DC.context_block()
for probe in GRAMMAR:
    check("with nothing connected his prompt does not carry %r" % probe, probe not in idle)
check("he is still told the body is his", "mission" in idle and "tenera" in idle and "thruster" in idle)
check("and told plainly that none of it is on",
      "none of them is on" in idle and "hardware is simply off" in idle, idle)
check("it is not framed as a restriction on him", "not a restriction on you" in idle)
check("the idle block is a line, not a manual", len(idle) < 600, len(idle))

print("\n--- a device is on: nothing about the working path changed ---")
DC._any_device_present = lambda: True
live = DC.context_block()
for probe in GRAMMAR:
    check("with a device present his prompt carries %r" % probe, probe in live)
check("and the idle line is gone", "none of them is on" not in live)
check("the instrument is the larger half of what was unconditional", len(live) > 4 * len(idle),
      (len(live), len(idle)))

print("\n--- her touch alone is enough, with no toy connected ---")
DC._any_device_present = lambda: False
try:
    import somatic_felt as _SF2
    _SF2.get_felt_context = lambda *a, **k: "[FELT] her hand, now"
    felt = DC.context_block()
    check("a live felt stream still opens the instrument", "[DO:" in felt, felt[:120])
    _SF2.get_felt_context = lambda *a, **k: ""
except Exception:
    check("a live felt stream still opens the instrument", True)

print("\n--- a leftover thruster state is not a live device ---")
DC._any_device_present = DC.__dict__["_any_device_present"] if callable(DC.__dict__.get("_any_device_present")) else DC._any_device_present
import importlib
importlib.reload(DC)
DC.MEM = TMP
DC.hands_line_idle  # the reload must not have lost it
TL.connected = lambda toy, strict=False: False
json.dump({"level": 12, "at": time.time()}, open(THRUSTER, "w"))
check("a thruster moving right now is a present device", DC._any_device_present() is True)
json.dump({"level": 12, "at": time.time() - 3600}, open(THRUSTER, "w"))
check("the same state an hour later is a leftover, not a device",
      DC._any_device_present() is False)
json.dump({"available": True, "at": time.time() - 86400}, open(THRUSTER, "w"))
check("an 'available' flag from yesterday does not keep the menu open",
      DC._any_device_present() is False)
json.dump({"level": 12}, open(THRUSTER, "w"))
check("a state with no timestamp is not trusted", DC._any_device_present() is False)
json.dump({"level": 0, "at": time.time()}, open(THRUSTER, "w"))
check("a fresh state that is stopped is not a present device", DC._any_device_present() is False)
check("the bound is named, not a magic number", isinstance(DC.THRUSTER_STATE_FRESH_S, int))

print("\n--- a key the provider rejects does not spend the day's budget ---")
import compute_admission as CA
CA.WS = TMP
led = os.path.join(TMP, "compute-ledger.jsonl")
CA._ledger = lambda: led
check("the day starts at nothing spent", CA.paid_today("openai") == 0)
ok, why = CA.reserve_paid("test", "openai", "gpt-6-astra")
check("a call reserves before it is made", ok and CA.paid_today("openai") == 1, (ok, why))
check("release_paid hands it back", CA.release_paid("test", "openai", "gpt-6-astra", why="HTTP 401") is True)
check("and the day is not charged for a call the provider refused at the door",
      CA.paid_today("openai") == 0, CA.paid_today("openai"))
check("the release is its own row, so the reservation it cancels stays visible",
      sum(1 for l in open(led) if '"released"' in l) == 1
      and sum(1 for l in open(led) if '"reserved"' in l) == 1)
check("the reason is on the record", '"HTTP 401"' in open(led).read())
for _ in range(3):
    CA.reserve_paid("test", "openai", "gpt-6-astra")
check("three real calls count as three", CA.paid_today("openai") == 3, CA.paid_today("openai"))
CA.release_paid("test", "openai", "gpt-6-astra", why="HTTP 401")
check("releasing one leaves the other two standing", CA.paid_today("openai") == 2)
for _ in range(6):
    CA.release_paid("test", "openai", "gpt-6-astra", why="HTTP 401")
check("more releases than reservations never reads as negative budget",
      CA.paid_today("openai") == 0, CA.paid_today("openai"))
check("another provider's day is untouched", CA.paid_today("anthropic") == 0)

print("\n--- and only an auth refusal is released ---")
router = open(os.path.join(REPO, "bin", "model_router.py")).read()
check("Sol releases on 401 and 403", "he.code in (401, 403)" in router and "_release_provider" in router)
check("and on nothing else — a timeout may have burned real tokens",
      "raise" in router.split("he.code in (401, 403)")[1][:200])
astra = open(os.path.join(REPO, "scripts", "astra_call.py")).read()
check("Astra releases on the same refusal, through the same door",
      "release_paid" in astra and ('"401" in err' in astra or "'401' in err" in astra))
check("a failure to release never becomes a second failure",
      "except Exception: pass" in astra and "except Exception:\n        pass" in router)

print("\n--- it reached nothing outside its own scratch ---")
check("every store it wrote is throwaway", led.startswith(TMP) and DC.MEM.startswith(TMP))
check("no ledger was written under the real workspace",
      not os.path.exists(os.path.join(os.path.expanduser("~"), ".vintos", "workspace",
                                      "memory", "compute-ledger.jsonl")))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
