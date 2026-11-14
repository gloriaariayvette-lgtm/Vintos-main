"""Live frames (and audio packets) into the frozen mind's own visual path, with KV reuse across windows.

Frames go through the checkpoint's unchanged image projection (the same native path that scored 67.2% and
75.4% on the registered motion QA). One open user turn holds a timeline of timestamped frames and audio spans
in a single KV cache. Old segments are evicted from the cache; because every cached token keeps its absolute
position and masks are built from those positions, evicting a segment is exactly the same as masking it, so the
retained tokens never need to be recomputed. A question is appended, answered, and rolled back, so the stream
continues without re-reading what it already saw.

No downloads, records, network access or background processes are started here. Frames stay in memory.
"""
import hashlib
import time

import numpy as np

from native_audio_runtime import FRAME, SAMPLE_RATE

STREAM_MARKER = "[[NATIVE_STREAM]]"
SOFT_TOKENS = 70             # per frame; the registered native motion QA setting
SOFT_TOKEN_CHOICES = (70, 140, 280)
RETAIN_FRAMES = 16           # ~16 x 72 tokens: older frames are already outside the 1,024-token local window
RETAIN_AUDIO_TOKENS = 200    # eight seconds of 40 ms audio tokens, the audio candidate's live window
AUDIO_SPAN_TOKENS = 50       # an audio span closes every two seconds so eviction stays granular
AUDIO_FLUSH_TOKENS = 10      # audio enters the mind in 400 ms steps (or sooner when a frame or question closes it)
WINDOW_TOKENS = 1024         # the checkpoint's local (sliding) attention window
SCENE_CHANGE = .15           # mean 32x32 luminance change (0..1) that marks a new scene
SCENE_MARKER = "[new scene]"
REPEAT_PENALTY = 1.1         # answer-token repetition penalty (the video path decodes greedily by default)
NO_REPEAT_NGRAM = 4          # no 4-token run is repeated inside one answer
LIVE_ANSWER_TOKENS = 32      # answers during a live stream are capped so ingestion never waits long


def _thumb(rgb):
    from camera_motion import thumb
    return thumb(rgb)


def _small_gray(rgb):
    from PIL import Image
    gray = Image.fromarray(np.asarray(rgb, dtype=np.uint8)).convert("L")
    return np.asarray(gray.resize((32, 32), Image.BOX), dtype=np.float32)
CONTEXT = 8192
ANSWER_RESERVE = 640         # question plus answer budget kept free at all times
PREFIX, QUERY = -1, -2       # owners of the open-turn prefix and of a rolled-back question/answer


def guard_repeats(scores, history, keys=None, penalty=REPEAT_PENALTY, ngram=NO_REPEAT_NGRAM):
    """Keep an answer from looping on itself ("the oration of the oration of ..."): every token already in this
    answer is penalised (HF-style: positive scores divided, negative multiplied), and a token that would repeat an
    ``ngram``-token run already in the answer is ruled out. ``keys`` (one per history token, e.g. its text lowercased
    without spaces) let "The blue square" and " the blue square" count as the same run. Only the answer's own tokens
    count, so the first token (and with it every one-word answer) is never changed."""
    history = list(history)
    keys = list(keys) if keys is not None else history
    if not history:
        return scores
    seen = np.unique(np.asarray(history, dtype=np.int64))
    seen = seen[seen < len(scores)]
    s = scores[seen]
    scores[seen] = np.where(s > 0, s / penalty, s * penalty)
    if ngram > 1 and len(history) >= ngram - 1:
        tail = tuple(keys[-(ngram - 1):])
        for i in range(len(history) - ngram + 1):
            if tuple(keys[i:i + ngram - 1]) == tail:
                scores[history[i + ngram - 1]] = -np.inf
    return scores


def stamp(seconds):
    minutes, rest = divmod(max(0, int(seconds)), 60)
    return "%02d:%02d" % (minutes, rest)


