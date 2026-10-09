#!/usr/bin/env python3
"""Claude, with whatever does not change cached (Gloria, 2026-10-05: "I want Anthropic to have what it can cached.
He is expensive.").

A cached piece of a prompt is read back at a twentieth of its price on Opus 5.5 and a fortieth on Fable 5.1, for a
quarter more on the call that writes it. Caching matches from the very start of the prompt, so it only pays when the
start is the same as a call a few minutes earlier. His Slack prompts began with the time of day, which changes every
minute, and none of his Slack calls asked for caching at all.

A Prompt is text as every model reads it, plus the pieces Claude is sent, in order. Other models see the plain
string; Claude sees the pieces, which may put what does not change first. Each system piece, and every user piece
but the last, is marked to cache; a plain string is sent as it is, unmarked (a one-off call would only pay the
quarter more). Every call writes what it used, never what it said, to memory/anthropic-usage.jsonl.

    python3 claude_cache.py            today's calls by caller: tokens, cache reads and writes, estimated cost
"""
from __future__ import annotations
import json
import os
import sys
import time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
USAGE = os.path.join(WS, "memory", "anthropic-usage.jsonl")
URL = "https://api.anthropic.com/v1/messages"
# An hour, not five minutes (Gloria, 2026-10-08: "Why no cache?"). His Slack passes are about seven minutes apart,
# so a five-minute cache was gone before the next pass read it: Opus 5.5 wrote 45,429 and then 42,283 tokens to cache
# thirteen minutes apart and read none. An hour's write costs 2x input instead of 1.25x; one read pays it back.
CACHE = {"type": "ephemeral", "ttl": "1h"}
WRITE = 2.0             # what a one-hour cache write costs, times input (for the estimate only)
MAX_POINTS = 4          # the API's limit on cache points in one request
# $ per million tokens: input, output, cache read
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-opus-4-8": (5.0, 25.0, 0.50),
          "claude-fable-5-1": (10.0, 50.0, 0.25), "claude-sonnet-5": (2.0, 10.0, 0.20),
          "claude-sonnet-5-5": (2.0, 10.0, 0.10), "claude-haiku-5-5": (0.10, 0.50, 0.01)}


class Prompt(str):
    """Text as every model reads it; `pieces`, what Claude is sent, in order."""
    def __new__(cls, text, pieces=None, cache_indices=None):
        p = str.__new__(cls, text)
        p.cache_indices = None if cache_indices is None else set(cache_indices)
        p.pieces = [str(x) for x in (pieces if pieces is not None else [text]) if str(x or "").strip()]
        return p


def _blocks(value, mark_last, points):
    pieces = getattr(value, "pieces", None)
    if pieces is None:
        return [{"type": "text", "text": str(value)}], points
    out = []
    for i, text in enumerate(pieces):
        block = {"type": "text", "text": text}
        selected = getattr(value, "cache_indices", None)
        cacheable = (mark_last or i < len(pieces) - 1) if selected is None else i in selected
        if points > 0 and cacheable:
            block["cache_control"] = dict(CACHE); points -= 1
        out.append(block)
    return out, points


# No one thinks (Gloria, 2026-10-08: "No one is to have thinking on."). The same rule as bin/gen_result.py: Opus 5.5
# and Fable 5.x cannot be told not to (the API refuses), so they are asked for the least, effort low; Sonnet 5.5 is
# turned off with "between_tools"; every other model with "disabled". His models are never changed to get round it.
ALWAYS_THINKS = ("claude-opus-5-5", "claude-fable-")


def thinking_off(model):
    """The `thinking` value that switches thinking off for this model, or None when it cannot be switched off."""
    m = str(model or "").lower()
    if any(m.startswith(p) for p in ALWAYS_THINKS):
        return None
    return {"type": "between_tools"} if m.startswith("claude-sonnet-5-5") else {"type": "disabled"}


