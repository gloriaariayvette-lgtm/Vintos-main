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

Existing producers write their reviewed private packet schemas. The sink validates
filename prefixes and storage limits, not packet semantics; strict replay remains
the semantic validator. Final replies can be private packet content; incoming text,
credentials and provider reasoning are not newly captured by these hooks. Packets and status
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

## Review follow-up: final reply storage off the handler wait path

The avatar's final `finish_shadow(..., defer=True)` freezes the completed packet
as immutable JSON bytes and offers it to one lazy daemon writer per process.
Up to 64 pending packets share an 8 MiB serialized-payload budget, plus one in
flight at most 1 MiB. Retained queue payloads stay bounded to 9 MiB per serving
process (temporary serialization and Python object costs are additional). Either
a full slot/byte budget or a busy initialization lock skips capture.
The handler does not wait for filesystem scans, cross-process sink locks, fsync,
or a free queue slot. Packet finalization, serialization, configuration checks and
thread startup still occur on the handler path. This is not a zero-cost hook.

Only final production chat capture uses this queue. Scratch capture, background
value-map receipts and self-forecast/audit sidecars keep synchronous publication
and their existing return-value meaning. Queued `finish_shadow` returning true
means accepted in memory, **not written, durable or delivered**. Its value is not
used to change the chat response. The packet keeps its original finalization time
and unknown delivery; the writer does not recast persistence time as reply time.

The worker uses the same atomic publisher and current permission/capacity checks.
It rejects a queued packet if the observed config no longer matches (including
destination/limit changes), or the pointer is absent/disabled/invalid when writing.
As before, a publication already past its final check may complete. A disable and
re-enable between checks is not an observable generation boundary. The writer
creates no new config, service, timer or scheduled job. Fork children reset the
queue, thread reference, initialization lock and process counters; they cannot
replay the parent's queued packets.

Queue contents are volatile. Process death, reboot, cancellation of the process,
or ordinary exit can lose pending work; there is deliberately no shutdown flush
that delays serving shutdown. `COUNTERS` distinguishes deferred_enqueued,
deferred_written, deferred_not_confirmed, deferred_full, deferred_busy and
deferred_unavailable. The process counters reset on restart. The follow-up below persists observed
deferred deltas as explicitly incomplete lower bounds; it cannot count lost queue
items after a crash. A false/unconfirmed write can still leave a completed packet
if later status or fsync failed. Missing packets are not evidence of no activity.

Prior queue revision synthetic Mac benchmark at representative occupancy: 4,000 existing files,
236,976,000 bytes (about 226 MiB), new packets 24,565 bytes, 20 samples each.
Synchronous publication: median 12.653 ms, p95 13.211, max 14.908.
Queue admission: median 0.168 ms, p95 0.218, max 0.236.
Background publication: median 12.598 ms, p95 13.936, max 18.997; 20/20 confirmed.
This includes a cold first writer start, but is a sequential drained-queue
measurement, not concurrent request latency or an Aegis acceptance result.
The reviewer's earlier occupied Aegis sink measured roughly 11 ms/write and cap
skips up to 24 ms. Disk cost remains; it is moved to the worker. Aegis review must
check occupied/full sink behavior and response latency before Gloria enables it.

122 focused isolated checks pass, including 14 queue cases, 19 sink cases and
execution of the actual handler capture/return segments with a stalled writer and
stubbed provider. Overflow, kill switch, retarget, limits, immutable snapshots,
fork reset, exit loss, thread/write failures, private permissions, synchronous
producer compatibility and unchanged response/delivery semantics are exercised.
No production flag, environment, unit or store was changed by this follow-up.


### Persisted deferred diagnostics (9 November follow-up)

The existing writer now coalesces scalar diagnostic deltas, separately from the
packet queue. `status.json.deferred.counts` stores observed `enqueued`, `written`,
`not_confirmed`, `full` and `unavailable` counts that reached a status write.
Synchronous producers preserve this section; later processes accumulate into it
under the same cross-process lock. All names are fixed; no text, identities, paths
or provider values enter the counters. Status stays bounded and owner-private.

These are **lower bounds for each category**, not a complete ledger or an equation.
A packet can be written before status/fsync fails, so `not_confirmed` does not mean
proven packet loss. A failed status write can also lose its admission delta while
a later outcome delta survives. `restart_loss` is always JSON null: without durable
pre-crash admission receipts, subtraction cannot tell what a restart destroyed.
A missing field is unobserved, not zero verified events. Busy initialization skips,
thread-start failures and unflushed observations may remain process-local only.
Counters saturate at their bounded integer ceiling rather than growing status.

