# Judges witness implementation log

## 8 November 2026 — first offline contracts

Branch `codex/judges-witness-slices`, based on shared branch commit `2ec82c5c`.
Accepted coordination notes 1 and 2. Scope is the offline foundation of slices
1 and 2; it does not claim completed production instrumentation.

- Added strict admission and allowlisted generation/context-effect receipt
  contracts. Actual served identity is never filled from requested configuration.
- Preserved supplied receipts through provenance normalization and merged-chat
  carrying. Existing global legacy eligibility remains unchanged.
- Added explicit snapshot adapters, duplicate-safe evidence census, descriptive
  behaviour receipt and a causal on-message innovation reader using supplied
  frozen embeddings. Missing evidence is counted, not guessed.
- Protected scratch execution and covered indirect effects, unknown evidence,
  temporal boundaries, repeatability, rename/subprocess/network and write limits.
- No real-data run, fit, model call, production write, scheduled worker or feed
  substitution. Synthetic fixture errors are contract checks, not accuracy results.

The detailed contract, runnable command and outstanding capture hooks are in
[the experiment README](../experiments/judges-witness/README.md). The next step
is independent review of these contracts before hooking producer paths. Full
Aegis suite and test merge belong to Claude Code; neither is claimed here.

Validation on the Mac through `scripts/run_isolated_test.py`: witness 21/21,
provenance 11/11, merged chat 26/26, entry owners 11/11: **69 checks passed across
four focused suites**. Generated ownership/untested reports refreshed; diff
whitespace check passed. Scratch restart produced byte-identical aggregate
reports from the same synthetic input. These are correctness/isolation checks,
not evidence of real-data predictive accuracy.
