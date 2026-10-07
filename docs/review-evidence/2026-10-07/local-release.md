# Completed two-file local release — October 7

Historical two-file release receipt. The subsequent separately approved phone last-seen release supersedes
only the installed home_presence.py hash below; see `phone-last-seen.md`. Its newer file is protected from this
older rollback by the hash guard. Chemistry parser release remains unchanged.

Both prior deployed files exactly matched commit b304baf8f28bdce69d0db96c6af78904e65dbe66. No newer runtime drift
was overwritten. The owner-authorized scoped wrapper follows the existing user-owned module promotion/service
activation pattern (`deploy-atelier.sh` promotion section and Chemistry activation at lines 929-932), without
running that script's unrelated broad sync. No sudo, protection changes, remote push, or effect-authority change.

Installed in `/home/gloria/.vintos/workspace/scripts/`, owner gloria, mode 0644:

| File | SHA256 |
| --- | --- |
| home_presence.py | 5347817f383bcdbcdf77c9fcfd46c755790d57a2d9b12ba58e162e58213685cc |
| chemistry_lab.py | 200be7e45339a7836574d072433e37a9d75be13d63cfe2bb814c8ae070a60732 |

The Lab was stopped during its idle poll (not an in-flight turn), files promoted atomically, installed-file
synthetic smoke tests run, and only `vintos-chemistry-lab.service` started again. PID 397949 -> 580925; final
ActiveState=active, SubState=running, ExecMainStatus=0, NRestarts=0. The parser module is loaded by the new daemon.
The presence script loads on its next normal cron invocation; no real phone probe or sensor event was triggered.

Installed-file smoke explicitly imported the two live paths inside `isolated_exec.run` with read-only mounts
of those two files and repository code/tests, scratch HOME/store, and bubblewrap network isolation. Production
data/credentials were not mounted. Four presence and seven parser diagnostics tests passed, with mocked
hardware/network/providers/sensor reactions. There was no live model or notification smoke test.

Backup: `/home/gloria/.vintos/workspace/scoped-releases/software-fixes-20261007/` (0700), containing both original
modules and the 0600 manifest. Exact prior hashes:

- home_presence.py: e30ce3c82835fd416cc6538cd16bd1ffeb594dec28594bd2213f09dd9a3186e9
- chemistry_lab.py: 05031949945f55a7902a24c5acb79317c1a58cc8e175d5d35384d0f1dcd68790

Rollback as the existing gloria user in Ubuntu WSL, without sudo:

```bash
python3 -B /mnt/c/Users/glori/Documents/Codex/2026-10-03/task/release-local-fixes-20261007.py --rollback
```

It verifies current/backup hashes, refuses to overwrite a later release, restores only those two files, and
reactivates only the Lab service. It does not rewind state, diagnostics, queues, usage, or repository history.
Rollback was prepared and inspected, not executed against the successful release.

Task-directory artifacts: `local-fixes-release-receipt-20261007.json`, `release-local-fixes-20261007.py`,
`installed-smoke-test_home_presence_atomic.py.log`, `installed-smoke-test_lab_parser_diagnostics.py.log`.

The requested two fixes are locally released. Study timer/worker remain inactive; no duplicate Study requests,
paid calls, Forge steps/resets, notification changes, or unrelated restarts occurred. mmWave remains undeployed
preparation, with no hardware pipeline or new authority. New paid work and any notification digest change are
separate gates, not blockers to this completed release.
