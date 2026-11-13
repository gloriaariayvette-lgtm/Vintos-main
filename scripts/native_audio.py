"""Opt-in local waveform route. A missing or failed route never selects another provider."""
import base64
import hashlib
import json
import os
import urllib.parse
import urllib.request

ANCHOR_SHA256 = "989526926b49de244b87dc69ce23949652062a699925c9bdf9dc249116c4079d"


def base_url():
    raw = os.environ.get("VINTOS_NATIVE_AUDIO_BASE", "").rstrip("/")
    if not raw:
        return ""
    url = urllib.parse.urlsplit(raw)
    if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.username or url.password or url.path or url.query or url.fragment
            or not url.port or url.port == 8840):
        raise ValueError("Native audio requires its own explicit loopback URL; use a private SSH tunnel between hosts")
    return raw


def enabled():
    return bool(base_url())


def verify():
    base = base_url()
    if not base:
        raise RuntimeError("Native audio is not configured")
    # Do not inherit HTTP proxy configuration for private audio.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base + "/health", timeout=5) as response:
        receipt = json.load(response)
    if (receipt.get("checkpoint_sha256") != ANCHOR_SHA256 or receipt.get("native_audio") is not True
            or receipt.get("max_audio_seconds") != 8 or receipt.get("raw_audio_retained") is not False):
        raise RuntimeError("Native audio service does not match the frozen local checkpoint contract")
    return base


def require_stage(base):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base.rstrip("/") + "/health", timeout=5) as response:
        receipt = json.load(response)
    if receipt.get("external_ears") is not True:
        raise RuntimeError("Voice stage must support external ears before native audio is enabled")


def content(audio_b64, sample_rate):
    rate = int(sample_rate or 24000)
    raw = base64.b64decode(audio_b64, validate=True)
    if rate not in (16000, 24000, 48000) or not raw or len(raw) % 2 or len(raw) > 8 * rate * 2:
        raise ValueError("Native audio accepts at most eight seconds of mono PCM16 at 16, 24 or 48 kHz")
    return [{"type": "text", "text": "Reply to the recording itself. Its transcript in the turn record is only an index."},
            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "pcm16", "sample_rate": rate}}]


def hear(audio_b64, sample_rate, post):
    parts = content(audio_b64, sample_rate)
    audio = parts[1]["input_audio"]
    raw, _ = post(verify() + "/listen", {"audio": audio["data"], "sample_rate": audio["sample_rate"]}, 180)
    heard = json.loads(raw)
    if heard.get("checkpoint_sha256") != ANCHOR_SHA256 or heard.get("native_audio") is not True:
        raise RuntimeError("Audio response came from an unverified checkpoint")
    # The reference identifies captured bytes, not a claim that all their details were stored.
    heard["capture_ref"] = "sha256:" + hashlib.sha256(base64.b64decode(audio_b64)).hexdigest()
    heard["record_gap"] = "The short transcript does not capture every audible detail. A missing detail is not captured."
    return heard


class Stream:
    """One canonical 16 kHz PCM stream, capped at eight seconds. No recording is stored."""
    def __init__(self, prompt=None, post=None):
        self.base = verify()
        self.closed = False
        self.samples = 0
        self._send = post or self._post
        result = self._send(self.base + "/audio/start", {"prompt": prompt} if prompt else {})
        self.session_id = result["session_id"]

    @staticmethod
    def _post(url, body):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with opener.open(request, timeout=180) as response:
            return json.load(response)

    def push(self, pcm):
        if self.closed or not pcm or len(pcm) % 2 or self.samples + len(pcm) // 2 > 128000:
            raise ValueError("Closed stream, invalid PCM16 chunk or eight-second budget exceeded")
        result = self._send(self.base + "/audio/push", {"session_id": self.session_id,
                            "audio": base64.b64encode(pcm).decode()})
        self.samples += len(pcm) // 2
        return result

    def finish(self):
        if self.closed:
            raise ValueError("Stream already closed")
        try:
            result = self._send(self.base + "/audio/finish", {"session_id": self.session_id})
            if result.get("checkpoint_sha256") != ANCHOR_SHA256 or result.get("native_audio") is not True:
                raise RuntimeError("Stream result came from an unverified checkpoint")
        except Exception:
            try:
                self.abort()
            except Exception:
                pass  # The bounded server session also expires if the connection is lost.
            raise
        self.closed = True
        return result

    def abort(self):
        if not self.closed:
            self.closed = True
            self._send(self.base + "/audio/abort", {"session_id": self.session_id})
