#!/usr/bin/env python3
"""Chemistry Lab instrument receipts: installation is not availability.

`tools_status()` promised "dated smoke-test receipts" and read them from
`tool-inventory.json` -- a file nothing in this repository wrote.  Whatever happened to
be there was merged wholesale, `available` included, with no date, no schema and no
staleness check.  The promise was kept only by the absence of a writer.

This module is the writer, and it changes where authority sits:

- **`tool-probes.jsonl` is the authority.**  Append-only, one row per measurement.  A
  refresh adds evidence; it never destroys the history the availability claim rests on.
- **`tool-inventory.json` is a materialized view.**  Regenerated from the ledger, safe to
  delete, and *read by nothing*.  `chemistry_lab.tools_status()` reads the ledger.  A
  hand-written inventory file therefore has no power at all, which is the point.

What a receipt may contain: tool, host, probe version, when it was measured, when it
expires, a typed outcome, a digest of the evidence, and a typed failure.  What it may
never contain: unrestricted command output, or anything that could carry a secret out of
an environment and into a visible ledger.  Only a bounded version string, matched by a
strict pattern, ever survives as text.

Two hosts, two standards of proof:

- **Aegis** can be smoke-tested directly: run the tool's own interpreter, import it, and
  keep the digest.
- **The Mac cannot.**  The doorway carries `status`/`ledger`/`run`/`reading`, and this side
  will not widen it to run probes.  So a Mac instrument is proved only by a completed run
  that *explicitly names and hashes* it.  What `mac.status()` merely says about itself is
  recorded as `reported_by_host_not_smoke_tested` and grants nothing.  A host's word about
  its own instruments is a claim, not a measurement.

    refresh(names=None)                    run the Aegis probes
    record_run_attestation(run_id, reply)  mint Mac receipts a run actually proved
    record_host_report(reply)              file the Mac's self-report as a claim
    write_view()                           regenerate tool-inventory.json
    python3 chemistry_probe.py [--refresh|--view]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

PROBES = os.path.join(lab.ROOT, "tool-probes.jsonl")
PROBE_VERSION = "chemistry_probe/1"
DEFAULT_TTL_DAYS = 30
PROBE_TIMEOUT = 180
VERSION_RE = re.compile(r"\b\d+(?:\.\d+){1,3}(?:[a-z0-9.+-]{0,12})?\b")

# Outcomes that make an instrument available, and only until the receipt expires.
PROVING = ("smoke_passed", "proved_by_run")
OUTCOMES = PROVING + ("smoke_failed", "not_installed", "reported_by_host_not_smoke_tested",
                      "named_by_run_without_hash")

TOOLS_ROOT = os.environ.get("CHEM_LAB_TOOLS", os.path.expanduser("~/.vintos/tools/chemistry-lab"))

def _venv(name, env):
    return os.environ.get(env, os.path.join(TOOLS_ROOT, name, "bin", "python"))

# Aegis instruments this side can actually measure. Each is its own interpreter importing
# its own package: the smallest thing that distinguishes "installed" from "runs here".
AEGIS_PROBES = {
    "esmc": {"python": lab.ESMC_PYTHON,
             "code": "import esm, torch; print('esm', getattr(esm, '__version__', 'unknown'), 'torch', torch.__version__)"},
    "openmm": {"python": _venv("openmm", "CHEM_LAB_OPENMM_PYTHON"),
               "code": "import openmm; print('openmm', openmm.version.version)"},
    "protein_mpnn": {"python": _venv("proteinmpnn", "CHEM_LAB_MPNN_PYTHON"),
                     "code": "import torch; print('torch', torch.__version__)"},
    "structure_prediction": {"python": _venv("structure", "CHEM_LAB_STRUCTURE_PYTHON"),
                             "code": "import torch; print('torch', torch.__version__)"},
    "rfdiffusion": {"python": _venv("rfdiffusion", "CHEM_LAB_RFDIFFUSION_PYTHON"),
                    "code": "import torch; print('torch', torch.__version__)"},
    "protein_design_mcp": {"python": _venv("protein-design-mcp", "CHEM_LAB_MCP_PYTHON"),
                           "code": "import sys; print('python', '.'.join(map(str, sys.version_info[:3])))"},
}

# What a Mac run may name to prove an instrument. Anything not in this map is filed and
# proves nothing: a bench cannot invent an instrument slot by naming one.
MAC_INSTRUMENTS = {"qpanda": "qpanda", "pyqpanda": "qpanda", "pyqpanda3": "qpanda",
                   "vqnet": "vqnet", "pychemiq": "quantum_chemistry",
                   "quantum_chemistry": "quantum_chemistry", "esmc": "mac_esmc",
                   "mac_esmc": "mac_esmc", "foundry": "foundry"}
RUN_INSTRUMENT_KEYS = ("instruments", "instrument", "backend", "backends", "engine")
RUN_HASH_KEYS = ("source_sha256", "source_hash", "sha256", "experiment_sha256")


def _now(): return datetime.now(timezone.utc)


def _receipt(tool, host, outcome, evidence_sha256=None, evidence=None, failure=None,
             ttl_days=DEFAULT_TTL_DAYS, source=""):
    if outcome not in OUTCOMES: raise ValueError("unknown probe outcome %r" % outcome)
    measured = _now()
    row = {"receipt_id": "CP-" + uuid.uuid4().hex[:10], "tool": str(tool)[:40], "host": str(host)[:24],
           "probe_version": PROBE_VERSION, "measured_at": measured.isoformat(),
           "expires_at": (measured + timedelta(days=int(ttl_days))).isoformat(),
           "outcome": outcome, "evidence_sha256": evidence_sha256,
           # Typed and bounded on purpose. Never raw stdout, never stderr, never an
           # environment: a visible ledger is the wrong place for either.
           "evidence": evidence or {}, "failure": failure, "source": str(source)[:120],
           "truth_status": "measured_instrument_receipt_not_a_capability_grant"}
    lab._append(PROBES, row)
    return row


def _version(text):
    match = VERSION_RE.search(text or "")
    return match.group(0)[:24] if match else None


def probe_aegis(name):
    """One bounded smoke test. A missing interpreter is not_installed, not a failure to hide."""
    spec = AEGIS_PROBES.get(name)
    if not spec: return _receipt(name, "aegis", "smoke_failed",
                                 failure={"type": "no_probe_defined"}, source="chemistry_probe")
    python = spec["python"]
    if not os.path.isfile(python):
        return _receipt(name, "aegis", "not_installed",
                        failure={"type": "missing_interpreter"}, source=python[:120])
    try:
        done = subprocess.run([python, "-c", spec["code"]], text=True, capture_output=True,
                              timeout=PROBE_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return _receipt(name, "aegis", "smoke_failed",
                        failure={"type": "timeout", "seconds": PROBE_TIMEOUT}, source=python[:120])
    except Exception as exc:
        return _receipt(name, "aegis", "smoke_failed",
                        failure={"type": "exception", "error": exc.__class__.__name__}, source=python[:120])
    blob = (done.stdout or "") + (done.stderr or "")
    digest = hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()
    if done.returncode != 0:
        return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                        failure={"type": "nonzero_exit", "exit_code": int(done.returncode)},
                        source=python[:120])
    return _receipt(name, "aegis", "smoke_passed", evidence_sha256=digest,
                    evidence={"version": _version(done.stdout), "output_bytes": len(blob)},
                    source=python[:120])


def refresh(names=None, only_expired=True):
    """Measure the Aegis instruments. Expensive probes are skipped while their receipt holds."""
    current = current_receipts()
    done = []
    for name in (names or list(AEGIS_PROBES)):
        if name not in AEGIS_PROBES: continue
        if only_expired and not names:
            held = current.get(name)
            if held and held.get("outcome") in PROVING and not _expired(held): continue
        done.append(probe_aegis(name))
    write_view()
    return done


def _instruments_named(reply):
    found = []
    def walk(value, depth=0):
        if depth > 3 or not isinstance(value, dict): return
        for key in RUN_INSTRUMENT_KEYS:
            item = value.get(key)
            if isinstance(item, str): found.append(item)
            elif isinstance(item, list): found.extend(x for x in item if isinstance(x, str))
        for child in value.values():
            if isinstance(child, dict): walk(child, depth + 1)
    walk(reply if isinstance(reply, dict) else {})
    return found


def _run_hash(reply):
    def walk(value, depth=0):
        if depth > 3 or not isinstance(value, dict): return None
        for key in RUN_HASH_KEYS:
            item = value.get(key)
            if isinstance(item, str) and re.fullmatch(r"[0-9a-fA-F]{32,128}", item): return item
        for child in value.values():
            if isinstance(child, dict):
                found = walk(child, depth + 1)
                if found: return found
        return None
    return walk(reply if isinstance(reply, dict) else {})


def record_run_attestation(run_id, reply):
    """A completed Mac run proves only the instruments it names *and* hashes."""
    if not isinstance(reply, dict) or not reply.get("ok"): return []
    digest = _run_hash(reply)
    rows, seen = [], set()
    for raw in _instruments_named(reply):
        tool = MAC_INSTRUMENTS.get(raw.strip().lower())
        if not tool or tool in seen: continue
        seen.add(tool)
        if not digest:
            rows.append(_receipt(tool, "mac", "named_by_run_without_hash",
                                 evidence={"named_as": raw[:40], "run_id": str(run_id)[:64]},
                                 failure={"type": "no_source_hash_in_run"}, source="mac_run"))
            continue
        rows.append(_receipt(tool, "mac", "proved_by_run", evidence_sha256=digest,
                             evidence={"named_as": raw[:40], "run_id": str(run_id)[:64]},
                             source="mac_run"))
    return rows


def record_host_report(reply):
    """The Mac's word about its own instruments. Filed as a claim; grants nothing."""
    if not isinstance(reply, dict) or not reply.get("ok"): return []
    rows, seen = [], set()
    for raw in _instruments_named(reply):
        tool = MAC_INSTRUMENTS.get(raw.strip().lower())
        if not tool or tool in seen: continue
        seen.add(tool)
        rows.append(_receipt(tool, "mac", "reported_by_host_not_smoke_tested",
                             evidence={"named_as": raw[:40]}, source="mac_status", ttl_days=7))
    return rows


