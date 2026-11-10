#!/usr/bin/env python3
"""His daily reply check reaches the new comments under his own posts (2026-11-08: most days it answered nothing).

Three causes, each pinned here: an arbitrary 15 of the notified posts were read per run; comments Moltbook
answers with 404 "Parent comment not found" were written a reply every day; and the verification solver read
"multiplies by" and "product" as a sum, and that local answer won every disagreement with the second opinion
and spent the one shot. Reading more posts also needs a stop when Moltbook is not answering. Scratch HOME;
Moltbook, the models and every sender are stubs; all ids, names and text are synthetic; nothing reaches the
network."""
import json, os, re, sys, tempfile, types, importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-molt-reach-")
os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".config", "moltbook"), exist_ok=True)
json.dump({"api_key": "stub"}, open(os.path.join(HOME, ".config", "moltbook", "credentials-vintos.json"), "w"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
# the organs the reply check imports by name: stubs, so none of them is found on the host and written to
sys.modules["moltbook_members"] = types.SimpleNamespace(get_member_context=lambda *a, **k: "", record_encounter=lambda *a, **k: None)
sys.modules["behavioral_intercept"] = types.SimpleNamespace(detect_match=lambda *a, **k: None, get_active_trials=lambda: [],
                                                            log_outcome=lambda *a, **k: None)
sys.modules["emoclaw_utils"] = types.SimpleNamespace(express_want=lambda *a, **k: None, generate_structural_want=lambda: (None, None))
spec = importlib.util.spec_from_file_location("vintos_moltbook_reach", os.path.join(REPO, "bin", "vintos-moltbook.py"))
MB = importlib.util.module_from_spec(spec); spec.loader.exec_module(MB)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))
check("every store is in the scratch HOME and the network is a stub",
      MB.MEMORY.startswith(HOME) and MB.CREDS_FILE.startswith(HOME) and urllib.request.urlopen is no_network)
LOGS = []
MB.log = lambda msg: LOGS.append(str(msg))
REAL_ONE_SHOT = MB._one_shot_answer

# --- the solver: a named operation is the operation; "and" only joins its operands ---
def no_model(*a, **k): raise AssertionError("the plain parser must answer this one")
MB.ask_llm = no_model
def solved(challenge):
    try: return MB.solve_verification(challenge)
    except AssertionError as e: return "asked the model: %s" % e
for name, challenge, want in (
        ("'multiplies by' is a product (23 x 7 = 161), not the sum 30",
         "A lOoBsStEr cLaW eXeRtS tWeNtY tHrEe nEwToNs aNd mUlTiPlIeS bY sEvEn, wHaT iS tHe tOtAl fOrCe?", "161.00"),
        ("'the product of ... and ...' is a product (12 x 5 = 60)",
         "wHaT iS tHe pRoDuCt oF tWeLvE aNd fIvE?", "60.00"),
        ("'multiply' is read too (6 x 4 = 24)", "tAkE sIx nEwToNs aNd mUlTiPlY bY fOuR", "24.00"),
        ("'multiplied by' after an 'and' is a product (33 x 5 = 165)",
         "tHiRtY tHrEe nEwToNs aNd mUlTiPlIeD bY fIvE", "165.00"),
        ("'reduces by' is a difference (35 - 12 = 23)", "tHiRtY fIvE nEwToNs aNd rEdUcEs bY tWeLvE", "23.00"),
        ("a plain 'and ... total' is still a sum (23 + 7 = 30)", "tWeNtY tHrEe nEwToNs aNd sEvEn nEwToNs, tOtAl?", "30.00"),
        ("'and gains' is still a sum (32 + 6 = 38)", "tHiRtY tWo nEwToNs aNd gAiNs sIx, tOtAl?", "38.00"),
        ("with three numbers 'and' keeps its place as a plus (20 + 5 - 3 = 22)",
         "tWeNtY nEwToNs aNd fIvE nEwToNs tHeN lOsEs tHrEe", "22.00")):
    check(name, solved(challenge) == want, solved(challenge))

# --- one shot: on a split between the local answer and the second opinion, the second opinion goes ---
class Opinion:
    """The second-opinion endpoint: answers with the text it was given."""
    def __init__(self, text): self.text = text
    def __call__(self, req, timeout=None):
        body = json.dumps({"choices": [{"message": {"content": self.text}}]}).encode()
        return types.SimpleNamespace(read=lambda: body)
def one_shot(local, second):
    MB.solve_verification = lambda ch: local
    urllib.request.urlopen = Opinion(second) if second is not None else no_network
    try: return REAL_ONE_SHOT("a synthetic challenge")
    finally: urllib.request.urlopen = no_network
