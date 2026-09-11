#!/usr/bin/env python3
"""Candidate store writers and nearby locking references, found by static scanning.

This inventory does not prove read-modify-write safety. It cannot establish lock
scope, fallback behavior, runtime path identity or complete call-graph coverage.
Basenames and normalized module names are discovery keys, not ownership proof.
Regenerate docs/store-owners.md with --write.
"""
import os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STORE = re.compile(r'["\']([A-Za-z0-9_.\-]+\.(?:json|jsonl))["\']')
WRITE = re.compile(r'json\.dump\(|open\([^)]*["\'](?:w|a)\+?["\']|_atomic|save_ledger|append_ledger|atomic_json|_save\(|save_pool|save_json|compare_and_swap|os\.replace\(')
LOCK = re.compile(r'fcntl\.flock|LOCK_EX|save_ledger|append_ledger|_Lock\(|_table_lock|\.lock["\']|flock\(')
# Recognize nearby helper calls without claiming anything about their lock scope.
LOCKED_HELPERS = re.compile(r'compare_and_swap\(|write_json\(|_sg_write\(|locked_update|_locked_write|save_pool\(|save_ledger\(|append_ledger\(|atelier_ledger\.mark|_lu\(|_lu2\(|prediction_ledger\.')
SKIP = ("broker/tests", "__pycache__", "scripts/entry_owners.py", "scripts/store_owners.py")


def organ(path):
    """bin/x-y.py, bin/x_y.py and scripts/x_y.py are one organ."""
    b = os.path.basename(path); stem, ext = os.path.splitext(b)
    return re.sub(r"[-_]", "", stem) + ext


def scan():
    writers = collections.defaultdict(dict)
    for d in ("scripts", "bin", "skills/dreaming/scripts", "broker"):
        for root, _, fs in os.walk(os.path.join(REPO, d)):
            for f in fs:
                p = os.path.join(root, f); rel = os.path.relpath(p, REPO)
                if any(x in rel for x in SKIP) or not f.endswith((".py", ".sh")) or os.path.islink(p):
                    continue
                try:
                    s = open(p, errors="replace").read()
                except Exception:
                    continue
                # Which module constants name which store: STORE = ...("x.json") - the common shape, where
                # the write happens through the constant somewhere else in the file.
                consts = {}
                for cm in re.finditer(r'^\s*([A-Z_][A-Z0-9_]*)\s*=\s*[^\n]*?["\']([A-Za-z0-9_.\-]+\.(?:json|jsonl))["\']', s, re.M):
                    consts.setdefault(cm.group(2), set()).add(cm.group(1))
                for m in STORE.finditer(s):
                    # A write is the store's name and a write token in the SAME statement, or a write
                    # through the constant that names it. A read that merely sits near an unrelated
                    # write is not a write (review 46: the table must name real writers).
                    line_start = s.rfind("\n", 0, m.start()) + 1
                    line_end = s.find("\n", m.end());  line_end = len(s) if line_end < 0 else line_end
                    ctx = s[line_start:line_end] + s[m.end(): m.end() + 120]
                    via_const = ""
                    for c in consts.get(m.group(1), ()):
                        for wm in re.finditer(r"[^\n]*\b%s\b[^\n]*" % re.escape(c), s):
                            seg = wm.group(0)
                            if WRITE.search(seg) and "open(" in seg or re.search(r"(?:save_json|write_json|compare_and_swap|locked_update|_sg_write|_save|_atomic|save_ledger|append_ledger|_lu)\(\s*%s\b" % re.escape(c), seg):
                                via_const = seg; break
                        if via_const: break
                    if via_const:
                        ctx = ctx + " " + via_const
                    if WRITE.search(ctx) or via_const:
                        o = organ(rel)
                        w = writers[m.group(1)].setdefault(o, {"files": set(), "locking_reference": False, "how": ""})
                        w["files"].add(rel)
                        if LOCK.search(ctx):
                            w["locking_reference"] = True; w["how"] = w["how"] or "nearby locking syntax"
                        elif LOCKED_HELPERS.search(ctx):
                            w["locking_reference"] = True; w["how"] = w["how"] or "nearby locking-helper call"
    return writers


def table():
    rows = []
    for store, ws in sorted(scan().items()):
        rows.append({"store": store, "writers": sorted(ws), "files": sorted(f for w in ws.values() for f in w["files"]),
                     "locking_reference": all(w["locking_reference"] for w in ws.values()), "shared": len(ws) > 1, "rmw_status": "unverified",
                     "without_locking_reference": sorted(k for k, w in ws.items() if not w["locking_reference"]),
                     "how": {k: w.get("how", "") for k, w in ws.items() if w["locking_reference"]}})
    return rows


def render():
    rows = table()
    shared = [r for r in rows if r["shared"]]; unlocked = [r for r in shared if not r["locking_reference"]]
    out = ["# Memory stores: candidate writers and locking references", "",
           "Generated by `scripts/store_owners.py`. %d candidate store basenames; %d have multiple candidate writer modules. Regenerate with `python3 scripts/store_owners.py --write`." % (len(rows), len(shared)), "",
           "**This is a discovery inventory, not a concurrency certification.** A locking reference does not prove that the whole read-modify-write operation is protected, that fallback writes are safe, or that two paths refer to the same store. Missing references do not prove the absence of a lock. Every row's mutation safety remains unverified by this scanner. Basenames can combine different stores; indirect writers can be missed.", "",
           "## Shared-store candidates", "", "| store basename | candidate writers | nearby locking references |", "|---|---|---|"]
    out += ["| %s | %s | %s |" % (r["store"], ", ".join(r["writers"]),
                                   "detected for each candidate; scope unverified" if r["locking_reference"] else ("not detected for: " + ", ".join(r["without_locking_reference"]))) for r in shared]
    out += ["", "## One candidate writer found", "", "| store | writer |", "|---|---|"]
    out += ["| %s | %s |" % (r["store"], r["writers"][0]) for r in rows if not r["shared"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    t = render()
    if "--write" in sys.argv:
        open(os.path.join(REPO, "docs", "store-owners.md"), "w").write(t); print("written docs/store-owners.md")
    else:
        print(t)
