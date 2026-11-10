# Wall-clock gates under a backward step

Review note #55 reports an approximately 2.8-second backward wall-clock step every
30–45 seconds on the review host. That observation is reviewer-supplied, not a host
measurement performed here. The retained historical tracebacks lack the gate's
numeric operands, so this is a supported candidate mechanism, not retrospective
proof of which bound failed. This table records the original gate analysis; the
scoped #56 implementation below changes two source paths, with no host change.

| Named source gate | Can a roughly 3-second backward step break it? | Smallest robust design change |
| --- | --- | --- |
| `scripts/latent_feed.py:evidence`, `age = now - generated_at` and `epoch(cutoff) > now` | Yes: a just-written packet can become `future_packet` or `future_cutoff`, even if its content and checkpoint match. | Retain wall dates for evidence chronology; add a producer/consumer clock-domain receipt and monotonic freshness within a verified shared boot/domain. A changed or unknown domain stays unavailable. Do not remove the independent source-before-cutoff check or broadly admit future evidence. |
| `scripts/chemistry_lab.py:_human_identity`, `0 <= age < 86400`; `scripts/lab_sources.py:receipt` writes `retrieved_at` | Yes: a just-created receipt can have negative age, causing another lookup during grounding. | Cache the same-process verified receipt with monotonic expiry. For persisted reuse across processes, retain domain-qualified monotonic receipt time or an explicit bounded clock uncertainty policy; keep the one-day expiry and scientific identity checks. A tolerance would concern cache freshness only, never research evidence chronology. |
| `scripts/want_agent.py:_artifact`, `created - 2 <= mtime <= time.time() + 1` | Yes: a valid new file can exceed the upper bound after a step, or a file created after the step can fail the request's lower bound. The existing 2-second lower tolerance already covers the fixture's under-11-ms rounding. | Retain request-specific paths and byte checks. Attest file creation/observation under the request's own monotonic lifetime and recorded digest; preserve raw mtime as diagnostic metadata. Filesystem mtime alone cannot prove causal production during a stepped wall clock. Do not merely widen the window. |
| `scripts/witness_capture.py:Capture.request`, `_record_finalization`, `finalize` compare event clocks against start/prior nodes | Yes: a later event can look older and lose its witness receipt. | Record same-run monotonic sequence/elapsed evidence plus a wall anchor and clock domain throughout the receipt path. Keep original wall readings and distinguish cross-process ancestry. Do not clamp event times or relabel a failed causal check as witnessed. The current followthrough fallback preserves the decision but marks capture unavailable. |
| `scripts/witness_capture.py:finish_value_map_context`, `finish_value_map_call`, `finish_value_map_build` check nested start/end/read bounds | Yes: context/read/call/build ordering can appear reversed. | Carry one clock domain and monotonic event order across the nested build; preserve wall labels separately. Validate all nested observations in the same domain before admitting ancestry. Updating only the final timestamp would conceal missing ordering proof. |
| `scripts/witness_sink.py:recover_spool`, `age < 0`; `_publish_bytes`, `0 <= clock - retained_at <= retention_seconds` | Yes: committed ingress can be held until wall time catches up, and publication can refuse after a step between recovery and publication. This can exceed a 2-second test timeout without losing the durable packet. | Use same-domain monotonic retention age for new ingress/replay, retaining original wall time and conservative handling after restart/domain change. Keep the retention cap and configuration identity check. Do not turn unknown ages into fresh packets. |
| `scripts/witness_sink.py:_write_queued` recovery schedule | No for wall steps: its current startup/busy-queue cadence uses `time.monotonic()`. | No scheduling change needed. This does not fix the separate persisted retention gates above. |
| `experiments/character-reference/encode_cache.py:run` copy/encoding order | Previously yes: successive wall readings could reverse. Fixed in this tip. | One bracketed wall anchor plus monotonic elapsed copy/encoding times; record anchor/bracket/elapsed receipts. Invalid monotonic readings still refuse. This establishes run-local order, not cross-process UTC correctness. |

For the next failing isolated run, retain only aggregate numeric diagnostics:
wall operands and their difference, monotonic elapsed time, same-domain status and
fixed rejection reason. For artifact gates include `mtime - created` and
`mtime - now`; for cache/latent/spool gates include signed age. No private content,
paths, identifiers or notification destinations belong in committed logs.

Monotonic values are not epoch timestamps and must not be compared across arbitrary
boots or hosts. Persisted/live gates need domain-bound interval receipts; the two scoped
changes below implement these conservatively, with other gates still unchanged. The host clock correction remains the
owner's decision; these recommendations do not request additional model calls or
weaken evidence admission. Fixing the private producer does not make raw capture
complete: delivery, complete ancestry, references/modes and outcome anchors remain
independent requirements for the numerical judges.


## Note #56 implementation, pending independent review and deployment

`latent_feed.refresh()` now stamps new ordinarily timed packets with their
monotonic generation point, wall generation bound, exact cutoff and clock domain.
On Linux the domain binds the boot ID and time-namespace inode; elsewhere it is
limited to the creating process. These private runtime identifiers are never
written into public fixtures or reports. `evidence()` requires a matching domain
and unchanged generation/cutoff binding before using monotonic freshness. It still
refuses negative elapsed time, expired age, future evidence beyond the producer's
wall bound, changed checkpoints and removed/changed source evidence. A forward
wall age can expire a packet earlier, so suspend or forward correction cannot
extend its TTL. A backward wall step alone cannot make an observed earlier packet
future. No tolerance widened. Old packets and explicit `now=` replay calls retain
their existing wall checks; no receipt backfill or content regeneration occurs.
New receipts from a different boot/domain stay unavailable rather than falling back
to a permissive wall comparison. The existing refresh CLI uses the new path.

