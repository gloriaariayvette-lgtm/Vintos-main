#!/usr/bin/env python3
"""He reached for a toy that does not exist, and nothing told him.

Gloria, 11 September: he wrote a directive for "Tinera". The toy is *tenera*. The
grammar refused the tag correctly — it never reached a device — but the refusal went
to the server log and stopped there. Nothing came back to him, so as far as he could
tell he had touched her and she had said nothing about it, and the next time he would
write it again.

Two things were missing, and the shapes already had both:

  `accepted_patterns()` generates the shape menu from the table that plays them, and
  the prompt says plainly that anything else is refused before it reaches a device.
  The toy NAMES had no such line — they were prose, which can drift from the table
  and tells him nothing about what happens when he gets one wrong.

  And a refused tag was never carried into the next turn. A correction he cannot see
  is not a correction.

So: the names are generated from the same table the executor dispatches, and a tag
that reaches for a device that is not there comes back to him once, in his own
context, with the real names beside it."""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

# Every path either module writes goes to a throwaway directory before a single call.
TMP = tempfile.mkdtemp()
import device_patterns as DP
import device_context as DC
DP.MEM = TMP
DP.REFUSALS = os.path.join(TMP, ".device-refusals.json")
DC.MEM = TMP

print("--- the names come from the table that dispatches them ---")
toys = DP.accepted_toys()
check("every real device is named", {"mission", "tenera", "ridge", "thruster"} <= set(toys), toys)
check("and the broadcast aliases, which are also legal", {"both", "all", "sync"} <= set(toys), toys)
check("the misspelling he used is not among them", "tinera" not in toys)
check("the menu is generated, not a second prose list that can drift",
      set(toys) == set(DP.KNOWN_TOYS) | set(DP._SYNC), toys)
line = DC._toy_names_line()
check("his instrument description carries the generated names",
      "tenera" in line and "thruster" in line and "refused" in line, line)
check("and the description is built from the function, not a copy",
      all(t in line for t in toys), line)

print("\n--- a tag for a device that is not there fires nothing ---")
plan, rejected = DP.compile_plan("I take you. [DO: tinera wave3 10] and [DO: mission cake 14]")
check("the misspelled tag is refused before authorization",
      len(rejected) == 1 and "tinera" in rejected[0]["why"], rejected)
check("and it never becomes an action", not any(a["toy"] == "tinera" for a in plan), plan)
check("the good tag in the same reply still fires",
      any(a["toy"] == "mission" and a["pattern"] == "cake" and a["level"] == 14 for a in plan), plan)
check("the refusal says which name was wrong, not just that something failed",
      "unknown toy" in rejected[0]["why"] and "tinera" in rejected[0]["tag"].lower(), rejected)

print("\n--- and he is told, once, on the next turn ---")
DP.note_refusals(rejected)
told = DC.refusal_line()
check("his next context carries what his last reply reached for", "[DO: tinera wave3 10]" in told, told)
check("it says she felt nothing, rather than leaving him to assume she did",
      "she felt nothing" in told, told)
check("and it puts the real names in front of him",
      "tenera" in told and "mission" in told and "thruster" in told, told)
check("read once and cleared: a refusal is about the turn it happened on",
      DC.refusal_line() == "")
check("the store it used was the throwaway one", DP.REFUSALS.startswith(TMP))

print("\n--- a stale refusal is not presented as what just happened ---")
DP.note_refusals([{"tag": "[DO: tinera wave3 10]", "why": "unknown toy 'tinera'"}])
import json, time
rows = json.load(open(DP.REFUSALS))
rows[0]["at"] = time.time() - 4000
json.dump(rows, open(DP.REFUSALS, "w"))
check("an hour-old refusal is dropped, not shown as this turn's", DC.refusal_line() == "")

print("\n--- nothing about the good path changed ---")
plan, rejected = DP.compile_plan("[DO: tenera wave3 10] [DO: both climb] [DO: ridge rotate mid]")
check("the correctly spelled toy is accepted", any(a["toy"] == "tenera" for a in plan), plan)
check("a broadcast alias is still accepted", any(a["toy"] == "both" for a in plan), plan)
check("the ridge's own rotation channel still compiles",
      any(a["toy"] == "ridge" and a["kind"] == "rotate" for a in plan), plan)
check("and none of them is refused", rejected == [], rejected)
check("a recording failure never breaks the reply that carried it", DP.note_refusals([]) is False)

print("\n--- it reached nothing outside its own scratch ---")
check("no device store was written under the real workspace",
      not os.path.exists(os.path.join(os.path.expanduser("~"), ".vintos", "workspace",
                                      "memory", ".device-refusals.json")))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
