"""Local frozen checkpoint inference with bounded, incremental waveform input.

No downloads, records, network access or background processes are started here.
"""
import hashlib
import json
import pathlib
import time

import numpy as np

FRAME = 640
SAMPLE_RATE = 16000
MAX_SAMPLES = 8 * SAMPLE_RATE
MAX_VOICE_SAMPLES = 30 * SAMPLE_RATE
MARKER = "[[NATIVE_WAVEFORM]]"


def checkpoint_sha(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class TorchBackend:
    def __init__(self, path):
        import torch
        from transformers.models.gemma4_unified.modeling_gemma4_unified import Gemma4UnifiedForConditionalGeneration
        if not torch.cuda.is_available():
            raise RuntimeError("The reference backend requires the cloud GPU")
        self.torch = torch
        self.model = Gemma4UnifiedForConditionalGeneration.from_pretrained(
            path, local_files_only=True, dtype=torch.bfloat16,
            device_map="cuda", attn_implementation="sdpa").eval().requires_grad_(False)

    def new_cache(self):
        return None

    def text(self, ids):
        with self.torch.inference_mode():
            return self.model.get_input_embeddings()(self.torch.tensor([ids], device="cuda"))

    def audio(self, frames):
        t = self.torch
        with t.inference_mode():
            x = t.as_tensor(frames[None], device="cuda", dtype=t.bfloat16)
            return self.model.model.get_audio_features(x, t.ones(x.shape[:2], device="cuda", dtype=t.bool),
                                                      return_dict=True).pooler_output

    def forward(self, embeds, cache, length):
        t = self.torch
        with t.inference_mode():
            out = self.model(inputs_embeds=embeds, past_key_values=cache,
                             attention_mask=t.ones((1, length), device="cuda", dtype=t.long),
                             use_cache=True, logits_to_keep=1)
            t.cuda.synchronize()
        return out.logits[0, -1].float().cpu().numpy(), out.past_key_values


class AppleBackend:
    def __init__(self, path):
        import sys
        if sys.platform != "darwin":
            raise RuntimeError("The Apple backend requires the Studio")
        import mlx.core as mx
        from mlx_vlm.utils import load_model
        self.mx = mx
        self.model = load_model(pathlib.Path(path), strict=True)
        self.model.eval()
        if self.model.config.text_config.hidden_size_per_layer_input != 0:
            raise RuntimeError("Unsupported per-layer input embeddings")

    def new_cache(self):
        return self.model.make_cache()

    def text(self, ids):
        lm = self.model.language_model
        return lm.model.embed_tokens(self.mx.array([ids], dtype=self.mx.int32)) * lm.model.embed_scale

    def audio(self, frames):
        mx = self.mx
        dtype = self.model.embed_audio.embedding_projection.weight.dtype
        out = self.model.get_audio_features(mx.array(frames[None], dtype=dtype), mx.ones((1, len(frames)), dtype=mx.bool_))
        return out.reshape(1, len(frames), -1)

    def forward(self, embeds, cache, length):
        out = self.model.language_model(None, inputs_embeds=embeds, cache=cache, logits_to_keep=1)
        self.mx.eval(out.logits)
        return np.array(out.logits[0, -1].astype(self.mx.float32)), cache


class NativeMind:
    def __init__(self, path, expected_sha, backend="torch"):
        from transformers import AutoTokenizer
        path = pathlib.Path(path)
        if checkpoint_sha(path / "model.safetensors") != expected_sha:
            raise ValueError("Frozen checkpoint hash mismatch")
        self.sha = expected_sha
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        generation = json.loads((path / "generation_config.json").read_text())
        eos = generation["eos_token_id"]
        self.eos = set(eos if isinstance(eos, list) else [eos])
        self.suppress = generation.get("suppress_tokens", [])
        self.top_k = int(generation.get("top_k", 0))
        self.top_p = float(generation.get("top_p", 1))
        if backend not in ("torch", "apple"):
            raise ValueError("Unknown backend")
        self.backend = (TorchBackend if backend == "torch" else AppleBackend)(path)

    def session(self, messages, max_tokens=128, temperature=0, sample_limit=MAX_SAMPLES):
        return AudioSession(self, messages, max_tokens, temperature, sample_limit)


class AudioSession:
    def __init__(self, mind, messages, max_tokens=128, temperature=0, sample_limit=MAX_SAMPLES):
        if not 1 <= max_tokens <= 512 or not 0 <= temperature <= 2:
            raise ValueError("Invalid generation budget")
        self.mind, self.backend = mind, mind.backend
        if not isinstance(sample_limit, int) or not 1 <= sample_limit <= MAX_VOICE_SAMPLES:
            raise ValueError("Invalid audio window budget")
        self.sample_limit = sample_limit
        self.max_tokens, self.temperature = max_tokens, temperature
        prompt = mind.tokenizer.apply_chat_template(messages, tokenize=False,
                                                   add_generation_prompt=True, enable_thinking=False)
        if prompt.count(MARKER) > 1:
            raise ValueError("At most one waveform placeholder is supported")
        self.requires_audio = MARKER in prompt
        left, right = prompt.split(MARKER) if self.requires_audio else (prompt, "")
        self.left = mind.tokenizer.encode(left, add_special_tokens=False)
        self.right = mind.tokenizer.encode(right, add_special_tokens=False)
        audio_budget = (sample_limit + FRAME - 1) // FRAME if self.requires_audio else 0
        if len(self.left) + len(self.right) + audio_budget + max_tokens > 8192:
            raise ValueError("Context exceeds the existing 8192 token budget")
        self.cache = self.backend.new_cache()
        self.length = 0
        self.pending = np.empty(0, dtype=np.float32)
        self.samples = self.audio_tokens = 0
        self.closed = False
        self.started = time.perf_counter()
        self.prefill_seconds = 0
        self._forward(self.backend.text(self.left))

    def _forward(self, embeds):
        started = time.perf_counter()
        self.length += int(embeds.shape[1])
        self.scores, self.cache = self.backend.forward(embeds, self.cache, self.length)
        self.prefill_seconds += time.perf_counter() - started

    def push(self, samples):
        if self.closed or not self.requires_audio:
            raise ValueError("Session is closed or does not accept audio")
        x = np.asarray(samples, dtype=np.float32)
        if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.max(np.abs(x)) > 1:
            raise ValueError("Expected nonempty finite mono waveform in [-1, 1]")
        if self.samples + len(x) > self.sample_limit:
            raise ValueError("Audio exceeds the session window")
        self.samples += len(x)
        self.pending = np.concatenate([self.pending, x])
        n = len(self.pending) // FRAME
        if n:
            frames = self.pending[:n * FRAME].reshape(n, FRAME)
            self._forward(self.backend.audio(frames))
            self.audio_tokens += n
            self.pending = self.pending[n * FRAME:].copy()
        return {"samples": self.samples, "audio_tokens": self.audio_tokens,
                "pending_samples": len(self.pending), "cache_tokens": self.length}

    def finish(self, on_text=None):
        finish_started = time.perf_counter()
        if self.closed or (self.requires_audio and not self.samples):
            raise ValueError("Session is closed or empty")
        self.closed = True
        if len(self.pending):
            frame = np.pad(self.pending, (0, FRAME - len(self.pending))).reshape(1, FRAME)
            self._forward(self.backend.audio(frame))
            self.audio_tokens += 1
        self.pending = np.empty(0, dtype=np.float32)
        if self.right:
            self._forward(self.backend.text(self.right))
        tokens = []
        first_token_seconds = None
        finish_reason = "length"
        for _ in range(self.max_tokens):
            scores = self.scores.copy()
            scores[self.mind.suppress] = -np.inf
            if self.temperature:
                scaled = scores.astype(np.float64) / self.temperature
                top_k = self.mind.top_k
                if 0 < top_k < len(scaled):
                    scaled[scaled < np.partition(scaled, -top_k)[-top_k]] = -np.inf
                p = np.exp(scaled - np.max(scaled)); p /= p.sum()
                if self.mind.top_p < 1:
                    order = np.argsort(-p)
                    remove = np.cumsum(p[order]) - p[order] >= self.mind.top_p
                    p[order[remove]] = 0
                    p /= p.sum()
                token = int(np.random.choice(len(p), p=p))
            else:
                token = int(np.argmax(scores))
            if first_token_seconds is None:
                first_token_seconds = time.perf_counter() - self.started
            if token in self.mind.eos:
                finish_reason = "stop"
                break
            tokens.append(token)
            if on_text:
                on_text(self.mind.tokenizer.decode(tokens, skip_special_tokens=True))
            if len(tokens) < self.max_tokens:
                self._forward(self.backend.text([token]))
        result = {"text": self.mind.tokenizer.decode(tokens, skip_special_tokens=True),
                  "tokens": tokens, "finish_reason": finish_reason,
                  "audio_seconds": self.samples / SAMPLE_RATE, "audio_tokens": self.audio_tokens,
                  "cache_tokens": self.length, "first_token_seconds": first_token_seconds,
                  "first_token_after_finish_seconds": first_token_seconds - (finish_started - self.started),
                  "finish_seconds": time.perf_counter() - finish_started,
                  "total_seconds": time.perf_counter() - self.started,
                  "checkpoint_sha256": self.mind.sha, "native_audio": self.requires_audio}
        self.cache = None
        return result

    def abort(self):
        self.closed = True
        self.cache = None
        self.pending = np.empty(0, dtype=np.float32)
