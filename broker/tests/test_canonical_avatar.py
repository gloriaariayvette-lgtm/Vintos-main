#!/usr/bin/env python3
"""Her avatar and ReelRoom exchanges reach the lossless record (16 October). chat-canonical.jsonl took only the chat
doors and had never been written on Aegis, because her conversation is on the avatar route; every exchange older than
the ledger's 300 was lost to what learns from them. The server now appends each non-test avatar turn there, her row
carrying her own words, and the self head reads it. Scratch HOME; no network; torch and requests are stubs."""
import json, os, sys, tempfile, types, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="canonical-avatar-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules.setdefault("torch", types.SimpleNamespace(load=lambda f: None, tensor=lambda x: x, no_grad=None))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_self_head as SH
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:500]) if d and not ok else ""))
check("the record the head reads is scratch", SH.CANONICAL.startswith(HOME))

src = open(os.path.join(REPO, "bin", "server.py")).read()
start = src.index("async def avatar_chat(")
body = src[start:src.index("\nasync def ", start + 20)] if "\nasync def " in src[start + 20:] else src[start:]
block = body[body.index("The lossless record (chat-canonical.jsonl) took only the chat doors"):]
block = block[:block.index("if _surface != \"reelroom\" and not _test_turn:")]
check("the avatar route appends each turn to the lossless record", "_canon_append(" in block and "surface=_surface" in block)
check("only when the turn is not a test", body.count("if not _test_turn:\n                # The lossless record") == 1)
check("her row carries her own words and both rows the turn id", "original_text" in block and "turn_id=_cv_tid" in block)
check("ReelRoom is included (it is not behind the avatar-history save's reelroom exclusion)",
      body.index("The lossless record") < body.index('_append_avatar_history(av_chat_log'))

# what the server writes, the head reads
now = time.time()
rows = [{"role": "user", "content": "[Gloria sent you a photo: a cat on a sill]\n\n[Gloria's message with the photo:] look at him",
         "ts": now - 60, "surface": "avatar", "turn_id": "T-1", "original_text": "look at him"},
        {"role": "assistant", "content": "He has decided the sill is his and the sun is rent.", "ts": now - 50,
         "surface": "avatar", "turn_id": "T-1", "served_by": "x"}]
open(SH.CANONICAL, "w").write("".join(json.dumps(r) + "\n" for r in rows))
ex = SH.exchanges(rows=[], archive=True)
mine = [e for e in ex if "sill is his" in json.dumps(e)]
check("the self head reads an avatar exchange from the lossless record", len(mine) == 1, ex[-3:] if ex else ex)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
