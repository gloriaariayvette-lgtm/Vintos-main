#!/usr/bin/env python3
"""A held reply is settled, not unfinished: deviation_check seeds no thread when alignment holds; the
held-ledger entry is its record (Gloria, 2026-10-28: "That held - something I have been reaching for
landed ..." was seeded on every alignment above threshold). Slipping still seeds as before. Read from the
source's syntax tree; nothing runs, no socket opens."""
import ast, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))

path = os.path.join(REPO, "bin", "deviation_check.py")
src = open(path).read()
for twin in ("bin/deviation-check.py", "scripts/deviation_check.py", "scripts/deviation-check.py"):
    p = os.path.join(REPO, twin)
    check("%s is the same file" % twin, os.path.exists(p) and open(p).read() == src)

tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check")
def names(node):
    return {getattr(n, "id", None) for n in ast.walk(node)}
branch = next(n for n in ast.walk(fn) if isinstance(n, ast.If) and "final_dev" in names(n.test)
              and "DEVIATION_THRESHOLD" in names(n.test) and n.orelse)
held = branch.orelse[0]
check("the alignment branch is the elif of the deviation branch",
      isinstance(held, ast.If) and "final_aln" in names(held.test) and "ALIGNMENT_THRESHOLD" in names(held.test))

def seeds(stmts):
    out = []
    for s in stmts:
        for n in ast.walk(s):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "seed_thread":
                out.append(ast.get_source_segment(src, n))
    return out
check("holding seeds no thread", seeds(held.body) == [], seeds(held.body))
check("holding still writes its held-ledger record", "held-ledger.json" in ast.get_source_segment(src, held))
slip = seeds(branch.body)
check("slipping still seeds its deviation-check thread",
      len(slip) == 1 and slip[0].startswith('seed_thread("deviation-check", f"I slipped from what I intended'), slip)
check("the 'That held - something I have been reaching for landed' thread text is gone", "reaching for landed" not in src)

# A slip seeds its own thread whether or not a blush was written. Blush stopped seeding threads in
# 64c07124, so the old "blush already seeded this event" skip left every slip at >= 0.45 threadless.
slip_try = next((s for s in branch.body if isinstance(s, ast.Try)
                 and any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "seed_thread"
                         for n in ast.walk(s))), None)
check("the slip seed sits in a top-level try of the deviation branch", slip_try is not None)
slip_src = ast.get_source_segment(src, slip_try) if slip_try else ""
check("the slip seed is not gated on a blush having been written",
      "_blush_written" not in slip_src and "blush already seeded" not in src, slip_src)
check("the slip seed keeps its threshold quality path",
      'extra={"decision_mode": "threshold"}' in slip_src and "crossed the threshold" in slip_src, slip_src)
check("no other seed_thread call anywhere in deviation_check (one deviation, one thread)",
      sum(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "seed_thread"
          for n in ast.walk(tree)) == 1)
blush_src = open(os.path.join(REPO, "bin", "blush-ledger.py")).read()
check("blush still seeds no thread of its own, so the slip seed cannot double up",
      "seed_thread(" not in blush_src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
