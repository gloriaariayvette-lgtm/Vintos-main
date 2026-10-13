#!/usr/bin/env python3
"""Forge study caches its Fable rounds (2026-10-13). Each orchestrator round re-sent the same instructions, the
same brief and the same earlier reports, at full Fable price, with no cache point anywhere. Now the rounds go
through claude_cache: a cache point after the brief and after the newest report, so the next round reads what the
last one sent, and every call's cache use lands in memory/anthropic-usage.jsonl as caller forge-study.

Isolation: HOME and SPARK_WORKSPACE are throwaway before anything is imported; requests.post is a stub that records
the request and answers like the API; the study room and the subagent are fakes. Nothing leaves the machine."""
import json, os, sys, tempfile

TMP = tempfile.mkdtemp(prefix="forge-cache-")
os.environ["HOME"] = TMP
os.environ["SPARK_WORKSPACE"] = os.path.join(TMP, "ws")
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import requests
SENT = []
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
def _fake_post(url, json=None, headers=None, timeout=None, **k):
    SENT.append({"url": url, "body": json})
    rounds = sum(1 for x in SENT if "anthropic" in x["url"])
    reply = {"done": False, "tasks": [{"grep": "thing%d" % rounds, "why": "look"}]} if rounds < 3 else \
            {"done": True, "summary": "found it", "already_have": "yes", "where": "x.py"}
    return _Resp({"content": [{"type": "text", "text": __import__("json").dumps(reply)}], "stop_reason": "end_turn",
                  "usage": {"input_tokens": 10, "cache_read_input_tokens": 100 * rounds, "cache_creation_input_tokens": 50,
                            "output_tokens": 5}})
requests.post = _fake_post
requests.get = lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("this suite reaches nothing"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:900]) if d and not ok else ""))

import claude_cache, forge_study as FS
check("the usage log is throwaway", claude_cache.USAGE.startswith(TMP), claude_cache.USAGE)
check("the sender is a stub", requests.post is _fake_post)

class Room:
    def code_map(self): return "scripts/x.py — the thing\n" * 200
    def do_grep(self, q): return "x.py:1: " + q
    def do_read(self, p, start=1): return "content of " + p
sub = lambda system, user: "the subagent read it: " + user[-40:]

found = FS.investigate({"id": "p1", "capability": "thing", "why": "she asked", "origin": {"want": "a thing"}},
                       subagent=sub, room=Room())
calls = [x["body"] for x in SENT if "api.anthropic.com" in x["url"]]
check("the study ran its rounds through Fable", len(calls) >= 2 and found.get("state") == "done", (len(calls), found))
check("only the Anthropic endpoint was posted to", all("api.anthropic.com" in x["url"] for x in SENT), [x["url"] for x in SENT])

def blocks(b): return b["messages"][0]["content"]
def marked(b):
    return [i for i, x in enumerate(blocks(b)) if x.get("cache_control")]

b1, b2 = calls[0], calls[1]
check("round one marks the brief for caching", marked(b1) == [0], marked(b1))
check("a later round marks the brief and the newest report", marked(b2) == [0, len(blocks(b2)) - 1], marked(b2))
check("the marks ask for an hour", all(x["cache_control"].get("ttl") == "1h" for x in blocks(b2) if x.get("cache_control")))
check("at most four cache points per call", all(len(marked(b)) <= 4 for b in calls))
check("the system prompt is the same every round", all(c["system"] == calls[0]["system"] for c in calls))
t1 = [x["text"] for x in blocks(b1)]; t2 = [x["text"] for x in blocks(b2)]
check("round two starts with exactly what round one sent", t2[:len(t1)] == t1, (t1[:1], t2[:1]))
if len(calls) >= 3:
    t3 = [x["text"] for x in blocks(calls[2])]
    check("and round three with what round two sent", t3[:len(t2)] == t2)

rows = [json.loads(l) for l in open(claude_cache.USAGE)]
check("every Fable call is written to the usage log as forge-study",
      len(rows) == len(calls) and all(r["caller"] == "forge-study" and r["model"] == FS.FABLE for r in rows), rows)
check("the log carries the cache reads", sum(r["cache_read"] for r in rows) > 0)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
