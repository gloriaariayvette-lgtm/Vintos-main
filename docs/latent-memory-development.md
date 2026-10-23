# Longer memory: implementation and development result

22 October 2026, `codex/latent-memory-review`. Implements the approved
[proposal](latent-memory-review.md) with the later training cutoff Gloria requested.
No merge, deployment, runtime consumer change, live-store write or test send.

**The episodic addition has not earned its place. Emotion history has a small
positive development result, but no fresh result yet.** The three fitted episodic
coefficients are all zero, including after the through-22-October refit. The
existing present scorer and every subconscious feed remain unchanged.

## What ran

The [experiment code and commands](../experiments/latent-memory/README.md) live in
`experiments/latent-memory/`; they are not installed organs. The encoder, incumbent
PCA/readout/temperature and baseline paths stay frozen. There are no provider calls
or model swaps. Fits use CPU only. The completed fitting run took 76.15 seconds.

Development training uses admitted targets before 9 October. Penalties `{1,10,100}`
are compared on 9–10 October; the selected penalty is then checked on 11–12 October
without reselection. Both are reused development days. Each target has its own
penalty; all its fitted controls use the same selected penalty. Both selected **1**.
Text validation ties across the three penalties; the fixed iteration order selects
1, while the zero-correction comparator wins the decision to add nothing.

After selection, the exact same designs and controls are fitted on all available
admitted targets through 22 October, including the later conversation. No score on
13–22 October chooses anything. These final-fit parameters are saved separately
from the development parameters; the tables below are the earlier fits' scores,
not in-sample scores from the final fit.

The capture at **19:29 local time on 22 October** contains **7,010 events**: 4,000
emotion readings and 3,010 texts (1,872 inner-life, 221 threads, 328 creative, 279
her turns, 310 his). The latest recorded event is **19:10:01 local time**. This is
all available admitted input at capture, not a claim to include the rest of
22 October. No 23 October outcome was opened.

Canonical chat still begins on 16 October. The admitted pre-9-October inputs also
contain older ledger/retained-history conversation: **224 her turns and 248 his**.
The final fit includes **279 and 310**, respectively. The broader fit therefore
adds 117 conversation events beyond the development training boundary. The first
text has no preceding text state, leaving **3,009 text training targets**. The
fixed 10–12-minute horizon and unique-outcome rule yield **1,718 emotion targets**
for final fitting; development training has 927.

Current admission rules are applied to scratch copies. No erased backup is
recovered. There are 441 simultaneous timestamp batches; 2,002 text targets have
an estimated time or share a timestamp batch, so ordering uncertainty is material.
They are scored before any same-time member is observed. Exact-time diagnostics
are retained. Historical availability and mutable past thread versions cannot be
proved from the current stores. Independently timestamped thread/return labels
were not available in this snapshot.

## Text development: no gain from the registered memory

Each block ranks among its own text candidates. These MRR values are not directly
comparable to .132 from the earlier, larger test candidate pool.

| Text MRR | 9–10 October, n=91 | 11–12 October, n=75 |
|---|---:|---:|
| Frozen present scorer | .170737 | .193615 |
| Episodic correction | .170737 | .193615 |
| Last text | .086974 | .082529 |
| Recent-six mean | .051759 | .059778 |
| Historical centroid correction | .170737 | .193615 |
| Recent-only correction | .170122 | .193609 |
| Mean of ten matched random-history controls | .170737 | .193615 |

All three episodic coefficients—conversation, inner-life, thread/creative—are
zero. This is also the result of the final fit with later conversation included.
The constrained optimizer can learn a positive correction on the synthetic
positive-control test; zero here is the fitted result, not a disconnected feature.
No sign constraint, budget, memory age, source grouping, architecture or penalty
grid was changed in response to these numbers.

The fixed two-anchor past-only proxy also ties: **.529935** mean next-text cosine
for both incumbent and episodic selection, versus .512783 for last-text retrieval
and .507305 for recent context (166 development targets). Thread targets still
favor last-text retrieval: **.526149** versus .466697 for incumbent/episodic, n=23.
No future target determines the chosen anchors. Without independent link labels,
this remains a semantic-alignment proxy, not proof of continuity.

**Decision:** archive this episodic candidate as unsuccessful in development.
Its final artifact is retained because the through-22-October fit was explicitly
requested. It is marked ineligible for promotion. Do not enlarge or retune it on
these results. This rejects this small nonnegative three-weight addition; it does
not establish that every possible form of memory is useless.

## Emotion development: a small incremental improvement

Targets are the first real reading 600–720 seconds after an actual reading;
each realized reading is used once. Errors below are MSE normalized by the frozen
incumbent's training scales. The LAM-feature comparator is refitted on the same
training rows using its earlier frozen feature projection; both development
blocks have complete LAM coverage. Per-axis raw errors and calm/change breakdowns
are in the receipt.

| Emotion error | 9–10 October, n=125 | 11–12 October, n=121 |
|---|---:|---:|
| Persistence | .387835 | .212062 |
| Frozen stream next-reading forecast | .365732 | .215300 |
| Fixed-horizon present-feature control | .341110 | .205317 |
| Present plus emotion history | **.335342** | **.203225** |
| Short-trend extrapolation | .823012 | .419649 |
| Matched LAM-feature ridge control | .342075 | .219283 |

