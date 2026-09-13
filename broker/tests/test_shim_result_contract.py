#!/usr/bin/env python3
"""Shim + router result contract (review items 40, 41, 42, 43, 163).

40  all providers fail -> 502 with a JSON body naming providers and reasons; never 200 + empty content
41  reply model/usage/provider are the provider's real values (usage omitted when not given)
42  sampling / response_format / tools / images pass through; a provider that cannot honour one is
    skipped with an explicit reason (Gemma + tools), never silently dropped
43  one result dict shape from both the shim and model_router, truncated <- finish_reason=length
163 a request that timed out after send is not resent to the same provider; Idempotency-Key is sent

No network, no ~/.vintos: urllib/httpx are faked, log paths point at a tempdir.
"""
import os, sys, json, socket, tempfile, types, asyncio, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTD, "bin"))
TMP = tempfile.mkdtemp(prefix="shim-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

# ---------------------------------------------------------------- fake httpx for model_router
class _FakeResp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _FakeClient:
    handler = None; posts = []
    def __init__(self, timeout=None): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        _FakeClient.posts.append((url, headers or {}, json))
        return _FakeResp(await _FakeClient.handler(url, headers or {}, json))
fake_httpx = types.ModuleType("httpx"); fake_httpx.AsyncClient = _FakeClient
sys.modules["httpx"] = fake_httpx

import gen_result as GR
import vintos_claude_shim as S
import model_router as MR
S.LOG = os.path.join(TMP, "shim.log"); S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")
MR.USAGE_LOG = os.path.join(TMP, "usage.jsonl"); MR._MODE_FILE = os.path.join(TMP, "mode.json"); MR._KEY_FILE = os.path.join(TMP, "nokey")
MR.ROUTE_BUDGET_S, MR.ROUTE_FLOOR_S = 0.2, 0.2

# ---------------------------------------------------------------- fake urllib for the shim
class _FakeHTTP:
    def __init__(self, status, body): self.status, self._b = status, json.dumps(body).encode()
    def read(self): return self._b
CALLS = []
def fake_urlopen(handlers):
    """handlers: {provider: callable(body_dict, headers) -> dict | Exception}; records every send."""
    def _open(req, timeout=None):
        url = req.full_url
        prov = "anthropic" if "anthropic" in url else "xai" if "x.ai" in url else "gemma"
        body = json.loads(req.data); hdrs = {k.lower(): v for k, v in req.header_items()}
        CALLS.append((prov, body, hdrs))
        out = handlers[prov](body, hdrs)
        if isinstance(out, Exception): raise out
        return _FakeHTTP(200, out)
    return _open

def run(j, path="/v1/chat/completions", **handlers):
    CALLS.clear(); S.urllib.request.urlopen = fake_urlopen(handlers)
    s, h, b = S.handle_chat(j, path)
    return s, h, json.loads(b)

ANTH_OK = lambda body, h: {"id": "msg_1", "type": "message", "model": "claude-haiku-4-5-20251001", "stop_reason": "end_turn",
                           "content": [{"type": "text", "text": "hello from claude"}], "usage": {"input_tokens": 12, "output_tokens": 5}}
XAI_OK = lambda body, h: {"id": "cc_9", "model": "grok-4", "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello from grok"},
                                                                    "finish_reason": "stop"}], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
ANTH_ERR = lambda body, h: urllib.error.HTTPError("u", 529, "overloaded", {}, __import__("io").BytesIO(b'{"error":{"message":"Overloaded"}}'))
XAI_DOWN = lambda body, h: urllib.error.URLError(ConnectionRefusedError("refused"))
BASE = {"model": "grok-4", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 500}

print("--- 40: never 200 with empty content ---")
s, h, b = run(dict(BASE), anthropic=ANTH_ERR, xai=XAI_DOWN)
check("all providers fail -> 502", s == 502, s)
check("body is JSON error naming each provider + reason", b.get("error", {}).get("type") == "all_providers_failed"
      and [p["provider"] for p in b["error"]["providers"]] == ["anthropic", "xai"]
      and "Overloaded" in b["error"]["providers"][0]["reason"] and "refused" in b["error"]["providers"][1]["reason"], b)
check("statuses in body: error (HTTP 529) / unavailable (connection)",
      [p["status"] for p in b["error"]["providers"]] == ["error", "unavailable"], b)
