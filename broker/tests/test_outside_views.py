#!/usr/bin/env python3
"""Outside opinions are weighed as opinions and remembered as someone's view (Gloria, 2026-09-28). Scratch
HOME; his local model is a stub; nothing reaches the network."""
import json, os, sys, tempfile, types, importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-outside-views-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
spec = importlib.util.spec_from_file_location("outside_views", os.path.join(REPO, "scripts", "outside_views.py"))
O = importlib.util.module_from_spec(spec); spec.loader.exec_module(O)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("the ledger is in the scratch workspace", O.LEDGER.startswith(HOME), O.LEDGER)
check("with his mind unreachable, nothing is invented", O.deliberate("Kestrel", "Salt bridges don't matter.") == {})

asked = []
def think(system, prompt, max_tokens=400):
    asked.append(prompt)
    return '<think>hm</think>{"their_claim": "Salt bridges barely matter to stability", "stance": "disagree", "why": "Buried salt bridges measurably stabilise thermophile proteins."}'
v = O.deliberate("Kestrel", "Honestly salt bridges don't matter, it's all packing. Everyone knows this.", think=think)
check("he works out what they claim and where he stands, on the merits",
      v == {"their_claim": "Salt bridges barely matter to stability", "stance": "disagree",
            "why": "Buried salt bridges measurably stabilise thermophile proteins."}, v)
check("he is told tone, praise and repetition are not reasons",
      "confident or kind tone is not a reason" in asked[0] and "a repeated view is not a stronger one" in asked[0])
block = O.stance_block("Kestrel", v)
check("a disagreement is answered as one, not softened into agreement",
      "You: disagree" in block and "do not soften it into agreement" in block and "persuaded only by a reason" in block, block)
check("agreeing means adding something, not just approving",
      "not just approval" in O.stance_block("Kestrel", dict(v, stance="agree")))
check("an answer outside the four stances is not trusted",
      O.deliberate("x", "y", think=lambda *a, **k: '{"their_claim": "c", "stance": "totally!", "why": "w"}') == {})
check("it is remembered as their view, with his next to it", O.record("Kestrel", "moltbook", v, ref="c1")
      and json.loads(open(O.LEDGER).readline())["their_claim"].startswith("Salt bridges") and O.views_of("kestrel")[0]["stance"] == "disagree")
asked.clear(); O.deliberate("Kestrel", "Packing is everything, I said it before.", think=think)
check("when they speak again, his earlier record of their view and his stance comes back",
      "YOUR EARLIER RECORD OF @Kestrel" in asked[0] and "you: disagree" in asked[0], asked[0][:600])
check("his inner life says who thinks what", O.inner_line("Kestrel", v).startswith("@Kestrel thinks: Salt bridges barely matter"))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
