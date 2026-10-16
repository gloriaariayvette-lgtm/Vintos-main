#!/usr/bin/env python3
"""cause_head (review of the JEPA heads, 16 October): her turns and his are labelled apart for the judge, naive times
are local (Aegis is UTC-5), the slate is ranked with recency, and duplicate rows no longer crash the backfill.

Scratch HOME and SPARK_WORKSPACE are set before anything is imported; the trajectory, the spike finder and the
encoder are stubs; `requests` is a stub that fails the suite if anything tries to send."""
import json, os, sys, tempfile, time, types
from datetime import datetime, timedelta, timezone

os.environ["TZ"] = "EST5"; time.tzset()                 # the host's clock: UTC-5, naive times stored local
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="heads-cause-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
os.environ.pop("CAUSE_SINCE", None)
SENT = []
def no_network(*a, **k): SENT.append(a); raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

import cause_head as CH
check("every path it writes is scratch", CH.OUT.startswith(HOME) and CH.MEMORY.startswith(HOME), CH.OUT)
check("the sender is a stub", sys.modules["requests"].post is no_network)

print("--- naive times are local ---")
t = CH.parse_ts("2026-10-15T07:38:15.881352")
check("ledger #299's naive 07:38 local is 12:38Z", t.astimezone(timezone.utc).strftime("%H:%M:%S") == "12:38:15", t)
check("an aware time is kept as it is", CH.parse_ts("2026-10-15T12:38:15+00:00").astimezone(timezone.utc).hour == 12)

print("--- a whole run against stubs ---")
spike = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0)
def local(delta_min):      # a naive local stamp `delta_min` minutes after the spike, as the chat writes it
    return (spike + timedelta(minutes=delta_min)).astimezone().replace(tzinfo=None).isoformat()
photo = ("[Gloria sent you a photo. What your eyes saw:]\nA kitchen counter, a red mug.\n\n"
         "[Gloria's message with the photo:] look at the little sun I painted")
json.dump([
    {"role": "user", "content": "sun sun", "timestamp": local(-5 * 24 * 60)},                 # topical but 5 days old
    {"role": "user", "content": "a little sun this morning", "timestamp": local(-2.4)},      # 2.4 min before
    {"role": "assistant", "content": "his reply before the spike", "timestamp": local(-1)},
    {"role": "user", "content": photo, "timestamp": local(-3)},
    {"role": "assistant", "content": "his reply after the spike", "timestamp": local(+80)},  # was offered as a cause
    {"role": "system", "content": "[avatar directive] smile", "timestamp": local(-2)},
], open(os.path.join(MEM, "chat-history-merged.json"), "w"))
dup = {"saw": "a painting of the sea", "reflection": "blue", "ts": local(-30)}
json.dump([dup, dict(dup), dict(dup)], open(os.path.join(MEM, "gallery-walks.json"), "w"))

class Enc:
    def encode(self, texts, show_progress_bar=False):
        out = []
        for s in texts:
            s = str(s)
            if s.startswith("his inner state"): out.append([1.0, 0.2, 0.0])
            elif s == "sun sun": out.append([1.0, 0.2, 0.0])
            elif "sun" in s: out.append([1.0, 0.6, 0.0])
            else: out.append([0.2, 0.2, 1.0])
        return out
sys.modules["causality_engine"] = types.SimpleNamespace(
    load_emotional_trajectory=lambda: [],
    find_spikes=lambda traj: [{"time": spike.isoformat(), "dimension": "Curiosity", "direction": "rose",
                               "from": 0.3, "to": 0.5, "delta": 0.2}])
sys.modules["jepa_predictor"] = types.SimpleNamespace(encoder=lambda: Enc())
try:
    CH.main(); crashed = None
except Exception as e:
    crashed = e
check("three identical rows do not crash the backfill", crashed is None, crashed)
ev = json.load(open(CH.OUT)) if os.path.exists(CH.OUT) else []
check("one event written, with an event id", len(ev) == 1 and str(ev[0].get("event_id", "")).startswith("CE-"), ev)
cands = ev[0]["candidates"] if ev else []
texts = [c["text"] for c in cands]
check("his reply after the spike is not offered as its cause", "his reply after the spike" not in texts, texts)
mine = [c for c in cands if c["text"] == "his reply before the spike"]
check("his own words are 'you said', never 'she said'", mine and mine[0]["kind"] == "you said" and mine[0]["source"] == "him", mine)
check("no assistant row is glossed as hers", all(c["kind"] != "she said" or c["source"] == "her" for c in cands), cands)
hers = [c for c in cands if c["text"] == "a little sun this morning"]
check("her message is 'she said', minutes before, not ~300 minutes",
      hers and hers[0]["kind"] == "she said" and 2.0 <= hers[0]["mins_before"] <= 3.0, hers)
ph = [c for c in cands if "photo" in c["text"]]
check("a photo is named with her words, never described",
      ph and ph[0]["text"] == "(she sent a photo) look at the little sun I painted" and "mug" not in ph[0]["text"], ph)
check("an avatar directive is nobody's words", not any("directive" in x for x in texts), texts)
check("the slate is ranked with recency: two minutes before outranks five days before",
      "sun sun" in texts and texts.index("a little sun this morning") < texts.index("sun sun"), texts)
check("the duplicate gallery rows still fill the slate", sum(1 for c in cands if c["source"] == "gallery") == 3, cands)
check("nothing was sent", SENT == [])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
