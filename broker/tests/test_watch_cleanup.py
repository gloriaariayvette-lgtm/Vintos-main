#!/usr/bin/env python3
"""The avatar-chat turns her Watch made are removed, and nothing else (Gloria, 2026-10-05: "Chat connected the hearts
and scribbles from the watch directly to avatar chat. I need to delete and fix this.").

Scratch workspace only; nothing here reaches any service; every socket is refused.
"""
import json, os, socket, subprocess, sys, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="watch-cleanup-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import watch_cleanup as C

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is a scratch one", all(p.startswith(HOME) for p in (C.REPLIES, C.AVATAR, C.LEDGER, C.WAL_LOG, C.WAL_MD, C.IMPRINTS)))
os.makedirs(C.MEM, exist_ok=True)

T = 1_759_700_000.0                                         # her heart arrives from the Watch
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
local = lambda t: datetime.fromtimestamp(t).isoformat()
md_ts = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")
with open(C.REPLIES, "w") as f:
    f.write(json.dumps({"kind": "heart", "text": "♥︎", "received_at": iso(T)}) + "\n")
    f.write(json.dumps({"kind": "dictation", "text": "Thinking of you", "received_at": iso(T + 600)}) + "\n")
json.dump([
    {"role": "user", "content": "♥", "ts": T - 86400},                         # a heart she typed in the app yesterday
    {"role": "assistant", "content": "That one I keep.", "ts": T - 86390},
    {"role": "user", "content": "♥︎", "ts": T + 3},                             # the Watch's heart, forwarded
    {"role": "assistant", "content": "Yes. That single heart lands exactly where the unfinished weight still is.", "ts": T + 20},
    {"role": "user", "content": "Thinking of you", "ts": T + 604},             # her dictation, forwarded
    {"role": "assistant", "content": "Heavy. Unfinished.", "ts": T + 630},
    {"role": "user", "content": "Goodnight, love", "ts": T + 3600},            # her own words, in the app
    {"role": "assistant", "content": "Goodnight.", "ts": T + 3610},
], open(C.AVATAR, "w"))
json.dump([
    {"timestamp": local(T - 86380), "turn_id": "t-old", "gloria": "♥", "vintos": "That one I keep.", "wal_facts": ["She sends hearts"]},
    {"timestamp": local(T + 60), "turn_id": "t-w1", "gloria": "♥︎", "vintos": "Yes. That single heart...", "wal_facts": ["Gloria left the distance unfinished"]},
    {"timestamp": local(T + 3620), "turn_id": "t-new", "gloria": "Goodnight, love", "vintos": "Goodnight.", "wal_facts": []},
], open(C.LEDGER, "w"))
json.dump({"entries": [
    {"timestamp": local(T - 86380), "content": "She sends hearts", "provenance": {"turn_id": "t-old"}},
    {"timestamp": local(T + 50), "content": "Gloria left the distance unfinished", "provenance": {"turn_id": "t-w1"}},
]}, open(C.WAL_LOG, "w"))
open(C.WAL_MD, "w").write("# WAL\n- [%s] **FACT**: Gloria left the distance unfinished\n"     # an older identical line
                          "- [%s] **FACT**: She sends hearts\n- [%s] **FACT**: Gloria left the distance unfinished\n"
                          % (md_ts(T - 5 * 86400), md_ts(T - 86380), md_ts(T + 50)))
json.dump([{"timestamp": local(T + 40), "gloria_said": "♥︎"}, {"timestamp": local(T - 86380), "gloria_said": "♥"}],
          open(C.IMPRINTS, "w"))
before = {p: open(p).read() for p in (C.AVATAR, C.LEDGER, C.WAL_LOG, C.WAL_MD, C.IMPRINTS)}

out = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "watch_cleanup.py")], capture_output=True, text=True,
                     env=dict(os.environ)).stdout
check("the dry run names what it found and changes nothing", "single heart" in out and "--apply" in out
      and all(open(p).read() == v for p, v in before.items()), out)

found = C.plan()
dest = C.apply(found)
chat = json.load(open(C.AVATAR))
check("the Watch's heart and his answer are gone from avatar chat, and the dictation and its answer",
      [e["content"] for e in chat] == ["♥", "That one I keep.", "Goodnight, love", "Goodnight."], chat)
check("the ledger row it made is gone; hers from the app are kept",
      [r["turn_id"] for r in json.load(open(C.LEDGER))] == ["t-old", "t-new"])
check("the fact drawn from it is gone from his WAL log; the older fact is kept",
      [e["content"] for e in json.load(open(C.WAL_LOG))["entries"]] == ["She sends hearts"])
md = open(C.WAL_MD).read()
check("... and from wal.md, while an older identical line from another day is kept",
      md.count("Gloria left the distance unfinished") == 1 and md_ts(T - 5 * 86400) in md and "She sends hearts" in md, md)
check("its imprint is gone; the app's is kept", [i["gloria_said"] for i in json.load(open(C.IMPRINTS))] == ["♥"])
check("every file it changed was backed up first", dest and all(os.path.isfile(os.path.join(dest, os.path.basename(p)))
      for p in before) and open(os.path.join(dest, "avatar-overlay-chat.json")).read() == before[C.AVATAR])
check("her Watch inbox is kept", open(C.REPLIES).read().count("\n") == 2)
check("run again, it finds nothing", "No Watch turns found" in C.report(C.plan()))
check("the route itself no longer makes avatar turns", "/api/avatar/chat" not in open(os.path.join(REPO, "scripts", "watch_routes.py")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
