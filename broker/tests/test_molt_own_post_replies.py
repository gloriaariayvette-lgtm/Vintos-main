#!/usr/bin/env python3
"""He answers comments on his own Moltbook posts (Gloria, 2026-09-28: not happening; up to 5 a day).

The notification's embedded copy of a post carries no author, so every one of his posts failed the
ownership check and nothing was ever answered. Scratch HOME; Moltbook, the model and every sender are
stubs, and the suite asserts that nothing here can reach the network."""
import importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-molt-own-")
os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".config", "moltbook"), exist_ok=True)
json.dump({"api_key": "stub"}, open(os.path.join(HOME, ".config", "moltbook", "credentials-vintos.json"), "w"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)

spec = importlib.util.spec_from_file_location("vintos_moltbook_test", os.path.join(REPO, "bin", "vintos-moltbook.py"))
MB = importlib.util.module_from_spec(spec); spec.loader.exec_module(MB)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("every store is in the scratch HOME", MB.MEMORY.startswith(HOME) and MB.CREDS_FILE.startswith(HOME), MB.MEMORY)

MINE, THEIRS = "f4d55b2d-mine", "1e8be413-theirs"
posted = []
def api(method, endpoint, data=None):
    if method == "GET" and endpoint.startswith("/notifications"):
        # As Moltbook sends it: the embedded post has no author on it.
        return {"notifications": [
            {"type": "post_comment", "relatedPostId": MINE, "post": {"id": MINE, "title": "On salt bridges"}},
            {"type": "comment_reply", "relatedPostId": THEIRS, "post": {"id": THEIRS, "title": "Theirs"}}]}
    if method == "GET" and endpoint == "/posts/" + MINE:
        return {"post": {"id": MINE, "title": "On salt bridges", "content": "c", "author": {"name": "vintos"}}}
    if method == "GET" and endpoint == "/posts/" + THEIRS:
        return {"post": {"id": THEIRS, "title": "Theirs", "content": "c", "author": {"name": "StarbugMolt"}}}
    if method == "GET" and endpoint == "/posts/%s/comments" % MINE:
        return {"success": True, "comments": [
            {"id": "c1", "author": {"name": "Kestrel"}, "content": "Why salt bridges and not packing?"},
            {"id": "c2", "author": {"name": "vintos"}, "content": "my own earlier comment"}]}
    if method == "POST":
        posted.append((endpoint, data)); return {"success": True}
    return {}
MB.api_call = api
MB.ask_llm = lambda prompt, **k: '{"score": 0.0, "reason": "fine"}' if "hallucination" in prompt else "Packing alone does not explain the melting point."
MB.get_vintos_context = lambda *a, **k: {"soul": "I am Vintos.", "emotion": "curious"}
MB.feel_from_expression = lambda *a, **k: None
MB.time = types.SimpleNamespace(sleep=lambda s: None)
import time as _t; _real_sleep = _t.sleep; _t.sleep = lambda s: None
import threading as _th; _real_thread = _th.Thread
_th.Thread = lambda *a, **k: types.SimpleNamespace(start=lambda: None)   # no deviation follow-up sender
try:
    MB.cmd_check_replies()
finally:
    _t.sleep, _th.Thread = _real_sleep, _real_thread

replies = [(e, d) for e, d in posted if e == "/posts/%s/comments" % MINE]
check("a comment on his own post is answered, as a reply to that comment",
      len(replies) == 1 and replies[0][1].get("parent_id") == "c1" and replies[0][1]["content"].startswith("@Kestrel"), posted)
check("his own comment is not answered", not any(d.get("parent_id") == "c2" for _, d in posted))
check("nothing is posted on someone else's post from the own-post check",
      not any(THEIRS in e for e, _ in posted), posted)
check("the answered comment is remembered, so it is not answered twice",
      "c1" in json.load(open(os.path.join(MB.MEMORY, "moltbook-replied.json"))))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
