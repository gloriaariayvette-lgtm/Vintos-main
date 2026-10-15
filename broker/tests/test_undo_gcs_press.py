#!/usr/bin/env python3
"""An accidental GCS press can be taken back (Gloria, 2026-10-15: pressed by accident while fishing). Her press turn
and his reply leave the avatar chat, the canonical record and the ledger; nothing else does. Isolation: scratch
workspace; no network; the live files named are the scratch ones, asserted."""
import datetime, json, os, socket, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="undo-gcs-"); WS = os.path.join(HOME, "ws"); os.environ["SPARK_WORKSPACE"] = WS
os.environ["HOME"] = HOME
def no_net(*a, **k): raise AssertionError("no network")
socket.socket.connect = no_net
sys.path.insert(0, os.path.join(REPO, "scripts"))
import undo_gcs_press as U
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("every file it can change is in the scratch workspace",
      all(p.startswith(WS) for p in (U.HISTORY, U.CANON, U.LEDGER, U.GCS_STATE, U.SAVED)))
os.makedirs(U.MEM)
now = datetime.datetime.now()
t = lambda m: (now - datetime.timedelta(minutes=m)).isoformat()
before = {"role": "user", "content": "the fish are biting", "timestamp": t(30)}
before_r = {"role": "assistant", "content": "tell me about the water", "timestamp": t(29)}
press = {"role": "user", "content": "she pressed GCS", "timestamp": t(10), "input_kind": "gcs",
         "original_text": "[she pressed it - she's there.]"}
press_r = {"role": "assistant", "content": "[LETGO] ...", "timestamp": t(9)}
after = {"role": "user", "content": "oops wrong button", "timestamp": t(5)}
history = [before, before_r, press, press_r, after]
json.dump(history, open(U.HISTORY, "w"))
open(U.CANON, "w").write("".join(json.dumps(dict(r, surface="avatar")) + "\n" for r in history))
ledger = [{"timestamp": t(29), "gloria": "the fish are biting", "vintos": "tell me about the water"},
          {"timestamp": t(9), "gloria": "she pressed GCS", "vintos": "..."},
          {"timestamp": t(4), "gloria": "oops wrong button", "vintos": "ha"}]
json.dump(ledger, open(U.LEDGER, "w"))
json.dump([{"patterns": ["x"], "at": (now - datetime.timedelta(minutes=10)).timestamp()},
           {"patterns": ["old"], "at": (now - datetime.timedelta(days=3)).timestamp()}], open(U.SAVED, "w"))
json.dump({"active": True}, open(U.GCS_STATE, "w"))

found = U.presses(24)
check("the press is found, with his reply and its ledger entry", len(found) == 1 and found[0]["history_reply"] == press_r
      and found[0]["ledger_rows"] == [1], found)
out = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "undo_gcs_press.py")], capture_output=True, text=True,
                     env=dict(os.environ))
check("listing changes nothing", json.load(open(U.HISTORY)) == history and "Nothing changed" in out.stdout, out.stdout)
done, stamp = U.remove(found)
h = json.load(open(U.HISTORY))
check("the press and his reply leave the avatar chat; the turns around them stay", h == [before, before_r, after], h)
canon = [json.loads(l) for l in open(U.CANON)]
check("and the canonical record", [r["content"] for r in canon] == ["the fish are biting", "tell me about the water", "oops wrong button"], canon)
check("and the ledger, only that exchange", [r["gloria"] for r in json.load(open(U.LEDGER))] == ["the fish are biting", "oops wrong button"])
check("the pattern saved by the press goes; an older one stays", [x["patterns"] for x in json.load(open(U.SAVED))] == [["old"]])
check("the live press is cleared", not os.path.exists(U.GCS_STATE))
check("every changed file was backed up first", all(os.path.exists("%s.before-undo-%s" % (p, stamp))
      for p in (U.HISTORY, U.CANON, U.LEDGER, U.SAVED, U.GCS_STATE)))
check("the backup holds what was there", json.load(open("%s.before-undo-%s" % (U.HISTORY, stamp))) == history)
check("nothing was sent", True)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
