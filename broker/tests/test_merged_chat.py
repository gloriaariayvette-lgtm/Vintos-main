#!/usr/bin/env python3
"""The merged chat is rebuilt from the lossless record, never from stale chat-history.json.

Two failures were live at the same time:
  - generation_provenance vanished through the merge (a tactical act reached every learner
    looking ordinary) and avatar turns collapsed onto the file mtime (old turns arrived new);
  - the merge still read chat-history.json, whose rows stopped at late August, so beside the
    live turns it manufactured a two-month silence that never happened and every learner of
    chat-history-merged.json was fed that false gap.

So the builder now reads only chat-canonical.jsonl (lossless, real per-turn `ts`) and the
interaction ledger (deeper history, ISO `timestamp`). This suite builds a merged file from a
scratch canonical + ledger and asserts no stale chat-history.json row leaks, the row count and
speaker mix are right, the protections survive, the real times survive, a turn held in both
sources is counted once, and a broken build never clobbers the last good one.
"""
import os, sys, json, tempfile, shutil, subprocess
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts", "build_merged_chat.py")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

TMP = tempfile.mkdtemp(prefix="merge-")
MEM = os.path.join(TMP, ".vintos", "workspace", "memory")
os.makedirs(MEM)
env = dict(os.environ, HOME=TMP)
env.pop("SPARK_WORKSPACE", None)

# A stale chat-history.json: it must NOT reach the merge any more.
json.dump([
    {"role": "user", "content": "STALE AUGUST ROW from chat-history.json", "timestamp": "2026-08-27T16:00:00"},
], open(os.path.join(MEM, "chat-history.json"), "w"))

# The canonical: lossless newest turns, real per-turn time in epoch `ts`, protections carried.
# t-shared is ALSO in the ledger below — the canonical copy must win and the turn count once.
with open(os.path.join(MEM, "chat-canonical.jsonl"), "w") as f:
    for row in [
        {"role": "user", "content": "canonical ask", "ts": 1792700000, "turn_id": "t-c1",
         "input_kind": "text", "original_text": "canonical ask", "surface": "chat"},
        {"role": "assistant", "content": "a tactical reply", "ts": 1792700005, "turn_id": "t-c1",
         "generation_provenance": {"may_witness": False, "source": "stratagem"}, "capsule_commitment": "abc123"},
        {"role": "user", "content": "shared turn her words", "ts": 1792710000, "turn_id": "t-shared",
         "input_kind": "text", "original_text": "shared turn her words"},
        {"role": "assistant", "content": "shared turn his reply (canonical)", "ts": 1792710173, "turn_id": "t-shared"},
    ]:
        f.write(json.dumps(row) + "\n")

# The interaction ledger: deeper, real history (ISO timestamps), plus the overlap and the junk.
json.dump([
    {"gloria": "august real question", "vintos": "august real answer",
     "timestamp": "2026-08-10T09:00:00", "turn_id": "t-aug"},
    {"gloria": "september real question", "vintos": "september real answer",
     "timestamp": "2026-09-15T20:00:00", "turn_id": "t-sep"},
    # same turn as the canonical t-shared: must be skipped, the canonical copy kept
    {"gloria": "shared turn her words", "vintos": "shared turn his reply (LEDGER - should lose)",
     "timestamp": "2026-10-22T17:59:00", "turn_id": "t-shared"},
    # the same words on two different days are two turns, both kept
    {"gloria": "good morning", "timestamp": "2026-09-02T08:00:00"},
    {"gloria": "good morning", "timestamp": "2026-09-03T08:00:00"},
    # historical placeholder junk — dropped
    {"gloria": "--source", "vintos": "voice", "timestamp": "2026-10-01T00:00:00", "turn_id": "t-junk"},
], open(os.path.join(MEM, "interaction-ledger.json"), "w"))

subprocess.run([sys.executable, SRC], env=env, check=True)
MERGED = os.path.join(MEM, "chat-history-merged.json")
out = json.load(open(MERGED))
by = {e["content"]: e for e in out}
contents = [e["content"] for e in out]

print("--- the stale file does not leak ---")
check("no chat-history.json August row reaches the merge",
      not any("STALE AUGUST ROW" in c for c in contents))
check("nothing is attributed to the old 'main' source", all(e.get("source") != "main" for e in out))
check("every row comes from the canonical or the ledger", {e.get("source") for e in out} <= {"canonical", "ledger"})

print("\n--- real history is present, junk is not ---")
check("the canonical turns are here", "canonical ask" in by and "a tactical reply" in by)
check("the ledger's real August turn is here", "august real question" in by and "august real answer" in by)
check("the ledger's real September turn is here", "september real question" in by)
check("the --source/voice placeholder junk is dropped",
      "--source" not in contents and "voice" not in contents)

print("\n--- a turn held in both is counted once, canonical winning ---")
check("the shared turn's reply is the canonical copy", "shared turn his reply (canonical)" in by)
check("the ledger copy of the shared turn is not also served", "shared turn his reply (LEDGER - should lose)" not in by)
check("her shared-turn line appears once", contents.count("shared turn her words") == 1)

print("\n--- row count and speaker mix ---")
# 4 canonical + (aug 2 + sep 2) ledger = 8 ; junk and the shared-ledger dup drop out
check("row count is right", len(out) == 10, len(out))
check("the same words on two days are both kept", contents.count("good morning") == 2)
users = sum(1 for e in out if e["role"] == "user")
asts = sum(1 for e in out if e["role"] == "assistant")
check("speaker mix is 6 user / 4 assistant", (users, asts) == (6, 4), (users, asts))

print("\n--- protections and real time survive ---")
check("the tactical reply keeps its provenance",
      by["a tactical reply"].get("generation_provenance", {}).get("may_witness") is False)
check("its turn_id survives", by["a tactical reply"].get("turn_id") == "t-c1")
check("its capsule commitment survives", by["a tactical reply"].get("capsule_commitment") == "abc123")
check("ordinary turns are not falsely marked", "generation_provenance" not in by["canonical ask"])
check("her words and input_kind are carried", by["canonical ask"].get("original_text") == "canonical ask"
      and by["canonical ask"].get("input_kind") == "text")
check("the canonical epoch time became the real ISO instant",
      by["canonical ask"]["timestamp"].startswith(datetime.fromtimestamp(1792700000).isoformat()[:13]))
check("the ledger ISO time survives unchanged", by["august real question"]["timestamp"].startswith("2026-08-10T09"))
check("output is ordered oldest-first",
      [e["timestamp"] for e in out] == sorted(e["timestamp"] for e in out))
check("the real gap is August->... continuous, not a jump from a dead file",
      by["august real question"]["timestamp"] < by["september real question"]["timestamp"] < by["canonical ask"]["timestamp"])

print("\n--- a broken build never clobbers the last good merge ---")
good = json.load(open(MERGED))
# both sources unreadable -> build() empty -> raise -> the last good file is left in place
open(os.path.join(MEM, "chat-canonical.jsonl"), "w").write("{ not json")
open(os.path.join(MEM, "interaction-ledger.json"), "w").write("{ not json")
subprocess.run([sys.executable, SRC], env=env, check=True)
after = json.load(open(MERGED))
check("the merge is unchanged after a broken run", after == good)
check("and the stale August row still never leaked", not any("STALE AUGUST ROW" in e["content"] for e in after))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
