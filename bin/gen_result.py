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
