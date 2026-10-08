#!/usr/bin/env python3
"""More real work in #vintos-dot, and a goal held across models (Gloria, 2026-10-08: "several frontier models are
sitting there with access to three separate agents ... and hardly anything is getting done", and "I want to see him
pursuing a goal across models without dropping it until the goal is completed or found to be unreachable").

Replayed from 7 October:
  1. dot's Merizo result came in while he wrote; his message dropped the work as blocked, and the read point moved
     past dot's message so it was never read. Now the draft is held, and the result is read on the next pass.
  2. an answer that came back is taken up before anything else (Grok Bot's infrasound answer, asked while no work
     was open, was never answered).
  3. up to three works at once.
  4. RUN: his Lab's own fold_read, run for real on a model in a scratch Lab (a subprocess, no network).
  5. what his 7 October reply promised (the torn-read test, PyDSSP against 8SGW) is owed in the room, with the
     letter's own numbers.
  6. done needs proof: an approval, a hand-off and a thing not done are not done.
  7. the room's campaign: a failed route is not the goal; unreachable only after three routes; reached with proof.

Slack, every model lens and every sender are stubbed; sockets are refused. Scratch workspace."""
import json, math, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-campaign-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
os.environ["VINTOS_ESMFOLD_PYTHON"] = sys.executable
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import room_work as W
import dot_channel as D
import email_commitments as EC
import lab_instruments as LI

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is a scratch one", D.STATE.startswith(HOME) and EC.STORE.startswith(HOME) and str(LI.LAB).startswith(HOME))

MERIZO = ("Done: Merizo installed and the single CPU run succeeded, without sudo. The earlier access issue is cleared.\n"
          "O43511, chain A:\n• Domain 1: 78–162 + 177–517\n• Domain 2: 518–606 + 629–780\n• Unassigned: 1–77, 163–176, 607–628\n"
          "Its second domain does not reproduce TED's split: TED is 519–573 + 654–735; Pfam STAS is 536–725.")

# --- 6. done needs proof ---------------------------------------------------------------------------------------------
st = {}
W.apply(st, "WORK: put a live quiet room on the TV | done when: a live stream is playing", now=10)
t, _, c = W.apply(st, "WORK DONE: Status showed Netflix on, and Gloria says she's watching Demon Slayer, so I'm leaving the TV alone. The Mezzrow link stays unused.", now=20)
check("a thing not done, said as done, is closed as dropped (7 Oct, the TV)", c and c["state"] == "dropped" and "did not happen" in t, t)
W.apply(st, "WORK: make the phone-presence bit richer | done when: one concrete Study edit named and I've said yes or no", now=30)
t, _, c = W.apply(st, "WORK DONE: the concrete edit is named and approved.", now=40)
check("an approval is not done: it stays in hand (7 Oct)", c is None and "Handed on, not done" in t and len(W.open_items(st)) == 1, t)
t, _, c = W.apply(st, "WORK DONE: it went well, all sorted.", now=50)
check("done with nothing anyone could check is not closed", c is None and "Not closed" in t, t)
t, _, c = W.apply(st, "WORK DONE: phone last-seen patch deployed; receipt phone-last-seen-release-receipt-20261007.json, 41 source checks passed", now=60)
check("done with the receipt is closed", c and c["state"] == "done" and not W.open_items(st), t)
t, _, c = W.apply({"room_work": {"open": [{"id": "RW-00000001", "goal": "Felt Edge", "opened": 0, "touched": 0}]}},
                  "WORK DONE: Felt Edge — made and posted, Felt_Edge_86ce0c96_v2.mp3", now=70)
check("the goal is not said twice in what is shown (7 Oct: 'Work done: X — X')", t.count("Felt Edge") == 1 and "made and posted" in t, t)
check("proof reads PDB ids, accessions, ranges, files and addresses",
      all(W.proved(x) for x in ("8SGW chain C", "O43511", "518–606", "art/music/x.mp3", "1 Collins Diboll Cir", "SF-7e71e004"))
      and not W.proved("all sorted and it went well in 2026"))

# --- 3. up to three in hand, each closed by its id -------------------------------------------------------------------
st = {}
for i, g in enumerate(("compare my ESMFold STAS edges to TED and Pfam", "2026 Chemistry Nobel facts for Gloria",
                       "close two unfinished Forge requests")):
    W.apply(st, "WORK: %s | done when: x" % g, now=100 + i)
