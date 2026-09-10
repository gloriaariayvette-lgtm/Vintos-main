#!/usr/bin/env python3
"""store_compat.py - incremental store migration with compatibility readers and backups (review 48).

    from store_compat import load_json_compat, save_json_compat

    data, version = load_json_compat(path, migrations=[(1, m_0_to_1), (2, m_1_to_2)], default=[])
    ...
    save_json_compat(path, data, version)

A store family changes shape over time. Readers keep reading every shape: load_json_compat reads
the file, detects its version (a top-level "schema_version" when the store is a dict; the version
recorded in a sidecar <path>.version otherwise; 0 when neither exists) and applies the migrations
whose target version is newer, IN MEMORY. Nothing is rewritten by a read. The first WRITE at a new
version keeps a copy of the on-disk file as <path>.bak-v<old> before replacing it, and records the
new version in the sidecar for stores that are lists. Never a wholesale rewrite of anything that
was only read."""
import os, json, shutil

def _sidecar(path):
    return path + ".version"

def detect_version(path, data):
    if isinstance(data, dict) and "schema_version" in data:
        try: return int(str(data.get("schema_version")).split(".")[0])
        except Exception: return 0
    try:
        return int(open(_sidecar(path)).read().strip() or 0)
    except Exception:
        return 0

def load_json_compat(path, migrations=(), default=None):
    """-> (data, version_after_migrations). A missing file gives (default, latest target). An unreadable
    file raises (the caller's quarantine rule applies; this never treats corruption as empty)."""
    latest = max([v for v, _ in migrations], default=0)
    if not os.path.exists(path):
        return (default if default is not None else {}), latest
    with open(path) as f:
        data = json.load(f)
    version = detect_version(path, data)
    for target, fn in sorted(migrations, key=lambda m: m[0]):
        if target > version:
            data = fn(data)
            version = target
    return data, version

def save_json_compat(path, data, version, indent=2):
    """Write data at `version`. If the on-disk file is at an older version, it is kept as
    <path>.bak-v<old> first (once per version step)."""
    old_version = 0
    if os.path.exists(path):
        try:
            with open(path) as f:
                old_version = detect_version(path, json.load(f))
        except Exception:
            old_version = -1     # unreadable: keep it too
        if old_version != version:
            bak = "%s.bak-v%s" % (path, old_version if old_version >= 0 else "unreadable")
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
    if isinstance(data, dict) and version:
        data = dict(data); data["schema_version"] = version
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(data, f, indent=indent)
    os.replace(tmp, path)
    if not isinstance(data, dict):
        with open(_sidecar(path), "w") as f:
            f.write(str(version))
    return path

# --- the two store families that changed shape on 2026-09-05 --------------------------------
def ledger_v1(rows):
    """interaction-ledger.json: rows gained turn_id / surface / imprint_attached_late on 09-05.
    Older rows are read as legacy: the keys exist, set to None, so consumers need no branches."""
    if not isinstance(rows, list):
        return rows
    for r in rows:
        if isinstance(r, dict):
            r.setdefault("turn_id", None); r.setdefault("surface", None)
    return rows

def wal_v1(store):
    """the WAL log: entries gained source_turns (P04-05) on 09-05; older entries read with []."""
    if isinstance(store, dict):
        for e in store.get("entries") or []:
            if isinstance(e, dict):
                e.setdefault("source_turns", [])
    return store

LEDGER_MIGRATIONS = [(1, ledger_v1)]
WAL_MIGRATIONS = [(1, wal_v1)]
