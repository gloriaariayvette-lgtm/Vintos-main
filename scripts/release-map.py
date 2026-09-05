#!/usr/bin/env python3
"""release-map.py — which reviewed file actually runs on this host (review P01, 2026-09-05).

For every Python/shell file in the checkout's bin/ and scripts/: is it in the deploy manifest, does an
installed copy exist where the deploy puts it, and does that copy match the checkout. Then the part
that would have caught campaign.py and the three self-model files: every module the server or a
deployed script imports or spawns by name, and whether THAT file is deployed and current.

    python3 scripts/release-map.py [--src <checkout>] [--json]
    bash scripts/deploy-atelier.sh --map        (same thing, from the deploy script)

Reads only. Never installs. A row is one of:
    current      installed copy matches the checkout
    STALE        installed copy differs from the checkout (older, or edited on the host)
    MISSING      referenced or manifested, but no installed copy
    host-only    installed copy exists, nothing in the checkout by that name
    not-deployed in the checkout, in neither manifest nor any import - inert until something names it
"""
import os, re, sys, json, hashlib, subprocess

HOME = os.path.expanduser("~")
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if "--src" in sys.argv: SRC = os.path.abspath(sys.argv[sys.argv.index("--src") + 1])
DEST = {"scripts": os.path.join(HOME, ".vintos", "workspace", "scripts"), "bin": os.path.join(HOME, "Vintos")}

def repo_commit_time(rel):
    try:
        out = subprocess.run(["git", "-C", SRC, "log", "-1", "--format=%ct", "--", rel], capture_output=True, text=True, timeout=10).stdout.strip()
        return int(out) if out else None
    except Exception:
        return None

def newer_side(area, f, inst):
    """For a STALE row: is the checkout or the host copy the newer one? A host-newer file was edited on
    Aegis (by hand, by the Study, or by an older deploy of a newer branch) and must be diffed, not overwritten."""
    try: host_t = os.path.getmtime(inst)
    except Exception: return "unknown"
    repo_t = repo_commit_time(area + "/" + f)
    if repo_t is None: return "unknown"
    import datetime as _dt
    if host_t > repo_t + 60:
        return "HOST NEWER (edited on host %s)" % _dt.datetime.fromtimestamp(host_t).strftime("%m-%d %H:%M")
    return "checkout newer"

def sha(p):
    try: return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
    except Exception: return None

def manifest():
    """SCRIPTS/BINS from deploy-atelier.sh: every double-quoted assignment to either, multi-line included."""
    dep = os.path.join(SRC, "scripts", "deploy-atelier.sh")
    try: t = open(dep).read()
    except Exception as e:
        print("could not read deploy-atelier.sh:", e, file=sys.stderr); return set(), set()
    out = {"SCRIPTS": set(), "BINS": set()}
    for var in out:
        for m in re.finditer(var + r'="((?:[^"\\]|\\.)*)"', t, re.S):
            for tok in m.group(1).split():
                if not tok.startswith("$") and tok.endswith((".py", ".sh", ".json")): out[var].add(tok)
    return out["SCRIPTS"], out["BINS"]

IMPORT_RE = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w]*)\s+import|import\s+([A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*))", re.M)
NAME_RE = re.compile(r"""["']([A-Za-z0-9_\-]+\.(?:py|sh))["']""")

def references(path):
    """Module names imported, and script file names spawned by name, in one source file."""
    try: t = open(path, errors="replace").read()
    except Exception: return set(), set()
    mods = set()
    for m in IMPORT_RE.finditer(t):
        for name in (m.group(1) or m.group(2) or "").split(","):
            name = name.strip()
            if name: mods.add(name)
    files = set(NAME_RE.findall(t))
    return mods, files

