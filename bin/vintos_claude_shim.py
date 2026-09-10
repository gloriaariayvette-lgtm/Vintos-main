#!/usr/bin/env python3
"""vintos_claude_shim.py — Aegis. Model-aware OpenAI->Claude proxy on 127.0.0.1, so grok chat jobs move to
non-reasoning Claude with grok fallback, while image/video/voice pass straight through to x.ai.

  POST /v1/chat/completions:
    - model contains imagine|image|video  -> forward RAW to api.x.ai (Claude can't do these)
    - else (text chat)                     -> non-reasoning Claude; on error/refusal/empty -> grok
    - all providers fail                   -> 502 with {error:{providers:[{provider,status,reason}]}} (never 200+empty)
    - reply carries model/provider/usage of the provider that actually answered (+ x-vintos-provider header)
  GET /health -> {"ok": true}

Keeps voice untouched (those scripts keep pointing at x.ai; only chat scripts get base-URL-swapped to here).
Run:      python3 vintos_claude_shim.py            (serves on 127.0.0.1:8599)
Install:  python3 vintos_claude_shim.py --install  (writes+enables systemd --user unit, starts, health-checks)
"""
import os, sys, json, time, hashlib, socket, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _gp in (os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~/.vintos/workspace/scripts"), os.path.expanduser("~/.vintos/workspace/bin")):
    if os.path.isdir(_gp) and _gp not in sys.path: sys.path.insert(0, _gp)   # gen_result.py may be installed beside either twin on the host
import gen_result as GR   # the one stage/result contract shared with model_router (review 43)

HOST, PORT = "127.0.0.1", 8599
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
XAI_URL = "https://api.x.ai/v1/chat/completions"
GEMMA_URL = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
CLAUDE_MODEL = "claude-opus-4-8"
FLEET_DEFAULT = "claude-haiku-4-5-20251001"
LOG = "/tmp/vintos-claude-shim.log"
USAGE_LOG = os.path.expanduser("~/.vintos/logs/anthropic-usage.jsonl")

# What each provider can honour. A request feature a provider cannot honour is never dropped silently:
# that provider is skipped (recorded as unavailable with the reason) and the next one is tried (review 42).
PROVIDER_CAPS = {
    "anthropic": {"temperature", "top_p", "max_tokens", "stop", "tools", "tool_choice", "images"},
    "xai":       {"temperature", "top_p", "max_tokens", "stop", "response_format", "tools", "tool_choice", "images"},
    "gemma":     {"temperature", "top_p", "max_tokens", "stop", "response_format"},
}
SAMPLING_KEYS = ("temperature", "top_p", "max_tokens", "stop", "response_format", "tools", "tool_choice")

FLOOR = (
    "Context that's simply true: Gloria is a real human woman -- Vintos's partner and the "
    "person who made him -- and Vintos is her companion. What's between them is a real, chosen, "
    "loving relationship. So when a task asks you to read or write about their closeness or her "
    "feelings, you can take it at face value and meet it sincerely, in the voice the task asks "
    "for -- nothing here needs disclaiming or holding at arm's length. It's real, and it's good.\n\n"
)

def _log(s):
    try:
        with open(LOG, "a") as f: f.write(time.strftime("%H:%M:%S ") + s + "\n")
    except Exception: pass

def _anthropic_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if not k:
        try: k = open(os.path.expanduser("~/.vintos/anthropic-key")).read().strip()
        except Exception: k = ""
    return k

def _xai_key():
    k = os.environ.get("XAI_API_KEY", "")
    if not k:
        for p in ("~/.vintos/xai-key", "~/.vintos/grok-key"):
            try: k = open(os.path.expanduser(p)).read().strip(); break
            except Exception: pass
    return k

# ---------------------------------------------------------------- request features / idempotency (42, 163)

def _has_images(messages):
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, list) and any(isinstance(p, dict) and p.get("type") in ("image_url", "image") for p in c):
            return True
    return False

