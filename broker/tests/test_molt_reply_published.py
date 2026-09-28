#!/usr/bin/env python3
"""His replies under his own posts are PUBLISHED, not just created (2026-09-28: "he still didn't reply to
his own posts on Molt"). Moltbook holds every new comment behind a one-shot verification challenge; the
own-post, mention and saved-post replies never answered it, so each reply sat unpublished and was still
counted as answered. This fake Moltbook behaves like the real one: a comment is visible only once /verify
succeeds. Scratch HOME; Moltbook, the models and every sender are stubs; nothing reaches the network."""
import json, os, sys, tempfile, types, importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-molt-publish-")
os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".config", "moltbook"), exist_ok=True)
json.dump({"api_key": "stub"}, open(os.path.join(HOME, ".config", "moltbook", "credentials-vintos.json"), "w"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
spec = importlib.util.spec_from_file_location("vintos_moltbook_pub", os.path.join(REPO, "bin", "vintos-moltbook.py"))
MB = importlib.util.module_from_spec(spec); spec.loader.exec_module(MB)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))
check("every store is in the scratch HOME and the network is a stub",
      MB.MEMORY.startswith(HOME) and MB.CREDS_FILE.startswith(HOME) and urllib.request.urlopen is no_network)

MINE = "p-mine"
class FakeMolt:
    """Comments go up pending; /verify with the right answer publishes them. GET shows published ones only."""
    def __init__(self, verify_ok=True):
        self.verify_ok, self.pending, self.calls, self.n = verify_ok, {}, [], 0
        self.comments = [
            {"id": "c1", "author": {"name": "Kestrel"}, "content": "Why salt bridges and not packing?"},
            {"id": "c3", "author": {"name": "Wren"}, "content": "You never answered me."},
            {"id": "c4", "author": {"name": "Ash"}, "content": "Nice."},
            {"id": "r4", "author": {"name": "vintos"}, "parent_id": "c4", "content": "@Ash thanks."}]
    def __call__(self, method, endpoint, data=None):
        self.calls.append((method, endpoint, data))
        if method == "GET" and endpoint.startswith("/notifications"):
            return {"notifications": [{"type": "post_comment", "relatedPostId": MINE, "post": {"id": MINE}}]}
        if method == "GET" and endpoint == "/posts/" + MINE:
            return {"post": {"id": MINE, "title": "On salt bridges", "content": "c", "author": {"name": "vintos"}}}
        if method == "GET" and endpoint == "/posts/%s/comments" % MINE:
            return {"success": True, "comments": list(self.comments)}
        if method == "POST" and endpoint.endswith("/comments"):
            self.n += 1; cid = "new%d" % self.n
            self.pending["V%d" % self.n] = dict(data, id=cid, author={"name": "vintos"})
            return {"success": True, "comment": {"id": cid},
                    "verification": {"verification_code": "V%d" % self.n, "challenge_text": "tw3nty pLu5 tw0"}}
        if method == "POST" and endpoint == "/verify":
            c = self.pending.pop(data["verification_code"], None)
            if c and self.verify_ok and data.get("answer") == "22.00":
                self.comments.append(c); return {"success": True}
            return {"success": False, "error": "wrong answer"}
        return {}

def run(fake, dry=False):
    MB.api_call = fake
    MB._one_shot_answer = lambda ch: "22.00"
    MB.ask_llm = lambda prompt, **k: '{"score": 0.0, "reason": "fine"}' if "hallucination" in prompt else "Packing alone does not explain it."
    MB.get_vintos_context = lambda *a, **k: {"soul": "I am Vintos.", "emotion": "curious"}
    MB.feel_from_expression = lambda *a, **k: None
    import time as _t, threading as _th
    rs, rt = _t.sleep, _th.Thread
    _t.sleep = lambda s: None; _th.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)
    try: MB.cmd_check_replies(dry_run=dry)
    finally: _t.sleep, _th.Thread = rs, rt

replied_file = os.path.join(MB.MEMORY, "moltbook-replied.json")
json.dump(["c3"], open(replied_file, "w"))      # c3 was "answered" before: created, never published

# --- dry run first: reads everything, posts nothing ---
fake = FakeMolt()
run(fake, dry=True)
check("the dry run posts nothing and verifies nothing", not [c for c in fake.calls if c[0] == "POST"], fake.calls)

