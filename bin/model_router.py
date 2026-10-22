"""model_router.py — single source of model truth for Vintos text surfaces.
Claude drives chat/avatar; grok is the fallback (hard refusal, error, toggle=grok, or a forced-turn window).
Voice and Gemma calls are never routed here. Flip a surface in CLAUDE_SURFACES / the mode file, not across jobs."""
import paid_http
import os, sys, json, hashlib, time
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
            "ts": _ut.time(), "model": d.get("model", ""), "provider_request_id": d.get("id"), "stop_reason": d.get("stop_reason"),
            "in": _u.get("input_tokens"), "out": _u.get("output_tokens"),
            "cache_read": _u.get("cache_read_input_tokens"), "cache_write": _u.get("cache_creation_input_tokens")}) + "\n")
    except Exception: pass

_HOME = os.path.expanduser("~")

SOL_MODEL_DEFAULT = "gpt-5.6"


def _env(name, default=""):
    """The one reader for ~/.vintos/vintos.env. Nine places parsed this file by hand and
    disagreed about quotes; every Sol path was in the group that did not strip them, so a
    normally written OPENAI_API_KEY="sk-..." sent the quote marks in the Authorization
    header and OpenAI answered 401. See scripts/env_file.py."""
    import sys as _es
    _es.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    _es.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    try:
        from env_file import value as _ev
        return _ev(name, default)
    except Exception:
        # only reachable from a broken checkout; parse the way env_file would
        try:
            for l in open(os.path.join(_HOME, ".vintos", "vintos.env")):
                t = l.strip()
                if t.startswith("export "): t = t[7:].lstrip()
                if t.startswith(name + "="):
                    v = t.split("=", 1)[1].strip().rstrip("\r")
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'): v = v[1:-1]
                    return v.strip() or default
        except Exception:
            pass
        return default


_MODE_FILE = os.path.join(_HOME, ".vintos", "model-mode.json")
_KEY_FILE = os.path.join(_HOME, ".vintos", "anthropic-key")
CLAUDE_MODEL = "claude-opus-4-8"
# The claude family behind the toggle. "claude" stays Opus 4.8 until Anthropic
# sunsets it — his current voice is not being replaced out from under him.
CLAUDE_MODELS = {"claude": "claude-opus-4-8",
                 "opus55": "claude-opus-5-5",   # replaced the Sonnet 5 slot (Gloria, 2026-09-24)
                 "fable": "claude-fable-5-1"}
LEGACY_MODES = {"sonnet": "opus55"}   # a toggle saved as "sonnet" before the swap now means Opus 5.5
def current_mode():
    m = read_mode().get("mode", "claude")
    return LEGACY_MODES.get(m, m)
def current_claude_model():
    """The CHAT toggle's model. Only chat surfaces follow it; every other place uses location_model()."""
    return CLAUDE_MODELS.get(current_mode(), CLAUDE_MODEL)
# Each place he acts has its own model (Gloria, 2026-09-24). Flipping the chat toggle used to change
# his model everywhere at once; now it changes only the chat. A place not listed follows the chat toggle.
# Every place but the chat is Opus 5.5 (Gloria, 2026-10-20: "switch them all to Opus 5.5, just don't replace Opus 4.8
# in chat"). The chat toggle keeps its own choice.
LOCATION_MODELS = {"atelier": "claude-opus-5-5",       # visit, knock, threshold, opening, and the Atelier's voice
                   "self_review": "claude-opus-5-5",
                   "humor": "claude-opus-5-5",
                   "lab": "claude-sonnet-5-5",         # the Lab's Claude planning/reading lens (Gloria, 2026-10-20: "Lab planning okay")
                   "gap_review": "claude-opus-5-5"}    # the weekly review of where he hits walls
_LOCATIONS_FILE = os.path.join(_HOME, ".vintos", "model-locations.json")
def location_model(location):
    """This place's model: an override in ~/.vintos/model-locations.json, else its default, else the chat toggle."""
    try:
        chosen = json.load(open(_LOCATIONS_FILE)).get(location)
        if isinstance(chosen, str) and chosen.strip(): return chosen.strip()
    except Exception:
        pass
    return LOCATION_MODELS.get(location) or current_claude_model()
