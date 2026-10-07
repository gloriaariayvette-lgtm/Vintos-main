# Completed owner-authorized Study reconciliation

At 2026-10-07T21:51:12.008323Z, **SF-7e71e004** was reconciled through the newly supported local CLI to
`implemented_externally`. Its display label is **implemented locally; not Study-reviewed**. No automated Study
review/completion is asserted. This is an administrative external-release attestation, not a paid worker run.

Implementation commit: `477cd8c7f457545f2f389f9ce868266a746d6243`.
Changed runtime code: `scripts/study_fix.py`; new tests: `broker/tests/test_study_external_reconcile.py`.

The operation `reconcile_external` / `--reconcile-external`:

- Takes both existing worker and request locks; only queued registrations can transition. Exact repeats are
  idempotent; changed records, active states, different attestations or altered history are refused.
- Verifies a bounded receipt by SHA256 and SF ID, passing smoke evidence, an ancestor source commit, and matching
  currently installed eligible script bytes. Protected-file rules remain unchanged.
- Uses an expected original-record fingerprint, preserves every other row, original asked/by/what fields and
  log entries, appends a factual event, and writes atomically with file and directory fsync. No 200-row trimming.
- Counts the original submission as before. `tend()` still selects only queued records; reconciled records are
  skipped. Identical request text also stays deduplicated. Status/claim checks distinguish external implementation.

Verified evidence retained in this record:

- Phone release receipt: `/mnt/c/Users/glori/Documents/Codex/2026-10-03/task/phone-last-seen-release-receipt-20261007.json`
- Receipt SHA256: `3152a478d31e71696d77f172687cc233e208f392e4ef71f8b192c90a8c430516`
- Phone source commit: `0f92fb0ef05482c605cc12df557f1a5c71cbd492`
- Installed phone SHA256: `0ae177ee453e4408abdf5d0242b64c1e59d92e1c3f3016f3fd927c0e6c63b3e5`
- Original registration fingerprint: `fbfa68c6bbc95ecef996a44cee7d4adcf1a4e17d3e5d580cfc41a985df8a5e20`

Source validation: 11 reconciliation tests, 64 existing Study checks and 7 quota tests passed via the OS-isolated
runner with scratch stores and mocked providers/senders. Installed-file smoke repeated all 11 reconciliation
tests successfully. Repeating the actual approved reconciliation left production queue bytes unchanged. Every
other record and the original submission timestamp/history were compared and remained unchanged.

Deployed file: `/home/gloria/.vintos/workspace/scripts/study_fix.py`
SHA256: `f65937c84c03df9f96d2703f08e0299cd1707e1b112a1b755e3bd68c0927c217`
Prior SHA256: `63ed51dfc2907c388d80ef7e43d4c367aa1a1a896567bc32f171a9b4cc0d1da1`
Backup: `/home/gloria/.vintos/workspace/scoped-releases/study-reconciliation-20261007/` (0700), containing prior
module and a 0600 pre-reconciliation queue snapshot. The queue snapshot is forensic evidence, not an instruction
to restore a queued state. No rollback or deletion of record/history was performed.

Worker and timer remain inactive. No service restart, quota adjustment, remote push, paid call, notification or
security-setting change occurred. Local release record: `study-reconciliation-release-receipt-20261007.json` in
the task directory; source logs `reconciliation-test_*.log`, installed log `installed-study-reconciliation-smoke.log`.
