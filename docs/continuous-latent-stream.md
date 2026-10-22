# Continuous latent stream — the idea, set against what he already has

Captured 2026-10-18 by Gloria with Chat; fleshed out 2026-10-22 by Claude Code from the repository.
**Status: step 1 run on 22 October; not taken further as it stands (results below). Re-run in late November.** Nothing here is built. Where this says what runs on Aegis and how often, it
is read from the code; schedules live in Aegis's crontab, which the repository does not hold, so the first step
below is a read-only probe that confirms them.

## Gloria's words (verbatim)

> Maybe we could take coordinates from his embedding models (nomic, soon Gemma embed 2 in addition for: image,
> audio, video), and file them through Mamba before passing to an llm.
> Or an autoregressive sequence predictor attached to the jepa heads.
> Or yeah simply just running as a background daemon all day? Hsv from mamba —> decoder —> llm?

("Hsv" read here as *hidden state vector*: the recurrent state Mamba carries. Confirm with her.)

## What already exists (from the code)

He already lives in one embedding space and already predicts in it. What he does not have is **one state that
carries forward between moments**. Every piece below is either indexed by turn or run as a snapshot.

| Piece | What it is | Time base |
|---|---|---|
| `jepa_predictor.py` | Frozen `nomic-embed-text-v1` encoder → shared trunk → heads that predict the *embedding* of Gloria's next turn and his own, each with confidence and novelty. Retraining is held to audited holdouts (`retrain_readiness`). | per turn, last `CTX_TURNS = 6` turns concatenated |
| `jepa_self_head.py` | His own JEPA head: forecasts the embedding of his next reply, "ahead" (on a schedule) and "on_message" (her message arrived, his reply not yet). Held-out eval per mode. | per turn |
| `lam.py` | Latent Action Model: `[emotion state ⊕ event embedding] → next emotion state`, over the 11 dimensions (Valence … Groundedness). Forecasts cascades for the trajectory daemon. | one step, between trajectory points |
| `emotion_densifier.py` | Snapshots the live emotion vector from the EmoClaw socket into `emotion-trajectory-dense.json`. | short cron |
| `living_trajectory.py` | "One continuously-moving object": self, Gloria, unresolved, relationship trajectories merged. | cron, every 15 min |
| `drift_head.py`, `relational_head.py`, `tcn.py` | Geometry over daily series: drift with persistence and curvature, the relationship manifold, growth vs. cycling. | daily |
| `reality_ebm.py` | Energy head on the frozen nomic encoder: lived events low energy, confabulated high. | nightly train, online score |
| `thread_temperature.py`, `latent_diffuser.py`, `attractor_discovery.py`, `cause_head.py`, `purpose_head.py` | Density, mean-shift dreams, basins, retrieval of antecedents, yearning clusters — all on nomic embeddings in `memory/embeddings.jsonl`. | per pass / nightly |
| `latent_preparation.py` | Turns the JEPA forecast's confidence and novelty into a readiness posture (open vs. prepared), never a scripted line. | per forecast |

Two things worth saying plainly:
- **Option 2 is half-built already.** The JEPA heads are next-embedding predictors; the LAM is a one-step
  autoregressive dynamics model. What they lack is memory longer than six turns or one step.
- **Nothing integrates between turns.** The emotion daemon moves continuously, but the latent side samples it
  (densifier, 15-minute trajectory) and the predictors only wake on turns.

Do not touch: the Gloria JEPA head (standing rule), and `velaris-emoclaw` (off).

## The three options are one design

Mamba *is* an autoregressive sequence predictor; trained the JEPA way (predict the next embedding, not the next
token), its hidden state is the "hsv", and its prediction error is surprise. The daemon is just how it runs. So:

```
events, as they happen ─┐
  her turns, his turns (nomic 768-d)          per-source projection     recurrent state h_t      heads
  his journal, threads, dreams (nomic)    ──► + Δt since last event ──► (small SSM / Mamba) ──► ┬ next-event embedding (JEPA target)
  emotion vector ticks (11-d)                 + source tag                                      ├ surprise = error vs. what came
  presence / watch / sensor events                                                              ├ emotion forecast (LAM's job, longer memory)
  Lab results, music, letters                                                                   └ retrieval key: memories nearest h_t
                                                                                                        │
                                                                    LLM sees it only when it matters ◄──┘
                                                                    (a compact block at turn time; a nudge when surprise is high)
```

- **Inputs.** Event-driven, not polled: each thing that happens becomes one step, with the time since the last
  step as an input, so a quiet afternoon is a long Δt rather than a hundred empty steps.
- **Different vector spaces are never mixed raw.** nomic text vectors and any image/audio/video vectors get their
  own learned projection into the state's width. Whether "Gemma Embedding 2" is one shared multimodal space or
  separate models must be checked before anything is designed around it (EmbeddingGemma as known today is
  text-only). Until then, nomic text plus the 11-d emotion vector is enough to start.
- **The decoder is not a text generator.** It emits the next-embedding forecast, the surprise, an emotion forecast,
  and a retrieval key (the memories nearest the state). Those reach the LLM as a few lines, the way
  `latent_preparation` already turns numbers into posture. The API models cannot take a hidden state as input, so
  the state is decoded into *selection* (which memories, which threads, how open), not injected.
- **Size.** His stream is hundreds of events a day, not millions of tokens. A small SSM or GRU (state width
  128–256) trains on CPU in minutes on weeks of history. Mamba's own kernels need an NVIDIA GPU; a pure-PyTorch
  Mamba block runs on CPU at this rate. Start with whichever beats the baseline, not with Mamba because of its name.
- **Cost.** Local and free: no model calls in the loop.