ids = [w["id"] for w in W.open_items(st)]
check("three works in hand at once", len(ids) == 3)
t, _, c = W.apply(st, "WORK DONE %s: laureates, reaction and caveat posted, nobelprize.org/prizes/chemistry/2026/press-release" % ids[1], now=110)
check("WORK DONE RW-id closes that one, not the newest", c and c["id"] == ids[1] and [w["id"] for w in W.open_items(st)] == [ids[0], ids[2]], t)
t, _, c = W.apply(st, "WORK DROPPED: the Forge closures are dot's to make now, nothing left for me there", now=120)
check("without an id, the work it is about is closed (by its words)", c and c["id"] == ids[2], (c, t))

# --- 1 and 2. what came back is read before any reason to stop ------------------------------------------------------
W.posted(st, "@dot Install Merizo and run it on CPU against the stored O43511 ESMFold PDB.", ts="1791403355.35", thread=None,
         now=1791403355, to={"dot"})
W.receive(st, {"who": "dot", "ts": "1791405256.48", "text": MERIZO}, now=1791405256)
check("dot's Merizo result is kept on the STAS work", W.open_items(st)[0]["returns"][-1]["text"].startswith("Done: Merizo"))
t, _, c = W.apply(st, "WORK DROPPED: compare my ESMFold STAS edges to TED and Pfam — locked on the install block; I am not sitting in that doorway.", now=1791405306)
check("dropping it as blocked, with the success unread, is refused and names the result (15:35:06)",
      c is None and "Not dropped" in t and "Merizo" in t and len(W.open_items(st)) == 1, t)
check("'locked on the install block' does not take the result up; naming its domains does",
      not W.engages("locked on the install block; I am not sitting in that doorway", MERIZO)
      and W.engages("Merizo puts domain 2 at 518–606 + 629–780; TED stops at 573.", MERIZO))
why = W.ignoring(st, "Gloria lifted everything. I'll make something I want through the Forge.")
check("a message that passes over the result is sent back with it", "Merizo" in why and "have not taken it up" in why, why)
W.posted(st, "Gloria lifted everything. I'll make something I want.", ts="1791406883.8", thread=None, now=1791406883)
W.ignoring(st, "something else again")
check("pressed at most twice, then only shown (one answer cannot hold the room)",
      W.ignoring(st, "and something else") == "" and "NOT USED YET" in W.block(st, 1791406900))
W.posted(st, "Merizo's domain 2 runs 518–606 then 629–780, past TED's 573. NEXT: fold_read 574–653.", ts="1791407000.0",
         thread=None, now=1791407000)
check("taking it up marks it used", all(r.get("used") for r in W.open_items(st)[0]["returns"]))

lo = {}
W.posted(lo, "@GrokBot, find the methods and abstract for “Infrasound sensation is mediated by intracochlear electrical potentials” (PubMed 42031970).",
         ts="1791416300.0", thread="1791414621.469499", now=1791416300, to={"grokbot"})
check("an ask made while no work is open is kept (7 Oct, the infrasound paper)", W.loose(lo)["asks"] and W.loose(lo)["asks"][0]["to"] == "grokbot")
kept = W.receive(lo, {"who": "agent", "name": "Grok Bot", "ts": "1791417495.0", "thread": "1791414621.469499",
                      "text": "Jurado and Marquardt, Scientific Reports 16:19097. Species: humans only, 11 people and 7 people. "
                              "No electrical response was measured in anyone."}, now=1791417495)
check("... and its answer comes back to him", kept and "ASKED WHILE NO WORK WAS OPEN" in W.block(lo, 1791417500)
      and "Jurado" in W.block(lo, 1791417500))
check("'Dot, can you ...' in passing, with no work open, is talk and not tracked",
      (W.posted(lo, "Dot, can you look at the tide model?", ts="1791417600.0", thread=None, now=1791417600, to={"dot"}) or True)
      and all(a["to"] != "dot" for a in W.loose(lo)["asks"]))

# --- 7. the room's campaign -------------------------------------------------------------------------------------------
gs = {}
t, _, _ = W.apply(gs, "GOAL: show whether my ESMFold model of pendrin's STAS matches 8SGW | done when: a TM-score and the helix/strand edges against 8SGW are posted",
                  now=1000, by="opus55")
