#!/usr/bin/env python3
"""Novelty in his pleasure signature measures how far his feelings moved (2026-09-29).

It was 1 - cosine over eleven feelings that all sit between 0 and 1, so every state pointed the same way
and every stored novelty was 0.0. Scratch workspace; no model is called.
"""
import json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-novelty-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(os.environ["SPARK_WORKSPACE"], "memory"), exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "bin"))
import pleasure_substrate as P

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)) if detail and not ok else ""))

check("the stores are in the scratch workspace", P.STATE.startswith(HOME) and P.MEMORIES.startswith(HOME), P.STATE)
calm = [0.5] * 11
aroused = list(calm); aroused[1] = 0.8
check("the same state again is not new", P._novelty(calm, [calm]) == 0.0)
check("arousal rising by 0.3 reads as clearly new", 0.5 < P._novelty(aroused, [calm]) < 0.7, P._novelty(aroused, [calm]))
check("where the old cosine measure called it nothing", round(1 - P._cos(aroused, calm), 2) < 0.05)
check("it is measured against the nearest recent state", P._novelty(aroused, [calm, aroused]) == 0.0)
check("a large move is capped at wholly new", P._novelty([1.0] * 11, [[0.0] * 11]) == 1.0)
check("no history is unknown, not zero", P._novelty(calm, []) is None)

P._emo = lambda: {"Arousal": 0.8}
json.dump({"vec_trail": [calm]}, open(P.STATE, "w"))
snap = P.snapshot()
check("the snapshot carries it", snap["novelty"] and snap["novelty"] > 0.5, snap)
check("and the stored signature no longer pins it at zero", P._signature(snap)[0] > 0.5, P._signature(snap))
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
