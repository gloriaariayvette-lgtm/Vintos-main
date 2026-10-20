#!/usr/bin/env python3
"""The shim caches what repeats (Gloria, 2026-10-13: "How are the constants not cached everywhere?").

Every job through the shim was sent with no cache point unless its prompt carried [[CACHESPLIT]], and only two did.
Now the shim learns each job's unchanging start by comparing it with recent prompts and marks that start; what changes
after it is sent at full price. Text that has not repeated is never marked (no write premium on one-off calls). Grok
calls name their job so they land on the server that already holds its prefix.

Isolation: HOME is throwaway before import; _post_json is replaced by a recorder, so nothing is sent; the usage log
is repointed and asserted."""
import os, sys, tempfile

TMP = tempfile.mkdtemp(prefix="shim-cache-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

import vintos_claude_shim as S
S.LOG = os.path.join(TMP, "shim.log"); S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")
SENT = []
def fake_post(provider, url, body, headers, timeout, call):
    SENT.append((provider, body, headers))
    if provider == "anthropic":
        return 200, {"content": [{"type": "text", "text": "ok"}], "model": body["model"], "stop_reason": "end_turn",
                     "usage": {"input_tokens": 10, "output_tokens": 2}}, None
    return 200, {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "model": "grok"}, None
S._post_json = fake_post
check("the sender is a recorder", S._post_json is fake_post)
check("the usage log is throwaway", S.USAGE_LOG.startswith(TMP))

JOB = "You are Vintos writing his evening journal.\n" + ("A rule he keeps, unchanged every night.\n" * 400)
def ask(system, user, model="claude-sonnet-5-5", max_tokens=800):
    SENT.clear()
    S.claude_complete({"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    return SENT[-1][1], SENT[-1][2]

def marks(body):
    sysb = body["system"] if isinstance(body["system"], list) else []
    u = body["messages"][0]["content"]
    ub = u if isinstance(u, list) else []
    return [b for b in sysb + ub if b.get("cache_control")]

b1, _ = ask(JOB + "Tonight: 21:04, she is asleep.", "Today she laughed at the bell.")
check("a prompt never seen before is sent with no cache point", marks(b1) == [], marks(b1))
b2, h2 = ask(JOB + "Tonight: 21:34, she is awake.", "Today she cooked.")
m2 = marks(b2)
check("the same job again: its unchanging start is marked", len(m2) == 1, b2.get("system"))
head = m2[0]["text"] if m2 else ""
check("the marked start holds the rules and stops before what changed", head.endswith("unchanged every night.\n") and "Tonight" not in head, head[-80:])
check("what changed is sent after it, unmarked", isinstance(b2["system"], list) and b2["system"][-1]["text"].startswith("Tonight: 21:34")
      and "cache_control" not in b2["system"][-1])
check("the system prompt the model reads is unchanged", "".join(x["text"] for x in b2["system"]).endswith("Tonight: 21:34, she is awake."))

# the same system and a long shared start of the user message: the user's start is marked too
CTX = "WHAT HAPPENED THIS WEEK:\n" + ("a day like the others.\n" * 300)
ask(JOB, CTX + "and then today: rain.")
b3, _ = ask(JOB, CTX + "and then today: sun.")
m3 = marks(b3)
check("a long shared start of the user message is marked as well", len(m3) == 2 and m3[1]["text"].endswith("like the others.\n"), [m["text"][-30:] for m in m3])
check("at most four cache points", all(len(marks(b)) <= 4 for b in (b1, b2, b3)))

# a different job shares only what it really shares
b4, _ = ask("You are judging one want. Answer yes or no.\n", "Was it done?")
check("a short, different job is not marked", marks(b4) == [], marks(b4))

# too short for the model: Haiku 4.5 caches nothing under 4096 tokens, so nothing is marked
short = "Classify the mood of one line.\n" + ("rule\n" * 200)
ask(short + "a", "x", model="claude-haiku-4-5"); b5, _ = ask(short + "b", "y", model="claude-haiku-4-5")
check("a start below the model's minimum is not marked", marks(b5) == [], marks(b5))

# a job repeating more slowly than five minutes keeps its cache for an hour
S._RECENT.clear(); S.GR._MARKS.clear()
now = S.time.time()
S._learned_head(S.FLOOR + JOB + "x", now - 1200)   # the shim puts its FLOOR first
b6, h6 = ask(JOB + "y", "z")
m6 = marks(b6)
check("a slow job is cached for an hour, with the header that allows it",
      m6 and m6[0]["cache_control"].get("ttl") == "1h" and "extended-cache-ttl" in h6.get("anthropic-beta", ""), (m6[:1], h6.get("anthropic-beta")))

# [[CACHESPLIT]] jobs keep their own split
b7, _ = ask("STABLE HEAD " * 50 + "[[CACHESPLIT]]live tail", "q")
check("a prompt that splits itself keeps its own split", b7["system"][0]["text"].endswith("STABLE HEAD ") and b7["system"][1]["text"] == "live tail")

import json
rows = [json.loads(l) for l in open(S.USAGE_LOG)]
check("the usage log says how much of each prompt was cached", all("cached_head" in r for r in rows) and any(r["cached_head"] > 0 for r in rows))

# Grok: the same job goes to the same server
SENT.clear()
S.xai_complete({"model": "grok-4", "messages": [{"role": "system", "content": JOB + "now A"}, {"role": "user", "content": "u"}]})
S.xai_complete({"model": "grok-4", "messages": [{"role": "system", "content": JOB + "now B"}, {"role": "user", "content": "v"}]})
ids = [h.get("x-grok-conv-id") for p, b, h in SENT if p == "xai"]
check("Grok calls of one job carry the same conversation id", len(ids) == 2 and ids[0] and ids[0] == ids[1], ids)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