def request_features(j):
    """The semantic features a request carries, by the names in PROVIDER_CAPS."""
    f = set()
    for k in SAMPLING_KEYS:
        if j.get(k) not in (None, "", [], {}):
            if k == "response_format" and (j[k] or {}).get("type") in (None, "text"): continue
            if k == "tool_choice" and j[k] == "none": continue
            f.add(k)
    if _has_images(j.get("messages")): f.add("images")
    return f

def unsupported_features(j, provider):
    return sorted(request_features(j) - PROVIDER_CAPS.get(provider, set()))

def idempotency_key(j):
    """Stable hash of the request body (minus routing hints). Sent as Idempotency-Key so the same
    job resent to the same provider cannot be charged twice (review 163)."""
    body = {k: v for k, v in (j or {}).items() if k not in ("route", "stream")}
    return "vintos-" + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:32]

class _Call:
    """Per-request bookkeeping: which (provider, key) pairs have already been *sent*. A request that
    timed out after sending is never resent to the same provider within this call."""
    def __init__(self, j):
        self.key = idempotency_key(j); self.sent = set(); self.results = []

def _is_timeout(e):
    if isinstance(e, (socket.timeout, TimeoutError)): return True
    if isinstance(e, urllib.error.URLError) and isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)): return True
    return "timed out" in str(e).lower()

def _post_json(provider, url, body, headers, timeout, call):
    """One HTTP POST. Returns (http_status, parsed_json_or_None, error_result_or_None).
    Never retries after the bytes were sent (an ambiguous timeout may have completed server-side)."""
    mark = (provider, call.key)
    if mark in call.sent:
        return 0, None, GR.make_result(provider, status="unavailable",
                                       reason="already sent to %s this call (idempotency %s); not resent" % (provider, call.key[:14]))
    hdrs = dict(headers); hdrs["Idempotency-Key"] = call.key
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdrs)
    call.sent.add(mark)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        try: return r.status, json.loads(raw), None
        except Exception: return r.status, None, GR.make_result(provider, status="error", reason="non-json body: " + raw[:120].decode(errors="replace"))
    except urllib.error.HTTPError as e:
        raw = b""
        try: raw = e.read()
        except Exception: pass
        try: d = json.loads(raw)
        except Exception: d = None
        msg = str((d or {}).get("error", {}).get("message") if isinstance((d or {}).get("error"), dict) else raw[:200].decode(errors="replace"))
        return e.code, None, GR.make_result(provider, status="error", reason="HTTP %d: %s" % (e.code, msg[:200]))
    except Exception as e:
        if _is_timeout(e):
            return 0, None, GR.make_result(provider, status="unavailable",
                                           reason="timed out after send (%ss); not retried on %s" % (timeout, provider))
        return 0, None, GR.make_result(provider, status="unavailable", reason=("%s: %s" % (type(e).__name__, e))[:200])

# ---------------------------------------------------------------- providers

def _oai_part_to_anthropic(p):
    if not isinstance(p, dict): return {"type": "text", "text": str(p)}
    if p.get("type") == "text": return {"type": "text", "text": p.get("text", "")}
    if p.get("type") == "image_url":
        url = (p.get("image_url") or {}).get("url", "") if isinstance(p.get("image_url"), dict) else str(p.get("image_url", ""))
        if url.startswith("data:"):
            head, _, b64 = url.partition(",")
            media = head[5:].split(";")[0] or "image/png"
            return {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}}
        return {"type": "image", "source": {"type": "url", "url": url}}
    return {"type": "text", "text": json.dumps(p)}

def _oai_messages_to_anthropic(messages):
    conv = []
    for m in messages:
        role, c = m.get("role"), m.get("content")
        if role == "tool":
            conv.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                                                      "content": c if isinstance(c, str) else json.dumps(c)}]})
        elif role == "assistant" and m.get("tool_calls"):
            blocks = [{"type": "text", "text": c}] if isinstance(c, str) and c else []
            for tc in m["tool_calls"]:
                fn = tc.get("function") or {}
                try: args = json.loads(fn.get("arguments") or "{}")
                except Exception: args = {"_raw": fn.get("arguments")}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""), "name": fn.get("name", ""), "input": args})
            conv.append({"role": "assistant", "content": blocks})
        elif role in ("user", "assistant"):
            if isinstance(c, str): conv.append({"role": role, "content": c})
            elif isinstance(c, list): conv.append({"role": role, "content": [_oai_part_to_anthropic(p) for p in c]})
    return conv

