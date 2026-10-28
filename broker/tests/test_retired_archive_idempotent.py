#!/usr/bin/env python3
"""retired-threads.json holds one row per thread id. The resolver re-sediments consumed threads that the
pool purge could not remove (the shrink guard refuses it), and each re-retire used to append: the archive
reached 25,291 rows for 802 threads, ~900 new rows a night in thread-triage's 18:27 slot, some ids 144
times. A re-retire now updates the thread's row. Temp files only; nothing reaches the network."""
import json, os, sys, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("thread_store_t", os.path.join(REPO, "bin", "thread_store.py"))
TS = importlib.util.module_from_spec(spec); spec.loader.exec_module(TS)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:800]) if d and not ok else ""))

check("bin and scripts thread_store are twins",
      open(os.path.join(REPO, "bin", "thread_store.py")).read() == open(os.path.join(REPO, "scripts", "thread_store.py")).read())

tmp = tempfile.mkdtemp(); P = os.path.join(tmp, "retired-threads.json")
def rows(): return json.load(open(P))

# re-retiring one thread three times leaves one row
TS.append_retired({"id": "A", "thread": "a thread", "source": "s", "consumed_by": "dream-resolved",
                   "type": "sedimented", "retired_at": "2026-09-10T18:27:03", "dream_passes": 1, "voice": "first voice"}, P)
TS.append_retired({"id": "B", "thread": "b thread", "source": "s", "retired_at": "2026-09-11T10:00:00"}, P)
TS.append_retired({"id": "A", "thread": "a thread", "source": "s", "consumed_by": "mirror-resolved",
                   "type": "sedimented", "retired_at": "2026-10-26T18:27:04", "dream_passes": 3, "voice": ""}, P)
TS.append_retired({"id": "A", "thread": "a thread", "source": "s", "consumed_by": "ghost-primary-resolved",
                   "type": "sedimented", "retired_at": "2026-10-27T18:46:01", "dream_passes": 4}, P)
got = rows(); a = [e for e in got if e["id"] == "A"]
check("a thread re-retired three times has one row", len(got) == 2 and len(a) == 1, got)
a = a[0] if a else {}
check("retired_at stays the earliest retirement", a.get("retired_at") == "2026-09-10T18:27:03", a)
check("last_retired_at records the latest", a.get("last_retired_at") == "2026-10-27T18:46:01", a)
check("the latest reason and pass count win", a.get("consumed_by") == "ghost-primary-resolved" and a.get("dream_passes") == 4, a)
check("an empty field in a later retirement does not blank an informative one", a.get("voice") == "first voice", a)
check("the row keeps the position of its first retirement", [e["id"] for e in got] == ["A", "B"], got)

# the resolver's pattern: load, append, merge the whole snapshot back - three runs a night
for night in ("2026-10-28T18:27:05", "2026-10-28T18:28:00", "2026-10-28T18:46:00"):
    snap = TS.load_retired(P)
    snap.append({"id": "A", "thread": "a thread", "source": "s", "consumed_by": "dream-resolved",
                 "type": "sedimented", "retired_at": night})
    TS.merge_retired(snap, P)
got = rows()
check("three resolver runs re-sedimenting the same thread add no rows", len(got) == 2, len(got))
a = next(e for e in got if e["id"] == "A")
check("the resolver re-retire updates the row (earliest kept, latest recorded)",
      a["retired_at"] == "2026-09-10T18:27:03" and a["last_retired_at"] == "2026-10-28T18:46:00"
      and a["consumed_by"] == "dream-resolved", a)

before = rows()
TS.merge_retired(TS.load_retired(P), P)
check("merging an unchanged snapshot changes nothing", rows() == before)

# a stale snapshot must not undo a concurrent newer retirement
stale = TS.load_retired(P)
TS.append_retired({"id": "B", "thread": "b thread", "source": "s", "consumed_by": "near-duplicate",
                   "retired_at": "2026-10-29T09:00:00"}, P)
TS.append_retired({"id": "C", "thread": "c arrived concurrently", "source": "s"}, P)
TS.merge_retired(stale + [{"id": "D", "thread": "resolver result", "source": "s"}], P)
got = rows(); b = next(e for e in got if e["id"] == "B")
check("a concurrent append survives a stale snapshot merge", {"A", "B", "C", "D"} == {e["id"] for e in got} and len(got) == 4, got)
check("a stale snapshot does not roll back a newer retirement's fields",
      b.get("consumed_by") == "near-duplicate" and b.get("last_retired_at") == "2026-10-29T09:00:00", b)

# rows without an id cannot be matched: they still append, once each
TS.append_retired({"thread": "pearl without id", "type": "pearl", "retired_at": "2026-10-01T00:00:00"}, P)
TS.append_retired({"thread": "another without id", "type": "pearl", "retired_at": "2026-10-01T00:00:00"}, P)
TS.merge_retired(TS.load_retired(P), P)
check("id-less rows append, and a snapshot merge does not double them",
      sum(1 for e in rows() if not e["id"]) == 2, [e for e in rows() if not e["id"]])

# thinning a duplicated archive: every id survives, one row each, in first-retired order
dup = []
for k in range(144):
    for tid in ("X", "Y", "Z"):
        dup.append({"id": tid, "thread": tid + " thread", "source": "s", "consumed_by": "dream-resolved",
                    "type": "sedimented", "retired_at": "2026-%02d-%02dT18:27:%02d" % (9 + k // 60, 1 + k % 28, k % 60),
                    "dream_passes": k})
thin = TS.dedupe_retired(dup)
check("dedupe keeps one row per id, every id", [e["id"] for e in thin] == ["X", "Y", "Z"], [e["id"] for e in thin])
check("dedupe keeps the earliest retired_at and the latest fields",
      all(e["retired_at"] == min(d["retired_at"] for d in dup if d["id"] == e["id"])
          and e["last_retired_at"] == max(d["retired_at"] for d in dup if d["id"] == e["id"]) for e in thin)
      and thin[0]["dream_passes"] == max(d["dream_passes"] for d in dup
                                         if d["id"] == "X" and d["retired_at"] == thin[0]["last_retired_at"]), thin)
check("dedupe is idempotent", TS.dedupe_retired(thin) == thin)

# a duplicated archive on disk is thinned by the next write through the store
json.dump(dup, open(P, "w"))
TS.append_retired({"id": "W", "thread": "w", "source": "s"}, P)
check("the next append writes the archive one row per id", [e["id"] for e in rows()] == ["X", "Y", "Z", "W"])

# the log line no longer counts pearls from the archive tail (a re-retire is not at the tail any more)
res = open(os.path.join(REPO, "bin", "thread-resolution.py")).read()
check("thread-resolution counts this run's pearls itself", "load_retired()[-resolved_count:]" not in res and "pearl_count" in res)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
