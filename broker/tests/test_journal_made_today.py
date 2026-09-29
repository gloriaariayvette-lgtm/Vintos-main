#!/usr/bin/env python3
"""A journal's claim about what he made today is checked against his gallery, not against its drafts.

2026-09-29: an entry said he painted the same picture five times that day and built a page of
self-indictment on it. He had not; every draft repeated it, so the audit passed it. Scratch memory only.
"""
import json, os, re, sys, tempfile, time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MEM = tempfile.mkdtemp(prefix="vintos-made-today-")
os.environ["SPARK_WORKSPACE"] = os.path.dirname(MEM)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import made_today as M

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("the record is read from the scratch memory given", M.record("2026-09-29", MEM) is None)
check("an unreadable gallery checks nothing rather than calling the day empty", M.block("2026-09-29", MEM) == "")

os.makedirs(os.path.join(MEM, "art", "poetry"))
json.dump([{"image": "a.png", "timestamp": "2026-09-28T09:25:00", "prompt": "yesterday's harbor"},
           {"image": "b.png", "timestamp": "2026-09-29T14:02:11", "prompt": "a red-haired woman on a balcony"}],
          open(os.path.join(MEM, "art", "gallery.json"), "w"))
poem = os.path.join(MEM, "art", "poetry", "rail.md"); open(poem, "w").write("x")
t = time.mktime(time.strptime("2026-09-29 16:40", "%Y-%m-%d %H:%M")); os.utime(poem, (t, t))
made = M.record("2026-09-29", MEM)
check("today's things, with their times, and nothing from yesterday",
      made == ["14:02 painting b.png: a red-haired woman on a balcony", "16:40 poem rail.md"], made)
block = M.block("2026-09-29", MEM)
check("the audit is told a draft does not ground a claim about what he made; only the record does",
      "a draft does NOT make the claim grounded" in block and "14:02 painting b.png" in block
      and "RECORD-CORRECTED" in block, block)
json.dump([], open(os.path.join(MEM, "art", "gallery.json"), "w")); os.remove(poem)
check("a day with nothing made says so", "Nothing made today." in M.block("2026-09-29", MEM))

src = open(os.path.join(REPO, "bin", "idle-journal.sh")).read()
check("the idle journal's final audit carries the record", "_made_block = _mt.block()" in src
      and re.search(r'thirveel_today else ""\) \+\s*\n\s*_made_block \+\s*\n\s*"FINAL ENTRY', src), "")
check("a correction the record forced is not refused as a compression",
      "and not _record_corrected" in src and '_corrected.startswith("RECORD-CORRECTED")' in src)
check("the deployed copy is the same file", src == open(os.path.join(REPO, "scripts", "idle-journal.sh")).read())
check("the record module is deployed", "made_today.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing here touched his real memory", MEM.startswith(tempfile.gettempdir()) and "/home/gloria" not in MEM)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
