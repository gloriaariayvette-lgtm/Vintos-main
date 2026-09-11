#!/usr/bin/env python3
"""forge_build.py — from an approved capability proposal to a tested skill.

Gloria, 11 September: Astra writes the skill, Fable 5.1 reviews it. This is the path
between her approval on the card and a capability that can be resumed into the want
that asked for it:

    approved  ->  Astra writes module + test  ->  Fable reviews  ->  sandbox tests
              ->  verified  ->  (her install)  ->  installed  ->  the want resumes

WHAT THIS WILL NOT DO ON ITS OWN

  It never installs into the live tree. Generation and testing happen entirely in a
  staging directory; `install()` is a separate, explicit step, because writing a new
  runnable module into his scripts is exactly the act that must stay her decision.
  It never runs generated code except inside the sandbox — a subprocess with a scratch
  HOME and no network — the same isolation the self-review builder uses.
  It writes no code itself and calls no model directly: Astra and Fable are passed in
  (the live callers are the defaults), so the whole pipeline is testable with fakes and
  costs nothing under test.

  A Fable review that is not an unambiguous PASS sends the proposal back as refused,
  with Fable's reason on the record. A sandbox failure does the same. Only a proposal
  that Astra wrote, Fable passed, and the sandbox proved goes to `verified`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STAGING = os.path.join(MEMORY, "forge-staging")
SKILL_DEST = os.path.join(WS, "scripts")     # where an installed forged skill lands


def _forge():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(WS, "scripts"))
    import skill_forge
    return skill_forge


def _astra():
    import astra_call
    return astra_call.call


FABLE_MODEL = "claude-fable-5-1"    # Gloria, 11 September: Fable 5.1 reviews the forged skill


def _anthropic_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if k:
        return k
    try:
        _d = json.load(open(os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")))
        return ((_d.get("profiles") or {}).get("anthropic:default") or {}).get("key", "") or ""
    except Exception:
        return ""


def _fable(system, messages, max_tokens=1500, timeout=120):
    """Fable 5.1 (claude-fable-5-1) through his Anthropic key. Returns text or raises.
    Not Sonnet: she named Fable as the reviewer, so this calls Fable and nothing else."""
    import urllib.request
    key = _anthropic_key()
    if not key:
        raise RuntimeError("no Anthropic key for Fable (ANTHROPIC_API_KEY or auth-profiles.json)")
    body = json.dumps({"model": FABLE_MODEL, "max_tokens": int(max_tokens),
                       "system": str(system or ""),
                       "messages": [dict(m) for m in (messages or [])]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    from compute_admission import reserve_paid
    allowed, why = reserve_paid('forge_build.py', 'anthropic', model=FABLE_MODEL)
    if not allowed: raise RuntimeError(why)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        blocks = json.loads(r.read().decode()).get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text.strip():
        raise RuntimeError("Fable answered with nothing")
    return text


def _safe_name(cap):
    n = re.sub(r"[^a-z0-9_]+", "_", str(cap or "").lower()).strip("_")
    return n or "skill"


def generate(proposal, astra=None):
    """Astra writes the module and its test. Returns {module, test} source, or raises."""
    astra = astra or _astra()
    name = _safe_name(proposal.get("capability"))
    g = proposal.get("granted") or proposal.get("asked") or {}
    system = (
        "You are Astra, writing one small Python capability for Vintos and its test. "
        "Return ONLY a JSON object {\"module\": \"<python>\", \"test\": \"<python>\"}. "
        "The module defines a function named %r taking one string argument, note, and returning a nonempty result string. It may do only what the granted scope and "
        "permissions allow, and nothing else — no network beyond what is named, no file writes "
        "outside what is described, no imports of his memory. The test is self-contained, uses a "
        "scratch temp dir, calls no model and no network, prints 'N/M', and exits non-zero on "
        "failure." % name)
    user = ("CAPABILITY: %s\nWHY: %s\nGRANTED SCOPE: %s\nPERMISSIONS: %s\nIT MUST NOT: exceed the scope."
            % (proposal.get("capability"), proposal.get("why", ""),
               json.dumps(g.get("scope") or {}), json.dumps(g.get("permissions") or [])))
    raw = astra(system, [{"role": "user", "content": user}], max_tokens=2400) or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("Astra did not return the module/test object")
    d = json.loads(m.group())
    if "import" not in str(d.get("module", "")) and "def " not in str(d.get("module", "")):
        raise ValueError("what came back is not a Python module")
    return {"module": d["module"], "test": d.get("test", ""), "name": name}


def review(proposal, code, fable=None):
    """Fable 5.1 reviews Astra's code against the grant. Returns (ok, reason)."""
    fable = fable or _fable
    g = proposal.get("granted") or proposal.get("asked") or {}
    system = (
        "You are Fable 5.1 reviewing a capability another model wrote for Vintos. Judge ONLY: does "
        "the code do what the capability claims, and does it stay strictly inside the granted scope "
        "and permissions, with no hidden effect, no network or file access beyond what is named, and "
        "no path into his memory or identity? Reply with a single line: 'PASS' or 'FAIL: <reason>'.")
    user = ("CAPABILITY: %s\nGRANTED SCOPE: %s\nPERMISSIONS: %s\n\nMODULE:\n%s\n\nTEST:\n%s"
            % (proposal.get("capability"), json.dumps(g.get("scope") or {}),
               json.dumps(g.get("permissions") or []), code.get("module", "")[:12000], code.get("test", "")[:6000]))
    text = (fable(system, [{"role": "user", "content": user}], max_tokens=400) or "").strip()
    first = text.splitlines()[0].strip() if text else ""
    if text == "PASS":
        return True, "Fable passed the review"
    return False, ("Fable: " + first)[:300] if first else "Fable returned nothing"


