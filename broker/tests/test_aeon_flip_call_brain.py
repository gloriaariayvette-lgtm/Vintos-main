#!/usr/bin/env python3
"""After the AEON flip, his local call brain moves with it, thinking off; before it, both
keep their 26B routes. Scratch HOME; every network call is stubbed or refused."""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="aeon-flip-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ.pop("VINTOS_LOCAL_BRAIN", None)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import subcon_target as S
import voice_local as V

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

FLAG = os.path.join(HOME, ".vintos", "subcon-target.json")
def flag(name):
    os.makedirs(os.path.dirname(FLAG), exist_ok=True)
    json.dump({"target": name}, open(FLAG, "w"))

os.makedirs(os.path.join(HOME, ".vintos", "pool"), exist_ok=True)
json.dump([{"label": "aeon-12b", "machine": "aegis", "model": "aeon/gemma-4-12b", "url": "http://aegis.test:1234/v1/chat/completions"},
           {"label": "aeon-12b", "machine": "studio", "model": "aeon-gemma-4-12b", "url": "http://studio.test:8840/v1/chat/completions"},
           {"label": "e4b-duo", "machine": "imac", "model": "e4b", "url": "http://imac.test/v1/chat/completions"}],
          open(os.path.join(HOME, ".vintos", "pool", "backends.json"), "w"))

# the 26B was removed (2026-11-08): with no flag at all the call brain is AEON on the Studio
url, body = V._brain_body({"max_tokens": 5})
check("no flag: the call brain is AEON on the Studio",
      url == "http://studio.test:8840/v1/chat/completions" and body["model"] == "aeon-gemma-4-12b", (url, body))

# a record that has not all passed changes no route (it only withholds residual readings)
flag("aeon")
_real_unmet = S.unmet
S.unmet = lambda *a, **k: ["Valence: not passed"]
url, body = V._brain_body({"max_tokens": 5})
check("flag without a full pass: still AEON", body["model"] == "aeon-gemma-4-12b", body)

# the flip, everything passed
S.unmet = lambda *a, **k: []
url, body = V._brain_body({"stream": True, "max_tokens": 5})
check("flipped: the call brain is AEON on the Studio", url == "http://studio.test:8840/v1/chat/completions"
      and body["model"] == "aeon-gemma-4-12b", (url, body))
check("flipped: thinking off, both ways", body.get("reasoning_effort") == "none"
      and body.get("chat_template_kwargs") == {"enable_thinking": False}, body)
check("flipped: the stream flag is kept", body.get("stream") is True)

os.environ["VINTOS_LOCAL_BRAIN"] = "some-named-model"
url, body = V._brain_body({})
check("an explicit VINTOS_LOCAL_BRAIN keeps its own route", url == V.LM + "/v1/chat/completions"
      and body["model"] == V.BRAIN and "reasoning_effort" not in body, (url, body))
os.environ.pop("VINTOS_LOCAL_BRAIN")
os.remove(os.path.join(HOME, ".vintos", "pool", "backends.json"))
url, body = V._brain_body({})
check("flipped, no AEON backend configured: its own route, never a half-made one", body["model"] == V.BRAIN, body)

# Gloria prediction moved with phase 2 (its _subcon_url/_subcon_model); the flipped route is the shim's lane
check("flipped: the generative route is the shim's thinking-off subconscious lane",
      S.generative_route("x", "y") == (S.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"))
S.unmet = _real_unmet
os.remove(FLAG)
check("flag removed: generative route is still AEON's lane", S.generative_route("x", "y") == (S.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"))

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