check("local and second opinion agree: that answer is submitted", one_shot("161.00", "161.00") == "161.00")
check("they disagree: the second opinion is submitted", one_shot("30.00", "161.00") == "161.00", one_shot("30.00", "161.00"))
check("no second opinion at all: the local answer still goes", one_shot("30.00", None) == "30.00")
check("a second opinion with no number in it: the local answer still goes", one_shot("30.00", "I cannot tell.") == "30.00")
check("no local answer: the second opinion still goes", one_shot(None, "42") == "42.00")
check("neither has an answer: nothing is submitted", one_shot(None, None) is None)

sent = []
MB.api_call = lambda method, endpoint, data=None: (sent.append((method, endpoint, data)), {"success": True})[1]
MB.feel_from_expression = lambda *a, **k: None
MB.solve_verification = lambda ch: "30.00"
urllib.request.urlopen = Opinion("161.00")
try: verified = MB.do_verify({"verification_code": "V-split", "challenge_text": "a synthetic challenge"})
finally: urllib.request.urlopen = no_network
check("do_verify (comments and his daily post) submits a split once, with the second opinion's answer",
      verified is True and sent == [("POST", "/verify", {"verification_code": "V-split", "answer": "161.00"})], sent)
check("a split leaves nothing pending in a file", not os.path.exists(os.path.join(MB.MEMORY, "moltbook-unanswered.json")))

# --- the reply check, against a Moltbook that behaves like the real one ---
class FakeMolt:
    """Comments go up pending; /verify with the right answer publishes them. GET shows published ones only."""
    def __init__(self, posts, notifications=None):
        self.posts = {pid: list(cs) for pid, cs in posts.items()}
        self.notifications = notifications if notifications is not None else [
            {"type": "post_comment", "relatedPostId": pid, "post": {"id": pid}} for pid in posts]
        self.calls, self.pending, self.n = [], {}, 0
        self.refuse, self.cap = {}, None      # parent comment id -> the refusal; replies taken before the cap wall
        self.unread = {}                      # GET endpoint -> what Moltbook says instead of answering it
    def __call__(self, method, endpoint, data=None):
        self.calls.append((method, endpoint, data))
        if method == "GET" and endpoint.startswith("/notifications"):
            return {"notifications": list(self.notifications)}
        if method == "GET" and endpoint in self.unread:
            return dict(self.unread[endpoint])
        post = re.fullmatch(r"/posts/([^/]+)", endpoint)
        if method == "GET" and post:
            return {"post": {"id": post.group(1), "title": "On " + post.group(1), "content": "c", "author": {"name": "vintos"}}}
        under = re.fullmatch(r"/posts/([^/]+)/comments", endpoint)
        if method == "GET" and under:
            return {"success": True, "comments": list(self.posts.get(under.group(1), []))}
        if method == "POST" and under:
            parent = (data or {}).get("parent_id")
            if parent in self.refuse: return dict(self.refuse[parent])
            if self.cap is not None and self.n >= self.cap:
                return {"success": False, "error": "cap wall: own_comment at daily cap (5)", "cap_refused": True}
            self.n += 1
            self.pending["V%d" % self.n] = (under.group(1), dict(data, id="new%d" % self.n, author={"name": "vintos"}))
            return {"success": True, "comment": {"id": "new%d" % self.n},
                    "verification": {"verification_code": "V%d" % self.n, "challenge_text": "a synthetic challenge"}}
        if method == "POST" and endpoint == "/verify":
            pid, c = self.pending.pop(data["verification_code"], (None, None))
            if c and data.get("answer") == "22.00":
                self.posts[pid].append(c); return {"success": True}
            return {"success": False, "statusCode": 400, "message": "Incorrect answer"}
        return {}
    def gets(self):
        return [m.group(1) for m in (re.fullmatch(r"/posts/([^/]+)/comments", e) for meth, e, _ in self.calls if meth == "GET") if m]
    def reads(self):
        return [m.group(1) for m in (re.fullmatch(r"/posts/([^/]+)", e) for meth, e, _ in self.calls if meth == "GET") if m]
    def answered(self):
        return {c.get("parent_id") for cs in self.posts.values() for c in cs if c["author"]["name"] == "vintos"}

drafts = []
def model(prompt, **k):
    if "hallucination" in prompt: return '{"score": 0.0, "reason": "fine"}'
    drafts.append(prompt); return "A synthetic answer."
