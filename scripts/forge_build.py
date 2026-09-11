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
        "The module defines a function named %r. It may do only what the granted scope and "
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
    if first.upper().startswith("PASS"):
        return True, "Fable passed the review"
    return False, ("Fable: " + first)[:300] if first else "Fable returned nothing"


def sandbox_test(module_src, test_src, name):
    """Run the test in a subprocess with a scratch HOME and no network. (ok, output)."""
    d = tempfile.mkdtemp(prefix="forge-sbx-")
    modp = os.path.join(d, "%s.py" % name)
    testp = os.path.join(d, "test_%s.py" % name)
    open(modp, "w").write(module_src)
    open(testp, "w").write(test_src or "print('0/0'); raise SystemExit(1)")
    env = {"HOME": d, "PATH": os.environ.get("PATH", ""), "PYTHONPATH": d,
           "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9"}
    try:
        r = subprocess.run([sys.executable, testp], cwd=d, env=env,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    except Exception as e:
        return False, "sandbox could not run: %s" % str(e)[:200]


def run(proposal_id, astra=None, fable=None):
    """The pipeline for one approved proposal. Returns the forge row and a note.

    Only advances toward verified; never installs. A refusal (Fable or the sandbox)
    sends the proposal back through skill_forge.mark(..., 'refused')."""
    sf = _forge()
    p = sf._get(sf._load(), proposal_id)
    if p is None:
        return None, "no proposal %r" % proposal_id
    if p.get("state") != "approved":
        return None, "proposal is %s, not approved: only an approved proposal is built" % p.get("state")
    try:
        code = generate(p, astra=astra)
    except Exception as e:
        sf.mark(proposal_id, "refused", "Astra could not write it: %s" % str(e)[:200])
        return None, "generation failed: %s" % str(e)[:200]
    ok, why = review(p, code, fable=fable)
    if not ok:
        sf.mark(proposal_id, "refused", why)
        return None, "review refused: %s" % why
    os.makedirs(STAGING, exist_ok=True)
    stem = os.path.join(STAGING, "%s-%s" % (proposal_id, code["name"]))
    open(stem + ".py", "w").write(code["module"])
    open(stem + ".test.py", "w").write(code.get("test", ""))
    sf.mark(proposal_id, "built", "Astra wrote it, Fable passed; staged at %s.py" % stem)
    passed, output = sandbox_test(code["module"], code.get("test", ""), code["name"])
    if not passed:
        sf.mark(proposal_id, "refused", "the sandbox test failed: %s" % output[-160:])
        return None, "sandbox failed: %s" % output[-160:]
    row, mwhy = sf.mark(proposal_id, "verified", "sandbox passed", extra={"staged": stem + ".py"})
    return row, "verified; awaiting her install"


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
    if not staged or not os.path.isfile(staged):
        return None, "the verified module is not on disk at %r" % staged
    dest = os.path.join(SKILL_DEST, os.path.basename(staged).split("-", 2)[-1])
    try:
        shutil.copy2(staged, dest)
    except Exception as e:
        return None, "install copy failed: %s" % str(e)[:160]
    row, _ = sf.mark(proposal_id, "installed", "installed to %s" % dest, extra={"installed_to": dest})
    return row, "installed to %s; the want it came from is now resumable" % dest


if __name__ == "__main__":
    sf = _forge()
    for r in sf._load():
        if r.get("state") in ("approved", "built", "verified"):
            print("%-11s %-10s %s" % (r["id"], r["state"], r["capability"]))
    print("run(<id>) builds an approved one; install(<id>) installs a verified one.")
