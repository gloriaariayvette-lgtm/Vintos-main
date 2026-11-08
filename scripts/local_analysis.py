"""Bounded offline artifact work for wants, using the existing OS sandbox.

No provider, install, network, device, live-store or arbitrary-host access in
the child. Inputs are named copies of his artifact files. The trusted parent
checks declared outputs and retains a receipt bound to the want and exact job.
Execution is evidence of running code and producing files, not scientific truth.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
SCHEMA = "local-analysis-v1"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ValueError("use simple input/output filenames")
    return value


def _write(path, value):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        os.chmod(tmp, 0o600)
        f.write(_json(value) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _output(path, spec):
    if path.resolve() != path.absolute() or path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_OUTPUT_BYTES:
        raise ValueError("declared output missing, empty, linked or too large")
    data = path.read_bytes()
    kind = spec.get("kind")
    if kind == "json":
        value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if not isinstance(value, dict) or not all(k in value for k in spec.get("required_keys", [])):
            raise ValueError("JSON output does not meet its declared shape")
    elif kind == "csv":
        import csv, io
        rows = list(csv.reader(io.StringIO(data.decode())))
        if len(rows) < 2 or not all(k in rows[0] for k in spec.get("required_columns", [])):
            raise ValueError("CSV output needs its declared header and data")
    elif kind == "wav":
        import wave
        with wave.open(str(path), "rb") as f:
            if f.getnframes() < 1 or f.getframerate() < 1:
                raise ValueError("empty audio output")
    elif kind == "text":
        if not data.decode().strip():
            raise ValueError("empty text output")
    else:
        raise ValueError("unsupported declared output kind")
    return {"name": path.name, "bytes": len(data), "sha256": _sha(data), "kind": kind}


def run(params, want_id, *, workspace=None, runner=None):
    """Run one exact code/input/output contract; reuse verified success, never prose."""
    ws = Path(workspace or os.environ.get("SPARK_WORKSPACE", Path.home() / ".vintos/workspace")).resolve()
    result = {"schema": SCHEMA, "want_id": str(want_id), "status": "BLOCKED", "artifacts": [],
              "findings": "", "reason": "", "scientific_validation": "not_asserted"}
    try:
        if not want_id or not isinstance(params, dict):
            raise ValueError("a bound want and structured job are required")
        code, inputs, outputs = params.get("code"), params.get("inputs", {}), params.get("outputs")
        if not isinstance(code, str) or not code.strip() or len(code) > 12000:
            raise ValueError("code must be nonempty Python, at most 12000 characters")
        compile(code, "want-analysis", "exec")
        if not isinstance(inputs, dict) or len(inputs) > 8 or not isinstance(outputs, dict) or not 1 <= len(outputs) <= 8:
            raise ValueError("use at most eight named inputs and one to eight declared outputs")
        for name, spec in outputs.items():
            _name(name)
            if not isinstance(spec, dict) or spec.get("kind") not in ("json", "csv", "wav", "text"):
                raise ValueError("output needs a supported kind")
            for field in ("required_keys", "required_columns"):
                if field in spec and (not isinstance(spec[field], list) or len(spec[field]) > 32
                                     or any(not isinstance(v, str) or len(v) > 100 for v in spec[field])):
                    raise ValueError("invalid output shape")
        snapshots, bindings, size = {}, {}, 0
        allowed = (ws / "memory/art", ws / "memory/want-artifacts")
        for name, relative in inputs.items():
            _name(name)
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("inputs must name relative artifact paths")
            raw = ws / relative
            source = raw.resolve(strict=True)
            if raw != source or not any(root in source.parents for root in allowed) or not source.is_file():
                raise ValueError("input is not an ordinary file in an artifact shelf")
            if source.stat().st_size > MAX_INPUT_BYTES - size:
                raise ValueError("input budget exceeded")
            data = source.read_bytes(); size += len(data)
            if size > MAX_INPUT_BYTES: raise ValueError("input budget exceeded")
            snapshots[name] = data
            bindings[name] = {"path": relative, "sha256": _sha(data), "bytes": len(data)}
        fingerprint = _sha(_json({"want": str(want_id), "code": code, "inputs": bindings, "outputs": outputs}).encode())
        root = ws / "memory/want-artifacts"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.resolve() != root:
            raise ValueError("artifact output root must not be a symlink")
        job = root / fingerprint
        job.mkdir(mode=0o700, exist_ok=True)
        if job.resolve() != job: raise ValueError("job path must not be a symlink")
        receipt = job / "receipt.json"
        result.update(job_id=fingerprint, receipt=str(receipt), input_bindings=bindings,
                      code_sha256=_sha(code.encode()))
        with (job / "lock").open("a") as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return dict(result, status="RUNNING", reason="same exact job is already running")
            if receipt.exists():
                if receipt.is_symlink(): raise ValueError("linked receipt refused")
                old = json.loads(receipt.read_text())
                if old.get("schema") != SCHEMA or old.get("job_id") != fingerprint or old.get("want_id") != str(want_id):
                    raise ValueError("receipt does not belong to this exact job")
                if old.get("status") == "SUCCEEDED":
                    actual = [_output(job / "artifacts" / n, s) for n, s in sorted(outputs.items())]
                    if actual == old.get("artifacts"):
                        return dict(old, reused=True)
                    raise ValueError("retained artifact changed; completion is no longer proved")
                # Do not silently rerun an interrupted or failed exact program.
                # A revised program/input/output contract creates a new job.
                return dict(old, status="BLOCKED", reused=True,
                            reason=old.get("reason") or "interrupted job; revise or inspect before another attempt")
            result.update(status="RUNNING", started_at=time.time())
            _write(receipt, result)
            try:
                with tempfile.TemporaryDirectory(prefix="attempt-", dir=job) as td:
                    scratch = Path(td)
                    (scratch / "inputs").mkdir(); (scratch / "outputs").mkdir()
                    for name, data in snapshots.items(): (scratch / "inputs" / name).write_bytes(data)
                    program = scratch / "task.py"
                    # Names are serialized data, not interpolated Python fragments.
                    header = ("from pathlib import Path\ninputs = " + repr({n: str(scratch / "inputs" / n) for n in sorted(inputs)})
                              + "\noutput_dir = Path(" + repr(str(scratch / "outputs")) + ")\n")
                    program.write_text(header + code)
                    if runner is None:
                        from isolated_exec import run as runner
                    done = runner([sys.executable, str(program)], str(scratch), timeout=45)
                    (job / "stdout.txt").write_text(str(done.stdout or "")[:16000])
                    (job / "stderr.txt").write_text(str(done.stderr or "")[:16000])
                    if done.returncode != 0:
                        raise RuntimeError("isolated program failed; inspect the private stderr receipt")
                    artifacts = [_output(scratch / "outputs" / name, spec) for name, spec in sorted(outputs.items())]
                    if sum(a["bytes"] for a in artifacts) > MAX_OUTPUT_BYTES:
                        raise ValueError("total output budget exceeded")
                    dest = job / "artifacts"; dest.mkdir()
                    for a in artifacts: shutil.copyfile(scratch / "outputs" / a["name"], dest / a["name"])
                    result.update(status="SUCCEEDED", artifacts=artifacts, reason="",
                        findings="Local analysis ran; checked artifacts: " + ", ".join(str(dest / a["name"]) for a in artifacts)
                                 + ". Receipt: " + str(receipt) + ". Scientific correctness is not asserted.")
            except Exception as exc:
                result.update(status="FAILED", reason=str(exc)[:300], error_type=type(exc).__name__)
            result["ended_at"] = time.time(); _write(receipt, result)
        return result
    except Exception as exc:
        return dict(result, status="BLOCKED", reason=str(exc)[:300], error_type=type(exc).__name__)


def retain_result(want, result, path):
    """Record the job under this exact selected step; never fulfill or replace a plan."""
    from store_guard import locked_update
    from want_spine import step_params_signature
    signature = step_params_signature(want)
    if not signature or not isinstance(result, dict) or result.get("schema") != SCHEMA or result.get("want_id") != want.get("id"):
        return False
    recorded = []
    def update(rows):
        for row in rows:
            if row.get("id") == want.get("id") and not row.get("fulfilled") and step_params_signature(row) == signature:
                step = row["steps"][row.get("current_step_index", 0)]
                step["execution_receipt"] = result
                row["last_execution"] = {"status": result["status"], "reason": result.get("reason"),
                                         "job_id": result.get("job_id"), "step_signature": signature}
                recorded.append(True)
                return rows
        return None
    locked_update(path, update, default=[], reader="local_analysis.retain_result")
    return bool(recorded)


def artifact_menu(workspace=None, limit=12):
    """Bounded local inventory for the existing planner; no remote fetch or guessing."""
    ws = Path(workspace or os.environ.get("SPARK_WORKSPACE", Path.home() / ".vintos/workspace")).resolve()
    found = []
    for base in (ws / "memory/art", ws / "memory/want-artifacts"):
        if not base.is_dir() or base.resolve() != base: continue
        visited = 0
        for folder, dirs, files in os.walk(base, followlinks=False):
            visited += 1
            dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()
                       and len(Path(folder).relative_to(base).parts) < 3]
            if visited > 80: break
            for name in sorted(files)[:200]:
                p = Path(folder) / name
                if p.suffix.lower() not in (".wav", ".mp3", ".flac", ".csv", ".mid", ".json", ".txt"):
                    continue
                if base.name == "want-artifacts" and p.parent.name != "artifacts": continue
                if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= MAX_INPUT_BYTES: continue
                found.append((p.stat().st_mtime, str(p.relative_to(ws)), p.stat().st_size))
    return "\n".join("- %s (%d bytes)" % (path, size) for _, path, size in sorted(found, reverse=True)[:limit]) or "No local artifact inputs found. Do not invent a path."