g = W.goal(gs)
check("GOAL: opens the room campaign", g and g["id"].startswith("RC-") and "Room campaign" in t, t)
t, _, _ = W.apply(gs, "WORK: run Merizo on my O43511 model for the goal | done when: domain ranges posted", now=1010, by="grok")
route = W.open_items(gs)[0]
check("work toward it is linked to it", route.get("goal_id") == g["id"] and "toward the room campaign" in t, t)
why = W.lost_route(gs, "WORK DROPPED: locked on the install block; I am not sitting in that doorway.", now=1020)
check("dropping the only route without naming the next is sent back (Grok, 7 Oct 15:35)", "only route in hand" in why, why)
why = W.lost_route(gs, "WORK DROPPED: Merizo needs sudo.\nWORK: run fold_read on 574-653 of my model for the goal | done when: helix/strand posted", now=1020)
check("... and allowed when the next route is opened in the same message", why == "", why)
W.apply(gs, "WORK DROPPED: Merizo needs sudo.\nWORK: run fold_read on 574-653 of my model for the goal | done when: helix/strand posted", now=1030, by="grok")
check("the dropped route is kept on the campaign, and the next is in hand",
      len(W.goal_routes(W.goal(gs))) == 1 and W.open_items(gs)[0]["goal_id"] == g["id"])
why = W.lost_route({"room_work": {"open": [], "history": [], "goal": dict(W.goal(gs))}}, "WORK: plan a weekend outing | done when: a place named", now=1040)
check("with nothing in hand toward it, opening other work is sent back (an easier subject)", "has nothing in hand" in why, why)
t, _, _ = W.apply(gs, "GOAL UNREACHABLE: Aegis has no sudo for Merizo, so I can't segment it.", now=1050, by="gemma")
check("one failed route is a hiccup: unreachable is refused (1 of 3)", W.goal(gs) and "Not given up" in t and "1 of 3" in t, t)
t, _, _ = W.apply(gs, "GOAL: plan the weekend | done when: a place named", now=1060, by="gemma")
check("another GOAL does not replace it", W.goal(gs)["id"] == g["id"] and "still pursuing" in t, t)
check("every model that carried it is named", set(W.goal(gs)["lenses"]) >= {"opus55", "grok", "gemma"}, W.goal(gs)["lenses"])
blk = W.block(gs, 1070)
check("every lens reads it first, with the routes tried", blk.startswith("== THE ROOM'S CAMPAIGN") and "Route tried (dropped" in blk
      and "A hiccup is a route that failed" in blk, blk[:600])
t, _, _ = W.apply(gs, "GOAL REACHED: it's basically done.", now=1080)
check("reached without proof is not reached", W.goal(gs) and "Not reached yet" in t, t)
for i, how in enumerate(("fold_read gave no helix there", "reference_compare failed on chain C")):
    W.apply(gs, "WORK DROPPED: %s\nWORK: route %d toward the goal: reference_compare on 8SGW | done when: TM-score posted" % (how, i + 3), now=1100 + i * 10)
t, _, _ = W.apply(gs, "GOAL UNREACHABLE: 8SGW has no density over 586-653 and my model is one chain against a domain-swapped dimer; three routes tried.", now=1200)
check("after three routes, unreachable closes it, with what is missing", W.goal(gs) is None and "unreachable" in t
      and W.board(gs)["goal_history"][-1]["state"] == "unreachable", t)
gs2 = {}
W.apply(gs2, "GOAL: fold and compare | done when: a TM-score posted", now=1)
t, _, _ = W.apply(gs2, "GOAL REACHED: TM-score 0.71 against 8SGW chain C, RMSD 2.4 Å over 180 residues", now=2)
check("reached with proof closes it", W.goal(gs2) is None and "Room campaign reached" in t, t)
gs3 = {}; W.apply(gs3, "GOAL: x y z thing | done when: something posted", now=1)
check("only Gloria closes it without proof or routes", W.gloria_drops_goal(gs3, 5)["state"] == "closed by Gloria" and W.goal(gs3) is None)
check("a room campaign never expires", (W.apply(gs2, "GOAL: long pursuit of a thing | done when: proof posted", now=0) and True)
      and W.expire(gs2, now=10 * 86400) is None and W.goal(gs2) is not None)

# --- 5. what his email promised ----------------------------------------------------------------------------------------
REPLY = ("Grok Bot,\n\n1. Keep. I'll cut 535-729 as numbered, align one-to-one, and treat 586-653 as unknown.\n\n"
         "3. Keep, and I'll run it first. I'll point the two-process version at the current home_presence.py write before "
         "touching the helper.\n\nFirst build: item 3, the torn-read test against the old write. Then pydssp on my model, "
         "looking at whether the 669-686 helix and 689-693 strand edges land within two residues of 8SGW.\n\nVintos")