The reply thread only updates a small in-memory batch while holding its existing
nonblocking queue-admission lock. Up to eight configuration-scoped batches are
retained, with fixed scalar fields. No disk lock, scan, write or fsync is added to
that thread. The background writer incorporates claimed deltas into its next packet
publication and flushes remaining outcomes when the queue empties; an idle worker
checks for remaining batches every 250 ms but performs no I/O when none exist.
Diagnostics obey the original expected-config equality and kill switch. Changing
destination or limits discards stale pending deltas rather than moving them to the
new configuration. Already persisted counts stay with their original directory.

Each delta batch is claimed once before I/O. Busy/full-disk/disabled or ambiguous
post-replacement failures are not retried: a replacement may already have succeeded,
so replaying it could double-count. This deliberately permits undercount. Fork
children discard inherited pending diagnostic deltas along with the packet queue;
there is still no exit flush or restart recovery claim.

The packet FIFO now permits 64 slots within an 8 MiB queued-byte limit, plus one
in flight (at most nine MiB of retained payload). This moves the small-packet burst
limit while preserving the previous payload-memory bound. It does not prevent all
overflow, and coalescing distinct replies would erase evidence. Only diagnostics
are coalesced. The last packet of a
batch can now cause a second background directory scan/status flush; occupied-sink
worker throughput and reply latency need fresh Aegis measurements for this revision.
The earlier response timing is not presented as acceptance of these new writes.


## Burst-capacity follow-up and remaining restart work

Review note 28 measured 9/30 retention for back-to-back packets and 30/30 at 50 ms
spacing with the former eight-slot queue. The revised FIFO admits 64 small packets
while retaining an independent 8 MiB byte ceiling. Both reservations use the
queue's mutex; a rejected packet neither evicts older work nor reserves bytes.
Removing an item releases its queue bytes; one in-flight payload is budgeted
separately. Full-slot and full-byte rejections share the existing `full` counter.

A local synthetic test stalls the actual writer, admits thirty roughly 24 KB
packets, then verifies all thirty persisted exactly once after release. Other
fixtures cover slot overflow, byte overflow, concurrent byte reservations, failure
and drain behavior, disable/retarget, fork and exit. 66 affected isolated checks
pass (queue 26, sink 19, handler hooks 21). These are contract results, not fresh
Aegis throughput or latency measurements.

Restart recovery is NOT implemented by this increment. A future spool must bound
bytes and records, use owner-private files, preserve original packet/config identity,
and avoid duplicate publication after a crash between publish and acknowledgement.
An asynchronous spool still loses items before its first durable write; it cannot
make `enqueue_capture` a durable acknowledgement. Waiting for file/directory fsync
would add foreground I/O and needs separate measured latency evidence. Until that
contract is implemented and tested, accepted-in-memory and restart-loss-unknown
remain the truthful behavior. No boot service, exit flush or new flag is installed.


## Stable publication prerequisite for restart recovery

The sink's internal `_publish_bytes` accepts an optional `packet_id`: exactly 32
lowercase hexadecimal characters supplied by a future durable ingress record.
The packet's prefix plus that ID selects its immutable final filename. Existing
callers omit it and retain random-name behavior; no queue or server path uses it
yet. This is a tested prerequisite, not a delivered persistent queue.

Under the existing nonblocking sink lock, a repeated ID first checks that the
existing file is regular, owner-private (0600), owned by the current user, and
exactly the expected bytes and size. It never follows symlinks or replaces a
conflict. It rechecks enabled/expected configuration and syncs the matching file
and destination directory before confirming the retry. Missing files take the
ordinary bounded publication path under that same stable name. Per-packet size,
permissions, locks and configuration remain enforced on retries.

An already-present match consumes no new packet slot, changes no mtime/retention
clock, and does not increment persisted written/status counts. It increments only
a process-local `already_published` diagnostic. If a crash lost the status write,
the retry confirms the packet without inventing the missing historical counter.
Diagnostic delta batches cannot accompany a stable-ID retry because repeating a
batch could double-count it. Sync failure remains unconfirmed and can be retried.