def _sol_model():
    """The Sol lens's model. Environment first, then SOL_MODEL= in ~/.vintos/vintos.env
    (the same file that holds his OpenAI key), so switching Sol is one line in that
    file and never depends on how the service loads its environment."""
    m = os.environ.get("SOL_MODEL", "")
    if m: return m
    try:
        return _env("SOL_MODEL") or SOL_MODEL_DEFAULT
    except Exception:
        return "gpt-5.6"
SOL_MODEL = _sol_model()

def _openai_key():
    k = os.environ.get("OPENAI_API_KEY", "")
    if k: return k
    try:
        return _env("OPENAI_API_KEY")
    except Exception:
        return ""

def _reserve_provider(provider, model, paid_reservation=None, organ="model_router"):
    import sys
    sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"scripts"))
    from compute_admission import claim_paid, reserve_paid
    if paid_reservation is not None:
        if not isinstance(paid_reservation, dict):
            raise RuntimeError("paid reservation is malformed")
        ok, why = claim_paid(str(paid_reservation.get("organ") or ""), provider, model,
                             units=1, reservation_id=paid_reservation.get("reservation_id"))
        if not ok: raise RuntimeError(why)
        return paid_reservation.get("reservation_id")
    import uuid
    receipt = uuid.uuid4().hex
    ok,why=reserve_paid(organ,provider,model,reservation_id=receipt)
    if not ok:raise RuntimeError(why)
    return receipt


def _release_provider(provider, model, why="", reservation_id=None, paid_reservation=None):
    """Hand back a reservation for a call the provider refused at the door. Best effort:
    failing to release must never turn a provider error into a second failure."""
    try:
        import sys
        sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(__file__)),"scripts"))
        from compute_admission import release_paid
        organ = (paid_reservation or {}).get("organ", "model_router") if isinstance(paid_reservation, dict) else "model_router"
        release_paid(organ, provider, model, why=why, reservation_id=reservation_id)
    except Exception:
        pass

