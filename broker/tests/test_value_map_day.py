#!/usr/bin/env python3
"""The value map keeps a whole day (2026-10-13). Every run used to archive the live map and overwrite it, so however
often it ran, value-map.md held one entry. Now a run on a new day archives and starts over, and a later run the same
day adds beneath the earlier ones. The readers that took the top of the file now take the newest entry.

Isolation: HOME is a throwaway directory before anything is imported, requests is stubbed so the model call cannot
leave the machine, the model function and source_cache are replaced, and MAP_FILE is repointed and asserted."""
import importlib.util, os, sys, tempfile, types
from datetime import datetime as _real_dt

TMP = tempfile.mkdtemp(prefix="valuemap-")
os.environ["HOME"] = TMP
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.makedirs(os.path.join(TMP, ".vintos", "workspace", "memory"), exist_ok=True)

import requests
SENT = []
def _no_send(*a, **k):
    SENT.append(a); raise requests.ConnectionError("this suite reaches nothing")
requests.post = requests.get = requests.put = _no_send

sc = types.ModuleType("source_cache")
sc.unchanged = lambda *a, **k: False
sc.commit = lambda *a, **k: None
sc.last = lambda *a, **k: {}
sys.modules["source_cache"] = sc

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:900]) if d and not ok else ""))

copies = [os.path.join(REPO, p) for p in ("scripts/value_map.py", "scripts/value-map.py", "bin/value-map.py")]
check("the value-map copies are identical", len({open(p).read() for p in copies}) == 1)

spec = importlib.util.spec_from_file_location("value_map_t", copies[0])
VM = importlib.util.module_from_spec(spec); spec.loader.exec_module(VM)
VM.MAP_FILE = os.path.join(TMP, "value-map.md")
ARCH = os.path.join(TMP, "value-map-archive.md")
check("the map is throwaway", VM.MAP_FILE.startswith(TMP))
check("the sender is a stub", requests.post is _no_send)

VM.gather_full_context = lambda: "context"
CALLS = []
def fake_llm(system, user, temperature=0.6):
    CALLS.append(1); return "RANK 1 — entry %d\nWhy: x\nEvidence: y" % len(CALLS)
VM.llm = fake_llm

class FakeDT(_real_dt):
    NOW = _real_dt(2026, 10, 13, 8, 0)
    @classmethod
    def now(cls, tz=None): return cls.NOW
VM.datetime = FakeDT

def run(y, mo, d, h):
    FakeDT.NOW = _real_dt(y, mo, d, h, 0); VM.build_map()

run(2026, 10, 13, 8); run(2026, 10, 13, 14); run(2026, 10, 13, 20)
live = open(VM.MAP_FILE).read()
check("three runs in a day leave three entries", live.count("— Value Map") == 3, live)
check("in the order they were made", live.index("08:00") < live.index("14:00") < live.index("20:00"), live)
check("nothing was archived within the day", not os.path.exists(ARCH))

run(2026, 10, 14, 8)
live = open(VM.MAP_FILE).read()
arch = open(ARCH).read()
check("a new day starts the map over", live.count("— Value Map") == 1 and "2026-10-14 08:00" in live, live)
check("yesterday's three went to the archive", arch.count("— Value Map") == 3 and "2026-10-14" not in arch, arch)

# the readers that took the top of the file now take the newest entry
run(2026, 10, 14, 14)
newest = "entry %d" % len(CALLS)
import re as _vmre
pick = _vmre.split(r"\n(?=## \d{4}-\d{2}-\d{2})", "\n" + open(VM.MAP_FILE).read())[-1].strip()
check("the newest entry is the one picked", newest in pick and "14:00" in pick, pick)
for p in ("scripts/map_view_compiler.py", "scripts/unseen.py", "scripts/dot_channel.py"):
    src = open(os.path.join(REPO, p)).read()
    check(p + " reads the newest value-map entry", '_vmre.split(r"\\n(?=## \\d{4}-\\d{2}-\\d{2})"' in src)
check("nothing reached the world", not SENT, SENT)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
