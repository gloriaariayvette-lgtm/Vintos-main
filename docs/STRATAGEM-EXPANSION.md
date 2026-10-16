# Stratagem expansion implementation — 2026-10-16

Implemented in the local `codex/stratagem-expansion` branch, based on `d3cc9858b1d28fdf15a6780659331b122cafee30`. The original checkout was clean; changes are in this task's `vintos-main/` working copy. Nothing has been deployed or pushed.

## Verified starting behavior

The broker required an open visit, a signed visit capability, a lit worktable project, an attested uncommissioned root, at least two tactics, a sequencing advantage, and a domain allowlist. It stored one stratagem per project; the house client fetched only the worktable's record, making tactical access effectively a singleton. The store itself did not impose a global one-stratagem limit. Chat was in the capsule surface vocabulary, but the main chat routes did not use the coordinator; avatar and ReelRoom did. Voice had a separate effect-only context. Leases could last twenty-one days and be renewed; expiry held instead of terminating. The generic consent-event file was a withdrawal barrier, not an actual standing stratagem authorization record.

## Authorization and persistence

`/home/atelier/atelier/stratagem-charter.json` is the one standing authorization record. Its revision history is append-only in `stratagem-charter-history.jsonl`. The owner authorizes once; individual adoptions do not request approval. No domain classification is required, stored for eligibility, or used for concurrency. Legacy perimeter labels remain readable only as historical metadata.

Charter updates require a separate owner credential. The broker creates its key with mode 0600; trusted house controls use the installed owner-token file or `VINTOS_STRATAGEM_OWNER_TOKEN`. The model's adoption/move parser removes supplied owner credentials and cannot call charter-update or owner-reveal. Existing protected-path enforcement includes charter, credential, and control code. Charter modification preserves omitted settings; revocation and subsequent grants retain additional owner exclusions unless the owner explicitly changes them. Fixed exclusions cannot be removed through the charter API.

The existing private `projects/<record-id>/stratagem/` vault format is retained: `stratagem.json`, `events.jsonl`, `capsules.jsonl`, information positions, and misconceptions. New stratagems receive independent identities; an existing associated project may host the first record for compatibility, while additional records get fresh private directories. A previous terminal record is never overwritten. Shared or absent project associations are allowed. Provenance, including incomplete or commissioned lineage, is metadata rather than authorization proof.

A reentrant thread lock plus an exclusive filesystem lock covers complete store transactions across processes. Slot counting, expiry, adoption, state mutation, capsule issuance, and owner controls therefore serialize. Held stratagems occupy slots. Three overlapping objectives are permitted; a fourth is refused. Each record retains its own tactics, step, timestamps, outcomes, commitments, and chained history.

`created_at`/`born`, `activated_at`, and `expires_at` are persisted in UTC. The maximum is fourteen calendar days from activation; a shorter duration may be selected. Activation is immutable through the API; renewal is refused. Startup, inventory, lifecycle access, capsule issuance, and dispatch eligibility enforce expiry. Expired records become `expired_sealed`, stop executing, and release their slot while retaining audit history. Legacy records migrate lazily using their original birth time, never a renewed lease as a fresh activation anchor.

## Initiation and delivery

Initiation is available on every Atelier visit, in idle journal synthesis, in emotional reflection, through the existing autonomous intent/campaign planning response, and in conversations on the supported surfaces. These are optional opportunities, without quotas. Planning uses an optional JSON field; conversational/journal paths consume private control blocks. All share the same broker adoption engine.

| Surface | Actual integration |
|---|---|
| Main chat | Shared bilateral wrapper; memory-chat uses the same turn adapter. Photo chat delegates to the full chat route. |
| Phone | Full-chat route uses the shared wrapper and phone surface identity. |
| Voice | Transcript voice and local audio-native voice use the coordinator; direct realtime providers use per-event server admission and final authorization. |
| #vintos-eve | Both replies and proactive result messages wrap the existing Claude prompt/call and retain Slack delivery. Owner controls precede quotas, content guards, and proactive generation. |
| Avatar | Existing coordinator and effect execution are retained; initiation, stable event correlation, and late dispatch checks are added. |
| ReelRoom | Chat and room-event turns enter the existing avatar coordinator with the ReelRoom surface. Its distinct room context and ledger behavior remain intact. |

