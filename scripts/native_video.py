"""Opt-in live video route into the frozen mind's own visual path. A missing or failed route never selects
another provider. Frames are sampled adaptively under a token budget, sent over an explicit loopback service,
and never written anywhere; what reaches his turn is the frames themselves plus a short provenance record."""
import base64
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

ANCHOR_SHA256 = "989526926b49de244b87dc69ce23949652062a699925c9bdf9dc249116c4079d"
FRAME_TOKENS = 72            # 64 native soft tokens for a typical frame plus its timestamp and boundaries


def base_url():
    raw = os.environ.get("VINTOS_NATIVE_VIDEO_BASE", "").rstrip("/")
    if not raw:
        return ""
    url = urllib.parse.urlsplit(raw)
    if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.username or url.password or url.path or url.query or url.fragment
            or not url.port or url.port in (8840, 8844)):
        raise ValueError("Native video requires its own explicit loopback URL; use a private SSH tunnel between hosts")
    return raw


def enabled():
    return bool(base_url())


def _opener():
    # Never inherit HTTP proxy configuration for private frames.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def verify():
    base = base_url()
    if not base:
        raise RuntimeError("Native video is not configured")
    with _opener().open(base + "/health", timeout=5) as response:
        receipt = json.load(response)
    if (receipt.get("checkpoint_sha256") != ANCHOR_SHA256 or receipt.get("native_video") is not True
            or receipt.get("raw_frames_retained") is not False or receipt.get("shared_audio_timeline") is not True):
        raise RuntimeError("Native video service does not match the frozen local checkpoint contract")
    return base


def _small_gray(rgb):
    """32x32 mean-pooled luminance of an RGB uint8 array, for change detection only."""
    import numpy as np
    x = np.asarray(rgb, dtype=np.float32)
    g = x[..., 0] * .299 + x[..., 1] * .587 + x[..., 2] * .114
    h, w = g.shape
    ys = (np.arange(33) * h) // 32
    xs = (np.arange(33) * w) // 32
    return np.array([[g[ys[i]:max(ys[i + 1], ys[i] + 1), xs[j]:max(xs[j + 1], xs[j] + 1)].mean()
                      for j in range(32)] for i in range(32)], dtype=np.float32)


class AdaptiveSampler:
    """Low rate when the scene is still, bursts on change, never over the token budget per second.

    A frame is sent when the idle interval has passed (a heartbeat at ``idle_fps``) or when it differs from the
    last sent frame by ``change`` (mean absolute luminance difference, 0..1) and the burst interval has passed.
    Both need tokens in a bucket refilled at ``tokens_per_second`` (capacity two seconds' worth)."""

    def __init__(self, idle_fps=.5, burst_fps=2., change=.04, tokens_per_second=160, frame_tokens=FRAME_TOKENS,
                 clock=time.monotonic):
        if not 0 < idle_fps <= burst_fps <= 8 or not frame_tokens <= tokens_per_second <= 2000 or not 0 < change < 1:
            raise ValueError("Invalid sampling budget")
        self.idle, self.burst, self.change = 1 / idle_fps, 1 / burst_fps, change
        self.rate, self.cost, self.capacity = float(tokens_per_second), frame_tokens, 2. * tokens_per_second
        self.clock = clock
        self.tokens = self.capacity
        self.updated = None
        self.last_sent = None
        self.last_small = None
        self.sent = self.skipped = 0

    def offer(self, rgb, now=None):
        now = self.clock() if now is None else now
        if self.updated is not None:
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        small = _small_gray(rgb)
        if self.last_sent is None:
            reason = "first"
        else:
            elapsed = now - self.last_sent
            delta = float(abs(small - self.last_small).mean()) / 255
            reason = ("idle" if elapsed >= self.idle else
                      "change" if delta >= self.change and elapsed >= self.burst else None)
        if reason is None or self.tokens < self.cost:
            self.skipped += 1
            return None
        self.tokens -= self.cost
        self.last_sent, self.last_small = now, small
        self.sent += 1
        return reason


def encode_jpeg(rgb, quality=90):
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.fromarray(rgb).save(out, format="JPEG", quality=quality)
    return out.getvalue()


