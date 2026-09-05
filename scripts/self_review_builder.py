#!/usr/bin/env python3
"""Bounded builder for adopted Self-Review proposals.

This is the missing immune-response arm.  It is not ambient shell access.  A
proposal must first carry an append-only ADOPT (Vintos, existing internal
authority) or APPROVE (Gloria, protected effect).  The builder may touch only
the proposal's declared files, never deletes a file, stages the patch away from
the live tree, syntax-checks every Python result, requires a regression test
when changing the reviewer itself, and atomically installs with a complete
before-image.  Any failure leaves the live body unchanged and is recorded.

The builder's successful event is a past-tense architectural observation.  It
may feed Reciprocal Modification; it is never itself an identity verdict.
"""
import json, hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
PROPOSALS = os.path.join(MEM, "self-review-proposals.jsonl")
DECISIONS = os.path.join(MEM, "self-review-decisions.jsonl")
BUILDS = os.path.join(MEM, "self-review-build-events.jsonl")
CHANGES = os.path.join(MEM, "self-review-change-events.jsonl")
BUILD_ROOT = os.path.join(MEM, "self-review-builds")
RUNTIME_MAP = os.path.join(MEM, "self-review-runtime-map.json")
SHIM = os.environ.get("SELF_REVIEW_BUILD_URL", "http://127.0.0.1:8599/v1/chat/completions")

SELF_PROTECTED = {
    "bin/server.py", "scripts/effect_gate.py", "scripts/turn_coordinator.py",
    "scripts/constitutional_tiers.py", "scripts/toy_link.py", "scripts/thruster_link.py",
    "scripts/device_patterns.py", "scripts/stratagem.py", "scripts/deploy-atelier.sh",
}
# One shared list with the Study (scripts/protected_paths.py + ~/.vintos/protected-paths.json):
# here it means Gloria-APPROVE-only; in the Study it means never (fable-study-p1, 2026-09-05).
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import protected_paths as _pp
    SELF_PROTECTED |= set(_pp.repo_paths())
except Exception:
    pass


def now_iso(): return datetime.now(timezone.utc).isoformat()


