#!/usr/bin/env python3
"""Last night's reflection is whole sentences, never cut at a decimal point (2026-10-03: the morning read
"overestimated Desire by 0.24. 44), alongside the discrepancy in desire (0."). Source and a pure function only;
nothing is predicted, written or sent."""
import ast, os, re, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
src = open(os.path.join(REPO, "bin", "emotional-reflection.py")).read()
node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_sentences")
ns = {"re": re}; exec(compile(ast.Module(body=[node], type_ignores=[]), "reflection", "exec"), ns)
S = ns["_sentences"]
text = ("I overestimated her arousal (0.44 measured against 0.75), alongside the discrepancy in desire (0.20). "
        "She was quieter than I read. Maybe tired.")
got = S(text)
check("a sentence with decimals stays whole", got[0] == "I overestimated her arousal (0.44 measured against 0.75), "
      "alongside the discrepancy in desire (0.20).", got)
check("and the next sentences are their own", got[1:] == ["She was quieter than I read.", "Maybe tired."], got)
check("the first sentence over 40 characters is the whole first one, not a fragment",
      next(s for s in got if len(s) > 40).endswith("(0.20)."))
check("empty text gives one empty sentence, never an error", S("") == [""])
check("the carry line and the seeded thread both use it, and neither splits on '.'",
      "_sentences(narrative) if len(s.strip()) > 40" in src and "seed_text = (_sentences(narrative)[0]" in src
      and 'narrative.split(".")' not in src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
