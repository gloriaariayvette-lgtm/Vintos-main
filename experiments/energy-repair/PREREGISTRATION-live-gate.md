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

Nothing was iterated; the held-out seeds are scored next, once.