EMPTY_ANTH = lambda body, h: {"id": "m", "model": "claude-haiku-4-5-20251001", "stop_reason": "end_turn", "content": [], "usage": {"input_tokens": 1, "output_tokens": 0}}
EMPTY_XAI = lambda body, h: {"id": "c", "model": "grok-4", "choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]}
s, h, b = run(dict(BASE), anthropic=EMPTY_ANTH, xai=EMPTY_XAI)
check("empty completions from every provider -> 502, not 200+empty", s == 502 and "empty completion" in json.dumps(b), (s, b))
s, h, b = run(dict(BASE), path="/gemma/v1/chat/completions", gemma=lambda b_, h_: socket.timeout("timed out"), xai=EMPTY_XAI)
check("/gemma route with gemma timeout + empty grok -> 502 (old code answered 200 empty)", s == 502, (s, b))
check("named Aegis utility lane does not inherit the Mac Gemma default",
      S.provider_chain(BASE, "/gemma-aegis/v1/chat/completions") == ["aegis_gemma", "gemma", "xai"]
      and S.AEGIS_GEMMA_URL.startswith("http://172.18.16.1:")
      and S.AEGIS_GEMMA_MODEL == "google/gemma-4-12b-qat")

print("--- 41: real model / usage / provider ---")
s, h, b = run(dict(BASE), anthropic=ANTH_OK, xai=XAI_OK)
check("200 with text", s == 200 and b["choices"][0]["message"]["content"] == "hello from claude", b)
check("model = model that answered (not the requested grok-4)", b["model"] == "claude-haiku-4-5-20251001", b["model"])
check("usage = provider's real counts", b["usage"] == {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}, b.get("usage"))
check("provider field + x-vintos-provider header", b["provider"] == "anthropic" and h["x-vintos-provider"] == "anthropic", (b.get("provider"), h))
check("id = provider request id", b["id"] == "msg_1", b["id"])
s, h, b = run(dict(BASE), anthropic=ANTH_ERR, xai=XAI_OK)
check("fallback to grok reports grok's model/usage/provider", b["model"] == "grok-4" and b["usage"]["total_tokens"] == 10
      and h["x-vintos-provider"] == "xai", (b.get("model"), b.get("usage"), h))
s, h, b = run(dict(BASE), anthropic=ANTH_ERR, xai=lambda b_, h_: {"id": "c", "model": "grok-4",
      "choices": [{"message": {"role": "assistant", "content": "no counts"}, "finish_reason": "stop"}]})
check("no usage from provider -> usage omitted and marked estimated (never fake zeros)",
      "usage" not in b and b.get("usage_estimated") is True, b)

print("--- 42: sampling / response_format / tools / images pass through; unsupported -> explicit ---")
req = dict(BASE, temperature=0.3, stop=["END"], tools=[{"type": "function", "function": {"name": "f", "description": "d",
           "parameters": {"type": "object", "properties": {"x": {"type": "string"}}}}}], tool_choice="required",
           messages=[{"role": "user", "content": [{"type": "text", "text": "look"},
                      {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}]}])
TOOL_ANTH = lambda body, h: {"id": "m2", "model": "claude-haiku-4-5-20251001", "stop_reason": "tool_use",
                             "content": [{"type": "tool_use", "id": "tu_1", "name": "f", "input": {"x": "1"}}], "usage": {"input_tokens": 3, "output_tokens": 2}}
s, h, b = run(req, anthropic=TOOL_ANTH, xai=XAI_OK)
sent = CALLS[0][1]
check("temperature + stop reach anthropic", sent.get("temperature") == 0.3 and sent.get("stop_sequences") == ["END"], sent)
check("tools + tool_choice translated for anthropic", sent["tools"][0]["name"] == "f" and sent["tools"][0]["input_schema"]["properties"]["x"]
      and sent["tool_choice"] == {"type": "any"}, sent.get("tools"))
check("image part translated to an anthropic image block", sent["messages"][0]["content"][1] ==
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}}, sent["messages"][0])
check("tool_use comes back as OpenAI tool_calls / finish_reason=tool_calls",
      b["choices"][0]["message"]["tool_calls"][0]["function"] == {"name": "f", "arguments": '{"x": "1"}'}
      and b["choices"][0]["finish_reason"] == "tool_calls", b["choices"][0])
tiny = dict(BASE, max_tokens=50, tools=req["tools"], tool_choice="auto")
s, h, b = run(tiny, gemma=lambda b_, h_: {"id": "g", "model": "gemma", "choices": [{"message": {"content": "dropped-tools answer"}, "finish_reason": "stop"}]},
              anthropic=TOOL_ANTH, xai=XAI_OK)
check("tools on a tiny call: gemma skipped (would drop tools), anthropic answers", h["x-vintos-provider"] == "anthropic"
      and [c[0] for c in CALLS] == ["anthropic"], (h, [c[0] for c in CALLS]))