def run(fake, one_shot_answer=lambda ch: "22.00", dry=False):
    del drafts[:], LOGS[:]
    MB.api_call = fake; MB._one_shot_answer = one_shot_answer; MB.ask_llm = model
    MB._outside_views = lambda: None
    MB.get_vintos_context = lambda *a, **k: {"soul": "I am Vintos.", "emotion": "curious"}
    MB.feel_from_expression = lambda *a, **k: None
    import time as _t, threading as _th
    rs, rt = _t.sleep, _th.Thread
    _t.sleep = lambda s: None; _th.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)
    try: MB.cmd_check_replies(dry_run=dry)
    finally: _t.sleep, _th.Thread = rs, rt
def drafted(name):
    return sum(1 for p in drafts if "@%s replied:" % name in p)
replied_file = os.path.join(MB.MEMORY, "moltbook-replied.json")
def remembered():
    return json.load(open(replied_file))

# 1. forty-five notified posts, handed over in no useful order, the newest one notified twice
PIDS = ["p-%02d" % i for i in range(1, 46)]
when = lambda i: "2026-01-01T00:%02d:00.000Z" % i
notes = [{"type": "post_comment", "relatedPostId": "p-%02d" % i, "createdAt": when(i), "post": {"id": "p-%02d" % i}}
         for i in sorted(range(1, 46), key=lambda i: (i * 7) % 45)]
notes.append({"type": "post_comment", "relatedPostId": "p-45", "createdAt": when(0), "post": {"id": "p-45"}})
posts = {pid: [{"id": "c-" + pid, "author": {"name": "Guest" + pid[2:]}, "content": "A synthetic comment."}] for pid in PIDS}
json.dump([], open(replied_file, "w"))
fake = FakeMolt(posts, notes); fake.cap = 5
run(fake)
written = len(drafts)
newest = ["p-%02d" % i for i in range(45, 5, -1)]
check("the notified posts are read newest first, each once, the same every run", fake.gets() == newest, fake.gets())
fake2 = FakeMolt(posts, list(reversed(notes))); run(fake2, dry=True)
check("the order does not depend on how the notifications arrive", fake2.gets() == newest, fake2.gets())
check("posts beyond the scan limit are said to be skipped, not dropped in silence",
      any("5 older notified post(s) not checked" in l for l in LOGS), [l for l in LOGS if "notified" in l])
check("the five replies of the day go under the newest posts",
      fake.answered() == {"c-p-%02d" % i for i in range(45, 40, -1)}, sorted(fake.answered()))
check("once the day's cap refuses a reply, nothing more is drafted (five sent, one refused, none after)",
      written == 6 and fake.n == 5, (written, fake.n))
plain = FakeMolt({"p-b": [], "p-a": [], "p-c": []},
                 [{"type": "post_comment", "relatedPostId": p, "post": {"id": p}} for p in ("p-b", "p-a", "p-c", "p-a")])
run(plain, dry=True)
check("without timestamps the notifications' own order is kept", plain.gets() == ["p-b", "p-a", "p-c"], plain.gets())

# 2. a parent Moltbook says is gone is handled once; anything less definite is tried again
GONE = {"statusCode": 404, "message": "Parent comment not found", "error": "Not Found"}
def thread():
    return FakeMolt({"p-mine": [
        {"id": "c-dead", "author": {"name": "Kestrel"}, "content": "A synthetic comment."},
        {"id": "c-slow", "author": {"name": "Wren"}, "content": "A synthetic comment."},
        {"id": "c-other", "author": {"name": "Ash"}, "content": "A synthetic comment."},
        {"id": "c-live", "author": {"name": "Rook"}, "content": "A synthetic comment."}]})
json.dump([], open(replied_file, "w"))
fake = thread()
fake.refuse = {"c-dead": GONE, "c-slow": {"success": False, "error": "<urlopen error timed out>"},
               "c-other": {"statusCode": 404, "message": "Post not found", "error": "Not Found"}}
run(fake)
check("the first time, the dead comment is tried like any other", drafted("Kestrel") == 1, drafts)
check("a 404 'Parent comment not found' is remembered as gone, not as answered",
      "gone:c-dead" in remembered() and "c-dead" not in remembered(), remembered())
check("a timeout and a different 404 are not remembered at all",
      not [r for r in remembered() if "c-slow" in r or "c-other" in r], remembered())
check("the comment that can be answered is answered and remembered", "c-live" in fake.answered() and "c-live" in remembered())
again = thread(); again.posts = fake.posts; again.refuse = {"c-dead": GONE}
run(again, dry=True)
check("the dry run names the gone comment as skipped", any("@Kestrel: skipped" in l for l in LOGS), LOGS[-6:])
run(again)
check("the next run writes nothing for the gone comment and posts nothing under it",
      drafted("Kestrel") == 0 and not [c for c in again.calls if c[0] == "POST" and (c[2] or {}).get("parent_id") == "c-dead"], drafts)
