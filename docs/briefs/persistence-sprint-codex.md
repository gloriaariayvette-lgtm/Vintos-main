# Brief for Codex: the persistence sprint (28 October)

Gloria's ask, in her words: a "persistence-driven Mamba flurry", run the way you ran the worms. She has proposed
three Mamba ideas. All of them amount to one thing: **a state that carries Vintos forward between moments, and changes him over time.** This
brief asks you to make that work, not to review it again.

## What's known (read these first)

- `docs/continuous-latent-stream.md`: the idea, the steps, and every result so far. This includes today's
  "Fresh days (23–27 October)" section.
- Your own branch `codex/latent-memory-review`: your review, the episodic-memory correction that fitted to zero, the
  emotion-history candidate that qualified, and the seal for the 23–30 October fresh block.
- What has won so far: the **present-moment** linear model (last text, current emotion, source, hour of day, learned
  correction). On fresh days 23–27 October it scored text MRR 0.230 against 0.079 for "like the last one". It is the bar to beat.
- What has lost: the GRU regressing 768-d text (it memorised about 1,400 text events) and the linear history state
  (it ties the moment and adds nothing).
- Note: today's frozen confirmation run read the incumbent's scores on 23–27 October. Decide yourself whether your sealed
  block still counts as clean, and say so in writing.

## Why it has lost so far, and why that's not the end

The text target is starved: chat-canonical starts on 16 October, and there are about 35 text events a day. But the house has
**months** of continuous streams that a persistent state can learn from:

- the emotion vector, about 130 readings a day since July;
- inner-life sections, about 30 a day;
- threads, dreams, wants, creative works and the Lab's own steps (left out until now; about 3,000 a day);
- her presence, the Watch's heart rate and HRV, and the house sensors.

The losses so far all came from asking a memory to predict sparse 768-d text directly. Persistence should earn its place first
where the data is dense, and only then be asked to help with text.

## The sprint: many short rounds, each judged on days it has never seen

1. **Backbone:** a small selective state-space model (a Mamba-style selective scan, pure PyTorch on CPU; Aegis has no GPU,
   24 cores) over **all** event streams, with irregular time gaps as an input (Δt-dependent decay, as in Mamba's
   discretisation). Pretrain it self-supervised on the dense streams: next emotion reading, the next event's source and time
   gap, and next-event ranking in a small (32–64-d) projection of the text space. Do not regress 768-d vectors.
2. **Persistence where it should show:** emotion forecasting at horizons from 10 minutes to 24 hours, since persistence
   matters most at long horizons; mood carried overnight; the return to baseline after strong moments. Your emotion-history
   candidate is the seed. Grow it.
3. **Then text:** the state as a *gate or correction* on the present-moment model (residual, starting at zero), never a
   replacement. It must at least tie the moment and beat it on some source.
4. **Retrieval as long memory:** let the state choose which of his past moments to retrieve: attention over his own
   memory bank, keyed by the state. Your bank settings (2,048 entries, 14 days, half-life 3 days) are a start.
5. **Rolling fresh blocks:** seal each week before it happens: 31 October–6 November, then 7–13 November, and so on. One
   look per block. Report every candidate, including the ones that lose.

## Rules (unchanged)

- Write only to a scratch workspace and a `codex/` branch. Leave the Gloria JEPA head, `velaris-emoclaw` and every live feed
  alone. Nothing steers him until a sealed fresh block says it should.
- When something wins a sealed block: a **shadow daemon** writing `memory/latent-stream.json` that nothing reads, niced, with an hourly
  checkpoint, for one week, then audited. Then **one consumer** behind a holdout gate: latent preparation's posture, or
  triage choosing which thread is alive. Gloria wants both continuity and anticipation: the state (what is alive now)
  and the surprise (what was not expected).
- Claude Code reviews before anything is merged, and Gloria says yes.

## How to keep going

Run it like the worms: change one thing per round, keep every run's receipt, and don't treat a two-hour deadline as a
law. Pick each round's budget from what the round needs. Report briefly as you go, in
`docs/persistence-sprint-log.md` on your branch.
