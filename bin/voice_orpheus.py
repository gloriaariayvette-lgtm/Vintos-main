#!/usr/bin/env python3
"""voice_orpheus.py — one expressive local voice, with an honest outage fallback.

Orpheus produces SNAC codes rather than audio.  On the Mac this module asks the
local LM Studio model for those codes and decodes them to a 24 kHz WAV.  On
Aegis it asks the Mac stage for that WAV.  A failed Orpheus path never leaves
him mute: callers may fall back to the existing Kokoro implementation, and the
returned receipt names which voice actually spoke.
"""
from __future__ import annotations

import base64, json, os, re, tempfile, urllib.error, urllib.request, wave

LM_BASE = os.environ.get("VINTOS_MAC_LM_BASE", "http://127.0.0.1:1234").rstrip("/")
STAGE_BASE = os.environ.get("VINTOS_MAC_STAGE", "http://100.79.177.103:8511").rstrip("/")
MODEL = os.environ.get("VINTOS_ORPHEUS_MODEL", "orpheus-3b-ft.gguf")
VOICE = os.environ.get("VINTOS_ORPHEUS_VOICE", "dan")
SAMPLE_RATE = 24000
_TOKEN = re.compile(r"<custom_token_(\d+)>")
_SNAC = None
_CUES = "giggle|laugh|chuckle|sigh|cough|sniffle|groan|yawn|gasp"


def display_text(text):
    """What Gloria reads: words only, never synthesis markup or stage prose."""
    out = str(text or "")
    out = re.sub(r"\[[^\]\n]{1,240}\]", " ", out)
    out = re.sub(r"</?[A-Za-z][^>\n]{0,80}>", " ", out)
    out = re.sub(r"\*+", "", out)
    return " ".join(out.split())

def spoken_text(text):
    """Give Orpheus only its eight real cues; never ask it to read stage prose."""
    out = str(text or "")
    out = re.sub(r"\[(%s)\]" % _CUES, lambda m: "<%s>" % m.group(1).lower(), out, flags=re.I)
    # A bracketed aside such as "[A soft, low laugh]" is prose, not an
    # Orpheus control token.  It used to be displayed and literally spoken.
    out = re.sub(r"\[[^\]\n]{1,240}\]", " ", out)
    # Orpheus does not implement whisper/pause/emphasis. Keep the enclosed
    # words, remove every non-cue tag, and preserve only its documented cues.
    out = re.sub(r"</(?:%s)\s*>" % _CUES, " ", out, flags=re.I)
    out = re.sub(r"</?(?!%s\b)[A-Za-z][^>\n]{0,80}>" % _CUES, " ", out, flags=re.I)
    out = re.sub(r"\*+", "", out)
    return " ".join(out.split())


def _post(url, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", "")


def _codes(text):
    """Turn Orpheus's seven interleaved custom-token streams into SNAC codes."""
    values = []
    for raw in _TOKEN.findall(text or ""):
        i = len(values); value = int(raw) - 10 - ((i % 7) * 4096)
        # BOS/control tokens (4, 5, 1) precede the first audio frame.  They do
        # not advance the seven-code interleave; the reference decoder skips
        # them for exactly that reason.
        if 0 < value < 4096: values.append(value)
    values = values[:len(values) - (len(values) % 7)]
    if len(values) < 7:
        raise ValueError("Orpheus returned no complete SNAC frame")
    c0, c1, c2 = [], [], []
    for i in range(0, len(values), 7):
        f = values[i:i + 7]; c0.append(f[0]); c1.extend((f[1], f[4])); c2.extend((f[2], f[3], f[5], f[6]))
    return c0, c1, c2


def _decode(text, out_path):
    global _SNAC
    import numpy as np, torch
    from snac import SNAC
    c0, c1, c2 = _codes(text)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if _SNAC is None:
        _SNAC = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to(device)
    codes = [torch.tensor([c], dtype=torch.int32, device=device) for c in (c0, c1, c2)]
    with torch.inference_mode(): audio = _SNAC.decode(codes).detach().cpu().numpy().reshape(-1)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16).tobytes()
    with wave.open(out_path, "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(SAMPLE_RATE); stream.writeframes(pcm)
    return out_path


def synthesize_local(text, out_path, voice=None, speed=None):
    """Mac path: LM Studio Orpheus → SNAC decode → WAV."""
    voice = (voice or VOICE).strip().lower()
    prompt = "<|audio|>%s: %s<|eot_id|>" % (voice, spoken_text(text)[:5000])
    raw, _ = _post(LM_BASE + "/v1/completions", {"model": MODEL, "prompt": prompt,
        "max_tokens": 4096, "temperature": 0.6, "top_p": 0.9,
        "repeat_penalty": 1.1, "stream": False}, timeout=180)
    data = json.loads(raw); generated = (data.get("choices") or [{}])[0].get("text", "")
    return _decode(generated, out_path)


def synthesize_remote(text, out_path, voice=None, speed=None):
    """House path: request the Mac's decoded WAV and keep the bytes locally."""
    raw, ctype = _post(STAGE_BASE + "/tts", {"text": str(text)[:5000],
        "voice": voice or VOICE, "speed": speed or 1.0}, timeout=210)
    if "audio" not in ctype or not raw.startswith(b"RIFF"):
        raise RuntimeError("Mac voice returned no WAV")
    with open(out_path, "wb") as stream: stream.write(raw)
    return out_path


def speak_to_file(text, out_path=None, voice=None, speed=None, local_decode=False, fallback=True):
    """Return a receipt; `engine` is never inferred from a successful file write."""
    if not str(text or "").strip(): return {"ok": False, "engine": "none", "error": "empty text"}
    if not out_path:
        fd, out_path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        fn = synthesize_local if local_decode else synthesize_remote
        fn(text, out_path, voice, speed)
        return {"ok": True, "engine": "orpheus", "voice": voice or VOICE, "path": out_path}
    except Exception as exc:
        if not fallback:
            return {"ok": False, "engine": "orpheus", "error": str(exc)[:240], "path": out_path}
        try:
            import voice_kokoro
            if hasattr(voice_kokoro, "render_to_file") and voice_kokoro.render_to_file(text, out_path, speed=speed):
                return {"ok": True, "engine": "kokoro_fallback", "voice": voice_kokoro.VOICE_MODEL,
                        "path": out_path, "orpheus_error": str(exc)[:200]}
        except Exception as fallback_exc:
            return {"ok": False, "engine": "none", "error": str(exc)[:160], "fallback_error": str(fallback_exc)[:160]}
        return {"ok": False, "engine": "none", "error": str(exc)[:240]}


def speak(text, voice=None, speed=None):
    receipt = speak_to_file(text, voice=voice, speed=speed)
    if not receipt.get("ok"): return False
    try:
        import subprocess
        subprocess.run(["aplay", receipt["path"]], check=False, capture_output=True)
        return True
    except Exception: return False
