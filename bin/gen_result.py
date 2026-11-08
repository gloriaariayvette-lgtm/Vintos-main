"""gen_result.py — the one result contract for bilateral generation (review item 43).

Both bin/vintos_claude_shim.py (the OpenAI-compatible shim) and bin/model_router.py (the in-process
router) return this shape for every provider stage, so callers can tell *which* provider answered,
under *which* model, at *what* real cost, and whether the text is whole.

    {"provider": "anthropic"|"xai"|"gemma"|"openai"|...,
     "model": <model that actually answered, "" if unknown>,
     "request_id": <provider request id, "" if unknown>,
     "status": one of STATUSES,
     "usage": {"prompt_tokens", "completion_tokens", "total_tokens"} from the provider, or None,
     "text": <assistant text, "" when nothing usable>,
     "finish_reason": <provider finish/stop reason, normalised to OpenAI names where known>,
     "reason": <one line saying why status is not valid>,
     "tool_calls": [OpenAI-shaped tool calls] or None}

status:  valid       - text (or tool calls) present, provider finished on its own
         truncated   - finish_reason=length / max_tokens: text present but cut short
         held        - the provider declined (refusal / content filter)
         unavailable - no answer from that provider (timeout, connection, key missing, feature unsupported)
         error       - provider returned an error body / status
"""
STATUSES = ("valid", "held", "unavailable", "truncated", "error")
KEYS = ("provider", "model", "request_id", "status", "usage", "text", "finish_reason", "reason", "tool_calls")

_LENGTH = ("length", "max_tokens")
_REFUSAL = ("refusal", "content_filter")


def normalise_finish(reason):
    r = str(reason or "")
    if r in _LENGTH: return "length"
    if r in ("end_turn", "stop_sequence", "stop", ""): return "stop"
    if r in ("tool_use", "tool_calls"): return "tool_calls"
    return r


def make_result(provider, model="", request_id="", status="error", usage=None, text="",
                finish_reason="", reason="", tool_calls=None):
    if status not in STATUSES:
        raise ValueError("bad status %r" % (status,))
    if usage is not None:
        usage = normalise_usage(usage)
    return {"provider": provider, "model": model or "", "request_id": request_id or "", "status": status,
            "usage": usage, "text": text or "", "finish_reason": finish_reason or "",
            "reason": reason or "", "tool_calls": tool_calls or None}


def normalise_usage(u):
    """Provider usage -> OpenAI names. Returns None when the provider gave no counts."""
    if not isinstance(u, dict): return None
    p = u.get("prompt_tokens", u.get("input_tokens"))
    c = u.get("completion_tokens", u.get("output_tokens"))
    if p is None and c is None: return None
    p, c = int(p or 0), int(c or 0)
    out = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": int(u.get("total_tokens") or (p + c))}
    for k in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        if u.get(k) is not None: out[k] = int(u[k])
    return out


def status_from(text, finish_reason, tool_calls=None):
    """Status for a successful provider reply: valid / truncated / held / error(empty)."""
    fr = str(finish_reason or "")
    if fr in _REFUSAL: return "held"
    if not (text or tool_calls): return "error"
    if fr in _LENGTH: return "truncated"
    return "valid"


def usable(r):
    return r.get("status") in ("valid", "truncated") and bool(r.get("text") or r.get("tool_calls"))


def from_anthropic(d, provider="anthropic"):
    """Anthropic /v1/messages body -> result."""
    if not isinstance(d, dict): return make_result(provider, status="error", reason="non-json body")
    if d.get("type") == "error":
        return make_result(provider, status="error", reason=str((d.get("error") or {}).get("message") or d)[:200])
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    calls = [{"id": b.get("id", ""), "type": "function",
              "function": {"name": b.get("name", ""), "arguments": __import__("json").dumps(b.get("input") or {})}}
             for b in d.get("content", []) if b.get("type") == "tool_use"] or None
    fr = normalise_finish(d.get("stop_reason"))
    st = status_from(text, d.get("stop_reason"), calls)
    return make_result(provider, model=d.get("model", ""), request_id=d.get("id", ""), status=st,
                       usage=d.get("usage"), text=text, finish_reason=fr, tool_calls=calls,
                       reason="" if st in ("valid", "truncated") else ("refusal" if st == "held" else "empty completion"))


