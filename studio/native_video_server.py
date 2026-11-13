#!/usr/bin/env python3
"""Explicitly started loopback video stream service; never downloads, stores frames or changes a route."""
import argparse
import base64
import io
import json
import queue
import threading
import time
import urllib.parse
import uuid
from http.server import ThreadingHTTPServer

import numpy as np

from native_apriltags import TagDetector
from native_audio_runtime import NativeMind
from native_audio_server import handler as audio_handler
from native_sensory_tap import SensoryTap
from native_video_runtime import RETAIN_FRAMES, SOFT_TOKENS, AppleStream, LiveSession

MAX_IMAGE_BYTES = 6 * 1024 * 1024   # base64 must fit the shared handler's 8 MB request limit
MAX_PIXELS = 4096 * 4096
IDLE_SECONDS = 30


def decode_image(data):
    """A JPEG or PNG frame, decoded in memory only."""
    raw = base64.b64decode(data, validate=True)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Frame exceeds the request budget")
    if not (raw.startswith(b"\xff\xd8") or raw.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("Expected a JPEG or PNG frame")
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Frame exceeds the pixel budget")
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def pcm16(data):
    raw = base64.b64decode(data, validate=True)
    if not raw or len(raw) % 2 or len(raw) > 8 * 16000 * 2:
        raise ValueError("Expected mono PCM16 at 16 kHz, at most eight seconds per packet")
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768


class VideoService:
    def __init__(self, mind, stream, tap=None, detector=None):
        self.mind, self.stream = mind, stream
        self.tap, self.detector = tap, detector
        self.lock = threading.Lock()
        self.active = None
        self.expires = 0
        self._timer = None
        # Every model call runs on this one thread: MLX state is per thread, while HTTP requests arrive on many.
        self._jobs = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="native-video-inference", daemon=True)
        self._worker.start()

    def _work(self):
        while True:
            job, done = self._jobs.get()
            try:
                done["result"] = job()
            except BaseException as exc:   # handed back to the request thread unchanged
                done["error"] = exc
            done["event"].set()

    def _on_worker(self, job):
        if threading.current_thread() is self._worker:
            return job()
        done = {"event": threading.Event()}
        self._jobs.put((job, done))
        done["event"].wait()
        if "error" in done:
            raise done["error"]
        return done["result"]

    def _drop(self):
        self.active = None
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _arm(self):
        self.expires = time.monotonic() + IDLE_SECONDS
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(IDLE_SECONDS + .05, self._reap)
        self._timer.daemon = True
        self._timer.start()

    def _reap(self):
        with self.lock:
            self._on_worker(self.expire)

    def expire(self):
        if self.active and time.monotonic() > self.expires:
            self.active[1].abort()
            self._drop()

    def close(self):
        with self.lock:
            if self.active:
                self._on_worker(self.active[1].abort)
            self._drop()

    def dispatch(self, path, body, on_text=None):
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError("Inference is busy")
        try:
            return self._on_worker(lambda: self._dispatch(path, body, on_text))
        finally:
            self.lock.release()

    def _dispatch(self, path, body, on_text=None):
        if True:   # body kept at its original indentation; runs on the inference thread under self.lock
            self.expire()
            if path == "/video/start":
                if self.active:
                    raise BlockingIOError("A stream is already active")
                on_embedding = None
                if self.tap is not None:
                    self.tap.start(body.get("feed") or "unknown")
                    to_numpy = getattr(self.stream, "numpy", np.asarray)
                    on_embedding = lambda kind, at, e, ref: self.tap.embedding(kind, at, to_numpy(e), ref)
                session = LiveSession(self.mind, self.stream, body.get("instruction"),
                                      int(body.get("retain_frames", RETAIN_FRAMES)), on_embedding=on_embedding)
                session_id = uuid.uuid4().hex
                self.active = (session_id, session)
                self._arm()
                return {"session_id": session_id, "soft_tokens_per_frame": SOFT_TOKENS,
                        "retain_frames": session.retain_frames, "audio_sample_rate": 16000}
            if not self.active or body.get("session_id") != self.active[0]:
                raise ValueError("Unknown or expired stream")
            session = self.active[1]
            at = body.get("at")
            at = None if at is None else float(at)
            if path == "/video/abort":
                session.abort(); self._drop()
                return {"ok": True}
            if path == "/video/frame":
                rgb = decode_image(body["image"])
                result = session.frame(rgb, at, int(body.get("soft_tokens", SOFT_TOKENS)))
                tags = []
                if self.detector is not None and self.detector.available:
                    started = time.perf_counter()
                    tags = self.detector.detect(rgb)
                    result["tag_seconds"] = time.perf_counter() - started
                    for tag in tags:
                        if self.tap is not None:
                            self.tap.tag(result["at"], tag, result["frame_ref"])
                result["tags"] = [{k: t[k] for k in ("tag_id", "family", "decision_margin", "center", "pose")} for t in tags]
            elif path == "/video/audio":
                result = session.audio(pcm16(body["audio"]), at)
            elif path == "/video/ask":
                result = session.ask(str(body["question"]), int(body.get("max_tokens", 128)),
                                     float(body.get("temperature", 0)), on_text)
            elif path == "/video/finish":
                window = session.window()
                session.abort(); self._drop()
                return {"ok": True, "window": window, "raw_frames_retained": False}
            else:
                raise KeyError("Unknown endpoint")
            self._arm()
            return dict(result, raw_frames_retained=False)


