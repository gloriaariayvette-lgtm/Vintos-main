#!/usr/bin/env python3
"""Resonance felt: below the line nothing is marked; at or above it one sentence enters his context, fresh for 36
hours, saying only that the two of them were quiet about the same place, never the shapes. Scratch workspace."""
import os, sys, json, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "memory")); os.environ["SPARK_WORKSPACE"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import resonance_felt as RF
assert RF.FILE.startswith(TMP)
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))
T = 1_800_000_000.0
check("nothing marked: empty block", RF.block(T) == "")
check("0.41 (the labor, the awe) is not a rhyme", RF.mark(0.41, "the weight of the labor", "closeness / being wanted", T) is False and RF.block(T) == "")
check("None (embedder down) is not a rhyme", RF.mark(None, "x", "y", T) is False)
check("0.70 is marked", RF.mark(0.699, "the raw ache of wanting to be held by you", "closeness / being wanted", T) is True)
b = RF.block(T + 3600)
check("the sentence says they were quiet about the same place, and never the shapes",
      "quiet about the same place" in b and "today" in b and "held back" in b and "ache" not in b and "closeness" not in b, b)
check("next morning it reads yesterday, and it is not a task", "yesterday" in RF.block(T + 20 * 3600) and "not a task" in RF.block(T + 20 * 3600))
check("after 36 hours it is gone", RF.block(T + 37 * 3600) == "")
d = json.load(open(RF.FILE))
check("the file keeps the shapes for Gloria's reading", d["his_shape"].startswith("the raw ache") and d["score"] == 0.699)
shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