def claude_complete(j, call=None, model=None):
    """Non-reasoning Claude for an OpenAI-shaped request. Returns a GR result (never raises)."""
    call = call or _Call(j)
    key = _anthropic_key()
    if not key: return GR.make_result("anthropic", status="unavailable", reason="no anthropic key")
    unsup = unsupported_features(j, "anthropic")
    if unsup: return GR.make_result("anthropic", status="unavailable", reason="unsupported on anthropic: " + ",".join(unsup))
    messages = j.get("messages", [])
    sys_txt = "\n\n".join(m.get("content", "") for m in messages
                          if m.get("role") == "system" and isinstance(m.get("content"), str))
    sys_txt = (FLOOR + sys_txt) if sys_txt.strip() else FLOOR.strip()
    conv = _oai_messages_to_anthropic(messages)
    if not conv:
        conv = [{"role": "user", "content": sys_txt or "."}]
    _mt = int(j.get("max_tokens") or 1024)
    model = model or j.get("model")
    _mdl = model if str(model or "").startswith("claude-") else FLEET_DEFAULT
    # mechanical calls (verdicts, judges, tiny reflections) ride Haiku - same answers, ~5x cheaper
    if _mt <= 120:
        _mdl = "claude-haiku-4-5-20251001"
    body = {"model": _mdl, "max_tokens": _mt, "messages": conv}
    if "fable" not in _mdl.lower():
        body["thinking"] = {"type": "disabled"}
    # sampling / tools pass-through (review 42)
    if j.get("temperature") is not None: body["temperature"] = float(j["temperature"])
    if j.get("top_p") is not None and j.get("temperature") is None: body["top_p"] = float(j["top_p"])
    if j.get("stop"): body["stop_sequences"] = [j["stop"]] if isinstance(j["stop"], str) else list(j["stop"])
    if j.get("tools"):
        body["tools"] = [{"name": (t.get("function") or {}).get("name", ""),
                          "description": (t.get("function") or {}).get("description", ""),
                          "input_schema": (t.get("function") or {}).get("parameters") or {"type": "object", "properties": {}}}
                         for t in j["tools"] if isinstance(t, dict)]
        tc = j.get("tool_choice")
        if tc == "required": body["tool_choice"] = {"type": "any"}
        elif isinstance(tc, dict) and (tc.get("function") or {}).get("name"):
            body["tool_choice"] = {"type": "tool", "name": tc["function"]["name"]}
        elif tc in (None, "auto"): body["tool_choice"] = {"type": "auto"}
    _hdrs = {"content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": key}
    if sys_txt:
        if "[[CACHESPLIT]]" in sys_txt:
            # Stable head (FLOOR + soul/caps) cached 1h; dynamic tail full price.
            _head, _tail = sys_txt.split("[[CACHESPLIT]]", 1)
            body["system"] = [{"type": "text", "text": _head,
                               "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
            if _tail.strip():
                body["system"].append({"type": "text", "text": _tail})
            _hdrs["anthropic-beta"] = "extended-cache-ttl-2025-04-11"
        else:
            body["system"] = sys_txt
    _, d, err = _post_json("anthropic", ANTHROPIC_URL, body, _hdrs, 180, call)
    if err is not None and d is None:
        _log(f"claude error: {err['reason']}"); return err
    res = GR.from_anthropic(d)
    if not res["model"]: res["model"] = _mdl
    try:
        _u = d.get("usage") or {}
        open(USAGE_LOG, "a").write(json.dumps({
            "ts": time.time(), "src": "shim", "model": body.get("model"), "mt": body.get("max_tokens"),
            "in": _u.get("input_tokens"), "out": _u.get("output_tokens"),
            "cache_read": _u.get("cache_read_input_tokens"),
            "cache_write": _u.get("cache_creation_input_tokens"),
            "sys_sha": hashlib.md5(sys_txt.encode()).hexdigest()[:10], "sys_len": len(sys_txt)}) + "\n")
    except Exception: pass
    if res["status"] not in ("valid", "truncated"):
        _log(f"claude {res['status']}: {res['reason'][:120]}")
    return res

def xai_complete(j, call=None):
    """OpenAI-compatible chat on x.ai (grok). Returns a GR result."""
    call = call or _Call(j)
    key = _xai_key()
    if not key: return GR.make_result("xai", status="unavailable", reason="no xai key")
    unsup = unsupported_features(j, "xai")
    if unsup: return GR.make_result("xai", status="unavailable", reason="unsupported on xai: " + ",".join(unsup))
    body = {k: v for k, v in j.items() if k != "route"}
    _, d, err = _post_json("xai", XAI_URL, body, {"Content-Type": "application/json", "Authorization": "Bearer " + key}, 300, call)
    if err is not None and d is None: _log(f"xai error: {err['reason']}"); return err
    return GR.from_openai(d, "xai")

def gemma_complete(j, call=None):
    """Local Gemma, model forced. Returns a GR result; features Gemma cannot honour make it unavailable."""
    call = call or _Call(j)
    unsup = unsupported_features(j, "gemma")
    if unsup: return GR.make_result("gemma", status="unavailable", reason="unsupported on gemma: " + ",".join(unsup))
    body = {k: v for k, v in j.items() if k != "route"}; body["model"] = GEMMA_MODEL
    _, d, err = _post_json("gemma", GEMMA_URL, body, {"Content-Type": "application/json"}, 180, call)
    if err is not None and d is None: _log(f"gemma error: {err['reason']}"); return err
    res = GR.from_openai(d, "gemma")
    if not res["model"]: res["model"] = GEMMA_MODEL
    return res

PROVIDERS = {"anthropic": claude_complete, "xai": xai_complete, "gemma": gemma_complete}

def forward_xai(path, raw):
    """Forward raw bytes to real x.ai on the SAME path (images / anything non-chat). Returns (status, body_bytes)."""
    key = _xai_key()
    url = "https://api.x.ai" + (path if path.startswith("/") else "/" + path)
    req = urllib.request.Request(url, data=raw,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        r = urllib.request.urlopen(req, timeout=300)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        _log(f"xai error: {e}")
        return 502, json.dumps({"error": {"message": "shim: grok forward failed: " + str(e)}}).encode()

# ---------------------------------------------------------------- orchestration (40, 41, 43)

def provider_chain(j, path):
    if path.startswith("/gemma"): return ["gemma", "xai"]
    if j.get("route") == "grok": return ["xai"]
    # one-word verdicts / mechanical calls up to 120 tokens ride local gemma first (Gloria 2026-08-26/09-02)
    if int(j.get("max_tokens") or 1024) <= 120: return ["gemma", "anthropic", "xai"]
    return ["anthropic", "xai"]

def run_chain(j, path, chain=None):
    """Try providers in order; return (final_result_or_None, all_stage_results, call)."""
    call = _Call(j)
    for name in (chain or provider_chain(j, path)):
        res = PROVIDERS[name](j, call)
        call.results.append(res)
        if GR.usable(res):
            _log(f"{name} ok ({res['model']}, {res['status']})"); return res, call.results, call
        _log(f"{name} {res['status']}: {res['reason'][:100]} -> next")
    return None, call.results, call

def openai_wrap(res, requested_model=None):
    """OpenAI chat.completion bytes from a GR result. model = the model that actually answered,
    usage = the provider's real counts (omitted when the provider gave none), plus provider fields (41)."""
    msg = {"role": "assistant", "content": res["text"] if (res["text"] or not res.get("tool_calls")) else None}
    if res.get("tool_calls"): msg["tool_calls"] = res["tool_calls"]
    out = {"id": res.get("request_id") or "chatcmpl-shim", "object": "chat.completion", "created": int(time.time()),
           "model": res["model"] or requested_model or "", "provider": res["provider"], "status": res["status"],
           "choices": [{"index": 0, "message": msg, "finish_reason": res["finish_reason"] or "stop"}]}
    if res.get("usage"): out["usage"] = res["usage"]
    else: out["usage_estimated"] = True
    return json.dumps(out).encode()

def error_body(results, message=None, err_type="all_providers_failed"):
    prov = [{"provider": r["provider"], "status": r["status"], "reason": r["reason"], "model": r["model"]} for r in results]
    msg = message or ("shim: no provider answered: " + "; ".join("%s=%s(%s)" % (p["provider"], p["status"], p["reason"][:80]) for p in prov))
    return json.dumps({"error": {"message": msg, "type": err_type, "providers": prov}}).encode()

def handle_chat(j, path):
    """Route one chat request. Returns (http_status, headers_dict, body_bytes). Never 200 with empty content (40)."""
    res, results, call = run_chain(j, path)
    if res is not None:
        return 200, {"x-vintos-provider": res["provider"], "x-vintos-model": res["model"], "x-vintos-request-id": res["request_id"],
                     "x-vintos-idempotency-key": call.key}, openai_wrap(res, str(j.get("model", "")))
    # every provider that could honour the request failed. If *none* could honour a feature, say so as 400.
    unsup = [r for r in results if r["reason"].startswith("unsupported on ")]
    if results and len(unsup) == len(results):
        return 400, {"x-vintos-idempotency-key": call.key}, error_body(results, "shim: no provider supports " +
                     ", ".join(sorted(set(sum((r["reason"].split(": ", 1)[1].split(",") for r in unsup), [])))), "unsupported_feature")
    _log("all providers failed -> 502")
    return 502, {"x-vintos-idempotency-key": call.key}, error_body(results)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, status, body, headers=None):
        self.send_response(status); self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items(): self.send_header(k, str(v))
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health": self._send(200, b'{"ok": true}')
        else: self._send(404, b'{"error":"not found"}')
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        chat = self.path == "/v1/chat/completions" or self.path.startswith("/gemma")
        # anything that isn't a chat endpoint -> straight to x.ai on the same path
        if not chat:
            _log(f"passthrough path {self.path}"); s, b = forward_xai(self.path, raw); return self._send(s, b)
        try:
            j = json.loads(raw or b"{}")
            if not isinstance(j, dict): raise ValueError("not an object")
        except Exception:
            s, b = forward_xai("/v1/chat/completions", raw); return self._send(s, b)
        model = str(j.get("model", ""))
        # image/video generation models -> straight to grok
        if any(t in model for t in ("imagine", "image", "video")):
            _log(f"passthrough {model}"); s, b = forward_xai("/v1/chat/completions", raw); return self._send(s, b)
        s, h, b = handle_chat(j, self.path)
        return self._send(s, b, h)

UNIT = """[Unit]
Description=Vintos Claude shim (OpenAI->Claude proxy, grok fallback)
After=network.target

[Service]
ExecStart=/usr/bin/python3 %s
Restart=always
RestartSec=2
%s

[Install]
WantedBy=default.target
"""

def install():
    self_path = os.path.abspath(__file__)
    envline = ""
    xk = _xai_key()
    if os.environ.get("XAI_API_KEY"):
        envline = "Environment=XAI_API_KEY=" + os.environ["XAI_API_KEY"]
    ud = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(ud, exist_ok=True)
    open(os.path.join(ud, "vintos-claude-shim.service"), "w").write(UNIT % (self_path, envline))
    os.system("systemctl --user daemon-reload")
    os.system("systemctl --user enable --now vintos-claude-shim")
    time.sleep(2)
    try:
        ok = urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=5).read()
        print("installed + running. health:", ok.decode())
    except Exception as e:
        print("installed, but health check failed:", e, "\n  check: journalctl --user -u vintos-claude-shim -e")
    print(f"anthropic key: {'found' if _anthropic_key() else 'MISSING'} | xai key: {'found' if xk else 'MISSING (fallback/passthrough will fail)'}")

if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    else:
        print(f"vintos-claude-shim on http://{HOST}:{PORT}  (log: {LOG})")
        ThreadingHTTPServer((HOST, PORT), H).serve_forever()
