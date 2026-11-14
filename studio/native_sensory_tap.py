"""A bounded sensory tap for a JEPA/Mamba-style consumer: timestamped embeddings from the live stream, taken
where the mind's own encoders hand them to the language model (after the native vision/audio projection,
before any LLM layer), plus AprilTag events. Memory only: a ring bounded by event count and bytes; nothing is
written to disk, and the service exposes it over its loopback port only.

Event schema (version 1), one JSON object per event:
    seq       monotonically increasing integer (resume with ?since=seq)
    t         unix seconds when the event entered the mind
    dt        seconds since the previous event on this tap (event-driven: a quiet scene is a long dt)
    stream    opaque id of the live session (a fresh one per /video/start)
    feed      source label given by the client (e.g. "xiao-cam", "door", "replay")
    kind      "frame" | "audio" | "tag"
    at        seconds on the stream clock (the shared audio/video timeline)
    space     the vector space, never mixed raw with another: "aeon-12b/vision-proj" or "aeon-12b/audio-proj"
    dim       vector width (3840 for both spaces of this checkpoint)
    tokens    how many soft tokens were pooled into the vector
    vector    base64 of little-endian float16, length dim: mean of the soft tokens (frame/audio only)
    tokens_b64  optional, float16 [tokens x dim], only when the tap was started with keep_tokens
    ref       frame_ref / audio_ref (sha256 of what entered; the media itself is never kept)
    tag_id, family, decision_margin, center, corners, pose (tag events; pose is null without camera intrinsics)
"""
import base64
import collections
import threading
import time
import uuid

import numpy as np

SCHEMA_VERSION = 1


def _b64(x):
    return base64.b64encode(np.ascontiguousarray(np.asarray(x, dtype="<f2")).tobytes()).decode()


class SensoryTap:
    def __init__(self, max_events=4096, max_bytes=64 << 20, keep_tokens=False, clock=time.time):
        if not 1 <= max_events <= 1 << 20 or not 1 << 16 <= max_bytes <= 1 << 30:
            raise ValueError("Invalid tap bounds")
        self.max_events, self.max_bytes, self.keep_tokens, self.clock = max_events, max_bytes, keep_tokens, clock
        self.events = collections.deque()
        self.bytes = 0
        self.seq = 0
        self.last_t = None
        self.dropped = 0
        self.lock = threading.Lock()
        self.stream = None
        self.feed = "unknown"

    def start(self, feed="unknown"):
        self.stream = uuid.uuid4().hex[:12]
        self.feed = str(feed)[:40]
        return self.stream

    def _push(self, event):
        size = sum(len(v) for v in event.values() if isinstance(v, str)) + 256
        with self.lock:
            now = self.clock()
            self.seq += 1
            event.update(v=SCHEMA_VERSION, seq=self.seq, t=round(now, 4),
                         dt=None if self.last_t is None else round(now - self.last_t, 4),
                         stream=self.stream, feed=self.feed)
            self.last_t = now
            self.events.append((event, size))
            self.bytes += size
            while len(self.events) > self.max_events or self.bytes > self.max_bytes:
                _, s = self.events.popleft()
                self.bytes -= s
                self.dropped += 1
        return event["seq"]

    def embedding(self, kind, at, embeds, ref=None):
        """``embeds`` is [1, tokens, dim] (or [tokens, dim]) as handed to the language model."""
        x = np.asarray(embeds, dtype=np.float32).reshape(-1, np.asarray(embeds).shape[-1])
        event = {"kind": kind, "at": round(float(at), 3), "space": "aeon-12b/%s-proj" % ("vision" if kind == "frame" else "audio"),
                 "dim": int(x.shape[1]), "tokens": int(x.shape[0]), "vector": _b64(x.mean(axis=0)), "ref": ref}
        if self.keep_tokens:
            event["tokens_b64"] = _b64(x)
        return self._push(event)

    def tag(self, at, detection, ref=None):
        return self._push(dict(detection, kind="tag", at=round(float(at), 3), ref=ref))

    def since(self, seq=0, limit=256):
        with self.lock:
            out = [e for e, _ in self.events if e["seq"] > seq][:max(1, min(int(limit), 1024))]
            return {"v": SCHEMA_VERSION, "events": out, "next": out[-1]["seq"] if out else seq,
                    "oldest": self.events[0][0]["seq"] if self.events else None, "dropped": self.dropped}

    def clear(self):
        with self.lock:
            self.events.clear(); self.bytes = 0


def decode_vector(event, key="vector"):
    """Consumer helper: the float16 vector(s) of one event as float32."""
    raw = np.frombuffer(base64.b64decode(event[key]), dtype="<f2").astype(np.float32)
    return raw.reshape(-1, event["dim"]) if key == "tokens_b64" else raw