`begin_shadow()` now opts its request-local `Capture` into measured monotonic
lifecycle ordering. Requests, observed results and final boundaries retain actual
wall readings plus elapsed samples (bounded to 128); fork/domain loss or invalid
monotonic order still refuses. A backward wall event no longer discards the whole
capture. The private packet retains the event and observed model metadata, marks
wall order unknown, and emits an unknown witness receipt. Even if the final wall
time later recovers, the intermediate reversal remains unknown. This fixes packet
retention, **not** cross-process chronology or strict judge scoreability. No raw
clock is clamped, rewritten or mapped into a fabricated epoch. The coverage report
can count the packet's retained raw final time while still denying admission.

Direct/reconstructed `Capture(...)` calls without a contemporaneously observed
interval keep strict wall checks. In particular, `want_working_thread` reconstructs
capture after the action: it cannot honestly recover earlier monotonic intervals,
so its existing unavailable-capture fallback remains. Value-map nested build clocks,
Lab identity reuse, artifact-mtime admission and durable-spool retention gates are
not changed by this commit. Host correction and their future receipt work remain
separate. Tests use synthetic inputs and injected backward clocks, never services
or private observations. Neither change makes missing ancestry or delivery known.


## Review #58: artifact upper-window uncertainty

New want requests pair their raw created_at wall bound with bracketed monotonic
samples and a boot/time-namespace domain (process-local fallback elsewhere). The
filesystem comparison still uses wall mtime, created_at minus two seconds, and
current wall plus one second. When only the upper comparison fails, a matching
anchor can establish a backward wall discrepancy; mtime must still be no later
than the anchored upper estimate plus the same one-second allowance. Such a file
continues with unknown_order, never an assertion of causal creation. Raw clocks,
elapsed bounds and the discrepancy remain on the revision's clock checks, including
after repeated arrival/completion. CLI manifests retain the initial observation.
Unknown ordering does not bypass exact request paths, hashes, known-output rejection
or any other delivery gate. Legacy or changed-domain anchors cannot authorize this
path. The lower wall bound remains unchanged, including its backstep limitation.


## Review #58: identity cache and recovery exception boundary

Source receipt serialization and identity cache reading now both use time.time.
A persisted negative cache age is unknown: re-read that wall clock exactly once,
then use/count the existing refresh if still unknown. Process-local counters expose
unknown_age, wall_rechecked, wall_recheck_resolved and unknown_age_refresh without
source contents. New successful fetches retain a bounded exact-digest interval
anchor scoped to process, path and symbol. That interval prevents repeat lookups
during same-process grounding/retrieval after a wall backstep; the persisted receipt
must still match byte-for-byte. The one-day cap uses monotonic elapsed and permits
early forward-wall expiry. Unknown/reversed intervals, changed rows/processes and
expired receipts cannot reuse it. Failures cache nothing; identity validation and
research chronology are untouched. No persisted age is reclassified as fresh just
because its wall age is negative, and no model call is added.

recover_spool now catches configuration/clock acquisition exceptions within its
existing recovery boundary, counts spool_replay_unconfirmed, and keeps the writer
alive for volatile work and subsequent recovery. Durable ingress remains intact.
The separate persisted spool-retention wall-clock gates remain unchanged.


## Review #59: retained latent consumer-test failure

The reviewer retained future_packet from test_09 during a real-host 20-run stress
check (latent 19/20, capture 20/20). That fixture used explicit refresh(now=...),
which intentionally creates a legacy replay packet without a freshness clock,
then invoked real consumer paths with their default wall clock. A backward step
correctly refuses that combination. Consumer tests 05/08/09 now use default
refresh and assert a monotonic freshness receipt. Replay tests retain explicit
clocks, including a 2.8-second negative control that still refuses future_packet.
Each consumer path passes 50 injected post-publication backward steps in isolated
synthetic fixtures. Production gates are unchanged. This establishes the retained
fixture mismatch, not a general explanation for every historical clock failure.


Note #64: durable ingress v3 carries a process-random domain plus PID and a
monotonic staging point. Recovery in that process uses the larger of monotonic
elapsed age and wall age: forward steps can expire early, backward steps cannot
renew retention. Original packet contents and original retained wall timestamp
are unchanged. Legacy v1/v2 and foreign-process v3 entries still use wall age.
Negative/unknown order is retained unchanged and counted as retry-next-pass for
at most eight observations, then held with one diagnostic; the normal wall check
continues and may release it once order is known. At most 64 retry records are
kept in process memory. This does not publish unknown-age legacy entries, add a
tolerance, rebase their timestamps, or silently expire them. Restart loses these
process-local diagnostics, not durable records. Nonfinite clocks remain inert.

### Forecast launch prefix compatibility after ingress v3

The handoff fixture now asserts v3 staging and retains an explicit converted v2
fixture for already-staged launches. Both test invalid/missing prefixes and replay
under only the launch prefix. v3's two allowed prefixes exposed an additional
regression: a launch header changed to `capture-` was accepted because its payload
digest still matched. Recovery now checks that the payload's exact
`self-forecast-launch-v1` discriminator agrees with the launch prefix, rejecting
both launch-to-capture and capture-to-launch relabeling. This is a consistency
check, not authentication. Legacy v1/v2 handling, retention clocks and payload
bytes remain unchanged; no new producer or model calls are involved.
