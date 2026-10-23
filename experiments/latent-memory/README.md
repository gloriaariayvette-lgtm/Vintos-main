# Longer-memory scratch experiment

Implements the reviewed [proposal](../../docs/latent-memory-review.md) with Gloria's
approved change: select regularization with pre-9-October training and 9–10 October
validation, check 11–12 October without reselection, then fit the fixed designs and
controls on all available admitted inputs through 22 October. The incumbent stays
frozen. The two targets have separate selected penalties; each target's controls
use its selected penalty, with no additional control-specific search. The
present-feature emotion control has fixed penalty 10, matching the incumbent's
emotion penalty. Failed development designs are refitted for review but remain
ineligible for promotion; the zero-correction comparator is always reported.

This directory is offline experiment code, deliberately outside the deployment
manifest. There are no runtime feed changes, scheduled jobs, sends, network model
calls or writes to live stores. Training and serialized parameters remain private
scratch artifacts. Only aggregate receipts belong in Git.

## Capture

Set `SPARK_WORKSPACE` and `LATENT_MEMORY_SCRATCH` to the same new private scratch
directory. Use the existing CPU interpreter and frozen local encoder snapshot.
`collect.py` copies only named input stores into scratch, applies the existing
admission rules, bounds the events by local date, and stores a numeric snapshot.
All Python file writes are guarded to that root; network connections are denied.
The original stores are read-only. The `--cache` argument names the existing
text-vector cache; it is read-only and only currently admitted texts are reused.
The LAM argument supplies its earlier frozen feature projection, not a forecast
head to install or change. Its comparator readout is fitted on this experiment's
training rows, with the same fixed 600–720 second target contract.

```sh
python3 experiments/latent-memory/collect.py \
  --source-memory /path/to/source/memory \
  --cache /path/to/existing/text-vectors.jsonl \
  --lam /path/to/private/lam-linear.npz \
  --encoder /path/to/local/encoder/snapshot
```

Do not reuse a failed capture directory: each capture makes a new `memory/` copy.
A current mutable record is not proof of its past version or arrival time.
The snapshot marks that limitation, and the report makes no continuity-label
claim. Same-time observations form an atomic batch during replay; deterministic
ordering inside the committed batch affects only later states, never forecasts
of another event in that batch.

## Develop and refit

With the same scratch environment, choose a new output directory beneath it:

```sh
python3 experiments/latent-memory/replay.py fit \
  --snapshot /path/to/private/events.npz \
  --incumbent /path/to/private/present-moment.npz \
  --out /path/to/private/final-fit
```

The runner rejects a snapshot containing any event on or after 23 October in
America/Chicago. It fits three constrained episodic coefficients, plus centroid,
recent-only and ten source/age-matched random controls. Text temperature and all
incumbent parameters stay fixed. Each target contributes one loss from the state
before its timestamp batch. The emotion experiment fits a history correction to
a frozen present-feature horizon fit, with persistence, incumbent, short-trend
and matched LAM-feature ridge controls. Training losses crossing split boundaries
are excluded. Final refits use all within-cutoff targets, including those earlier
validation days; their development scores are still those of the earlier fits.

Artifacts:

- `development.json`: complete regularization grid, earlier-fit development
  scores, controls, source counts and two-anchor retrieval proxy.
- `development-fits.npz`: the earlier fitted parameters, retained for review.
- `frozen.npz`: the through-22-October fits, including controls.
- `manifest.json`: selected penalties, data/code/checkpoint hashes, exact capture
  coverage, fresh block boundaries, development eligibility and frozen contract.
- `report.json`: aggregate receipt; it contains no scores on 13–22 October.

The two-anchor metric selects from a common past-only bank before reading the
outcome. It is next-text similarity, not evidence that an independently identified
unfinished thread was recalled. Without trustworthy historical link labels,
continuity remains unproved.

## Fresh evaluation

The registered block is **23–29 October inclusive, America/Chicago**. Capture of
that block (`collect.py --through 2026-10-29`) refuses to run before 30 October.
Likewise the evaluator refuses early, before loading fresh inputs. No interim
score check or automatic collection job is installed.

After the block closes, use a new private capture directory. For evaluation,
point the two scratch environment variables at a common private parent containing
the capture, sealed fit and new report directory:

```sh
python3 experiments/latent-memory/replay.py evaluate \
  --snapshot /path/to/private/fresh/events.npz \
  --incumbent /path/to/private/present-moment.npz \
  --sealed /path/to/private/final-fit \
  --out /path/to/private/fresh-report
```

The evaluator requires the exact sealed code and incumbent/checkpoint hashes and
a seal made before 23 October. It creates an exclusive evaluation-attempt receipt
before scoring; a second attempt is refused. An insufficient block is terminal,
not an excuse to extend the window. Keep the sealed executable alongside the
checkpoint. Do not delete the attempt receipt to obtain another look.

Primary contrasts use paired day bootstrap draws and the registered 98.75%
intervals. For sparse LAM coverage, compare both predictors on the same covered
rows, including the 5% practical threshold. No output promotes or installs a
head. Claude Code reviews any next step before a merge.

## Validation

`broker/tests/test_latent_memory.py` runs with synthetic vectors, scratch paths,
stubbed network access and the repository's OS-isolated runner. It covers target
causality, ties, duplicates, bank bounds, controls, constrained fitting, horizon
uniqueness, gaps, split crossing, source removal/rebuild, incumbent state restart,
future-cutoff refusal, no early/repeated evaluation, paired bootstrap behavior,
partial comparator coverage and final fitting after the development freeze.
The full broker-suite receipt is linked from the development report.
