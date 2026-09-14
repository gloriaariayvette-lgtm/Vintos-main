#!/usr/bin/env python3
"""Daily-inner and body context reach only the chat surfaces that own them.

The suite executes the shared readers against a scratch memory directory, stubs the
device provider, and never imports the running server or reaches a provider/network.
"""
import ast
import os
import sys
import tempfile
import types
from datetime import date

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SERVER_PATH = os.path.join(REPO, "bin", "server.py")
SOURCE = open(SERVER_PATH, encoding="utf-8").read()
TREE = ast.parse(SOURCE)
TMP = tempfile.mkdtemp(prefix="vintos-chat-context-")
MEM = os.path.join(TMP, "memory")
os.makedirs(MEM)


def function_source(name):
    rows = [node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name]
    assert len(rows) == 1, (name, len(rows))
    return ast.get_source_segment(SOURCE, rows[0])


def load_function(name, extra=None):
    scope = {"os": os, "MEMORY": MEM, "WORKSPACE": TMP}
    scope.update(extra or {})
    exec(function_source(name), scope)
    return scope[name]


daily = load_function("_daily_inner_context")
today = date.today().isoformat()
today_path = os.path.join(MEM, "daily-inner-life-%s.md" % today)
open(today_path, "w", encoding="utf-8").write("TODAY-UNIQUE daily receipt")
block = daily()
assert block.startswith("[YOUR INNER LIFE TODAY]\n") and "TODAY-UNIQUE" in block

# Empty today falls back to the newest non-empty ledger instead of erasing continuity.
open(today_path, "w", encoding="utf-8").write("  \n")
older = os.path.join(MEM, "daily-inner-life-2026-09-12.md")
open(older, "w", encoding="utf-8").write("FALLBACK-UNIQUE remembered receipt")
assert "FALLBACK-UNIQUE" in daily()

main = function_source("chat_full_context")
avatar = function_source("avatar_chat")
gather = function_source("gather_vintos_context")
debug = function_source("debug_context")
assert "context = gather_vintos_context()" in main
assert "_daily_inner = _daily_inner_context()" in gather
assert "{_daily_inner_context()}" in avatar
assert '"has_daily_inner"' in debug and '"daily_inner_occurrences"' in debug

# Main is words-only; Avatar/ReelRoom share avatar_chat and retain the live body reader.
assert "_hw_context(include_devices=False)" in main
assert "_last_device_context()" not in main
assert '_surface = "reelroom" if getattr(msg, "surface", None) == "reelroom" else "avatar"' in avatar
assert "system_prompt + _hw_context()" in avatar

calls = []
fake_device = types.SimpleNamespace(context_block=lambda: calls.append("read") or "LIVE-INSTRUMENT")
sys.modules["device_context"] = fake_device
hw = load_function("_hw_context", {"_HW_BTN": os.path.join(TMP, "stop.json")})
assert hw(include_devices=False) == "" and calls == [], "words-only must not read device state"
assert "LIVE-INSTRUMENT" in hw() and calls == ["read"], "embodied surfaces get live context"

# No test path points at the live workspace and no sender/provider exists in this suite.
assert not MEM.startswith(os.path.expanduser("~/.vintos"))
assert "requests" not in globals() and "urllib" not in globals()
print("17/17 passed")
