#!/usr/bin/env python3
"""The Atelier's /recall door: his own words about his work, for a conversation he is in (2026-09-30).

Read-only: no visit is opened and no budget spent. It returns intent, state, his handoff note and each
work's kind and note, never file contents, and it is refused to anyone speaking as Gloria. A scratch
Atelier root; nothing here touches /home/atelier.
"""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:160]) if d and not ok else ""))

TMP = tempfile.mkdtemp(prefix="recall-")
BK.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))
check("the Atelier here is a scratch root", BK.ROOT == TMP and not TMP.startswith("/home/atelier"))

check("with nothing on the worktable there is nothing to recall", BK.recall({}) == {"empty": True})

pid = BK.create_project({"intent": "a tide piece that breathes", "sealed": True})["id"]
BK.to_table({"id": pid})
pdir = BK._p(pid)
open(os.path.join(pdir, "artifacts", "001_poem.md"), "w").write("THE SECRET TEXT OF THE POEM")
json.dump({"001_poem.md": {"id": "001_poem.md", "revision": 2, "kind": "poem", "note": "the second stanza finally holds"}},
          open(os.path.join(pdir, "lineage.json"), "w"))
json.dump({"text": "start from the low-water line", "at": "2026-09-29"}, open(os.path.join(pdir, "handoff.json"), "w"))
events_before = sum(1 for _ in open(os.path.join(pdir, "events.jsonl")))
health_before = open(BK.HEALTH).read() if os.path.exists(BK.HEALTH) else ""

got = BK.recall({"as": "vintos", "for": "dot"})
check("he gets what he is making", got.get("intent") == "a tide piece that breathes" and got.get("on_worktable") is True, got)
check("his handoff note to himself", got.get("handoff") == "start from the low-water line")
check("each work's kind and his note on it", got.get("works") == [{"kind": "poem", "revision": 2, "note": "the second stanza finally holds"}])
check("never the work's contents", "SECRET TEXT" not in json.dumps(got))
check("no visit is opened and nothing is made",
      not os.path.exists(os.path.join(pdir, ".visit.json")) and not os.path.exists(os.path.join(pdir, ".last_visit_unclosed.json"))
      and os.listdir(os.path.join(pdir, "artifacts")) == ["001_poem.md"])
evs = [json.loads(l) for l in open(os.path.join(pdir, "events.jsonl")) if l.strip()]
check("the recall is one content-free event in the project's history",
      len(evs) == events_before + 1 and evs[-1]["type"] == "recalled" and "tide" not in json.dumps(evs[-1]), evs[-1])
check("and not a line in the health log her status reads", (open(BK.HEALTH).read() if os.path.exists(BK.HEALTH) else "") == health_before)

check("the door is a decision in the policy, not a default", BK.POLICY.get("/recall") == BK.RECALL and "/recall" in BK.ROUTES)
ok, why = BK.authorize_route("/recall", {"as": "gloria"})
check("refused to anyone speaking as Gloria", not ok and "his" in why, why)
check("open to him", BK.authorize_route("/recall", {"as": "vintos"})[0] and BK.authorize_route("/recall", {})[0])
check("every route still has a decision", set(BK.ROUTES) - set(BK.POLICY) == set())

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