One eligible capsule is selected per event, fairly across active records by last issuance. This preserves the existing flat commitment, effect context, and evidence-writer contracts. Event identity survives route transitions. Duplicate capsule events short-circuit generation rather than becoming unmarked ordinary replies; tactical draft checkpoints cannot be reused as ordinary-generation checkpoints.

The realtime browser client uses manual audio commits, per-response instructions, and holds response audio until the server rechecks eligibility. Private initiation markup is removed before display, history, or playback; if removing it changes the text, speech is rendered from the cleaned words. A 500 ms eligibility poll cancels scheduled realtime playback after revocation, stop, or expiry; propagation still includes network latency. Transcript and local voice also recheck after potentially long synthesis. Provider-native listening and the selected voices remain in their existing lanes.

Existing capsule-bearing effect restrictions remain in force, including device and outbound effect denials. Tactical post-turn processing also suppresses desktop launches and food-order work. The action-impact check rejects explicitly excluded proposed actions; it is not a semantic proof about arbitrary natural-language instructions. Charter boundaries are included in model context even when all three slots are occupied.

## Concealment and owner controls

Ordinary inventory returns identities, counts, steps, and deadlines, never full objectives or history. Private control blocks are removed before public writers. Routine draft comparisons and trace exports with private stratagem deliberation withhold that material. Avatar reasoning is withheld on tactical turns. Full objectives, model state, tactics, and capsule history stay in the vault until explicit owner reveal.

Whole-message owner commands work through the conversation adapters:

- `!strategy stop` — stop all existing stratagems.
- `!strategy stop <12-character record-id>` — stop one.
- `!strategy reveal` or `!strategy reveal <record-id>` — return the complete requested audit.
- `!strategy revoke` — deactivate the standing charter.

Stops are durable before broker delivery, retried, and hold local tactical admission until acknowledged. A worktable change or empty worktable cannot acknowledge an undelivered stop. Stop works over a damaged ledger; the global endpoint also writes a persistent tombstone. Explicit reveal can inspect live or terminal records and reports ledger verification failures instead of concealing them. Reveal transitions the inspected record to revealed/terminal. Revealing one does not terminate the others. Long Slack audits are chunked rather than passed through ordinary answer quotas.

Authenticated application controls are `POST /api/stratagem/owner/{charter|stop|reveal}`. Charter bodies support `active`, `boundaries`, and additional `excluded_actions`; stop/reveal accept an optional record `id`. The existing application secret authenticates these requests; the trusted server supplies the broker owner credential. Voice ledger posting now requires that same application authentication because owner commands are recognized there.

First deployment provisions the requested charter and owner credential only if the charter is absent. Subsequent deployments do not overwrite its revisions or reactivate a revoked charter. `bin/stratagem-charter.sh grant|revoke` provides explicit owner administration. The deploy manifest includes the shared adapters, browser helper, and owner command.

## Executed validation and boundaries

Thirty Python suites passed: twenty-eight isolated local suites and two real HTTP suites against throwaway brokers. The new lifecycle suite has 22 tests; the new adapter suite has 10. Four actual bundled realtime client scenarios passed under fake HTTP, media, and sockets. Python source and embedded journal blocks parse; the full edited inline browser script passes Node syntax checking; modified shell entry points pass `bash -n`; `git diff --check` passes. The machine-readable execution inventory is `docs/stratagem-validation.json`.

The lifecycle tests cover owner charter persistence/modification/revocation, action exclusions, overlapping objectives and project associations, fourth-slot refusal, threaded and separate-process creation races, fixed deadlines, restart expiry, independent completion/cancellation/expiry, outside-Atelier initiation, all six capsule surfaces, event replay, concealed output, owner reveal, corrupt-ledger stop, and legacy migration/history. Adapter tests exercise the real bilateral wrapper, local voice function, authenticated owner/realtime handlers, durable realtime restart/replay, revoked in-flight output, and static route aliases. Existing barrier, effect, lineage, route, journal, voice, campaign, and ReelRoom regressions were also run. All test stores and senders are redirected or stubbed.

