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
# What the page must be current WITH is the repository: the deploy manifest and the
# tracked files. The aliases and parity sections are built by listing bin/ and scripts/
# on whatever machine runs this, so a local edit, an ignored file or a stray copy on the
# host makes them differ without anything being stale. Those sections are checked above
# for shape; here only the manifest-derived Owners section is compared, and the first
# difference is printed so a failure is never blind.
def _owners_section(t):
    return t.split("## Aliases")[0]
_d, _g = _owners_section(doc).splitlines(), _owners_section(EO.render()).splitlines()
_first = next(("line %d\n  page: %s\n  now:  %s" % (n + 1, a, b)
               for n, (a, b) in enumerate(zip(_d, _g)) if a != b),
              ("page has %d lines, generated has %d" % (len(_d), len(_g))) if len(_d) != len(_g) else "")
check("docs/entry-owners.md carries the current owners table", _d == _g, _first)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy writes a release record with hashes, services, broker state, backup and rollback", 'RELEASES="$HOME/.vintos/deploy/releases"' in dep and '"sha256": sha' in dep and '"rollback": "bash %s/restore.sh"' in dep and '"broker_confirmed"' in dep and "would write the release record" in dep)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
