#!/usr/bin/env bash
# avatar/build.sh - the reproducible build entry for what this checkout owns of the graphics bundle
# (review 24). Validates clips/manifest.json against the files on disk, checks overlay.html has no
# external dependency, and writes BUNDLE-MANIFEST.json (file, bytes, sha256). Fetches nothing.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
python3 - "$here" <<'PY'
import os, sys, json, hashlib, re
here = sys.argv[1]; bad = []
ov = os.path.join(here, "overlay.html")
src = open(ov, errors="replace").read()
ext = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', src)
if ext: bad.append("overlay.html has external dependencies: %s" % ", ".join(ext))
man_p = os.path.join(here, "clips", "manifest.json")
files = []
try:
    man = json.load(open(man_p))
    entries = man if isinstance(man, list) else (man.get("clips") or man.get("files") or [])
    names = [e if isinstance(e, str) else (e.get("file") or e.get("src") or e.get("name")) for e in entries]
    for n in names:
        if not n: continue
        p = os.path.join(here, "clips", os.path.basename(n))
        if not os.path.exists(p): bad.append("manifest names a clip that is not on disk: %s" % n)
except FileNotFoundError:
    bad.append("clips/manifest.json missing")
except Exception as e:
    bad.append("clips/manifest.json unreadable: %s" % e)
for root, _, fs in os.walk(here):
    for f in fs:
        if f in ("BUNDLE-MANIFEST.json", "build.sh"): continue
        p = os.path.join(root, f)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        files.append({"file": os.path.relpath(p, here), "bytes": os.path.getsize(p), "sha256": h})
out = {"built_from": "avatar/build.sh", "files": sorted(files, key=lambda x: x["file"]), "external_dependencies": ext,
       "note": "the three.js stage itself is packaged in the phone app (vintos-app); see docs/graphics-bundle.md"}
tmp = os.path.join(here, "BUNDLE-MANIFEST.json.tmp"); json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, os.path.join(here, "BUNDLE-MANIFEST.json"))
if bad:
    print("BUNDLE CHECK FAILED:"); [print("  - " + b) for b in bad]; sys.exit(1)
print("bundle manifest written: %d file(s), no external dependencies" % len(files))
PY