class PositionedKV:
    """One layer's keys and values with their absolute positions. RoPE reads ``offset`` (the next position),
    which never moves backwards on eviction, so retained keys keep their exact rotations."""

    def __init__(self, mx):
        self.mx = mx
        self.keys = self.values = None
        self.positions = np.empty(0, dtype=np.int64)
        self.offset = 0

    def update_and_fetch(self, keys, values):
        mx = self.mx
        n = int(keys.shape[2])
        if self.keys is None:
            self.keys, self.values = keys, values
        else:
            self.keys = mx.concatenate([self.keys, keys], axis=2)
            self.values = mx.concatenate([self.values, values], axis=2)
        self.positions = np.concatenate([self.positions, np.arange(self.offset, self.offset + n)])
        self.offset += n
        return self.keys, self.values

    def keep(self, index):
        index = np.asarray(index, dtype=np.int64)
        if len(index) == len(self.positions):
            return
        if not len(index):
            self.keys = self.values = None
        else:
            take = self.mx.array(index.astype(np.int32))
            self.keys = self.mx.take(self.keys, take, axis=2)
            self.values = self.mx.take(self.values, take, axis=2)
        self.positions = self.positions[index]

    def truncate(self, length):
        """Drop the newest tokens (a rolled-back question); the next position follows the kept tail."""
        if length >= len(self.positions):
            return
        self.positions = self.positions[:length]
        self.keys = self.keys[..., :length, :] if length else None
        self.values = self.values[..., :length, :] if length else None
        self.offset = int(self.positions[-1]) + 1 if length else 0

    @property
    def nbytes(self):
        return 0 if self.keys is None else int(self.keys.nbytes + self.values.nbytes)


def stream_masks(layers, caches, length, window, vision, hidden=None, mx=None):
    """Boolean masks per layer type from absolute positions: causal, the local window on sliding layers, and
    bidirectional attention inside one image when the chunk is a single image (the checkpoint's vision rule).
    ``hidden`` is a set of positions to mask; it exists only to check that eviction equals masking."""
    first = caches[0]
    q = np.arange(first.offset, first.offset + length)
    k = np.concatenate([first.positions, q])
    allowed = k[None, :] <= q[:, None]
    if hidden:
        allowed &= ~np.isin(k, np.fromiter(hidden, dtype=np.int64))[None, :]
    local = allowed & ((q[:, None] - k[None, :]) < window)
    if vision:
        allowed[:, -length:] = True
        local[:, -length:] = True
    full, sliding = mx.array(allowed), mx.array(local)
    return [sliding if layer.layer_type == "sliding_attention" else full for layer in layers]


def resize_like_hf(rgb, height, width):
    """The reference resize: antialiased bicubic (the kernel torch's antialias path shares with PIL), done by
    PIL's native code, back to uint8."""
    x = np.asarray(rgb, dtype=np.uint8)
    if x.shape[:2] == (height, width):
        return x
    from PIL import Image
    return np.asarray(Image.fromarray(x).resize((width, height), Image.BICUBIC), dtype=np.uint8)


