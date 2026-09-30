#!/usr/bin/env python3
"""Only the entry is printed into the entry (2026-09-30).

idle-journal.sh sends the drafting block's stdout into the entry file. "[Journal] Sol B1 failed (HTTP Error
400)" was printed there and became the 11:06 entry. Every other line in that block must go to stderr, and
the prompt is mended of broken emoji halves before any model is called. Source checks only; nothing runs.
"""
import ast, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

for p in ("bin/idle-journal.sh", "scripts/idle-journal.sh"):
    s = open(os.path.join(REPO, p)).read()
    m = re.search(r"python3 << 'PYEOF' > \"\$_JRN_ENTRY_TMP\"\n(.*?)\nPYEOF\n", s, re.S)
    check("%s: the drafting block is found" % p, bool(m))
    tree = ast.parse(m.group(1))
    stray = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            to_err = any(k.arg == "file" for k in node.keywords)
            only_entry = len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "_raw"
            if not to_err and not only_entry:
                stray.append(node.lineno)
    check("%s: nothing but the entry prints into the entry" % p, not stray, stray)
    check("%s: the prompt is mended before the first draft" % p,
          m.group(1).index('encode("utf-16", "surrogatepass")') < m.group(1).index("_a1r = _claude_sync("))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
