#!/usr/bin/env python3
"""A Lab discovery on its way to becoming an instrument — staged, and stopped at every gate.

The Lab can invent a game. The Forge can make it durable. Neither may silently install the
other's ideas, and this is the road between them:

    idea -> bounded_interface -> canary_passed -> offered_to_forge

Each move has exactly one predecessor, the way ``skill_forge.mark()`` does, because a
staged approval that can be entered halfway is not staged. And each stage is a real gate:

- **idea** must cite a Lab occasion from the eligible spark feed. A question he asked of
  nothing is still his; it is not evidence that an instrument is missing.
- **bounded_interface** must name one function and a *typed, bounded* parameter schema.
  An interface that accepts free text is not an interface, it is a way in. Nothing here
  ever accepts source code as a parameter.
- **canary_passed** requires the canary to have actually run under
  ``isolated_exec.run`` — the repository's real OS boundary — and its test to contain a
  real assertion and actually call the proposed function. A test that asserts nothing
  passes everything.
- **offered_to_forge** hands it to ``skill_forge.propose()`` against a **live want she
  already has**, whose source is the ``lab`` spark.

What this module may never do, and the suite proves each one:

- **create the want.** Wanting is his, through the ordinary door. A proposal pipeline that
  can manufacture its own admission is not a gate, and the whole point of the spark law is
  that a capability is asked for out of something he was already trying to do.
- **approve or install anything.** Those are hers and the Forge's. This module does not
  import them and does not call them.
- **run generated code outside the boundary**, or count a canary that did not run.

    idea(text, spark_key)                  -> the row
    interface(pid, function, parameters, returns)
    canary(pid, source, test)              -> runs it under the OS boundary
    offer(pid, want_id, why)               -> skill_forge.propose(), or a refusal
    python3 chemistry_proposal.py [show]
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab
import chemistry_spark as spark

PROPOSALS = os.path.join(lab.ROOT, "instrument-proposals.jsonl")

IDEA = "idea"
INTERFACE = "bounded_interface"
CANARY_PASSED = "canary_passed"
OFFERED = "offered_to_forge"
WITHDRAWN = "withdrawn"
REFUSED = "refused"
TERMINAL = (OFFERED, WITHDRAWN, REFUSED)
# One predecessor each. There is no way into the middle of this.
PREDECESSOR = {INTERFACE: IDEA, CANARY_PASSED: INTERFACE, OFFERED: CANARY_PASSED}

# A parameter may be one of these and nothing else. "code", "source", "script" and "expr"
# are absent deliberately: an instrument that takes code is the arbitrary-execution route
# wearing an interface.
PARAMETER_TYPES = ("number", "integer", "boolean", "enum", "accession", "shortstring")
MAX_PARAMETERS = 8
MAX_ENUM = 12
CANARY_TIMEOUT = 60


def _rows(): return lab._jsonl(PROPOSALS)


def _latest(pid):
    found = None
    for row in _rows():
        if row.get("proposal_id") == pid: found = row
    return found


def _write(row):
    lab._append(PROPOSALS, row)
    return row


def _advance(pid, state, **extra):
    """Append the next stage, or a refusal saying why it could not be entered."""
    current = _latest(pid)
    if current is None: return {"refused": "no proposal %s" % pid}
    if current["state"] in TERMINAL:
        return {"refused": "proposal %s is %s and does not move again" % (pid, current["state"])}
    if current["state"] != PREDECESSOR.get(state):
        return {"refused": "%s follows %s, not %s" % (state, PREDECESSOR.get(state), current["state"])}
    row = dict(current, state=state, at=lab.now_iso(),
               history=(current.get("history", []) + [{"at": lab.now_iso(), "state": state}])[-12:])
    row.update(extra)
    return _write(row)


def idea(text, spark_key):
    """An instrument idea, cited to the Lab occasion that raised it."""
    text = str(text or "").strip()[:400]
    if len(text) < 20: return {"refused": "an idea needs saying in more than a few words"}
    cited = None
    for row in spark.feed(200):
        if row.get("key") == spark_key: cited = row
    if cited is None:
        return {"refused": "no eligible Lab occasion %r: an idea must cite one" % str(spark_key)[:40]}
    return _write({"proposal_id": "CI-" + uuid.uuid4().hex[:10], "at": lab.now_iso(),
                   "state": IDEA, "idea": text, "spark_key": spark_key,
                   "provenance": cited.get("provenance") or {},
                   "history": [{"at": lab.now_iso(), "state": IDEA}],
                   "truth_status": "lab_instrument_idea_not_a_want_and_not_a_capability"})


def _bounded(parameters):
    """A typed, bounded schema, or the reason it is not one."""
    if not isinstance(parameters, dict) or not parameters:
        return None, "an interface needs a named parameter schema"
    if len(parameters) > MAX_PARAMETERS:
        return None, "at most %d parameters" % MAX_PARAMETERS
    clean = {}
    for name, spec in parameters.items():
        name = str(name)[:40]
        if not isinstance(spec, dict): return None, "parameter %s has no type" % name
        kind = str(spec.get("type", ""))
        if kind not in PARAMETER_TYPES:
            return None, "parameter %s is %r; allowed: %s" % (name, kind, ", ".join(PARAMETER_TYPES))
        entry = {"type": kind}
        if kind in ("number", "integer"):
            try: entry["min"], entry["max"] = float(spec["min"]), float(spec["max"])
            except Exception: return None, "numeric parameter %s needs min and max" % name
            if entry["min"] >= entry["max"]: return None, "parameter %s has an empty range" % name
        if kind == "enum":
            values = [str(v)[:40] for v in (spec.get("values") or [])][:MAX_ENUM]
            if len(values) < 2: return None, "enum parameter %s needs at least two values" % name
            entry["values"] = values
        if kind == "shortstring":
            try: entry["max_length"] = min(120, int(spec.get("max_length", 40)))
            except Exception: return None, "parameter %s needs a max_length" % name
        clean[name] = entry
    return clean, None


def interface(pid, function, parameters, returns):
    """The bounded interface the instrument would present. No parameter may carry code."""
    function = str(function or "").strip()
    if not function.isidentifier(): return {"refused": "the interface needs one function name"}
    clean, why = _bounded(parameters)
    if why: return {"refused": why}
    returns = str(returns or "").strip()[:200]
    if not returns: return {"refused": "say what it returns"}
    return _advance(pid, INTERFACE, interface={"function": function, "parameters": clean,
                                               "returns": returns})


def _test_is_real(source, test, function):
    """A canary that asserts nothing proves nothing, and one that never calls the function
    proves something else. Both checks are structural, not textual."""
    try: tree = ast.parse(test)
    except SyntaxError as exc: return "the canary test does not parse: %s" % exc.msg
    if not any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
        return "the canary test contains no assertion"
    called = any(isinstance(node, ast.Call) and
                 ((isinstance(node.func, ast.Name) and node.func.id == function) or
                  (isinstance(node.func, ast.Attribute) and node.func.attr == function))
                 for node in ast.walk(tree))
    if not called: return "the canary test never calls %s" % function
    try: ast.parse(source)
    except SyntaxError as exc: return "the canary source does not parse: %s" % exc.msg
    return None


def canary(pid, source, test):
    """Run the canary under the repository's OS boundary. Nothing else counts as passing."""
    current = _latest(pid)
    if current is None: return {"refused": "no proposal %s" % pid}
    if current.get("state") != INTERFACE:
        return {"refused": "%s follows %s, not %s" % (CANARY_PASSED, INTERFACE, current.get("state"))}
    function = (current.get("interface") or {}).get("function", "")
    why = _test_is_real(source, test, function)
    if why: return {"refused": why}
    digest = hashlib.sha256((source + "\x1f" + test).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="chem-canary-") as scratch:
        module = os.path.join(scratch, "instrument.py")
        runner = os.path.join(scratch, "canary.py")
        with open(module, "w", encoding="utf-8") as stream: stream.write(source)
        with open(runner, "w", encoding="utf-8") as stream:
            stream.write("import sys; sys.path.insert(0, %r)\nfrom instrument import *\n" % scratch + test)
        try:
            from isolated_exec import run
            done = run([sys.executable, runner], scratch, timeout=CANARY_TIMEOUT)
        except Exception as exc:
            # Missing isolation is an error, never a fallback: an unrun canary is not a
            # passed one, and this stage exists precisely to be hard to reach.
            return {"refused": "the canary could not run under the OS boundary: %s"
                               % str(exc)[:160]}
    if done.returncode != 0:
        # The author of the canary is the one who needs this, and it is their own code, so a
        # bounded tail of the failure goes back. It is not written to any ledger.
        tail = (done.stderr or done.stdout or "").strip().splitlines()[-1:] or [""]
        return {"refused": "the canary failed under isolation (exit %d): %s"
                           % (done.returncode, tail[0][:300])}
    return _advance(pid, CANARY_PASSED,
                    canary={"sha256": digest, "isolation": "isolated_exec",
                            "at": lab.now_iso(), "exit_code": 0})