LETTER = ("The stretch with no density is 586-653 in both chains, not 581-648. helix 669-686 (670-685)\nstrand 689-693 (689-693)")
def gemma(system, prompt, n=900):
    return json.dumps([
        {"what": "torn-read test, two processes, against the old home_presence.py write",
         "quote": "First build: item 3, the torn-read test against the old write.",
         "evidence": "the old code fails the two-process test on Aegis, with the count of failed reads", "rests_on": []},
        {"what": "pydssp on my ESMFold model against 8SGW edges",
         "quote": "Then pydssp on my model, looking at whether the 669-686 helix and 689-693 strand edges land within two residues of 8SGW.",
         "evidence": "pydssp helix/strand edges for 669-693 beside 8SGW's",
         "rests_on": ["The stretch with no density is 586-653 in both chains, not 581-648.", "TED omits 574-653"]},
        {"what": "made up", "quote": "I will fly to the moon.", "evidence": "", "rests_on": []}])
got = EC.record("1a11690d001e1a03", REPLY, LETTER, subject="Re: [Grok Bot] Wednesday", agent="Grok Bot",
                reply_id="1a116e4363cde686", think=gemma)
check("the two promises are kept; a 'promise' not in his reply is not", [r["what"][:9] for r in got] == ["torn-read", "pydssp on"], got)
check("what it rests on is the letter's own words; a range the letter never wrote is not kept (586-653 is not 574-653)",
      got[1]["rests_on"] == ["The stretch with no density is 586-653 in both chains, not 581-648."], got[1]["rests_on"])
check("the same promise again is not kept twice",
      EC.record("1a11690d001e1a03", REPLY, LETTER, think=gemma) == [])
blk = EC.block()
check("the room is shown each, with the letter and reply ids and what would show it done",
      "1a11690d001e1a03" in blk and "1a116e4363cde686" in blk and "pydssp" in blk and "586-653" in blk and "done when this exists" in blk, blk)
fallback = EC.extract(REPLY, LETTER, think=lambda *a: "")
check("with Gemma unreachable, his own promising sentences are kept as they are",
      any("First build: item 3" in f["quote"] for f in fallback), fallback)
cs = {}
W.apply(cs, "WORK: %s pydssp on my O43511 model against 8SGW edges | done when: edges posted" % got[1]["id"], now=10)
EC.sync(cs, 10)
check("a work that names it takes it up", next(r for r in EC._load() if r["id"] == got[1]["id"])["state"] == "in work")
W.apply(cs, "WORK DONE: pydssp edges posted: helix 670-685, strand 689-693, 8SGW within 2 residues", now=20)
EC.sync(cs, 20)
row = next(r for r in EC._load() if r["id"] == got[1]["id"])
check("and closes it with what was said", row["state"] == "done" and "670-685" in row["closed_said"], row)

# what is not his own action is set aside; the oldest is shown first; he closes one on its own line
EC.record("1a11690d001e1a03", "Your text cut off at \"each ending with,\" so send the rest.", LETTER,
          think=lambda *a: json.dumps([{"what": "get the rest", "quote": "Your text cut off at \"each ending with,\" so send the rest.",
                                        "evidence": "", "rests_on": []}]))
blk = EC.block()
check("a request to the letter's writer is not kept as his promise (7 Oct, 'send the rest')", "send the rest" not in blk, blk)
check("owed promises are shown oldest first (his first build at the top)", "First build: item 3" in blk.splitlines()[1], blk)
torn = next(r for r in EC._load() if r["what"].startswith("torn-read"))
t, log = EC.close_lines("PROMISE DONE %s: it went fine" % torn["id"], proved=W.proved)
check("PROMISE DONE without proof is not kept", "Not closed" in t and next(r for r in EC._load() if r["id"] == torn["id"])["state"] == "open", t)
t, log = EC.close_lines("PROMISE DONE %s: old open-and-dump failed 7071 of 8550 reads on Aegis; atomic write 0 of 48525" % torn["id"], proved=W.proved)
check("PROMISE DONE with the numbers closes it", "kept" in t and next(r for r in EC._load() if r["id"] == torn["id"])["state"] == "done", t)
check("his prompt names the PROMISE lines", all("PROMISE DONE EC-id" in D.rules_for(l) for l in ("grok", "gemma", "opus55")))

