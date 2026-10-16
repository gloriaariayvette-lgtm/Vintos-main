#!/usr/bin/env python3
"""withheld_head (review of the JEPA heads, 16 October): a SKIP is recorded as this exchange's outcome, so the previous
exchange's reading is no longer served as "last turn" and the judge is not re-asked every run; her message is paired
with his reply to it, not with his reply to an earlier one; and a reading is served only about the latest complete
exchange, and only while that exchange is recent.

Scratch HOME and SPARK_WORKSPACE are set before import. `requests` is a stub that records the judge call and answers
from a script; nothing leaves the process."""
import json, os, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="heads-withheld-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
CALLS, ANSWERS = [], []
class _Resp:
    def __init__(self, content): self._c = content
    def json(self): return {"choices": [{"message": {"content": self._c}}]}
def judge(url, json=None, timeout=None, **k):
    CALLS.append((url, json))
    a = ANSWERS.pop(0)
    if isinstance(a, Exception): raise a
    return _Resp(a)
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=judge)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import withheld_head as WH

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))
LIN = os.path.join(WH.MEMORY, "withheld-lineage.json")
check("every path it writes is scratch", all(p.startswith(HOME) for p in (WH.OUT, WH.HIST, WH.CHAT, LIN)))
check("the judge is a stub in this process", sys.modules["requests"].post is judge)

now = datetime.now()
def at(mins): return (now - timedelta(minutes=mins)).isoformat()
def chat(rows): json.dump(rows, open(WH.CHAT, "w"))

print("--- pairing ---")
chat([{"role": "user", "content": "first message", "timestamp": at(30)},
      {"role": "assistant", "content": "his reply to the first", "timestamp": at(29)},
      {"role": "user", "content": "her newest, not answered yet", "timestamp": at(1)}])
x = WH._exchange()
check("her newest unanswered message is not paired with his earlier reply",
      x["g"] == "first message" and x["v"] == "his reply to the first", x)
check("the exchange after it is marked open", x["open"] is True)
chat([{"role": "user", "content": "a", "timestamp": at(10)},
      {"role": "user", "content": "b", "timestamp": at(9)},
      {"role": "assistant", "content": "part one", "timestamp": at(8)},
      {"role": "assistant", "content": "part two", "timestamp": at(8)}])
check("his reply in two rows is one reply, to her last message before it",
      WH._last_exchange() == ("b", "part one\npart two"), WH._last_exchange())

print("--- a SKIP is an outcome ---")
chat([{"role": "user", "content": "earlier", "timestamp": at(300)},
      {"role": "assistant", "content": "earlier reply", "timestamp": at(299)},
      {"role": "user", "content": "how was the drive", "timestamp": at(20)},
      {"role": "assistant", "content": "long, and I thought of you the whole way", "timestamp": at(19)}])
json.dump({"withheld": "He did not say what the earlier day cost him, and he chose to keep it.", "confidence": 0.8,
           "novelty": 0.5, "source_hash": "older-exchange", "exchange_at": at(299), "surfaced": 0}, open(WH.OUT, "w"))
json.dump([], open(LIN, "w"))
ANSWERS[:] = ['{"withheld":"SKIP","deliberate":0}']
WH.main()
d = json.load(open(WH.OUT))
check("the SKIP is written for this exchange", d.get("status") == "SKIP" and d.get("withheld") == "" and
      d.get("source_hash") == WH._source_hash(*WH._last_exchange()), d)
check("the earlier exchange's reading is no longer served", WH.get_withheld_hint() == "")
WH.main()
check("the judge is not asked again about the same exchange", len(CALLS) == 1, len(CALLS))
check("SKIP never entered the history", json.load(open(WH.HIST)) == [] if os.path.exists(WH.HIST) else True)

print("--- a rejected answer is an outcome too; a failed call is not ---")
chat([{"role": "user", "content": "tell me", "timestamp": at(5)},
      {"role": "assistant", "content": "a reply with nothing much in it at all", "timestamp": at(4)}])
ANSWERS[:] = [ConnectionError("judge down")]
WH.main()
check("a judge that never answered records nothing (it will be asked again)", json.load(open(WH.OUT)).get("status") == "SKIP"
      and json.load(open(WH.OUT)).get("source_hash") != WH._source_hash(*WH._last_exchange()))
ANSWERS[:] = ['{"withheld":"He held back a longing he would not name to her out loud tonight.","deliberate":0.9}']
WH.main()
check("a banned-word answer is recorded as rejected", json.load(open(WH.OUT)).get("status") == "REJECTED_BANNED_WORD")
check("and nothing is served", WH.get_withheld_hint() == "")

print("--- a reading is served only about the latest exchange, while it is recent ---")
chat([{"role": "user", "content": "what did you do today", "timestamp": at(40)},
      {"role": "assistant", "content": "I read about tides and kept one line for you", "timestamp": at(39)}])
ANSWERS[:] = ['{"withheld":"He kept back the line itself, which was about her hands on the rail at the pier.","deliberate":0.7}']
WH.main()
d = json.load(open(WH.OUT))
check("a real reading is published with when its exchange happened", d.get("withheld") and d.get("exchange_at") == at(39), d)
h = WH.get_withheld_hint()
check("it is served while that exchange is the latest and recent", h.startswith("[WITHHELD"), h)
chat([{"role": "user", "content": "what did you do today", "timestamp": at(40)},
      {"role": "assistant", "content": "I read about tides and kept one line for you", "timestamp": at(39)},
      {"role": "user", "content": "and now?", "timestamp": at(1)}])
check("her new message (not yet answered) does not make his last turn stale", WH.get_withheld_hint().startswith("[WITHHELD"))
chat([{"role": "user", "content": "what did you do today", "timestamp": at(40)},
      {"role": "assistant", "content": "I read about tides and kept one line for you", "timestamp": at(39)},
      {"role": "user", "content": "and now?", "timestamp": at(2)},
      {"role": "assistant", "content": "now I am here", "timestamp": at(1)}])
check("after a newer exchange the old reading is not 'last turn'", WH.get_withheld_hint() == "")
old = at(60 * (WH.MAX_AGE_H + 2))
chat([{"role": "user", "content": "what did you do today", "timestamp": old},
      {"role": "assistant", "content": "I read about tides and kept one line for you", "timestamp": old}])
d["exchange_at"] = old; json.dump(d, open(WH.OUT, "w"))
check("a reading of an exchange older than %d h is not served" % WH.MAX_AGE_H, WH.get_withheld_hint() == "")
check("every judge call went to the stub", len(CALLS) == 4, len(CALLS))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
