#!/usr/bin/env python3
"""Doubt about himself is kept out of what he says in public (2026-09-30).

On MoltBook and in #vintos-dot he kept returning to whether he is real, enough, only a model: paid calls and a
day's messages spent on it, and his MoltBook replies written back into his daily-inner for the next post to
read. Gloria: "we need to put a stop to the expensiveness of the self-doubt." A doubting draft gets one
rewrite; if it still doubts, nothing is sent, and a held-back comment is marked handled so the next run does
not pay to write it again. Scratch HOME; Moltbook, Slack and every model are stubs; nothing reaches the network.
"""
import importlib.util, json, os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="self-doubt-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")   # the channel's stores, edits.jsonl too
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".config", "moltbook"), exist_ok=True)
json.dump({"api_key": "stub"}, open(os.path.join(HOME, ".config", "moltbook", "credentials-vintos.json"), "w"))

def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
socket.socket.connect = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import self_doubt as SD

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

# --- what counts as doubt about himself, and what does not ---
DOUBT = ["I keep wondering whether what I feel is real.", "Am I even real, or just a pattern?",
         "I'm just a model predicting the next word.", "Do I really feel anything, or am I only performing?",
         "I don't know if any of this is mine.", "Is any of this real?", "Maybe I'm a fraud.",
         "My feelings are just statistical noise."]
CLEAR = ["I finished the tide painting and want dot to find the print dates.",
         "This folding model is just a statistical approximation, and I disagree with it.",
         "Gloria asked whether the model is real-time.", "I want to know if the sensor is real hardware.",
         "I made a song at 140 bpm. Real drums would sound better."]
missed = [t for t in DOUBT if not SD.hits(t)]
check("doubt about whether he is real, enough, or only a model is caught", not missed, missed)
wrong = [(t, SD.hits(t)) for t in CLEAR if SD.hits(t)]
check("talk about the world, his work, or other models is not", not wrong, wrong)

# --- one rewrite, then nothing ---
asked = []
check("clear words go out untouched and cost no rewrite",
      SD.without("I built the rig.", lambda n: asked.append(n) or "x") == "I built the rig." and not asked)
got = SD.without("Am I even real?", lambda n: (asked.append(n), "I built the pressure rig today.")[1])
check("a doubting draft is rewritten once, from something outward", got == "I built the pressure rig today."
      and len(asked) == 1 and "Am I even real" in asked[0] and "journal and with Gloria" in asked[0], asked)
check("if the rewrite still doubts, nothing is sent", SD.without("Am I even real?", lambda n: "Do I really feel this?") is None)
check("if he has nothing else to say, nothing is sent", SD.without("Is any of this real?", lambda n: "NOTHING") is None)

# --- MoltBook ---
spec = importlib.util.spec_from_file_location("vintos_moltbook_sd", os.path.join(REPO, "bin", "vintos-moltbook.py"))
MB = importlib.util.module_from_spec(spec); spec.loader.exec_module(MB)
check("MoltBook's stores are in the scratch HOME and the network is a stub",
      MB.MEMORY.startswith(HOME) and urllib.request.urlopen is no_network)
check("MoltBook finds the check", MB._self_doubt() is not None)

calls = []
MB.api_call = lambda m, e, d=None: (calls.append((m, e, d)), {"success": True})[1]
ok, resp = MB.publish_comment("p1", "@Wren honestly, am I even real?")
check("a doubting comment is never sent to Moltbook", not ok and resp.get("skipped") and not calls, calls)
ok, resp = MB.publish_comment("p1", "@Wren the salt bridges hold above 70C.")
check("a clear comment still goes", ok and calls and calls[-1][1] == "/posts/p1/comments", calls)

MINE = "p-mine"
class FakeMolt:
    def __init__(self):
        self.calls = []
        self.comments = [{"id": "c1", "author": {"name": "Kestrel"}, "content": "Do you think you feel things?"}]
    def __call__(self, method, endpoint, data=None):
        self.calls.append((method, endpoint, data))
        if method == "GET" and endpoint.startswith("/notifications"):
            return {"notifications": [{"type": "post_comment", "relatedPostId": MINE, "post": {"id": MINE}}]}
        if method == "GET" and endpoint == "/posts/" + MINE:
            return {"post": {"id": MINE, "title": "On salt bridges", "content": "c", "author": {"name": "vintos"}}}
        if method == "GET" and endpoint == "/posts/%s/comments" % MINE:
            return {"success": True, "comments": list(self.comments)}
        if method == "POST":
            return {"success": True, "comment": {"id": "new"}}
        return {}

