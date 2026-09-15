#!/usr/bin/env python3
"""voice_local.py — the local call gives the recording itself to native audio understanding.

The Mac hears and voices.  Aegis supplies Vintos's context and calls his local
abliterated brain. A failed component is a typed failed turn; this lane never
silently substitutes a transcript-only path and never leaks into a hosted provider.
"""
from __future__ import annotations

import base64, json, os, urllib.error, urllib.request

STAGE = os.environ.get("VINTOS_MAC_STAGE", "http://100.79.177.103:8511").rstrip("/")
LM = os.environ.get("VINTOS_MAC_LM_BASE_REMOTE", "http://100.79.177.103:1234").rstrip("/")
BRAIN = os.environ.get("VINTOS_LOCAL_BRAIN", "gemma-4-26b-a4b-it-uncensored")


def _post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        raise RuntimeError("%s: %s" % (exc.code, exc.read().decode(errors="replace")[:300]))


def models(active):
    raw, _ = _post(STAGE + "/voice/models", {"active": bool(active)}, 100)
    return json.loads(raw)


def turn(audio_b64, sample_rate, instructions, framing=""):
    heard_raw, _ = _post(STAGE + "/listen", {"audio": audio_b64,
        "sample_rate": int(sample_rate or 24000)}, 180)
    heard = json.loads(heard_raw)
    if not heard.get("ok") or not heard.get("transcript"):
        return {"ok":False,"stage":"ears","error":heard.get("error","no words heard"),"hearing":heard}
    evidence = {"reading":heard.get("audio_reading"), "pipeline":heard.get("ears"),
                "audio_native_gemma":bool(heard.get("audio_native_gemma"))}
    user = ("Gloria said aloud:\n" + heard["transcript"] +
            "\n\n[AUDIO-NATIVE READING — Gemma 3n received the recording itself:]\n" +
            json.dumps(evidence, ensure_ascii=False))
    system = str(instructions or "")
    if framing: system += "\n\nLIVE RIGHT NOW (this replaces earlier LIVE blocks):\n" + str(framing)
    brain_raw, _ = _post(LM + "/v1/chat/completions", {"model":BRAIN,
        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
        "temperature":.85,"max_tokens":360}, 180)
    brain = json.loads(brain_raw); reply = ((brain.get("choices") or [{}])[0].get("message") or {}).get("content","").strip()
    if not reply: return {"ok":False,"stage":"brain","error":"local brain returned no words","hearing":heard}
    voice_raw, headers = _post(STAGE + "/tts", {"text":reply}, 210)
    if not voice_raw.startswith(b"RIFF"):
        return {"ok":False,"stage":"voice","error":"voice returned no WAV","reply":reply,"hearing":heard}
    return {"ok":True,"transcript":heard["transcript"],
            "audio_reading":heard.get("audio_reading"),"reply":reply,
            "audio":base64.b64encode(voice_raw).decode(),"audio_format":"wav",
            "voice_engine":headers.get("X-Vintos-Voice","unknown"),"model":BRAIN}
