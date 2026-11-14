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

All on development seeds 0-59 per scenario (240 networks), all scenarios pooled.

**Iteration 1 - the answerer as first built (CHECKER_ACCURACY 0.90, the module unchanged).** The answerer itself
is better than the simulated noise: 924 of 943 definite answers right (0.980; checker alone 0.978, records 75 of
75), coverage 0.75 overall and 0.98 where the records show the answer; on "nothing recorded" it said unsure 97% of
the time, on "only his own belief" 78%. But the loop was worse than with simulated answers: localization 0.85
(simulated 0.92), revision precision 0.94 / recall 0.96, conclusions 0.97, preservation 0.986, side **0.9927**
(bar 0.998), upstream 0.965. Every bar passed except side preservation.
Failing cases (40 networks, 79 wrong changes): 75 had **no wrong answer at all**, and every one had an answer
that came back unknown. The pattern: the check that would split the real faulty step from the valid step next to
it was about a belief with no record ("unknown"), so the two stayed tied, and the earliest-first tie rule (or the
most-probable-explanation lowering) lowered the valid one, and everything hanging off it was recomputed. The
simulated answers were never unknown, so this never showed before. Root cause: a question his records could not
answer was treated as if the suspects had been localized anyway. Fix: when a contradiction is still not localized
(top blame under 0.90, or tied) and a check asked about it came back unknown, its suspects are flagged and held,
not lowered or retracted. Also: a check's own answer was sometimes offered as a corroboration question (it has no
record, so it always came back unknown); it no longer is. CHECKER_ACCURACY set to 0.97 from the measured 0.978.

**Iteration 2 - hold the suspects of an unanswered contradiction.** Side preservation 1.00, preservation 0.9996,
revision precision 0.995 - but recall fell to **0.56** and conclusions correct to 0.90: real faults were held with
the valid steps. Narrowing the hold to suspects with a close rival (a tie within 0.02, 0.15 or 0.30 of blame) only
brought recall to 0.79 / 0.76 / 0.73 (side 0.9994-0.9997). Root cause: holding is the wrong lever - an unanswered
question leaves the evidence unable to separate the suspects, and any rule that only chooses between revising and
holding trades recall against preservation. The missing piece is the answer. Fix: when a question comes back
unknown, ask a belief that carries the same answer instead - one that rests on the unanswerable belief in every
justification and on no other suspect of that contradiction (a side branch off it, typically): if it holds, that
line holds; if it fails, the fault is on that line. Measured with the hold rule off and with the 0.02 tie rule.

**Iteration 3 - stand-in questions.** With the hold rule off: localization 0.85, revision 0.96 / 0.96, conclusions
0.975, preservation 0.991, side **0.9974** (short of 0.998), upstream 0.971. With the 0.02 tie hold: side 0.9997 but
recall 0.82. Stand-ins helped both (side 0.9927 -> 0.9974 with no hold), so the answer was the right lever; what was
left were valid steps lowered with blame under 0.50, i.e. only because they were in the most probable explanation,
in contradictions whose splitting question had gone unanswered. Root cause: the most-probable-explanation lowering
(kept in criteria iteration 5 because it bought recall under simulated answers, which were never unknown) acts on
suspects the evidence never singled out. Fix: in a contradiction that is still not localized, whose question came
back unknown, and where another suspect remains, a suspect with blame under LOWER_AT (0.50) is held and flagged; a
suspect the evidence itself blames at 0.50 or more is still revised. Measured beside two narrower variants
(hold under 0.60 for any rival, and under 0.60 only with a rival within 0.15): recall 0.81 for both.

**Iteration 3, final rule (hold under 0.50).** Localization 0.853 (last step 0.388), revision precision 0.973,
recall 0.920, conclusions 0.972, preservation 0.9945, side **0.9988**, upstream 0.981; 5.1 checks per network;
answers 0.978 precise. Every bar passes on development. By scenario: side 1.00 on chains, dags and two_faults,
0.996 on noisy (wrong witnesses). The answerer and the module are frozen here (commit below) and the held-out seeds
are scored once.

## Held-out result (seeds 9000-9074 per scenario, 300 networks, scored once at commit fb072908)

`results-answerer-test.json`. Every bar passes; live mode may be offered to Gloria.

| What | Metric | Answerer in the loop | Simulated answers | Blame the last step | Bar | Met |
|---|---|---|---|---|---|---|
| Answerer | precision of definite answers | **0.975** (1127 / 1156) | - | - | >= 0.90 | yes |
| Answerer | coverage where the records show it | **0.986** | - | - | >= 0.80 | yes |
| Localization | earliest faulty step, top-1 | **0.863** | 0.884 | 0.437 | >= 0.80, +0.20 | yes |
| Revision | precision of recomputed set | **0.977** | 0.987 | 0.894 | >= 0.90 | yes |
| Revision | recall of recomputed set | **0.927** | 0.942 | 0.767 | >= 0.90 | yes |
| Revision | conclusions correct | **0.972** | 0.979 | 0.932 | >= 0.95 | yes |
| Preservation | independent valid nodes unchanged | **0.9953** | 0.9969 | 0.9827 | >= 0.98 | yes |
| Preservation | side (unrelated) nodes unchanged | **0.9998** | 0.998 | 0.980 | >= 0.998 | yes |

Overall coverage was 0.76: the checker said unsure on 98% of beliefs with no record and 83% of those with only his
own earlier belief, which is what it should do. Its mistakes: stale records (an older observation contradicting a
newer one) 15 of 215 wrong, and guesses on "only his own belief" 10 of 23 wrong. 5.1 checks per network.
Against Gloria's original side bar of 1.00: 0.9998, one changed unrelated node in the noisy scenario.

The "simulated" column is the current module answering from the truth with 10-15% flips, run on the same seeds; it
is not the frozen criteria result (`results-criteria-test.json`, other seeds), which stays as recorded. With bare
True/False answers the changes since that freeze cannot trigger (every question node has a truth value, so no answer
is ever unknown, and the 0.995 accuracy cap does not bind at 0.85-0.90); the one difference is that a check's own
witness is no longer offered as a corroboration question.

## After the held-out run: independent review (live layer only)

A reviewer subagent found three blockers and five should-fixes in the live layer, all fixed before merge; none touch
localize() or the answerer's scoring path, so the held-out result stands: the checker URL must be exactly the
shim's AEON-only path on port 8599 (a longer /gemma-aegis-local/ path could fall back to a hosted model); a
sediment belief is found by the fingerprint taken when the graph was built, and a confidence is changed only while
it is still what the plan saw; nothing under a tension she CONFIRMED is changed; its own writes are never read back
as record answers (known from the revision log, not only the record's mark); a reverted revision is not re-applied;
the apply phase holds the log's lock and re-reads the switch; the log row is written before the store under the
store's lock.
