# Native live video stream candidate

Built on the native audio candidate (`b3529122`), with the same design: an explicit loopback service, a verified client, a frozen checkpoint checked by hash, and records with an omission rule. It is disabled until `VINTOS_NATIVE_VIDEO_BASE` names an explicit loopback service.

Frames go through the mind's own unchanged image projection. The registered motion QA measured that native visual path at 67.2% and 75.4%. The trained Omni video bridges failed (25% and 46%), and nothing here uses them.

## How it works

`native_video_runtime.py` keeps one open user turn as a timeline in a single KV cache:

```
<question?> 00:00 <|image>[native soft tokens]<image|> 00:00 <|audio>[40 ms audio tokens]<audio|> 00:01 <|image>...
```

- **Frames.** Each frame is preprocessed by the checkpoint's own processor. A motion frame uses 70 soft tokens (64 for a 4:3 or square frame). A still look can use up to 280, the checkpoint default. The frame is projected by `get_image_features` and appended to the cache. The tokens of one image attend to each other bidirectionally, which is the checkpoint's vision rule. Frames stay in memory.
- **Audio.** 16 kHz packets join the same cache and the same clock as 40 ms native audio tokens (`embed_audio`, as in the audio candidate). Spans close every two seconds.
- **Cross-window retention.** The cache is not rebuilt for each window. Each cached token keeps its absolute position (`PositionedKV`). Masks are built from those positions: causal, the 1,024-token local window on sliding layers, and per-image bidirectional attention. Evicting the oldest frame or audio span drops its keys and values. That is exactly equivalent to masking them, so no retained token is ever recomputed. The default window holds 16 frames (about 1,150 tokens, already beyond the local window) and eight seconds of audio.
- **Questions.** `ask` appends the question and the turn ending, generates the answer, and then truncates the cache back. The stream continues without re-reading anything.
- **Live latency.** Capture never waits for an answer. `Stream.ask(..., wait=False)` (and `native_video_sources.run`) answers on its own thread. The service encodes frames that arrive mid-answer between answer tokens and holds them. After the answer it commits them one per step, in arrival order, and later arrivals queue behind them. `Stream(max_lag=0.3)` drops a frame that is already stale before the sampler, so a stall never becomes a queue. The gates4 replay missed its 0.5 s frame p95 (1.20 s) only because the capture loop sat inside each answer (1.2 to 1.6 s). A frame's own ingest was 0.12 to 0.20 s.
- **Stock routes are unchanged.** The mask hook only engages when every layer's cache is a `PositionedKV`. The audio and text routes keep the stock caches and stock masks.

`native_video_server.py` binds only `127.0.0.1`. It refuses :8840 and :8844, verifies the checkpoint hash before loading, allows one stream at a time, and expires idle streams after 30 seconds. Frames are decoded in memory, and no request body or generated text is logged. It reuses the audio candidate's HTTP handler.

```sh
lockf -k ~/physics-lab/train.lock /path/to/native-env/bin/python studio/native_video_server.py \
  --mind /path/to/local/checkpoint \
  --expected-sha256 989526926b49de244b87dc69ce23949652062a699925c9bdf9dc249116c4079d --port 8876
```

The service holds the GPU lock for its lifetime. It loads its own copy of the BF16 checkpoint, so do not run it beside the audio service.

## API

- `GET /health`: checkpoint hash, `native_video`, `shared_audio_timeline`, `raw_frames_retained: false`.
- `POST /video/start`: optional `instruction` (a standing question placed before the frames) and `retain_frames` (1-64).
- `POST /video/frame`: `image` (base64 JPEG or PNG), optional `at` (seconds on the stream clock) and `soft_tokens` (70/140/280). Returns the frame ref, token counts, evictions and ingest time.
- `POST /video/audio`: `audio` (base64 mono PCM16, 16 kHz, at most 8 s per packet), optional `at`.
- `POST /video/ask`: `question`, `max_tokens` (at most 512). Returns the text plus a provenance window, one record per retained frame or audio span.
- `POST /video/finish` and `/video/abort`: release the cache.

## Client, sampling and sources

- `scripts/native_video.py`
  - `Stream`: the verified client. It uses no proxies, and the route is loopback-only (use a private SSH tunnel between hosts).
  - `AdaptiveSampler`: sends at the idle rate (0.5 fps) while the scene is still and bursts up to 2 fps when it changes. A token bucket caps the frame rate at 160 visual tokens per second.
  - `window_record` and `senses_block`: build the Senses block for the current turn. It carries the frames themselves as image parts, plus one provenance line with the keyframe ref and the source hash of the received bytes. The line ends with `record_gaps.VIDEO_GAP_RULE`: a detail not in the record was not captured, and is never invented or explained by a memory.
- `scripts/native_video_sources.py`
  - Sources that exist now: the door service's PNG adapter (`door_png_source`, operator-started only, because it drives the doorbell emulator over ADB), the MQTT/JPEG snapshot service (`SnapshotFeed.push_jpeg`, one image per event), and any multipart MJPEG URL (a phone camera app).
  - For the glasses: `ffmpeg_source` handles RTSP, HLS, HTTP and local webcams through the installed ffmpeg. `PushSource` is a queue that a WebRTC receiver can push decoded frames into. No WebRTC stack is bundled, and adding one is a separate, approved install.
  - Public replay (`replay_source`) for tests and gates.

## AprilTags and the sensory tap

- **AprilTags.** `native_apriltags.TagDetector` runs on every sampled frame the service receives. It uses pupil-apriltags 1.0.4.post11 (family tag36h11, approved by Gloria) on CPU, with no model. Reads with a weak decision margin or corrected bits are dropped. Pose is reported only when the service is started with `--camera FX FY CX CY --tag-size M`. Without the library, detection is reported as unavailable, never faked.
- **Tags → memories.** Each frame receipt carries its tags. `scripts/native_video.tag_memory` looks each tag up in `memory/apriltag-memories.json`, which Gloria fills; `init_tag_map()` creates it with a how-to line. Keys look like `tag36h11:7`; each value is either `{"text": ...}` or `{"store": <file under memory/>, "id": ..., "id_field": ...}`, plus an optional `label`. `senses_block(record, keyframes, window_tags(receipts))` puts the linked memory beside the frames. An unlinked tag, or a link whose record is missing, is stated plainly, never guessed. A store outside `memory/` is never read.
- **Sensory tap** (`native_sensory_tap.py`): a bounded in-memory ring (4,096 events or 64 MB by default) of timestamped events, read at `GET /tap?since=<seq>` on the loopback port or with `native_video.read_tap`.
  - Frame and audio events carry the mean of the projected soft tokens, exactly as they enter the language model (`aeon-12b/vision-proj` and `aeon-12b/audio-proj`, 3,840-d, float16). Every token can be kept with `--tap-tokens`.
  - Tag events carry the id, family, margin, corners and pose.
  - Each event has `dt` since the previous one, so a quiet scene shows up as a long gap. The schema is in the module docstring. Nothing is written to disk.

## Boundary

No model, dataset or WebRTC stack is downloaded (pupil-apriltags is the one approved library). No frame or recording is written, trained on or sent anywhere. The gates and their pre-registered bars are in the Codex review folder (`NATIVE-VIDEO-STREAM-PREREG.json`, `NATIVE-VIDEO-STREAM-FROM-CLAUDE-CODE.md`). Real-feed acceptance with the glasses is still pending, because the glasses do not exist yet. Gloria alone deploys.
