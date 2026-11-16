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
import re
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
# The camera note's own template wording. An answer may report what the note says, never in the note's bookkeeping
# words: round-4 dev answers spliced short pieces of it ("the current scene" + "has lasted" + "12 frame(s)") that no
# single four-token run of the note catches. Active only for the phrases the asked note actually contains.
NOTE_TEMPLATE_PHRASES = ("began at", "has lasted", "frame(", "scene(")   # each refusal is a whole word or a bracket
# Round 5: when a speech question finds no words, that is a structured result (no_speech_captured), not note text the
# answer could quote; the answer opens with his own sentence for it and goes on from there.
NO_WORDS_REPLY = "I couldn't make out any words."
NO_SOUND_REPLY = "I didn't hear anyone speaking."
TRANSCRIBE_SPEECH = True     # a question about speech first hears the retained sound alone and transcribes it
HEAR_MIN_CONFIDENCE = .6     # mean per-token probability below which a transcript is not trusted (dev: noise and
                             # made-up transcripts sat below .6, real speech above .62)
HEAR_SECONDS = 8.            # "what is being said" hears the retained sound (the audio window is eight seconds)
HEAR_TOKENS = 16             # the transcript budget: about twelve words, so the first answer token stays near a second
HEAR_PROMPT = " Write down exactly what the speaker says in this audio."
SPEECH_QUESTION = re.compile(r"\b(said|say|says|saying|speak|speaks|speaking|spoke|talk|talks|talking|hear|heard|"
                             r"hearing|words?|transcri\w*|voices?|audio|conversation|told)\b", re.I)
NO_WORDS = re.compile(r"^\W*(no words|no speech|nothing\W*$|silence\W*$|\[?inaudible)|\bno (discernible |spoken |audible |clear )?"
                      r"(words|speech)\b|\b(muffled|difficult to understand|sound effect)\b", re.I)
HEAR_ECHO = re.compile(r"\b(word for word|transcrib\w*|write down|what the speaker says|the word (is|for)|translation|in this (case|context)|\(note)", re.I)   # the request echoed or misread (a word lookup, a translation), not speech
LEAD_IN = re.compile(r"^\W*(the )?(words|audio|speech)( spoken)?( in this (clip|audio|passage|video))?( says| are| is)?\s*:\s*",
                     re.I)
SOUND_NOTE = True            # every question says what sound this turn holds (the record-gap rule for speech)
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


