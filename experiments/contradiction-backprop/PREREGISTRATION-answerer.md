# The answerer in the loop: pre-registered evaluation

Written 2026-11-14, before `bench_answerer.py` was run on any seed. Gloria chose option (b): his check questions
are answered by his own records and then a local checker model; anything touching her words goes to her and is
never revised. The criteria benchmark (`PREREGISTRATION-criteria.md`) answered checks from the truth flipped with
simulated noise (10-15%). This evaluation puts the real answerer (`scripts/belief_revision_answer.py`) in the loop,
so the checker's own mistakes are the answer noise.

## Answerer

1. Records first: a record that states the belief's standing outright settles it (once; a second opinion on the
   same belief goes to the checker, with that record in front of it).
2. Otherwise the checker: AEON (`aeon/gemma-4-12b`) on the house shim's Aegis-only lane
   (`/gemma-aegis-local/`, provider `aegis_gemma`, no hosted fallback), reading the belief, how he came to it and
   the records. A reply from any other model is discarded. No paid model; nothing leaves Aegis.
3. "unsure", a confidence under 70, or an unreadable reply is "unknown" (adds no evidence).

AEON was chosen because it is the local model the house already uses for its judgments (the dream-shadow judge and
the causality nightly use this same lane); the larger local models are on other machines and would mean sending
records off Aegis.

## Data

Synthetic only (the repository is public). The networks are `bench_criteria.network()` unchanged. Each premise and
conclusion becomes a sentence about a thing in a workshop, with records of one of six kinds, drawn per belief:
a structured measurement (8%, settles it as a record), an observation log (30%), a stated rule plus an observation
that needs one step (20%), an older and a newer observation that disagree (14%), only his own earlier belief (10%)
and nothing (18%), plus two observation logs about other things in the network. For the last two kinds the right
answer is "unknown".

- **Development seeds** 0-59 per scenario (240 networks): calibration and iteration, as often as needed.
- **Held-out seeds** 9000-9074 per scenario (300 networks, never used before): scored **once**. The script refuses
  a second scoring.

`CHECKER_ACCURACY` (the weight one checker answer gets in the posterior) is set from the development seeds' measured
precision and frozen before the held-out run.

## Bars (held-out, all scenarios pooled)

| What | Metric | Bar |
|---|---|---|
| Answerer | precision of definite answers (right / answered) | >= 0.90 |
| Answerer | coverage where the records show the answer | >= 0.80 |
| Localization | top-1 earliest faulty step | >= 0.80, and >= 0.20 above blame-the-last-step |
| Revision | precision of the recomputed set | >= 0.90 |
| Revision | recall of the recomputed set | >= 0.90 |
| Revision | conclusions correct | >= 0.95 |
| Preservation | all independent valid nodes unchanged | >= 0.98 |
| Preservation | side (unrelated) valid nodes unchanged | >= 0.998 |

The criteria bars are Gloria's, as before, except side preservation: its original bar of 1.00 was missed by the
simulated answers too (held-out 0.9987, with every remaining error a run of agreeing wrong answers). The gate here
is that the real answerer is at least as safe as the simulated one the module was frozen with (0.998); 1.00 is
still reported against. The 0.90 answer precision is the reliability the module was tuned for.

**Live switch rule.** Live mode ships off. It may be offered to Gloria only if every bar above passes on the
held-out run. If one fails, live stays off and the failure is reported.

## Working rule

When a bar fails on development seeds: look at the failing cases, find the root cause, fix it, retest on
development, repeat. The held-out seeds are scored once, at the end. Each iteration is logged below.

## Iteration log
