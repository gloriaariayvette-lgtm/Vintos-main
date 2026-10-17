#!/usr/bin/env python3
"""A Study fix edits a module and its twin copies together, and a missed old text says where it nearly is (SF-67752b13,
15 October: attempt 2 changed scripts/memory-search.py but not its twin bin/memory_search.py, and the twin check
refused the fix; attempts 1 and 3 could not find their old text). A scratch repository; nothing runs or sends."""
import os, sys, tempfile
HOME = tempfile.mkdtemp(prefix="study-twins-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "ws")
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
root = os.path.join(HOME, "repo")
for d in ("bin", "scripts", "broker/tests"): os.makedirs(os.path.join(root, d))
SRC = "def search(q):\n    data = resp.json()['data'][0]['embedding']\n    return data\n"
open(os.path.join(root, "scripts", "memory-search.py"), "w").write(SRC)
open(os.path.join(root, "bin", "memory_search.py"), "w").write(SRC)
os.symlink("memory-search.py", os.path.join(root, "scripts", "memory_search.py"))
open(os.path.join(root, "scripts", "other.py"), "w").write(SRC)
check("the repository is scratch", root.startswith(HOME))
plan = {"edits": [{"path": "scripts/memory_search.py", "old": "    data = resp.json()['data'][0]['embedding']\n",
                   "new": "    data = embedding_from(resp)\n"}],
        "new_files": [{"path": "broker/tests/test_memory_search_reply.py", "content": "print('ok')\n"}]}
changed = S.apply_edits(plan, root=root)
read = lambda p: open(os.path.join(root, p)).read()
check("the edit through the symlink lands in the real file", "embedding_from(resp)" in read("scripts/memory-search.py"))
check("and in its twin copy in bin/", "embedding_from(resp)" in read("bin/memory_search.py"), changed)
check("both are named as changed", "bin/memory_search.py" in changed, changed)
check("a different module with the same text is left alone", "embedding_from" not in read("scripts/other.py"))
try:
    S.apply_edits({"edits": [{"path": "scripts/memory-search.py", "old": "def search(q):\n  data = resp.json()\n", "new": "x"}],
                   "new_files": [{"path": "broker/tests/test_x2.py", "content": "1"}]}, root=root)
    msg = ""
except ValueError as e:
    msg = str(e)
check("a missed old text says where its first line is", "found 0 times" in msg and "line 1" in msg, msg)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
