#!/usr/bin/env python3
"""astra_call.py — Astra, for the one job she is spent on outside review.

She is the review lens (gpt-6-astra, direct to OpenAI). Gloria, 11 September: she also
writes the Blender script for a print, because that is code and the local model cannot
write it. Ten minutes of her a day, counted by the caller that spends her.

This module is the call and nothing else. It holds no budget of its own — the budget
lives with the capability that spends it, so there is one place to look and one place
to change it.

    call(system, messages, max_tokens=1800) -> text
"""
import json
import os
import sys

MODEL = "gpt-6-astra"
ENDPOINT = "https://api.openai.com/v1/responses"
ENV_FILE = os.path.expanduser("~/.vintos/vintos.env")


def _key():
    k = os.environ.get("OPENAI_API_KEY", "")
    if k:
        return k
    try:
        for line in open(ENV_FILE):
            if line.strip().startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def call(system, messages, max_tokens=1800, timeout=180):
    """One synchronous turn. Raises on anything that is not an answer, so the caller
    records the seconds and reports the failure rather than inventing a result."""
    key = _key()
    if not key:
        raise RuntimeError("no OpenAI key (OPENAI_API_KEY in ~/.vintos/vintos.env)")
    import urllib.request
    text_in = "\n\n".join(str(m.get("content", "")) for m in (messages or [])
                          if isinstance(m, dict))
    body = {"model": MODEL, "input": [{"role": "system", "content": str(system or "")},
                                      {"role": "user", "content": text_in}],
            "max_output_tokens": int(max_tokens)}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    if d.get("status") not in (None, "completed"):
        raise RuntimeError("Astra %s: %s" % (d.get("status"), json.dumps(d.get("error") or {})[:200]))
    text = d.get("output_text") or ""
    if not text:
        text = "".join(c.get("text", "") for it in d.get("output", []) if it.get("type") == "message"
                       for c in it.get("content", []) if c.get("type") == "output_text")
    if not text.strip():
        raise RuntimeError("Astra answered with nothing")
    return text


if __name__ == "__main__":
    print("model:  %s" % MODEL)
    print("key:    %s" % ("present" if _key() else "missing"))
    print("budget: held by whatever spends her; printing allows ten minutes a day")
