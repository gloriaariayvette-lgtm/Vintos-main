# Production shadow capture: separate proposal, disabled

8 November 2026. This document proposes the next enablement contract. It does
not enable capture, authorize a deploy or claim that the current scratch sink
can safely be enabled on a serving process.

## Current evidence and boundary

Claude Code's coordination note 10 reports an Aegis private-copy census of 641
assistant rows across three stores, 197 distinct identified turns, and zero
strict-eligible turns. All 641 have unknown served identity. Missing receipts,
missing turn identity and unknown provenance are retained as missing evidence;
there is no historical eligibility backfill.

The same note reports 100 synthetic Aegis finish-shadow calls: median 1.50 ms,
p95 1.98 ms, maximum 3.03 ms, during two full suites. These are reviewer-reported
measurements, not a new Codex access/run or a serving latency guarantee.

Today's capture sink requires both `JUDGES_CAPTURE_SCRATCH` and
`SPARK_WORKSPACE` to name the same private scratch root. **Do not set those on
the production service.** Doing so would repoint unrelated serving stores.
Framework handoff remains unconfirmed delivery; incomplete upstream ancestry
remains unknown, even after external fragments have explicit origins.

## Proposed enablement increment

1. Add a dedicated, independently validated production shadow destination and
   an explicit mode flag, both absent by default. Do not reuse or change
   `SPARK_WORKSPACE`. The destination must be an owner-private directory outside
   the live stores and repositories, reject symlinks, and have bounded size.
2. Retain only the packet schema already reviewed: exact final returned text,
   its binding, turn/request/attempt identity, observed model metadata, hashes
   and dependency receipts. No credentials, endpoints, incoming text or tool
   reasoning. These packets are private; aggregate exports require review too.
3. Use atomic, no-overwrite mode-0600 packets. Proposed retention: seven days
   and 256 MiB, whichever limit comes first, managed inside that one directory.
   Hitting a capacity or writer failure must skip capture and leave serving
   unchanged; a diagnostic count must distinguish skips from no activity.
4. Prove mode-off byte-equivalent replies, restricted writes, capacity handling,
   failure isolation and no inherited test/provider transports in a full isolated
   suite on Aegis. Add delivery acknowledgement only when an existing trustworthy
   producer can attest it; never relabel framework return as delivery.
5. Give Gloria a reviewed service/config change naming the exact private path,
   bounds and rollback. Enabling that distinct shadow mode requires her yes.
   The command belongs to that future tested increment, not this document.

Rollback must remove only the dedicated capture configuration and restore the
prior service configuration through Gloria's normal deployment route. It must
not change live workspace paths, model routing, feeds or delete private packets
implicitly. Retention and later removal of retained packets are separate,
explicitly documented operations.

Capture alone will not make turns strict-eligible: unknown assembled context,
indirect value-map dependencies, unobserved provider attempts and unconfirmed
client delivery still need their own evidence. No character verdict or live
steering is enabled by this proposal. Meanwhile, offline paired innovation
controls and provenance producers can continue on review branches.