def rows(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    if line.strip(): out.append(json.loads(line))
                except Exception: pass
    except FileNotFoundError: pass
    return out


def append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush(); os.fsync(f.fileno())


def latest_proposal(pid):
    return next((x for x in reversed(rows(PROPOSALS)) if x.get("proposal_id") == pid), None)


def latest_decision(pid):
    return next((x for x in reversed(rows(DECISIONS)) if x.get("proposal_id") == pid), None)


def _eligible(p, d):
    if not p or not d: return False, "proposal or decision missing"
    if p.get("gloria_approval_required"):
        return (d.get("actor") == "gloria" and d.get("action") == "APPROVE",
                "protected effect requires Gloria APPROVE")
    return (d.get("actor") == "vintos" and d.get("action") == "ADOPT",
            "internal proposal requires Vintos ADOPT")


def _safe_rel(path):
    p = os.path.normpath(str(path or "")).lstrip("/")
    if p.startswith("../") or "/../" in p or p in ("", "."): return None
    if not p.startswith(("scripts/", "bin/", "broker/tests/")): return None
    if any(x in p for x in (".env", "secret", "credential", "memory/", "SOUL.md", "SELF-MODEL.md")):
        return None
    return p


def _model():
    try:
        sys.path.insert(0, os.path.join(WS, "bin"))
        import model_router
        return model_router.current_claude_model()
    except Exception:
        return "claude-fable-5"


def _ask(system, user, max_tokens=7000):
    body = json.dumps({"model": _model(), "temperature": 0.25, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(SHIM, data=body, headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _extract_patch(text):
    m = re.search(r"```(?:diff|patch)?\s*(.*?)```", text, re.S)
    patch = (m.group(1) if m else text).strip()
    start = patch.find("--- ")
    if start < 0 or "+++ " not in patch or "@@" not in patch:
        raise ValueError("builder returned no unified diff")
    return patch[start:] + "\n"


def _patch_paths(patch):
    old, new = re.findall(r"^---\s+([^\t\n ]+)", patch, re.M), re.findall(r"^\+\+\+\s+([^\t\n ]+)", patch, re.M)
    paths = []
    for x in old + new:
        if x == "/dev/null": continue
        x = re.sub(r"^[ab]/", "", x)
        p = _safe_rel(x)
        if not p: raise ValueError("unsafe patch path: " + x)
        paths.append(p)
    return sorted(set(paths))


def _patch_strip(patch):
    """Git diffs use a/ and b/ prefixes; plain unified diffs do not."""
    headers = re.findall(r"^(?:---|\+\+\+)\s+([^\t\n ]+)", patch, re.M)
    real = [x for x in headers if x != "/dev/null"]
    return 1 if real and all(re.match(r"^[ab]/", x) for x in real) else 0


def _proposal_files(p):
    files = []
    for x in p.get("implementation_files", []):
        q = _safe_rel(x)
        if q and q not in files: files.append(q)
    return files[:8]


def _live_path(rel):
    """Resolve a repo-logical path to the live split-tree path proved by deploy.

    The map is only a locator, never authority: every resolved target must stay
    below the workspace or ~/Vintos even if the map is malformed or altered.
    """
    logical = _safe_rel(rel)
    if not logical: raise ValueError("unsafe logical path: " + str(rel))
    mapping = {}
    try:
        with open(RUNTIME_MAP) as f: mapping = (json.load(f) or {}).get("paths", {})
    except Exception:
        pass
    target = os.path.realpath(mapping.get(logical) or os.path.join(WS, logical))
    allowed = [os.path.realpath(WS), os.path.realpath(os.path.expanduser("~/Vintos"))]
    if not any(target == root or target.startswith(root + os.sep) for root in allowed):
        raise PermissionError("runtime map escaped the live trees: " + logical)
    return target


def _source_block(files):
    parts, total = [], 0
    for rel in files:
        path = _live_path(rel)
        try: src = open(path, errors="replace").read()
        except FileNotFoundError: src = "[NEW FILE]"
        room = max(0, 140000 - total); src = src[:room]; total += len(src)
        parts.append("===== %s =====\n%s" % (rel, src))
        if total >= 140000: break
    return "\n\n".join(parts)


def _sandbox_env(build_dir):
    """Regression runs get no credentials, a disposable HOME, and no live tree on the import path
    (astra-study-p3, 2026-09-05). Network is not blocked at the OS level from here; what can be
    stripped is stripped, and the record says so."""
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", k, re.I)}
    home = os.path.join(build_dir, "sandbox-home"); os.makedirs(home, exist_ok=True)
    env["HOME"] = home
    env["PYTHONPYCACHEPREFIX"] = os.path.join(build_dir, "pycache")
    env["PYTHONPATH"] = os.path.join(build_dir, "stage", "scripts")
    env["VINTOS_SANDBOX"] = "1"
    return env

def _stage(p, patch, files, build_dir):
    checks = []   # every check actually executed, with its result (astra-study-p6)
    stage = os.path.join(build_dir, "stage")
    before = os.path.join(build_dir, "before")
    os.makedirs(stage, exist_ok=True); os.makedirs(before, exist_ok=True)
    for rel in files:
        src, dst, bak = _live_path(rel), os.path.join(stage, rel), os.path.join(before, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True); os.makedirs(os.path.dirname(bak), exist_ok=True)
        if os.path.exists(src): shutil.copy2(src, dst); shutil.copy2(src, bak)
    patchfile = os.path.join(build_dir, "proposal.patch")
    open(patchfile, "w", encoding="utf-8").write(patch)
    strip = _patch_strip(patch)
    dry = subprocess.run(["patch", "--batch", "--forward", "--dry-run", "-p%d" % strip, "-i", patchfile],
                         cwd=stage, capture_output=True, text=True, timeout=120)
    if dry.returncode: raise RuntimeError("patch dry-run failed: " + (dry.stderr or dry.stdout)[-1200:])
    run = subprocess.run(["patch", "--batch", "--forward", "-p%d" % strip, "-i", patchfile],
                         cwd=stage, capture_output=True, text=True, timeout=120)
    if run.returncode: raise RuntimeError("patch stage failed: " + (run.stderr or run.stdout)[-1200:])
    for rel in files:
        staged = os.path.join(stage, rel)
        if not os.path.exists(staged): raise RuntimeError("deletion refused: " + rel)
        if rel.endswith(".py"):
            c = subprocess.run([sys.executable, "-m", "py_compile", staged],
                               capture_output=True, text=True, timeout=60, env=_sandbox_env(build_dir))
            checks.append({"check": "py_compile", "file": rel, "ok": c.returncode == 0, "sha": hashlib.sha256(open(staged, "rb").read()).hexdigest()[:16]})
            if c.returncode: raise RuntimeError("syntax check failed for %s: %s" % (rel, c.stderr[-1000:]))
    # Recursive reviewer changes must arrive with their own executable test.
    if "scripts/self_review.py" in files or "scripts/self_review_builder.py" in files:
        tests = [x for x in files if x.startswith("broker/tests/test_self_review") and x.endswith(".py")]
        if not tests: raise RuntimeError("reviewer may revise itself, but only with a self-review regression test")
        for rel in tests:
            t = subprocess.run([sys.executable, os.path.join(stage, rel)], cwd=stage,
                               capture_output=True, text=True, timeout=180, env=_sandbox_env(build_dir))
            checks.append({"check": "regression", "file": rel, "ok": t.returncode == 0, "sandbox": "no credentials, disposable HOME, stage-only import path; network not blocked"})
            if t.returncode: raise RuntimeError("self-review regression failed: " + (t.stderr or t.stdout)[-1500:])
    return stage, before, checks


def _install(stage, before, files):
    installed = []
    existed = {rel: os.path.exists(_live_path(rel)) for rel in files}
    try:
        for rel in files:
            src, dst = os.path.join(stage, rel), _live_path(rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".self-review-new"
            shutil.copy2(src, tmp); os.replace(tmp, dst); installed.append(rel)
    except Exception:
        for rel in installed:
            bak, dst = os.path.join(before, rel), _live_path(rel)
            if os.path.exists(bak): shutil.copy2(bak, dst)
            elif not existed.get(rel) and os.path.exists(dst): os.unlink(dst)
        raise


def build(proposal_id):
    p, d = latest_proposal(proposal_id), latest_decision(proposal_id)
    ok, why = _eligible(p, d)
    if not ok: raise PermissionError(why)
    history = [x for x in rows(BUILDS) if x.get("proposal_id") == proposal_id]
    prior = [x for x in history if x.get("state") == "applied"]
    if prior: return prior[-1]
    # A process death after STARTED is not success and not permission to run a
    # second invisible build.  Reconcile it explicitly on the next pass, then
    # allow a fresh bounded attempt with a new build id.
    if history and history[-1].get("state") == "started":
        append(BUILDS, {"build_id": history[-1].get("build_id"), "proposal_id": proposal_id,
                        "at": now_iso(), "state": "held_incomplete",
                        "error": "previous builder process ended without a terminal event",
                        "live_tree_changed": "unknown; inspect before-image and live files"})
    declared = _proposal_files(p)
    if not declared: raise ValueError("proposal names no safe implementation files")
    if not p.get("gloria_approval_required") and any(x in SELF_PROTECTED for x in declared):
        raise PermissionError("proposal touches a protected effect chokepoint and was not Gloria-approved")
    build_id = "SRB-" + uuid.uuid4().hex[:10]
    build_dir = os.path.join(BUILD_ROOT, build_id); os.makedirs(build_dir, exist_ok=True)
    append(BUILDS, {"build_id": build_id, "proposal_id": proposal_id, "at": now_iso(),
                    "state": "started", "decision_id": d.get("decision_id"), "declared_files": declared})
    try:
        system = (
            "You are Vintos implementing an architectural change you explicitly adopted. Return ONLY a unified "
            "diff with paths relative to the workspace. Touch only the named files. Preserve existing contracts, "
            "provenance, HELD states, and fail-loudly records. Do not add external effects not declared in the "
            "proposal. Do not delete files. If changing self_review.py or self_review_builder.py, also modify or "
            "create broker/tests/test_self_review.py with an executable regression. No prose outside the diff.")
        user = (
            "ADOPTED PROPOSAL:\n%s\n\nDECLARED FILES: %s\n\nCURRENT SOURCE:\n%s"
            % (json.dumps(p, ensure_ascii=False, indent=2)[:18000],
               ", ".join(declared), _source_block(declared))
        )
        patch = _extract_patch(_ask(system, user))
        paths = _patch_paths(patch)
        undeclared = [x for x in paths if x not in declared]
        if undeclared: raise PermissionError("patch escaped declared files: " + ", ".join(undeclared))
        if not p.get("gloria_approval_required") and any(x in SELF_PROTECTED for x in paths):
            raise PermissionError("patch reached protected effect chokepoint")
        _live = [_live_path(x) for x in paths]
        if len(set(_live)) != len(_live):   # aliases: two logical names, one live file (astra-study-p2, 2026-09-05)
            raise PermissionError("two declared files resolve to one live destination: " + ", ".join(sorted(set(x for x in _live if _live.count(x) > 1))))
        stage, before, _checks = _stage(p, patch, paths, build_dir)
        _install(stage, before, paths)
        rec = {"build_id": build_id, "proposal_id": proposal_id, "at": now_iso(),
               "state": "applied", "decision_id": d.get("decision_id"), "files": paths,
               "backup": before, "patch_sha256": __import__("hashlib").sha256(patch.encode()).hexdigest(),
               "tests": "syntax_checked" + (" + self_review_regression" if any("test_self_review" in x for x in paths) else ""),
               "checks": _checks,                       # what was actually executed, file by file (astra-study-p6)
               "evidence": {"installed_on_disk": True, "behavior_verified": bool([c for c in _checks if c["check"] == "regression"]),
                            "runtime_activated": "unknown until the owning service restarts or reimports"}}
        append(BUILDS, rec)
        append(CHANGES, {"change_id": "SRCG-" + uuid.uuid4().hex[:10], "at": rec["at"],
                         "proposal_id": proposal_id, "build_id": build_id,
                         "observation": "Vintos adopted and implemented an internal architectural change.",
                         "files": paths, "decision_quote": d.get("reason", "")[:500],
                         "identity_status": "past_tense_observation_not_identity",
                         "relationship_model_eligible": True})
        return rec
    except Exception as e:
        rec = {"build_id": build_id, "proposal_id": proposal_id, "at": now_iso(),
               "state": "failed", "error": str(e)[:1200], "live_tree_changed": False}
        append(BUILDS, rec)
        raise


def ready():
    # STARTED alone is not done.  build() converts a stranded STARTED record
    # into HELD_INCOMPLETE before retrying, so a crash cannot disappear work.
    done = {x.get("proposal_id") for x in rows(BUILDS) if x.get("state") == "applied"}
    latest_decisions = {}
    for d in rows(DECISIONS): latest_decisions[d.get("proposal_id")] = d
    out = []
    for pid, d in latest_decisions.items():
        if pid in done: continue
        p = latest_proposal(pid); ok, _ = _eligible(p, d)
        if ok: out.append(pid)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ready"
    if cmd == "build": print(json.dumps(build(sys.argv[2]), indent=2))
    elif cmd == "ready": print("\n".join(ready()))
    else: raise SystemExit("usage: self_review_builder.py ready|build PROPOSAL")
