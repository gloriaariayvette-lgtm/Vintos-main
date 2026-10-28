# Carrying-state review log

## 28 October — Claude Code's eight revisions

Created `codex/persistent-carry-review` directly from deploy `7b859dad`. Kept
forecasting code, broker experiments and forecast evidence on the old branch.
Revised authored journal admissions, real context switch and three-hour expiry,
adoption duration reset, clean complete-sentence fragments and deduplication,
state-driven selection with conversation/presence, recursive-input protection,
clock bounds and durable writes only on state change. Added real/synthetic clock
attribution and aggregate midnight receipts.

45 focused tests passed on Aegis's `/usr/bin/python3.12` in OS isolation, including
conversation/presence counterfactual selection and an unchanged state inode on a
quiet poll. The full suite and corrected real shadow are recorded below when run.
The old v1 worker's earlier observations are historical; they cannot satisfy the
new version's real-midnight release condition. No merge or live deployment.

## Corrected running path and full validation

Implementation `6b619db0`, final tested snapshot `3804b6a7` (runtime/tests identical).
Final full Aegis result: **542/542 suites passed**, including 45 carrying tests;
one existing optional SDK test internally skipped. The first full run was 540/542:
the new config required regeneration of `docs/store-owners.md`, and an unchanged
bench-page denial assertion failed once. The bench suite passed separately and in
the final full run; no bench source changed. Both run summaries are retained.

The v1 scratch process was identity-checked and stopped. Corrected v2 shadow now
runs from `/tmp/persistent-carry-review-20261028-rvc4LM`, PID in `shadow.pid`, with
fresh state and a 96-hour lease. Initial counts: 24 allowed journal records, three
threads, two wants, three explicitly imagined dreams; 624-character note. Actual
selected kinds observed: two journals and one dream, with no source quota.
Source references, switch off/on and three-hour expiry, full/compact readers and
extracted First Light assembly passed a private probe with one stubbed provider
call. Runtime hashes match the tested implementation. No shadow note is live.

**Actual midnights observed: zero. Release is held.** The continuation now runs at
00:10 and 09:10 Chicago time on this branch, checking real midnight receipts and
private note continuity. A synthetic receipt cannot satisfy acceptance. Shadow
carry origins will reset at any later owner-approved production adoption.
Evidence contains only scores/counts/timestamps/code hashes and test exits, no
source text, source identifiers, private vectors or checkpoints. No merge/deploy.
