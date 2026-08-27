#!/usr/bin/env python3
"""want_spine.py — the executor door (Sol Q1, S2 of the spine build).

One way to run a step. Every capability adapter returns the same envelope, and
a tool that cannot run produces BLOCKED with a named cause — never a silent
False that looks identical to honest emptiness. (The websearch symlink lay dead
for weeks because failure and no-result wore the same face.)

    run_step(capability, note, want) -> StepResult dict:
        result: SUCCEEDED | PARTIAL | NO_RESULT | FAILED | BLOCKED
        findings, block (type/evidence/resume_event), started/ended, error

Wraps the EXISTING router capabilities — nothing re-implemented, everything
re-enveloped. Direct dispatch retires in S3, same patch that adopts this."""
import os, sys, time, importlib.util

_ROUTER = None
def _router():
    global _ROUTER
    if _ROUTER is None:
        spec = importlib.util.spec_from_file_location(
            "wants_router_mod", os.path.expanduser("~/Vintos/wants-router.py"))
        _ROUTER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_ROUTER)
    return _ROUTER

# exception shapes that mean "a precondition is missing", not "the attempt failed"
_BLOCK_MAP = (
    (FileNotFoundError, "TOOL_UNAVAILABLE"),
    (PermissionError, "TOOL_UNAVAILABLE"),
    (ConnectionError, "RESOURCE_UNREACHABLE"),
    (TimeoutError, "RESOURCE_UNREACHABLE"),
)

def run_step(capability, note, want=None):
    res = {"capability": capability, "started": time.time(),
           "result": "FAILED", "findings": "", "block": None, "error": ""}
    r = _router()
    fn = getattr(r, capability, None)
    if not callable(fn):
        res["result"] = "BLOCKED"
        res["block"] = {"block_type": "CAPABILITY_ABSENT",
                        "evidence": "no function %r in router" % capability,
                        "resume_event": "capability added or step revised"}
        res["ended"] = time.time(); return res
    text = note or (want or {}).get("want", "") or ""
    try:
        ok = fn(text)
        if ok:
            res["result"] = "SUCCEEDED"
            try:
                res["findings"] = str(r.capture_findings(capability, text) or "")[:1500]
            except Exception:
                pass
        else:
            # the tool ran and produced nothing - a legal outcome, not a failure
            res["result"] = "NO_RESULT"
    except tuple(e for e, _ in _BLOCK_MAP) as e:
        bt = next(b for cls, b in _BLOCK_MAP if isinstance(e, cls))
        res["result"] = "BLOCKED"
        res["block"] = {"block_type": bt, "evidence": str(e)[:300],
                        "resume_event": "tool or resource restored"}
        res["error"] = str(e)[:300]
    except Exception as e:
        res["result"] = "FAILED"
        res["error"] = str(e)[:300]
    res["ended"] = time.time()
    return res

def apply_result(want, step, res):
    """Write the envelope's truth onto the want. BLOCKED marks the WANT blocked
    (with cause and resume event) so the router skips it instead of hammering;
    nothing here abandons, releases, or times anything out."""
    step["last_result"] = res["result"]
    if res["result"] == "SUCCEEDED":
        step["status"] = "completed"
        want.pop("blocked", None)
    elif res["result"] == "NO_RESULT":
        step["status"] = "completed"
        step["empty"] = True
        want.pop("blocked", None)
    elif res["result"] == "BLOCKED":
        want["blocked"] = dict(res["block"], blocked_step=step.get("capability"),
                               at=time.time())
    # FAILED leaves status pending: the router's ordinary retry cadence applies,
    # but the failure is now on the record instead of vanishing into a log line.
    hist = want.setdefault("step_history", [])
    hist.append({"step": step.get("capability"), "result": res["result"],
                 "findings": res.get("findings", "")[:800],
                 "error": res.get("error", ""), "at": res["ended"]})
    return want

if __name__ == "__main__":
    print(run_step(sys.argv[1] if len(sys.argv) > 1 else "be_silent",
                   " ".join(sys.argv[2:]) or "spine smoke test"))
