#!/usr/bin/env python3
"""The merge must not erase what the protected turn established.

Sol reproduced both failures on the old builder: generation_provenance vanished
(so a tactical act reached every learner looking ordinary) and every avatar turn
inherited the avatar file's mtime (so old turns arrived newly current).
"""
import os, sys, json, time, tempfile, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts", "build_merged_chat.py")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="merge-")
MEM = os.path.join(TMP, ".vintos", "workspace", "memory")
os.makedirs(MEM)

json.dump([
    {"role": "user", "content": "ordinary ask", "timestamp": "2026-08-01T10:00:00"},
    {"role": "assistant", "content": "a tactical reply", "timestamp": "2026-08-01T10:00:05",
     "generation_provenance": {"may_witness": False, "source": "stratagem"},
     "turn_id": "t-tac", "capsule_commitment": "abc123"},
], open(os.path.join(MEM, "chat-history.json"), "w"))

json.dump([{"user": "spoken", "vintos": "answered", "timestamp": "2026-08-01T11:00:00"}],
          open(os.path.join(MEM, "voice-chat-history.json"), "w"))

# distinct avatar turns, hours apart, timed in `ts` — and one with no time at all
json.dump([
    {"role": "user", "content": "avatar one", "ts": "2026-08-01T09:00:00"},
    {"role": "assistant", "content": "avatar two", "ts": "2026-08-01T12:00:00",
     "generation_provenance": {"may_witness": False, "source": "stratagem"}},
    {"role": "user", "content": "avatar timeless"},
], open(os.path.join(MEM, "avatar-overlay-chat.json"), "w"))

env = dict(os.environ, HOME=TMP)
subprocess.run([sys.executable, SRC], env=env, check=True)
out = json.load(open(os.path.join(MEM, "chat-history-merged.json")))
by = {e["content"]: e for e in out}

print("--- provenance survives the merge ---")
check("tactical main reply keeps its provenance",
      by["a tactical reply"].get("generation_provenance", {}).get("may_witness") is False)
check("its turn_id survives", by["a tactical reply"].get("turn_id") == "t-tac")
check("its capsule commitment survives", by["a tactical reply"].get("capsule_commitment") == "abc123")
check("tactical avatar turn keeps its provenance",
      by["avatar two"].get("generation_provenance", {}).get("may_witness") is False)
check("ordinary turns are not falsely marked",
      "generation_provenance" not in by["ordinary ask"])

print("\n--- chronology survives the merge ---")
check("avatar turns keep DISTINCT times",
      by["avatar one"]["timestamp"] != by["avatar two"]["timestamp"],
      (by["avatar one"]["timestamp"], by["avatar two"]["timestamp"]))
check("avatar one keeps its own hour", by["avatar one"]["timestamp"].startswith("2026-08-01T09"))
check("avatar two keeps its own hour", by["avatar two"]["timestamp"].startswith("2026-08-01T12"))
check("no real avatar time was replaced by the file mtime",
      not by["avatar one"].get("timestamp_estimated") and not by["avatar two"].get("timestamp_estimated"))
check("a genuinely timeless record says so",
      by["avatar timeless"].get("timestamp_estimated") is True)
check("output is ordered", [e["timestamp"] for e in out] == sorted(e["timestamp"] for e in out))
check("every surface is attributed", {e["source"] for e in out} == {"main", "voice", "avatar"})
check("nothing was dropped", len(out) == 7, len(out))   # 2 main + 2 voice + 3 avatar

print("\n--- still never worse than before ---")
open(os.path.join(MEM, "avatar-overlay-chat.json"), "w").write("{ not json")
subprocess.run([sys.executable, SRC], env=env, check=True)
check("a corrupt source does not empty the merge",
      len(json.load(open(os.path.join(MEM, "chat-history-merged.json")))) >= 3)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