class _Health:
    """Adapter so the audio candidate's HTTP handler (stream emitter, error mapping, no logging) is reused."""
    def __init__(self, service):
        self.service = service
        self.mind = service.mind

    def dispatch(self, path, body, on_text=None):
        try:
            return self.service.dispatch(path, body)
        except (BlockingIOError, ValueError, TypeError, KeyError):
            raise
        except Exception as exc:
            # Unexpected faults are logged by type and code location only: never request bodies, frames or text.
            import sys
            import traceback
            frames = traceback.extract_tb(exc.__traceback__)
            sys.stderr.write("native video fault on %s: %s at %s\n" % (path, type(exc).__name__, " <- ".join(
                "%s:%d %s" % (f.filename.rsplit("/", 1)[-1], f.lineno, f.name) for f in reversed(frames[-6:]))))
            sys.stderr.flush()
            raise


def handler(service):
    base = audio_handler(_Health(service))

    class Handler(base):
        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path == "/tap" and service.tap is not None:
                query = urllib.parse.parse_qs(url.query)
                try:
                    since, limit = int(query.get("since", ["0"])[0]), int(query.get("limit", ["256"])[0])
                except ValueError:
                    return self.reply(400, {"error": "Invalid tap query"})
                return self.reply(200, service.tap.since(since, limit))
            if url.path != "/health":
                return self.reply(404, {"error": "Unknown endpoint"})
            self.reply(200, {"checkpoint_sha256": service.mind.sha, "native_video": True,
                             "soft_tokens_per_frame": SOFT_TOKENS, "retain_frames": RETAIN_FRAMES,
                             "shared_audio_timeline": True, "raw_frames_retained": False,
                             "sensory_tap": service.tap is not None,
                             "apriltags": bool(service.detector is not None and service.detector.available)})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mind", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--tap-events", type=int, default=4096, help="sensory tap ring size; 0 disables the tap")
    parser.add_argument("--tap-tokens", action="store_true", help="keep every soft token in the tap, not only the mean")
    parser.add_argument("--camera", type=float, nargs=4, metavar=("FX", "FY", "CX", "CY"), help="intrinsics for tag pose")
    parser.add_argument("--tag-size", type=float, help="printed tag edge in metres, for tag pose")
    args = parser.parse_args()
    if args.port in (8840, 8844) or not 1024 <= args.port <= 65535:
        raise ValueError("Choose an unreserved loopback port")
    mind = NativeMind(args.mind, args.expected_sha256, "apple")
    tap = SensoryTap(args.tap_events, keep_tokens=args.tap_tokens) if args.tap_events else None
    detector = TagDetector(intrinsics=args.camera, tag_size=args.tag_size)
    service = VideoService(mind, AppleStream(mind.backend), tap, detector)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(service))
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        service.close()
        server.server_close()


if __name__ == "__main__":
    main()
