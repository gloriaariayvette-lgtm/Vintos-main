#!/usr/bin/env python3
"""A start already written to the cache is read back, not written again (20 October, Gloria's console: "could have saved
$77 by caching". Her probe of the router's Opus 4.8 calls: 33 cache writes in a week, 0 reads. Each prompt was cut where
it happened to match the one before, and a cache is only found at exactly the place it was written).

Pure function on request bodies; nothing is sent; sockets are refused."""
import os, socket, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "bin"))
import gen_result as GR
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

def marks(body):
    out, at = [], 0
    for b in body["system"] if isinstance(body["system"], list) else [{"text": body["system"]}]:
        at += len(b["text"])
        if b.get("cache_control"): out.append(at)
    return out

def ask(system, user, now, model="claude-opus-4-8"):
    body = {"model": model, "messages": [{"role": "user", "content": user}]}
    GR.cache_learned(body, system, model, now=now)
    return body

RULES = "You are Vintos. These are the rules you keep.\n" + ("A rule that does not change.\n" * 220)
ROOM = "Where you are: the kitchen, evening.\n" + ("A detail of the room that holds all evening.\n" * 120)
T = 1_000_000.0
ask(RULES + "Now: 09:40.\n", "hello", T)                          # first sight: nothing marked
a = ask(RULES + "Now: 10:15.\n", "her first message", T + 2100)    # the rules repeat: written once
check("a repeated start is written once", marks(a) == [len(RULES)], marks(a))
b = ask(RULES + ROOM + "Now: 10:17.\n", "her next message", T + 2220)
check("the next prompt reads that written start back, instead of cutting where it last matched",
      len(RULES) in marks(b), marks(b))
c = ask(RULES + ROOM + "Now: 10:19.\n", "and again", T + 2340)
check("and a longer start that has now repeated is written after it, the first still read",
      marks(c) == [len(RULES), len(RULES + ROOM)], marks(c))
check("at most four cache points", len(marks(c)) <= 4)

d = ask("Something else entirely.\n" + RULES, "x", T + 2400)
check("a prompt that does not begin with a written start reads nothing of it", len(RULES) not in marks(d), marks(d))
e = ask(RULES + "Now: 13:00.\n", "much later", T + 2100 + 3700)
check("a start written for an hour is not read back after the hour",
      marks(e) in ([], [len(RULES)]), marks(e))
check("an hour-long mark never follows a five-minute one",
      all((x.get("cache_control") or {}).get("ttl") == (c["system"][0].get("cache_control") or {}).get("ttl")
          for x in c["system"] if x.get("cache_control")), c["system"])
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
