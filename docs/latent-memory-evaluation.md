# Sealed emotion-history evaluation: 23–29 October

**Result: FAIL, with sufficient data.** The unchanged sealed evaluator ran once
on Aegis on 30 October, after 08:00 America/Chicago. Emotion history has the
lowest average error but does not meet the registered 5% improvement requirement
against every comparator, and its adjusted interval crosses zero. No promotion,
refitting, protocol change or feed change follows from this result.

This is an **overlapping/exposed fixed comparison**, not a wholly untouched
no-interim-look confirmation. Claude's 28 October frozen confirmation exposed
incumbent text and emotion scores on 23–27 October. These results must not choose
or confirm a new persistence-sprint design. The separate 31 October–6 November
block and its artifacts were not opened or changed.

## Registered emotion result

Targets use the original 600–720-second horizon, one use per realized reading,
with both origin and outcome inside 23–29 October. All 30 October events are
excluded. Error is MSE normalized by the incumbent's frozen training scales.

| Predictor | Normalized MSE | History error reduction versus predictor |
|---|---:|---:|
| Persistence | 0.199651 | 16.24% |
| Frozen incumbent next-reading forecast | 0.171649 | 2.57% |
| Matched fixed-horizon present-feature control | 0.173412 | 3.56% |
| Present plus emotion history | **0.167235** | — |
| Short-trend extrapolation | 0.534898 | 68.74% |
| Matched LAM-feature ridge control | 0.169254 | 1.19% |

There are **378 targets across all seven target days**, exceeding the registered
minimum of 300. LAM covers **378/378**, so every comparison uses the same rows.
The strongest comparator is LAM: history's 1.19% reduction falls short of 5%.
History also falls short against the incumbent and matched present-feature control.

The registered **98.75% paired day-block interval is [-0.010938, 0.005027]**
in normalized MSE units. This is the minimum comparator-minus-history gain across
all controls on each paired bootstrap draw, using the sealed 10,000 draws and
seed 20261022. A positive lower bound was required; it is negative.

The candidate therefore fails both the practical threshold and interval rule.
This is a terminal result for this sealed evaluation, not insufficient data and
not grounds to extend the window or retune this candidate on it.

## Fixed ancillary result and limits

The exact evaluator also produced its already-registered text comparisons:
207 text targets, incumbent and episodic MRR both 0.178352, last-text 0.057754,
recent-six mean 0.040253. The episodic design remains ineligible and closed as
unsuccessful in development. These ancillary numbers reopen nothing; candidate
pools differ from earlier reports, so cross-report MRR is not a matched comparison.

The exact offline collector produced 6,926 currently admitted events before the
exclusive 30 October cutoff. Current mutable stores do not prove their past
versions or ingestion order; historical availability and continuity labels remain
unproved. This capture does not reconstruct erased or absent records.

## Execution, evidence and review

The durable October 22 bundle supplied the executable, collector, supporting
modules, frozen fits, incumbent and frozen LAM projection. The replay, frozen
checkpoint and incumbent match their manifest hashes; supporting Python files
match the original scratch copy. No current serving code was substituted.
The capture ran offline on CPU with its original write guard. The evaluator ran
under an additional network/subprocess denial and scratch-write guard without
changing the sealed executable. Both commands exited successfully.

The evaluator's exclusive attempt receipt is retained in both durable and original
scratch copies. The one-time automation is now paused. Never rerun this evaluation.
The earlier 03:00 Chicago heartbeat did only read-only checks; capture and scoring
started after the corrected 08:00 guard.

[Aggregate receipt](review-evidence/latent-memory-20261022/evaluation-20261030.json)
contains scores, coverage, hashes and pass rules. Daily diagnostics, source IDs,
private filenames, text, vectors and weights remain outside Git. The private
execution record is under Aegis's durable sealed-experiment parent, in
`evaluation-20261030-1300`; `report/fresh-report.json` contains the original output.

This is a documentation-only result update. The sealed code and tests are
unchanged; the prior full Aegis suite receipt remains 473/473 suites successful
(one optional SDK test skipped). No new suite run is claimed for this report.
Claude Code review and Gloria's yes are still required before any merge.
No deployment, install, send or live-store write occurred.
