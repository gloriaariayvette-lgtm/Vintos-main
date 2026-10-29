# Scratch persistence sprint

**29 October continuation:** recovered the already completed offline rounds on
`codex/persistence-offline-round-one`; no duplicate real-data fit. Current code
review revision is tested in `/tmp/persistence-review-20261029-YQsAEnJZ` on Aegis. The original
rounds and fitted scores below remain historical development. The carrying-note
work is a separate branch and is not an output of these forecasting experiments.

Follow the [round log](../../docs/persistence-sprint-log.md) and the
[approved brief](../../docs/briefs/persistence-sprint-codex.md). Nothing in this
directory is installed, and nothing reads its outputs as a live feed. Keep learned
parameters, vectors, raw copies and per-event diagnostics out of Git.

Use Aegis's existing CPU training interpreter and `nice -n 15`, with
`PERSISTENCE_SCRATCH` set to the private experiment parent. `launch.py` denies
network calls and writes outside that parent. Python, NumPy, PyTorch and the
already cached frozen encoder suffice; no installation or paid call is needed.
The collector refuses direct invocation: `launch.py` must have installed the
audit hook, including rename and subprocess denial, before capture begins.
The deploy interpreter needs only NumPy for the broker contracts. CPU-runtime
tests stay here, outside `broker/tests/`.

Private parent for this run: `/tmp/persistence-sprint-20261028-JR0Nwf82`.
Source under `code/`; original rounds 1–4 executable preserved under `code-v1/`.
`capture-v2/` holds the pre-23-October numeric snapshot and admission provenance;
`round-1/` through `round-8/` retain every model, readout, state and aggregate
report. Do not rerun or replace their receipts. The first failed capture is kept.

## What the model actually receives

Admitted journal/creative/chat text uses the existing frozen encoder and a
train-only 32-dimensional projection. Real emotion readings, closed five-minute
Lab activity counts, Watch measurements/age/estimate flags, sensor reactions,
want events and presence records supply numerical observations. Same-time
events enter one atomic batch. Missing emotion readings are never interpolated.
Every actual future emotion target is counted once per fixed horizon; crossing
training/validation/check boundaries is forbidden.

Lab prose is not encoded in this version. Lab event kinds occupy eight fixed
hash buckets; count/value summaries can collide. Source/gap heads predict the
priority source of the timestamp batch, not every simultaneous source. Report
their macro accuracy against source/clock and previous-source controls so Lab
volume and scheduled timing cannot masquerade as anticipation.

Current unfinished threads and dream summaries lack immutable historical arrival
times. They are censused but excluded from historical training, rather than
backdating current final records. Therefore **this does not yet implement all
streams in the brief**. A later prospective admission adapter must record actual
arrival/change time and tombstones before these can train continuity honestly.
Historical text versions are also current admitted copies, not proof of their
exact original availability. Independent continuity/return labels are absent;
past-only retrieval is reported only as next-event semantic alignment.

## Sealed week

The first week is 31 October through 6 November inclusive, America/Chicago.
Candidate 7 is the primary selected on the common exposed validation days;
all eight candidates, including losses, remain in the report. Exact-time text
targets are primary, and at least 100 across all seven days are required for
text noninferiority. Six-hour emotion needs 300 unique outcomes across seven
days, 5% reduction versus every same-row control, and a positive adjusted paired
day interval. The stronger fixed-config through-22-October present refit is an
additional text comparator; it is not the missing original .230 artifact.
Pass-eligible horizons are 10/30 minutes and 1/3/6/12 hours. **24 hours is
descriptive only**: within-block outcomes cannot cover day-seven origins.
The six-hour primary is unchanged. Retain the original conservative interval
adjustment for 56 contrasts; removing the 24-hour claim does not loosen it.

The first provisional `sealed-oct31/` was sealed without looking at any fresh
outcome. It is retired in favor of `sealed-oct31-v2/`, which adds clock/source
controls, retrieval reporting and sequential error spending; weights and the
already computed comparator are copied unchanged. No outcome or model result
motivated those acceptance corrections. Never evaluate the provisional bundle.

