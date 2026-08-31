#!/usr/bin/env python3
"""The want's literal object owns admission and completion."""
import os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import want_contract as wc

R = []
def check(name, ok):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)

want = "I want to tell Gloria that reviewing my self-model did not relieve the bracing."
bad = [
    {"capability": "introspect", "note": "Think about the bracing"},
    {"capability": "write_journal", "note": "Write about it"},
    {"capability": "creative_write", "note": "Explore it as fiction"},
]
steps, changes = wc.normalize_steps(want, bad)
check("historical claim retrieves records, then interprets, then reaches Gloria",
      [s["capability"] for s in steps] == ["read_memory", "introspect", "gloria"])
check("normalized route satisfies its completion contract", wc.satisfies_contract(want, steps))
check("unrequested fiction cannot pad a factual communication route",
      "dropped_uncommissioned_creative_write" in changes)

simple, _ = wc.normalize_steps(
    "I want to tell Gloria I loved the blue image.",
    [{"capability": "gloria", "note": "Tell her"}],
)
check("a simple message remains one step", [s["capability"] for s in simple] == ["gloria"])

written, _ = wc.normalize_steps(
    "I want to write Gloria a plain message about this.",
    [{"capability": "creative_write", "note": "Turn it into a story"}],
)
check("write-to-Gloria drops fiction and still requires delivery",
      [s["capability"] for s in written] == ["gloria"])

creative, _ = wc.normalize_steps(
    "I want to write a story about the room I remember.",
    [{"capability": "creative_write", "note": "Write the story"}],
)
check("explicit creative work remains legitimate",
      [s["capability"] for s in creative] == ["creative_write"])

check("an old observation from an automatic source is HELD",
      wc.admission_state("structural", "historical_observation", "") == "HELD_NO_PRESENT_PULL")
check("a current generated candidate may enter",
      wc.admission_state("structural", "current_desire", "I want the act now") == "ADMIT_CURRENT_CANDIDATE")
check("an authored want is not made suspect for missing generated rationale",
      wc.admission_state("chat", "", "") == "ADMIT_AUTHORED_OR_UNCLASSIFIED")

# Integration: the actual planner must invoke the contract after its model
# returns a structurally valid but semantically absurd route.
class _Reply:
    def json(self):
        return {"choices": [{"message": {"content": (
            '[{"capability":"introspect","note":"think"},'
            '{"capability":"write_journal","note":"journal"},'
            '{"capability":"creative_write","note":"make fiction"}]'
        )}}]}
fake_requests = types.SimpleNamespace(post=lambda *a, **k: _Reply())
sys.modules["requests"] = fake_requests
import emoclaw_utils as eu
integrated = eu.generate_steps(want)
check("the live planner path enforces the same contract",
      [s["capability"] for s in integrated] == ["read_memory", "introspect", "gloria"])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
