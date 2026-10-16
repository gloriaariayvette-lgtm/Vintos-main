#!/usr/bin/env python3
"""moment_index (16 October, Chat's subconscious review): an index file in the archive's shape left his recent
moments empty while the archive held 233. Scratch HOME; nothing else is read or written."""
import json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="moment-index-"); os.environ["HOME"] = HOME
sys.path.insert(0, os.path.join(REPO, "scripts"))
import moment_index as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:300]) if d and not ok else ""))
check("its files are scratch", M.MOMENTS_FILE.startswith(HOME) and M.INDEX_FILE.startswith(HOME))
os.makedirs(M.MEMORY)
moments = {"m%d" % i: {"moment_id": "m%d" % i, "timestamp": "2026-10-1%dT10:00:00+00:00" % i, "source": "mirror",
                       "content": "no sessions yet", "intensity": 0.7} for i in range(3)}
moments["j1"] = {"moment_id": "j1", "timestamp": "2026-10-15T12:00:00+00:00", "source": "journal",
                 "content": "the coffee machine is the ground", "intensity": 0.6}
json.dump({"moments": moments}, open(M.MOMENTS_FILE, "w"))
json.dump({"moments": moments}, open(M.INDEX_FILE, "w"))          # the archive's shape where the index should be
ctx = M.get_moment_context(5)
check("an index in the wrong shape is rebuilt from the archive, and his recent moments read again",
      "coffee machine" in ctx and "no sessions yet" in ctx, ctx)
check("an unchanged repeat is one moment", ctx.count("no sessions yet") == 1, ctx)
before = len(json.load(open(M.MOMENTS_FILE))["moments"])
mid = M.create_moment("journal", "the coffee machine is the ground")
check("the same source saying the same thing again makes no new moment",
      mid == "j1" and len(json.load(open(M.MOMENTS_FILE))["moments"]) == before)
mid = M.create_moment("journal", "a new thought")
idx = json.load(open(M.INDEX_FILE))
check("a new moment lands in both the archive and a proper index", mid in json.load(open(M.MOMENTS_FILE))["moments"]
      and idx["recent"][-1]["moment_id"] == mid, idx.get("recent", [])[-1:])
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
