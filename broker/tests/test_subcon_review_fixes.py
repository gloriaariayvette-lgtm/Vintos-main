#!/usr/bin/env python3
"""Three fixes from Chat's subconscious review (16 October), in a scratch workspace with no model and no network:
her words apart from a photo's or video's composed description; presence's "recent" by when a reply was said; and no
"what lands" pattern served without evidence."""
import json, os, sys, tempfile, types
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="subcon-fixes-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
CALLS = []
def no_network(*a, **k): CALLS.append(a); raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import her_words as H, presence_audit as PA, withheld_head as WH, mutual_simulation as MS
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:300]) if d and not ok else ""))
check("every store is scratch", all(p.startswith(HOME) for p in (PA.CHAT, PA.OUT, WH.CHAT, MS.OUT, MS.AUDIT)))

print("--- her words ---")
photo = {"role": "user", "content": "[Gloria sent you a photo. What your eyes saw:]\nA kitchen counter, a red mug.\n\n"
                                    "[Gloria's message with the photo:] look what I made"}
check("an old photo row gives her message, not the description", H.her_words(photo) == ("look what I made", "photo"))
check("as her turn, the photo is named and not described", H.as_her_turn(photo) == "(she sent a photo) look what I made")
video = {"role": "user", "content": "[Gloria sent you a video, 12 seconds long.]\n[What your eyes saw, across the clip:]\n"
                                    "a beach\n[Gloria's message with the video:] ", "input_kind": "video",
         "original_text": "[Gloria sent you a video without a message]"}
check("a video sent without a message has no words of hers", H.her_words(video) == ("", "video"))
check("an ordinary turn is her words as they are", H.her_words({"role": "user", "content": "I remembered the vegetables."})
      == ("I remembered the vegetables.", "text"))
check("his own turn is not hers", H.her_words({"role": "assistant", "content": "hi"}) == ("", ""))
merge = open(os.path.join(REPO, "scripts", "build_merged_chat.py")).read()
check("the merge carries what she sent and her own words", '"input_kind", "original_text"' in merge)
json.dump([{"role": "user", "content": "x", "timestamp": "2026-10-15T07:00:00"}, photo,
           {"role": "assistant", "content": "It's lovely.", "timestamp": "2026-10-15T07:01:00"}], open(WH.CHAT, "w"))
check("withheld reads her words, not the photo's description", WH._last_exchange() == ("(she sent a photo) look what I made", "It's lovely."),
      WH._last_exchange())

print("--- presence: recent is when it was said ---")
now = datetime.now()
old, new = (now - timedelta(days=60)).isoformat(), (now - timedelta(hours=2)).isoformat()
json.dump([{"role": "user", "content": "hello", "timestamp": old}, {"role": "assistant", "content": "an August reply", "timestamp": old},
           photo | {"timestamp": new}, {"role": "assistant", "content": "a reply today", "timestamp": new}], open(PA.CHAT, "w"))
seen = []
PA.score = lambda um, reply, ts: (seen.append((um, reply)) or {"arrived": .6, "moved": .6, "left_alive": .6, "explained": .2,
                                                               "composite": 0.6, "note": "n"})
json.dump([{"id": "old1", "timestamp": old, "audited_at": now.isoformat(), "composite": 0.1}], open(PA.OUT, "w"))
PA.main()
audits = json.load(open(PA.OUT))
check("a reply older than the window is not audited now", [r for _u, r in seen] == ["a reply today"], seen)
check("it is scored against her words, not the photo's description", seen and seen[0][0] == "(she sent a photo) look what I made", seen)
check("an old reply audited lately leaves the recent set", [a.get("id") for a in audits if a.get("id") == "old1"] == [], audits)

print("--- mutual simulation: what lands needs evidence ---")
json.dump([{"composite": 0.65, "note": "described the room", "arrived": .5, "moved": .5, "left_alive": .5, "explained": .3, "ts": i}
           for i in range(10)], open(MS.AUDIT, "w"))
MS.main()
out = json.load(open(MS.OUT))
check("with nothing that landed, no model is asked and nothing is said to land",
      out["what_works"] == [] and not out["works_eligible"] and not CALLS, (out, CALLS))
check("the hint says nothing about what lands", "land lately" not in MS.get_interaction_hint(), MS.get_interaction_hint())
json.dump({"what_works": ["teasing back"], "hint_id": "x", "edge_note": "e"}, open(MS.OUT, "w"))
check("a stored pattern without its evidence is not served", "teasing back" not in MS.get_interaction_hint())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
