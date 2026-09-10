#!/usr/bin/env python3
"""Review items 2, 11, 24, 25, 28, 29 (2026-09-10): the two server profiles register the same
things, the bootstrap seeds what the readers parse, the graphics bundle has a build entry, the
clients are listed, and the capability view verifies what CAPABILITIES.md describes. Scratch
HOME only; no network."""
import os, sys, ast, json, tempfile, subprocess, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-rel-")
os.environ["HOME"] = HOME
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

print("\n--- 2: nothing but uvicorn.run sits under the __main__ guard ---")
src = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
tree = ast.parse(src)
guards = [n for n in tree.body if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and getattr(n.test.left, "id", "") == "__name__"]
check("exactly one __main__ guard", len(guards) == 1, len(guards))
body = guards[0].body if guards else []
def names(node):
    out = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Attribute): out.add(x.attr)
        if isinstance(x, ast.Name): out.add(x.id)
    return out
under = set().union(*[names(n) for n in body]) if body else set()
check("no route, mount, router or startup handler under the guard", not ({"get", "post", "put", "delete", "mount", "include_router", "on_event", "add_api_route"} & under), sorted(under))
check("the guard only imports uvicorn and runs it", all(isinstance(n, (ast.Import, ast.ImportFrom, ast.Expr)) for n in body) and "run" in under, [type(n).__name__ for n in body])
last_route = max(m.end() for m in __import__("re").finditer(r'^@app\.(get|post|put|delete|patch)\(', src, __import__("re").M))
check("every route is defined before the guard", last_route < src.index('if __name__ == "__main__":'))
# review 10: duplicate route registrations, counted by AST over every nesting (a regex over the file
# also counts the routes named inside docstrings and the route-policy table, which is not a registration)
def _regs(node, chain=()):
    for ch in ast.iter_child_nodes(node):
        if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in ch.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post", "put", "delete", "patch", "api_route", "websocket") and d.args and isinstance(d.args[0], ast.Constant):
                    yield (d.func.attr, d.args[0].value)
            yield from _regs(ch, chain + (ch.name,))
        else:
            yield from _regs(ch, chain)
_all = list(_regs(tree)); _dup = {k for k in _all if _all.count(k) > 1}
check("no (method, path) is registered twice anywhere in server.py", not _dup, sorted(_dup))
check("docs/server-profiles.md names both profiles", all(k in open(os.path.join(REPO, "docs", "server-profiles.md")).read() for k in ("direct", "imported ASGI", "uvicorn.run")))

print("\n--- 11: the bootstrap seeds what the readers parse ---")
rc = subprocess.run(["bash", os.path.join(REPO, "bin", "setup_memory.sh")], capture_output=True, text=True, env=dict(os.environ, HOME=HOME))
check("setup_memory.sh runs clean into a scratch HOME", rc.returncode == 0 and "seeds validated" in rc.stdout, (rc.returncode, rc.stdout[-300:], rc.stderr[-300:]))
mem = os.path.join(HOME, ".vintos", "workspace", "memory")
st = open(os.path.join(mem, "emotional-state.txt")).read().strip().split("\n")
parsed = {l.split(":")[0].strip(): float(l.split(":")[1].split("|")[0]) for l in st if ":" in l}
check("emotional-state.txt parses the way emoclaw_utils reads it", len(parsed) >= 11 and parsed["Valence"] == 0.5, parsed)
check("trial-ledger seeds as {trials: []} for behavioral-intercept", json.load(open(os.path.join(mem, "trial-ledger.json"))) == {"trials": []})
check("interaction-ledger seeds as a list for the ledger", json.load(open(os.path.join(mem, "interaction-ledger.json"))) == [])
open(os.path.join(mem, "belief-sediment.json"), "w").write('["wrong shape"]')
rc2 = subprocess.run(["bash", os.path.join(REPO, "bin", "setup_memory.sh")], capture_output=True, text=True, env=dict(os.environ, HOME=HOME))
check("a seed the readers cannot parse fails the bootstrap", rc2.returncode != 0 and "SEED VALIDATION FAILED" in rc2.stdout and "belief-sediment.json" in rc2.stdout, rc2.stdout[-300:])

print("\n--- 24 / 25: bundle build entry, dependency manifest, clients listed ---")
rc3 = subprocess.run(["bash", os.path.join(REPO, "avatar", "build.sh")], capture_output=True, text=True)
check("avatar/build.sh runs and writes BUNDLE-MANIFEST.json", rc3.returncode == 0 and os.path.exists(os.path.join(REPO, "avatar", "BUNDLE-MANIFEST.json")), rc3.stdout + rc3.stderr)
bm = json.load(open(os.path.join(REPO, "avatar", "BUNDLE-MANIFEST.json")))
check("the manifest hashes every file and records no external dependency", bm["files"] and all("sha256" in f for f in bm["files"]) and bm["external_dependencies"] == [])
gb = open(os.path.join(REPO, "docs", "graphics-bundle.md")).read()
check("docs/graphics-bundle.md has a dependency table and a build entry", "three.js" in gb and "avatar/build.sh" in gb and "MIT" in gb)
cl = open(os.path.join(REPO, "docs", "clients.md")).read()
check("docs/clients.md lists each client with entry point, route and status", all(k in cl for k in ("phone app", "overlay.html", "ReelRoom", "active", "archived")))
check("the overlay was not moved", os.path.exists(os.path.join(REPO, "avatar", "overlay.html")))

print("\n--- 28 / 29: the capability view verifies what is described ---")
CV = load("cv_t", os.path.join(REPO, "scripts", "capability-view.py")); CV.MEMORY = mem; CV.WS = os.path.join(HOME, ".vintos", "workspace")
doc = CV.build()
check("routes derived with guarded/public", doc["summary"]["routes"] > 100 and 0 < doc["summary"]["guarded"] < doc["summary"]["routes"], doc["summary"])
check("every described capability carries dependencies and is VERIFIED", doc["described"] and all(d["status"] == "VERIFIED" and d["depends"] for d in doc["described"]), [d for d in doc["described"] if d["status"] != "VERIFIED"])
check("stamped with git rev and the diagnostic contract", doc.get("git_rev") and doc.get("contract") == "capability-view")
caps = open(os.path.join(REPO, "docs", "CAPABILITIES.md")).read()
check("CAPABILITIES.md carries a depends marker under every section", caps.count("<!-- depends:") == caps.count("\n## "), (caps.count("<!-- depends:"), caps.count("\n## ")))
tmp = os.path.join(HOME, "CAPS.md"); open(tmp, "w").write("## Flying\n<!-- depends: /api/fly, scripts/wings.py -->\nHe flies.\n")
d2 = CV.described(caps_path=tmp, route_paths=[r["path"] for r in doc["routes"]])
check("a described capability whose dependency is missing is UNVERIFIED, naming it", d2[0]["status"] == "UNVERIFIED" and set(d2[0]["missing"]) == {"/api/fly", "scripts/wings.py"}, d2)
rc4 = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "capability-view.py"), "--write"], capture_output=True, text=True, env=dict(os.environ, HOME=HOME))
check("--write lands memory/capability-view.json", rc4.returncode == 0 and os.path.exists(os.path.join(mem, "capability-view.json")), rc4.stdout + rc4.stderr)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
