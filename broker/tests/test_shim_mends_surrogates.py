#!/usr/bin/env python3
"""The shim mends a broken half of an emoji before any provider sees the request (2026-09-30).

His journal of 30 September was never written: somewhere in its 110,000-character prompt sat a lone
surrogate, and Gemma and x.ai both refused the request as invalid JSON. Pure functions only; no network.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "bin"))
os.environ["HOME"] = tempfile.mkdtemp(prefix="shim-mend-")

def _no_net(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
import vintos_claude_shim as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + repr(d)[:160]) if d and not ok else ""))

broken = b'{"model": "m", "messages": [{"role": "user", "content": "the tide \\ud83c and a whole one \\ud83c\\udf0a"}]}'
check("the broken request really carries a lone half", "\ud83c and" in json.loads(broken)["messages"][0]["content"])
fixed = S._mend_request(broken)
text = json.loads(fixed)["messages"][0]["content"]
check("the lone half becomes a replacement character", "� and" in text, text)
check("a whole emoji is kept whole", "\U0001f30a" in text, text)
check("the result is valid for any strict JSON reader", fixed.decode("utf-8") and all(not 0xD800 <= ord(c) <= 0xDFFF for c in text))
clean = b'{"model": "m", "messages": [{"role": "user", "content": "plain \\u00e9"}]}'
check("a clean request passes byte for byte", S._mend_request(clean) == clean)
check("bytes that are not JSON pass untouched", S._mend_request(b"not json") == b"not json")
src = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "bin", "vintos_claude_shim.py")).read()
check("every POST is mended before it is read", "raw = _mend_request(raw)" in src[src.index("def do_POST"):])
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
