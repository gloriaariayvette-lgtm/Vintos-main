#!/usr/bin/env python3
"""14 November: his_context keeps its 60,000-character limit for every surface; limit=None gives all of it (the Firepit)."""
import inspect, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="ctxcap-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dot_channel as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))
check("the default is the old limit", inspect.signature(D.his_context).parameters["limit"].default == 60000 == D.HIS_CONTEXT_CAP)
src = inspect.getsource(D.his_context)
check("both slices use the cap", src.count("[:limit]") == 2 and "[:60000]" not in src)
check("no cap is a whole slice", "abc"[:None] == "abc")
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