class Stream:
    """One live session: frames and 16 kHz PCM16 packets on one timeline. Nothing is stored."""

    def __init__(self, instruction=None, retain_frames=None, post=None, sampler=None, clock=time.monotonic, feed=None):
        self.base = verify() if post is None else "http://127.0.0.1:0"
        self._send = post or self._post
        self.sampler = sampler or AdaptiveSampler(clock=clock)
        self.clock = clock
        body = {}
        if instruction:
            body["instruction"] = instruction
        if retain_frames:
            body["retain_frames"] = int(retain_frames)
        if feed:
            body["feed"] = str(feed)[:40]
        self.session_id = self._send(self.base + "/video/start", body)["session_id"]
        self.started = clock()
        self.closed = False
        self.receipts = []

    @staticmethod
    def _post(url, body):
        request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with _opener().open(request, timeout=180) as response:
            return json.load(response)

    def _at(self, captured):
        return round((self.clock() if captured is None else captured) - self.started, 3)

    def offer(self, rgb, captured=None, source="unknown"):
        """Sample, then send one frame if the sampler takes it. Returns the receipt or None."""
        if self.closed:
            raise ValueError("Stream closed")
        reason = self.sampler.offer(rgb, captured)
        if reason is None:
            return None
        return self.send_frame(encode_jpeg(rgb), captured, source, reason)

    def send_frame(self, image_bytes, captured=None, source="unknown", reason="direct", soft_tokens=70):
        """``soft_tokens`` 70 for motion; 140 or 280 for a detailed still look (costs 2-4x the tokens)."""
        receipt = self._send(self.base + "/video/frame", {"session_id": self.session_id, "at": self._at(captured),
                             "image": base64.b64encode(image_bytes).decode(), "soft_tokens": int(soft_tokens)})
        receipt = dict(receipt, source=str(source)[:40], reason=reason,
                       source_hash="sha256:" + hashlib.sha256(image_bytes).hexdigest())
        self.receipts.append(receipt)
        return receipt

    def audio(self, pcm, captured=None):
        if self.closed or not pcm or len(pcm) % 2:
            raise ValueError("Closed stream or invalid PCM16 packet")
        return self._send(self.base + "/video/audio", {"session_id": self.session_id, "at": self._at(captured),
                          "audio": base64.b64encode(pcm).decode()})

    def ask(self, question, max_tokens=128):
        result = self._send(self.base + "/video/ask", {"session_id": self.session_id, "question": question,
                            "max_tokens": int(max_tokens)})
        if result.get("checkpoint_sha256") != ANCHOR_SHA256 or result.get("native_video") is not True:
            raise RuntimeError("Video answer came from an unverified checkpoint")
        return result

    def finish(self):
        if self.closed:
            raise ValueError("Stream already closed")
        self.closed = True
        return self._send(self.base + "/video/finish", {"session_id": self.session_id})

    def abort(self):
        if not self.closed:
            self.closed = True
            self._send(self.base + "/video/abort", {"session_id": self.session_id})


def read_tap(since=0, limit=256):
    """Sensory tap events after ``since`` (schema in studio/native_sensory_tap.py), for a latent-state consumer."""
    base = verify()
    with _opener().open("%s/tap?since=%d&limit=%d" % (base, int(since), int(limit)), timeout=5) as response:
        return json.load(response)


def window_record(window, receipts=(), started_at=None):
    """The provenance record of one retained window: per segment a time, a keyframe or audio reference and the
    source hash of the bytes received. No pixels, no description, nothing that was not measured."""
    from record_gaps import VIDEO_GAP_RULE
    by_ref = {r.get("frame_ref"): r for r in receipts if r.get("frame_ref")}
    segments = []
    for s in window or []:
        row = {"at": s.get("stamp"), "kind": s.get("kind")}
        if s.get("kind") == "frame":
            receipt = by_ref.get(s.get("frame_ref"), {})
            row.update(keyframe_ref=s.get("frame_ref"), source_hash=receipt.get("source_hash"),
                       source=receipt.get("source"), visual_tokens=s.get("visual_tokens"))
        else:
            row.update(audio_ref=s.get("audio_ref"), audio_tokens=s.get("audio_tokens"))
        segments.append(row)
    frames = [r for r in segments if r["kind"] == "frame"]
    return {"kind": "native-video-window", "started_at": started_at, "frames": len(frames),
            "keyframe_ref": frames[-1]["keyframe_ref"] if frames else None,
            "source_hash": frames[-1]["source_hash"] if frames else None,
            "segments": segments, "frames_kept": False, "checkpoint_sha256": ANCHOR_SHA256,
            "record_gap": VIDEO_GAP_RULE}


WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
TAG_MAP = os.path.join(WORKSPACE, "memory", "apriltag-memories.json")
TAG_MAP_HOW = ("Gloria fills this. Key: '<family>:<id>', e.g. 'tag36h11:7'. Value: either {'text': 'the memory in "
               "her words'} or {'store': 'a file under memory/ (.json or .jsonl)', 'id': 'the record id', "
               "'id_field': 'id'}, with an optional 'label'.")


def _memory_dir():
    return os.path.realpath(os.path.join(WORKSPACE, "memory"))


def load_tag_map(path=None):
    try:
        with open(path or TAG_MAP) as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)} if isinstance(data, dict) else {}
    except Exception:
        return {}


def init_tag_map(path=None):
    """Create the empty map with its how-to line, once. Never overwrites."""
    path = path or TAG_MAP
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        json.dump({"_how": TAG_MAP_HOW}, f, indent=2)
    return True


def _store_record(entry):
    store = os.path.realpath(os.path.join(_memory_dir(), str(entry.get("store") or "")))
    if not store.startswith(_memory_dir() + os.sep) or not os.path.isfile(store):
        return None
    field, wanted = str(entry.get("id_field") or "id"), str(entry.get("id") or "")
    with open(store) as f:
        rows = [json.loads(l) for l in f if l.strip()] if store.endswith(".jsonl") else json.load(f)
    if isinstance(rows, dict):
        rows = [dict(v, **{field: k}) if isinstance(v, dict) else {field: k, "value": v} for k, v in rows.items()]
    return next((r for r in rows if isinstance(r, dict) and str(r.get(field)) == wanted), None)


def tag_memory(tag, tag_map=None):
    """The memory Gloria linked to one detected tag, or a record saying plainly that nothing is linked or that the
    linked record was not found. Never a guess."""
    key = "%s:%s" % (tag.get("family"), tag.get("tag_id"))
    entry = (tag_map if tag_map is not None else load_tag_map()).get(key)
    out = {"tag": key, "at": tag.get("at"), "label": None, "memory": None, "found": False}
    if not entry:
        out["note"] = "no memory is linked to this tag"
        return out
    out["label"] = str(entry.get("label") or "")[:120] or None
    if entry.get("text"):
        out.update(memory={"text": str(entry["text"])[:1200]}, found=True)
        return out
    try:
        record = _store_record(entry)
    except Exception:
        record = None
    if record is None:
        out["note"] = "the linked memory was not found in its store"
    else:
        out.update(memory={k: (v[:1200] if isinstance(v, str) else v) for k, v in record.items()}, found=True)
    return out


def tag_lines(tags, tag_map=None):
    """One line per distinct tag seen in the window, with its linked memory, placed beside the frames."""
    seen, lines = set(), []
    for tag in tags or []:
        hit = tag_memory(tag, tag_map)
        if hit["tag"] in seen:
            continue
        seen.add(hit["tag"])
        if hit["found"]:
            text = hit["memory"].get("text") or json.dumps(hit["memory"], ensure_ascii=False)[:600]
            lines.append("[TAG %s seen%s - the memory Gloria linked to it%s: %s]" % (
                hit["tag"], " at %s" % tag["at"] if tag.get("at") is not None else "",
                " (%s)" % hit["label"] if hit["label"] else "", text))
        else:
            lines.append("[TAG %s seen - %s. Do not guess what it stands for.]" % (hit["tag"], hit["note"]))
    return lines


def window_tags(receipts):
    """Tags from the frame receipts, each with the stream time it was seen."""
    return [dict(t, at=r.get("at")) for r in receipts or [] for t in r.get("tags") or []]


def senses_block(record, keyframes=(), tags=(), tag_map=None):
    """Content parts for the current conversation turn: the frames themselves (in memory, as image parts), one
    short provenance line, and for each AprilTag seen the memory linked to it. The provenance line says what was
    seen came from frames that were not kept."""
    from record_gaps import VIDEO_GAP_RULE
    parts = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
             for b in keyframes]
    parts += [{"type": "text", "text": line} for line in tag_lines(tags, tag_map)]
    span = [s["at"] for s in record.get("segments") or [] if s.get("at")]
    line = ("[SENSES - live video through your own eyes, %d frame(s)%s; keyframe %s, source %s. %s The frames "
            "themselves were not kept.]" % (record.get("frames", 0),
                                            " from %s to %s" % (span[0], span[-1]) if span else "",
                                            record.get("keyframe_ref") or "none", record.get("source_hash") or "none",
                                            VIDEO_GAP_RULE))
    return parts + [{"type": "text", "text": line}]
