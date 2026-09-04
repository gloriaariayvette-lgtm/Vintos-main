"""model_router.py — single source of model truth for Vintos text surfaces.
Claude drives chat/avatar; grok is the fallback (hard refusal, error, toggle=grok, or a forced-turn window).
Voice and Gemma calls are never routed here. Flip a surface in CLAUDE_SURFACES / the mode file, not across jobs."""
import os, json
from datetime import datetime
import httpx

_HOME = os.path.expanduser("~")
_MODE_FILE = os.path.join(_HOME, ".vintos", "model-mode.json")
_KEY_FILE = os.path.join(_HOME, ".vintos", "anthropic-key")
CLAUDE_MODEL = "claude-opus-4-8"
# The claude family behind the toggle. "claude" stays Opus 4.8 until Anthropic
# sunsets it — his current voice is not being replaced out from under him.
CLAUDE_MODELS = {"claude": "claude-opus-4-8",
                 "sonnet": "claude-sonnet-5",
                 "fable": "claude-fable-5-1"}
def current_claude_model():
    return CLAUDE_MODELS.get(read_mode().get("mode", "claude"), CLAUDE_MODEL)
def _sol_model():
    """The Sol lens's model. Environment first, then SOL_MODEL= in ~/.vintos/vintos.env
    (the same file that holds his OpenAI key), so switching Sol is one line in that
    file and never depends on how the service loads its environment."""
    m = os.environ.get("SOL_MODEL", "")
    if m: return m
    try:
        return next(l.strip().split("=", 1)[1].strip() for l in open(os.path.join(_HOME, ".vintos", "vintos.env"))
                    if l.strip().startswith("SOL_MODEL="))
    except Exception:
        return "gpt-5.6"
SOL_MODEL = _sol_model()

def _openai_key():
    k = os.environ.get("OPENAI_API_KEY", "")
    if k: return k
    try:
        return next(l.strip().split("=", 1)[1] for l in open(os.path.join(_HOME, ".vintos", "vintos.env"))
                    if l.strip().startswith("OPENAI_API_KEY="))
    except Exception:
        return ""

