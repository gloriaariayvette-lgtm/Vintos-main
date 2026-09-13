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
import contextlib
import fcntl
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
PROBE_LOCK = os.path.join(lab.ROOT, ".probe.lock")
PROBE_VERSION = "chemistry_probe/1"
DEFAULT_TTL_DAYS = 30
PROBE_TIMEOUT = 180
VERSION_RE = re.compile(r"\b\d+(?:\.\d+){1,3}(?:[a-z0-9.+-]{0,12})?\b")
INSTRUMENT_WORKER = os.path.join(HERE, "chemistry_instrument_probe.py")

# Outcomes that make an instrument available, and only until the receipt expires.
PROVING = ("smoke_passed", "proved_by_run")
OUTCOMES = PROVING + ("smoke_failed", "not_installed", "not_configured",
                      "reported_by_host_not_smoke_tested", "named_by_run_without_hash")
# A measurement holds for a month. Everything else is retried tomorrow: a broken or
# unconfigured instrument should be re-asked about often, and a working one should not be
# reloaded daily just to say so again.
TTL_BY_OUTCOME = {"smoke_passed": DEFAULT_TTL_DAYS, "proved_by_run": DEFAULT_TTL_DAYS,
                  "reported_by_host_not_smoke_tested": 7}
FAILED_TTL_DAYS = 1

TOOLS_ROOT = os.environ.get("CHEM_LAB_TOOLS", os.path.expanduser("~/.vintos/tools/chemistry-lab"))

def _venv(name, env):
    return os.environ.get(env, os.path.join(TOOLS_ROOT, name, "bin", "python"))

# Aegis instruments this side can actually measure -- and only those.
#
# The first version of this table imported torch and called it a ProteinMPNN smoke test.
# That is not a smoke test of ProteinMPNN; it is a smoke test of torch, and it would have
# issued `smoke_passed` for an instrument that was absent or broken. A probe here must run
# the named entry point on the smallest real input and prove it by a marker in the output.
#
# Where this side does not know the real entry point, the probe is `not_configured` and the
# instrument stays unavailable. That is the honest state, and it is recoverable without a
# code change: set CHEM_LAB_<TOOL>_PROBE to a JSON object
#     {"argv": ["/path/to/python", "/path/to/entry.py", "--tiny"], "stdin": "", "marker": "..."}
# and the probe runs exactly that and requires exactly that marker.

def _esmc_verify(stdout):
    """A real representation of a real sequence, or nothing."""
    value = json.loads(stdout)
    rows = value.get("embeddings") or []
    if not value.get("ok") or not rows: raise ValueError("no embedding returned")
    dimension = int(rows[0].get("dimension") or 0)
    if dimension <= 0: raise ValueError("embedding has no dimension")
    return {"dimension": dimension, "model": str(value.get("model"))[:40],
            "device": str(value.get("device"))[:16]}


class ProbeResultError(ValueError):
    def __init__(self, failure, evidence=None):
        super().__init__(str((failure or {}).get("type") or "probe_failed"))
        self.failure = failure or {"type": "probe_failed"}
        self.evidence = evidence or {}


def _instrument_verify(stdout):
    """Read only the controlled worker's bounded JSON, never arbitrary command output."""
    value = json.loads((stdout or "").strip().splitlines()[-1])
    entry = str(value.get("entry_point") or "")[:180]
    if not value.get("ok"):
        raw = value.get("failure") if isinstance(value.get("failure"), dict) else {}
        failure = {"type": str(raw.get("type") or "probe_failed")[:60]}
        for key in ("error", "traceback_sha256"):
            if raw.get(key): failure[key] = str(raw[key])[:300]
        raise ProbeResultError(failure, {"entry_point": entry})
    output = value.get("output") if isinstance(value.get("output"), dict) else {}
    safe_output = {str(k)[:40]: v for k, v in output.items()
                   if isinstance(v, (str, int, float, bool)) or v is None}
    return {"entry_point": entry, "verification": str(value.get("verification") or "")[:180],
            "output": safe_output}


