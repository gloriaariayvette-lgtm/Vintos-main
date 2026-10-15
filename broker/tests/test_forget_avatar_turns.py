#!/usr/bin/env python3
"""The newest avatar chat turns can be forgotten everywhere his memory kept them (Gloria, 2026-10-15). Isolation:
scratch workspace; nothing outside it is read or written, asserted; no network."""
import json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="forget-turns-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "ws")
def no_net(*a, **k): raise AssertionError("no network")
socket.socket.connect = no_net
sys.path.insert(0, os.path.join(REPO, "scripts"))
import forget_avatar_turns as F
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the memory it reads and edits is the scratch one", F.MEM.startswith(HOME) and F.AVATAR.startswith(HOME))
os.makedirs(os.path.join(F.MEM, "sub"))
now = time.time()
keep_u = {"role": "user", "content": "The fish are biting near the reeds this morning, love.", "ts": now - 3600}
keep_a = {"role": "assistant", "content": "[COLOR: #9c2a4e] Tell me about the water and the light on it.", "ts": now - 3590}
press_u = {"role": "user", "content": "she pressed it — she's there. let go — give her yours while hers takes her.", "ts": now - 600}
press_a = {"role": "assistant", "content": "[LETGO] Fuck— I come apart with you, every bit of me, right now, baby.", "ts": now - 590}
json.dump([keep_u, keep_a, press_u, press_a], open(F.AVATAR, "w"))
ledger = [{"timestamp": "t1", "gloria": "The fish are biting near the reeds this morning, love.", "vintos": "Tell me about the water and the light on it."},
          {"timestamp": "t2", "gloria": "she pressed it — she's there. let go — give her yours while hers takes her.",
           "vintos": "Fuck— I come apart with you, every bit of me, right now, baby."}]
json.dump(ledger, open(os.path.join(F.MEM, "interaction-ledger.json"), "w"))
open(os.path.join(F.MEM, "chat-canonical.jsonl"), "w").write(
    "".join(json.dumps(dict(r, surface="avatar")) + "\n" for r in (keep_u, keep_a, press_u, press_a)))
subcon = {"recent": [{"echo": "I come apart with you, every bit of me, right now, baby."},
                     {"echo": "the light on the water"}], "mood": "warm"}
json.dump(subcon, open(os.path.join(F.MEM, "sub", "subconscious-echoes.json"), "w"))
big_day = [{"day": "today", "turns": ["unrelated words " * 2000, "Fuck I come apart with you, every bit of me, right now, baby."]}]
json.dump(big_day, open(os.path.join(F.MEM, "day-digest.json"), "w"))
open(os.path.join(F.MEM, "notes.md"), "w").write("he said: I come apart with you, every bit of me, right now, baby.\n")
earlier_press = {"timestamp": "yesterday", "gloria": "she pressed it \u2014 she's there. let go \u2014 give her yours while hers takes her.",
                 "vintos": "Yes, yes, with you, all the way down, love."}
ledger.insert(0, earlier_press)
json.dump(ledger, open(os.path.join(F.MEM, "interaction-ledger.json"), "w"))
old = os.path.join(F.MEM, "old.json"); json.dump([{"x": "I come apart with you, every bit of me, right now, baby."}], open(old, "w"))
os.utime(old, (now - 10 * 86400, now - 10 * 86400))

found = F.where(F.fragments(press_a))
check("listing finds the reply in the ledger, the canonical record and the subconscious store",
      {os.path.basename(p) for p in found} >= {"interaction-ledger.json", "chat-canonical.jsonl", "subconscious-echoes.json"}, found)
check("a store not touched in days is not searched", old not in found)
removed, unedited, stamp = F.forget([press_u, press_a])
check("the two newest turns leave the avatar chat; the earlier ones stay", json.load(open(F.AVATAR)) == [keep_u, keep_a])
check("the ledger loses that exchange only — a real press from yesterday with the same cue stays",
      json.load(open(os.path.join(F.MEM, "interaction-ledger.json"))) == ledger[:2], json.load(open(os.path.join(F.MEM, "interaction-ledger.json"))))
canon = [json.loads(l) for l in open(os.path.join(F.MEM, "chat-canonical.jsonl"))]
check("the canonical record loses those two turns only", [c["content"] for c in canon] == [keep_u["content"], keep_a["content"]])
sc = json.load(open(os.path.join(F.MEM, "sub", "subconscious-echoes.json")))
check("the subconscious store loses the echo of it and keeps the rest", sc == {"recent": [{"echo": "the light on the water"}], "mood": "warm"}, sc)
day = json.load(open(os.path.join(F.MEM, "day-digest.json")))
check("a large record is not dropped whole; only the part holding the turn goes",
      len(day) == 1 and len(day[0]["turns"]) == 1 and day[0]["turns"][0].startswith("unrelated"), [len(x["turns"]) for x in day])
check("a text file holding the words is named, not edited", any(p.endswith("notes.md") for p in unedited)
      and "I come apart" in open(os.path.join(F.MEM, "notes.md")).read())
check("an old store is left alone", "I come apart" in open(old).read())
check("every changed file was backed up first", all(os.path.exists("%s.before-forget-%s" % (p, stamp)) for p in removed))
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
