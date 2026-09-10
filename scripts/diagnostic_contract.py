#!/usr/bin/env python3
"""diagnostic_contract.py - every diagnostic output names its contract and its producer (review 375).

    from diagnostic_contract import stamp, expect
    out = stamp(out, "systems-checkup")            # adds contract_version, producer {file, git_rev, at}
    ok, why = expect(doc, "systems-checkup")       # a reader that wants another version says so

CONTRACTS holds the version of each producer's output shape. Bump a version when a field's
meaning changes, not when a field is added. A reader compares major versions only."""
import os, json, subprocess
from datetime import datetime

CONTRACTS = {
    "systems-checkup": "1.0",       # bin/systems-checkup.py --json: {spark, manip, campaign, stratagem}
    "subsystem-audit": "1.0",       # scripts/subsystem_audit.py: memory/subsystem-audit.md header + lines
    "system-status": "1.0",         # bin/server.py GET /api/system/status
    "capability-view": "1.0",       # scripts/capability-view.py
    "compute-report": "1.0",        # scripts/compute-report.py
}

def git_rev(path=None):
    try:
        here = os.path.dirname(os.path.abspath(path or __file__))
        return subprocess.run(["git", "-C", here, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"

def producer(name, path=None):
    return {"name": name, "file": os.path.relpath(os.path.abspath(path or __file__), os.path.expanduser("~")) if path else name,
            "git_rev": git_rev(path), "at": datetime.now().isoformat()}

def stamp(doc, name, path=None):
    """Return doc (a dict) with contract_version and producer set. A non-dict is wrapped."""
    if name not in CONTRACTS:
        raise KeyError("unknown diagnostic contract %r" % name)
    if not isinstance(doc, dict):
        doc = {"value": doc}
    doc = dict(doc)
    doc["contract"] = name
    doc["contract_version"] = CONTRACTS[name]
    doc["producer"] = producer(name, path)
    return doc

def header_line(name, path=None):
    """One line for text producers (markdown headers)."""
    p = producer(name, path)
    return "contract: %s v%s · producer: %s @ %s · %s" % (name, CONTRACTS[name], p["file"], p["git_rev"], p["at"])

def expect(doc, name, version=None):
    """(ok, why): the reader's expectation against what the document says it is."""
    want = (version or CONTRACTS.get(name, "0")).split(".")[0]
    if not isinstance(doc, dict) or doc.get("contract") != name:
        return False, "document is not a %s output (contract=%r)" % (name, (doc or {}).get("contract") if isinstance(doc, dict) else None)
    got = str(doc.get("contract_version", "0")).split(".")[0]
    if got != want:
        return False, "expected %s v%s, got v%s from %s" % (name, want, got, (doc.get("producer") or {}).get("file"))
    return True, ""