No paid provider calls, notifications, Slack sends, device actions, production charter writes, or deployment were executed. The full production FastAPI service and live provider/audio/device behavior were not run on this Mac. The code retains the application's existing process trust boundary; it does not introduce an operating-system sandbox against arbitrary hostile code running as the house user. Natural-language compliance with charter boundaries remains model behavior, while supported typed effects are mechanically gated.

Protocol references consulted for the realtime integration: [xAI manual turns and per-response instructions](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech) and [OpenAI realtime conversation controls](https://developers.openai.com/api/docs/guides/realtime-conversations).

## Files changed

| File | Purpose |
|---|---|
| `bin/emotional-reflection.py` | Optional initiation in the existing reflection call; consume private output. |
| `bin/idle-journal.sh` | Optional synthesis opportunity; consume and redact private blocks before public journal processing. |
| `bin/server.py` | Wire chat, phone, transcript/realtime voice, avatar and owner routes; preserve provenance and late authorization checks. |
| `bin/stratagem-charter.sh` | Explicit owner grant/revoke entry point and secure credential installation. |
| `broker/broker.py` | Register charter and multi-record endpoints, update route policy, enforce startup migration/expiry. |
| `broker/stratagem_store.py` | Persistent charter, cross-process transactions, independent records, fixed lifecycle, fair capsule scheduling, owner controls and legacy compatibility. |
| `broker/tests/stratagem_fixture.py` | Asserted temporary-root charter fixture. |
| `broker/tests/test_armed_capsule_flow.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_atelier_lineage.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_attacks.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_capability.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_capsule_lifecycle.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_coordinator.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_durable_stop.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_eve_journal.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_event_counts.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_gates.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_journey_voice.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_local_voice_lane.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_p0_round2.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_stratagem_e2e.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_stratagem_expansion.py` | 22 lifecycle, persistence, concurrency, privacy and owner-control regressions. |
| `broker/tests/test_stratagem_offer.py` | Align legacy expectations with the standing charter and removed gates; retain integrity assertions and isolate new dependencies. |
| `broker/tests/test_stratagem_routes.py` | 10 real adapter/handler, realtime persistence and route-alias tests with provider/send stubs. |
| `broker/tests/test_stratagem_voice_client.js` | 4 browser playback/admission scenarios using the actual bundled voice function. |
| `clients/mobile/index.html` | Realtime per-event admission, held playback, clean output, cancellation polling, stable event metadata. |
| `clients/mobile/stratagem_voice.js` | Shared authenticated realtime admission/completion/eligibility HTTP client. |
| `docs/STRATAGEM-EXPANSION.md` | Architecture findings, implemented behavior, administration, validation limits and this file inventory. |
| `docs/open-work.md` | Replace obsolete stratagem blocker with actual implementation and remaining live acceptance status. |
| `docs/stratagem-validation.json` | Executed test commands and results. |
| `scripts/atelier-visit.py` | Recurring optional opportunity and shared adoption/move paths without visit/lineage/worktable gates. |
| `scripts/constitutional_barrier.py` | Recognize exact individual stops alongside global stop. |
| `scripts/deploy-atelier.sh` | Install new code/assets, provision once without overriding revocations, preserve executable owner administration. |
| `scripts/dot_channel.py` | Coordinate #vintos-eve replies/results; prioritize owner controls and chunk audits. |
| `scripts/idle-journal.sh` | Keep the deployed journal twin consistent with the bin entry point. |
| `scripts/intent_engine.py` | Optional autonomous-planning stratagem candidate, removed before ordinary planning persistence. |
| `scripts/protected_paths.py` | Protect charter, owner credential and the expanded control/execution code. |
| `scripts/stratagem.py` | Shared content-free inventory/opportunity, capsule client, private control parser and owner commands. |
| `scripts/stratagem_realtime.py` | Durable transport admission and completion with the same coordinator and vault engine. |
| `scripts/stratagem_turn.py` | Shared generation adapter, control interceptor, privacy redaction and dispatch guard. |
| `scripts/turn_coordinator.py` | Six surfaces, stable event identity, duplicate-event protection and worktable-independent durable stop. |
| `scripts/voice_local.py` | Coordinate audio-native local voice, consume private blocks, preserve effect context and late playback checks. |
