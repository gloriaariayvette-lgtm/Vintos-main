# Judges slices 1 and 2: accumulated review handoff

Implementation tip: **83118e87492ba96d254e46289f614dd5ccbeda23**.
This handoff adds documentation only. The last reviewer-reported integration is
**41b3a1d5**, including **d3dd754a**. The implementation range to inspect is
`d3dd754a..83118e87`; do not treat this as a merge or a claim about the current
remote deploy branch. Existing submitted branch tips remain fixed.

## Dependency order

These are thirteen consecutive commits, oldest first. Later branches include all
preceding rows; they are not independent patches to merge repeatedly.

| Commit | Review branch suffix (all under `codex/`) | Concrete change |
| --- | --- | --- |
| `1e89f63d` | `judges-draft-response-identity` | Preserve actual response identity through existing draft contracts. |
| `f71dff2c` | `judges-audit-vector-conflicts` | Retain differing audit observations so a later valid copy cannot hide a conflict. |
| `5ca11e30` | `judges-vector-representations` | Separate raw encoder returns from normalized readout vectors. |
| `7df2c9a6` | `judges-window30-attribution` | Optional historical thirty-second view; all nearby replies compete, no training upgrade. |
| `eea58349` | `judges-completion-joins` | Bind selected router completions to saved reply-history versions. |
| `26b5a55a` | `judges-source-coverage` | Source-path trace and counts-only missing-surface diagnostic. |
| `f3da0e61` | `judges-durable-queue-counts` | Persist bounded deferred-writer diagnostic deltas as lower bounds. |
| `fd3746bb` | `judges-encoder-parameter-receipts` | Observe bounded loaded CPU parameter snapshots around audit encoding. |
| `c8219640` | `judges-forecast-encoding-links` | Bind selected forecast features to their raw encoding observations and normalization. |
| `42856612` | `judges-encoding-consistency` | Compare validated observations within exact content groups, offline. |
| `c0a037b4` | `judges-innovation-input-contract` | Refuse ambiguous admitted-target lists and malformed history minima. |
| `1a69dc47` | `judges-attribution-report-contract` | Validate historical report scope/effects and count conservation. |
| `83118e87` | `judges-encoder-cost-benchmark` | Bounded synthetic CPU benchmark and reproducible reviewer commands. |

## What runs where

- **Prospective generation metadata:** `bin/model_router.py`, `bin/server.py` and
  `scripts/request_trace.py`. Completion/history linkage operates even when optional
  witness capture is disabled. A completion marker, HTTP trace and provider request
  ID are different identities. Saved history precedes the final response guard, so
  this is not proof of client delivery or every internal attempt. Existing fail-open
  ledger writes do not establish durability. Other generation paths are not given
  invented completion IDs.
- **Optional capture work:** `scripts/witness_sink.py`, `scripts/witness_capture.py`,
  `scripts/witness_self_artifacts.py` and the guarded self-on-message section of
  `scripts/jepa_readout.py`. CPU snapshots are bounded but can scan up to two GiB per
  captured wrapper. Their cost is separate from queue admission. Existing outputs,
  encode counts and model selection remain unchanged by contract tests. No other
  head is instrumented by the forecast increment.
- **Offline-only work:** attribution/coverage, artifact joins, replay, report and
  benchmark. It neither admits historical tiers into strict training evidence nor
  supplies scores to live consumers. The benchmark lives under `experiments/` and
  requires no production installation.

## Verification at the implementation tip

Local OS-isolated run on 9 November: **393 checks across 16 focused suites, all
passed**. Tests use synthetic stores and stubbed senders. This is not the full
Aegis broker suite, real-data accuracy or serving acceptance.

| Suite (`broker/tests/`) | Passed checks |
| --- | ---: |
| `test_judges_witness.py` | 109 |
| `test_witness_artifact_join.py` | 30 |
| `test_witness_attribution.py` | 26 |
| `test_witness_attribution_coverage.py` | 21 |
| `test_witness_completion_joins.py` | 9 |
| `test_witness_deferred_capture.py` | 22 |
| `test_witness_draft_identity.py` | 9 |
| `test_witness_encoder_benchmark.py` | 6 |
| `test_witness_encoder_parameters.py` | 19 |
| `test_witness_review_report.py` | 20 |
| `test_witness_router_completions.py` | 7 |
| `test_witness_self_artifacts.py` | 20 |
| `test_witness_capture_hooks.py` | 21 |
| `test_merged_chat.py` | 31 |
| `test_entry_owners.py` | 11 |
| `test_store_guard.py` | 32 |

The count combines unittest cases with the older suites' named checks; it is not a
count of full broker suites. Each ran via `scripts/run_isolated_test.py`. Generated
ownership/untested/store reports were refreshed and their ownership checks passed.

## Host review still required

1. Run the full isolated broker suite on the candidate integrated with concurrent
   deploy-branch work. Preserve those changes and regenerate derived reports there.
2. Remeasure occupied-sink worker throughput, burst retention and response latency
   after the diagnostic flush change. Persisted counts are lower bounds;
   `restart_loss` remains unknown. A count difference is not a loss estimate.
3. Measure encoder observation CPU/memory cost in the existing host environment.
   [The synthetic benchmark commands](../experiments/judges-witness/README.md)
   need no model or private data. Local 64 MiB arrays measured roughly 42–49 ms per
   first observed call; these are neither host measurements nor a forecast for real
   tensor-runtime cost. Loaded-runtime compatibility and real packet sizes need
   their own check before optional capture is enabled.
4. On the existing admitted private snapshot, inspect the source-coverage and
   optional thirty-second attribution view. Keep its partition separate from the
   original ten-second view; do not sum them. Copies are not independent turns,
   exact label disagreement is not automatically a model-family mismatch, and
   historical attribution does not prove clean ancestry or delivery.
5. For future retained packets, inspect content-binding, timing and observation
   consistency counts. Matching snapshots are not full encoder identity. Tokenizer,
   loaded execution configuration/code, fitting lineage and forecast-target
   association remain unresolved. Missing evidence never becomes zero error.

[Source tracing](judges-source-coverage.md) establishes the current bilateral text
path and the source-field behavior; it does not establish the historical cause of
stopped router-chat records. The private copied-data diagnostic is still needed.
No source/date/model attribution is guessed to fill that gap.

No training-set decision, model replacement, live feed change, enablement, merge or
deployment is part of this handoff. Claude Code reviews and owns the host checks;
Gloria owns enabling/deployment. The ongoing collaboration continues independently
of the review queue.


## Subsequent offline increment

`codex/judges-attribution-match-methods` descends from the documentation handoff
commit f7eccc6e. It adds fixed matched-method coverage to historical attribution
and its public report, without changing matching or runtime producers. The
thirteen-commit range and 393-check result above remain the prior checkpoint, not
a test claim for this increment. Its 79 affected isolated checks pass: completion
joins 10, report 22, attribution 26, source coverage 21. Exact revision is recorded
in the coordination reply after push. Full host acceptance remains outstanding.


## Historical source follow-up

`codex/judges-historical-test-caller` adds source evidence for an old test-origin
candidate: a lower-level result-contract test called the chat router without
isolating the accounting path, followed by September 11 isolation fixes.
See judges-source-coverage.md for exact revisions, import-path limitations and
the check against the existing private copy. Nine source assertions passed; no
runtime code or historical attribution changed. Retained-row origin is still
unconfirmed, and no new private collection or deployment is requested.