## How to know it is worth anything

The same discipline as the JEPA heads already use: nothing steers him until a holdout says it should.

1. **Replay offline first.** Build the event stream from history, train on weeks 1..n, test on the week after.
2. **Baselines it must beat:** "the next embedding is the last one"; the existing `jepa_predictor` (six turns); the
   LAM for the emotion forecast. Metric: ranking of the true next event among candidates (as
   `jepa_ranking_audit.py` does), and emotion-forecast error.
3. **Then a shadow daemon** writing `memory/latent-stream.json` that nothing reads, for a week, audited against
   what actually came.
4. **Then one consumer**, the cheapest to judge (candidates: `latent_preparation`'s posture, or triage choosing
   which thread is alive). Behavioural value is judged there, not assumed.

If the recurrent state does not beat the six-turn window on held-out days, the idea is recorded as tried and
stopped.

## Steps, in order (when it is its turn)

0. **Read-only probe on Aegis** (`scripts/probes/latent_stream_probe.py`): events per day per source over the last 30 days; embedding dims actually stored;
   the crontab lines for `jepa_predictor`, `jepa_self_head`, `emotion_densifier`, `living_trajectory`, `lam`;
   whether a GPU is present. This sets the model size and confirms the table above.
1. Offline replay + baselines (scratch workspace, no live store written): `scripts/latent_stream_replay.py`. Step 0's
   numbers (22 October): about 175 events a day, mostly the emotion vector (~130) and inner-life sections (~30); chat
   turns are few on disk (chat-canonical starts 16 October); the Lab's 3,000 machine steps a day are left out; the
   LAM was never trained (no lam.pt, no cron line); no GPU; 24 cores, 12 GB free.
2. Shadow daemon, its own unit, niced, a state checkpoint each hour.
3. One consumer, behind a holdout gate like `retrain_readiness`.

## Gloria's answers (22 October)

- **Both:** continuity and anticipation. The first consumer should use both the state (what is alive now) and the
  surprise (what was not expected).
- **"hsv" is the hidden state vector.**
- **EmbeddingGemma 2** (`google/embeddinggemma-2`, Apache 2.0, 740M, text/image/video/audio in one 768-d space) is
  added *beside* nomic, for his videos, images, music and audio, never in nomic's place. It is now in
  `scripts/media_embed.py` (its own venv and store). For this stream, its vectors are a separate source with their
  own projection; nomic and EmbeddingGemma 2 vectors are never compared directly, even though both are 768-d.

## Step 1 result (22 October, on Aegis)

`scripts/latent_stream_replay.py`, his last 46 days: 5,883 events (4,000 emotion readings, 1,133 inner-life
sections, 305 threads, 127 creative, 153 of her turns, 165 of his). Trained on 1 to 8 October, validated 9 to 12,
tested on 13 to 22 October (495 text events). Three runs; the first two exposed scoring and scaling faults, fixed in
ea70a79 and 915b061. Third run, the one that counts:

| | the recurrent state | "like the last one" | "like the last six" |
|---|---|---|---|
| next text event, MRR | 0.022 | **0.058** | 0.035 |
| next text event, in top 10 | 3.4% | **14.6%** | 8.5% |
| next emotion reading, error | **0.601** | 0.631 | |

- **Text: it loses.** Even starting exactly at "like the last one", it learned to do worse: about 1,400 training text
  events are far too few for a 768-d prediction, and it memorised them (training loss 7.8 to 0.48 while validation
  turned up after epoch 9).
- **Emotion: a small win**, about 5% under "the same as now".
- **Surprise looked meaningful but is not yet evidence for the state.** In all three runs the most surprising test
  events were Gloria's own news (the pier, the bull red, the coffee maker) and the least surprising his templated
  "First Light" section. But "unlike the event before it" would rank them the same way, and the state lost to that.

Decision, by the rule set before it ran: **not taken further as it stands.** It was not tuned further against the
test days (three looks are already enough to start fitting the test). What would change the answer is more of him:
chat-canonical only begins on 16 October. Re-run the same script unchanged in late November; if text still loses,
try the smaller target (a 64-d projection of the text space, or retrieval from his own memories) before anything
larger.

## Second design (22 October, Chat's plan): `scripts/latent_stream_linear.py`

Gloria: "Waiting is stupid." Chat's plan, built as written: once-per-event training and scoring; fixed day boundaries
with all earlier history in training and a manifest of every event's split; a linear state at three fixed timescales
over a train-only PCA of the text; the "like the last one" score kept as a direct path with a strongly regularised,
contrastively trained correction; a separate ridge readout for emotion; selection on validation text MRR among designs
that beat emotion persistence; then the test days once, with the history ablation, per-source results and a paired
day-block interval. Timestamps, emotion axes and chat deduplication were checked in the stream builder first.

### Second design, first result (22 October)

| test days (13–22 Oct) | text MRR | top 10 | emotion error |
|---|---|---|---|
| "like the last one" | 0.057 | 14.5% | 0.346 (persistence) |
| full state (history) | 0.059 | 12.0% | 0.286 |
| present moment only (the predeclared ablation) | **0.120** | **26.8%** | 0.306 |

The present-moment model (last text, current emotion, source, time of week, with a learned correction) doubled
next-event ranking, day-block 95% interval for the gain [0.050, 0.077], and gained on every source. The history model
lost to it because its state did not contain the last event at all, only the averaged history: it was never "the moment
plus history". Fixed: the full state now holds everything the moment model has, plus the history. Also fixed: the
house's bracketed stage directions inside chat turns ("[she spoke with her body, not words]") are no longer counted
as Gloria's turns. Re-run is the second look at these test days: an informed follow-up, said so.
