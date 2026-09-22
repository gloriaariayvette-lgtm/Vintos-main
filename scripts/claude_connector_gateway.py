#!/usr/bin/env python3
"""Claude-account twin of plugin_gateway.py: the Wants/Forge/Lab/Atelier client for THIS account's
own connectors, reached through claude_connector_relay.py.

Same shape as plugin_gateway.call() so a planner uses it through the identical `plugin_query` action;
routing between the two is by which catalog owns the plugin (see owns()). This does NOT modify Chat's
gateway — it reuses its durable receipt store by import so both gateways write one receipt ledger and
either load_receipt finds either call's result.

Chat's relay is a Mac over SSH; these connectors live on the account the SDK signs into, so the relay
runs LOCALLY here (the connector venv's python), one subprocess per call. A `transport=` seam lets a
test stand in for that subprocess without reaching the account.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import claude_connector_catalog
from claude_connector_catalog import policy
# Reuse Chat's durable receipt store WITHOUT modifying it — one ledger, cross-gateway load_receipt.
from plugin_gateway import _store, summary, load_receipt          # noqa: F401  (load_receipt re-exported)
from plugin_send_guard import PolicyHold

RELAY = os.path.join(HERE, "claude_connector_relay.py")
# The Agent SDK lives in the connector venv (externally-managed host python cannot import it).
RELAY_PYTHON = os.environ.get("VINTOS_CLAUDE_RELAY_PYTHON",
                              os.path.expanduser("~/.vintos/connector-venv/bin/python3"))


def owns(plugin):
    """True when this plugin is a Claude-account connector (route here, not to plugin_gateway)."""
    return plugin in claude_connector_catalog.PLUGINS


def _validate(result):
    """Turn a relay response into either a usable result or a raised hold/failure — for BOTH the
    subprocess and the test transport, so the seam can never skip the fail-closed check."""
    if not isinstance(result, dict) or not result.get("ok"):
        if isinstance(result, dict) and isinstance(result.get("receipt"), dict):
            raise PolicyHold(result["receipt"])
        raise RuntimeError("claude connector relay refused or failed: "
                           + str((result or {}).get("detail", "unknown"))[:160])
    return result


def _send(request, timeout=240, transport=None):
    if transport:
        return _validate(transport(request))
    if not Path(RELAY_PYTHON).is_file():
        raise RuntimeError("claude connector venv python unavailable")
    try:
        done = subprocess.run([RELAY_PYTHON, RELAY], input=json.dumps(request), text=True,
                              capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("claude connector relay timed out; outcome unknown and not retried") from exc
    if done.returncode and not done.stdout.strip():
        raise RuntimeError("claude connector relay unavailable")
    try:
        result = json.loads(done.stdout)
    except Exception as exc:
        raise RuntimeError("claude connector relay returned unreadable output") from exc
    return _validate(result)


def call(surface, plugin, tool, arguments, purpose, *, transport=None):
    """One connector call + a durable receipt, identical contract to plugin_gateway.call()."""
    entry = policy(plugin, surface, tool)                          # raises if tool is outside policy
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 1000:
        raise ValueError("bounded purpose required")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    request = {"plugin": plugin, "surface": surface, "tool": tool, "arguments": arguments}
    response = _send(request, transport=transport)
    receipt = _store(surface, plugin, tool, arguments, response["result"], entry["visibility"])
    return {"ok": True, "receipt": receipt, "summary": summary(response["result"])}