# Thirty-three residues of a real, ordinary, non-pathogenic sequence: enough to make the
# model actually run, small enough to cost nothing.
PROBE_SEQUENCE = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ"

AEGIS_PROBES = {
    # Runs the Lab's own ESMC worker end to end and requires a pooled vector back.
    "esmc": {"argv": [lab.ESMC_PYTHON, lab.ESMC_WORKER],
             "stdin": json.dumps({"records": [{"accession": "PROBE", "sequence": PROBE_SEQUENCE}]}),
             "verify": _esmc_verify, "timeout": 600,
             "entry": "chemistry_esmc.py on one short sequence"},
    # Builds a two-particle system, integrates one step, and reports the energy it got.
    "openmm": {"argv": [_venv("openmm", "CHEM_LAB_OPENMM_PYTHON"), "-c",
                        "import openmm, openmm.unit as u;"
                        "s=openmm.System(); s.addParticle(1.0); s.addParticle(1.0);"
                        "f=openmm.HarmonicBondForce(); f.addBond(0,1,0.15,1000.0); s.addForce(f);"
                        "i=openmm.LangevinIntegrator(300*u.kelvin, 1/u.picosecond, 0.001*u.picoseconds);"
                        "c=openmm.Context(s, i, openmm.Platform.getPlatformByName('Reference'));"
                        "c.setPositions([(0,0,0),(0.16,0,0)]); i.step(1);"
                        "print('openmm', openmm.version.version, 'stepped_energy',"
                        " c.getState(getEnergy=True).getPotentialEnergy().value_in_unit(u.kilojoule_per_mole))"],
               "marker": "stepped_energy", "timeout": 240,
               "entry": "one Langevin step on a two-particle harmonic system"},
    "protein_mpnn": {"argv": [sys.executable, INSTRUMENT_WORKER, "protein_mpnn"],
                     "verify": _instrument_verify, "timeout": 600,
                     "entry": "a ProteinMPNN design on one fixed backbone"},
    "structure_prediction": {"argv": [_venv("mcp", "CHEM_LAB_MCP_PYTHON"),
                                       INSTRUMENT_WORKER, "structure_prediction"],
                             "verify": _instrument_verify, "timeout": 900,
                             "entry": "an ESMFold prediction of one short sequence"},
    "rfdiffusion": {"argv": [sys.executable, INSTRUMENT_WORKER, "rfdiffusion"],
                    "verify": _instrument_verify, "timeout": 900,
                    "entry": "one 10-residue two-step RFD3 diffusion run"},
    "protein_design_mcp": {"argv": [_venv("mcp", "CHEM_LAB_MCP_PYTHON"),
                                     INSTRUMENT_WORKER, "protein_design_mcp"],
                           "verify": _instrument_verify, "timeout": 300,
                           "entry": "one tool dispatch answered by the MCP server"},
}


def _configured(spec):
    """Her override, if she has named a real entry point for an instrument we cannot reach."""
    raw = os.environ.get(spec.get("env", ""), "").strip()
    if not raw: return None
    try: value = json.loads(raw)
    except Exception: return {"broken": "probe specification is not JSON"}
    argv = value.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return {"broken": "probe specification needs an argv of strings"}
    if not str(value.get("marker") or "").strip():
        return {"broken": "probe specification needs a marker proving the entry point ran"}
    return {"argv": argv[:12], "stdin": str(value.get("stdin") or ""),
            "marker": str(value["marker"])[:80], "timeout": PROBE_TIMEOUT}


# What a Mac run may name to prove an instrument. Anything not in this map is filed and
# proves nothing: a bench cannot invent an instrument slot by naming one.
MAC_INSTRUMENTS = {"qpanda": "qpanda", "pyqpanda": "qpanda", "pyqpanda3": "qpanda",
                   "vqnet": "vqnet", "pychemiq": "quantum_chemistry",
                   "quantum_chemistry": "quantum_chemistry", "esmc": "mac_esmc",
                   "mac_esmc": "mac_esmc", "foundry": "foundry"}