def offer(pid, want_id, why="", risks="", scope=None, permissions=None):
    """Hand it to the Forge against a live want she already has.

    This does not create the want, does not approve, and does not install. If there is no
    live want whose source is the lab spark, the Forge refuses and that refusal is the
    record — it is not something to route around.
    """
    current = _latest(pid)
    if current is None: return {"refused": "no proposal %s" % pid}
    if current.get("state") != CANARY_PASSED:
        return {"refused": "%s follows %s, not %s" % (OFFERED, CANARY_PASSED, current.get("state"))}
    face = current.get("interface") or {}
    try:
        import skill_forge
    except Exception as exc:
        return {"refused": "the Forge is not reachable: %s" % str(exc)[:120]}
    proposal, refusal = skill_forge.propose(
        capability=face.get("function", ""),
        why=(str(why)[:400] or current.get("idea", ""))[:600],
        want_id=want_id,
        step_note="Chemistry Lab instrument, canary %s" % (current.get("canary") or {}).get("sha256", "")[:12],
        scope={"parameters": face.get("parameters", {}), "returns": face.get("returns", "")},
        permissions=list(permissions or []),
        risks=str(risks)[:600],
        touches=["memory/chemistry-lab"],
        tests="canary ran under isolated_exec; sha256 %s" % (current.get("canary") or {}).get("sha256", "")[:16],
        block={"block_type": "CAPABILITY_ABSENT", "blocked_step": face.get("function", "")},
    )
    if proposal is None:
        return _write(dict(current, state=REFUSED, at=lab.now_iso(), refused_reason=str(refusal)[:300],
                           history=(current.get("history", []) +
                                    [{"at": lab.now_iso(), "state": REFUSED, "why": str(refusal)[:200]}])[-12:]))
    return _advance(pid, OFFERED, forge_proposal_id=proposal.get("id"),
                    forge_state=proposal.get("state"))


