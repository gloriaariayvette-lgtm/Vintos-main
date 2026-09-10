#!/usr/bin/env python3
"""Review items 1, 6, 7, 18, 19, 22, 26 (2026-09-10): every entry point has a decided owner from the
deploy's own lists; aliases are listed with their targets; the twin parity matrix says which twins
differ and which member is deployed; the deploy writes a release record with hashes, services,
broker state, backup and rollback."""
import os, sys, json, importlib.util, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
spec = importlib.util.spec_from_file_location("eo", os.path.join(REPO, "scripts", "entry_owners.py")); EO = importlib.util.module_from_spec(spec); spec.loader.exec_module(EO)
L = EO._lists()
check("the deploy's four lists are read", all(L[k] for k in ("SCRIPTS", "BINS", "EXECUTABLE", "SKILLFILES")) and "server.py" in L["BINS"] and "compute_admission.py" in L["SCRIPTS"])
o = EO.owners(); by = {r["entry"]: r for r in o}
check("every manifest entry has one decided owner and rule", len(o) >= 200 and by["compute_admission.py"]["owner"].endswith("workspace/scripts/compute_admission.py") and by["server.py"]["rule"] == "BINS")
check("executables are marked", by["atelier-visit.py"]["executable"] is True and by["compute_admission.py"]["executable"] is False)
missing = [r["entry"] for r in o if not r["in_checkout"]]
check("every manifest entry exists in the checkout", not missing, missing)
a = EO.aliases()
check("aliases are listed with targets; host-only links are named as such", len(a) > 100 and all(r["target"] for r in a) and any(r["note"].startswith("host path") for r in a))
p = EO.parity()
check("the parity matrix has twin sets, each with identical/differs and the deployed member", len(p) > 20 and all("identical" in r and r["deployed"] for r in p) and any(not r["identical"] for r in p))
doc = open(os.path.join(REPO, "docs", "entry-owners.md")).read()
# The parity section carries content hashes, so any uncommitted local edit under bin/ or scripts/
# would make the committed page look stale. Compare the whole page on a clean tree; on a dirty one
# compare only the sections that do not depend on file contents, and say so.
import subprocess
try:
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--", "bin", "scripts"],
                           capture_output=True, text=True, timeout=20).stdout.strip()
except Exception:
    dirty = ""
gen = EO.render()
def _head(t):
    return t.split("## Twin parity")[0]
if dirty:
    check("docs/entry-owners.md is the generated table and is current (owners and aliases; the tree has local edits)",
          _head(doc) == _head(gen), dirty.splitlines()[:5])
else:
    check("docs/entry-owners.md is the generated table and is current", doc == gen)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy writes a release record with hashes, services, broker state, backup and rollback", 'RELEASES="$HOME/.vintos/deploy/releases"' in dep and '"sha256": sha' in dep and '"rollback": "bash %s/restore.sh"' in dep and '"broker_confirmed"' in dep and "would write the release record" in dep)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
