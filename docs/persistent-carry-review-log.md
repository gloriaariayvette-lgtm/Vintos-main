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
