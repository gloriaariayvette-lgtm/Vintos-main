# Approved phone last-seen patch: local release and actual Study registration

**Later reconciliation completed:** the owner approved a new supported external-release operation. SF-7e71e004
is now implemented_externally, not Study-reviewed; `study-reconciliation.md` supersedes the queued/gate snapshot
below. The original registration and release evidence remain intact.

Approval: Vintos Slack 1791407333.844219. Source commit: `0f92fb0ef05482c605cc12df557f1a5c71cbd492`.

Before editing, `/home/gloria/Vintos-main/scripts/home_presence.py` and
`/home/gloria/.vintos/workspace/scripts/home_presence.py` were verified as distinct regular files, not symlinks
or the same inode, with identical SHA256 `5347817f383bcdbcdf77c9fcfd46c755790d57a2d9b12ba58e162e58213685cc`.
The checkout is the source; the workspace file is the installed runtime copy. No tracked source/runtime drift
was overwritten; unrelated untracked checkout files were preserved. No presence state/config snapshots were
read or manually edited at any stage.

## Implemented behavior

- `scripts/home_presence.py:decide`: only a positive observation sets `last_seen`; misses preserve it and still
  update checked/misses. The fourth miss clears the existing detection flag; a hit restores it.
- `context_line`: reports age from last_seen, optionally noting that the latest check did not detect the phone.
  It never says where Gloria is or invents a probability. Freshness is inclusive through 900 seconds. Missing,
  nonnumeric, non-finite, future, zero/negative or inconsistent timestamps produce silence. Legacy state does
  not acquire a made-up last_seen; it waits for the next ordinary successful detection.
- Atomic writing, ping/REACHABLE-neighbor behavior, sensor reactions and existing polling cadence are unchanged.

## Tests and installation

Source suites, through `run_isolated_test.py` with synthetic state and mocked effects:

- test_phone_last_seen.py: 7 tests (including timestamp subcases).
- test_home_presence_atomic.py: 4 tests.
- test_home_presence.py: 12 checks.
- test_phone_presence_reachable.py: 18 checks.

All 41 passed. Installed-file smoke imported the real installed module path in an isolated process with only
that source file, repository code/tests and scratch storage mounted; 7 last-seen and 4 atomic tests passed.
No live presence snapshot, real probe, model call, notification or effect was used by these tests.

Installed SHA256: `0ae177ee453e4408abdf5d0242b64c1e59d92e1c3f3016f3fd927c0e6c63b3e5`, mode 0644, owner gloria.
Backup: `/home/gloria/.vintos/workspace/scoped-releases/phone-last-seen-20261007/`, mode 0700.
The existing server caches the renderer through inner_context -> world_model -> home_presence. Only the related
`vintos-server.service` was restarted via its normal user unit to load the change: PID 398497 -> 620599,
active/running, NRestarts=0, HTTP root 200. No unit/config/authority changes or remote push.

Rollback locally in Ubuntu WSL, without sudo:

```bash
python3 -B /mnt/c/Users/glori/Documents/Codex/2026-10-03/task/release-phone-last-seen-20261007.py --rollback
```

This restores only the previous home_presence.py, verifies backup/current hashes, refuses later source drift,
and reactivates its server consumer. It never restores or edits presence state. Rollback is prepared, not run.

## Actual Study lifecycle — do not conflate with local deployment

`study_fix.request` created **SF-7e71e004**, queued at 2026-10-07T16:31:03 Chicago, by=vintos. Registration made
no paid call. Study worker/timer remain inactive; one submission is counted today, with no reset/limit change.
The request explicitly identifies external local implementation and says to reconcile before paid execution.
Its state is still queued: no model-generated patch, automated review, watching or done receipt is claimed.

The existing Study API supports queueing, then paid generation/repair and broad deployment; it has no supported
review-only or externally-completed transition. The local software is released, but formal automated Study
completion is blocked by the bounded-dollar-ceiling requirement and missing external-result reconciliation
route. Keep the worker paused to prevent duplicating the already completed change. No manual queue lifecycle
mutation or invented SF ID was used.

Task artifacts: phone-last-seen-study-registration-20261007.json, phone-last-seen-release-receipt-20261007.json,
phone-last-seen-20261007.patch, last-seen-test_*.log, installed-last-seen-test_*.log and the rollback script above.