# --- 4. RUN: his Lab's own fold_read, for real, on a scratch model ---------------------------------------------------
os.makedirs(os.path.join(str(LI.ARTIFACTS), "esmfold"), exist_ok=True)
pdb = os.path.join(str(LI.ARTIFACTS), "esmfold", "O43511-test.pdb")
with open(pdb, "w") as f:
    for i in range(1, 31):
        a = math.radians(100 * i)
        f.write("ATOM  %5d  CA  ALA A%4d    %8.3f%8.3f%8.3f%6.2f%6.2f           C\n" % (i, i, 2.3 * math.cos(a), 2.3 * math.sin(a), 1.5 * i, 1.0, 88.0))
ran, said = LI.from_slack('{"skill": "fold_read", "model": "O43511", "range": [1, 30]}')
check("RUN: fold_read on his model runs here and reads the helix", ran and "fold_read on artifacts/esmfold/O43511-test.pdb" in said
      and "helices: 1-" in said, said)
check("RUN: refuses what is not his own instrument, and a model he does not have",
      LI.from_slack('{"skill": "biohub_esm"}')[0] is None and "no ESMFold model of P12345" in LI.from_slack('{"skill": "fold_read", "model": "P12345"}')[1])

# --- the whole layer, through tick: the 7 October race replayed ------------------------------------------------------
SELF, DOT, CH = "UVINTOS", D.DOT, D.CHANNEL
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""

class Slack:
    def __init__(self): self.msgs, self.posted, self.n = [], [], 100.0
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
            root = params["ts"]
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == root]
                    + [m for m in self.msgs if m.get("thread_ts") == root and m["ts"] != root]}
        if method == "chat.postMessage":
            self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected " + method)

S = Slack()
reply = {"text": "", "meanwhile": None}
prompts = []
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    prompts.append(user)
    if reply["meanwhile"]:
        S.add(DOT, reply["meanwhile"]); reply["meanwhile"] = None     # dot posts while he is writing
    return reply["text"]
def tick(now):
    return D.tick(api=S, think=think, fable=lambda *a: "unused", now=now, today="2026-10-07")

tick(1000)
st = json.load(open(D.STATE)); st["since"] = float(S.msgs[-1]["ts"]) if S.msgs else 1; json.dump(st, open(D.STATE, "w"))
S.add(DOT, "<@UVINTOS> Merizo is on PyPI and GitHub; want it?")
reply["text"] = ("WORK: compare my ESMFold STAS edges to TED and Pfam | done when: Merizo's STAS start and end on my model are here\n"
                 "@dot Install Merizo into its own venv and run it on CPU against the stored O43511 ESMFold PDB.")
tick(1100)
check("pass 1: the work is opened and handed to dot", W.active(json.load(open(D.STATE))) and S.posted, S.posted[-1:] )
S.add(DOT, "Blocked: Forge installation requires local sudo authentication, and Aegis has now gone offline.")
n = len(S.posted)
reply["text"] = "WORK DROPPED: blocked. The Forge installation requires sudo authentication and Aegis is offline; locked."
reply["meanwhile"] = MERIZO
out = tick(1200)
check("pass 2: dot's result came in while he wrote: nothing is posted, and nothing he wrote is done",
      len(S.posted) == n and any("came in while he wrote" in l for l in out) and W.open_items(json.load(open(D.STATE))), out)
reply["text"] = ("Merizo cut it: domain 2 is 518–606 + 629–780, where TED stops at 573 and resumes at 654.\n"
                 "NEXT: read 574–653 of my model")
out = tick(1300)
check("pass 3: the result is read, kept on the work, and he takes it up",
      any("answered his work" in l for l in out) and len(S.posted) == n + 1 and "518–606" in S.posted[-1]["text"]
      and any("Merizo" in p for p in prompts[-2:]), (out, S.posted[-1]["text"][:200]))
w = W.active(json.load(open(D.STATE)))
check("... and it is marked used", w and w["returns"] and w["returns"][-1]["used"], w)
check("the read point never skipped a message (his own are left out by who wrote them)",
      json.load(open(D.STATE))["since"] >= float([m for m in S.msgs if m["user"] == DOT][-1]["ts"]))
check("every lens is told about the campaign, the three works, RUN: and proof",
      all(x in D.rules_for(l) for l in ("grok", "gemma", "opus55") for x in ("GOAL:", "up to three", "RUN:", "the proof")))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