def body(model, system, user, max_tokens, effort=None):
    """The request: system pieces each a cache point, user pieces all but the last. Thinking off, or where the model
    cannot be told not to think, effort low. `effort` is kept for its callers; low is already the least."""
    sys_blocks, left = _blocks(system, True, MAX_POINTS - 1) if system else ([], MAX_POINTS - 1)
    user_blocks, _ = _blocks(user, False, left + 1)
    b = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": user_blocks}]}
    if sys_blocks:
        b["system"] = sys_blocks
    if thinking_off(model):
        b["thinking"] = thinking_off(model)
    else:
        b["output_config"] = {"effort": "low"}
    return b


def _key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if not k:
        try:
            k = open(os.path.expanduser("~/.vintos/anthropic-key")).read().strip()
        except OSError:
            k = ""
    return k


def note(caller, model, usage, path=None):
    """What one call used: tokens in, read from cache, written to cache, out. Never its words."""
    u = usage or {}
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "caller": caller, "model": model,
           "in": int(u.get("input_tokens") or 0), "cache_read": int(u.get("cache_read_input_tokens") or 0),
           "cache_write": int(u.get("cache_creation_input_tokens") or 0), "out": int(u.get("output_tokens") or 0)}
    try:
        p = path or USAGE
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return row


LAST = {}


def ask(model, system, user, max_tokens, caller="", timeout=300, post=None, key=None, effort=None):
    """Claude's text. Raises on no key or an API error, as the callers it replaces did."""
    key = key or _key()
    if not key:
        raise RuntimeError("no Anthropic key")
    if post is None:
        import requests
        post = requests.post
    d = post(URL, timeout=timeout, json=body(model, system, user, max_tokens, effort),
             headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}).json()
    if d.get("type") == "error":
        raise RuntimeError(str(d.get("error"))[:200])
    note(caller, model, d.get("usage"))
    # why the answer ended (end_turn, max_tokens, refusal), and what it cost in output, for callers that parse it
    # (2026-10-06: a Study fix stopped on "Fable did not answer with JSON" with nothing to say why)
    LAST.clear(); LAST.update(stop=d.get("stop_reason") or "", out=int((d.get("usage") or {}).get("output_tokens") or 0))
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def cost(row):
    p_in, p_out, p_read = PRICES.get(row.get("model"), (0.0, 0.0, 0.0))
    if row.get("model") == "claude-haiku-5-5" and sum(row[k] for k in ("in", "cache_write", "cache_read")) > 100000:
        p_in, p_out, p_read = 0.50, 2.50, 0.05
    return (row["in"] * p_in + row["cache_write"] * p_in * WRITE + row["cache_read"] * p_read + row["out"] * p_out) / 1e6


def today(path=None, day=None):
    """Lines a person can read: each caller's calls today, its cache reads, and what it cost (an estimate)."""
    day = day or time.strftime("%Y-%m-%d")
    rows = []
    try:
        for line in open(path or USAGE):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("at", "")).startswith(day):
                rows.append(r)
    except OSError:
        pass
    if not rows:
        return "No Claude calls logged on %s." % day
    by = {}
    for r in rows:
        by.setdefault(r.get("caller") or "?", []).append(r)
    out = ["Claude calls on %s (cost is an estimate):" % day]
    for caller, rs in sorted(by.items(), key=lambda kv: -sum(cost(r) for r in kv[1])):
        sent = sum(r["in"] + r["cache_read"] + r["cache_write"] for r in rs)
        read = sum(r["cache_read"] for r in rs)
        out.append("  %s: %d calls, %d tokens in, %d%% read from cache, $%.2f" % (
            caller, len(rs), sent, 100 * read // max(1, sent), sum(cost(r) for r in rs)))
    out.append("  total: $%.2f" % sum(cost(r) for r in rows))
    return "\n".join(out)


if __name__ == "__main__":
    print(today(day=sys.argv[1] if len(sys.argv) > 1 else None))