def main():
    scripts_m, bins_m = manifest()
    rows = []
    repo = {}
    repo_links = {}
    for area in ("scripts", "bin"):
        d = os.path.join(SRC, area)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith((".py", ".sh")) and not f.startswith("."):
                fp = os.path.join(d, f)
                if os.path.islink(fp):
                    # a symlink committed to git is not a source file: it names where the live copy is on the
                    # host. Comparing it to itself said "current" for every one of them (2026-09-05).
                    repo_links[(area, f)] = os.readlink(fp); continue
                repo[(area, f)] = fp
    # who references what: server + every manifested script + every repo script
    refs_mod, refs_file, by = set(), set(), {}
    for (area, f), p in repo.items():
        mods, files = references(p)
        for m in mods: refs_mod.add(m); by.setdefault(m, set()).add(f)
        for x in files: refs_file.add(x); by.setdefault(x, set()).add(f)
    def referenced(f):
        stem = f[:-3] if f.endswith(".py") else f
        return f in refs_file or stem in refs_mod or stem.replace("-", "_") in refs_mod
    for (area, f), p in sorted(repo.items()):
        inst = os.path.join(DEST[area], f)
        in_manifest = f in (scripts_m if area == "scripts" else bins_m)
        exists = os.path.exists(inst)
        live = os.path.realpath(inst) if exists else inst    # a symlinked install is judged by the file it points at
        state = ("current" if exists and sha(live) == sha(p) else "STALE" if exists else "MISSING")
        ref = referenced(f)
        if not in_manifest and not exists and not ref:
            state = "not-deployed"
        if f in ("deploy-atelier.sh", "release-map.py"):
            continue   # run from the checkout, never installed; naming themselves is not a reference
        link = os.readlink(inst) if exists and os.path.islink(inst) else None
        rows.append({"area": area, "file": f, "manifest": in_manifest, "referenced": ref,
                     "referenced_by": sorted(by.get(f, set()) | by.get(f[:-3] if f.endswith(".py") else f, set()))[:4],
                     "installed": inst if exists else None, "live": live if exists else None, "link": link, "state": state,
                     "newer": newer_side(area, f, live) if state == "STALE" else None})
    # host-only copies
    for area, d in DEST.items():
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith((".py", ".sh")) and (area, f) not in repo and (area, f) not in repo_links and not f.startswith("."):
                rows.append({"area": area, "file": f, "manifest": False, "referenced": False,
                             "referenced_by": [], "installed": os.path.join(d, f), "state": "host-only"})
    if "--diffs" in sys.argv:
        outd = sys.argv[sys.argv.index("--diffs") + 1] if len(sys.argv) > sys.argv.index("--diffs") + 1 and not sys.argv[sys.argv.index("--diffs") + 1].startswith("--") else os.path.join(HOME, ".vintos", "release-map")
        os.makedirs(outd, exist_ok=True)
        print("diffs: checkout (-) vs live host copy (+), written to", outd)
        for r in sorted(rows, key=lambda r: (r["area"], r["file"])):
            if r["state"] != "STALE": continue
            rp = repo[(r["area"], r["file"])]
            d = subprocess.run(["diff", "-u", rp, r["live"]], capture_output=True, text=True).stdout
            plus = sum(1 for l in d.splitlines() if l.startswith("+") and not l.startswith("+++"))
            minus = sum(1 for l in d.splitlines() if l.startswith("-") and not l.startswith("---"))
            fn = os.path.join(outd, "%s__%s.diff" % (r["area"], r["file"]))
            open(fn, "w").write(d)
            print("  %-8s %-34s host has +%-4d -%-4d  %s" % (r["area"], r["file"], plus, minus, r.get("newer") or ""))
        return
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1)); return
    order = {"MISSING": 0, "STALE": 1, "host-only": 2, "not-deployed": 3, "current": 4}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["area"], r["file"]))
    counts = {}
    for r in rows: counts[r["state"]] = counts.get(r["state"], 0) + 1
    print("release map for %s" % SRC)
    if repo_links: print("%d committed symlinks in the checkout were skipped as sources (they point at host paths)" % len(repo_links))
    print("installed roots: scripts -> %s, bin -> %s" % (DEST["scripts"], DEST["bin"]))
    print(" ".join("%s %d" % (k, v) for k, v in sorted(counts.items(), key=lambda kv: order.get(kv[0], 9))))
    print()
    for r in rows:
        if r["state"] == "current": continue
        why = []
        if r["state"] == "MISSING":
            why.append("in manifest" if r["manifest"] else "NOT in manifest")
            if r["referenced"]: why.append("referenced by " + ", ".join(r["referenced_by"]))
        if r["state"] == "STALE":
            why.append(r.get("newer") or "")
            why.append("in manifest - deploy will refresh it" if r["manifest"] else "NOT in manifest - deploy will NOT refresh it" + (", referenced by " + ", ".join(r["referenced_by"]) if r["referenced"] else ""))
        if r.get("link"): why.append("symlink -> " + r["link"])
        print("%-12s %-8s %-38s %s" % (r["state"], r["area"], r["file"], "; ".join(why)))
    # names the code spawns or loads by file name that exist in NEITHER the checkout nor the host
    # (the vintos-home.py class: every home route loaded a path with nothing at it)
    known = {r["file"] for r in rows} | {f for (_, f) in repo_links}
    nowhere = sorted(f for f in refs_file if f not in known and not any(os.path.exists(os.path.join(d, f)) for d in DEST.values())
                     and f not in ("deploy-atelier.sh", "release-map.py"))
    if nowhere:
        print("REFERENCED BY NAME, EXISTS NOWHERE (%d):" % len(nowhere))
        for f in nowhere: print("   %s  <- %s" % (f, ", ".join(sorted(by.get(f, set())))[:120]))
    missing_ref = [r for r in rows if r["state"] == "MISSING" and r["referenced"]]
    stale_unmanifested = [r for r in rows if r["state"] == "STALE" and not r["manifest"] and r["referenced"]]
    print()
    if missing_ref:
        print("REFERENCED BUT NOT ON THIS HOST (%d): these imports fail silently in try/except -" % len(missing_ref))
        for r in missing_ref: print("   %s/%s  <- %s" % (r["area"], r["file"], ", ".join(r["referenced_by"]) or "?"))
    if stale_unmanifested:
        print("REFERENCED, INSTALLED, BUT THE DEPLOY NEVER REFRESHES THEM (%d):" % len(stale_unmanifested))
        for r in stale_unmanifested: print("   %s/%s" % (r["area"], r["file"]))
    host_newer = [r for r in rows if r["state"] == "STALE" and str(r.get("newer", "")).startswith("HOST")]
    if host_newer:
        print("HOST COPY NEWER THAN THE CHECKOUT (%d) - diff before any install; these may hold repairs git never saw:" % len(host_newer))
        for r in host_newer: print("   %s/%s  %s%s" % (r["area"], r["file"], r["newer"], "  (IN MANIFEST: the next deploy overwrites it)" if r["manifest"] else ""))
    if not missing_ref and not stale_unmanifested:
        print("every referenced file is on this host and the deploy keeps it current.")

if __name__ == "__main__":
    main()