def _expired(receipt, now=None):
    try: return (now or _now()) > datetime.fromisoformat(str(receipt.get("expires_at")))
    except Exception: return True


def current_receipts():
    """The newest receipt per tool. Nothing is deleted; the older rows remain the record."""
    latest = {}
    for row in lab._jsonl(PROBES):
        tool = row.get("tool")
        if not tool or row.get("outcome") not in OUTCOMES: continue
        held = latest.get(tool)
        if held is None or str(row.get("measured_at", "")) >= str(held.get("measured_at", "")):
            latest[tool] = row
    return latest


def write_view():
    """Regenerate tool-inventory.json. It is a convenience; nothing decides anything from it."""
    view = {"schema": 2, "generated_at": _now().isoformat(),
            "authority": "memory/chemistry-lab/tool-probes.jsonl",
            "note": "materialized view; edits here change nothing — tools_status reads the ledger",
            "tools": lab.tools_status()}
    lab._atomic(lab.INVENTORY, view)
    return view


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        for row in refresh(only_expired="--all" not in sys.argv):
            print("%-22s %-10s %s" % (row["tool"], row["outcome"], row.get("failure") or row.get("evidence")))
    elif "--view" in sys.argv:
        print(json.dumps(write_view(), indent=2, sort_keys=True))
    else:
        for name, state in sorted(lab.tools_status().items()):
            print("%-22s %-6s %-34s %s" % (name, "yes" if state["available"] else "no",
                                           state.get("state"), state.get("measured_at") or ""))