def withdraw(pid, why=""):
    """Abandoning is allowed from anywhere except a terminal state — it is the one move
    that does not need a predecessor, because giving up on an idea is not a stage."""
    current = _latest(pid)
    if current is None: return {"refused": "no proposal %s" % pid}
    if current["state"] in TERMINAL:
        return {"refused": "proposal %s is %s and does not move again" % (pid, current["state"])}
    return _write(dict(current, state=WITHDRAWN, at=lab.now_iso(), withdrawn_reason=str(why)[:200],
                       history=(current.get("history", []) +
                                [{"at": lab.now_iso(), "state": WITHDRAWN}])[-12:]))


def open_proposals():
    latest = {}
    for row in _rows(): latest[row.get("proposal_id")] = row
    return [row for row in latest.values() if row.get("state") not in TERMINAL]


def state():
    latest = {}
    for row in _rows(): latest[row.get("proposal_id")] = row
    counts = {}
    for row in latest.values(): counts[row.get("state")] = counts.get(row.get("state"), 0) + 1
    return {"proposals": len(latest), "by_state": counts}


if __name__ == "__main__":
    print(json.dumps({"state": state(), "open": [
        {k: row.get(k) for k in ("proposal_id", "state", "idea", "spark_key")}
        for row in open_proposals()]}, ensure_ascii=False, indent=2))
