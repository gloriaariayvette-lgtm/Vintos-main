#!/usr/bin/env python3
"""capability-view.py - a versioned view of what he can actually do (reviews 28, 29).

Read-only. Derives, from the checkout it runs in:
  routes      every route registered in bin/server.py (method, path, guarded by the shared secret or
              public), by the same reading the route inventory test uses
  installed   the release map's view of installed files, when scripts/release-map.py can produce one
  receipts    the newest execution receipts that exist on this machine (effect receipts, post-turn
              records, delivery receipts, compute ledger) - paths and ages, never contents
  described   every entry in docs/CAPABILITIES.md that carries a `<!-- depends: ... -->` marker,
              checked against the routes and the files: VERIFIED when every dependency exists,
              UNVERIFIED naming what is missing

Stamped with the git revision and the diagnostic contract. `--write` puts it at
memory/capability-view.json; otherwise it prints JSON."""
import os, re, sys, json, glob, subprocess, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")

def git_rev():
    try:
        return subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"

def routes(server_path=None):
    src = open(server_path or os.path.join(REPO, "bin", "server.py"), errors="replace").read()
    out = []
    for dm in re.finditer(r'^@app\.(get|post|put|delete|patch)\("([^"]+)"[^\n]*\n(.*?)(?=^@app\.|\Z)', src, re.S | re.M):
        head = dm.group(3)[:2500]
        guarded = ("_require_secret(" in head) or ("X-Vintos-Secret" in head and "APP_SECRET" in head)
        out.append({"method": dm.group(1).upper(), "path": dm.group(2), "guarded": guarded})
    return out

def installed():
    rm = os.path.join(REPO, "scripts", "release-map.py")
    if not os.path.exists(rm):
        return {"available": False, "why": "no release map script"}
    try:
        r = subprocess.run([sys.executable, rm, "--src", REPO, "--json"], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip().startswith("{"):
            return {"available": True, "map": json.loads(r.stdout)}
        return {"available": False, "why": (r.stderr or r.stdout)[-300:] or "release map produced no JSON"}
    except Exception as e:
        return {"available": False, "why": str(e)[:200]}

def receipts():
    out = {}
    for name, pat in (("effect_receipts", "effect-receipts*.json*"), ("post_turn_records", "post-turn-record.jsonl"),
                      ("delivery_receipts", "delivery-receipts.json"), ("compute_ledger", "compute-ledger.jsonl"),
                      ("turn_records", "turn-records/*.json*")):
        files = sorted(glob.glob(os.path.join(MEMORY, pat)), key=lambda p: os.path.getmtime(p))
        if files:
            p = files[-1]
            out[name] = {"path": os.path.relpath(p, WS), "age_s": int(time.time() - os.path.getmtime(p)), "count": len(files)}
        else:
            out[name] = None
    return out

_MARK = re.compile(r"<!--\s*depends:\s*(.*?)\s*-->")

def described(caps_path=None, route_paths=None):
    """Every CAPABILITIES.md section with a depends marker, checked against routes and files."""
    p = caps_path or os.path.join(REPO, "docs", "CAPABILITIES.md")
    try:
        text = open(p, errors="replace").read()
    except Exception:
        return []
    rp = set(route_paths if route_paths is not None else [r["path"] for r in routes()])
    out = []
    for sec in re.split(r"\n(?=## )", text):
        title = sec.split("\n", 1)[0].lstrip("# ").strip()
        m = _MARK.search(sec)
        if not m:
            continue
        deps = [d.strip() for d in m.group(1).split(",") if d.strip()]
        missing = []
        for d in deps:
            if d.startswith("/"):
                if not any(d == r or (d.endswith("*") and r.startswith(d[:-1])) for r in rp):
                    missing.append(d)
            else:
                if not (os.path.exists(os.path.join(REPO, d)) or os.path.exists(os.path.join(WS, d))):
                    missing.append(d)
        out.append({"capability": title, "depends": deps, "status": "VERIFIED" if not missing else "UNVERIFIED", "missing": missing})
    return out

def build():
    rs = routes()
    doc = {"at": datetime.now().isoformat(), "git_rev": git_rev(), "routes": rs,
           "installed": installed(), "receipts": receipts(), "described": described(route_paths=[r["path"] for r in rs])}
    doc["summary"] = {"routes": len(rs), "guarded": sum(1 for r in rs if r["guarded"]),
                      "described": len(doc["described"]), "unverified": sum(1 for d in doc["described"] if d["status"] == "UNVERIFIED")}
    try:
        sys.path.insert(0, HERE)
        from diagnostic_contract import stamp
        doc = stamp(doc, "capability-view", path=__file__)
    except Exception:
        doc["contract"] = "capability-view"; doc["contract_version"] = "unstamped"
    return doc

def main(argv):
    doc = build()
    if "--write" in argv:
        os.makedirs(MEMORY, exist_ok=True)
        p = os.path.join(MEMORY, "capability-view.json")
        tmp = p + ".tmp"; json.dump(doc, open(tmp, "w"), indent=1); os.replace(tmp, p)
        print(p, json.dumps(doc["summary"]))
    else:
        print(json.dumps(doc, indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