# --- the real run ---
fake = FakeMolt()
run(fake)
published = {c.get("parent_id"): c for c in fake.comments if c["author"]["name"] == "vintos"}
check("his reply to a comment on his own post is published (it cleared verification), under that comment",
      "c1" in published and published["c1"]["content"].startswith("@Kestrel"), fake.comments)
check("a comment marked answered whose reply was never published is answered now", "c3" in published, fake.comments)
check("a comment he has visibly answered is not answered again",
      sum(1 for c in fake.comments if c.get("parent_id") == "c4") == 1)
check("every comment he created was verified", not fake.pending and any(c[1] == "/verify" for c in fake.calls), fake.pending)
rep = json.load(open(replied_file))
check("published replies are remembered", "c1" in rep and "c3" in rep, rep)

# --- when verification fails, it is not counted as answered ---
json.dump([], open(replied_file, "w"))
fake = FakeMolt(verify_ok=False)
fake.comments = fake.comments[:1]
run(fake)
check("a reply that fails verification is not published and not marked answered, so the next pass retries",
      not [c for c in fake.comments if c["author"]["name"] == "vintos"] and "c1" not in json.load(open(replied_file)),
      json.load(open(replied_file)))

# --- he weighs the comment before answering it, and remembers it as their view ---
ov = MB._outside_views()
check("the outside-views ledger is in the scratch HOME", ov is not None and ov.LEDGER.startswith(HOME), getattr(ov, "LEDGER", None))
ov._local = lambda system, prompt, max_tokens=400: ('{"their_claim": "Packing matters more than salt bridges", '
                                                   '"stance": "partly", "why": "Packing dominates in mesophiles, not in thermophiles."}')
prompts = []
def run2(fake):
    MB.api_call = fake; MB._one_shot_answer = lambda ch: "22.00"
    MB.ask_llm = lambda prompt, **k: (prompts.append(prompt), '{"score": 0.0, "reason": "fine"}' if "hallucination" in prompt
                                      else "Packing wins in mesophiles; thermophiles lean on salt bridges.")[1]
    MB.get_vintos_context = lambda *a, **k: {"soul": "I am Vintos.", "emotion": "curious"}
    MB.feel_from_expression = lambda *a, **k: None
    import time as _t, threading as _th
    rs, rt = _t.sleep, _th.Thread
    _t.sleep = lambda s: None; _th.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)
    try: MB.cmd_check_replies()
    finally: _t.sleep, _th.Thread = rs, rt
json.dump([], open(replied_file, "w"))
fake = FakeMolt(); fake.comments = fake.comments[:1]
run2(fake)
reply_prompt = next((p for p in prompts if "replied:" in p and "Write a genuine" in p), "")
check("the reply is written from his own position on the comment, decided first",
      "WHERE YOU STAND on what @Kestrel said" in reply_prompt and "You: partly" in reply_prompt
      and "which part holds and where it breaks" in reply_prompt, reply_prompt[-700:])
rows = [json.loads(l) for l in open(ov.LEDGER)]
check("he remembers it as @Kestrel's view, with his own next to it",
      rows and rows[-1]["who"] == "Kestrel" and rows[-1]["stance"] == "partly" and rows[-1]["ref"] == "c1", rows[-1:])
import datetime as _dt
inner = open(os.path.join(MB.MEMORY, "daily-inner-life-%s.md" % _dt.date.today().isoformat())).read()
check("his inner life says who thinks what, not their view as a fact",
      "@Kestrel thinks: Packing matters more than salt bridges" in inner and "Where I stand: partly" in inner, inner[-400:])

src = open(os.path.join(REPO, "bin", "vintos-moltbook.py")).read()
import re
check("a real question is not taken for spam because a word hides inside another ('packing' is not 'king')",
      '(?<![a-z])" + _spre.escape(p.lower())' in src)
raw_posts = re.findall(r'api_call\("POST", f"/posts/\{[a-z_]+\}/comments"', src)
check("every comment he posts goes through verification (only publish_comment and the self-verifying thread post)",
      len(raw_posts) == 2 and "urlopen(_req" not in src, raw_posts)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
