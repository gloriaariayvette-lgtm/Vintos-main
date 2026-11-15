# The exact solver as the live repair chooser: pre-registered regression gate

Written 2026-11-14, before `gate_live.py` was scored on any held-out seed. Gloria approved the exact solver for the
nightly contradiction repairs: "keep my words unchanged, preserve a reversible history while in testing (1 week…),
and the normal regression gate." This is that gate.

## What is compared

Live today (`belief_revision_live.py run`, BELIEF_REVISION=live) asks the check questions (`belief_revision.localize`,
answered by `belief_revision_answer`: records first, then local AEON) and applies belief_revision's own final plan
("old"). With BELIEF_REVISION_SOLVER=exact it asks the same questions and gets the same answers, then applies
`belief_revision_verify.choose` ("exact"): the proved minimum-energy repair over what may be revised. Her words are
bound out of that program (never in the repair, only flagged), and what is recomputed is exactly what no longer holds
once the repair is given up.

On every network below, both choosers repair the same network after the same checks and the same answers, and both
are scored by the benchmark's own scorer:

| benchmark | answers | held-out seeds | networks |
|---|---|---|---|
| criteria (`contradiction-backprop/bench_criteria.py`) | the truth, flipped at 10-15% | 5000-5149 x 4 scenarios | 600 |
| answerer (`contradiction-backprop/bench_answerer.py`) | records, then AEON, from the checker cache only | 9000-9074 x 4 | 300 |
| energy-repair (`energy-repair/bench.py`, checked track) | the cached post-check networks | 7000-7059 x 11 | 660 |

The answerer benchmark sends nothing: a prompt that is not in the checker cache is answered "unknown" for both
choosers alike, and the number of such misses is reported.

## The gate (pooled "all", per benchmark)

Gloria's three criteria. The exact chooser must not fall below the old one by more than noise, where noise is the
margin already used in this experiment's H2 (PREREGISTRATION.md):

| criterion | metric | pass if exact >= old minus |
|---|---|---|
| 1 localization | earliest faulty step found (each benchmark's own localization score) | 0.02 |
| 2 revision | recall of what was really wrong | 0.02 |
| 2 revision | precision of what was recomputed | 0.02 |
| 2 revision | conclusions correct | 0.02 |
| 3 preservation | independent valid reasoning left unchanged | 0.005 |

and, absolutely:

- preservation of the exact chooser >= 0.99 on every benchmark;
- her words revised by the exact chooser: 0 on every network.

The gate passes only if every line passes on every benchmark. If it fails, the solver is not switched on, and the
failure is reported to Gloria.

## Working rule

Development seeds (criteria 0-119, answerer 0-59, energy-repair 0-39) may be run as often as needed; any change is
logged below with its root cause. The held-out seeds are scored once (`gate_live.py --split test` refuses a second
scoring) into `results-live-gate.json`.

## Development log

**Dev run 1 (the chooser as first built, no change after it).** Gate PASS on every benchmark; no fallback, no
checker-cache miss, her words revised 0 times by either chooser.

| benchmark | localization old / exact | recall | precision | conclusions | preservation |
|---|---|---|---|---|---|
| criteria (480) | 0.902 / 0.895 | 0.949 / 0.967 | 0.971 / 0.966 | 0.978 / 0.985 | 0.9939 / 0.9928 |
| answerer (240) | 0.853 / 0.847 | 0.920 / 0.982 | 0.973 / 0.959 | 0.972 / 0.986 | 0.9945 / 0.9907 |
| energy (440) | 0.752 / 0.823 | 0.810 / 0.976 | 0.989 / 0.974 | 0.948 / 0.987 | 0.9967 / 0.9931 |

A held-out run was then started and stopped before it wrote or printed anything (no held-out number was seen),
because an independent review found real problems in the chooser as built:

1. it ignored what plan() HOLDS back - a revision resting on a single check answer, or a weak suspect of a
   contradiction whose question went unanswered - which is a live limit;
2. it withdrew everything resting on any revised source, even one only lowered a little (plan() lowers dependents in
   proportion and withdraws only when their standing halves);
3. it could choose sources live can never change (self-model entries, records), so the repair applied was not the
   minimum;
4. it flagged her words to her whenever the unconstrained minimum named them, even at low blame;
5. the gate did not fail on checker-cache misses.

Fixes: held sources stay held (see below); rederive is plan()'s own rule over the solver's revised set; live passes
choose() a test of what it can actually apply (target()), and everything else is bound out of the program; her words
are flagged from the unconstrained minimum only at blame >= FLAG_AT (plus everything plan() flagged); the gate now
also requires zero checker-cache misses on the answerer benchmark (`every_answer_from_the_cache`), the checker URL is
pinned to the one the cache was filled with, and a held-out run leaves a marker before it starts so it cannot be
re-run. The bars and margins are unchanged.

**Dev run 2 - held sources bound out of the program ("bound").** criteria and answerer pass; energy-repair FAILS:
precision 0.967 vs 0.989 (margin 0.02) and preservation 0.9916 vs 0.9967 (margin 0.005). Root cause: forbidding the
held source makes the program pick a costlier alternative that is often a valid neighbour - the same failure the
experiment saw when the solver was made to ignore single-answer repairs.

**Dev run 3 - held sources removed from the solver's repair after it is found, and left held ("flag", the final
rule).** Gate PASS on every benchmark; no fallback, no cache miss, her words revised 0 times.

| benchmark | localization old / exact | recall | precision | conclusions | preservation |
|---|---|---|---|---|---|
| criteria (480) | 0.902 / 0.895 | 0.949 / 0.954 | 0.971 / 0.967 | 0.978 / 0.978 | 0.9939 / 0.9932 |
| answerer (240) | 0.853 / 0.839 | 0.920 / 0.916 | 0.973 / 0.973 | 0.972 / 0.971 | 0.9945 / 0.9945 |
| energy (440) | 0.752 / 0.753 | 0.810 / 0.829 | 0.989 / 0.982 | 0.948 / 0.951 | 0.9967 / 0.9956 |

Keeping the hold costs most of the solver's gain seen in the experiment (energy-repair recall +0.02 instead of +0.17
in run 1): the single-answer hold, not the chooser, is what limits recall there. It is kept because it is a live limit;
lifting it is Gloria's decision. What the gate does not simulate, for either chooser alike: the five-a-day cap, and
target()'s refusals (synthetic ids do not name his stores).

The chooser is frozen here and the held-out seeds are scored once.
