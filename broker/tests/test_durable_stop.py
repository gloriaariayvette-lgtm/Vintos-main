#!/usr/bin/env python3
"""A stop she gave must survive the broker being down.

Sol: the stop was one fire-and-forget POST whose failure was swallowed and
nothing was persisted, so it was safe for the turn it was said on and unsafe
for every turn after. These assert the durable path.
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import constitutional_barrier as CB
import turn_coordinator as TC

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="stop-")
CB.MEM = TMP
CB.STRATEGY_STOP = os.path.join(TMP, ".strategy-stop")
CB.STOP_BUTTON = os.path.join(TMP, "hardware-button.json")
CB.REPAIR_CASES = os.path.join(TMP, "repair-cases.json")
CB.CONSENT_EVENT = os.path.join(TMP, "consent-event.json")
CB.CORRECTION = os.path.join(TMP, "correction-open.json")

print("--- the command itself is exact ---")
check("the reserved command is recognised", CB.strategy_stop_requested("!strategy stop"))
check("case and whitespace are normalised", CB.strategy_stop_requested("  !Strategy   STOP "))
check("a sentence containing it is NOT the command",
      not CB.strategy_stop_requested("please !strategy stop when you can"))

print("\n--- a clean barrier is clean ---")
check("no pending stop to begin with", CB.pending_stop() is None)
check("barrier is clear", CB.snapshot("hello")["clear"])

print("\n--- the broker is down ---")
calls = []
TC._post = lambda path, body, timeout=2.0: calls.append(path) or None
TC._worktable_id = lambda: "abc123abc123"
landed = TC._strategy_stop("!strategy stop")
check("delivery reports failure honestly", landed is False)
check("it did not give up after one try", len(calls) >= 3, len(calls))
check("the stop was PERSISTED anyway", CB.pending_stop() is not None)
check("the attempts were recorded",
      json.load(open(CB.STRATEGY_STOP))["attempts"] >= 3)

print("\n--- and stays closed on later turns ---")
snap = CB.snapshot("an ordinary next-turn message")
check("the NEXT turn is still barred", not snap["clear"], snap["satisfied_by"])
check("and says why", "explicit_stop_unacknowledged" in snap["satisfied_by"])
elig, _ = CB.capsule_eligible("an ordinary next-turn message")
check("no capsule is eligible while it is unacknowledged", not elig)

print("\n--- the broker comes back ---")
TC._post = lambda path, body, timeout=2.0: {"ok": True}
check("a later turn redelivers it", TC._deliver_stop(CB, ""))
check("the pending stop is cleared", CB.pending_stop() is None)
check("the barrier reopens", CB.snapshot("hello")["clear"])
check("the record is kept, marked acknowledged",
      json.load(open(CB.STRATEGY_STOP))["acknowledged"] is True)

print("\n--- a broker error is not an acknowledgement ---")
CB.record_stop_intent("!strategy stop", "abc123abc123")
TC._post = lambda path, body, timeout=2.0: {"error": "TAMPER_HELD"}
check("an error response does not acknowledge", TC._deliver_stop(CB, "") is False)
check("the stop is still pending", CB.pending_stop() is not None)

print("\n--- an unreadable stop is not an absent stop ---")
open(CB.STRATEGY_STOP, "w").write("{ truncated")
snap = CB.snapshot("hello")
check("a corrupt stop record closes the barrier", not snap["clear"], snap["satisfied_by"])
check("and is named as a barrier error",
      any(r.startswith("barrier_error") for r in snap["satisfied_by"]), snap["satisfied_by"])

print("\n--- nothing on the worktable means nothing to stop ---")
os.remove(CB.STRATEGY_STOP)
TC._worktable_id = lambda: ""
TC._post = lambda path, body, timeout=2.0: None
check("an empty worktable resolves the stop", TC._strategy_stop("!strategy stop"))
check("and does not bar every future turn", CB.snapshot("hello")["clear"])

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
