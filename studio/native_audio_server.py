#!/usr/bin/env python3
"""Explicitly started loopback audio service; never downloads or changes a route."""
import argparse
import base64
import hashlib
import io
import json
import math
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from native_audio_runtime import MARKER, MAX_SAMPLES, NativeMind


def waveform(data, sample_rate=16000, audio_format="pcm16"):
    raw = base64.b64decode(data, validate=True)
    if audio_format == "pcm16":
        if sample_rate not in (16000, 24000, 48000) or len(raw) % 2:
            raise ValueError("Expected mono PCM16 at 16, 24 or 48 kHz")
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    elif audio_format == "wav":
        import soundfile as sf
        with sf.SoundFile(io.BytesIO(raw)) as f:
            if f.channels != 1 or f.samplerate not in (16000, 24000, 48000) or f.frames > 8 * f.samplerate:
                raise ValueError("Expected a mono WAV of at most eight seconds")
            x = f.read(dtype="float32"); sample_rate = f.samplerate
    else:
        raise ValueError("Unsupported audio format")
    if not 0 < len(x) <= 8 * sample_rate or not np.isfinite(x).all() or np.max(np.abs(x)) > 1:
        raise ValueError("Invalid waveform or eight-second budget exceeded")
    if sample_rate != 16000:
        from scipy.signal import resample_poly
        divisor = math.gcd(sample_rate, 16000)
        x = resample_poly(x, 16000 // divisor, sample_rate // divisor).astype(np.float32)
        x = np.clip(x, -1, 1)
    if len(x) > MAX_SAMPLES:
        raise ValueError("Resampled audio exceeds the window budget")
    return x


class Service:
    def __init__(self, mind):
        self.mind = mind
        self.lock = threading.Lock()
        self.active = None
        self.expires = 0
        self._expiry_timer = None

    def _drop(self):
        self.active = None
        if self._expiry_timer:
            self._expiry_timer.cancel()
            self._expiry_timer = None

    def _arm_expiry(self):
        if self._expiry_timer:
            self._expiry_timer.cancel()
        self._expiry_timer = threading.Timer(max(.01, self.expires - time.monotonic()), self._reap)
        self._expiry_timer.daemon = True
        self._expiry_timer.start()

    def _reap(self):
        with self.lock:
            self.expire()
            if self.active:
                self._arm_expiry()

    def close(self):
        with self.lock:
            if self.active:
                self.active[1].abort()
            self._drop()

    def expire(self):
        if self.active and time.monotonic() > self.expires:
            self.active[1].abort()
            self._drop()

    def dispatch(self, path, body, on_text=None):
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError("Inference is busy")
        try:
            self.expire()
            if path == "/audio/start":
                if self.active:
                    raise BlockingIOError("A stream is already active")
                session = self.mind.session(self.messages(body), int(body.get("max_tokens", 128)),
                                            float(body.get("temperature", 0)))
                session_id = uuid.uuid4().hex
                self.active = (session_id, session, hashlib.sha256())
                self.expires = time.monotonic() + 30
                self._arm_expiry()
                return {"session_id": session_id, "sample_rate": 16000, "max_audio_seconds": 8}
            if path in ("/audio/push", "/audio/finish", "/audio/abort"):
                if not self.active or body.get("session_id") != self.active[0]:
                    raise ValueError("Unknown or expired stream")
                _, session, digest = self.active
                if path == "/audio/abort":
                    session.abort(); self._drop()
                    return {"ok": True}
                if path == "/audio/push":
                    # Stream chunks use one canonical rate; no per-chunk resampling artifacts.
                    x = waveform(body["audio"], 16000)
                    result = session.push(x)
                    digest.update(x.tobytes())
                    self.expires = time.monotonic() + 30
                    return result
                try:
                    return dict(session.finish(), audio_ref="sha256:" + digest.hexdigest(), raw_audio_retained=False)
                finally:
                    session.abort(); self._drop()
            if path not in ("/listen", "/v1/chat/completions"):
                raise KeyError("Unknown endpoint")
            if self.active:
                raise BlockingIOError("A stream is active")
            if path == "/listen":
                x = waveform(body["audio"], int(body.get("sample_rate", 24000)), body.get("format", "pcm16"))
                messages = self.messages({})
            else:
                messages = []
                x = None
                for message in body["messages"]:
                    content = message["content"]
                    if isinstance(content, list):
                        parts = []
                        for part in content:
                            if part.get("type") == "text":
                                parts.append(part["text"])
                            elif part.get("type") == "input_audio" and x is None:
                                audio = part["input_audio"]
                                x = waveform(audio["data"], int(audio.get("sample_rate", 16000)), audio["format"])
                                parts.append("<|audio>" + MARKER + "<audio|>")
                            else:
                                raise ValueError("Exactly one audio part and text parts are supported")
                        content = " ".join(parts)
                    messages.append({"role": message["role"], "content": content})
            session = self.mind.session(messages, int(body.get("max_tokens", 128)), float(body.get("temperature", 0)))
            try:
                # Exercise the same cache path for complete recordings and live chunks.
                if x is not None:
                    for i in range(0, len(x), 3200):
                        session.push(x[i:i + 3200])
                result = session.finish(on_text=on_text)
            finally:
                session.abort()
            result.update(audio_ref="sha256:" + hashlib.sha256(x.tobytes()).hexdigest() if x is not None else None,
                          raw_audio_retained=False)
            if path == "/listen":
                return dict(result, ok=True, transcript=result["text"], audio_reading=None,
                            ears="native-waveform", audio_native_gemma=True)
            return {"id": uuid.uuid4().hex, "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": result["text"]},
                                 "finish_reason": result["finish_reason"]}], "perception": result}
        finally:
            self.lock.release()

    @staticmethod
    def messages(body):
        prompt = str(body.get("prompt") or "Transcribe the following audio verbatim. Output only the words spoken.")
        if MARKER in prompt:
            raise ValueError("Reserved audio placeholder")
        return [{"role": "user", "content": prompt + " <|audio>" + MARKER + "<audio|>"}]


def handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log private request contents or generated words.

        def reply(self, code, data):
            raw = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers(); self.wfile.write(raw)

        def do_GET(self):
            if self.path != "/health":
                return self.reply(404, {"error": "Unknown endpoint"})
            self.reply(200, {"checkpoint_sha256": service.mind.sha, "native_audio": True,
                             "audio_tokens_per_second": 25, "max_audio_seconds": 8,
                             "raw_audio_retained": False})

        def do_POST(self):
            self.connection.settimeout(15)
            streaming = False
            sent = ""
            def emit(text, final=False):
                nonlocal streaming, sent
                # Hold the unfinished word so tokenizer whitespace cleanup cannot change sent text.
                stable = text if final else text[:max(text.rfind(" "), text.rfind("\n")) + 1]
                if not stable.startswith(sent) or len(stable) <= len(sent):
                    return
                if not streaming:
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                    self.end_headers(); streaming = True
                chunk = {"choices": [{"delta": {"content": stable[len(sent):]}, "index": 0}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode()); self.wfile.flush()
                sent = stable
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2 * 1024 * 1024:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected a request object")
                wants_stream = bool(body.get("stream")) and self.path == "/v1/chat/completions"
                result = service.dispatch(self.path, body, emit if wants_stream else None)
            except Exception as exc:
                if streaming:
                    self.wfile.write(b'data: {"error":"Native inference failed"}\n\ndata: [DONE]\n\n')
                    return
                if isinstance(exc, BlockingIOError):
                    return self.reply(409, {"error": "Audio inference is busy"})
                if isinstance(exc, (ValueError, TypeError, KeyError)):
                    return self.reply(400, {"error": "Invalid audio request"})
                return self.reply(500, {"error": "Native inference failed; no fallback was used"})
            if wants_stream:
                emit(result["choices"][0]["message"]["content"], final=True)
                if not streaming:
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                finish = result['choices'][0]['finish_reason']
                self.wfile.write(('data: ' + json.dumps({'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}) + '\n\ndata: [DONE]\n\n').encode())
            else:
                self.reply(200, result)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mind", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--backend", choices=["torch", "apple"], required=True)
    parser.add_argument("--port", type=int, default=8844)
    args = parser.parse_args()
    if args.port == 8840 or not 1024 <= args.port <= 65535:
        raise ValueError("Choose an unreserved loopback port")
    mind = NativeMind(args.mind, args.expected_sha256, args.backend)
    service = Service(mind)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(service))
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        service.close()
        server.server_close()


if __name__ == "__main__":
    main()
