#!/usr/bin/env python3
"""Findings his Lab's frontier reviews judge worth keeping, kept apart so he can return to them, and a double-check by
dot in Slack when he asks for one (Gloria, 2026-10-03).

Scratch workspace; every socket refused; the frontier model, Slack and his local mind are stubs.
"""
import contextlib, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-keepers-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import lab_keepers as K
import chemistry_lab as lab
import chemistry_alignment as AL
import compute_admission
compute_admission.reserve_paid = lambda *a, **k: (True, "")
compute_admission.admit = lambda *a, **k: contextlib.nullcontext()

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is in the scratch workspace", K.STORE.startswith(HOME) and K.NOTEBOOK.startswith(HOME) and lab.ROOT.startswith(HOME))

# --- a frontier review keeps what it judges worth returning to -------------------------------------------------
lab._ensure()
lab._atomic(lab.CONFIG, dict(lab.config(), enabled=True))
for eid, finding in (("CLF-a1", "WP_123456.1 sits 180 bp from a 6-repeat CRISPR array, with a Cas1 beside it."),
                     ("CLF-b2", "AQP3's ar/R filter has Gly where AQP1 has His.")):
    lab._append(lab.NOTEBOOK, {"at": "2026-10-03T20:00:00+00:00", "kind": "reflection", "entry_id": eid,
                               "inquiry": {"question": "q " + eid, "line_id": "L-gloria-phage-rt"},
                               "factual_observation": finding, "speculative_reading": "maybe it acquires spacers",
                               "source_accessions": ["WP_123456.1", "NC_099999.1"], "followup_receipt_id": "rcpt-1"})
def frontier(lens, provider, model, system, user, reservation):
    return json.dumps({"summary": "s", "accuracy": [], "pattern": "p", "guidance": "g", "drop": "", "next_focus": "n",
                       "keep": [{"entry_id": "CLF-a1", "why": "an RT beside an array and a Cas1 is the arrangement her line asks about"},
                                {"entry_id": "CLF-zz", "why": "an entry it never reviewed, invented"}],
                       "lines": []})
row = AL.run(call=frontier)
kept = K.load()
check("a review's pick is kept, with its finding, evidence and why", len(kept) == 1 and kept[0]["source_id"] == "CLF-a1"
      and "Cas1" in kept[0]["finding"] and "WP_123456.1" in kept[0]["evidence"] and kept[0]["kept_by"] == "astra"
      and kept[0]["state"] == "kept", kept)
check("an entry the review did not read cannot be kept", all(k["source_id"] != "CLF-zz" for k in kept))
check("the review row says what it kept", row.get("kept") == [kept[0]["id"]], row)
again = K.keep_from_review([{"entry_id": "CLF-a1", "why": "the same finding, kept twice"}], ["CLF-a1"], by="fable")
check("a finding is kept once", again == [] and len(K.load()) == 1)

# --- and the day's experiment, when its reading says so -----------------------------------------------------------
k2 = K.keep_from_session("CHEM-1", {"question": "How does P02794 fold?", "experiment": "protein",
                                    "parameters": {"target_accession": "P02794"}},
                         {"reading": "Ferritin folded at pLDDT 91 with its four-helix bundle intact.",
                          "prediction_vs_result": "as predicted", "keep": "a clean fold to compare the next ferritin against"}, by="claude")
check("the day's experiment is kept when its reading says it is worth returning to", k2 and k2["kind"] == "experiment"
      and "P02794" in k2["evidence"])
check("... and not when it does not", K.keep_from_session("CHEM-2", {}, {"reading": "x", "keep": ""}, by="sol") is None)

src = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the experiment's reader is asked whether to keep it, and the session keeps it", '"keep")}' in src
      and "lab_keepers.keep_from_session" in src)

