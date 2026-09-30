#!/usr/bin/env python3
"""Lab-only SSH doorway to the visible Chemistry bench on the Mac.

This deliberately has a separate config and command from Atelier QLab.  It
accepts JSON, returns JSON, and never retries a timed-out experiment whose
remote outcome is unknown.

**The door on the far side is wider than this one.**  ``bench_remote.py`` accepts
``action: "code"`` and will write a new executable experiment into the bench.  That
capacity belongs to the playground and is not something to quietly delete -- but it is
not the scheduled Lab's to reach.  Saying "this client simply has no code action" was an
argument from omission: an omission is undone by one careless edit.  So the allowlist
below is explicit and enforced at the point of send, and every refusal is returned as a
value rather than raised, in the shape the callers already read.

This is defence in depth on the near side only.  It does not make the far door safe.
The Mac's own ``code`` action still needs its own authenticated authority, separate from
the scheduled named-experiment route; ``docs/open-work.md`` carries that as open.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import uuid

MAX_HP_LATTICE_RESIDUES = 9
AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
HP_HYDROPHOBIC = frozenset("ACILMFV")  # Kyte-Doolittle >= 1.0, matching the Mac experiment

CONFIG = os.environ.get("VINTOS_CHEMISTRY_MAC_CONFIG",
                        os.path.expanduser("~/.vintos/chemistry-mac.json"))
DEFAULT_COMMAND = "/Users/kevin/qlab/bench_remote.py"
ESMFOLD_PYTHON = os.environ.get(
    "VINTOS_ESMFOLD_PYTHON",
    os.path.expanduser("~/.vintos/tools/chemistry-lab/esmc/bin/python"))
# The only actions the scheduled Lab may put through this door.  "code" is deliberately
# absent and must stay absent: named experiments in, results out.
ALLOWED_ACTIONS = ("status", "ledger", "run", "reading")
HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+$")
COMMAND_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")


def _read_config():
    try:
        with open(CONFIG, encoding="utf-8") as stream: cfg = json.load(stream)
    except FileNotFoundError:
        return None, "not configured"
    except Exception as exc:
        return None, "config unreadable: %s" % exc
    if not isinstance(cfg, dict): return None, "config is not an object"
    if not HOST_RE.fullmatch(str(cfg.get("host", ""))):
        return None, "config host must be user@tailscale-host"
    if not COMMAND_RE.fullmatch(str(cfg.get("command", DEFAULT_COMMAND))):
        return None, "config command must be one absolute path"
    return cfg, None


def _command(cfg):
    command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
               "-o", "StrictHostKeyChecking=accept-new"]
    identity = str(cfg.get("identity_file", "")).strip()
    if identity:
        command += ["-i", os.path.expanduser(identity), "-o", "IdentitiesOnly=yes"]
    if cfg.get("port"): command += ["-p", str(int(cfg["port"]))]
    command += [cfg["host"], shlex.quote(str(cfg.get("command", DEFAULT_COMMAND)))]
    return command


def request(body, timeout=600):
    if not isinstance(body, dict):
        return {"ok": False, "configured": False, "error": "Lab doorway body must be an object"}
    action = str(body.get("action", ""))
    if action not in ALLOWED_ACTIONS:
        return {"ok": False, "configured": False, "refused": "action_not_allowed",
                "error": "the Lab doorway carries %s only; %r is not the scheduled route's to send"
                         % ("/".join(ALLOWED_ACTIONS), action[:40])}
    cfg, error = _read_config()
    if error: return {"ok": False, "configured": False, "error": error}
    if action == "run":
        try:
            from voice_local import models as _voice_models
            _voice_models(False, evict_ears=True)
        except Exception:
            pass
    try:
        done = subprocess.run(_command(cfg), input=json.dumps(body), text=True,
                              capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "configured": True, "state": "unknown_after_timeout",
                "error": "Mac Lab experiment timed out after send; not retried"}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": "Mac Lab doorway failed: %s" % exc}
    if done.returncode and not done.stdout.strip():
        return {"ok": False, "configured": True,
                "error": "Mac Lab unreachable: " + done.stderr.strip()[-500:]}
    try: reply = json.loads(done.stdout)
    except Exception:
        return {"ok": False, "configured": True, "error": "Mac Lab returned unreadable output",
                "detail": done.stdout[-500:]}
    if not isinstance(reply, dict):
        return {"ok": False, "configured": True, "error": "Mac Lab reply is not an object"}
    reply["configured"] = True
    return reply


def status(timeout=20): return request({"action": "status"}, timeout=timeout)
def ledger(limit=12): return request({"action": "ledger", "limit": int(limit)}, timeout=30)
def _accession(parameters):
    """One exact requested accession, or none. Conflicting names are a refusal."""
    values = {str(parameters.get(key) or "").strip().upper()
              for key in ("requested_accession", "target_accession", "accession")
              if str(parameters.get(key) or "").strip()}
    if len(values) > 1:
        raise ValueError("protein request names conflicting accessions")
    if not values:
        return ""
    value = values.pop()
    if not re.fullmatch(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?", value):
        raise ValueError("protein request needs one exact UniProt accession")
    return value


def _record_sequence(record, accession):
    if not isinstance(record, dict):
        raise ValueError("UniProt returned no record for %s" % accession)
    found = str(record.get("primaryAccession") or record.get("accession") or "").upper()
    if found != accession:
        raise ValueError("UniProt returned %s while %s was requested" % (found or "no accession", accession))
    sequence_block = record.get("sequence")
    sequence = (sequence_block.get("value") if isinstance(sequence_block, dict) else sequence_block)
    sequence = re.sub(r"\s+", "", str(sequence or "").upper())
    if not sequence or any(letter not in AMINO_ACIDS for letter in sequence):
        raise ValueError("UniProt returned no usable sequence for %s" % accession)
    reported = (sequence_block.get("length") if isinstance(sequence_block, dict) else record.get("length"))
    if reported not in (None, "") and int(reported) != len(sequence):
        raise ValueError("UniProt sequence length disagrees for %s" % accession)
    return sequence


def _resolve_uniprot(accession):
    from lab_sources import Sources
    result = Sources().query({"source": "uniprot", "query": "accession:%s" % accession, "limit": 1})
    records = result.get("records") if isinstance(result, dict) else None
    record = records[0] if isinstance(records, list) and records else None
    return record, {"provider": "UniProtKB", "accession": accession,
                    "receipt_id": str(result.get("receipt_id") or "")}


def _hp_mapping(sequence):
    return [{"position": index + 1, "residue": residue,
             "hp": "H" if residue in HP_HYDROPHOBIC else "P"}
            for index, residue in enumerate(sequence)]


def prepare_protein(parameters, resolver=None):
    """Bind a named protein request to its exact sourced sequence before SSH."""
    parameters = dict(parameters or {})
    accession = _accession(parameters)
    if not accession:
        return {"ok": True, "parameters": parameters, "sequence_request": None}
    try:
        record, provenance = (resolver or _resolve_uniprot)(accession)
        sequence = _record_sequence(record, accession)
    except Exception as exc:
        return {"ok": False, "refused": "sequence_unavailable", "requested_accession": accession,
                "error": "could not source %s from UniProt: %s" % (accession, str(exc)[:240])}
    parameters.update({"requested_accession": accession, "target_accession": accession,
                       "sequence": sequence, "sequence_source": provenance})
    contract = {"requested_accession": accession, "sequence": sequence, "length": len(sequence),
                "source": provenance, "hp_mapping": _hp_mapping(sequence)}
    # The HP lattice remains deliberately tiny. A complete sourced protein is routed to
    # the commissioned local ESMFold instrument instead of being truncated or refused.
    # The returned result still passes the same accession/sequence identity contract.
    parameters["protein_backend"] = ("esmfold" if len(sequence) > MAX_HP_LATTICE_RESIDUES
                                     else "hp_lattice")
    return {"ok": True, "parameters": parameters, "sequence_request": contract}


def _run_esmfold(parameters, contract, worker=None):
    body = {"accession": contract["requested_accession"], "sequence": contract["sequence"],
            "sequence_source": contract["source"], "hp_mapping": contract["hp_mapping"]}
    if worker is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chemistry_esmfold.py")
        try:
            done = subprocess.run([ESMFOLD_PYTHON, path], input=json.dumps(body), text=True,
                                  capture_output=True, timeout=900, check=False)
        except subprocess.TimeoutExpired:
            return {"ok": False, "state": "unknown_after_timeout",
                    "error": "local ESMFold timed out; outcome not retried"}
        if done.returncode:
            detail = done.stderr.strip()
            try:
                reported = json.loads(done.stdout)
                if isinstance(reported, dict) and reported.get("error"):
                    detail = str(reported["error"])
            except Exception:
                pass
            return {"ok": False, "error": "local ESMFold failed: " + detail[-500:]}
        try: result = json.loads(done.stdout)
        except Exception:
            return {"ok": False, "error": "local ESMFold returned unreadable output"}
    else:
        result = worker(body)
    if not isinstance(result, dict) or not result.get("ok"):
        return result if isinstance(result, dict) else {"ok": False, "error": "local ESMFold returned no result"}
    run_id = "ESMFOLD-" + uuid.uuid4().hex[:12]
    reply = {"ok": True, "configured": True, "run_id": run_id,
             "run": {"run_id": run_id, "experiment": "protein", "parameters": parameters,
                     "execution": {"instrument": "Aegis ESMFold", "network": "local_files_only",
                                   "writes": "chemistry Lab artifact store"},
                     "result": result["result"]}}
    return _protein_result(reply, contract)


def _protein_result(reply, contract):
    """Fail a remote success whose title, sequence, or accession contradicts the request."""
    if not contract or not isinstance(reply, dict) or not reply.get("ok"):
        return reply
    result = (((reply.get("run") or {}).get("result")) if isinstance(reply.get("run"), dict)
              else reply.get("result"))
    result = result if isinstance(result, dict) else {}
    expected_accession, expected_sequence = contract["requested_accession"], contract["sequence"]
    actual_accession = str(result.get("requested_accession") or "").upper()
    actual_sequence = str(result.get("modeled_sequence") or result.get("real_sequence") or "").upper()
    source = result.get("sequence_source") if isinstance(result.get("sequence_source"), dict) else {}
    mapping = result.get("hp_mapping") if isinstance(result.get("hp_mapping"), list) else []
    title = str(result.get("title") or "")
    problems = []
    if actual_accession != expected_accession: problems.append("result accession %r" % actual_accession)
    if actual_sequence != expected_sequence: problems.append("modeled sequence differs from UniProt")
    if result.get("modeled_sequence_length") != len(expected_sequence): problems.append("modeled length differs")
    if str(source.get("accession") or "").upper() != expected_accession: problems.append("source accession differs")
    if [(row.get("position"), row.get("residue"), row.get("hp")) for row in mapping
        if isinstance(row, dict)] != [(row["position"], row["residue"], row["hp"])
                                     for row in contract["hp_mapping"]]:
        problems.append("HP mapping differs from sourced sequence")
    if expected_accession not in title or expected_sequence not in title: problems.append("title disagrees")
    reply["sequence_request"] = contract
    if problems:
        reply["ok"] = False
        reply["refused"] = "sequence_accession_mismatch"
        reply["sequence_check"] = {"outcome": "SEQUENCE_ACCESSION_MISMATCH",
                                   "requested_accession": expected_accession,
                                   "expected_sequence": expected_sequence,
                                   "actual_accession": actual_accession,
                                   "actual_sequence": actual_sequence,
                                   "problems": problems}
        reply["error"] = "sequence/accession mismatch: " + "; ".join(problems)
    else:
        reply["sequence_check"] = {"outcome": "SEQUENCE_ACCESSION_MATCH",
                                   "requested_accession": expected_accession,
                                   "modeled_sequence": actual_sequence,
                                   "modeled_sequence_length": len(actual_sequence)}
    return reply


def run(experiment, parameters=None, shots=4096, resolver=None, transport=None, esmfold_worker=None):
    parameters = dict(parameters or {})
    contract = None
    if str(experiment) == "protein" and _accession(parameters):
        prepared = prepare_protein(parameters, resolver=resolver)
        if not prepared.get("ok"): return prepared
        parameters, contract = prepared["parameters"], prepared["sequence_request"]
        if parameters.get("protein_backend") == "esmfold":
            return _run_esmfold(parameters, contract, worker=esmfold_worker)
    reply = (transport or request)({"action": "run", "experiment": experiment,
                                    "parameters": parameters, "shots": int(shots)})
    return _protein_result(reply, contract)
def reading(run_id, text):
    return request({"action": "reading", "run_id": str(run_id), "text": str(text)[:3000]}, timeout=30)


def configure(host, identity_file="", command=DEFAULT_COMMAND):
    if not HOST_RE.fullmatch(host): raise ValueError("host must look like user@tailscale-host")
    if not COMMAND_RE.fullmatch(command): raise ValueError("command must be one absolute path")
    value = {"host": host, "command": command}
    if identity_file: value["identity_file"] = identity_file
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    temporary = CONFIG + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, CONFIG); os.chmod(CONFIG, 0o600)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    setup = sub.add_parser("configure")
    setup.add_argument("--host", required=True); setup.add_argument("--identity-file", default="")
    setup.add_argument("--command", default=DEFAULT_COMMAND)
    args = parser.parse_args()
    if args.action == "configure":
        print(json.dumps({"ok": True, "config": configure(args.host, args.identity_file, args.command)}, indent=2))
    else: print(json.dumps(status(), indent=2))


if __name__ == "__main__": main()