check("gemma stage recorded as explicit 'unsupported on gemma: tools'",
      any(r["reason"] == "unsupported on gemma: tool_choice,tools" for r in S.run_chain(tiny, "/v1/chat/completions")[1]),
      S.run_chain(tiny, "/v1/chat/completions")[1][0])
s, h, b = run(dict(tiny), path="/gemma/v1/chat/completions", gemma=lambda b_, h_: {"choices": []}, xai=XAI_DOWN)
check("/gemma route + tools, grok down -> 502 body says gemma unsupported (not silently dropped)",
      s == 502 and b["error"]["providers"][0]["reason"].startswith("unsupported on gemma"), (s, b))
jsonreq = dict(BASE, response_format={"type": "json_object"})
s, h, b = run(jsonreq, anthropic=ANTH_OK, xai=lambda b_, h_: XAI_OK(b_, h_) | {"choices": [{"message": {"content": '{"a":1}'}, "finish_reason": "stop"}]})
check("response_format json: anthropic cannot honour it -> failed over to grok with response_format intact",
      h["x-vintos-provider"] == "xai" and CALLS[0][0] == "xai" and CALLS[0][1]["response_format"] == {"type": "json_object"}, (h, CALLS))
S.PROVIDER_CAPS["xai"].discard("response_format")
s, h, b = run(jsonreq, anthropic=ANTH_OK, xai=XAI_OK)
S.PROVIDER_CAPS["xai"].add("response_format")
check("feature no provider supports -> 400 unsupported_feature naming it, never a silent drop",
      s == 400 and b["error"]["type"] == "unsupported_feature" and "response_format" in b["error"]["message"] and CALLS == [], (s, b, CALLS))
s, h, b = run(dict(BASE, top_p=0.5, temperature=0.9, stop="X"), anthropic=ANTH_ERR, xai=XAI_OK)
check("grok gets temperature/top_p/stop untouched", CALLS[-1][1]["top_p"] == 0.5 and CALLS[-1][1]["temperature"] == 0.9 and CALLS[-1][1]["stop"] == "X", CALLS[-1][1])

print("--- 43: one result contract, shim and router ---")
res, stages, call = S.run_chain(dict(BASE), "/v1/chat/completions")
check("shim stage result has exactly the contract keys", set(res) == set(GR.KEYS), sorted(res))
check("all statuses from the contract set", all(r["status"] in GR.STATUSES for r in stages) and GR.STATUSES == ("valid", "held", "unavailable", "truncated", "error"), stages)
LONG_XAI = lambda b_, h_: XAI_OK(b_, h_) | {"choices": [{"message": {"content": "cut off mid"}, "finish_reason": "length"}]}
s, h, b = run(dict(BASE), anthropic=ANTH_ERR, xai=LONG_XAI)
check("finish_reason=length -> status truncated, still delivered (200, finish_reason=length)",
      s == 200 and b["status"] == "truncated" and b["choices"][0]["finish_reason"] == "length", b)
MAXT = lambda b_, h_: ANTH_OK(b_, h_) | {"stop_reason": "max_tokens"}
S.urllib.request.urlopen = fake_urlopen({"anthropic": MAXT})
res = S.claude_complete(dict(BASE))
check("anthropic stop_reason=max_tokens -> truncated", res["status"] == "truncated" and res["finish_reason"] == "length", res)
S.urllib.request.urlopen = fake_urlopen({"anthropic": lambda b_, h_: ANTH_OK(b_, h_) | {"stop_reason": "refusal"}})
check("anthropic refusal -> held", S.claude_complete(dict(BASE))["status"] == "held")

async def _router(handler, surface="avatar"):
    _FakeClient.handler = handler; _FakeClient.posts.clear()
    return await MR.route_reply_result(surface, "sys", [{"role": "user", "content": "hi"}], {"max_tokens": 50, "temperature": 0.4},
                                       "http://127.0.0.1:8599/v1/chat/completions", {"Authorization": "Bearer x"}, "grok-4")
async def anth_then_grok(url, hdrs, body):
    if "anthropic" in url:
        return {"id": "msg_r", "model": "claude-opus-4-8", "stop_reason": "max_tokens", "content": [{"type": "text", "text": "router text"}],
                "usage": {"input_tokens": 20, "output_tokens": 50}}
    return XAI_OK(body, hdrs)
r = asyncio.run(_router(anth_then_grok))
check("router result has the same contract keys (+ route/reasoning/stages)", set(GR.KEYS) <= set(r) and "route" in r and "stages" in r, sorted(r))
check("router: provider/model/request_id/usage are the provider's real values", r["provider"] == "anthropic" and r["model"] == "claude-opus-4-8"
      and r["request_id"] == "msg_r" and r["usage"]["total_tokens"] == 70, r)
