#!/usr/bin/env python3
"""No route is registered twice (2026-10-03). Six routes moved out of server.py into server_domains/humor_wants.py
were never removed from one side; the first registered ran, the other never did, and Sol's route gate rang every
day ("shadow routes GREW: 6 vs baseline 0"). Read from the source only: nothing is imported or started."""
import collections, glob, os, re, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))

DECO = re.compile(r'^@(app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')
where = collections.defaultdict(list)
for path in [os.path.join(REPO, "bin", "server.py")] + sorted(glob.glob(os.path.join(REPO, "bin", "server_domains", "*.py"))):
    if os.path.basename(path).startswith("patch_"):
        continue      # one-off patch scripts carry route text inside strings
    for i, line in enumerate(open(path, errors="replace"), 1):
        m = DECO.match(line)
        if m:
            where[(m.group(2).upper(), m.group(3))].append("%s:%d" % (os.path.relpath(path, REPO), i))
twice = {"%s %s" % k: v for k, v in where.items() if len(v) > 1}
check("no route is registered twice across server.py and its domain modules", not twice, twice)
check("the six the gate counted are each in one place",
      all(len(where[k]) == 1 for k in (("GET", "/api/humor/profile"), ("POST", "/api/humor/rate"), ("GET", "/api/mischief/log"),
                                        ("POST", "/api/mischief/rate/{filename}"), ("PATCH", "/api/wants/{want_id}"),
                                        ("PATCH", "/api/wants/{want_id}/multistep"))))
check("the wants routes are the domain's (store-locked), the humor routes server.py's, as they ran before",
      where[("PATCH", "/api/wants/{want_id}")][0].startswith("bin/server_domains/humor_wants.py")
      and where[("GET", "/api/humor/profile")][0].startswith("bin/server.py"))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