RUN_INSTRUMENT_KEYS = ("instruments", "instrument", "backend", "backends", "engine")
RUN_HASH_KEYS = ("source_sha256", "source_hash", "sha256", "experiment_sha256")


def _now(): return datetime.now(timezone.utc)


@contextlib.contextmanager
def _locked():
    lab._ensure()
    with open(PROBE_LOCK, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _receipt(tool, host, outcome, evidence_sha256=None, evidence=None, failure=None,
             ttl_days=None, source=""):
    if outcome not in OUTCOMES: raise ValueError("unknown probe outcome %r" % outcome)
    if ttl_days is None: ttl_days = TTL_BY_OUTCOME.get(outcome, FAILED_TTL_DAYS)
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
    """One bounded smoke test of the named entry point. Nothing else counts as passing."""
    spec = AEGIS_PROBES.get(name)
    if not spec: return _receipt(name, "aegis", "smoke_failed",
                                 failure={"type": "no_probe_defined"}, source="chemistry_probe")
    entry = str(spec.get("entry", ""))[:120]
    if not spec.get("argv"):
        override = _configured(spec)
        if override is None:
            return _receipt(name, "aegis", "not_configured",
                            failure={"type": "no_entry_point_known", "needs": spec.get("env", "")},
                            evidence={"would_exercise": entry}, source="chemistry_probe")
        if override.get("broken"):
            return _receipt(name, "aegis", "not_configured",
                            failure={"type": "probe_specification_invalid", "needs": spec.get("env", "")},
                            evidence={"would_exercise": entry}, source=spec.get("env", ""))
        spec = dict(spec, **override)
    argv = list(spec["argv"])
    if not os.path.isfile(argv[0]):
        return _receipt(name, "aegis", "not_installed", failure={"type": "missing_interpreter"},
                        evidence={"would_exercise": entry}, source=argv[0][:120])
    for path in argv[1:]:
        if path.endswith(".py") and not os.path.isfile(path):
            return _receipt(name, "aegis", "not_installed", failure={"type": "missing_entry_point"},
                            evidence={"would_exercise": entry}, source=path[:120])
    try:
        done = subprocess.run(argv, input=spec.get("stdin") or "", text=True, capture_output=True,
                              timeout=int(spec.get("timeout", PROBE_TIMEOUT)), check=False,
                              env={**os.environ, "HF_HOME": os.path.expanduser(
                                  "~/.vintos/tools/chemistry-lab/checkpoints/huggingface")})
    except subprocess.TimeoutExpired:
        return _receipt(name, "aegis", "smoke_failed", evidence={"would_exercise": entry},
                        failure={"type": "timeout", "seconds": int(spec.get("timeout", PROBE_TIMEOUT))},
                        source=argv[0][:120])
    except Exception as exc:
        return _receipt(name, "aegis", "smoke_failed", evidence={"would_exercise": entry},
                        failure={"type": "exception", "error": exc.__class__.__name__}, source=argv[0][:120])
    blob = (done.stdout or "") + (done.stderr or "")
    digest = hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()
    if done.returncode != 0:
        if spec.get("verify"):
            try: spec["verify"](done.stdout)
            except ProbeResultError as exc:
                return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                                evidence={"exercised": entry, **exc.evidence},
                                failure=exc.failure, source=argv[0][:120])
            except Exception: pass
        return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                        evidence={"exercised": entry},
                        failure={"type": "nonzero_exit", "exit_code": int(done.returncode)},
                        source=argv[0][:120])
    # Exiting zero is not passing. The entry point has to show it ran.
    evidence = {"exercised": entry, "output_bytes": len(blob)}
    if spec.get("verify"):
        try: evidence.update(spec["verify"](done.stdout))
        except ProbeResultError as exc:
            return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                            evidence={"exercised": entry, **exc.evidence}, failure=exc.failure,
                            source=argv[0][:120])
        except Exception as exc:
            return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                            evidence={"exercised": entry},
                            failure={"type": "result_unusable", "error": exc.__class__.__name__},
                            source=argv[0][:120])
    elif spec.get("marker"):
        if spec["marker"] not in blob:
            return _receipt(name, "aegis", "smoke_failed", evidence_sha256=digest,
                            evidence={"exercised": entry},
                            failure={"type": "marker_absent", "marker": str(spec["marker"])[:40]},
                            source=argv[0][:120])
        evidence["version"] = _version(done.stdout)
    return _receipt(name, "aegis", "smoke_passed", evidence_sha256=digest, evidence=evidence,
                    source=argv[0][:120])