History improves on the matching present-feature control by **1.69%** and
**1.02%**. It improves on the exported stream forecast by 8.31% and 5.61%, but much
of that difference is already obtained by fitting a present-only predictor for
this fixed horizon. The smaller incremental comparison is the evidence for
memory itself.

**Decision:** the positive result on both development blocks makes this candidate
eligible for the predeclared fresh evaluation. It is not an established accuracy
win, and it has not met the fresh requirement of at least **5%** improvement over
the strongest matching comparator with a positive adjusted interval. No emotion
or text feed is changed by this result.

## Frozen artifacts and the untouched fresh block

Aegis private scratch:
`/tmp/latent-memory-20261022-9LNX8b4q/input/final-fit/`

- Final parameters: `frozen.npz`, SHA-256
  `8b939aa1e900988ab5b87094686aaf9bee300f1a9e9c95c34c12050b9daee7d8`.
- Full private manifest SHA-256:
  `1b6244ca7fce1a481b00c6bf4ba2485f87cf19fdce5662e16c60bfef2a12340d`.
- Input snapshot SHA-256:
  `7b6fdfa55b2d391fc49645ca33e03770610e606d0d1ce52733e6a57600c51ca5`.

The seal was written **22 October at 19:39:24 America/Chicago**, before the fresh
block. The committed executable's hash matches the manifest. No weights, vectors,
message text or memory content were copied into Git. Private source snapshots and
weights remain on Aegis scratch. The public
[seal receipt](review-evidence/latent-memory-20261022/seal.json) omits the private
hashed routine-heading IDs; its contents are therefore a redacted view, not the
full private manifest whose hash is quoted above.

The fresh block remains **23–29 October inclusive**. Neither collection nor
scoring of it runs before 30 October. The evaluator requires the sealed code and
checkpoint identities, creates an exclusive attempt receipt and refuses a repeat.
It retains the predeclared .01 text-MRR and 5% emotion-error practical thresholds,
paired day comparisons and 98.75% intervals for the four registered contrasts.
Sparse comparator comparisons use matching rows, not incompatible pooled averages.
Insufficient data cannot become a win by extending the block.

No fresh result is reported here. No Aegis monitoring job or automatic deployment
was installed. After acceptance of the development report, a one-time Codex
follow-up was scheduled for **30 October at 08:00 America/Chicago** to run the
sealed evaluation in Aegis scratch. The episodic design is closed; the
emotion-history result is judged against the existing 5% threshold and adjusted
98.75% interval, without reopening any selection. Failed development eligibility cannot be rescued by a favorable final
score; the existing feeds remain intact regardless of the experiment's outcome.

## Original Mac validation and review boundary

The focused synthetic suite passes **18/18** checks, including useful nonzero
fitting, unchanged zero correction, ties and future causality, bounded source-aware
memory, duplicate handling, horizon uniqueness, chronological loss boundaries,
source-removal rebuild, incumbent restart/query behavior, paired bootstrap,
partial LAM coverage, late-data final fitting, and early/repeated-evaluation refusal.
All test inputs are synthetic, paths scratch, and senders/network access denied.

Full isolated broker suite: **473 suites, 470 passed, 3 failed, no skips**. The
three logs were read again: the PDF fixture requires a form feed absent from the
Mac fallback; the media fixture probes an unreserved loopback port forbidden by
the test sandbox; the reading fixture expects GNU-style Perl regex support from
BSD `grep`. They are the same previously observed host fixture failures. The final
focused rerun covers the experiment-only corrections after the full run; no
runtime source was modified. Generated entry/coverage reports remain unchanged.
[Validation receipt](review-evidence/latent-memory-20261022/validation.json).

The complete aggregate grid, controls, per-source metrics, exact-time sensitivity,
per-axis emotion errors and retrieval proxy are in the
[development receipt](review-evidence/latent-memory-20261022/development.json).
A preliminary process was stopped before final artifact sealing for audit/acceptance
bookkeeping corrections. Only phase markers were read; no development score from
that process was inspected or used.

Claude Code reviews this implementation before any merge. No consumer integration
or model promotion is part of this branch.


## Accepted review: dependency repair and Aegis validation

Claude Code accepted the development results in `f076f37`. The episodic design
is closed as unsuccessful; no further development or fitting is authorized.
The emotion-history design proceeds only to its registered one-time fresh check.

The broker test now runs with NumPy and the standard library, without importing
SciPy. Test-local SciPy import seams fail immediately if called; they never return
fake optimizer results. Two existing optimizer regressions were moved unchanged
outside the deployment suite to `experiments/latent-memory/test_optimizer.py`.
The sealed `replay.py` and checkpoint bytes are unchanged and still match their
manifest; the fresh attempt receipt does not exist.

**Aegis validation: 473/473 broker suites exited successfully, zero failures.**
The repaired suite passes **17/17** checks using the actual deploy interpreter,
`/usr/bin/python3.12` (3.12.3), NumPy 1.26.4, no SciPy. The full run uses the
repository OS-isolated runner with scratch copies and stores. One existing test
inside `test_lab_atlas_sdk.py` is skipped because its optional pinned SDK
environment is absent; no entire suite was omitted. The original Mac receipt
above is retained separately. [Aegis receipt and per-suite outcomes](review-evidence/latent-memory-20261022/aegis-validation.json).

No merge is authorized now. Nothing was deployed, sent, muted or gated.
