#!/usr/bin/env python3
"""The Atelier alone speaks first through Fable 5.1, then Astra on failure.

This does not alter any house toggle or conversational route. A refusal,
filtered/empty response, or provider fault spends no words from a local model;
the same sealed prompt is offered once to Astra as the explicit fallback.
"""
from __future__ import annotations
import asyncio, os, sys

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
ASTRA_MODEL = os.environ.get("VINTOS_ATELIER_ASTRA_MODEL", "gpt-6-astra")


def ask(system, user, max_tokens=2000):
    for path in (os.path.join(WS, "bin"), os.path.expanduser("~/Vintos")):
        if path not in sys.path: sys.path.append(path)
    import model_router
    convo = [{"role": "user", "content": user}]
    primary = model_router.CLAUDE_MODELS["fable"]
    try:
        text, _ = asyncio.run(model_router.claude_draft(
            system, convo, max_tokens=max(128, int(max_tokens)), model=primary))
    except Exception:
        text = None
    if text: return text
    try:
        text, _ = asyncio.run(model_router.sol_draft(
            system, convo, max_tokens=max(128, int(max_tokens)), model=ASTRA_MODEL))
    except Exception:
        text = None
    if not text: raise RuntimeError("both Atelier voices were unavailable")
    return text
