"""model_router.py — single source of model truth for Vintos text surfaces.
Claude drives chat/avatar; grok is the fallback (hard refusal, error, toggle=grok, or a forced-turn window).
Voice and Gemma calls are never routed here. Flip a surface in CLAUDE_SURFACES / the mode file, not across jobs."""
import os, sys, json, hashlib
from datetime import datetime
import httpx
for _gp in (os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~/.vintos/workspace/scripts"), os.path.expanduser("~/.vintos/workspace/bin")):
    if os.path.isdir(_gp) and _gp not in sys.path: sys.path.insert(0, _gp)   # gen_result.py may be installed beside either twin on the host
import gen_result as GR   # the one stage/result contract shared with vintos_claude_shim (review 43)
make_result, RESULT_STATUSES = GR.make_result, GR.STATUSES
USAGE_LOG = os.path.expanduser("~/.vintos/logs/anthropic-usage.jsonl")

def idempotency_key(body):
    """Stable hash of the provider request; sent as Idempotency-Key so a resend of the same job to the
    same provider cannot double-charge (review 163). The router never resends after a timeout itself:
    a timed-out primary is recorded unavailable and only the *other* provider is tried."""
    return "vintos-" + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:32]

def _log_usage(d):
    try:
        _u = d.get("usage") or {}
        import time as _ut
        open(USAGE_LOG, "a").write(json.dumps({
            "ts": _ut.time(), "model": d.get("model", ""),
            "in": _u.get("input_tokens"), "out": _u.get("output_tokens"),
            "cache_read": _u.get("cache_read_input_tokens"), "cache_write": _u.get("cache_creation_input_tokens")}) + "\n")
    except Exception: pass

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

async def _grok_result(convo, params, endpoint, headers, model, system_text):
    """grok stage -> GR result (never raises on a bad body; transport errors propagate to route_reply)."""
    body = {"model": model, "messages": [{"role": "system", "content": system_text}] + convo,
            "max_tokens": params.get("max_tokens", 400),
            "temperature": params.get("temperature", 0.85),
            "top_p": params.get("top_p", 0.95),
            "route": "grok"}
    hdrs = dict(headers or {}); hdrs["Idempotency-Key"] = idempotency_key(body)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(endpoint, headers=hdrs, json=body)
        try: d = r.json()
        except Exception: d = None
    res = GR.from_openai(d, "xai")
    if not res["model"]: res["model"] = model
    return res

async def _grok(convo, params, endpoint, headers, model, system_text):
    res = await _grok_result(convo, params, endpoint, headers, model, system_text)
    if not GR.usable(res): raise RuntimeError("grok %s: %s" % (res["status"], res["reason"]))
    return res["text"]

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
    for k in ("temperature", "top_p"):
        if params.get(k) is not None and k not in body:
            body[k] = float(params[k]); break   # Anthropic takes one of the two
    if params.get("stop"): body["stop_sequences"] = [params["stop"]] if isinstance(params["stop"], str) else list(params["stop"])
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.anthropic.com/v1/messages", json=body,
            headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                     "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key,
                     "Idempotency-Key": idempotency_key(body)})
        try: d = r.json()
        except Exception: d = None
    if isinstance(d, dict): _log_usage(d)
    res = GR.from_anthropic(d)
    if not res["model"]: res["model"] = body["model"]
    res["reasoning"] = "".join(b.get("thinking", "") for b in (d or {}).get("content", []) if b.get("type") == "thinking") if isinstance(d, dict) else ""
    return res

MODEL_PROFILE = os.environ.get("VINTOS_MODEL_PROFILE", "mixed")   # review 164: local | mixed

def profile():
    return (os.environ.get("VINTOS_MODEL_PROFILE") or MODEL_PROFILE or "mixed").strip().lower()

def _needs_provider(convo, params):
    """What the local model (Gemma) cannot honour: tools, images, very long context."""
    why = []
    if (params or {}).get("tools") or (params or {}).get("tool_choice"):
        why.append("tools")
    for m in convo or []:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") in ("image_url", "image") for x in c):
            why.append("images"); break
    if sum(len(str(m.get("content", ""))) for m in (convo or []) if isinstance(m, dict)) > 60000:
        why.append("long context")
    return why

def _ledger(res, surface, t0, stage=""):
    """review 171: every stage's measured latency, memory and reported usage, no quality claim."""
    try:
        import time as _lt, compute_admission as _ca
        _ca.record("router:" + str(surface), "foreground", provider=res.get("provider", ""), model=res.get("model", ""),
                   stage=stage or res.get("status", ""), latency_ms=int((_lt.time() - t0) * 1000), usage=res.get("usage"))
    except Exception:
        pass

ROUTE_BUDGET_S = float(os.environ.get("VINTOS_ROUTE_BUDGET_S", "150"))   # primary model, whole call
ROUTE_FLOOR_S = float(os.environ.get("VINTOS_ROUTE_FLOOR_S", "45"))      # the fallback always gets at least this