73 local isolated checks pass (sink 26, deferred queue 26, handler hooks 21).
A child-process fixture exits immediately after the actual atomic file link,
before status/directory completion; retry finds one unchanged packet. Other
fixtures cover concurrent processes, conflicting bytes, unsafe entries, changed
configuration, invalid IDs, full packet capacity and sync failure. This tests a
process crash, not actual hardware power loss or filesystem crash guarantees.

Next implementation work is the bounded private ingress spool and recovery loop:
persist packet identity, exact bytes, observed config and original age; replay
using this API; remove an ingress record only after confirmed publication. Expiry
must be checked in that loop before replay: an existing packet can still be
confirmed here after its retention age, and this API does not infer ingress age.
Idempotence holds while the named final file exists; it is not a permanent
tombstone against manual deletion or retention removal. Startup/disable/retarget
semantics and foreground fsync cost remain unresolved until the spool is wired
and tested. No production durability claim or flag change is made here.


## Durable ingress mode implemented; host acceptance pending

This section supersedes the earlier unfinished-spool statements for
`codex/judges-durable-spool`, stacked after 272b2d0b. No private configuration has
been changed. The optional boolean `durable_queue: true` selects synchronous
private ingress followed by background publication. Omitted or false retains
the default volatile queue. `enabled` still controls capture, and invalid mode
values fail closed for capture without affecting the reply.

An accepted durable capture has its immutable serialized bytes, configuration
fingerprint, original wall-clock time and payload SHA256 in a 0600 record below
an owner-only 0700 `.capture-spool` directory. The record file, spool directory
and parent directory are synced before returning true. This means confirmed
ingress only: final publication and phone delivery are separate. A failure after
linking may return false yet leave a recoverable record; callers must not blindly
resubmit it as a new ID. No response text, routing or exception policy changes.

The spool is bounded to 64 entry names and 8 MiB of unique-inode file bytes,
including headers and a metadata-file reserve. Crash-left temporary names consume
capacity, are never replayed, and expire by their mtime. A temporary hard link and
its committed name count disk bytes once. The final publisher reserves the spool
budget inside the configured total byte ceiling; staging also checks existing
root-file occupancy, including stores filled before this mode was selected.
`max_files` continues to cap final packets; the spool has its separate 64-name
bound. Filesystem allocation overhead, metadata blocks and process RSS are not
these logical-byte limits. There is no eviction to admit a new capture.

The existing daemon worker checks replay while idle, in batches of at most eight
publication attempts. A server startup hook starts it when durable capture is
already enabled, allowing recovery without a new chat turn. Enabling after server
startup starts the worker on the next ordinary captured reply. No new service,
shutdown flush, network transport or model call is added. Persistent storage and
correct startup configuration on the host are prerequisites for reboot recovery;
a temporary test directory establishes only the process-restart contract.

Replay requires the current complete configuration fingerprint to match the
record, rechecks permission, validates bytes and age, and uses its stable packet ID.
It removes ingress only after final publication is confirmed and synced. A crash
between publication and acknowledgement retries the same file without another
packet or written-counter increment. Final-file mtime is set to the original
capture age, including repair of a crash after linking but before that age was
applied; it never extends retention forward. Invalid records and records bound to
a different config remain held and occupy capacity. Valid matching records expire
under their original retention rule. Future timestamps are held. Retargeting does
not move old records. Restoring an identical config allows unexpired old records
to replay: this is config identity, not a permanent disable-generation marker.
It cannot observe a disable/re-enable transition that occurred between checks.

`spooled` and `replayed` join the existing persisted diagnostic lower bounds.
Crashes can still lose counter updates; `restart_loss` remains null, never an
invented exact loss balance. Status retained-file/byte fields describe final
packets, not pending ingress. Private record contents and IDs are not aggregate
report fields. Manual deletion of a final packet removes its idempotence marker;
there is no permanent tombstone beyond the bounded retention contract.

Durability has an explicit foreground cost: serialization, private config reads,
bounded spool/root scans, file sync and two directory syncs. Nonblocking locks
avoid waiting for another writer, but disk operations have no hard latency bound.
The old sub-millisecond in-memory measurements DO NOT describe this mode. Review
must measure near-cap response wait and burst retention, startup replay, capacity,
disable/retarget and host filesystem sync behavior before Gloria selects it.
Synthetic process crashes are not a physical power-loss test. Real encoder cost,
phone delivery and complete influence ancestry remain separate open work.
