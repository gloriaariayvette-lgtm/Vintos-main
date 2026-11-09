# Dedicated production shadow sink — implemented, still disabled

8 November 2026. Review branch implementation; no configuration was installed,
service changed, capture enabled or production data written by this work.

## Evidence and scope

The reviewer reported a fresh private-copy census at 4a8fc11e: 641 assistant copies,
197 distinct identified replies, zero strict-eligible replies and 35 on-message
forecasts held for absent eligible final replies. This is a strict receipt result,
not proof that historical model labels were never recorded. Coordination note 24
identifies existing row labels and compute-ledger records; their separate historical
attribution tier is pending. No historical clean-lineage or delivery backfill follows.

`witness_sink.py` provides storage for the existing capture, value-map and scoped
self-forecast sidecars. `JUDGES_CAPTURE_CONFIG` explicitly names its config. With
no pointer, missing/invalid config or anything except boolean `enabled: true`, the
production sink is off. Existing scratch mode takes precedence and retains its
original requirement that scratch and workspace name the same private directory.
**Never set JUDGES_CAPTURE_SCRATCH or repoint SPARK_WORKSPACE on a serving process.**

## Preparation for a later approved enablement

Through Gloria's normal reviewed deployment/configuration route, prepare one
owner-private 0700 destination outside every repository and live workspace, and a
0600 configuration such as the following (substitute the actual approved absolute
private path; this example is not an install command):

```json
{
  "schema": "judges-shadow-sink-v1",
  "enabled": false,
  "directory": "/absolute/private/shadow-directory",
  "max_bytes": 268435456,
  "max_files": 4096,
  "retention_seconds": 604800,
  "max_packet_bytes": 1048576
}
```

Add only `JUDGES_CAPTURE_CONFIG=/absolute/private/judges-capture.json` to the intended
serving/job environments through that same route. The pointer does not enable
capture while the file says false. Child jobs inherit the pointer; independent cron
jobs require their own reviewed environment entry. No unit, cron or environment
file is changed by this branch. Validate this wiring on Aegis before enablement.
The script is included in the deployment manifest; no live reader consumes its
packets and no judge/feed is replaced.

Once the reviewed disabled config/destination and pointer are in place, Gloria's
single enable step is:

```sh
python3 ~/.vintos/workspace/scripts/witness_sink.py enable --config /absolute/private/judges-capture.json
```

The command validates the prepared private file and limits, and atomically changes
only its enabled field. The same command with `disable` is the kill switch; no
restart or workspace/model change is needed. Config is rechecked at observation
and publication boundaries. An operation already past its final check may finish;
this is not a transaction spanning config replacement and file publication.

Rollback: disable that config, remove only its environment pointer through the
normal configuration route, and use the normal code rollback if necessary. Existing
packets remain private; disabling/rollback does not erase them. No automatic enable
step is added to deployment.

## Storage and failure contract

Packets are written atomically without replacement, mode 0600, inside the validated
0700 destination. Symlink traversal, wrong ownership, nonregular managed files,
unmanaged entries and workspace/repository destinations are refused. A nonblocking
cross-process lock serializes writers; contention skips capture rather than waiting.
Managed expired packets and abandoned pending files expire on later publication
attempts. No timer is installed: with no writers, expiry is not an exact wall-clock
deletion deadline. Disabling capture also stops this opportunistic maintenance.

Bounds are at most seven days, 256 MiB including an 8 KiB bookkeeping reserve,
4096 retained packet/pending files and 1 MiB per packet. Limits may be lowered.
Unexpired packets are not evicted to make room: capacity skips the new packet.
Directory scans are capped at 4112 entries. Only recognized private packet names
and pending files are eligible for expiry; unknown files are never deleted.

`status.json` records lock-owning write/capacity/expiry counts and current retained
bytes/files. Configuration failures, oversize packets, lock contention and write
failures have process-local `witness_sink.COUNTERS`; these do not survive restart
and cannot always be persisted when the sink is unavailable. Status explicitly
states its incomplete coverage. A successful packet followed by status/fsync
failure may exist despite a false return. None of these states proves no activity.
Capture failure is caught at existing producer boundaries and leaves serving intact.

Only the existing reviewed private packet schemas are admitted by the sink's
producer prefix allowlist. Final replies can be private packet content; incoming
text, credentials and provider reasoning are not newly captured. Packets and status
never enter Git. Exact target embeddings and checkpoint manifests are separate
retention work, not claimed implemented by this storage increment.

## Validation and remaining acceptance

314 affected isolated checks pass, including 19 new sink cases and actual synthetic
self-forecast off/on equality. Tests cover config absence/disable/retarget, limits,
atomic failures, multi-process capacity, hot disable, retention, symlinks, permissions,
scratch precedence and operator enable/disable. Existing renderer, capture, self
head and value-map suites pass; value-map aliases remain identical.

100 tiny synthetic local storage publications into a growing private scratch sink:
median 1.139 ms, p95 1.300 ms, maximum 1.659 ms. This measures storage only on the Mac,
not end-to-end requests, full-size packets, a full sink or Aegis serving latency.
The reviewer's earlier Aegis scratch finish-shadow benchmark was median 1.50 ms,
p95 1.98 ms, maximum 3.03 ms; it predates this production sink. The full isolated
Aegis suite plus representative packet/occupancy latency remain required review
checks before Gloria's enable decision. No production latency guarantee is made.

Capture does not establish complete ancestry, authenticated client delivery or
previously missing attempts. Those facts remain unknown. Historical model-label
attribution and separately retained evaluation inputs remain distinct tasks.