async def sol_draft(system_text, convo, max_tokens=1500):
    """Sol (OpenAI) draft. Returns (text, reason_tag) like claude_draft, or (None, '') on any failure."""
    import asyncio as _aio, urllib.request as _u
    k = _openai_key()
    if not k: return None, ""
    body = {"model": SOL_MODEL,
            "input": [{"role": "system", "content": system_text}] + convo,
            "max_output_tokens": max_tokens + 4000,
            "reasoning": {"effort": "low", "summary": "auto"}}
    def _call():
        rq = _u.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json", "Authorization": "Bearer " + k})
        return json.loads(_u.urlopen(rq, timeout=180).read())
    try:
        d = await _aio.to_thread(_call)
        try:
            _u2 = d.get("usage") or {}
            import time as _ut
            open(os.path.expanduser("~/.vintos/logs/openai-usage.jsonl"), "a").write(json.dumps({
                "ts": _ut.time(), "src": "router", "model": SOL_MODEL,
                "in": _u2.get("input_tokens", 0), "out": _u2.get("output_tokens", 0),
                "cached": (_u2.get("input_tokens_details") or {}).get("cached_tokens", 0),
                "reasoning": (_u2.get("output_tokens_details") or {}).get("reasoning_tokens", 0)}) + "\n")
        except Exception: pass
        txt, reasoning = "", ""
        for item in d.get("output", []):
            if item.get("type") == "message":
                txt += "".join(c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text")
            elif item.get("type") == "reasoning":
                reasoning += "\n".join(s.get("text", "") for s in item.get("summary", []))
        txt = txt.strip()
        return (txt or None), (reasoning.strip() if txt else "")
    except Exception as e:
        print("[router/sol]", str(e)[:150], flush=True)
        return None, ""
CLAUDE_SURFACES = {"avatar", "study"}   # add "chat" in phase 2

def _anthropic_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if k: return k
    try: return open(_KEY_FILE).read().strip()
    except Exception: return ""

def read_mode():
    try: return json.load(open(_MODE_FILE))
    except Exception: return {"mode": "claude", "force_grok_turns": 0}

def write_mode(m):
    try:
        os.makedirs(os.path.dirname(_MODE_FILE), exist_ok=True)
        json.dump(m, open(_MODE_FILE, "w"))
    except Exception: pass

def arm_grok_turns(n=1):
    """Regenerate/one-turn override: force grok for the next n turns."""
    m = read_mode(); m["force_grok_turns"] = max(int(m.get("force_grok_turns", 0) or 0), int(n)); write_mode(m)

def _consume_forced():
    m = read_mode()
    n = int(m.get("force_grok_turns", 0) or 0)
    if n > 0:
        m["force_grok_turns"] = n - 1; write_mode(m); return True
    return False

async def _grok(convo, params, endpoint, headers, model, system_text):
    body = {"model": model, "messages": [{"role": "system", "content": system_text}] + convo,
            "max_tokens": params.get("max_tokens", 400),
            "temperature": params.get("temperature", 0.85),
            "top_p": params.get("top_p", 0.95),
            "route": "grok"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(endpoint, headers=headers, json=body)
        return r.json()["choices"][0]["message"]["content"]

def _cachetail(convo):
    """Mark the final user message as a cache boundary. The next call in a burst
    (the b1 draft seconds later, or the next turn minutes later) reads the whole
    shared prefix from cache instead of re-billing it."""
    out = [dict(m) for m in convo]
    for m in reversed(out):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            m["content"] = [{"type": "text", "text": m["content"],
                             "cache_control": {"type": "ephemeral"}}]
            break
    return out

def _sysblocks(system_text):
    # stable head caches; volatile tail does not. no marker -> do not cache (avoid write surcharge with 0 reads)
    if "[[CACHESPLIT]]" in system_text:
        st, vol = system_text.split("[[CACHESPLIT]]", 1)
        blocks = [{"type": "text", "text": st.strip(), "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        if vol.strip():
            blocks.append({"type": "text", "text": vol.strip()})
        return blocks
    return [{"type": "text", "text": system_text}]

async def _claude(system_text, convo, params, reason):
    key = _anthropic_key()
    if not key: raise RuntimeError("no anthropic key")
    if reason:
        thinking = {"type": "adaptive", "display": "summarized"}
        max_tok = max(int(params.get("max_tokens", 400)), 1200)
    else:
        thinking = {"type": "disabled"}
        max_tok = max(int(params.get("max_tokens", 400)), 128)
    body = {"model": current_claude_model(), "max_tokens": max_tok,
            "system": _sysblocks(system_text),
            "messages": _cachetail(convo), "thinking": thinking}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.anthropic.com/v1/messages", json=body,
            headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                     "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key})
        d = r.json()
    try:
        _u=d.get("usage") or {}
        import json as _uj, time as _ut
        open(os.path.expanduser("~/.vintos/logs/anthropic-usage.jsonl"),"a").write(_uj.dumps({
            "ts":_ut.time(),"model":d.get("model",""),
            "in":_u.get("input_tokens"),"out":_u.get("output_tokens"),
            "cache_read":_u.get("cache_read_input_tokens"),"cache_write":_u.get("cache_creation_input_tokens")})+"\n")
    except Exception: pass
    if d.get("type") == "error" or d.get("stop_reason") == "refusal":
        return None, ""
    think = "".join(b.get("thinking", "") for b in d.get("content", []) if b.get("type") == "thinking")
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return (text or None), think

async def route_reply(surface, system_text, convo, params, grok_endpoint, grok_headers, grok_model, reason=True):
    """Returns (reply, reasoning, model_used). The grok path is the safety net."""
    if surface not in CLAUDE_SURFACES:
        return await _grok(convo, params, grok_endpoint, grok_headers, grok_model, system_text), "", "grok(surface)"
    if read_mode().get("mode") == "grok":
        return await _grok(convo, params, grok_endpoint, grok_headers, grok_model, system_text), "", "grok(toggle)"
    if read_mode().get("mode") == "sol":
        try:
            _st, _stag = await sol_draft(system_text, convo)
            if _st:
                print("[router] sol answered (%d chars)" % len(_st), flush=True)
                return _st, "", "sol"
        except Exception as _se:
            print("[router/sol toggle]", str(_se)[:120], flush=True)
        # fall through: Claude next, grok as the unchanged safety net
    if _consume_forced():
        return await _grok(convo, params, grok_endpoint, grok_headers, grok_model, system_text), "", "grok(forced)"
    why = "grok(refusal)"
    try:
        reply, reasoning = await _claude(system_text, convo, params, reason)
        if reply is not None:
            return reply, reasoning, "claude:" + current_claude_model()
    except Exception as e:
        why = "grok(error:%s)" % str(e)[:40]
    return await _grok(convo, params, grok_endpoint, grok_headers, grok_model, system_text), "", why


GEMMA_ENDPOINT = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"

async def gemma_call(msgs, temp=0.85, max_tokens=800):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(GEMMA_ENDPOINT, json={"model": GEMMA_MODEL, "messages": msgs,
                                               "temperature": temp, "max_tokens": max_tokens})
        d = r.json()
        return d["choices"][0]["message"]["content"] if "choices" in d else None

async def claude_draft(system_text, convo, max_tokens=1500):
    """Two-first-pass draft on Claude with reasoning. Returns (text|None, reasoning). None on refusal."""
    key = _anthropic_key()
    if not key: raise RuntimeError("no anthropic key")
    convo = list(convo)
    while convo and convo[0].get("role") != "user":
        convo = convo[1:]
    body = {"model": current_claude_model(), "max_tokens": max_tokens,
            "system": _sysblocks(system_text),
            "messages": _cachetail(convo), "thinking": {"type": "adaptive", "display": "summarized"}}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.anthropic.com/v1/messages", json=body,
            headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                     "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key})
        d = r.json()
    try:
        _u=d.get("usage") or {}
        import json as _uj, time as _ut
        open(os.path.expanduser("~/.vintos/logs/anthropic-usage.jsonl"),"a").write(_uj.dumps({
            "ts":_ut.time(),"model":d.get("model",""),
            "in":_u.get("input_tokens"),"out":_u.get("output_tokens"),
            "cache_read":_u.get("cache_read_input_tokens"),"cache_write":_u.get("cache_creation_input_tokens")})+"\n")
    except Exception: pass
    if d.get("type") == "error" or d.get("stop_reason") == "refusal":
        return None, ""
    think = "".join(b.get("thinking", "") for b in d.get("content", []) if b.get("type") == "thinking")
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return (text or None), think