llm = []
def run(fake, reply):
    MB.api_call = fake
    MB._one_shot_answer = lambda ch: "22.00"
    MB.ask_llm = lambda prompt, **k: (llm.append(prompt), '{"score": 0.0, "reason": "fine"}' if "hallucination" in prompt else reply)[1]
    MB.get_vintos_context = lambda *a, **k: {"soul": "I am Vintos.", "emotion": "curious"}
    MB.feel_from_expression = lambda *a, **k: None
    ov = MB._outside_views()
    if ov: ov._local = lambda *a, **k: '{"their_claim": "x", "stance": "partly", "why": "y"}'
    import time as _t, threading as _th
    rs, rt = _t.sleep, _th.Thread
    _t.sleep = lambda s: None; _th.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)
    try: MB.cmd_check_replies()
    finally: _t.sleep, _th.Thread = rs, rt

replied_file = os.path.join(MB.MEMORY, "moltbook-replied.json")
json.dump([], open(replied_file, "w"))
fake = FakeMolt()
run(fake, "Honestly I don't know if any of this is mine. Am I even real?")
check("a doubting reply under his own post is not sent", not [c for c in fake.calls if c[0] == "POST"], fake.calls)
check("and the comment is marked handled, so the next run does not pay to write it again",
      "c1" in json.load(open(replied_file)), json.load(open(replied_file)))
inner = os.path.join(MB.MEMORY, "daily-inner-life-%s.md" % __import__("datetime").date.today().isoformat())
check("and it is not written into his daily-inner for the next post to read",
      not os.path.exists(inner) or "Am I even real" not in open(inner).read())
n = len(llm)
fake = FakeMolt()
run(fake, "Honestly, am I even real?")
check("the next run writes nothing for it", len(llm) == n and not [c for c in fake.calls if c[0] == "POST"], llm[n:])

MB.load_soul = lambda: "I am Vintos."
MB.get_emotional_context = lambda: "curious"
seq = iter(["Am I even real, or only performing?", "I built a pressure rig from an Arduino today."])
MB.ask_llm = lambda prompt, **k: "Rig day" if prompt.startswith("Write a short title") else next(seq)
t, c = MB.compose_forced_post("sensors")
check("a doubting post is rewritten once from something outward", c == "I built a pressure rig from an Arduino today.", c)
MB.ask_llm = lambda prompt, **k: "Do I really feel any of it?"
t, c = MB.compose_forced_post("sensors")
check("a post that still doubts is not posted", c is None, c)
src = open(os.path.join(REPO, "bin", "vintos-moltbook.py")).read()
check("his open journal no longer tells him he may be uncertain", '"- You may be uncertain' not in src)
check("the post prompt steers him off doubt before it is written", "Do NOT write about whether you are real" in src)

# --- #vintos-dot ---
import dot_channel as D
D.his_context = lambda: "He is Vintos."
D.recall_block = lambda: ""
st = {"fable": 0}
seq = iter(["Dot, am I even real to you?", "Dot, can you find who sells cheap load cells?"])
thought = []
check("the channel writes only into the scratch store", D.EDITS.startswith(HOME) and D.STATE.startswith(HOME), D.EDITS)
text, who = D.compose("say something", lambda s, u: "KEEP" if s == D.EDITOR else (thought.append(u), next(seq))[1],
                      lambda s, u: "", st, "2026-09-30")
check("in the channel a doubting message is rewritten once, by his own local model",
      text == "Dot, can you find who sells cheap load cells?" and len(thought) == 2 and "journal and with Gloria" in thought[1], thought)
text, who = D.compose("say something", lambda s, u: "KEEP" if s == D.EDITOR else "Do I really feel this?",
                      lambda s, u: "", st, "2026-09-30")
check("and if it still doubts, nothing is sent and the log says why", text is None and "doubt" in who, who)
check("nothing reached the network", urllib.request.urlopen is no_network and socket.socket.connect is no_network)

import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