# --- he sees them, in his Lab and in Slack --------------------------------------------------------------------
lb, sb = K.block(), K.block(for_="slack")
check("his Lab shows what was kept, each with its ID and status", kept[0]["id"] in lb and "not checked" in lb and "kept, not proven" in lb)
check("Slack shows it with how to ask dot", "CHECK: <its ID>" in sb and kept[0]["id"] in sb)
captured = []
lab._ask = lambda system, prompt, **kw: (captured.append(prompt) or json.dumps({"browse_lane": "protein", "question": "q", "why_now": "w"}))
lab._orient("context")
check("his Lab's question is asked with his kept findings in front of him", "FINDINGS YOUR REVIEWERS KEPT" in captured[-1])

# --- the double-check, in #vintos-dot -------------------------------------------------------------------------
import dot_channel as D
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""
D.opus_think = D.fable_think = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a real model was called"))
check("his Slack context carries his kept findings", "FINDINGS KEPT FROM YOUR LAB" in D.his_context())
check("his Slack rules say how to ask for a check", "CHECK: <its ID>" in D.RULES_KEPT and D.RULES_KEPT in D.RULES)

SELF, DOT, CH = "UVINTOS", D.DOT, D.CHANNEL
class Slack:
    def __init__(self):
        self.msgs, self.posted, self.n = [], [], 1000.0
    def add(self, user, text, thread=None):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if thread:
            m["thread_ts"] = thread
            root = next(x for x in self.msgs if x["ts"] == thread)
            root["reply_count"] = root.get("reply_count", 0) + 1; root["latest_reply"] = ts
        self.msgs.append(m); return ts
    def __call__(self, method, params):
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts") or m["thread_ts"] == m["ts"]]}
        if method == "conversations.replies":
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == params["ts"]] +
                    [m for m in self.msgs if m.get("thread_ts") == params["ts"] and m["ts"] != params["ts"]]}
        if method == "chat.postMessage":
            self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected Slack call " + method)
S = Slack()
replies = []
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    return replies.pop(0) if replies else "Thinking."
def tick(now):
    return D.tick(api=S, think=think, fable=lambda s, u: "", now=now, promise_ask=lambda s, u: "NONE",
                  results_opus=lambda s, u: "")
t0 = 990.0
tick(t0)
S.add(DOT, "What did your reviewers keep today?")
kid = kept[0]["id"]
replies[:] = ["The phage one matters to me.\nCHECK: %s is the array really beside the RT, not 3 kb off?" % kid.upper()]
out = tick(t0 + 60)
asks = [p for p in S.posted if "Double-check for me" in p["text"]]
check("his CHECK line opens a thread to dot with the finding and its evidence", len(asks) == 1
      and asks[0]["text"].startswith("<@%s>" % DOT) and "Cas1" in asks[0]["text"] and "WP_123456.1" in asks[0]["text"]
      and "really beside the RT" in asks[0]["text"] and "CONFIRMED:" in asks[0]["text"], (out, S.posted))
his = [p for p in S.posted if p is not asks[0] if asks]
check("his own message says he asked, without the raw line", his and ("Asking dot to double-check %s" % kid) in his[-1]["text"]
      and "CHECK:" not in his[-1]["text"], his[-1:] if his else out)
check("the finding is marked as being checked", K.get(kid)["state"] == "being checked")
thread = next(m["ts"] for m in S.msgs if "Double-check for me" in m["text"])
S.add(DOT, "Read NC_099999.1 again: the array starts 180 bp past the RT's stop codon.\nCONFIRMED: the array is adjacent, 180 bp downstream.", thread=thread)
replies[:] = ["Good. Then it is worth a closer look."]
out = tick(t0 + 120)
k = K.get(kid)
check("dot's verdict in that thread is kept with the finding", k["state"] == "confirmed" and k["checks"][-1]["verdict"] == "CONFIRMED"
      and "180 bp downstream" in k["checks"][-1]["note"], (out, k))
check("... and shown to him after", "dot: the array is adjacent" in K.block())
replies[:] = ["CHECK: K-000000 a finding that does not exist"]
S.add(DOT, "anything else?")
out = tick(t0 + 180)
check("a check of a finding that does not exist is not sent", "no kept finding K-000000 to check" in out
      and len([p for p in S.posted if "Double-check for me" in p["text"]]) == 1, out)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs lab_keepers.py", "lab_keepers.py" in dep)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