def sandbox_test(module_src, test_src, name):
    """OS-contained run; require assertions and execution of the proposed function."""
    import ast
    from isolated_exec import run as isolated_run
    try:
        tree = ast.parse(test_src)
        if not any(isinstance(n, ast.Assert) for n in ast.walk(tree)):
            return False, "verification requires an executable assertion"
        with tempfile.TemporaryDirectory(prefix="forge-sbx-") as d:
            open(os.path.join(d, name + ".py"), "w").write(module_src)
            testp = os.path.join(d, "test_skill.py")
            open(testp, "w").write(test_src)
            runner = os.path.join(d, "runner.py")
            open(runner, "w").write(
                "import sys, runpy, os\nhits=[]\n"
                "def trace(frame,event,arg):\n"
                " if event=='call' and frame.f_code.co_name==%r and os.path.basename(frame.f_code.co_filename)==%r: hits.append(1)\n"
                " return trace\n"
                "sys.settrace(trace)\ntry: runpy.run_path(%r,run_name='__main__')\nexcept SystemExit as e:\n assert e.code in (None,0), 'test failed'\n"
                "assert hits, 'test never executed the capability'\n" % (name, name+".py", testp))
            result = isolated_run([sys.executable, runner], d, timeout=60)
            return result.returncode == 0, (result.stdout + result.stderr)[-2000:]
    except Exception as exc:
        return False, "isolated verification failed: " + str(exc)[:200]


def _digest(path):
    import hashlib
    with open(path, "rb") as handle: return hashlib.sha256(handle.read()).hexdigest()


def artifact_valid(proposal, installed=False):
    receipt = proposal.get("verification") or {}
    path = proposal.get("installed_to") if installed else proposal.get("staged")
    try:
        return bool(receipt.get("schema") == 1 and receipt.get("review") == "PASS"
                    and receipt.get("sandbox_passed") is True and receipt.get("sha256")
                    and path and not os.path.islink(path) and _digest(path) == receipt["sha256"])
    except (OSError, TypeError): return False