class AppleStream:
    """Streaming adapter over the Codex AppleBackend: same loaded model, same embeddings, own caches."""

    def __init__(self, backend, soft_tokens=SOFT_TOKENS):
        import mlx.core as mx
        from mlx_vlm.models.gemma4_unified import processing_gemma4_unified as unified
        from mlx_vlm.models.gemma4.processing_gemma4 import get_aspect_ratio_preserving_size
        self.mx, self.base, self.model = mx, backend, backend.model
        self.processor = unified.Gemma4UnifiedImageProcessor(max_soft_tokens=soft_tokens)
        self._patches, self._pad, self._size = (unified._convert_image_to_model_patches, unified._pad_patches,
                                                get_aspect_ratio_preserving_size)
        text_model = self.model.language_model.model
        self.window = int(text_model.window_size)
        self.hidden = None
        original = text_model._make_masks
        if getattr(original, "_native_stream", False):
            return
        stream = self

        def make_masks(h, cache, mm_token_type_ids=None):
            # Stock caches (the audio and text routes) keep the stock masks unchanged.
            if not cache or not all(isinstance(c, PositionedKV) for c in cache):
                return original(h, cache, mm_token_type_ids)
            return stream_masks(text_model.layers, cache, int(h.shape[1]), stream.window,
                                mm_token_type_ids is not None, stream.hidden, mx)

        make_masks._native_stream = True
        text_model._make_masks = make_masks

    def new_cache(self):
        return [PositionedKV(self.mx) for _ in self.model.language_model.model.layers]

    def numpy(self, x):
        return np.array(x.astype(self.mx.float32))

    def text(self, ids):
        return self.base.text(ids)

    def audio(self, frames):
        return self.base.audio(frames)

    def pixels(self, rgb, soft_tokens=SOFT_TOKENS):
        """Patches exactly as the HF reference prepares them: torchvision-style resize, 1/255, no normalisation."""
        p = self.processor
        x = np.asarray(rgb, dtype=np.uint8)
        height, width = self._size(x.shape[0], x.shape[1], p.patch_size, soft_tokens * p.pooling_kernel_size ** 2,
                                   p.pooling_kernel_size)
        x = resize_like_hf(x, height, width).astype(np.float32) / 255.
        patches, positions = self._patches(x.transpose(2, 0, 1), p.model_patch_size)
        count = patches.shape[0]
        patches, positions = self._pad(patches, positions, soft_tokens)
        return patches[None], positions[None], count

    def image(self, rgb, soft_tokens=SOFT_TOKENS):
        mx = self.mx
        patches, positions, count = self.pixels(rgb, soft_tokens)
        dtype = self.model.vision_embedder.patch_dense.weight.dtype   # HF casts pixels to the projection dtype
        features = self.model.get_image_features(mx.array(patches).astype(dtype), mx.array(positions))
        return features.astype(self.model.language_model.model.embed_tokens.weight.dtype).reshape(1, int(count), -1)

    def forward(self, embeds, cache, vision=False):
        mx = self.mx
        kwargs = {"mm_token_type_ids": mx.full((1, int(embeds.shape[1])), 2, dtype=mx.int32)} if vision else {}
        out = self.model.language_model(None, inputs_embeds=embeds, cache=cache, logits_to_keep=1, **kwargs)
        mx.eval(out.logits)
        return np.array(out.logits[0, -1].astype(mx.float32))

    @staticmethod
    def length(cache):
        return len(cache[0].positions)

    @staticmethod
    def keep(cache, index):
        for layer in cache:
            layer.keep(index)

    @staticmethod
    def truncate(cache, length):
        for layer in cache:
            layer.truncate(length)


def frame_ref(rgb):
    x = np.ascontiguousarray(np.asarray(rgb, dtype=np.uint8))
    return "sha256:" + hashlib.sha256(np.array(x.shape, dtype=np.int64).tobytes() + x.tobytes()).hexdigest()


