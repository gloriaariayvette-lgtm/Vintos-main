#!/usr/bin/env python3
"""The planner is shown every spent subject (14 October). At 2,500 characters the 42 newest of 259 were cut
("and 42 more"), and after the repair deploy 29 of 58 refusals were exactly those: methanobactin, methionine
synthase, superoxide dismutase, secretin, ammonia monooxygenase, alkaline phosphatase, metallo-beta-lactamase.
Scratch HOME and workspace; no socket opens; no model is asked."""
import json, os, socket, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-spent-list-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the spent store is a scratch one and sockets are refused", C.SPENT.startswith(HOME) and socket.socket.connect is _no)

# a store shaped like 14 October's: 259 subjects, the newest of them the ones that were cut
old = ["SLC%dA%d" % (f, m) for f in range(1, 40) for m in range(1, 4)] + ["Protein family member %d" % i for i in range(140)]
new = ["methanobactin", "methionine synthase", "superoxide dismutase 1", "secretin", "ammonia monooxygenase",
       "alkaline phosphatase", "Metallo-beta-lactamase", 'HFE" or', 'TBP OR "protein_name:"TATA-binding protein']
now = time.time()
rows = {s.lower(): {"subject": s, "at": now - 3600 - i} for i, s in enumerate(old)}
rows.update({s.lower(): {"subject": s, "at": now - i} for i, s in enumerate(new)})
os.makedirs(os.path.dirname(C.SPENT), exist_ok=True); json.dump(rows, open(C.SPENT, "w"))
got = C.spent_subjects(now)
check("the newest spent subjects come first", got[:3] == ["methanobactin", "methionine synthase", "superoxide dismutase 1"], got[:5])
check("query debris is read back as the name", "HFE" in got and "TBP" in got and not any('"' in g or " OR " in g for g in got), [g for g in got if "HF" in g or "TBP" in g])
shown = C._compact_names(got, C.SPENT_PROMPT_CHARS)
check("the planner's list names every spent subject, none cut", "more" not in shown.split(", ")[-1] and all(n in shown for n in new[:7]), shown[-200:])
check("intent terms stop at a lowercase joiner", C._intent_terms("gene:HFE or gene:TFRC") == ["gene:HFE"], C._intent_terms("gene:HFE or gene:TFRC"))

spent = {"subjects": got}
mbl = {"question": "What are the zinc-binding residues of the metallo-beta-lactamase of Pseudomonas aeruginosa?"}
check("a spent subject is still refused", C.spent_retrieval(mbl, spent))
check("and the refusal can name it", C.spent_matches(C._inquiry_text(mbl), got) == ["Metallo-beta-lactamase"])
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the planner's refusal names the spent subject", 'already ended without an answer (%s)" % ", ".join(' in src)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
