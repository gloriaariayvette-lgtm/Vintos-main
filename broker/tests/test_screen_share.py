#!/usr/bin/env python3
"""Screen share without a screen or a model: a tick describes only when the picture changed or the description
aged out, stores the hash and never the image, and the context block his prompt receives says what is on her
screen while sharing is on and fresh, says the look is pending or stale when it is, and is empty when sharing
is off. Scratch workspace only."""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "memory")); os.environ["SPARK_WORKSPACE"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import screen_share as SS
assert SS.MEMORY.startswith(TMP)
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))


class FakeBackend:
    def __init__(self): self.shot = b"screen-A"; self.title = "Edge - recipes"
    def capture(self): return (self.shot, (1600, 670), (3440, 1440))
    def describe(self): return {"active_window": self.title}

calls = []
def fake_gemma(prompt, shot): calls.append((prompt, shot)); return f"Gloria has a recipe for lasagne open in Edge, comments below it. ({shot.decode()})"

T = 1_000_000.0
check("off: no context", SS.context_block(T) == "")
SS._write({"active": True, "pid": os.getpid(), "started_at": T, "description": "", "described_at": None, "last_hash": ""})
check("on, nothing described yet: he is told the first look is pending", "first look is on its way" in SS.context_block(T))

b = FakeBackend()
d = SS.tick(b, caller=fake_gemma, now=T + 5)
check("first tick describes and stores hash, title, description; never the image", len(calls) == 1 and d["description"].startswith("Gloria has a recipe")
      and d["last_hash"] and "screen-A" not in json.dumps({k: v for k, v in d.items() if k != "description"}) and d["active_window"] == "Edge - recipes", d)
d = SS.tick(b, caller=fake_gemma, now=T + 11)
check("unchanged picture within the window: no new Gemma call", len(calls) == 1 and d["captures"] == 2)
b.shot = b"screen-B"
d = SS.tick(b, caller=fake_gemma, now=T + 17)
check("changed picture: described again, previous kept, Gemma shown the prior description", len(calls) == 2 and "screen-B" in d["description"]
      and "screen-A" in d["previous_description"] and "previous description" in calls[1][0].lower(), d)
d = SS.tick(b, caller=fake_gemma, now=T + 17 + SS.REDESCRIBE_S + 1)
check("same picture but the description aged out: described again", len(calls) == 3)

blk = SS.context_block(T + 17 + SS.REDESCRIBE_S + 2)
check("context block names the window, the age, the description and the grounding rule",
      "SHARING HER SCREEN" in blk and "Edge - recipes" in blk and "screen-B" in blk and "do not invent" in blk and "Before that:" in blk, blk)
check("stale description is flagged, not repeated as current", "may be out of date" in SS.context_block(T + 17 + SS.REDESCRIBE_S + 2 + SS.FRESH_S + 5))

def broken(prompt, shot): raise RuntimeError("gemma down")
b.shot = b"screen-C"
d = SS.tick(b, caller=broken, now=T + 900)
check("describe failure keeps the last words and records the error", d["description"].startswith("Gloria has") and "gemma down" in d["describe_error"])

st = SS.stop("test")
check("stop: inactive, reason kept, context empty", st["state"]["active"] is False and st["state"]["reason"] == "test" and SS.context_block(T + 901) == "")
SS._write({"active": True, "pid": 999999, "description": "x", "described_at": T})
check("a dead loop process reads as inactive", SS.status()["active"] is False and "gone" in SS.status()["reason"])
rows = [json.loads(l) for l in open(SS.LOG)]
check("log holds hashes and text, never image bytes", all("screen-A" not in json.dumps(r.get("hash", "")) for r in rows) and any(r.get("changed") for r in rows))

import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
