# Native waveform stream candidate

This candidate sends recordings directly into the frozen mind's own audio projection. It is disabled in the voice lane until `VINTOS_NATIVE_AUDIO_BASE` names an explicit loopback service. The existing photo route is unchanged.

`native_audio_runtime.py` frames mono 16 kHz waveforms into 640-sample tokens. It prefills the left prompt once, appends complete audio frames into the same KV cache, pads only the final incomplete frame, then appends the native turn ending and generates the answer. Live packet windows are limited to eight seconds (200 audio tokens); complete voice recordings retain the existing thirty-second limit (750 audio tokens). Context remains capped at 8192 tokens and reserves the actual recording budget. Cache reuse is within a window; a new window starts a fresh cache. Cross-window sliding retention is not implemented.

`native_audio_server.py` binds only `127.0.0.1`, refuses the household port, verifies the local checkpoint hash before loading, permits one active audio stream, and expires inactive sessions after 30 seconds. It stores no recordings and logs no request bodies or generated words. CUDA is the cloud reference backend; MLX is the Apple backend. No model is downloaded by either backend.

For an operator-controlled Studio acceptance run, use a dedicated environment with `requirements-apple-native.txt` and run the service under the existing GPU lock:

```sh
lockf -k ~/physics-lab/train.lock /path/to/native-env/bin/python \
  studio/native_audio_server.py --backend apple --mind /path/to/local/checkpoint \
  --expected-sha256 989526926b49de244b87dc69ce23949652062a699925c9bdf9dc249116c4079d \
  --port 8844
```

That lock is held for the service lifetime. Coordinate its stop before another heavy GPU job. No launch agent, production service, private pool configuration or household endpoint is installed by this change. A caller on another host needs an explicitly configured private SSH tunnel to this loopback service.

## API

- `GET /health`: checkpoint hash, audio capability and window budget.
- `POST /audio/start`: optional `prompt`; returns `session_id`.
- `POST /audio/push`: `session_id`, `audio` as base64 mono PCM16 at exactly 16 kHz. Arbitrary sample-aligned packet boundaries are supported.
- `POST /audio/finish`: `session_id`; returns generated text, a waveform digest, token counts and measured timing. This releases the cache.
- `POST /audio/abort`: releases an unfinished session.
- `POST /listen`: complete PCM16 recording of at most thirty seconds with `sample_rate` 16000, 24000 or 48000; transcribes with the same mind. The transcription budget scales with duration, up to 512 output tokens.
- `POST /v1/chat/completions`: text messages or one `input_audio` part (`pcm16` with sample rate, or mono `wav`), up to thirty seconds. `stream: true` streams generated text as SSE. Complete recordings are resampled once and prefilled in bulk; live streams append packets as they arrive.

`scripts/native_audio.Stream` is the bounded packet client. It verifies the service and avoids HTTP proxies. `voice_local` uses the same mind's transcription for commands, duplicate handling and turn bookkeeping, while sending the original waveform as an audio part for the actual reply. A native-route failure is explicit. The disabled lane retains its previous behavior.

The voice stage must advertise `external_ears` in its health response before a native call can start. The matching stage change warms its existing voice while skipping the unused audio model. Ending the call still releases the voice. This capability check fails before a legacy stage can warm its old ears.

Auditory records retain the original PCM digest, short transcript, measured acoustics and checkpoint provenance. An absent acoustic reading stays empty. The record-gap rule explicitly says that omitted details were not captured. The existing held-call retention and test-mode rules remain in force.

## Validation and adoption boundary

The cloud bulk/200 ms/irregular-packet replay produced identical tokens on three public development clips. The HTTP test passed identity, session parity, source-reference parity, incremental reply and text-only checks. A paced public recording passed the registered ingestion and post-window decode timing bars. These are public replay tests, not a glasses test.

The native audio projection passed the Apple CPU numerical check (max absolute error 3.82e-6, relative L2 error 1.89e-7). Full Apple model/cache replay also passed: all three public development clips matched CUDA token-for-token for bulk and 200 ms input. The existing GGUF/native projection passed the original vision check at 19/22 with every original pass retained, and its three audio transcripts matched BF16 words. The earlier trained external audio bridge failed its sealed ASR gate and is not used here.

The first complete Studio run executed all 699 suites through the repository's OS-isolated runner: 684 passed; all 15 failures also reproduced on unchanged source. The native route, stream, existing voice, auditory memory and target-admission suites passed. A Linux guest on the cloud pod is being used for the complete Linux test environment. No isolation boundary is weakened.

Before adoption: finish the full Linux run, voice-rate/long-recording compatibility checks, persona/emotion/worm gates, and a real glasses feed check with timestamped evidence. The named decoder has not yet been located in the checked host locations. No merge or deployment is authorized by these pilot results. Review goes through the repository's documented review and owner approval process.
