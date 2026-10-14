#!/usr/bin/env python3
"""Introspection's absorb step reaches its final step (2026-10-14). run() only ever wrote `results`, while the absorb
read `results2`, so the absorb always looked failed: introspection printed draft A and stopped, every run. The
absorb threads now fill results2, and run() writes the list it is given.

Source only, plus the run()/absorb wiring exercised in isolation: nothing calls a model."""
import os, re, sys, threading
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
src = open(os.path.join(REPO, "bin", "introspection.sh")).read()
check("the absorb threads fill results2", src.count("1500, results2))") == 2)
# run() as written, against a stub model: the list it is given is the one filled
m = re.search(r"results = \[None, None\]\ndef run\(.*?\n(?=def |\S)", src, re.S)
ns = {"call_llm": lambda msgs, temp, max_tok: "absorbed:" + msgs}
exec(m.group(0), ns)
results2 = [None, None]
ts = [threading.Thread(target=ns["run"], args=(i, "d%d" % i, 0.7, 10, results2)) for i in (0, 1)]
[t.start() for t in ts]; [t.join() for t in ts]
check("both absorbed drafts arrive where the next step reads them", results2 == ["absorbed:d0", "absorbed:d1"], results2)
check("the first drafts' list is left alone", ns["results"] == [None, None], ns["results"])
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