async def sol_draft(system_text, convo, max_tokens=1500, paid_reservation=None, model=None):
    """Sol (OpenAI) draft. Returns (text, reason_tag) like claude_draft, or (None, '') on any failure."""
    import asyncio as _aio, urllib.request as _u
    k = _openai_key()
    if not k: return None, ""
    chosen = model or SOL_MODEL
    system_text = str(system_text or "").replace("[[CACHESPLIT]]", "")   # Claude's split hint, not words for Sol
    body = {"model": chosen,
            "input": [{"role": "system", "content": system_text}] + for_responses(convo),
            # OpenAI keeps a cached start for minutes by default; her messages come hours apart, so it was always
            # gone. Kept a day instead; a model that refuses the option is asked again without it (2026-10-13).
            "prompt_cache_retention": "24h",
            "max_output_tokens": max_tokens + 4000,
            "reasoning": {"effort": "low", "summary": "auto"},
            # the same job's repeats go to the server that already holds its start (2026-10-13)
            "prompt_cache_key": "vintos-" + __import__("hashlib").md5(str(system_text)[:2000].encode()).hexdigest()[:16]}
    def _call():
        receipt = _reserve_provider("openai",chosen,paid_reservation)
        rq = _u.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json", "Authorization": "Bearer " + k})
        try:
            try:
                return json.loads(paid_http.send(_u.urlopen, __file__, rq, timeout=180).read())
            except _u.HTTPError as he0:
                _why = ""
                try: _why = he0.read().decode(errors="replace")
                except Exception: pass
                if he0.code != 400 or "prompt_cache_retention" not in _why:
                    raise _u.HTTPError(he0.url, he0.code, he0.msg, he0.hdrs, None)
                body.pop("prompt_cache_retention", None)
                rq2 = _u.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + k})
                return json.loads(paid_http.send(_u.urlopen, __file__, rq2, timeout=180).read())
        except _u.HTTPError as he:
            # A key the provider rejects costs nothing, but the reservation was already
            # taken. Left standing, a dead key spends the whole day's paid budget on calls
            # that never happened, and the next REAL Astra call - a forge build, the
            # printer's Blender script - is refused for a budget nothing used.
            if he.code in (401, 403):
                _release_provider("openai", chosen, "HTTP %d from the provider" % he.code,
                                  receipt, paid_reservation)
            raise
    try:
        d = await _aio.to_thread(_call)
        try:
            _u2 = d.get("usage") or {}
            import time as _ut
            open(os.path.expanduser("~/.vintos/logs/openai-usage.jsonl"), "a").write(json.dumps({
                "ts": _ut.time(), "src": "router", "model": chosen, "provider_request_id": d.get("id"), "provider_status": d.get("status"),
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

# Her choice on the toggle must hold (Gloria, 2026-10-19: "the toggle reverted to opus 4.8 when I had opus 5.5
# selected"). The file was written in place, so a read landing mid-write failed and came back as the default
# ("claude", Opus 4.8) - and the next read-modify-write (arm_grok_turns, the toggle, the decline guard) saved that
# default over her choice. Now writes are atomic, and a read that fails returns the last mode actually read.
_LAST_GOOD = {}

def read_mode():
    for _ in range(3):
        try:
            m = json.load(open(_MODE_FILE))
            if isinstance(m, dict) and m.get("mode"):
                _LAST_GOOD.clear(); _LAST_GOOD.update(m)
                return dict(m)
        except FileNotFoundError:
            break
        except Exception:
            time.sleep(0.02)
    return dict(_LAST_GOOD) if _LAST_GOOD else {"mode": "claude", "force_grok_turns": 0}

def write_mode(m):
    try:
        os.makedirs(os.path.dirname(_MODE_FILE), exist_ok=True)
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix=".model-mode.", suffix=".tmp", dir=os.path.dirname(_MODE_FILE))
        with os.fdopen(fd, "w") as f: json.dump(m, f)
        os.replace(tmp, _MODE_FILE)
        if isinstance(m, dict) and m.get("mode"):
            _LAST_GOOD.clear(); _LAST_GOOD.update(m)
    except Exception as e:
        print("[model_router] could not save the toggle: %s" % e, flush=True)

def update_mode(change):
    """Read, change and write the mode file as one step no other writer can interleave with. Each write was already
    atomic, but four places read, change and write (her toggle, the forced-Grok count, the turn that spends it, the
    decline guard): two processes doing that at once lost one update - a turn spending its forced Grok turn could
    write the old model back over her toggle a moment earlier. `change(m)` edits m in place; its result is returned."""
    import fcntl
    os.makedirs(os.path.dirname(_MODE_FILE), exist_ok=True)
    with open(_MODE_FILE + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            m = read_mode()
            before = json.dumps(m, sort_keys=True)
            result = change(m)
            if json.dumps(m, sort_keys=True) != before:   # every turn asks; only a real change is written
                write_mode(m)
            return result
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

def arm_grok_turns(n=1):
    """Regenerate/one-turn override: force grok for the next n turns."""
    def arm(m): m["force_grok_turns"] = max(int(m.get("force_grok_turns", 0) or 0), int(n))
    update_mode(arm)

def _consume_forced():
    def spend(m):
        n = int(m.get("force_grok_turns", 0) or 0)
        if n > 0:
            m["force_grok_turns"] = n - 1; return True
        return False
    return update_mode(spend)

async def _grok_result(convo, params, endpoint, headers, model, system_text):
    """grok stage -> GR result (never raises on a bad body; transport errors propagate to route_reply)."""
    body = {"model": model, "messages": [{"role": "system", "content": system_text}] + for_chat(convo),
            "max_tokens": params.get("max_tokens", 400),
            "temperature": params.get("temperature", 0.85),
            "top_p": params.get("top_p", 0.95),
            "route": "grok"}
    hdrs = dict(headers or {}); hdrs["Idempotency-Key"] = idempotency_key(body)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await paid_http.asend(c.post, __file__, endpoint, headers=hdrs, json=body)
        try: d = r.json()
        except Exception: d = None
    res = GR.from_openai(d, "xai")
    if not res["model"]: res["model"] = model
    return res

async def _grok(convo, params, endpoint, headers, model, system_text):
    res = await _grok_result(convo, params, endpoint, headers, model, system_text)
    if not GR.usable(res): raise RuntimeError("grok %s: %s" % (res["status"], res["reason"]))
    return res["text"]

# A picture she sends goes to whichever brain is toggled, in her message (Gloria, 2026-10-01: "I wanted the
# correlating model to receive it in the same message"). It travels as a neutral part,
# {"type": "image", "media_type": ..., "data": <base64>}, and each provider gets it in its own shape here.
def _neutral_image(p):
    return isinstance(p, dict) and p.get("type") == "image" and "data" in p


def has_images(convo):
    return any(isinstance(m, dict) and isinstance(m.get("content"), list) and any(_neutral_image(p) for p in m["content"])
               for m in convo or [])


def _data_url(p):
    return "data:%s;base64,%s" % (p.get("media_type") or "image/jpeg", p.get("data") or "")


def _shaped(convo, text, image):
    out = []
    for m in convo or []:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list):
            m = dict(m, content=[image(p) if _neutral_image(p) else
                                 text(p) if isinstance(p, dict) and p.get("type") == "text" else p for p in c])
        out.append(m)
    return out


def for_anthropic(convo):
    return _shaped(convo, lambda p: {"type": "text", "text": p.get("text", "")},
                   lambda p: {"type": "image", "source": {"type": "base64", "media_type": p.get("media_type") or "image/jpeg",
                                                          "data": p.get("data") or ""}})


def for_chat(convo):
    """OpenAI-style chat completions: Grok through the shim, and Gemma in LM Studio."""
    return _shaped(convo, lambda p: {"type": "text", "text": p.get("text", "")},
                   lambda p: {"type": "image_url", "image_url": {"url": _data_url(p)}})


def for_responses(convo):
    """OpenAI's Responses API (Sol)."""
    return _shaped(convo, lambda p: {"type": "input_text", "text": p.get("text", "")},
                   lambda p: {"type": "input_image", "image_url": _data_url(p)})


def for_gemini(convo):
    """Google's Gemini API: user/model turns of parts; pictures as inline data; consecutive turns of one role joined."""
    out = []
    for m in convo or []:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"): continue
        c = m.get("content")
        parts = []
        for p in (c if isinstance(c, list) else [{"type": "text", "text": str(c or "")}]):
            if _neutral_image(p):
                parts.append({"inline_data": {"mime_type": p.get("media_type") or "image/jpeg", "data": p.get("data") or ""}})
            elif isinstance(p, dict) and p.get("type") == "text" and str(p.get("text") or "").strip():
                parts.append({"text": p["text"]})
        if not parts: continue
        role = "model" if m["role"] == "assistant" else "user"
        if out and out[-1]["role"] == role: out[-1]["parts"] += parts
        else: out.append({"role": role, "parts": parts})
    return out


GEMINI_MODEL = "gemini-4-argon"   # Google's Gemini 4 Argon (Gloria, 2026-10-14): the second lens, and on the toggle
GOOGLE_USAGE_LOG = os.path.expanduser("~/.vintos/logs/google-usage.jsonl")


async def gemini_draft(system_text, convo, max_tokens=1500, paid_reservation=None, model=None):
    """A draft from Gemini (Argon). Returns (text|None, ''), like claude_draft and sol_draft. Its usage, cached tokens
    included, goes to ~/.vintos/logs/google-usage.jsonl. Gemini caches a repeated start by itself."""
    key = _env("GEMINI_API_KEY")
    if not key: raise RuntimeError("no GEMINI_API_KEY in ~/.vintos/vintos.env")
    chosen = model or GEMINI_MODEL
    body = {"contents": for_gemini(convo), "generationConfig": {"maxOutputTokens": int(max_tokens) + 2000}}
    st = str(system_text or "").replace("[[CACHESPLIT]]", "")
    if st.strip(): body["systemInstruction"] = {"parts": [{"text": st}]}
    try: _reserve_provider("google", chosen, paid_reservation)   # the same daily paid-call budget every provider has
    except ImportError: pass
    async with httpx.AsyncClient(timeout=180) as c:
        r = await paid_http.asend(c.post, __file__, "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % chosen, json=body,
                         headers={"Content-Type": "application/json", "x-goog-api-key": key})
        d = r.json()
    if d.get("error"): raise RuntimeError(str(d["error"])[:200])
    try:
        u = d.get("usageMetadata") or {}
        import time as _gt
        os.makedirs(os.path.dirname(GOOGLE_USAGE_LOG), exist_ok=True)
        open(GOOGLE_USAGE_LOG, "a").write(json.dumps({"ts": _gt.time(), "model": chosen, "in": u.get("promptTokenCount"),
            "out": u.get("candidatesTokenCount"), "thinking": u.get("thoughtsTokenCount"),
            "cached": u.get("cachedContentTokenCount")}) + "\n")
    except Exception: pass
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in ((cand.get("content") or {}).get("parts") or []) if not p.get("thought"))
    return (text.strip() or None), ""


async def described(convo):
    """The same turn with each picture put into words by Gemma, for a route that could not carry the picture."""
    out = []
    for m in convo or []:
        c = m.get("content") if isinstance(m, dict) else None
        if isinstance(c, list) and any(_neutral_image(p) for p in c):
            texts, n = [], 0
            for p in c:
                if _neutral_image(p):
                    n += 1
                    try:
                        seen = await gemma_call([{"role": "user", "content": [
                            {"type": "image", "media_type": p.get("media_type"), "data": p.get("data")},
                            {"type": "text", "text": "Say plainly what this picture shows, in two to four sentences."}]}],
                            temp=0.3, max_tokens=300)
                    except Exception:
                        seen = ""
                    texts.append("[Picture %d, put into words because this route could not carry it:] %s"
                                 % (n, (seen or "(it could not be seen)").strip()))
                elif isinstance(p, dict) and p.get("type") == "text":
                    texts.append(p.get("text", ""))
            m = dict(m, content="\n\n".join(t for t in texts if t))
        out.append(m)
    return out


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
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            blocks = [dict(b) for b in m["content"]]
            texts = [b for b in blocks if b.get("type") == "text"]
            if texts:
                texts[-1]["cache_control"] = {"type": "ephemeral"}
            m["content"] = blocks
            break
    return out

def _learned_body(body, system_text, model):
    """Mark for caching only the start of this prompt that has already repeated within the hour (GR.cache_learned).
    The fixed [[CACHESPLIT]] head was marked for an hour on every call and the last message for five minutes; with
    her messages hours apart neither was ever read back - the router's rows were 99% cache writes, 0% reads, each
    write billed above full price (2026-10-13). The marker itself is only a hint for the old split and is removed."""
    st = str(system_text or "").replace("[[CACHESPLIT]]", "")
    body["messages"] = [dict(m) for m in body.get("messages", [])]
    learned = GR.cache_learned(body, st, model)
    return learned


def _sysblocks(system_text):
    # stable head caches; volatile tail does not. no marker -> do not cache (avoid write surcharge with 0 reads)
    if "[[CACHESPLIT]]" in system_text:
        st, vol = system_text.split("[[CACHESPLIT]]", 1)
        blocks = [{"type": "text", "text": st.strip(), "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
        if vol.strip():
            blocks.append({"type": "text", "text": vol.strip()})
        return blocks
    return [{"type": "text", "text": system_text}]

# Room for his thinking ON TOP of the reply. max_tokens counts thinking and reply together, and it was 1200 in
# all: a turn that thought for ~1200 tokens had nothing left, and "[SCENE:" went out as his whole reply
# (2026-10-01, t-41f6c4549c8a4627). Only tokens used are billed.
THINK_ROOM = 6000
_TAG_ONLY = __import__("re").compile(r"\[[A-Z_]+\s*:[^\]]*(?:\]|$)")


def words_left(text):
    """What of a reply is words once his private tags, closed or cut off, are taken out."""
    return _TAG_ONLY.sub(" ", str(text or "")).strip()


async def _claude(system_text, convo, params, reason, paid_reservation=None):
    key = _anthropic_key()
    if not key: raise RuntimeError("no anthropic key")
    # `reason` no longer turns thinking on: no one thinks (Gloria, 2026-10-08: "No one is to have thinking on.").
    # A model that cannot be told not to (Opus 5.5, Fable) thinks as little as it can, and is still given room so
    # its thinking never eats the reply.
    thinking = GR.thinking_off(current_claude_model())
    max_tok = max(int(params.get("max_tokens", 400)), 128) + (0 if thinking else THINK_ROOM)
    body = {"model": current_claude_model(), "max_tokens": max_tok,
            "messages": for_anthropic(convo)}
    _learned_body(body, system_text, body["model"])
    GR.least_thinking(body)
    # Do NOT send temperature/top_p to Anthropic: its current models reject them
    # ("temperature is deprecated for this model"), which 400'd the whole claude
    # route. Only stop passes through.
    if params.get("stop"): body["stop_sequences"] = [params["stop"]] if isinstance(params["stop"], str) else list(params["stop"])
    _reserve_provider("anthropic",current_claude_model(),paid_reservation)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await paid_http.asend(c.post, __file__, "https://api.anthropic.com/v1/messages", json=body,
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
    """What the local model (Gemma) cannot honour: tools, very long context. Gemma sees, so a picture is not one
    (it is his eyes already; 2026-10-01 the picture itself goes to whichever brain answers)."""
    why = []
    if (params or {}).get("tools") or (params or {}).get("tool_choice"):
        why.append("tools")
    def _textlen(c):   # a picture's bytes are not context length
        return sum(len(str(p.get("text", ""))) for p in c if isinstance(p, dict)) if isinstance(c, list) else len(str(c or ""))
    if sum(_textlen(m.get("content", "")) for m in (convo or []) if isinstance(m, dict)) > 60000:
        why.append("long context")
    return why

def _ledger(res, surface, t0, stage=""):
    """review 171: every stage's measured latency, memory and reported usage, no quality claim."""
    try:
        import time as _lt, compute_admission as _ca
        _ca.record("router:" + str(surface), "foreground", provider=res.get("provider", ""), model=res.get("model", ""),
                   stage=stage or res.get("status", ""), latency_ms=int((_lt.time() - t0) * 1000), usage=res.get("usage"),
                   extra={"provider_request_id": res.get("request_id") or None, "finish_reason": res.get("finish_reason")})
    except Exception:
        pass

ROUTE_BUDGET_S = float(os.environ.get("VINTOS_ROUTE_BUDGET_S", "150"))   # primary model, whole call
ROUTE_FLOOR_S = float(os.environ.get("VINTOS_ROUTE_FLOOR_S", "45"))      # the fallback always gets at least this

async def route_reply_result(surface, system_text, convo, params, grok_endpoint, grok_headers, grok_model, reason=True,
                             paid_reservation=None):
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
        try:   # review 79: a provider call reserves against the day's paid budget first; refused -> held, named
            _reserve_provider("xai", grok_model, paid_reservation,
                              organ="model_router:%s" % surface)
        except Exception as exc:
            return GR.make_result("xai", model=grok_model, status="held",
                                  reason=("paid admission unavailable: %s" % exc)[:200])
        try:
            coro = _grok_result(convo, params, grok_endpoint, grok_headers, grok_model, system_text)
            res = await (_rb_aio.wait_for(coro, timeout=timeout) if timeout else coro)
            if not GR.usable(res) and has_images(convo):
                # the picture could not go through this route: once more, with it put into words by Gemma
                coro = _grok_result(await described(convo), params, grok_endpoint, grok_headers, grok_model, system_text)
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
    # A forced Grok turn comes before every toggle. It used to be checked only after Sol, Argon and local, so when
    # Argon declined and the guard forced Grok, Argon was simply asked again (Gloria, 2026-10-15: "I SHOULD have
    # received a Grok turn but I didn't").
    if _consume_forced():
        return await grok_stage("grok(forced)")
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
    if read_mode().get("mode") == "argon":
        try:
            _gt, _ = await gemini_draft(system_text, convo, max_tokens=(params or {}).get("max_tokens", 900))
            if _gt:
                print("[router] argon answered (%d chars)" % len(_gt), flush=True)
                res = GR.make_result("google", model=GEMINI_MODEL, status="valid", text=_gt, finish_reason="stop")
                res["route"] = "argon"; stages.append(res); res["stages"] = stages
                return res
        except Exception as _ae:
            print("[router/argon toggle]", str(_ae)[:120], flush=True)
        # fall through: Claude next, grok as the unchanged safety net
    if read_mode().get("mode") == "local":
        _t0l = _rb_t.time()
        try:
            _txt = await gemma_call(([{"role":"system","content":system_text}] if system_text else []) + list(convo or []),
                                    temp=(params or {}).get("temperature",.85), max_tokens=(params or {}).get("max_tokens",900))
            if _txt:
                res = GR.make_result("gemma", model=GEMMA_MODEL, status="valid", text=_txt, finish_reason="stop")
                res["route"]="gemma(avatar toggle)"; stages.append(res); res["stages"]=stages
                _ledger(res, surface, _t0l, "local-toggle"); return res
        except Exception as _le:
            stages.append(GR.make_result("gemma", model=GEMMA_MODEL, status="unavailable", reason=str(_le)[:200]))
        # The explicit local choice degrades to the existing Claude→Grok route;
        # it never turns an offline Mac into an empty avatar reply.
    if _consume_forced():
        return await grok_stage("grok(forced)")
    why = "grok(refusal)"
    _t0 = _rb_t.time()
    try:
        # the primary gets at most the route budget; the safety net gets what is left, never less than a
        # floor. Before this the two stages could take 120s each while the caller had already given up
        # and answered "no reply formed" (review P10, 2026-09-05).
        res = await _rb_aio.wait_for(_claude(system_text, convo, params, reason, paid_reservation), timeout=ROUTE_BUDGET_S)
        stages.append(res); _ledger(res, surface, _t0, "claude")
        if GR.usable(res) and res["status"] == "truncated" and not words_left(res["text"]):
            # cut off before a single word reached her: the same model once more, without thinking, rather than
            # a tag fragment as his reply or another model's voice
            res["status"], res["reason"] = "unavailable", "cut off before any words: %r" % res["text"][:40]
            _t1 = _rb_t.time()
            res = await _rb_aio.wait_for(_claude(system_text, convo, params, False, paid_reservation),
                                         timeout=max(ROUTE_FLOOR_S, ROUTE_BUDGET_S - (_rb_t.time() - _t0)))
            stages.append(res); _ledger(res, surface, _t1, "claude-again")
            if GR.usable(res) and not words_left(res["text"]):
                res["status"], res["reason"] = "unavailable", "cut off before any words again"
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


GEMMA_ENDPOINT = "http://100.79.177.103:1234/v1/chat/completions"
GEMMA_MODEL = "gemma-4-26b-a4b-it-uncensored"

async def gemma_call(msgs, temp=0.85, max_tokens=800):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await paid_http.asend(c.post, __file__, GEMMA_ENDPOINT, json={"model": GEMMA_MODEL, "messages": for_chat(msgs),
                                               "temperature": temp, "max_tokens": max_tokens})
        d = r.json()
        return d["choices"][0]["message"]["content"] if "choices" in d else None

CHAT_GROK = ("http://127.0.0.1:8599/v1/chat/completions", "grok-4.20-0309-non-reasoning")   # the chat's own Grok path


async def draft_in_the_moment(system_text, convo, max_tokens=400):
    """(text or None, model): whichever brain the chat toggle holds right now - Grok, Sol, Argon, local or a Claude.
    For what should be done by "the model in use in the moment" (Gloria, 2026-10-20, naming what he felt: "usually
    Grok"). A forced Grok turn belongs to the chat and is not spent here."""
    mode = current_mode()
    if mode == "grok":
        res = await _grok_result(convo, {"max_tokens": max_tokens}, CHAT_GROK[0], {}, CHAT_GROK[1], system_text)
        return (res["text"] if GR.usable(res) else None), CHAT_GROK[1]
    if mode == "sol":
        text, _ = await sol_draft(system_text, convo, max_tokens=max_tokens)
        return text, SOL_MODEL
    if mode == "argon":
        text, _ = await gemini_draft(system_text, convo, max_tokens=max_tokens)
        return text, GEMINI_MODEL
    if mode == "local":
        text = await gemma_call(([{"role": "system", "content": system_text}] if system_text else []) + list(convo),
                                max_tokens=max_tokens)
        return text, GEMMA_MODEL
    model = current_claude_model()
    text, _ = await claude_draft(system_text, convo, max_tokens=max_tokens, model=model)
    return text, model


async def claude_draft(system_text, convo, max_tokens=1500, paid_reservation=None, model=None):
    """Two-first-pass draft on Claude, without thinking (Gloria, 2026-10-08). Returns (text|None, reasoning); reasoning
    is '' except from a model that cannot be told not to think. None on refusal."""
    key = _anthropic_key()
    if not key: raise RuntimeError("no anthropic key")
    convo = list(convo)
    while convo and convo[0].get("role") != "user":
        convo = convo[1:]
    chosen = model or current_claude_model()
    thinking = GR.thinking_off(chosen)
    body = {"model": chosen, "max_tokens": max_tokens + (0 if thinking else THINK_ROOM),   # thinking shares the budget
            "messages": for_anthropic(convo)}
    _learned_body(body, system_text, chosen)
    GR.least_thinking(body)
    _reserve_provider("anthropic",chosen,paid_reservation)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await paid_http.asend(c.post, __file__, "https://api.anthropic.com/v1/messages", json=body,
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