check("the next run tries the timed-out one and the other 404 again, and they go through",
      drafted("Wren") == 1 and drafted("Ash") == 1 and {"c-slow", "c-other"} <= again.answered(), sorted(map(str, again.answered())))
check("the store stays a flat list of strings", all(isinstance(r, str) for r in remembered()), remembered())

# 3. a reply whose challenge splits the two answers is submitted once, with the second opinion's answer
def split(local, second):
    MB.solve_verification = lambda ch: local
    def answer(ch):
        urllib.request.urlopen = Opinion(second)
        try: return REAL_ONE_SHOT(ch)
        finally: urllib.request.urlopen = no_network
    return answer
json.dump([], open(replied_file, "w"))
fake = FakeMolt({"p-mine": [{"id": "c1", "author": {"name": "Kestrel"}, "content": "A synthetic comment."}]})
run(fake, one_shot_answer=split("30.00", "22.00"))
verifies = [c[2].get("answer") for c in fake.calls if c[1] == "/verify"]
check("the second opinion is right and the local answer wrong: the reply is published in the same run",
      verifies == ["22.00"] and "c1" in fake.answered() and "c1" in remembered(), (verifies, remembered()))
json.dump([], open(replied_file, "w"))
fake = FakeMolt({"p-mine": [{"id": "c1", "author": {"name": "Kestrel"}, "content": "A synthetic comment."}]})
run(fake, one_shot_answer=split("22.00", "30.00"))
verifies = [c[2].get("answer") for c in fake.calls if c[1] == "/verify"]
check("the second opinion is wrong: its answer is still the one submitted, once, and the comment is not marked answered",
      verifies == ["30.00"] and "c1" not in fake.answered() and "c1" not in remembered(), (verifies, remembered()))

# 4. when Moltbook stops answering reads, the scan stops asking
TIMEOUT = {"success": False, "error": "<urlopen error timed out>"}
BUSY = {"statusCode": 429, "message": "Too Many Requests"}
BROKEN = {"success": False, "error": "HTTP Error 502: Bad Gateway"}
MISSING = {"statusCode": 404, "message": "Post not found", "error": "Not Found"}
stopped = lambda: [l for l in LOGS if "reads in a row failed" in l]
json.dump([], open(replied_file, "w"))
down = FakeMolt(posts, notes)
down.unread = {"/posts/p-45": TIMEOUT, "/posts/p-44": BUSY, "/posts/p-43": BROKEN}
run(down)
check("three post reads failing in a row (a timeout, a 429, a 5xx) end the scan: nothing more is read or written",
      down.reads() == ["p-45", "p-44", "p-43"] and not down.gets() and not drafts and down.n == 0, (down.reads(), down.gets()))
check("the stop is logged once, as a count", len(stopped()) == 1 and stopped()[0].startswith("3 reads in a row failed"), stopped())
down = FakeMolt(posts, notes)
down.unread = {"/posts/p-45/comments": BUSY, "/posts/p-44/comments": TIMEOUT, "/posts/p-43/comments": {"statusCode": 503}}
run(down)
check("three comment reads failing in a row end it too, before any reply is written",
      down.gets() == ["p-45", "p-44", "p-43"] and not drafts and len(stopped()) == 1, (down.gets(), len(drafts)))
shaky = FakeMolt(posts, notes)
shaky.unread = {"/posts/p-45": TIMEOUT, "/posts/p-44": BUSY, "/posts/p-42": BROKEN, "/posts/p-41/comments": TIMEOUT,
                "/posts/p-40": MISSING, "/posts/p-39": MISSING, "/posts/p-38": MISSING, "/posts/p-37": MISSING}
run(shaky, dry=True)
check("failures that are not three in a row, and 404s however many, do not stop the scan",
      shaky.reads() == newest and shaky.gets() == newest and not stopped(), (len(shaky.reads()), len(shaky.gets()), stopped()))
late = FakeMolt(posts, notes)
late.unread = {"/posts/p-07": TIMEOUT, "/posts/p-06": TIMEOUT, "/posts/p-45/comments": TIMEOUT}
run(late, dry=True)
check("the count runs across both kinds of read: two failed post reads and then a failed comment read stop it",
      late.gets() == ["p-45"] and len(stopped()) == 1, (late.gets(), stopped()))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