check("router: stop_reason=max_tokens -> truncated", r["status"] == "truncated" and r["finish_reason"] == "length", r["status"])
check("router: temperature passed to anthropic", _FakeClient.posts[0][2].get("temperature") == 0.4, _FakeClient.posts[0][2])
t = asyncio.run(MR.route_reply("avatar", "sys", [{"role": "user", "content": "hi"}], {"max_tokens": 50},
                               "http://127.0.0.1:8599/v1/chat/completions", {}, "grok-4"))
check("route_reply tuple view unchanged for existing callers", t[0] == "router text" and t[2] == "claude:claude-opus-4-8", t)
async def refuse_then_grok(url, hdrs, body):
    if "anthropic" in url: return {"id": "m", "model": "claude-opus-4-8", "stop_reason": "refusal", "content": [], "usage": {"input_tokens": 1, "output_tokens": 0}}
    return XAI_OK(body, hdrs)
r = asyncio.run(_router(refuse_then_grok))
check("router: refusal stage held, grok answers with its own model/usage", r["stages"][0]["status"] == "held" and r["provider"] == "xai"
      and r["model"] == "grok-4" and r["usage"]["total_tokens"] == 10 and r["route"] == "grok(refusal)", r)
r = asyncio.run(_router(lambda u, h, b: XAI_OK(b, h), surface="chat"))
check("router: grok(surface) result carries provider=xai", r["provider"] == "xai" and r["route"] == "grok(surface)", r)

print("--- 163: no resend after ambiguous timeout; idempotency key ---")
s, h, b = run(dict(BASE), anthropic=lambda b_, h_: socket.timeout("timed out"), xai=XAI_OK)
check("anthropic timeout -> sent exactly once, then grok", [c[0] for c in CALLS] == ["anthropic", "xai"], [c[0] for c in CALLS])
check("Idempotency-Key header sent to every provider, same key", len({c[2].get("idempotency-key") for c in CALLS}) == 1
      and CALLS[0][2]["idempotency-key"].startswith("vintos-") and h["x-vintos-idempotency-key"] == CALLS[0][2]["idempotency-key"], CALLS[0][2])
check("key is a hash of the request (stable, ignores route hint)", S.idempotency_key(BASE) == S.idempotency_key(dict(BASE, route="grok"))
      and S.idempotency_key(BASE) != S.idempotency_key(dict(BASE, max_tokens=501)))
call = S._Call(dict(BASE)); CALLS.clear(); S.urllib.request.urlopen = fake_urlopen({"anthropic": lambda b_, h_: socket.timeout("timed out")})
r1 = S.claude_complete(dict(BASE), call); r2 = S.claude_complete(dict(BASE), call)
check("timed-out stage recorded unavailable with 'not retried'", r1["status"] == "unavailable" and "not retried" in r1["reason"], r1)
check("second attempt on the same provider within the call is refused without sending", r2["status"] == "unavailable"
      and "already sent" in r2["reason"] and len(CALLS) == 1, (r2["reason"], len(CALLS)))
s, h, b = run(dict(BASE), anthropic=lambda b_, h_: socket.timeout("timed out"), xai=lambda b_, h_: socket.timeout("timed out"))
check("both time out -> 502 naming both as unavailable/timed out, each sent once",
      s == 502 and all(p["status"] == "unavailable" and "timed out" in p["reason"] for p in b["error"]["providers"]) and len(CALLS) == 2, (s, b))
async def slow_claude(url, hdrs, body):
    if "anthropic" in url: await asyncio.sleep(1.0); return {}
    return XAI_OK(body, hdrs)
r = asyncio.run(_router(slow_claude))
check("router: primary timeout -> stage unavailable 'not retried', anthropic posted once, grok answers",
      r["stages"][0]["status"] == "unavailable" and "not retried" in r["stages"][0]["reason"]
      and sum("anthropic" in p[0] for p in _FakeClient.posts) == 1 and r["provider"] == "xai" and r["route"].startswith("grok(primary timed out"), r)
check("router: Idempotency-Key on both provider posts", all(p[1].get("Idempotency-Key", "").startswith("vintos-") for p in _FakeClient.posts), _FakeClient.posts)

print("--- hygiene ---")
import compute_admission as CA
check("compute ledger is isolated in this suite", os.path.commonpath([os.path.realpath(CA._ledger()), os.path.realpath(TMP)]) == os.path.realpath(TMP))
check("provider clients are fakes", MR.httpx.AsyncClient is _FakeClient and S.urllib.request.urlopen.__name__ == "_open")
check("usage log went to the tempdir, not ~/.vintos", os.path.exists(os.path.join(TMP, "usage.jsonl")), TMP)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