class LiveSession:
    """One open turn: a timeline of frames and audio spans in one cache, a bounded retained window, and
    questions that are answered then rolled back."""

    def __init__(self, mind, stream, instruction=None, retain_frames=RETAIN_FRAMES,
                 retain_audio_tokens=RETAIN_AUDIO_TOKENS, clock=time.monotonic, on_embedding=None, scene_markers=False,
                 on_pixels=None):
        # on_embedding(kind, at, embeds, ref): the projected embeddings exactly as they enter the mind, for a tap.
        # on_pixels(at, thumb, ref): a 96-px thumbnail of each committed frame (camera_motion), just before its
        # on_embedding call; the thumbnail lives only in memory.
        self.on_embedding = on_embedding
        self.on_pixels = on_pixels
        self.scene_markers = bool(scene_markers)   # write "[new scene]" before a frame that differs from the last
        self.last_small = None
        self.answering = False                     # while True, frames and audio are encoded/held, then committed
        self.deferred = []
        if not 1 <= int(retain_frames) <= 64 or not 0 <= int(retain_audio_tokens) <= 750:
            raise ValueError("Invalid retention window")
        self.mind, self.stream, self.tokenizer = mind, stream, mind.tokenizer
        self.retain_frames, self.retain_audio_tokens = int(retain_frames), int(retain_audio_tokens)
        self.clock = clock
        self.instruction = str(instruction).strip() if instruction else ""
        content = self.instruction + STREAM_MARKER
        if instruction and STREAM_MARKER in str(instruction):
            raise ValueError("Reserved stream placeholder")
        prompt = self.tokenizer.apply_chat_template([{"role": "user", "content": content}], tokenize=False,
                                                    add_generation_prompt=True, enable_thinking=False)
        left, self.closing = prompt.split(STREAM_MARKER)
        tok = self.tokenizer
        self.boi, self.eoi = self._ids(tok.boi_token), self._ids(tok.eoi_token)
        # The prompt already holds the empty thinking block (enable_thinking=False); an answer never opens another
        # channel or turn (it showed as a leading "thought" in live answers).
        convert = getattr(tok, "convert_tokens_to_ids", None)
        unk = getattr(tok, "unk_token_id", None)
        self.blocked = sorted({i for i in (convert(["<|channel>", "<channel|>", "<|turn>"]) if convert else [])
                               if isinstance(i, int) and i >= 0 and i != unk})
        self._keys = {}
        self.boa, self.eoa = self._ids(getattr(tok, "boa_token", "<|audio>")), self._ids(getattr(tok, "eoa_token", "<audio|>"))
        self.cache = stream.new_cache()
        self.next_pos = 0              # absolute position of the next committed token (rolled-back questions excluded)
        self.window_tokens = int(getattr(stream, "window", WINDOW_TOKENS))
        self.owner = np.empty(0, dtype=np.int64)
        self.positions = np.empty(0, dtype=np.int64)   # absolute position of every committed cached token
        self.segments = {}             # id -> provenance of one frame or audio span
        self.next_id = 0
        self.pending_close = None      # (ids, owner) closing the last frame or audio span
        self.audio_span = None
        self.audio_tail = np.empty(0, dtype=np.float32)
        self.closed = False
        self.started = clock()
        self.frames = self.evicted_frames = self.audio_tokens = 0
        self.scores = None
        self._forward(self.stream.text(self._ids(left, raw=True)), PREFIX)

    def _ids(self, text, raw=False):
        return self.tokenizer.encode(text, add_special_tokens=False)

    def _forward(self, embeds, owner, vision=False):
        n = int(embeds.shape[1])
        if self.stream.length(self.cache) + n + ANSWER_RESERVE > CONTEXT:
            raise ValueError("Context exceeds the existing 8192 token budget")
        self.scores = self.stream.forward(embeds, self.cache, vision)
        self.owner = np.concatenate([self.owner, np.full(n, owner, dtype=np.int64)])
        self.positions = np.concatenate([self.positions, np.arange(self.next_pos, self.next_pos + n)])
        self.next_pos += n

    def _text(self, ids, owner):
        if ids:
            self._forward(self.stream.text(ids), owner)

    def _close_pending(self):
        if self.pending_close:
            ids, owner = self.pending_close
            self.pending_close = None
            return ids, owner
        return [], None

    def _open(self, kind, at, opener, marker="", **record):
        """Write ``[close of previous] mm:ss <open>`` as one chunk; the close keeps its previous owner."""
        segment = self.next_id
        self.next_id += 1
        close_ids, close_owner = self._close_pending()
        # The native video layout: "<question> 00:00 <|image>...<image|> 00:00 <|image>..."
        space = " " if (segment or self.instruction) else ""
        lead = self._ids(space + (marker + " " if marker else "") + stamp(at) + " ")
        embeds = self.stream.text(close_ids + lead + opener)
        n_close = len(close_ids)
        self._forward(embeds, segment)
        if n_close:
            self.owner[-len(lead) - len(opener) - n_close:-len(lead) - len(opener)] = close_owner
        self.segments[segment] = dict(record, kind=kind, at=round(float(at), 3), stamp=stamp(at))
        return segment

    def _seconds(self, at):
        return self.clock() - self.started if at is None else float(at)

    def frame(self, rgb, at=None, soft_tokens=SOFT_TOKENS):
        """Append one frame through the native image projection. Returns a receipt; the frame is not kept.
        ``soft_tokens`` is the native budget: 70 for motion, up to 280 (the checkpoint default) for a still look.
        While an answer is being decoded (or what arrived during it is still being committed) the frame is encoded
        now and enters the timeline after everything that arrived before it."""
        prepared = self.prepare_frame(rgb, at, soft_tokens)
        if self.answering or self.deferred:
            self.deferred.append(("frame", prepared))
            return {"frame_ref": prepared["ref"], "at": round(prepared["at"], 3), "visual_tokens": int(prepared["embeds"].shape[1]),
                    "deferred": True, "evicted_segments": [], "ingest_seconds": prepared["seconds"]}
        return self.commit_frame(prepared)

    def prepare_frame(self, rgb, at=None, soft_tokens=SOFT_TOKENS):
        """Validate and encode a frame through the native image projection; the timeline is not touched."""
        if self.closed:
            raise ValueError("Session is closed")
        if soft_tokens not in SOFT_TOKEN_CHOICES:
            raise ValueError("Unsupported visual token budget")
        x = np.asarray(rgb)
        if x.ndim != 3 or x.shape[2] != 3 or x.dtype != np.uint8 or not 32 <= min(x.shape[:2]) or max(x.shape[:2]) > 4096:
            raise ValueError("Expected an RGB uint8 frame between 32 and 4096 pixels per side")
        started = time.perf_counter()
        embeds = self.stream.image(x, soft_tokens) if soft_tokens != SOFT_TOKENS else self.stream.image(x)
        return {"embeds": embeds, "at": self._seconds(at), "ref": frame_ref(x), "shape": x.shape[:2],
                "small": _small_gray(x) if self.scene_markers else None, "started": started,
                "thumb": _thumb(x) if self.on_pixels else None, "seconds": time.perf_counter() - started}

    def commit_frame(self, prepared):
        self._end_audio_span()
        at, ref, embeds = prepared["at"], prepared["ref"], prepared["embeds"]
        scene = False
        if prepared["small"] is not None:
            scene = self.last_small is not None and float(np.abs(prepared["small"] - self.last_small).mean()) / 255 >= SCENE_CHANGE
            self.last_small = prepared["small"]
        segment = self._open("frame", at, self.boi, frame_ref=ref, height=int(prepared["shape"][0]),
                             width=int(prepared["shape"][1]), marker=SCENE_MARKER if scene else "")
        if scene:
            self.segments[segment]["scene_change"] = True
        self._forward(embeds, segment, vision=True)
        if self.on_pixels and prepared.get("thumb") is not None:
            try:
                self.on_pixels(at, prepared["thumb"], ref)
            except Exception:
                pass   # a consumer never affects what the mind sees
        self._tap("frame", at, embeds, ref)
        self.segments[segment]["visual_tokens"] = int(embeds.shape[1])
        self.segments[segment]["end_pos"] = self.next_pos - 1
        self.pending_close = (self.eoi, segment)
        self.frames += 1
        evicted = self._evict()
        return {"segment": segment, "frame_ref": ref, "at": round(at, 3), "visual_tokens": int(embeds.shape[1]),
                "cache_tokens": self.stream.length(self.cache), "retained_frames": self._count("frame"),
                "evicted_segments": evicted, "scene_change": scene,
                "ingest_seconds": time.perf_counter() - prepared["started"]}

    def audio(self, samples, at=None):
        """Append mono 16 kHz samples on the same timeline as the frames (40 ms native audio tokens)."""
        if self.closed:
            raise ValueError("Session is closed")
        x = np.asarray(samples, dtype=np.float32)
        if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.max(np.abs(x)) > 1 or len(x) > 8 * SAMPLE_RATE:
            raise ValueError("Expected a nonempty finite mono waveform in [-1, 1], at most eight seconds")
        started = time.perf_counter()
        at = self._seconds(at)
        if self.answering or self.deferred:
            self.deferred.append(("audio", x, at))
            return {"audio_tokens": self.audio_tokens, "pending_samples": len(self.audio_tail) + len(x),
                    "deferred": True, "evicted_segments": [], "ingest_seconds": time.perf_counter() - started}
        return self._commit_audio(x, at, started)

    def _commit_audio(self, x, at, started=None):
        started = time.perf_counter() if started is None else started
        if self.audio_span is None:
            self.audio_span = self._open("audio", at, self.boa, audio_tokens=0, digest=hashlib.sha256())
        span = self.segments[self.audio_span]
        span["digest"].update(x.tobytes())
        self.audio_tail = np.concatenate([self.audio_tail, x])
        n = len(self.audio_tail) // FRAME
        if n < AUDIO_FLUSH_TOKENS:
            n = 0   # held until 400 ms are ready (or a frame/question closes the span): one model pass, not five
        while n:
            take = min(n, AUDIO_SPAN_TOKENS - span["audio_tokens"])
            frames = self.audio_tail[:take * FRAME].reshape(take, FRAME)
            embeds = self.stream.audio(frames)
            self._forward(embeds, self.audio_span)
            self._tap("audio", at + span["audio_tokens"] * FRAME / SAMPLE_RATE, embeds, "span:%d" % self.audio_span)
            self.audio_tail = self.audio_tail[take * FRAME:].copy()
            span["audio_tokens"] += take
            self.audio_tokens += take
            n -= take
            if span["audio_tokens"] >= AUDIO_SPAN_TOKENS:
                self._end_audio_span(pad=False)
                if n or len(self.audio_tail):
                    at += AUDIO_SPAN_TOKENS * FRAME / SAMPLE_RATE
                    self.audio_span = self._open("audio", at, self.boa, audio_tokens=0, digest=hashlib.sha256())
                    span = self.segments[self.audio_span]
        evicted = self._evict()
        return {"audio_tokens": self.audio_tokens, "pending_samples": len(self.audio_tail),
                "cache_tokens": self.stream.length(self.cache), "evicted_segments": evicted,
                "ingest_seconds": time.perf_counter() - started}

    def _end_audio_span(self, pad=True):
        if self.audio_span is None:
            return
        span = self.segments[self.audio_span]
        if pad and len(self.audio_tail):
            n = -(-len(self.audio_tail) // FRAME)
            frames = np.pad(self.audio_tail, (0, n * FRAME - len(self.audio_tail))).reshape(n, FRAME)
            embeds = self.stream.audio(frames)
            self._forward(embeds, self.audio_span)
            self._tap("audio", span["at"] + span["audio_tokens"] * FRAME / SAMPLE_RATE, embeds, "span:%d" % self.audio_span)
            span["audio_tokens"] += n
            self.audio_tokens += n
        if pad:
            self.audio_tail = np.empty(0, dtype=np.float32)
        span["audio_ref"] = "sha256:" + span.pop("digest").hexdigest()
        self.pending_close = (self.eoa, self.audio_span)
        self.audio_span = None

    def _tap(self, kind, at, embeds, ref):
        if self.on_embedding:
            try:
                self.on_embedding(kind, at, embeds, ref)
            except Exception:
                pass   # a consumer never affects what the mind sees

    def _count(self, kind):
        return sum(1 for s in self.segments.values() if s["kind"] == kind)

    def _evict(self):
        """Drop the oldest frames beyond the frame window and the oldest audio beyond the audio window."""
        doomed = []
        frames = sorted(i for i, s in self.segments.items() if s["kind"] == "frame")
        doomed += frames[:max(0, len(frames) - self.retain_frames)]
        # A frame that has slid out of the local attention window leaves the global layers too, so every
        # layer sees the same retained past.
        horizon = self.next_pos - self.window_tokens
        doomed += [i for i in frames if i not in doomed and self.segments[i].get("end_pos", horizon) < horizon]
        spans = sorted((i for i, s in self.segments.items() if s["kind"] == "audio" and i != self.audio_span), reverse=True)
        kept = sum(self.segments[i].get("audio_tokens", 0) for i in self.segments
                   if i == self.audio_span)
        for i in spans:
            kept += self.segments[i].get("audio_tokens", 0)
            if kept > self.retain_audio_tokens:
                doomed.append(i)
        if self.pending_close:
            doomed = [i for i in doomed if i != self.pending_close[1]]
        if not doomed:
            return []
        keep = np.flatnonzero(~np.isin(self.owner, doomed))
        self.stream.keep(self.cache, keep)
        self.owner = self.owner[keep]
        self.positions = self.positions[keep]
        for i in doomed:
            if self.segments.pop(i)["kind"] == "frame":
                self.evicted_frames += 1
        return sorted(doomed)

    def window(self):
        """Provenance of what the mind currently holds: one record per retained frame or audio span."""
        return [dict({k: v for k, v in s.items() if k != "digest"}, segment=i) for i, s in sorted(self.segments.items())]

    def ask(self, question, max_tokens=128, temperature=0, on_text=None, recent_seconds=None, view_from=None,
            note=None, recall_frames=None):
        """Answer from the retained window, then roll the question and answer back out of the cache."""
        steps = self.ask_steps(question, max_tokens, temperature, on_text, recent_seconds, view_from, note,
                               recall_frames)
        while True:
            try:
                next(steps)
            except StopIteration as done:
                return done.value

    def ask_steps(self, question, max_tokens=128, temperature=0, on_text=None, recent_seconds=None, view_from=None,
                  note=None, recall_frames=None):
        """The same answer one token per step, so a caller can take in arrivals between tokens: while it runs,
        frames are encoded and audio held, and both enter the timeline right after the answer is rolled back.
        ``recent_seconds`` limits the answer to frames from the last N seconds before the question (older
        frames are masked for the question and answer only; they stay in the window). ``view_from`` does the
        same from an absolute stream time (e.g. where the camera mamepa says the present happening began), and
        ``note`` is a short text (e.g. the camera mamepa's summary) placed before the question.
        ``recall_frames`` is a list of (stream seconds, projected embeddings) kept by the camera mamepa from an
        earlier scene that has left the window; each is shown again as a stamped image span just before the note.
        Recalled frames are always read with the retained frames masked, so what is shown again is seen as it was,
        not through the scene that followed it.
        All of these are rolled back with the answer."""
        if self.closed:
            raise ValueError("Session is closed")
        if not 1 <= int(max_tokens) <= 512 or not 0 <= float(temperature) <= 2:
            raise ValueError("Invalid generation budget")
        if STREAM_MARKER in str(question) or STREAM_MARKER in str(note or ""):
            raise ValueError("Reserved stream placeholder")
        if self.answering:
            raise BlockingIOError("An answer is already being decoded")
        started = time.perf_counter()
        self._end_audio_span()
        close_ids, close_owner = self._close_pending()
        self._text(close_ids, close_owner)
        mark = self.stream.length(self.cache)
        question = str(question).strip()
        note = str(note or "").strip()
        question_ids = self._ids((" " + note if note else "") + (" " + question if question else "") + self.closing)
        if len(question_ids) + int(max_tokens) > ANSWER_RESERVE:
            raise ValueError("Question and answer exceed the reserved budget")
        recall_frames = list(recall_frames or [])
        recall_tokens = sum(int(e.shape[1]) + 8 for _, e in recall_frames)
        if self.stream.length(self.cache) + recall_tokens + ANSWER_RESERVE > CONTEXT:
            raise ValueError("Recalled frames exceed the existing 8192 token budget")
        hidden = None
        frames = [s for s in self.segments.values() if s["kind"] == "frame"]
        horizons = []
        if recent_seconds is not None and frames:
            horizons.append(max(s["at"] for s in frames) - float(recent_seconds))
        if view_from is not None and frames:
            horizons.append(min(float(view_from), max(s["at"] for s in frames)))   # never hides the newest frame
        if horizons:
            horizon = max(horizons)
            old = [i for i, s in self.segments.items() if s["kind"] == "frame" and s["at"] < horizon - 1e-6]
            hidden = set(int(p) for p in self.positions[np.isin(self.owner, old)])
        window_frames = [i for i, s in self.segments.items() if s["kind"] == "frame"]
        everything = set(int(p) for p in self.positions[np.isin(self.owner, window_frames)])
        recall_hidden = (everything | (hidden or set())) or None
        tokens, finish_reason, first = [], "length", None
        self.answering = True

        def forward(embeds, vision=False, mask=None):
            self.stream.hidden = hidden if mask is None else mask
            try:
                return self.stream.forward(embeds, self.cache, vision)
            finally:
                self.stream.hidden = None

        try:
            for at, embeds in recall_frames:
                forward(self.stream.text(self._ids(" " + stamp(at) + " ") + self.boi), mask=recall_hidden)
                forward(embeds, vision=True, mask=recall_hidden)
                forward(self.stream.text(self.eoi), mask=recall_hidden)
            self.scores = forward(self.stream.text(question_ids))
            for _ in range(int(max_tokens)):
                token = self._choose(float(temperature), tokens)
                if first is None:
                    first = time.perf_counter() - started
                if token in self.mind.eos:
                    finish_reason = "stop"
                    break
                tokens.append(token)
                if on_text:
                    on_text(self.tokenizer.decode(tokens, skip_special_tokens=True))
                if len(tokens) < int(max_tokens):
                    self.scores = forward(self.stream.text([token]))
                    yield len(tokens)
        finally:
            self.stream.truncate(self.cache, mark)
            self.owner, self.positions = self.owner[:mark], self.positions[:mark]
            self.answering = False
            self.pending_close = None
        result = {"text": self.tokenizer.decode(tokens, skip_special_tokens=True), "tokens": tokens,
                  "finish_reason": finish_reason, "first_token_seconds": first,
                  "total_seconds": time.perf_counter() - started, "window": self.window(),
                  "cache_tokens": mark, "frames_seen": self.frames, "frames_evicted": self.evicted_frames,
                  "checkpoint_sha256": self.mind.sha, "native_video": True}
        # Commit what arrived during the answer one item per step, in arrival order, so the caller can take in
        # new arrivals in between (they queue behind the held items, never ahead of them).
        committed = 0
        while self.deferred:
            self._commit_deferred(self.deferred.pop(0))
            committed += 1
            if self.deferred:
                yield len(tokens)
        result["deferred_committed"] = committed
        return result

    def _commit_deferred(self, item):
        kind, *payload = item
        if kind == "frame":
            self.commit_frame(payload[0])
        else:
            self._commit_audio(payload[0], payload[1])

    def flush_deferred(self):
        """Commit everything that is held, in arrival order."""
        items, self.deferred = self.deferred, []
        for item in items:
            self._commit_deferred(item)
        return len(items)

    def _key(self, token):
        key = self._keys.get(token)
        if key is None:
            key = self._keys[token] = self.tokenizer.decode([token], skip_special_tokens=False).strip().lower() or token
        return key

    def _choose(self, temperature, history=()):
        scores = self.scores.copy()
        scores[self.mind.suppress] = -np.inf
        if self.blocked:
            scores[self.blocked] = -np.inf
        scores = guard_repeats(scores, history, [self._key(t) for t in history])
        if not temperature:
            return int(np.argmax(scores))
        scaled = scores.astype(np.float64) / temperature
        top_k = int(getattr(self.mind, "top_k", 0))
        if 0 < top_k < len(scaled):
            scaled[scaled < np.partition(scaled, -top_k)[-top_k]] = -np.inf
        p = np.exp(scaled - np.max(scaled)); p /= p.sum()
        top_p = float(getattr(self.mind, "top_p", 1))
        if top_p < 1:
            order = np.argsort(-p)
            p[order[np.cumsum(p[order]) - p[order] >= top_p]] = 0
            p /= p.sum()
        return int(np.random.choice(len(p), p=p))

    def abort(self):
        self.closed = True
        self.cache = None
        self.audio_tail = np.empty(0, dtype=np.float32)
        self.pending_close = None
