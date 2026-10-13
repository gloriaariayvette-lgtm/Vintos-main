#!/usr/bin/env python3
"""OpenAI calls name their job (2026-10-13). OpenAI caches a repeated prompt start by itself, but a job's repeats
only find it on the server that holds it; prompt_cache_key sends them there. Each call's cached tokens go to the
OpenAI usage log the router already writes.

Isolation: HOME is throwaway before import; urlopen is replaced by a recorder, so nothing is sent."""
import io, json, os, sys, tempfile

TMP = tempfile.mkdtemp(prefix="openai-key-")
os.environ["HOME"] = TMP
os.environ["OPENAI_API_KEY"] = "test-openai"
os.makedirs(os.path.join(TMP, ".vintos", "logs"), exist_ok=True)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

import urllib.request
SENT = []
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake_urlopen(req, timeout=None):
    SENT.append((req.full_url, json.loads(req.data.decode())))
    return _Resp(json.dumps({"status": "completed", "output_text": "ok",
                             "usage": {"input_tokens": 3000, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 2048}}}).encode())
urllib.request.urlopen = fake_urlopen

import astra_call as A
check("the sender is a recorder", urllib.request.urlopen is fake_urlopen)
A._key = lambda: "test-openai"
A._direct_call("You are Astra. The rules, unchanged.\n" * 50 + "Today: x", [{"role": "user", "content": "a"}])
A._direct_call("You are Astra. The rules, unchanged.\n" * 50 + "Today: x", [{"role": "user", "content": "b"}])
A._direct_call("A different job entirely.", [{"role": "user", "content": "c"}])
keys = [b.get("prompt_cache_key") for u, b in SENT]
check("every OpenAI call names its job", all(k and k.startswith("vintos-") for k in keys), keys)
check("the same job carries the same name", keys[0] == keys[1], keys)
check("a different job carries a different one", keys[2] != keys[0], keys)
log = os.path.join(TMP, ".vintos", "logs", "openai-usage.jsonl")
rows = [json.loads(l) for l in open(log)]
check("each call's cached tokens are logged", len(rows) == 3 and all(r["src"] == "astra" and r["cached"] == 2048 for r in rows), rows)
check("only OpenAI was addressed", all("api.openai.com" in u for u, b in SENT))
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
