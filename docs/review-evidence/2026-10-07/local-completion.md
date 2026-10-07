# Authorized local software completion — October 7

The campaign source includes the reviewed dated quota changes and isolated mmWave preparation, plus the two
requested fixes below. This is owner-authorized repository work, not a Study self-edit or a change to its
protected-file gates. No agent model was called. Existing unrelated untracked checkout files were excluded.

## Atomic presence state

`scripts/home_presence.py` writes complete JSON to a unique 0600 temporary file beside STATE, flushes and fsyncs,
then atomically replaces STATE. Failed writes/fsync/replacement preserve the prior state and clean the temporary
file. Hysteresis, freshness, timestamps and existing sensor_reactions invocation remain unchanged. This prevents
partial-read corruption; it does not add cross-process read/modify/write serialization.

## Bounded parser evidence

`scripts/chemistry_lab.py` captures the original response before normalization/repair, under an opaque UUID in
ROOT/diagnostics. Directory mode 0700; raw/repaired/event files mode 0600. Each file is capped at 64 KiB; a locked
retention pass keeps at most 200 evidence files, pruning complete oldest groups, including after partial writes.
Oversized text is a bounded UTF-8 byte prefix, not a promise of complete evidence. The hidden lock is not an
evidence file. Disk/permission failures are best-effort and do not prevent parsing; an evidence ID does not
guarantee that storage succeeded.

`strict_parse_failed` and `repaired` are distinct metadata events. Strict-before-repair and existing JSON boundary
behavior remain. ModelJSONError contains fixed labels and an evidence ID instead of model excerpts; the existing
fault/tick/orientation paths propagate that safe error. Raw/repaired text is not copied to general logs. The old
test that required model text in errors was replaced with an assertion of the newly requested privacy contract.

## Validation

All suites ran via `scripts/run_isolated_test.py`: scratch stores, fixture/stub provider and network effects,
Linux bubblewrap network/filesystem isolation. No production notification, model call, deployment, restart or
Forge step was invoked.

- `test_home_presence_atomic.py`: 4 tests, including partial write/fsync/replace failures.
- `test_lab_parser_diagnostics.py`: 7 tests, including original-before-repair, permissions, size/retention,
  write-failure cleanup, safe fault output, and actual orientation/tick parser path with a mocked response.
- `test_lab_json_parser.py`: 20 checks.
- `test_lab_json_boundary.py`: 17 checks.
- `test_home_presence.py`: 12 checks.
- `test_chemistry_lab.py`: 40 checks.

Earlier unchanged quota/mmWave validation: quota 7, Study 64, Forge cards 4, deployment bundle 14, mmWave 5.
Some existing JSON readers emitted ResourceWarnings; no assertions failed. Logs are in the task directory's
`campaign-validation-20261007/`. No broad suite or live smoke test is claimed.

## Deployment and deduplication

`study-requests.json` is marked implemented_locally_do_not_submit_duplicates. Neither request was submitted;
the live Study queue is untouched. Its timer remains paused pending a dollar ceiling. Forge is exhausted at
10/10 and must not be reset or topped up. Notification behavior is unchanged pending separate approval.

Presence/parser fixes and mmWave preparation are not live. mmWave remains absent from deployment manifests and
has no commissioned hardware or consumer. Only the previously documented scoped quota deployment is live.
Remaining release gates: publish/review the source integration through the normal repository workflow and
perform separately authorized scoped deployment; new paid work requires a dollar ceiling. Do not use the broad
deploy to overwrite known unrelated runtime drift.