async def route_reply_result(surface, system_text, convo, params, grok_endpoint, grok_headers, grok_model, reason=True):
    """One GR result (provider, model, request_id, status, usage, text, ...) plus:
         route  - why that provider was chosen ("claude:<model>", "grok(surface)", "grok(primary timed out ...)")
         stages - every stage result in order (the claude stage that timed out / refused is kept, status held/unavailable)
       A primary that times out is recorded unavailable and never resent (review 163); only grok is tried next."""
    import asyncio as _rb_aio, time as _rb_t
    stages = []
    if profile() == "local":
        # review 164: a local-only profile makes NO provider request. Text-only work goes to Gemma;
        # a task needing a capability Gemma lacks is HELD, named, never quietly sent to a provider.
        _need = _needs_provider(convo, params)
        _t0l = _rb_t.time()
        if _need:
            res = GR.make_result("gemma", model=GEMMA_MODEL, status="held",
                                 reason="local profile: no provider request; needs " + ", ".join(_need))
        else:
            try:
                _txt = await gemma_call(([{"role": "system", "content": system_text}] if system_text else []) + list(convo or []),
                                        temp=(params or {}).get("temperature", 0.85), max_tokens=(params or {}).get("max_tokens", 800))
                res = GR.make_result("gemma", model=GEMMA_MODEL, status=("valid" if _txt else "unavailable"), text=_txt or "",
                                     finish_reason="stop" if _txt else "", reason="" if _txt else "gemma returned nothing")
            except Exception as _ge:
                res = GR.make_result("gemma", model=GEMMA_MODEL, status="unavailable", reason=str(_ge)[:200])
        res["route"] = "gemma(local profile)"; stages.append(res); res["stages"] = stages
        _ledger(res, surface, _t0l, "local")
        return res
    async def grok_stage(tag, timeout=None):
        _tg0 = _rb_t.time()
        try:
            coro = _grok_result(convo, params, grok_endpoint, grok_headers, grok_model, system_text)
            res = await (_rb_aio.wait_for(coro, timeout=timeout) if timeout else coro)
        except _rb_aio.TimeoutError:
            res = GR.make_result("xai", model=grok_model, status="unavailable", reason="timed out after send (%ss); not retried" % int(timeout or 60))
        except Exception as e:
            res = GR.make_result("xai", model=grok_model, status="unavailable", reason=("%s: %s" % (type(e).__name__, e))[:200])
        res["route"] = tag; stages.append(res); res["stages"] = stages
        _ledger(res, surface, _tg0, "grok")
        return res
    if surface not in CLAUDE_SURFACES:
        return await grok_stage("grok(surface)")
    if read_mode().get("mode") == "grok":
        return await grok_stage("grok(toggle)")
    if read_mode().get("mode") == "sol":
        try:
            _st, _stag = await sol_draft(system_text, convo)
            if _st:
                print("[router] sol answered (%d chars)" % len(_st), flush=True)
                res = GR.make_result("openai", model=SOL_MODEL, status="valid", text=_st, finish_reason="stop")
                res["route"] = "sol"; stages.append(res); res["stages"] = stages
                return res
        except Exception as _se:
            print("[router/sol toggle]", str(_se)[:120], flush=True)
        # fall through: Claude next, grok as the unchanged safety net
    if _consume_forced():
        return await grok_stage("grok(forced)")
    why = "grok(refusal)"
    _t0 = _rb_t.time()
    try:
        # the primary gets at most the route budget; the safety net gets what is left, never less than a
        # floor. Before this the two stages could take 120s each while the caller had already given up
        # and answered "no reply formed" (review P10, 2026-09-05).
        res = await _rb_aio.wait_for(_claude(system_text, convo, params, reason), timeout=ROUTE_BUDGET_S)
        stages.append(res); _ledger(res, surface, _t0, "claude")
        if GR.usable(res):
            res["route"] = "claude:" + current_claude_model(); res["stages"] = stages
            return res
        why = "grok(%s)" % ("refusal" if res["status"] == "held" else res["status"])
    except _rb_aio.TimeoutError:
        why = "grok(primary timed out at %ds)" % int(ROUTE_BUDGET_S)
        stages.append(GR.make_result("anthropic", model=current_claude_model(), status="unavailable",
                                     reason="timed out after send (%ds); not retried" % int(ROUTE_BUDGET_S)))
    except Exception as e:
        why = "grok(error:%s)" % str(e)[:40]
        stages.append(GR.make_result("anthropic", model=current_claude_model(), status="unavailable", reason=str(e)[:200]))
    _left = max(ROUTE_FLOOR_S, ROUTE_BUDGET_S + ROUTE_FLOOR_S - (_rb_t.time() - _t0))
    return await grok_stage(why, timeout=_left)

async def route_reply(surface, system_text, convo, params, grok_endpoint, grok_headers, grok_model, reason=True):
    """Returns (reply, reasoning, model_used). The grok path is the safety net.
    Thin view over route_reply_result for existing callers; raises when no stage produced text (as before)."""
    res = await route_reply_result(surface, system_text, convo, params, grok_endpoint, grok_headers, grok_model, reason)
    if not GR.usable(res):
        raise RuntimeError("route_reply: %s %s: %s" % (res["provider"], res["status"], res["reason"]))
    return res["text"], res.get("reasoning", ""), res["route"]


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
                     "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key,
                     "Idempotency-Key": idempotency_key(body)})
        d = r.json()
    _log_usage(d)
    res = GR.from_anthropic(d)
    if not GR.usable(res):
        return None, ""
    think = "".join(b.get("thinking", "") for b in d.get("content", []) if b.get("type") == "thinking")
    return res["text"], think
