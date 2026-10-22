#!/usr/bin/env python3
"""Read-only: why the Study's Claude Code run is refused when the connector relay's is not (22 October).
Writes nothing, prints no secret (only whether an auth variable is SET). Four one-word turns on the subscription:
the relay's model and the Study's, each with the shell's environment as it is and with the auth variables removed.

    ~/.vintos/connector-venv/bin/python3 study_sub_probe.py
"""
import asyncio, os, subprocess, glob

AUTH = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
print("auth variables set in this shell:", [k for k in AUTH if os.environ.get(k)] or "none")
print("stored login present:", os.path.exists(os.path.expanduser("~/.claude/.credentials.json")))
for c in glob.glob(os.path.join(os.path.dirname(os.__file__), "..", "**", "claude_agent_sdk", "_bundled", "claude"), recursive=True)[:1]:
    print("bundled claude:", subprocess.run([c, "--version"], capture_output=True, text=True).stdout.strip())
from importlib.metadata import version
print("claude-agent-sdk:", version("claude-agent-sdk"))


async def turn(model):
    from claude_agent_sdk import query, ClaudeAgentOptions
    out = "no result"
    async for m in query(prompt="Reply with the single word OK.", options=ClaudeAgentOptions(model=model, max_turns=1, allowed_tools=[])):
        if isinstance(getattr(m, "result", None), str):
            out = ("ERROR " if getattr(m, "is_error", False) else "ok ") + m.result[:200]
    return out

saved = {k: os.environ.get(k) for k in AUTH}
for stripped in (False, True):
    if stripped:
        for k in AUTH: os.environ.pop(k, None)
    for model in ("claude-haiku-5-5", "claude-opus-5-5", "opus"):
        try: r = asyncio.run(asyncio.wait_for(turn(model), 120))
        except Exception as e: r = "ERROR %s: %s" % (type(e).__name__, str(e)[:200])
        print("%-26s %-18s %s" % ("auth vars removed" if stripped else "shell as is", model, r))
