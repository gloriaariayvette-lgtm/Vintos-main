#!/usr/bin/env python3
"""claude_sub.py — one Claude answer on Gloria's Claude subscription instead of the paid API (22 October: "use this
subscription for study and connectors", then "move the Forge onto the subscription").

Same signed-in login the connector relay and the Study's writer use (~/.claude/.credentials.json, through the Claude
Agent SDK in the connector venv). No tools, one turn: a plain question and its answer, as claude_cache.ask gives.

    ask(model, system, user, caller=..., timeout=..., effort=...) -> text, or raises

claude_cache.ask calls this first for the callers named in SUBSCRIBED and goes to the paid API only when it raises,
so a lapsed login or a usage limit costs money only for that call, and is logged as such. What the subscription
answered is written to memory/subscription-usage.jsonl, never to the paid ledger.

As a script it is the child that runs in the connector venv: one JSON request on stdin, one JSON answer on stdout.
"""
import asyncio, json, os, subprocess, sys, time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
USAGE = os.path.join(WS, "memory", "subscription-usage.jsonl")
SDK_PY = os.path.expanduser(os.environ.get("VINTOS_CONNECTOR_PY", "~/.vintos/connector-venv/bin/python3"))
# Only the stored login may answer: an inherited key would bill the API, a token would sign in as someone else.
AUTH_ENV = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
# Which of his callers go to the subscription first: the Study and the Forge (Gloria, 22 October).
SUBSCRIBED = ("study-fix", "forge-study", "forge-review")


def subscribed(caller):
    return os.environ.get("VINTOS_SUBSCRIPTION", "1") != "0" and str(caller or "").split(":")[0] in SUBSCRIBED


def _note(caller, model, ok, seconds, why=""):
    try:
        os.makedirs(os.path.dirname(USAGE), exist_ok=True)
        with open(USAGE, "a") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "caller": caller, "model": model,
                                "ok": ok, "seconds": round(seconds, 1), **({"why": why[:200]} if why else {})}) + "\n")
    except OSError:
        pass


def ask(model, system, user, caller="", timeout=600, effort=None, run=None):
    """The subscription's answer, or raises. `run` stands in for the venv child in tests."""
    req = {"model": model, "system": str(system or ""), "user": str(user or ""), "effort": effort}
    started = time.time()
    try:
        if run is not None:
            out = run(req)
        else:
            if not os.path.exists(SDK_PY):
                raise RuntimeError("no connector venv at %s" % SDK_PY)
            env = {k: v for k, v in os.environ.items() if k not in AUTH_ENV}
            r = subprocess.run([SDK_PY, os.path.abspath(__file__)], input=json.dumps(req), text=True,
                               capture_output=True, timeout=timeout, env=env)
            try:
                out = json.loads(r.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                raise RuntimeError("the subscription answered nothing readable (exit %d)" % r.returncode)
        if not out.get("ok") or not str(out.get("text") or "").strip():
            raise RuntimeError("subscription: %s" % (out.get("error") or "an empty answer"))
    except subprocess.TimeoutExpired:
        _note(caller, model, False, time.time() - started, "timed out")
        raise RuntimeError("subscription: timed out after %ds" % timeout)
    except Exception as exc:
        _note(caller, model, False, time.time() - started, str(exc))
        raise
    _note(caller, model, True, time.time() - started)
    return out["text"]


async def _answer(req):
    from claude_agent_sdk import query, ClaudeAgentOptions        # in the connector venv only
    import dataclasses
    kw = dict(model=req["model"], system_prompt=req["system"], tools=[], allowed_tools=[], max_turns=1,
              permission_mode="dontAsk")
    if req.get("effort") and "effort" in {f.name for f in dataclasses.fields(ClaudeAgentOptions)}:
        kw["effort"] = req["effort"]
    text, error = "", None
    async for message in query(prompt=req["user"], options=ClaudeAgentOptions(**kw)):
        result = getattr(message, "result", None)
        if isinstance(result, str):
            text = result
            if getattr(message, "is_error", False):
                error = result[:300] or str(getattr(message, "subtype", ""))
    return {"ok": error is None, "text": text, **({"error": error} if error else {})}


def main():
    for k in AUTH_ENV:
        os.environ.pop(k, None)
    try:
        out = asyncio.run(_answer(json.loads(sys.stdin.read())))
    except Exception as exc:
        out = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