def _wordy(key):
    """A key that carries words (not a number, a space or punctuation alone)."""
    return isinstance(key, str) and any(c.isalpha() for c in key)


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
                 on_pixels=None, sound_notes=None):
        # on_embedding(kind, at, embeds, ref): the projected embeddings exactly as they enter the mind, for a tap.
        # on_pixels(at, thumb, ref): a 96-px thumbnail of each committed frame (camera_motion), just before its
        # on_embedding call; the thumbnail lives only in memory.
        self.on_embedding = on_embedding
        self.on_pixels = on_pixels
        self.sound_notes = SOUND_NOTE if sound_notes is None else bool(sound_notes)
        self.transcribe_speech = TRANSCRIBE_SPEECH
        self.transcript = None                     # the last hearing pass's transcript (None when none ran)
        self._note_runs = None                     # ((), (), template phrases) of the current question's note
        self.no_speech_captured = False            # the last speech question found no words (a result, not a note)
        self.transcript_confidence = self.transcript_raw = None
        self.scene_markers = bool(scene_markers)   # write "[new scene]" before a frame that differs from the last
        self.last_small = None
        self.answering = False                     # while True, frames and audio are encoded/held, then committed
        self.deferred = []
        self.committing = False                    # while True, an answer's held items are being committed
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
        try:
            found = convert(["<|channel>", "<channel|>", "<|turn>"]) if convert else []
        except Exception:
            found = []
        self.blocked = sorted({i for i in found if isinstance(i, int) and i >= 0 and i != unk})
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
        self._recover_held()
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
        self._recover_held()
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
            span.setdefault("_embeds", []).append(embeds)
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
            span.setdefault("_embeds", []).append(embeds)
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

    def _concat(self, parts):
        if len(parts) == 1:
            return parts[0]
        mx = getattr(self.stream, "mx", None)
        return mx.concatenate(parts, axis=1) if mx is not None else np.concatenate([np.asarray(p) for p in parts], axis=1)

    @staticmethod
    def heard_note(transcript, start, end):
        """The transcript the hearing pass made, with its provenance; or that no words could be made out."""
        start, end = stamp(start), stamp(end)
        text = re.sub(r"\$\\text\{|\}\$|\*\*|__", "", transcript or "")   # markup is not speech
        text = " ".join(LEAD_IN.sub("", text).split())
        quoted = re.findall(r'"([^"]+)"', text)
        text = " ".join(quoted) if quoted else text
        text = text.replace('"', "'").strip()[:400]
        if not text or NO_WORDS.search(text):
            return ("[HEARD from the microphone (%s-%s): words not made out, so for what is being said: the words were "
                    "not captured.]" % (start, end))
        return '[HEARD from the microphone (%s-%s): "%s"]' % (start, end, text)

    def sound_note(self):
        """Provenance of what can be said about speech: the sound this turn holds is the microphone's own audio,
        heard directly, with no written transcript; with none, nothing was captured. Words must come from that
        sound, never from the picture or the camera's notes (the record-gap rule)."""
        spans = [s for s in self.segments.values() if s["kind"] == "audio" and s.get("audio_tokens")]
        if not spans:
            return "[SOUND: none captured, so no speech was captured.]"
        seconds = sum(s["audio_tokens"] for s in spans) * FRAME / SAMPLE_RATE
        end = max(s["at"] + s["audio_tokens"] * FRAME / SAMPLE_RATE for s in spans)
        return "[SOUND: %d s from the microphone (%s-%s), heard directly, no transcript.]" % (
            max(1, round(seconds)), stamp(min(s["at"] for s in spans)), stamp(end))

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
        return [dict({k: v for k, v in s.items() if k != "digest" and not k.startswith("_")}, segment=i)
                for i, s in sorted(self.segments.items())]

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
        self._recover_held()   # a failed earlier answer's held arrivals enter before this question
        if self.answering or self.committing:
            raise BlockingIOError("An answer is already being decoded")
        started = time.perf_counter()
        self._end_audio_span()
        close_ids, close_owner = self._close_pending()
        self._text(close_ids, close_owner)
        mark = self.stream.length(self.cache)
        question = str(question).strip()
        note = str(note or "").strip()
        sound = self.sound_note() if self.sound_notes else ""
        self.transcript = self.transcript_confidence = self.transcript_raw = None
        speech = bool(self.transcribe_speech and self.sound_notes and SPEECH_QUESTION.search(question or ""))
        self.no_speech_captured, reply = False, ""
        if speech and not any(s["kind"] == "audio" and s.get("audio_tokens") for s in self.segments.values()):
            self.no_speech_captured, reply, sound = True, NO_SOUND_REPLY, ""

        def question_chunk(sound):
            # the camera note's template phrases are never said (a seen tag's records may say them)
            words = " ".join(re.sub(r'"[^"]*"|\[TAG [^\]]*\]?', " ", note or "").lower().split())
            phrases = [tuple(k for k in (self._key(t) for t in self._ids(" " + ph)) if isinstance(k, str))
                       for ph in NOTE_TEMPLATE_PHRASES if ph in words
                       and ph not in " ".join(re.findall(r'\[TAG [^\]]*\]?', note or "")).lower()]   # a record may say it
            phrases = [ph for ph in phrases if len(ph) >= 2]
            self._note_runs = ((), (), phrases) if phrases else None
            # order: the camera note, the question, then what was heard last, so an answer that quotes the
            # transcript runs on into the end of the turn, never into the camera note's label
            return self._ids((" " + note if note else "") + (" " + question if question else "")
                             + ("\n" + sound if sound else "") + self.closing)

        question_ids = question_chunk(sound)
        if len(question_ids) + int(max_tokens) + (HEAR_TOKENS * 2 if self.transcribe_speech else 0) > ANSWER_RESERVE:
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
        heard = []
        if self.transcribe_speech and self.sound_notes and SPEECH_QUESTION.search(question or ""):
            spans = sorted((s["at"], i) for i, s in self.segments.items() if s["kind"] == "audio" and s.get("_embeds"))
            heard = [(at, e) for at, i in spans for e in self.segments[i]["_embeds"]]
            keep, need = [], int(HEAR_SECONDS * SAMPLE_RATE / FRAME)
            for piece in reversed(heard):           # the last HEAR_SECONDS: what is being said now
                if need <= 0:
                    break
                keep.insert(0, piece)
                need -= int(piece[1].shape[1])
            heard = keep
        if heard:
            hear_end = max(s["at"] + s["audio_tokens"] * FRAME / SAMPLE_RATE
                           for s in self.segments.values() if s["kind"] == "audio" and s.get("audio_tokens"))
            hear_start = max(0., hear_end - sum(int(e.shape[1]) for _, e in heard) * FRAME / SAMPLE_RATE)
            pieces = set(int(p) for p in self.positions[np.isin(self.owner, [i for _, i in spans])])
            heard_hidden = (everything | pieces) or None   # the sound alone: no frame and none of its own pieces
            if self.stream.length(self.cache) + recall_tokens + sum(int(e.shape[1]) for _, e in heard) + 64 \
                    + ANSWER_RESERVE > CONTEXT:
                raise ValueError("Recalled frames exceed the existing 8192 token budget")
        tokens, finish_reason, first = [], "length", None
        self.answering = True

        def forward(embeds, vision=False, mask=None):
            self.stream.hidden = hidden if mask is None else mask
            try:
                return self.stream.forward(embeds, self.cache, vision)
            finally:
                self.stream.hidden = None

        try:
            if heard:
                # Hearing pass: the retained sound in one piece, without the frames that cut it into pieces, is
                # transcribed; then rolled back. The answer gets the transcript with where it came from.
                hear_mark = self.stream.length(self.cache)
                forward(self.stream.text(self._ids(" " + stamp(hear_start) + " ") + self.boa), mask=heard_hidden)
                forward(self._concat([e for _, e in heard]), mask=heard_hidden)
                self.scores = forward(self.stream.text(self.eoa + self._ids(HEAR_PROMPT + self.closing)), mask=heard_hidden)
                yield 0   # arrivals are taken in (encoded and held) between hearing steps too
                said, logps = [], []
                for _ in range(HEAR_TOKENS):
                    t = self._choose(0., said)
                    z = self.scores.astype(np.float64)
                    z = z[np.isfinite(z)]
                    logps.append(float(self.scores[t]) - float(np.max(z) + np.log(np.exp(z - np.max(z)).sum())))
                    if t in self.mind.eos:
                        break
                    said.append(t)
                    self.scores = forward(self.stream.text([t]), mask=heard_hidden)
                    yield 0
                self.stream.truncate(self.cache, hear_mark)
                self.transcript = self.transcript_raw = self.tokenizer.decode(said, skip_special_tokens=True).strip()
                self.transcript_confidence = float(np.exp(np.mean(logps))) if logps else 0.
                quoted = re.findall(r'"([^"]+)"', self.transcript)
                if self.transcript_confidence < HEAR_MIN_CONFIDENCE or HEAR_ECHO.search(
                        " ".join(quoted) if quoted else self.transcript):   # the request echoed, quoted or not
                    self.transcript = ""   # too unsure, or the request echoed back: the words were not captured
                heard_text = self.heard_note(self.transcript, hear_start, hear_end)
                if '"' in heard_text:
                    question_ids = question_chunk(heard_text)
                if '"' not in heard_text or len(question_ids) + int(max_tokens) > ANSWER_RESERVE:
                    self.no_speech_captured, reply = True, NO_WORDS_REPLY   # a result, not a note to quote
                    question_ids = question_chunk("")
            for at, embeds in recall_frames:
                forward(self.stream.text(self._ids(" " + stamp(at) + " ") + self.boi), mask=recall_hidden)
                forward(embeds, vision=True, mask=recall_hidden)
                forward(self.stream.text(self.eoi), mask=recall_hidden)
            self.scores = forward(self.stream.text(question_ids))
            if reply:
                said = self._ids(reply)[:int(max_tokens)]
                tokens.extend(said)
                first = time.perf_counter() - started
                if on_text:
                    on_text(self.tokenizer.decode(tokens, skip_special_tokens=True))
                if len(tokens) < int(max_tokens):
                    self.scores = forward(self.stream.text(said))
            for _ in range(int(max_tokens) - len(tokens)):
                token = self._choose(float(temperature), tokens, self._note_runs)
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
            self._note_runs = None
            self.owner, self.positions = self.owner[:mark], self.positions[:mark]
            self.answering = False
            self.pending_close = None
        result = {"text": self.tokenizer.decode(tokens, skip_special_tokens=True), "tokens": tokens,
                  "finish_reason": finish_reason, "first_token_seconds": first,
                  "total_seconds": time.perf_counter() - started, "window": self.window(),
                  "cache_tokens": mark, "frames_seen": self.frames, "frames_evicted": self.evicted_frames,
                  "checkpoint_sha256": self.mind.sha, "native_video": True, "transcript": self.transcript,
                  "transcript_confidence": self.transcript_confidence,
                  "no_speech_captured": self.no_speech_captured}
        # Commit what arrived during the answer one item per step, in arrival order, so the caller can take in
        # new arrivals in between (they queue behind the held items, never ahead of them).
        committed = 0
        self.committing = True
        try:
            while self.deferred:
                self._commit_deferred(self.deferred.pop(0))
                committed += 1
                if self.deferred:
                    yield len(tokens)
        finally:
            self.committing = False
        result["deferred_committed"] = committed
        return result

    def _recover_held(self):
        """Items are held only while an answer is decoded or its held items are being committed. If an answer
        failed (or was abandoned) before committing them, commit them now, in order, so later arrivals are never
        held forever."""
        if self.deferred and not self.answering and not self.committing:
            self.flush_deferred()

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

    def _choose(self, temperature, history=(), notes=None):
        scores = self.scores.copy()
        scores[self.mind.suppress] = -np.inf
        if self.blocked:
            scores[self.blocked] = -np.inf
        keys = [self._key(t) for t in history]
        scores = guard_repeats(scores, history, keys)
        if not notes:
            return self._pick(scores, temperature)
        phrases = notes[2] if len(notes) > 2 else ()
        # whitespace tokens are skipped and any token spelling the refused word is refused
        said = [k for k in keys if isinstance(k, str)]
        banned = set()
        for ph in phrases:
            if len(said) >= len(ph) - 1 and tuple(said[len(said) - len(ph) + 1:]) == ph[:-1]:
                banned.add(ph[-1])
        token = self._pick(scores, temperature)
        for _ in range(64):   # each refused spelling leaves the race; the last pick stands (never the first refused)
            key = self._key(token)
            if not (isinstance(key, str) and key in banned):
                break
            scores[token] = -np.inf
            token = self._pick(scores, temperature)
        return token

    def _pick(self, scores, temperature):
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