def from_openai(d, provider):
    """OpenAI-compatible chat.completion body (xai / gemma / openai) -> result."""
    if not isinstance(d, dict): return make_result(provider, status="error", reason="non-json body")
    if d.get("error") or not d.get("choices"):
        e = d.get("error")
        msg = e.get("message") if isinstance(e, dict) else (e or "no choices in reply")
        return make_result(provider, model=d.get("model", ""), request_id=d.get("id", ""), status="error",
                           usage=d.get("usage"), reason=str(msg)[:200])
    ch = d["choices"][0] or {}
    msg = ch.get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):  # some servers return content parts
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    calls = msg.get("tool_calls") or None
    fr = normalise_finish(ch.get("finish_reason"))
    st = status_from(text, ch.get("finish_reason"), calls)
    return make_result(provider, model=d.get("model", ""), request_id=d.get("id", ""), status=st,
                       usage=d.get("usage"), text=text, finish_reason=fr, tool_calls=calls,
                       reason="" if st in ("valid", "truncated") else ("refusal" if st == "held" else "empty completion"))


# No thinking, for anyone (Gloria, 2026-10-08: "No one is to have thinking on."). What turns it off differs by model:
# Sonnet 5.5 refuses "disabled" and takes "between_tools"; Opus 5.5 and Fable 5.x cannot be told not to think at all
# (the API refuses), so they are asked for the least: effort low, with room left to write. His models are never
# changed to get round this (Gloria, 2026-10-08).
ALWAYS_THINKS = ("claude-opus-5-5", "claude-fable-")


def thinking_off(model):
    """The `thinking` value that switches thinking off for this model, or None when it cannot be switched off."""
    m = str(model or "").lower()
    if any(m.startswith(p) for p in ALWAYS_THINKS):
        return None
    if m.startswith("claude-sonnet-5-5"):
        return {"type": "between_tools"}
    return {"type": "disabled"}


def least_thinking(body):
    """Thinking off where the model allows it; where it does not, effort low. Returns the body."""
    off = thinking_off(body.get("model"))
    if off:
        body["thinking"] = off
    else:
        body.setdefault("output_config", {})["effort"] = "low"
    return body


# Every job through the shim (and every avatar and Lab call through model_router) was sent uncached unless its prompt carried [[CACHESPLIT]], and only two did
# (Gloria, 2026-10-13: "How are the constants not cached everywhere?"). The shim now learns each job's
# unchanging start by comparing its prompt with the recent ones: the longest start it shares with a prompt
# seen in the last hour is marked for caching; whatever changes after it is sent at full price. Only text
# that has already repeated is marked, so a one-off call never pays the cache-write premium.
import threading as _thr, time, os
_RECENT = []                      # (time, text) of recent prompts, newest last
_MARKS = []                       # (time, text up to its cache point, ttl) of starts already written to the cache
_RECENT_LOCK = _thr.Lock()
_RECENT_MAX = 96
_RECENT_SECS = 3600
# the shortest start each model will cache, in characters (tokens x 3, so a marked start is never too short)
_MIN_TOKENS = (("claude-haiku-4-5", 4096), ("claude-opus-4-8", 1024), ("claude-sonnet-5-", 512),
               ("claude-sonnet-5", 1024), ("claude-", 512))


def _min_chars(model):
    m = str(model or "")
    return next(t for p, t in _MIN_TOKENS if m.startswith(p)) * 3