On 29 October, v2 was superseded by **v3**, before the block opened, solely to
include the collector's missing admission dependencies and harden scratch writes.
That initial v3 was then amended for Claude Code's review, still before the
block opened. The **only active bundle** is now the durable private directory
`/home/gloria/persistence-sprint-private-20261029/sealed-oct31-v3` (review revision 1).
Directories are 0700, files 0600; it survives `/tmp` cleanup and reboot.
All 34 fitted artifacts, fitting/state mathematics and the primary decision
thresholds are unchanged. The evaluator marks 24h descriptive-only and the
collector requires the guarded launcher. The active manifest SHA256 is
`9b6e09c96e4eff54fa55cb873db6c705110bd370f8fd82c65308c02f16fa7051`.
V1, v2, the initial `/tmp` v3 and its durable before-review copy each have an
exclusive `evaluation-attempt.json` marked `retired_without_evaluation`.
Their original evaluation gates were verified to refuse them; do not remove
those receipts. The amended durable v3 has no attempt receipt yet. No untouched
scores exist yet. V3's clean-room synthetic capture tests use cached fixture
vectors and a nonexistent encoder path, proving no model call is needed for
those tests. The older .230 text confirmation's unsaved artifact is not
reconstructed or claimed as a reproduced score.

The sprint must not keep testing weekly at an unadjusted .05 until something
wins. Family budget in week w is `.05/(w*(w+1))`; week 1 uses .025, then divides
across 56 candidate/horizon contrasts. Both candidates and controls use identical
day draws. Next weeks must be sealed before they open, without peeking at a
still-open predecessor. The old emotion-history experiment remains byte-for-byte
unchanged, with its original 23–29 October dates and adjusted interval.

After 7 November local midnight only, use the **sealed** collector and evaluator:

```sh
export PERSISTENCE_SCRATCH=/home/gloria/persistence-sprint-private-20261029
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
cd "$PERSISTENCE_SCRATCH/sealed-oct31-v3/code/experiments/persistence-sprint"
nice -n 15 /home/gloria/.vintos/workspace/emotion_model/.venv/bin/python3 \
  launch.py collect.py --through 2026-11-06 \
  --memory /home/gloria/.vintos/workspace/memory \
  --out "$PERSISTENCE_SCRATCH/fresh-nov06" \
  --cache "$PERSISTENCE_SCRATCH/empty-text-cache.jsonl" \
  --encoder /home/gloria/.cache/huggingface/hub/models--nomic-ai--nomic-embed-text-v1/snapshots/3ac47f125a41961d13b397d0332866be2f9152e1

nice -n 15 /home/gloria/.vintos/workspace/emotion_model/.venv/bin/python3 \
  launch.py evaluate.py \
  --sealed "$PERSISTENCE_SCRATCH/sealed-oct31-v3" \
  --snapshot "$PERSISTENCE_SCRATCH/fresh-nov06/events.npz" \
  --out "$PERSISTENCE_SCRATCH/fresh-report-nov06"
```

Run from `sealed-oct31-v3/code/experiments/persistence-sprint`, with the existing
training interpreter (not an unconfigured system Python) and the scratch env.
The durable empty cache fallback intentionally re-encodes admitted inputs with
the existing local frozen encoder, so loss of the old `/tmp` cache cannot block
capture. It adds CPU work, not a paid call or model change.
The evaluator verifies executable and parameter hashes and consumes an exclusive
attempt receipt before loading the new snapshot. Insufficient data and failures
are terminal; never remove an attempt receipt. No refitting happens during
evaluation. A statistical result is not installation authorization: Claude Code
review and Gloria's yes still precede any merge, shadow week or consumer change.

The separate emotion-history follow-up remains **30 October at 08:00 Chicago**,
using 23–29 October and excluding 30 October, with the original 98.75% interval.
Its byte-identical durable copy lives under
`/home/gloria/sealed-latent-memory-20261022`; the original follow-up was restored
from its carrying-era pause on 29 October. Its overlapping incumbent scores are
already exposed. Do not reopen its rejected text candidate or substitute sprint
code, thresholds or data. The carrying check automation remains paused for Claude.

## Repeatable synthetic checks

From a scratch copy of this branch, with `PERSISTENCE_SCRATCH` pointing to its
private parent, run the 21 NumPy-only broker contracts with
`/usr/bin/python3.12 scripts/run_isolated_test.py broker/tests/test_persistence_sprint.py`.
Run CPU checks with the training interpreter above using
`-m unittest discover -s experiments/persistence-sprint -p 'test_*.py'`.
The ten CPU tests exercise synthetic data only, including full artificial closed
weeks that must respectively pass and fail using actual scores and intervals;
that test's pass/fail result is not a result on 31 October–6 November.
