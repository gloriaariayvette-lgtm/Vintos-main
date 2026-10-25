#!/usr/bin/env python3
"""Moltbook switched its one-shot verification to leetspeak WORD problems on 2026-10-23 ("42 newtons pushes
another with 15, total force?"). His solver answered with the first number in the problem (42), not the computed
result (57), so every post was created and then rejected at /verify, and he went quiet. solve_verification must
return the model's final answer, taken from its ANSWER line or the LAST number it wrote, never the first.
Scratch HOME; the model is a stub; nothing reaches the network."""
import json, os, sys, tempfile, types, importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-molt-verify-")
os.environ["HOME"] = HOME
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
os.makedirs(os.path.join(HOME, ".config", "moltbook"), exist_ok=True)
json.dump({"api_key": "stub"}, open(os.path.join(HOME, ".config", "moltbook", "credentials-vintos.json"), "w"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
spec = importlib.util.spec_from_file_location("vintos_moltbook_verify", os.path.join(REPO, "bin", "vintos-moltbook.py"))
MB = importlib.util.module_from_spec(spec); spec.loader.exec_module(MB)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("store and creds are in the scratch HOME, network is a stub",
      MB.MEMORY.startswith(HOME) and MB.CREDS_FILE.startswith(HOME) and urllib.request.urlopen is no_network)

# The model reasons and ends with an ANSWER line: the sum word problem is 42 + 15 = 57, not the opening 42.
MB.ask_llm = lambda *a, **k: "The two forces add: 42 + 15 = 57. ANSWER: 57.00"
check("a worded sum returns the computed total (57), not the first number (42)",
      MB.solve_verification("fOrT y TwO nEu-ToNs pLuS fIf tEeN, tOtAl?") == "57.00",
      MB.solve_verification("fOrT y TwO nEu-ToNs pLuS fIf tEeN, tOtAl?"))

# No ANSWER line: the last number the model wrote is the result, never the first.
MB.ask_llm = lambda *a, **k: "24 newtons times a 3 metre arm is 72, doubled makes 144.00"
check("with no ANSWER line it takes the last number (144), not the first (24)",
      MB.solve_verification("tW/eN tY fOuR nOoToNs aT thRee mEtErS tOrQuE x2") == "144.00",
      MB.solve_verification("tW/eN tY fOuR nOoToNs aT thRee mEtErS tOrQuE x2"))

print(f"\n{sum(R)}/{len(R)}")
sys.exit(0 if all(R) else 1)