def learned_head(text, now=None):
    """(length of the start of `text` that a recent prompt shared, how long ago that prompt was seen).
    The start ends on a line break, so a cached piece never cuts a word. Records `text` either way."""
    now = time.time() if now is None else now
    best, ago = 0, None
    with _RECENT_LOCK:
        _RECENT[:] = [(t, x) for t, x in _RECENT if now - t < _RECENT_SECS]
        for t, x in _RECENT:
            n = len(os.path.commonprefix([text, x]))
            if n > best:
                best, ago = n, now - t
        _RECENT.append((now, text))
        del _RECENT[:-_RECENT_MAX]
    if best < len(text):
        best = text.rfind("\n", 0, best) + 1
    return best, ago


def _written_start(text, n, now):
    """The longest start already written to the cache that this prompt begins with, within the shared start: reading
    it back needs a cache point at exactly that place. Cut anywhere else, the cache is missed and written again: the
    router wrote 33 times in a week and read 0, each prompt cut where it happened to match the one before (2026-10-20,
    pairs two minutes apart, 10:15 and 10:17). (length, ttl) or (0, None)."""
    best, ttl = 0, None
    with _RECENT_LOCK:
        _MARKS[:] = [(t, x, l) for t, x, l in _MARKS if now - t < (3600 if l == "1h" else 300)]
        for t, x, l in _MARKS:
            if best < len(x) <= n and text.startswith(x):
                best, ttl = len(x), l
    return best, ttl


def _remember_start(text, n, ttl, now):
    with _RECENT_LOCK:
        _MARKS.append((now, text[:n], ttl))
        del _MARKS[:-_RECENT_MAX]


def cache_learned(body, sys_txt, model, now=None):
    """Mark the learned unchanging start of system + first user message. Returns what was marked."""
    now = time.time() if now is None else now
    first = body["messages"][0] if body.get("messages") else None
    user0 = first["content"] if first and first.get("role") == "user" and isinstance(first.get("content"), str) else ""
    joined = sys_txt + "\x00" + user0
    n, ago = learned_head(joined, now)
    if n < _min_chars(model):
        body["system"] = sys_txt
        return {"auto": 0}
    written, ttl = _written_start(joined, n, now)
    if written < _min_chars(model): written = 0
    cc = {"type": "ephemeral"}
    if ago is not None and ago > 240:   # repeats slower than the 5-minute cache lasts: keep it an hour
        cc = {"type": "ephemeral", "ttl": "1h"}
    if written and n - written < _min_chars(model):
        n, cc = written, ({"type": "ephemeral", "ttl": "1h"} if ttl == "1h" else {"type": "ephemeral"})   # read it
    elif n > written:
        _remember_start(joined, n, cc.get("ttl", "5m"), now)   # what is longer than any written start is written
    # Cache points: the start already written (read back), the end of the system prompt when the mark runs past it,
    # and the new mark. An hour-long point may not follow a five-minute one, so a written start under an hour-long
    # mark is asked for an hour too.
    points = sorted({c for c in (written, n) if c} | ({len(sys_txt)} if n > len(sys_txt) else set()))
    hour = cc.get("ttl") == "1h" or ttl == "1h"
    mark = {"type": "ephemeral", "ttl": "1h"} if hour else {"type": "ephemeral"}
    def blocks(text, cuts):
        out, at = [], 0
        for c in cuts:
            if c > at:
                out.append({"type": "text", "text": text[at:c], "cache_control": dict(mark)}); at = c
        if text[at:].strip():
            out.append({"type": "text", "text": text[at:]})
        return out
    body["system"] = blocks(sys_txt, [c for c in points if c <= len(sys_txt)])
    user_cuts = [c - len(sys_txt) - 1 for c in points if c > len(sys_txt) + 1]
    if user_cuts and first is not None:
        first["content"] = blocks(user0, user_cuts)
    cc = mark
    return {"auto": n, "ttl": cc.get("ttl", "5m")}
