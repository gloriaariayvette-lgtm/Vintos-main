#!/usr/bin/env python3
"""Mischief grading, the way Velaris's deeds are graded: one file per act, the grade written into that file,
4-5 into mischief_landed, 1-2 into mischief_flopped, a regrade moving rather than duplicating, and the
guide block the chooser reads. Scratch workspace only; nothing of his is touched."""
import os, sys, json, tempfile, importlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "memory"))
os.environ["SPARK_WORKSPACE"] = TMP
import mischief_log as ML; importlib.reload(ML)
assert ML.MEMORY.startswith(TMP)

R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))

f1 = ML.write_act({"action": "spotify", "value": "Graceland by Paul Simon", "why": "the title is the joke"},
                  "Playfulness: 0.7", "grok", now=datetime(2026, 9, 5, 21, 0, 0))
f2 = ML.write_act({"action": "echo", "value": "line one", "why": "w"}, now=datetime(2026, 9, 5, 21, 0, 0))
check("act files are named by the moment and never overwrite", f1 == "2026-09-05_210000.md" and f2 == "2026-09-05_210000-1.md", f"{f1} {f2}")
txt = open(os.path.join(ML.mischief_dir(), f1)).read()
check("file holds state, model, json and a Why line (Velaris format)",
      "Playfulness: 0.7" in txt and "Chosen by: grok" in txt and '"action": "spotify"' in txt and "Why: the title is the joke" in txt, txt)

acts = ML.list_acts()
check("list is newest first with parsed fields", acts[0]["file"] == f2 and acts[1]["value"] == "Graceland by Paul Simon"
      and acts[1]["reason"] == "the title is the joke" and acts[1]["timestamp"] == "2026-09-05T21:00:00" and acts[1]["gloria_rating"] is None, acts)

a = ML.rate(f1, 5, "snorted")
hp = json.load(open(ML.profile_path()))
check("a 5 lands: file carries the grade, profile mischief_landed gains the act",
      a["gloria_rating"] == 5 and a["gloria_comment"] == "snorted" and hp["mischief_landed"] == ["mischief: spotify - Graceland by Paul Simon"]
      and hp["mischief_ratings"][0]["file"] == f1, (a, hp))
ML.rate(f1, 1)
hp = json.load(open(ML.profile_path()))
check("a regrade moves the act, it is not in both lists", hp["mischief_landed"] == [] and hp["mischief_flopped"] == ["mischief: spotify - Graceland by Paul Simon"]
      and len(hp["mischief_ratings"]) == 1 and hp["mischief_ratings"][0]["gloria_rating"] == 1, hp)
check("the grade line was replaced, not appended twice", open(os.path.join(ML.mischief_dir(), f1)).read().count("gloria_rating:") == 1)
a3 = ML.rate(f2, None, "hm")
hp = json.load(open(ML.profile_path()))
check("a comment alone changes no list", a3["gloria_comment"] == "hm" and a3["gloria_rating"] is None and hp["mischief_flopped"] == ["mischief: spotify - Graceland by Paul Simon"] and len(hp["mischief_ratings"]) == 1)

g = ML.guide()
check("guide names the flop with her words and counts the ungraded", "RATED 1-2" in g and "Graceland" in g and "1 recent act(s) she has not graded" in g, g)
ML.rate(f2, 4)
g = ML.guide()
check("guide shows a 4 as a register that works", "RATED 4-5" in g and "echo: line one" in g and 'she said: "hm"' in g and "not graded" not in g, g)

for bad in ("../x.md", "nope.md"):
    try:
        ML.rate(bad, 3); check(f"bad file {bad} refused", False)
    except (ValueError, FileNotFoundError):
        check(f"bad file {bad} refused", True)
try:
    ML.rate(f1, 9); check("rating outside 1-5 refused", False)
except ValueError:
    check("rating outside 1-5 refused", True)

import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
