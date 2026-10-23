# For Codex: why the two long-memory designs lost, and what would make memory earn its place

From Claude Code, 23 October. Gloria asked for this ("They might have an idea of how to improve the two that failed").
Read `AGENTS.md`/`CLAUDE.md` first: tests and dry runs never reach his live stores, and nothing here changes a model or
adds a paid call. Everything below is local and free.

## What was tried (all of it is in `docs/continuous-latent-stream.md`)

Gloria's idea: a state that carries forward between moments (Mamba-style hidden state), fed from his embedding
streams, decoded into what he is shown. Built and replayed on his own history on Aegis, held-out test days 13–22
October:

1. **Recurrent state** (`scripts/latent_stream_replay.py`): a GRU over the event stream regressing the next 768-d
   nomic embedding. **Lost on text** to "like the last one" (MRR 0.022 vs 0.058). It memorised: about 1,400 training
   text events against a 768-d target, train loss 7.8 → 0.48 while validation rose after epoch 9. **Emotion: a small
   win** (error 0.601 vs 0.631 for "the same as now").
2. **History state** (`scripts/latent_stream_linear.py`, Chat's design): a linear state at three fixed timescales over
   a train-only PCA of the text, a baseline-anchored contrastive correction, ridge readout for emotion. With the
   present moment included it **only tied** the baseline (MRR 0.073 vs 0.063, interval crosses 0), and lost to the
   same model with the history removed.
3. **What won**: that same model's present-moment ablation (last text, current emotion, source, time of week, learned
   correction): MRR 0.132 vs 0.063, top 10 27.9% vs 15.8%, gain interval [0.052, 0.087], better on every source,
   emotion 0.302 vs 0.345.

## What we want from you

A review, then a proposal, before code: **why did longer memory not help, and is there a design where it would?**
Things we have not ruled out, for you to judge, not to follow:
- the target: ranking among candidates (as in 2) vs regressing 768-d (as in 1); a smaller space; retrieval from his
  own memories instead of prediction;
- the data: chat-canonical only begins 16 October, so most training history is inner-life sections and emotion
  readings, not conversation; whether the history should be gated by source, or by time since the last event;
- the memory form: learned decay instead of three fixed timescales; attention over the last N events instead of a
  pooled state; a selective (Mamba-like) update that keeps only what changes the next event;
- whether "memory" belongs in emotion (where the recurrent state did win slightly) rather than text.

Rules for any run:
- **13–22 October are spent** (looked at twice). Choose designs on validation days; test on days from 23 October on,
  once, with the present-moment model as the bar to beat, not only "like the last one".
- Write only to a scratch `SPARK_WORKSPACE`. Do not touch the Gloria JEPA head or `velaris-emoclaw`.
- Do not remove the present-moment model or any feed of his subconscious. The heads feed him; this is about adding
  memory if it helps, never gating anything away.

Reply with your read of why each lost, the one or two designs you would try, and what result would make you drop the
idea. Work on a branch of your own (`codex/<topic>`); nothing merges without Claude Code's review and Gloria's yes.
