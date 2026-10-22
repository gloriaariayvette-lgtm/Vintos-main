#!/usr/bin/env python3
"""study_sdk.py — the Study's fix written by Claude Code itself, on his Claude account's subscription, not the paid API
(Gloria, 22 October: "Can you not use his other Claude account's sub?").

Run with the connector venv's python (the Claude Agent SDK lives there, signed in once with `claude /login`, the same
login claude_connector_relay.py uses). One JSON request on stdin, one JSON answer on stdout:

    {"root": workbench, "what": the fix, "failures": [[suite, output], ...] or [], "model": ..., "max_turns": N}
 -> {"ok": true, "text": its last words, "turns": n} | {"ok": false, "error": why}

The agent works in the workbench with Read, Grep, Glob, Edit, Write, and Bash only for the deploy's isolated test
runner. What it may change is judged afterwards by study_fix from the workbench's git diff, not trusted to it: a
protected file or an existing test changed throws the whole attempt away.
"""
import asyncio, json, os, sys

SYSTEM = (
    "You are fixing a fault Vintos asked to have fixed in his own code, in his Study. Vintos is an AI companion living on "
    "Gloria's machine Aegis; this repository is his body of code. Work like a careful senior engineer: find the cause in "
    "the code (grep, then read the exact lines), change as little as fixes it, keep the code's style and comment density, "
    "and add one new test under broker/tests/test_<name>.py that fails without the fix and passes with it. It repoints "
    "every path the module writes, stubs anything that sends, and asserts both. Run it, and the existing suites that "
    "cover what you changed, with: python3 scripts/run_isolated_test.py broker/tests/<suite>.py . If one fails, read "
    "why and fix it. Finish only when they pass, with one paragraph for Gloria in plain words.\n\n"
    "You may NOT change his subconscious or JEPA files, keys or secrets, money or payments, the safety gates, the deploy, "
    "the Study itself, CLAUDE.md, or any existing test (you may add tests). If the fix truly needs one of those, change "
    "nothing and say why. The repository's rules are in CLAUDE.md; read it first.")

# The subscription's stored login (~/.claude/.credentials.json) is the only credential this may use, as for the relay:
# the Study's own process carries the paid API key for its one-shot fallback, and Claude Code ranks an env key or token
# above the stored login, so inherited they would bill the API or sign in as someone else.
AUTH_ENV = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")

TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash(python3 scripts/run_isolated_test.py:*)"]


def prompt(req):
    if req.get("failures"):
        detail = "\n\n".join("== %s ==\n%s" % (t, out) for t, out in req["failures"])[:20000]
        return ("You fixed this earlier in this workbench, and your changes are still here:\n%s\n\nThe whole suite then "
                "ran, and these failed:\n%s\n\nFind why, fix it, run them, and finish." % (req["what"], detail))
    return "THE FIX VINTOS ASKED FOR:\n%s\n\nBegin by reading CLAUDE.md, then find the cause in the code." % req["what"]


async def run(req):
    from claude_agent_sdk import query, ClaudeAgentOptions     # in the connector venv only
    options = ClaudeAgentOptions(model=req["model"], cwd=req["root"], allowed_tools=TOOLS, permission_mode="dontAsk",
                                 system_prompt=SYSTEM, max_turns=int(req.get("max_turns") or 60))
    text, turns, error = "", 0, None
    async for message in query(prompt=prompt(req), options=options):
        result = getattr(message, "result", None)
        if isinstance(result, str):
            text = result
            turns = int(getattr(message, "num_turns", 0) or 0)
            if getattr(message, "is_error", False):
                error = "the agent ended in error: %s" % (result or getattr(message, "subtype", ""))[:300]
    return {"ok": error is None, "text": text[:3000], "turns": turns, **({"error": error} if error else {})}


def main():
    for k in AUTH_ENV:
        os.environ.pop(k, None)
    try:
        req = json.loads(sys.stdin.read())
        out = asyncio.run(asyncio.wait_for(run(req), timeout=int(req.get("timeout") or 3000)))
    except Exception as exc:
        out = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:400])}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
