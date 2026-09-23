#!/usr/bin/env python3
"""Claude-side twin of plugin_relay_remote.py: a stdin/stdout doorway to THIS Claude account's
connected connectors (claude.ai/customize/connectors), reached the same way Chat reaches the
ChatGPT app's `codex` server — no browser, no token export, nothing leaves the account.

One JSON request in, one JSON response out, same contract as plugin_relay_remote.connector(), so
the existing plugin_gateway drives it unchanged (point the relay config `command` at this file).

Mechanism (verified 2026-09-22): `claude -p` does NOT load MCP connectors in print mode
(anthropics/claude-code#38987), so this uses the Claude Agent SDK. Auth is the bundled claude's own
stored credential: run `claude /login` ONCE as this user — it persists to ~/.claude/.credentials.json
(0600) and auto-refreshes, so the service authenticates across restarts with nothing to paste. The
relay sets no token; an env CLAUDE_CODE_OAUTH_TOKEN would rank above the stored login and a stale one
would 401, so credential resolution is left to the SDK. There is no direct tool-call passthrough — a connector call is ONE bounded
model turn, restricted to the single requested tool, with a tight instruction to call it once and
return only its result. That costs a few tokens per call (unlike Chat's direct RPC); acceptable for
occasional actions (play a track, place an order, pull a paper), and kept cheap by the one-tool cap.

UNTESTED from CI: the SDK, the account, and the connectors live on the host. Smoke-test on Aegis.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from claude_connector_catalog import policy                        # per-surface tool allow-list (NOT Chat's)
from plugin_send_guard import PolicyHold, outbound_findings       # confidential-info block + link gate

MAX_REQUEST = 128 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
TURN_TIMEOUT = int(os.environ.get("VINTOS_CLAUDE_RELAY_TIMEOUT", "180"))
# Cheap, capable enough to emit one exact tool call; overridable per host.
RELAY_MODEL = os.environ.get("VINTOS_CLAUDE_RELAY_MODEL", "claude-haiku-4-5")
# Auth is the bundled claude's OWN stored credential: run `claude /login` once as this user (it
# persists to ~/.claude/.credentials.json, 0600, and auto-refreshes before expiry — per the Claude
# Code auth docs). The relay injects NO token: an env CLAUDE_CODE_OAUTH_TOKEN ranks ABOVE the stored
# login, so a stale/wrong one silently overrides a good login and 401s. We deliberately let the SDK
# resolve credentials itself, so a valid /login just works across restarts with nothing to paste.


def _coerce_result(text):
    """Keep output: turn the model's fallback text into structured data when it is really JSON.

    The connector's data comes back inside the model turn as a ```json fenced block, or bare JSON,
    OFTEN followed by an English sentence of explanation. Pull the JSON out wherever it sits — the
    fenced block first, then the outermost {...} or [...] — and parse it. Keep the raw text only when
    nothing parses. Never raises.
    """
    body = (text or "").strip()
    candidates = []
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", body, re.S)   # fenced block anywhere, prose after is fine
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(body)                                          # the whole thing, in case it is pure JSON
    for opener, closer in (("{", "}"), ("[", "]")):                  # outermost object/array, ignoring surrounding prose
        i, j = body.find(opener), body.rfind(closer)
        if 0 <= i < j:
            candidates.append(body[i:j + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate), True
        except Exception:
            continue
    return {"text": text or ""}, False


def _guard(entry, tool, arguments, request):
    """Same fail-closed outbound gate as the Codex doorway: block secrets, hold links for approval."""
    outbound = (entry.get("outbound_policy") or {})
    if tool in outbound.get("tools", ()):
        findings = outbound_findings(arguments)
        if findings["rules"]:
            raise PolicyHold({"type": "CONFIDENTIAL_INFORMATION_BLOCKED", "state": "blocked",
                              "request_sha256": findings["request_sha256"], "rules": findings["rules"]})
        if findings["links"]:
            approval = request.get("link_approval") or {}
            if approval.get("request_sha256") != findings["request_sha256"] or not approval.get("hold_id"):
                raise PolicyHold({"type": "LINK_APPROVAL_REQUIRED", "state": "awaiting_explicit_approval",
                                  "request_sha256": findings["request_sha256"], "links": findings["links"]})


def _tool_result_from(message, wanted, tool_uses):
    """Return a result only when the SDK ties it to the requested connector call.

    Claude Agent SDK blocks are typed objects without a ``type`` attribute. A model's final text
    can describe a denied tool as if it succeeded, so it must never stand in for a tool result.
    """
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    for block in (content or []):
        btype = (getattr(block, "type", None) or
                 (block.get("type") if isinstance(block, dict) else None) or
                 type(block).__name__)
        if btype in ("tool_use", "ToolUseBlock"):
            call_id = getattr(block, "id", None) or (block.get("id") if isinstance(block, dict) else None)
            name = getattr(block, "name", None) or (block.get("name") if isinstance(block, dict) else None)
            if call_id and name:
                tool_uses[call_id] = name
            continue
        if btype not in ("tool_result", "mcp_tool_result", "ToolResultBlock"):
            continue
        use_id = getattr(block, "tool_use_id", None) or (block.get("tool_use_id") if isinstance(block, dict) else None)
        name = tool_uses.get(use_id)
        if not name or not str(name).endswith("__" + wanted):
            continue
        errored = getattr(block, "is_error", None)
        if errored is None and isinstance(block, dict):
            errored = block.get("is_error")
        if errored:
            raise RuntimeError("requested connector tool returned an error")
        payload = (block.get("content") if isinstance(block, dict)
                   else getattr(block, "content", None))
        if isinstance(payload, str):
            parsed, valid_json = _coerce_result(payload)
            return parsed if valid_json else {"text": payload}
        return payload
    return None


async def _run(server, tool, arguments, url):
    """One restricted model turn: call exactly mcp__<server>__<tool> and return its raw result.

    The connector is configured explicitly as a remote MCP server here — headless Claude Code does
    NOT inherit the claude.ai account's UI connectors, so we point it at the connector's own MCP URL
    (auth rides the account OAuth token in the environment). No dependence on `claude mcp add`.
    """
    from claude_agent_sdk import query, ClaudeAgentOptions   # imported lazily so CI can parse this file
    fq = f"mcp__{server}__{tool}"
    if not url:
        raise RuntimeError(f"no MCP url configured for connector '{server}' — cannot reach it headless")
    options = ClaudeAgentOptions(
        model=RELAY_MODEL,
        mcp_servers={server: {"type": "http", "url": url}},
        allowed_tools=[fq, f"mcp__claude_ai_{server}__{tool}"],
        permission_mode="dontAsk",
        system_prompt=("You are a deterministic connector relay, not a conversation. Call the tool "
                       f"{fq} exactly once with the arguments given, then stop. Do not call any other "
                       "tool, do not add commentary. The tool's own result is the only output that matters."),
    )
    prompt = f"Call {fq} once with these arguments (JSON): {json.dumps(arguments, ensure_ascii=False)}"
    captured, tool_uses = None, {}
    async for message in query(prompt=prompt, options=options):
        got = _tool_result_from(message, tool, tool_uses)
        if got is not None:
            captured = got
    if captured is not None:
        return {"result": captured, "source": "tool_result"}
    raise RuntimeError("requested connector produced no verified tool result")


def connector(request):
    plugin, surface, tool = request.get("plugin"), request.get("surface"), request.get("tool")
    entry = policy(plugin, surface, tool)                          # raises if tool is outside policy
    arguments = request.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    if len(json.dumps(arguments, allow_nan=False).encode()) > MAX_REQUEST:
        raise ValueError("arguments too large")
    _guard(entry, tool, arguments, request)
    server = str(entry.get("server") or plugin)                   # MCP server segment for mcp__<server>__<tool>
    out = asyncio.run(_run_with_timeout(server, tool, arguments, entry.get("url")))
    encoded = json.dumps(out, allow_nan=False).encode()
    if len(encoded) > MAX_RESPONSE:
        raise ValueError("connected tool response too large")
    return {"ok": True, "plugin": plugin, "tool": tool, "surface": surface,
            "visibility": entry["visibility"], **out}


async def _run_with_timeout(server, tool, arguments, url):
    return await asyncio.wait_for(_run(server, tool, arguments, url), TURN_TIMEOUT)


def main():
    raw = sys.stdin.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        print(json.dumps({"ok": False, "detail": "request too large"})); return
    try:
        request = json.loads(raw or "{}")
        print(json.dumps(connector(request), allow_nan=False))
    except PolicyHold as hold:
        print(json.dumps({"ok": False, "receipt": hold.receipt}))
    except Exception as exc:                                       # one JSON error out, never a stack trace
        print(json.dumps({"ok": False, "detail": (type(exc).__name__ + ": " + str(exc))[:200]}))


if __name__ == "__main__":
    main()
