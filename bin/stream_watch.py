#!/usr/bin/env python3
"""stream_watch.py - start his live scene while he is still writing.

His tags come first in a reply, and a reply takes 60-120s to finish. Waiting
for the whole thing before reading [RENDER: ...] wastes most of that. This
module wraps model_router's two model calls with STREAMING versions that watch
the arriving text; the moment a [RENDER: ...] tag closes, the callback in
EARLY fires (avatar_stage.start_live) and the render overlaps the rest of his
writing. The returned reply is byte-identical to the non-streaming path.

Only active where EARLY is set (the avatar handler sets it per request via a
contextvar); every other caller of the router gets the original functions.
Any streaming failure falls back to the original call.
"""
import json, re, contextvars, httpx

EARLY = contextvars.ContextVar("vintos_early_tag", default=None)
_RE = re.compile(r"\[RENDER:\s*([^\]]+)\]", re.I)


class _Watch:
    def __init__(self):
        self.buf, self.fired = "", False

    def feed(self, t):
        if not t:
            return
        self.buf += t
        if self.fired:
            return
        m = _RE.search(self.buf)
        if m:
            self.fired = True
            cb = EARLY.get()
            if cb:
                try:
                    cb(m.group(1).strip())
                except Exception as e:
                    print("[stream-watch] early tag callback failed:", e, flush=True)


async def grok_stream(convo, params, endpoint, headers, model, system_text, fallback):
    if EARLY.get() is None:
        return await fallback(convo, params, endpoint, headers, model, system_text)
    body = {"model": model, "messages": [{"role": "system", "content": system_text}] + convo,
            "max_tokens": params.get("max_tokens", 400),
            "temperature": params.get("temperature", 0.85),
            "top_p": params.get("top_p", 0.95),
            "route": "grok", "stream": True}
    w = _Watch()
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            async with c.stream("POST", endpoint, headers=headers, json=body) as r:
                if "text/event-stream" not in r.headers.get("content-type", ""):
                    d = json.loads(await r.aread())
                    text = d["choices"][0]["message"]["content"]
                    w.feed(text)
                    return text
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        d = json.loads(data)
                    except Exception:
                        continue
                    ch = (d.get("choices") or [{}])[0]
                    w.feed((ch.get("delta") or {}).get("content") or "")
        if not w.buf:
            raise RuntimeError("empty stream")
        return w.buf
    except Exception as e:
        print("[stream-watch] grok stream fell back:", e, flush=True)
        return await fallback(convo, params, endpoint, headers, model, system_text)


async def claude_stream(mr, system_text, convo, params, reason, fallback):
    if EARLY.get() is None:
        return await fallback(system_text, convo, params, reason)
    key = mr._anthropic_key()
    if not key:
        raise RuntimeError("no anthropic key")
    if reason:
        thinking = {"type": "adaptive", "display": "summarized"}
        max_tok = max(int(params.get("max_tokens", 400)), 1200)
    else:
        thinking = {"type": "disabled"}
        max_tok = max(int(params.get("max_tokens", 400)), 128)
    body = {"model": mr.current_claude_model(), "max_tokens": max_tok,
            "system": mr._sysblocks(system_text),
            "messages": mr._cachetail(convo), "thinking": thinking, "stream": True}
    w, think, refusal, errored = _Watch(), [], False, False
    try:
        async with httpx.AsyncClient(timeout=240) as c:
            async with c.stream("POST", "https://api.anthropic.com/v1/messages", json=body,
                                headers={"content-type": "application/json",
                                         "anthropic-version": "2023-06-01",
                                         "anthropic-beta": "extended-cache-ttl-2025-04-11",
                                         "x-api-key": key}) as r:
                if r.status_code != 200:
                    raise RuntimeError("HTTP %s: %s" % (r.status_code, (await r.aread())[:200]))
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        d = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    t = d.get("type")
                    if t == "content_block_delta":
                        delta = d.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            w.feed(delta.get("text") or "")
                        elif delta.get("type") == "thinking_delta":
                            think.append(delta.get("thinking") or "")
                    elif t == "message_delta":
                        if (d.get("delta") or {}).get("stop_reason") == "refusal":
                            refusal = True
                    elif t == "error":
                        errored = True
                        break
        if errored:
            raise RuntimeError("stream error event")
        if refusal:
            return None, ""
        return (w.buf or None), "".join(think)
    except Exception as e:
        print("[stream-watch] claude stream fell back:", e, flush=True)
        return await fallback(system_text, convo, params, reason)


def install(mr):
    """Wrap model_router's _grok/_claude once. route_reply looks them up by
    module attribute, so the wrappers take effect without editing the router."""
    if getattr(mr, "_stream_watch_installed", False):
        return
    g, c = mr._grok, mr._claude

    async def _g(convo, params, endpoint, headers, model, system_text):
        return await grok_stream(convo, params, endpoint, headers, model, system_text, g)

    async def _c(system_text, convo, params, reason):
        return await claude_stream(mr, system_text, convo, params, reason, c)

    mr._grok, mr._claude, mr._stream_watch_installed = _g, _c, True