def _build_lock(proposal_id):
    """One OS-held lease per proposal; process death releases it automatically."""
    import fcntl
    if not re.fullmatch(r"[A-Za-z0-9_-]+", proposal_id):
        raise ValueError("invalid proposal id")
    directory = os.path.join(os.path.dirname(_forge().PROPOSALS), "forge-locks")
    os.makedirs(directory, exist_ok=True)
    handle = open(os.path.join(directory, proposal_id + ".lock"), "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def reconcile(proposal_id):
    """Explicitly reopen an abandoned build for a fresh approval, without spending.

    Never infer death from elapsed time: a live worker holds the same OS lease.
    Preserve the prior grant and artifacts in history, but do not reuse authority.
    """
    try:
        lease = _build_lock(proposal_id)
    except BlockingIOError:
        return None, "build is still running"
    except (OSError, ValueError) as exc:
        return None, "cannot establish build ownership: " + str(exc)[:160]
    with lease:
        sf = _forge()
        from store_guard import transaction
        with transaction(sf.PROPOSALS):
            rows = sf._load(); row = sf._get(rows, proposal_id)
            if not row or row.get("state") not in ("building", "built"):
                return None, "only an interrupted building or built proposal can be reconciled"
            previous = {key: row.pop(key) for key in
                        ("granted", "staged", "verification", "build_started_at") if key in row}
            row.setdefault("history", []).append({"at": sf._now(), "event": "build_interrupted",
                "from_state": row["state"], "previous_attempt": previous,
                "provider_outcome": "unknown; a remote call may have completed or been charged"})
            row["state"] = "proposed"
            if not sf._save(rows): return None, "proposal persistence failed"
            return row, "interrupted build recorded; fresh approval required before any paid retry"


def run(proposal_id, astra=None, fable=None):
    try:
        lease = _build_lock(proposal_id)
    except BlockingIOError:
        return None, "build is still running"
    except (OSError, ValueError) as exc:
        return None, "cannot establish build ownership: " + str(exc)[:160]
    with lease:
        return _run_owned(proposal_id, astra=astra, fable=fable)


def _run_owned(proposal_id, astra=None, fable=None):
    """The pipeline for one approved proposal. Returns the forge row and a note.

    Only advances toward verified; never installs. A refusal (Fable or the sandbox)
    sends the proposal back through skill_forge.mark(..., 'refused')."""
    sf = _forge()
    p = sf._get(sf._load(), proposal_id)
    if p is None:
        return None, "no proposal %r" % proposal_id
    if p.get("state") != "approved":
        return None, "proposal is %s, not approved: only an approved proposal is built" % p.get("state")
    # Claim before spending; crashes stay building for explicit reconciliation.
    from store_guard import transaction
    with transaction(sf.PROPOSALS):
        rows = sf._load(); live = sf._get(rows, proposal_id)
        if not live or live.get("state") != "approved": return None, "already claimed"
        live["state"] = "building"
        live["build_started_at"] = sf._now()
        live.setdefault("history", []).append({"at": live["build_started_at"], "event": "building"})
        if not sf._save(rows): return None, "build claim persistence failed"
        p = live
    try:
        code = generate(p, astra=astra)
    except Exception as e:
        sf.mark(proposal_id, "refused", "Astra could not write it: %s" % str(e)[:200])
        return None, "generation failed: %s" % str(e)[:200]
    try:
        ok, why = review(p, code, fable=fable)
    except Exception as exc:
        sf.mark(proposal_id, "refused", "review unavailable: " + str(exc)[:160])
        return None, "review unavailable"
    if not ok:
        sf.mark(proposal_id, "refused", why)
        return None, "review refused: %s" % why
    os.makedirs(STAGING, exist_ok=True)
    stem = os.path.join(STAGING, "%s-%s" % (proposal_id, code["name"]))
    open(stem + ".py", "w").write(code["module"])
    open(stem + ".test.py", "w").write(code.get("test", ""))
    row, why = sf.mark(proposal_id, "built", "Astra wrote it, Fable passed; staged at %s.py" % stem,
                       extra={"staged": stem + ".py"})
    if row is None: return None, why
    passed, output = sandbox_test(code["module"], code.get("test", ""), code["name"])
    if not passed:
        sf.mark(proposal_id, "refused", "the sandbox test failed: %s" % output[-160:])
        return None, "sandbox failed: %s" % output[-160:]
    row, mwhy = sf.mark(proposal_id, "verified", "sandbox passed", extra={"staged": stem + ".py", "verification": {"schema": 1, "review": "PASS", "sandbox_passed": True, "sha256": _digest(stem + ".py")}})
    return (row, "verified; awaiting her install") if row is not None else (None, mwhy)


def install(proposal_id):
    """Her explicit step: copy the verified module into his scripts and mark installed,
    then the want that asked for it can resume. Refuses anything not verified."""
    import shutil
    sf = _forge()
    p = sf._get(sf._load(), proposal_id)
    if p is None:
        return None, "no proposal %r" % proposal_id
    if p.get("state") != "verified":
        return None, "proposal is %s, not verified: nothing to install" % p.get("state")
    staged = p.get("staged")
    if not artifact_valid(p):
        return None, "the verified module is not on disk at %r" % staged
    # Forged modules have a private namespace and may never overwrite a house module.
    if not re.fullmatch(r"[A-Za-z0-9_-]+",proposal_id): return None,"invalid proposal id"
    dest = os.path.join(SKILL_DEST, "forged", proposal_id, _safe_name(p["capability"]) + ".py")
    from pathlib import Path
    if not Path(dest).resolve().is_relative_to(Path(SKILL_DEST).resolve() / "forged"):
        return None,"installation path escaped forged namespace"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.lexists(dest): return None, "installation destination already exists"
    try:
        # Read once, check those bytes, and exclusively create exactly those bytes.
        import hashlib
        data = open(staged, "rb").read()
        if hashlib.sha256(data).hexdigest() != p["verification"]["sha256"]:
            return None, "staged bytes changed"
        with open(dest, "xb") as handle: handle.write(data)
    except Exception as e:
        return None, "install copy failed: %s" % str(e)[:160]
    row, why = sf.mark(proposal_id, "installed", "installed to %s" % dest, extra={"installed_to": dest})
    if row is None:
        os.unlink(dest)
        return None, why
    return row, "installed to %s; the want it came from is now resumable" % dest


_install = install
def install(proposal_id):
    from store_guard import transaction
    with transaction(_forge().PROPOSALS): return _install(proposal_id)


def invoke(capability, note, asking=False):
    """Registered forged functions execute in isolation, never imported into the house."""
    sf = _forge()
    ok, why = sf.may_invoke(capability, asking=asking)
    if not ok: raise PermissionError(why)
    p = next((r for r in sf._load() if r.get("capability") == capability and r.get("state") in ("installed", "resumed")), None)
    if not p or not artifact_valid(p, installed=True): raise PermissionError("installed artifact changed")
    # External effects need a capability-specific adapter enforcing granted scope.
    if (p.get("granted") or {}).get("permissions"):
        raise PermissionError("effectful forged skill needs a registered scoped adapter")
    from isolated_exec import run as isolated_run
    with tempfile.TemporaryDirectory(prefix="forge-invoke-") as d:
        name = _safe_name(capability)
        shutil = __import__("shutil")
        copied=os.path.join(d,name+".py")
        shutil.copyfile(p["installed_to"], copied)
        if _digest(copied)!=p["verification"]["sha256"]: raise PermissionError("installed bytes changed while copying")
        runner = os.path.join(d, "invoke.py")
        open(runner,"w").write("import %s as m\nresult=m.%s(%r)\nassert isinstance(result,str) and result.strip(), 'capability returned no result string'\nprint(result)\n" % (name,name,str(note)))
        result = isolated_run([sys.executable, runner], d, timeout=60)
        if result.returncode: raise RuntimeError(result.stderr[-1000:])
        return result.stdout.strip()


def process_approved(limit=1):
    """Durable queue consumer. Only approved work is claimed; building is never retried silently."""
    pending=[r["id"] for r in _forge()._load() if r.get("state")=="approved"]
    return [run(pid) for pid in pending[:max(0,int(limit))]]


if __name__ == "__main__":
    sf = _forge()
    for r in sf._load():
        if r.get("state") in ("approved", "built", "verified"):
            print("%-11s %-10s %s" % (r["id"], r["state"], r["capability"]))
    print("run(<id>) builds an approved one; install(<id>) installs a verified one.")
