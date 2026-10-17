# Press/hold duration bench: trial log and coverage

`scripts/press_hold_bench.py` is a dependency-free Python3.10+ CLI/library for
recording supplied observations. It does not press a device, acquire measurements,
run a sweep, classify a word, compute a score, call a model or send anything.
It uses Unix `fcntl` locks (Linux/WSL/macOS). No installation or service is needed;
it is not added to a deployment manifest.

Every operation requires an explicit `--store`. A run contains exactly eight
distinct, case-sensitive words and five distinct, finite, positive durations in
**milliseconds**. Words may contain internal spaces when shell-quoted, but no
surrounding whitespace/control characters, and are limited to 64 characters.
Run/trial IDs use 1-64 ASCII letters, digits, underscores or hyphens, starting with
a letter/digit. Runs explicitly declare `synthetic` or `observed`; kinds cannot
be mixed within a run. Only mark a run observed when recording actual observations.

## Synthetic usage example

The numbers, labels and score below are **invented software-demo data**, not
experimental results. The words/durations are examples, not a prescribed protocol.
Run from the repository root. Pick a new run ID when reusing an existing store.

```sh
python3 scripts/press_hold_bench.py init --store /tmp/press-hold-demo --run-id synthetic-example --data-kind synthetic --words tap press hold push pause stay touch wait --durations-ms 100 250 500 750 1000
python3 scripts/press_hold_bench.py record --store /tmp/press-hold-demo --run-id synthetic-example --trial-id t1 --word tap --requested-duration-ms 100 --measured-duration-ms 101 --expected-label press --observed-label press --score 0.75 --score-method synthetic-example-v1 --status scored
python3 scripts/press_hold_bench.py coverage --store /tmp/press-hold-demo --run-id synthetic-example --require-complete
```

The last command prints JSON with `expected_cells:40`, `scored_cells:1`,
`complete:false`, and 39 missing scored cells; it exits 1 because completeness was
requested. Omitting `--require-complete` reports the same coverage with exit 0.
Exit 2 means invalid input, corrupt data or an I/O error. `--help` lists commands.
`init` prints the generated run ID if `--run-id` is omitted; `--source-commit`
optionally records a full lowercase 40-character Git SHA in the run manifest.

Files for this example:

```text
/tmp/press-hold-demo/synthetic-example/manifest.json
/tmp/press-hold-demo/synthetic-example/scores.jsonl
```

The manifest records `schema_version`, `run_id`, `data_kind`, `created_at_utc`,
`words`, `durations_ms`, and nullable `source_commit`. Initialization creates an
empty log and refuses an existing run directory; it never resets a run.

## Trial schema and validation

Each UTF-8 JSONL row has exactly these keys (schema version 1):

| Key | Meaning |
|---|---|
| `schema_version`, `run_id`, `data_kind` | Inherited run identity; kind is synthetic or observed. |
| `trial_id` | Unique attempt ID within this run. |
| `word` | Exact member of the run's eight words. |
| `requested_duration_ms` | Exact member of the run's five durations; finite, positive. |
| `measured_duration_ms` | Supplied finite, nonnegative measurement or null. Never replaced with requested duration. Zero is valid. |
| `expected_label`, `observed_label` | `press` or `hold`; observed label may be null when not scored. Expected label is required and must remain consistent within a word-duration cell. |
| `score`, `score_method` | Supplied normalized score in [0,1] and named scoring method. No scoring rule is inferred. Zero is a real score, distinct from null. |
| `status` | `scored`, `unscored` or `failed`. |
| `error_code` | Required only for failed trials; same safe identifier syntax as trial IDs. Null otherwise. |
| `retry_of` | Prior failed/unscored attempt ID, or null for an independent attempt/repeat. |
| `recorded_at_utc` | UTC ISO timestamp of logging, not a fabricated acquisition time. |

`scored` requires measurement, observed label, score and method. `unscored` and
`failed` require null score/method; optional partial measurement/observed label
may be retained. A failed row requires `error_code`. Booleans are not numbers;
NaN/infinity, unknown fields and duplicate JSON keys are rejected. No raw prompts,
device payloads or freeform error bodies are part of this schema.

To record a synthetic failure without inventing a score:

```sh
python3 scripts/press_hold_bench.py record --store /tmp/press-hold-demo --run-id synthetic-example --trial-id f1 --word press --requested-duration-ms 100 --expected-label press --status failed --error-code synthetic_timeout
```

## Duplicates, repeats, retries and integrity

- Replaying a `trial_id` with identical data is an idempotent no-op: `appended:false`
  and its original row/timestamp are returned. Changed data with that ID is refused.
- Use a new ID without `retry_of` for an independent repeat. Repeats count as
  attempts but cannot inflate distinct-cell coverage.
- Use a new ID with `--retry-of f1` for a retry of a failed/unscored attempt in the
  same cell. Retry chains are linear: no forks and no retries of a scored attempt.
  For a second retry, name the latest failed/unscored attempt. All attempts remain.
- Appends use an exclusive file lock, append mode, flush and fsync. Readers take a
  shared lock. Cooperating processes serialize validation and append, including
  duplicate detection. Coverage opens files read-only and never consumes records.
- Existing rows are validated before append or coverage. A torn final line,
  corrupt row, foreign identity/version or duplicate stored ID stops the operation;
  no automatic truncation, repair or replacement occurs. Symlink run directories,
  manifests and ledgers are refused. This is not a tamper-proof storage system.
- A filesystem failure during initialization can leave a partial run directory;
  the CLI refuses to reuse it automatically. Preserve it for inspection and choose
  a fresh run ID. Successful log writes are append-only; there is no reset/edit CLI.

## What coverage means

The expected matrix is the manifest's 8×5=40 cells, each identified by exact word
and requested duration. `complete:true` means each has at least one **scored**
attempt, regardless of score value or correctness. It does not mean a quality
threshold was met or that synthetic data is experimental evidence.

The summary includes attempt/measurement/scored-cell counts, total trials,
per-status counts, retry count, `missing_scored_cells` and `unattempted_cells`.
Failed or unscored attempts remain missing from scored coverage. Repeats/retries
do not create extra cells. Runs never borrow observations from another run.

## Focused tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B broker/tests/test_press_hold_bench.py
```

Tests use explicitly asserted temporary stores and a network-send blocker. All
rows are synthetic fixtures; no hardware/model/provider/sender is invoked. They
cover append preservation, validation, run isolation, 40-cell coverage, repeats,
duplicate IDs, retries, missing/failed scores, concurrency, corruption and CLI use.