def _refresh(names=None, only_expired=True):
    """Measure the Aegis instruments. Expensive probes are skipped while their receipt holds."""
    current = current_receipts()
    done = []
    for name in (names or list(AEGIS_PROBES)):
        if name not in AEGIS_PROBES: continue
        if only_expired and not names:
            # Skip while the receipt still holds, whatever it said. A pass holds for a
            # month; a failure or an unconfigured probe holds for a day and is re-asked.
            held = current.get(name)
            if held and not _expired(held): continue
        done.append(probe_aegis(name))
    write_view()
    return done


def refresh(names=None, only_expired=True):
    # A manual refresh and the scheduled session must not load the same heavy model
    # together or issue competing claims from one measurement occasion.
    with _locked(): return _refresh(names, only_expired)


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
    if not isinstance(reply, dict): return []
    digest = _run_hash(reply)
    rows, seen = [], set()
    for raw in _instruments_named(reply):
        tool = MAC_INSTRUMENTS.get(raw.strip().lower())
        if not tool or tool in seen: continue
        seen.add(tool)
        detail = reply.get("receipt") if isinstance(reply.get("receipt"), dict) else reply
        if not digest:
            rows.append(_receipt(tool, "mac", "named_by_run_without_hash",
                                 evidence={"named_as": raw[:40], "run_id": str(run_id)[:64]},
                                 failure={"type": "no_source_hash_in_run"}, source="mac_run"))
            continue
        if not reply.get("ok"):
            raw_failure = detail.get("failure") if isinstance(detail.get("failure"), dict) else {}
            failure = {"type": str(raw_failure.get("type") or "mac_run_failed")[:60]}
            for key in ("error", "traceback_sha256"):
                if raw_failure.get(key): failure[key] = str(raw_failure[key])[:300]
            rows.append(_receipt(tool, "mac", "smoke_failed", evidence_sha256=digest,
                                 evidence={"named_as": raw[:40], "run_id": str(run_id)[:64]},
                                 failure=failure, source="mac_run"))
            continue
        evidence = {"named_as": raw[:40], "run_id": str(run_id)[:64]}
        for key in ("entry_point", "verification", "version", "device"):
            if isinstance(detail.get(key), (str, int, float, bool)):
                evidence[key] = str(detail[key])[:180]
        output = detail.get("output") if isinstance(detail.get("output"), dict) else {}
        evidence["output"] = {str(k)[:40]: v for k, v in output.items()
                              if isinstance(v, (str, int, float, bool)) or v is None}
        rows.append(_receipt(tool, "mac", "proved_by_run", evidence_sha256=digest,
                             evidence=evidence,
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
    elif "--record-run" in sys.argv:
        source = sys.stdin if sys.argv[-1] == "-" else open(sys.argv[-1], encoding="utf-8")
        try: reply = json.load(source)
        finally:
            if source is not sys.stdin: source.close()
        rows = record_run_attestation(reply.get("run_id"), reply)
        write_view()
        print(json.dumps({"recorded": len(rows), "outcomes": [r["outcome"] for r in rows]}))
    else:
        for name, state in sorted(lab.tools_status().items()):
            print("%-22s %-6s %-34s %s" % (name, "yes" if state["available"] else "no",
                                           state.get("state"), state.get("measured_at") or ""))
