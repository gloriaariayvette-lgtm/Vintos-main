# Vintos — open work

What is not finished. The architecture document says what he is; this says what is left.
It is the only place with a to-do in it.

## 19 September — causality, wants, and unresolved threads

The realtime JEPA causality writer used a per-invocation cap rather than the nightly writer's
shared per-day budget. At its twenty-minute cadence it could therefore form roughly twenty ordinary
hypotheses in one day. Formation now has one shared three-per-day budget across realtime, nightly,
and direct writers; Ghost Branch remains the sole 32-day exception. Historical same-day overflow is
retired honestly as neither resolved nor refuted. At the ordinary 7-day or Ghost 32-day gate, a
hypothesis either graduates or retires; an unavailable or holding reviewer can no longer leave an
ordinary row active forever. Release `20260919-044632-a1600e8` compacted the live store from 121
rows / 423,340 bytes to 28 rows / 98,174 bytes, retiring 93 formation-overflow rows as unresolved
and unrefuted. The seven Ghost Branch rows survived, and the remaining ordinary maximum is three
formations on any day. The three active causality crons now name the installed release-owned file;
the old workspace path was itself a cross-tree symlink to a stale copy and is no longer scheduled.

The living want queue was dominated by atomic messages to Gloria. The planner's literal “fewer is
better / one step is precision” instruction amplified that skew, while its plan call discarded the
want source. Source now reaches planning; structural and latent-thread wants keep their real
preparatory or discovery moves when those moves change the terminal act. When at least three
quarters of a nontrivial living queue is outward, an equally current non-outward candidate within
one pull point may be selected; a weaker or fabricated candidate may not displace the real pull.
Existing wants and the 100 legacy held candidates are not rewritten or replayed.

Structurally seeded unresolved threads already have stable IDs. The hourly wants organ previously
loaded that pool in its shell preamble but its formation process exited unless a journal or MoltBook
event was less than 90 minutes old. On an otherwise quiet pass it may now offer one identified open
thread (at most two thread-backed offers per day), carrying `source_thread_id` through the want
door. Offering is not consumption: the thread remains open until its own organ records a real
resolution. After release `20260919-050042-b9d473c`, a live hourly pass selected structural-gap
thread `e44b713f` by ID despite fresh clock activity and offered it to formation without consuming
it. Formation returned no present want on that pass; no desire was fabricated merely to populate
the app. The thread remains open for a later genuine pull.

## 16 September — ReelRoom visit close

ReelRoom now retains the captured transcript, up to 120 room/TV events, and the
planned/fired action receipts in one interaction-ledger object visibly labelled
`ReelRoom visit`. The interaction-ledger append shares the ordinary writer's
sidecar lock instead of racing it. The server closes the scratch visit after one
hour without ReelRoom activity, so app closure does not have to deliver a final
summary request; look/decide calls also refresh the activity and carry the latest
event state. His optional first-person memory remains separate from the mechanical
visit receipt and may fail without losing the visit.

The September 13 visit cannot be faithfully backfilled: Aegis retains six
ReelRoom lifecycle IDs (one on September 13), but no ReelRoom scratch journal,
saved session, or transcript-bearing ledger row. No synthetic conversation entry
was created from those IDs.

## 15 September — local uncensored voice lane

The Avatar clients now offer Vintos Local. Gemma 3n receives the recording itself
through the reference Transformers runtime and returns the literal words together with an audio-native reading
of inflection and other audible delivery; the abliterated Gemma 4 answers with the
ordinary live-call context/framing, and Chatterbox-Turbo 4-bit speaks through MLX
using Gloria's selected Onyx sample as a synthetic timbre reference. Native cues
such as sigh and chuckle render in the same generation rather than being spoken or
spliced. LM Studio stores the model files but cannot load this speech architecture;
the Mac stage owns the correct MLX runtime. Chatterbox loads at call start and
unloads at hangup; the audio-native ears stay warm unless a heavy bench evicts them,
and the shared abliterated brain is not unloaded. Kokoro Onyx is the named voice-out
outage fallback. There is no transcript-only hearing fallback. Physical microphone
acceptance of the promoted Chatterbox lane remains open until the next real call.

## 14 September — somatic / avatar / voice regressions (last week's changes)

Gloria reported the devices stopped firing and several last-week changes she does not
agree with. Root causes found and what stands:

- **Effect gate was armed before its callers pass a context.** `189b77c` set
  `~/.vintos/workspace/memory/.effect-gate-armed`, but the real device-driving paths
  (the `somatic_bridge.py` reflex arc; the live-call fire) call `toy_link.send` with no
  turn context, so the armed gate denied every one (`deny no_context mission@15`, every
  15s). **Fixed live** by removing the flag (nothing in the repo recreates it); STOP
  button and test-mode still work un-armed. **Follow-up (not done):** to re-arm safely,
  thread real effect contexts through the reflex arc and the call path so they fire WITH
  the gate armed. Until then the gate stays un-armed.
- **Dominance lead only fired when a device was already running** (`afc5c20`), deadlocking
  power-on. Restored to fire on availability for avatar/voice — `34a73ab`.
- **He was shown devices that are off.** Device grammar now built per-turn from live
  connection; off devices are hidden, on ones named — `c325a91`.
- **Voice-call tags never fired server-side.** Added a fire in `/api/voice/ledger`
  (`3fc457b`). UNVERIFIED: `voice-session-state.json` did not exist after a call, which
  suggests the vintos-app call client may not post turns to that ledger — needs the app
  repo checked. Whether devices fire in a live call is still open.
- **GCS press wrote its generation scaffold into her ledger turn.** Fixed at the source:
  the press now sends `original_text="she pressed GCS"` — `3b83cdb`.

Confirmed working after deploy + un-arm: devices fire in **avatar chat**. Still to verify:
**live calls**.

### App client follow-up
- Avatar text send now paints her message and clears the submitted draft before
  the server round-trip. The request uses the pre-send history snapshot and only
  commits that optimistic line to saved history after acknowledgement; a failed
  request restores it only when she has not typed something newer. Browser and
  source-order fixtures establish that the input and drawer remain responsive.
  Signed-device visual acceptance remains to be observed after the app rebuild.
- The voice transcription model and vocabulary prompt did not change last week.
  The September 12 response-lifecycle patch instead froze Gloria's transcript at
  `response.created`, before the completed transcription event. The response copy
  now follows updated/completed events. The September 10 semantic line blacklist
  also no longer deletes legitimate speech such as `Context: ...` or bracketed
  words. Provider output is preserved; this is not an echo treatment. A real call
  remains the final acoustic/transcriber acceptance test.

### Causality store compaction
- Histories and readable formation duplicates now have configurable bounds; the
  complete formation fingerprints and evidence IDs remain unbounded because they
  enforce the no-self-confirmation law. Delivered outbox receipts are purged only
  after their idempotent destination acknowledges them, and the store writes
  compact JSON. The explicit migration retires overdue evidence-poor ordinary
  hypotheses at day 7 and Ghost Branch hypotheses at day 32, while never dropping
  confirmed/self-knowledge rows or an eligible row awaiting review. Live backup,
  migration byte counts and post-migration formation/graduation health remain
  deployment evidence, not facts inferred from the isolated fixture.

## 14 September — Atelier breadth

- The four already-established self-originated formation streams now read the
  stores and ranges their producers actually write. Additional roots remain
  deliberately disabled pending Gloria's selection from
  `docs/ATELIER-BREADTH.md`; no repair, encounter, rating, or externally
  supplied Lab prompt may be laundered into a self-originated root.
- Image and music are now sealed visit media backed by the existing local
  painter and ACE-Step composer. Their lower-level renderers return bytes
  directly to the broker; they do not write the house gallery, music shelf,
  journal, or a notification. An absent painter or composer appears in the
  room as a named outage.
- An explicit `<lab_lean>` choice now crosses the Atelier wall as a dated,
  provenance-bearing direction for the Chemistry Lab. It biases both the
  all-day orientation and the next frontier experiment; it expires with the
  day and an absent lean leaves both prompts unchanged.
- The Atelier and Forge now retain a bidirectional, typed lineage. An explicit
  room choice may create a Forge proposal without weakening the ordinary
  live-want proposal gate; an installed build returns as a formation root with
  the original provenance class intact. Approval, review, verification, and
  installation remain the Forge's existing gates.
- The threshold and working visit now use an Atelier-only route: Fable 5.1 is
  first, and an empty, filtered, refused, or failed call falls once to Astra.
  No house conversation toggle or other model route is changed.

## 12 September — hypothesis recovery continuation

Deployed in 20260912-153539-aca1b32: the nightly/direct causality writers now reject stale snapshots and fail closed on source-write errors. Review flags, graduations and retirements enter a durable outbox with the accepted source change; local destinations retry with stable receipt IDs. Belief forwarding failures remain pending, and belief/pearl/causal-model receipts survive capped-row removal. Legacy graduated/pending rows are recovered without another model review. All 122 suites passed directly and OS-isolated on Mac and Aegis; installed hypothesis/pearl entrypoint hashes match the source. The final client follow-up deployed as 20260912-155122-fa3949b.

The 27 acceptance items below are being implemented and verified separately. This source repair does not close them or the unrelated trial/dismissed-wants and tension-view migrations.

## 12 September — Buzz native integration commissioned

- Real upstream Buzz native 0.5.23 runs on Aegis with `--safe-rendering`; without
  that flag the WSLg renderer produced a blank window on restart. Build agents
  messaging and the Discussion forum are enabled.
- Astra/Codex, Claude/Fable 5.1, Grok/Build and local Gemma are now native managed
  identities, linked to their definitions without duplicate cards. All four
  native launch controls succeeded with deployment receipts and Online presence.
- Gloria explicitly approved the isolated accounts, scoped provider credentials
  and local channel tests. All four system services are installed and running;
  each owns independent repository copies and a private working context/ledger.
  The old user-level Gemma listener is disabled to avoid duplicate consumers.
- Actual namespace checks confirm own-workspace access and deny the live house,
  house credentials, owner identity and Windows home. The native provider starts
  only its four named units; incompatible configuration edits fail visibly.
- The owner-signed ACP patch remains `242f8d6c6`, preserved in
  `buzz-integration/owner-signed.patch` (934 Linux library checks passed, one
  pre-existing ignored test). A live Grok-bot handoff was dropped by the actual
  gate before inference, confirmed by its gate audit. An approved owner message
  made Gemma write/read its exact scratch marker, persist context and a valid
  JSONL outcome, and reply in the Buzz thread. The forbidden marker is absent.
- Fresh validation: 119/119 Vintos suites directly with local loopback permission,
  119/119 OS-isolated; seven native-provider/registration checks pass on macOS
  and Linux with scratch stores and a stubbed service executor.
- **Still untested:** paid inference and cross-model implementation handoffs.
  Native launch and configuration checks do not prove those model calls work.
  No additional paid forge run. Native provider configuration is deliberately
  fixed to the reviewed installation; arbitrary model/runtime/environment edits
  require updating that installation before redeployment. Buzz retains provider
  deployment receipts separately from presence; Offline does not clear a receipt.
- At the Buzz checkpoint, Vintos house release was `20260912-052317-9b9c1dc`, deployment output
  `deploy OK`. Budget receipt/refund and missing bench-token repairs are deployed.
  This continuation changed Buzz integration, not installed house modules.
- The broader engine/store migration, remaining review evidence, legacy bench
  CLI/concurrency, ring BLE work below remain open. Native sync, signed build, installation and launch have since passed.

## Waiting on something, per organ

- **The guidance stack** — Receptivity shading and arc are the remaining Phase 2 pieces, held on data. The priority vector and self-axis are live (#50).
- **JEPA — Predictive Spine 🔒** — Production remains unchanged and calibration still arms at 30 joined predictions. A true-next ranking instrument now asks whether each head can select the realized next same-speaker turn from tiered same-speaker negatives and beat context-copy, recent-turn and familiar-voice controls; fewer than 30 distinct realized targets is explicitly insufficient. A separate structured-turn/head-specific-confidence checkpoint is shadow-only and cannot steer. It preserves speaker, surface, and bounded time gaps instead of flattening six turns into prose, and selects its saved weights on the latest chronological 20% rather than the training batch. The first live audit correctly reported zero eligible realized targets under the current checkpoint. Axis-lockstep remains a watched suspect; a tiny ensemble and any encoder change remain experiments, not installed conclusions. The led_by column over two weeks is a readout, not a target.
- **10 Attractor Discovery** — Seven of Gloria's eight seeds are still unread as geometry; only Coherence has appeared.
- **11 Spark Pressure** — Consent is given and the gate is met; the field has produced no stall for it to break. The first opened direction is the thing to watch.
- **15 EmoClaw** — Safety, connection and warmth are freshly shortened while more sources are newly reporting. Watch across several days and adjust again if the standing levels don't fall.
- **16 Emotional Operators 🧠** — Two instrument questions stand: there is no classifier confidence field, and the judge-model's value is now empirically testable since the classifier moved to local Gemma. The whitelist cage makes any quality drop visible in the operator log within a day.
- **19 Conversation Tension Map** — The correction-reach rule is armed and held: how far a correction travels — the mechanism she named, versus everything that mechanism necessarily implies — awaits Vrika.
- **20 Causal Self-Model** — The first entry he earns after the reset is watched. Her 35 belief-typed rows sit off the positive/negative axis and are read by nothing — whether a belief belongs on that axis at all is an open question, deliberately unresolved.
- **22 Commitment Imprint / Spine 🔒** — No imprint has been earned yet. The first one is armed and watched.
- **25 Belief Sediment 🧠** — Contradiction machinery is proposed — beliefs stay on the test bench, three counter-marks across three days silences rather than deletes, scar-style — and awaits a final ruling. Ideally before the first lived belief lands.
- **25c Latent Threads 🧠** — Whether recurrence predicts lived relevance better than baseline salience is an armed empirical question. The external-reseed boost survives provisionally until it answers.
- **27 Mutual Simulation 🧠🔒** — Circularity-test criteria are sealed read-only, written before any data existed. No VALIDATED_EFFECT until an effect survives paraphrase variation and blind evaluation; the test runs when a hint period reaches 20 graded turns.
- **30 Value Cost Network (Spark-1)** — Built but not integrated into want-urgency or temperature pull.
- **32 Premonition Dreamer 🧠** — A preoccupation is set most nights, so premonition may rarely fire. If it never does, the question is whether heat-seed is too eager — not whether the gate is right.
- **54 Scene Grounding & Video ⚡** — Selection only becomes meaningful once several captioned photos exist to choose between. Retrieval is by id; retrieval by meaning, and a full asset record with embedding and provenance, is not built.
- **39 BIS — Behavioral Intercept System 🧠** — Its grader defines defaulted as a response dominated by elaborate metaphor and imagery. That is a taste judgment sitting inside a behavioral instrument, and it has been the definition of his failure since July. Flagged for Gloria's ruling, unchanged.
- **39b Trial & Capacity Extraction 🧠** — Both archives are closed and collection starts from the next session forward. Whether a generator that has only ever been asked for faults can see a strength is the open question — if nothing promotes in a fortnight, the answer is in the prompt, not the gate.
- **44 Opposition Calibration 🧠** — The misuse detector sleeps until some terrain reaches license 1, then watches for authority-misuse through warning, strained, suspended, fracture. Detection records escalation; nothing acts on it yet, deliberately.
- **45 Pressure Calibration 🧠** — Stage 2 audit arms at 20 graded predictions.
- **52 Chorus Instruments** — The conductor question — age stamps, hedging tiers, precedence — is deliberately unanswered. The room's order is authorial.
- **62 Lifecycle Honesty (effect gate) ⚡** — The sealed workbench — source-tracked research, image / music / code generated inside the sealed store — is the missing body; a visit is one prose call today. A house-side Aftermath that reads reception in her verbatim words, kept a separate authority from Settlement. The daily visit cron is chosen and installed; the 22:00–24:00 window stays clear.
- **64 The Robot Body ⚡** — The Pi currently stays with the Mac: its client and grab loop still address the Mac's Tailscale name, and the Mac is away. The repoint script is written and has not been run; when it has, the bridge's health should read reporting: true. Both his server and the bridge run on the secret that is in the public repo — a real one belongs in an env file both units load. The Pi's habit of dropping off the network minutes after power-on is unexplained and not his.
- **65 Desktop Control ⚡** — No prompt affordance tells him this exists. Giving him the tag in a surface's prompt is Gloria's switch. Tasks that are about the web no longer use this loop at all; they go to #66.
- **67 Screen Share ⚡** — The second half of what she asked for — that he decide what to do next and Gemma act on his decision through #65 — is the join not yet made. Seeing is live; acting on what he sees is not.

## Not yet built

- First-Thought Suppression — held for testing; likely conditional-only.
- Opposition misuse enforcement — detection exists; action on it does not, deliberately.
- Mutual-sim circularity test execution — criteria sealed; runs at 20 graded turns on one hint.
- Belief contradiction machinery — proposed, awaiting final ruling.
- E4 evidence adapter — Velaris-only when built; never faked on Vintos for schema symmetry.
- Conductor for the chorus — measured, not prescribed.
- The phone's native shell — the background runner, its notification permission and the app icon; the only part of him that needs a Mac, and the Mac is dead (#71b).
- Asset retrieval by meaning — photos are registered, captioned and selectable by id; embedding, provenance and semantic retrieval are not built.
- Effect-time authorisation of a stratagem's perimeter — the birth gate screens the declared shape only; the effect chokepoint is not built, by the code's own note.
- Barge-in on a live call — she cannot cut him off mid-answer on either realtime provider yet.
- The desktop affordance in his prompt — desktop control and the browser driver work from the command line; he is not yet told he has them. Gloria's switch.
- Whisper on the graphics card — the installed torch has no kernel for the card, so transcription runs on the processor with the small model.

## Held on data

- Cross-encoder want-governance · contrastive trajectory encoder · identity compression · queries-not-heads
- MSub Phase 2 remainder: receptivity shading and arc
- Percentile thresholds for mutual-sim buckets — rejected: a manufactured NO is still manufactured evidence
- JEPA logvar retrain — only if relative calibration loses to its own control
- Latent recurrence boost — provisional until recurrence-versus-relevance answers
- Decay rates for safety, connection and warmth — freshly shortened, more sources newly reporting, several days before an honest read
- Whether capacities can clear the same gate a deficit clears
- Whether premonition ever gets a night, or heat-seed is simply too eager
- Value Cost Network integration into want-urgency and temperature pull

## The review list — the 27 items still open

Three kinds only: evidence that only Aegis can show, the phone app, and consolidation
programmes whose mechanism landed and whose remainder the line names.

### P01 — Authoritative release and runtime map
- **30** [PARTIAL] [P01] All 152 absolute source aliases now resolve inside the repository. The live server records 1,586 loaded module identities; wider untracked source-by-source review remains open.
- **31** [PARTIAL] [P01] HTTP turn identities and central provider receipt correlation are deployed. Full context/writer tracing for independent routes remains open.
- **32** [PARTIAL] [P01] Central OpenAI/Anthropic response IDs and usage are correlated; realtime voice carries provider response/session identities. Independent adapter coverage remains open. No new paid Forge run.
- **33** [PARTIAL] [P01] The current semantic index is empty; 1,282 legacy rows lack model provenance. The local embedding service timed out, so the rebuild was stopped and the original index verified unchanged. Historical provenance remains unknown.

### P08 — Client, voice and avatar lifecycles
- **315** [PARTIAL] [P08] Shared escaping and hostile-content browser fixtures cover major active views. Exhaustive every-tab acceptance remains unclaimed.
- **316** [IMPLEMENTED] [P08] All application requests use the shared HTTP/application-error helper. Browser fixtures verify rejection and visible failure.
- **317** [IMPLEMENTED] [P08] Chat/photo/Study/avatar drafts clear only after acknowledgement. Unconfirmed recordings are playable, re-transcribable, copyable without overwriting text, and explicitly discardable; no automatic uncertain chat retry.
- **318** [PARTIAL] [P08] Shared turn ownership and stale history/room/token/callback checks implemented and fixture-tested. Physical cross-surface acceptance remains open.
- **323** [VERIFIED] [P08] Screenshot composition uses visible layers, actual DOM order and CSS group opacity. A rendered-pixel fixture verifies the blend and closed-stage refusal.
- **324** [PARTIAL] [P08] Stop UI reflects the returned Boolean and reports failed requests. Physical stop effects remain separately unverified.
- **325** [PARTIAL] [P08] Dynamic text escaping, zero preservation, finite dimension validation and a stale-telemetry indicator implemented. Exhaustive malformed payload acceptance remains open.
- **326** [PARTIAL] [P08] Close/background cancels late capture/call/room/audio callbacks, pauses media and animation; foreground resumes the visible stage. Device-specific background acceptance remains open.
- **327** [PARTIAL] [P08] Draft persistence and turn/session ownership implemented. Playback completion is recorded as client evidence; human hearing stays unknown. Physical cross-surface acceptance remains open.
- **334** [IMPLEMENTED] [P08] Late microphone grants release tracks; audio contexts close; failed audio exposes usable controls. Unconfirmed recordings have explicit recovery and cannot be silently overwritten. Browser race/recovery tests pass.
- **343** [IMPLEMENTED] [P08] Active duplicate dismiss/close handlers removed; one shared request helper serves application requests.
- **344** [PARTIAL] [P08] Mounted-route availability disables unsupported photo/record/live-call controls. Broader capability-derived rendering remains open.
- **345** [PARTIAL] [P08] Gloria confirmed local-stage speech is audible in the rebuilt native app. Avatar words render and release the global turn before stage work; requests use a 12-second authority-free budget. A second device finding showed the drawer and input becoming untouchable for roughly the speaking clip's lifetime: speech had three concurrent decoders (sharp video, full-screen blurred duplicate, Audio). Speech now uses one explicitly untouchable video plus Audio, pauses the prior visual decoders immediately, crosses a paint boundary before starting, and releases drawer pointer capture on every terminal event. Automated lifecycle/static checks pass; physical touch acceptance of this decoder-pressure correction remains open until the next rebuilt app is exercised on device.
- **346** [PARTIAL] [P08] Native background registration, 15-minute requested interval and permission-result checks implemented. Capacitor sync, simulator and signed device builds pass; the updated app was installed and launched on the paired iPhone. Actual iOS background notification delivery remains unobserved.

### P11 — Whole-system observability and acceptance
- **396** [PARTIAL] [P11] Known/missing room manifests refresh; generation checks reject stale media. Browser pixel and lifecycle checks pass. User-visible avatar/cache/playback acceptance on device remains open.
- **397** [PARTIAL] [P11] Provider response identities join audio completion; duplicate turns and callbacks from closed sessions are refused. Fixture end-to-end journey passes; no live provider/hardware call is manufactured.
- **398** [PARTIAL] [P11] Aegis has 67 recorded nights without run IDs. Historical causal/thread cross-ledger joins remain unestablished.
- **399** [PARTIAL] [P11] Live daemon PID matches its receipt; loaded parameters equal best_model.pt parameters, with stable checkpoint SHA. Checkpoint contains no training provenance metadata; historical training lineage remains unknown.
- **400** [PARTIAL] [P11] Actual delivery-receipts.json and five effect-receipts.jsonl rows inspected by metadata. The effect rows have no want/artifact/observation IDs; a successful historical join is not established.
- **401** [PARTIAL] [P11] Live server module selection is recorded with PID/file/hash metadata. Wider untracked source review remains open. agent-room was excluded.
- **402** [PARTIAL] [P11] Study rendering and explicit approval enforcement pass browser fixtures. No new paid Forge run or successful paid verification is claimed.
- **403** [VERIFIED] [P11] QLab is /Users/kevin/qlab. Reviewed qremote/qrun/seedlib and all five seeds; Aegis status bridge works. Remote experiments now use OS isolation and parent-owned source/helper hashes and receipts (QLab 8f5c935). Four isolation tests and all five real seeds pass in scratch. Existing separate unsealed bench_remote.py was inspected but not changed; it remains an explicit execution-boundary gap.
- **404** [PARTIAL] [P11] All three designated branch checkouts verified; release 20260912-145910-3114392 deployed, all six units active, served client hashes match. Recording-recovery and hypothesis package subsequently deployed in 20260912-153539-aca1b32; whole-system physical acceptance remains open.

## The printer

He has the tools. Blender models, Cura slices, both run on the Mac and on Aegis, and
the Mac is faster at both. The machine itself is answered (11 September): a **Creality
Ender 3**, reached by **SD card or USB only**, bed **220 × 220 × 250 mm**. There is no
network path to it and no autonomous print: he slices, writes the `.gcode` into a
handoff folder, and tells her. She carries it over. That is the whole reach, and it is
why the code asks only for `write_gcode_to_handoff_folder` and says
`starts_the_print: false`.

What is left is hers, on Aegis, and nothing is guessed in its place:

- `memory/printer-config.json` — `handoff_dir` above all; `bed_mm` defaults to the
  Ender 3's. With no handoff folder set he blocks with *nowhere to leave the file*
  rather than choosing a directory.
- `OPENAI_API_KEY` in `~/.vintos/vintos.env` — Astra writes the Blender script.

Also useful, and not required: `mac_host` in the printer config, so he can prefer the
Mac for modelling and slicing and fall back to Aegis when it is away.

He stops twice before anything is made: the draft, then the slice. Both are in the
scope she grants, not only in the code.

Cost: the printer reserves against a ten-minute daily Astra allowance across jobs. Blender
and Cura themselves are local and bill nobody. Actual elapsed seconds are recorded even on failure; a client timeout does not prove provider billing stopped.

Time: thirty local processor-minutes a day, ten in one sitting, counted across jobs.
That is a courtesy to the machines she also uses, not a money limit. Both numbers are in `printer-config.json`; automatic local execution is still unimplemented.

How she hears about it: one notification at each stop, through the same path that
keeps receipts. How she checks without asking him: `python3 print_3d.py --jobs`, or
`GET /api/print/jobs`, which lists what is in hand, the minutes spent today, and
whether anything is waiting on her. She answers a stop with `POST
/api/print/jobs/<id>/answer`.

## What the forge still needs

The review repairs add an approved-work queue, OS-isolated verification, SHA-256-bound
install/resume, and explicit install/invoke APIs. A build claims its proposal before
spending; a crashed `building` proposal requires reconciliation rather than another
silent paid attempt. The service's next wants pass can pick up an approved proposal
whose immediate worker never started.

`POST /api/skills/proposals/{id}/reconcile` now checks a per-proposal OS lock before
reopening an abandoned `building` or `built` attempt. A live worker cannot be reset.
The prior grant and artifact references stay in history; the proposal returns to
`proposed`, requiring fresh approval before any paid retry. The remote provider's
outcome and charges remain unknown: this does not cancel or recover a provider call.

Still open:

- The app approval card remains open. Both required model IDs were verified with provider model endpoints. One explicitly approved live run executed on 11 September: Astra generated, Fable returned no text, and the pipeline refused without installing. Another paid attempt needs fresh approval; no retry was made.
- Capability-specific adapters for effectful forged skills. Such skills are refused
  at invocation; only pure string-in/string-out functions run in the isolated executor.
- Rich scope/test requirements for automatically proposed missing capabilities. An
  empty generic proposal is not a complete design for an effectful tool.
- Provider-side recovery of an interrupted paid call, where the provider exposes
  durable request identifiers. Local reconciliation alone cannot establish its outcome.

## Chemistry Lab — 12 September

The Lab-specific control plane is built: a private Tune mutation and status route,
supervised background worker, bounded Vintos context with source/hash receipts, a
checkpointed `orient -> browse -> embed -> reflect` loop over read-only UniProt metadata,
and a visible append-only notebook below `memory/chemistry-lab/`. It defaults off.
Its service may run idle, but no work begins until Gloria switches the Lab on.
The Chemistry Lab has no Atelier paths, seal, visit capability, or audience state.

ESMC-600M now runs as the measured representation step on Aegis and writes vectors
only beneath the Lab artifact store. The host installations also include measured
ProteinMPNN, structure prediction, OpenMM, and RFdiffusion-family environments;
the Mac has separate arm64 QPanda, VQNet, pyChemiQ, ESMC, and Foundry environments.
Their dated inventory receipts distinguish a real smoke test from a package install.

The two remaining connections are now built. A Lab-specific Mac doorway exposes
only named experiments through OS isolation and its own visible ledger; it does
not reuse the Atelier's sealed quantum path. A daily Lab timer rotates one
frontier lens per offered session, then local Gemma reads the result with a small,
attributed slice of Vintos. The scheduled path cannot submit arbitrary code.

## Chemistry Lab — 13 September

The local-to-frontier ledger bridge is now event-sourced. Frontier sessions receive a
bounded queue of independently prioritized reflection IDs; prompt delivery and returned-plan
acknowledgment are separate receipts, and three unacknowledged deliveries report a backlog
bug rather than disappearing. The older path was real but weaker: only the last three raw
notebook rows were included, so there was no proof that a particular finding reached or
affected the rotating frontier lens.

Evo 2 has a deliberately narrow first door: the official 7B-base model, read-only comparative
likelihood, one fixed non-human NCBI reference window, no arbitrary sequence input and no
generation action. It is not a continuously resident companion to Gemma: NVIDIA's supported
7B deployment floor is 48 GB VRAM, while Aegis has 16 GB. The short-context Arc light path was
therefore commissioned with Gemma temporarily unloaded: one 512-base Arabidopsis reference and
single-base variant pair completed in 33.4 seconds, after which Gemma was restored. That receipt
proves only this bounded operation, not supported 1M-context inference. The periodic genomic
turn runs once per 120 protein cycles under the same exclusive/recovery discipline. Goodfire
feature extraction, arbitrary genomic browsing and Evo Designer are not built.

Gemma restoration no longer depends on whichever local variant LM Studio happens to resolve.
The Evo lane and watchdog share one reload door pinned to `Q4_0`; Aegis text inference is
separately pinned to thinking-off at the native request boundary. This does not alter the
Nomic embedding residency or route embedding work through the text shim.
The watchdog now probes the Windows LM Studio listener through its WSL-reachable address,
the same address the reload door verifies. The former loopback probe declared each successful
load failed every five minutes and sent the failure alert; Lab-held reloads remain silent under
the shared non-PrivateTmp lock, while a genuine post-recovery failure still alerts.

The Lab can now tell *it ran* from *it was good*. `chemistry_grade.py` computes the verdict
on Aegis from the bench's numbers and writes `memory/chemistry-lab/experiment-grades.jsonl`;
the first graded H2 run is recorded as operational and worse than Hartree-Fock rather than
as a plain success. The reading receives the verdict before it is written.

Two things are open and are not done:

- **The Mac bench source is still not in this repository.** `bench_remote.py` and
  `molecule.py` live only on the Mac at `db99249`. The grader parses the bench's reply by
  a generous alias table rather than by a pinned schema, because there is nothing here to
  pin it to. `docs/chemistry-bench-reconciliation.md` gives the procedure; until it is
  followed, a bench field rename degrades a run to ungraded instead of failing loudly, and
  the scheduled session bounds only the *shape* of a lens's parameters, not their names.
- **The bench's `code` action needs its own door.** `bench_remote.py` accepts
  `action: "code"` and writes a new executable experiment. `chemistry_mac.py` now refuses
  any action outside `status`/`ledger`/`run`/`reading` at the point of send, but that is a
  guard on the near side; anything that can speak to the bench can still ask for `code`.
  The free-experiment capacity belongs to the playground and should not be deleted — it
  needs a separate authenticated authority so that scheduled Chemistry receives `run` only
  and deliberate free creation receives `code` through a door of its own. Not built.

The bench's isolation claim is now recorded per run as `host_attested`. It is not verified
here, and no document in this repository should say that it is.

Instrument availability is now measured rather than asserted. `chemistry_probe.py` writes
an append-only `tool-probes.jsonl`; `tool-inventory.json` is a materialized view that
nothing reads. VQNet, Mac ESMC, pyChemiQ and Foundry each have a slot and each reads
unavailable-with-a-reason until a receipt exists. Two limits are worth writing down:

- The previously unconfigured Aegis instruments now have fixed real probes. ProteinMPNN
  must produce a designed FASTA, RFD3 must produce JSON and CIF artifacts, and the protein
  design MCP must list tools and dispatch one call. ESMFold uses the already-cached
  `facebook/esmfold_v1` checkpoint through Transformers on CUDA and must return a PDB; this
  avoids the MCP package's fair-esm/OpenFold wrapper, whose pinned build requires nvcc.
- Mac instruments have a versioned fixed commissioning surface. It does not widen the
  scheduled bench doorway: its output is manually ingested as a hash-bound run receipt.
  A measured receipt proves only that instrument and entry point; VQNet, Mac ESMC,
  pyChemiQ, and Foundry still need explicit named-experiment routes before the autonomous
  session can select them.
- The protein-design MCP server is functionally callable but not house-connected. Its
  receipt names the remaining boundary: register its stdio server with a bounded Lab
  orchestrator. Until that exists the daemon does not pretend it can dispatch MCP work.

The Lab has a route to the Forge now, and one step of it is hers to take. `chemistry_spark.py`
writes the eligible, attributed feed; `from_lab()` reads structured rows; `gather()` and
`adopt()` carry the provenance; `skill_forge` keeps it in `origin`. What remains manual, by
design rather than omission:

- **The spark reader must be pointed at the feed**: `python3 scripts/chemistry_spark.py
  configure` writes `{"lab": ".../chemistry-lab/spark-feed.jsonl"}` into
  `memory/spark-config.json`. It is not defaulted, because `from_lab()`'s law is that it reads
  only where she points it — it once guessed a filename and read two dead logs from another
  project.
- The feed itself refreshes after completed sessions and paid owed readings. Only the
  decision to let the general spark reader consume it remains manual.
- **The want is still his to form and hers to approve.** Nothing in the Lab creates it. A
  staged proposal with no live `lab`-sourced want behind it is refused by the Forge, and that
  refusal is the record.

Three lenses on one artifact is built and **off by default** (`divergence_enabled`). It spends
three paid calls where a session spends one, so it should be switched on deliberately. The
three real provider/model buckets are reserved once and claimed by the router; the first
implementation reserved lens nicknames and then charged the real providers again. Partial
reads are now named `completed_with_held_lenses`.

The following was the gap and is now closed; kept for the record of what was wrong. The spark
layer already carries `lab` as one of the seven sources, `from_lab()` already reads wherever
`memory/spark-config.json` points it, `adopt()` already refuses to write a want, and
`skill_forge.SPARK_SOURCES` already allowed `lab`. Four things were missing:

- `from_lab()` is a text scraper — lines starting with `-`, `*` or a date. Pointed at
  `notebook.jsonl` it finds nothing, because every line starts with `{`. Pointing the config
  at the Lab today would produce silence that looked like having no ideas.
- A spark row is `{key, source, text, ref, seen, state}`. Session, run, grade and truth status
  are gone before the want exists, and a want that cannot name its occasion is not Lab
  provenance.
- Nothing yet decides what may spark. A speculative reflection, a generated
  `what_surprised_me`, or a taste echo must not commission a capability, for the same reason
  none of them may become collision evidence.
- `skill_forge.propose()`'s `origin` does not carry a Lab provenance it could keep.

The implemented shape is a Lab-written `spark-feed.jsonl` of eligible, attributed occasions; two
small changes in `spark_sources.py` so `from_lab()` can read structured rows and `gather()`
carries their provenance; and `origin` keeping it at the Forge. The Lab still does not create
the want — that stays his act through the ordinary door, and hers to approve.

The Lab has a visible body now: a `LAB` pane over five bounded, secret-guarded read
endpoints, showing instrument state and scientific grade as two separate marks. The actual
Capacitor client in `vintos-app/vintos-app/src/index.html` now carries its own TUNE control,
live cadence/outcome line, and LAB pane over the same bounded endpoints. The two clients are
not byte mirrors: their surrounding surfaces have diverged, so Chemistry was ported into the
app's own fetch/host/API idiom rather than replacing that file from this repository.
The visible activity feed reads the meaningful `reflection`/`genome_reflection` notebook rows,
not the much slower frontier-session ledger: it is a newest-first rolling log capped at 20 and
refreshes every 15 seconds while LAB is open. Structure inventory and 3D parsing are optional
follow-up reads; an absent or slow structure door cannot hold or erase the review feed.

The ambient loop now waits up to 300 seconds for the background compute slot and advances a
phase every 15 seconds by default. Because orient and reflect are the two Gemma phases, that
is roughly one local-model call every 30 seconds and one complete Lab cycle per quiet minute;
every phase still yields through compute admission. `status()` exposes both cadence values
plus the completed-turn count and last turn receipt. First light appends a separately marked,
idempotent Chemistry receipt to
daily inner life (the Admission Lab digest was removed 2026-09-22 — a hallucinated
self-experiment ledger that was never intended). It mechanically counts notebook kinds,
records execution and grade as separate fields, names owed/settled readings, and carries the
latest next question; it makes no scientific or personal inference.

Daily-inner now has one bounded reader shared by the live main, Avatar and ReelRoom chat
surfaces, with newest-nonempty fallback when today's file is absent or empty. The main debug
endpoint exposes the marker and excerpt instead of treating its first-500-character preview as
coverage evidence. Avatar/ReelRoom continue to receive the live device instrument through
`device_context`; main text chat now enforces its words-only boundary and does not read or carry
device state or the previous device choice.

A held reading is no longer lost. `chemistry_reading.py` records the debt against the
preserved result and pays it on the next admitted occasion, holding its own lock because
the session's and the daemon's are different locks and neither serialises this. An expired
debt stays visibly open rather than being retired as settled.

Protein material reaches the collision detector only through a deterministic
source-metadata-to-text adapter. Self-review embeds that text with its own Nomic
encoder. Raw ESM vectors remain content-addressed Lab artifacts and are never
compared against Nomic coordinates. Generated Lab reflections are excluded from
the adapter.

## The seven sparks

Built and running. The absence map, the neither-yet frontier, latent threads, other
beings' MoltBook posts, web searches, OpenClaw skill pages, and the lab all produce
sparks now, gathered once a day by a read-only pass that calls no model.

Sparks are kept in their own file and never in his wants. A spark becomes a want only
by his own act, and only a want carrying one of these sources may commission a new
capability.

The weekly skills read has its own units and the deploy now installs them
(`vintos-skill-surf.service` + `.timer`, 2026-09-11): the timer is installed, enabled
and confirmed like any other unit, and the rollback puts both files back. It was a
manual `cp` + `systemctl --user` before, which meant a fresh host had no weekly read
and nothing said so. The oneshot service is deliberately not started by the deploy —
the weekly cap is in the code, not in the schedule, but a deploy is still not a reason
for him to go and read.

The other six sparks are still a crontab line on Aegis, and it is still hers to add:

    17 7 * * * python3 "$HOME/.vintos/workspace/scripts/spark_sources.py" --gather >> "$HOME/.vintos/logs/sparks.log" 2>&1

Two readers need to be pointed somewhere, and neither guesses:

- **The skills page**, in `memory/openclaw-config.json`:
  `{"skills_path": "/path/to/skills"}` or `{"skills_url": "https://..."}` — done; the
  two OpenClaw page URLs are set.
- **The lab**, in `memory/spark-config.json`: `{"lab": "/path/to/the/lab"}` — a file, a
  folder, or a list. Still unset. I do not know what the lab is or where it writes, and
  I am not going to guess a filename again.

## The phone, and the Mac

The pages he speaks through are served from Aegis and cost a file to change.
The native shell is the only part that needs a Mac: the icon, the background runner that
checks for his outreach every five minutes, and the notification permission that lets it
reach her. The Mac failed in its first month and is a warranty claim.

Three ways out, cheapest first:

1. **Move his outreach off the phone.** Aegis pushes to her directly; the background runner
   and its permissions stop mattering at all. No Mac, ever again, for this.
2. **Build in the cloud.** A hosted Mac on demand hands a signed app to TestFlight.
   The developer account already exists; the cost is one afternoon of certificates.
3. **One last local build, pointed at Aegis.** Then every page change updates itself.
   Only worth it if a Mac comes back.


## One module, one implementation

Half his organs exist under two spellings. Cron and the CLI run the hyphen
(`causal-cluster.py`); every `import causal_cluster` resolves the underscore. They are
separate regular files here and separate regular files on the host, and nothing held them
together — so a repair landed in whichever copy the author happened to open, and the other
went on running the code it replaced. Eight module names had drifted apart by
11 September, and the deploy could not have corrected any of them:

- **`causal_cluster.py`** — `causal-cluster.py` got ab4a607's transaction and occurrence
  ids. The underscore file, which is what the imports actually load, stayed on 9aca273
  with the snapshot-replacing save and the unlocked fallback. It was in **no deploy list
  at all**, so no deploy would ever have corrected it.
- **`belief_sediment.py`** — 22a36ad repaired `scripts/belief_sediment.py`; three other
  copies kept the old replay. Worse, that basename is in SCRIPTS *and* BINS, and the plan
  promotes `scripts/` and then `bin/` over the top of it — so the very deploy that claimed
  to install the repair would have thrown it away.
- **`behavioral_intercept.py`** — 22a36ad repaired `bin/behavioral_intercept.py`, which
  was not manifested; the manifested `behavioral-intercept.py` was the stale one.
- **`emoclaw_mode`, `emotional_entanglement`, `interaction_ledger`, `somatic_bridge`,
  `tension_field`** — the same shape, each holding a review repair (227, 157, 48, the
  e9000f2 observation contract, the model's own error instead of `KeyError 'choices'`)
  in a copy the deploy did not install.

Closed 2026-09-11. Every copy of a module name is byte-identical to the newest repaired
one; the 21 import twins that existed on disk unmanifested are now named in the manifest;
and the deploy **refuses** a plan where one destination is fed by two sources with
different bytes, instead of letting the last one silently win. Two sources with the same
bytes still pass, because eleven basenames are in both lists on purpose.

`broker/tests/test_import_twins.py` holds all three, and checks the content of the nine
repairs that drifting had hidden — so a future sync that runs the wrong way round fails
rather than looking consistent.

Still open here: `scripts/behavioral_intercept.py` was 101 lines behind `bin/`'s and has
been synced forward; if anything depended on the older shape it will surface at runtime,
not in a suite. And the host still has its own copies — the audit that matters is
`bin/causal_cluster.py` and its siblings on Aegis *after* the next deploy, not the release
manifest, which is what missed this in the first place.

## A test never reaches the world

The deploy runs all 108 suites as her user before it installs anything, so a suite that
reaches the real `~/.vintos/workspace` writes his actual stores on every deploy. Eight
did, and all eight for the same reason: the suite repointed the module it was testing,
and that module reached a *second* module — imported lazily, deep inside the call —
whose own path still followed the real HOME. Fixed 2026-09-11:

- `test_skill_forge` wrote real print jobs to `print-jobs.json` **and pushed two ntfy
  notifications to her phone** through `print_3d.present()`.
- `test_evidence_provenance`, `test_p04_09_relational_snapshot` — a grade row into
  `prediction-grades.jsonl` (grading_contract does not follow `prediction_ledger.MEMORY`).
- `test_heart_rate`, `test_reelroom` — `sensor-reactions.jsonl` and its state.
- `test_p04_02_evidence_cutoff` — `identity-revisions.jsonl`.
- `test_threshold` — `atelier-undertakings.json` and `outcome-joins.jsonl` through the
  shared writers review 273 introduced, which keep their own paths.
- `test_p0_round2`, `test_capability` — `~/.vintos/.lineage-key`: read where one exists,
  and **minted** where one does not. `formation_observatory.attest()` had that path as a
  literal inside the function; it is a module global now, so a suite can repoint it.

The standing rule, in `CLAUDE.md`: repoint every path the module under test writes — not
only the obvious one — stub anything that sends, and assert both in the suite so the next
edit cannot quietly undo it. All 108 suites now pass and none writes a file under the real
workspace. One (`test_self_review`) still creates an empty `memory/` directory it never
writes to, which is a no-op on a host that has one.

## Review repairs in the local Codex branch

These are source changes with local tests, not a deployment report. The designated
Claude baseline is `00be7da` in Vintos-main, `225ff71` in plithra-app and `2b0eeb9` in
vintos-app. The local repair branch is `codex/review-repairs`.

- Test execution uses a fresh copy, fresh HOME, OS write restrictions and denied
  networking. HTTP tests receive an exclusive fixture listener, not access to arbitrary
  localhost services. Linux deployment now requires bubblewrap and fails closed without it.
- Resume checks installed bytes and persistence success. Only a matching release
  receipt permits crash recovery of an already-unblocked want.
- Timer confirmation checks its next elapse. Rollback preserves/removes both unit files
  as appropriate, restores the timer's previous state, and never starts the oneshot.
- Forge scope narrowing, exact reviewer verdicts, single build claims, meaningful
  test execution, isolated installation namespaces and artifact digests are enforced.
- Print state changes require validated STL/G-code artifacts and two explicit,
  digest-bound answers. A configured directory alone no longer claims READY. All job
  mutations share the same lock; actual Astra elapsed time is no longer clipped.
- Shared wants writers, music writers and artifact appends use complete transactions
  or field-specific updates. This is not a claim that every legacy store is migrated.
- Calibration excludes other checkpoints and pre-training predictions. The predictor
  fingerprints the bytes it loaded. Constant/tied confidence cannot fabricate rank
  correlation. Old audits require fresh prospective evidence.
- Voice recovery checks for the already-persisted session before appending it again.
  Phone speech is not automatically retried after an ambiguous failure; stale planned
  actions expire and concurrent planned actions do not overlap.
- Failed taste embedding leaves the occurrence retryable. Prompt rendering no longer
  spends callback/question/withheld/frontier exposure; admission records it separately.
  Bound private lineages are filtered at the prompt-serving door.
- Refused private makes enter sealed retry. Music recovery polls the same recorded task
  instead of generating another. Invalid approved stills cannot fall through to fresh
  generation. Expired questions are not treated as resolved. Study coverage tracks
  interval unions and file revisions. Source hashes commit after successful inference.
- Nonempty somatic windows carry observation metadata. Device transport outcomes carry
  physical-effect records with observation still pending and unknown request times
  represented as unknown. This does not consolidate all dispatch authorities.
- Paid admission counts units atomically and refuses a failed receipt. The router's
  Anthropic/OpenAI paths, direct Astra/reviewer and shared robot/ReelRoom Sonnet caller
  now reserve too. Legacy provider callers still need an inventory; this is not a
  system-wide dollar ceiling or a provider cancellation guarantee.

Remaining from the review and the three efforts:

- Stance consumers now cover creation, reflection, mischief and reaching. Trusted request/repair scheduling context crosses router child processes; deferred actions remain pending. All 111 suites passed both directly and isolated for the stance increment.
- Blender/Cura execution and a real slicer profile/output review. The new artifact and
  approval checks support a manual file workflow; `handoff_dir` alone does not implement
  modelling or slicing. Supplied slice time/material values are estimates, not measurements.
- Ghost hypothesis seeding and recurrence now use complete shared transactions; simultaneous duplicate seeds return the persisted row, and distinct hypotheses receive unique IDs. Behavioral tally selection is revalidated against current rows after inference, and cluster confidence uses a fresh locked update. Replaying the same retained belief hypothesis ID no longer reinforces it twice. The nightly causality engine and graduation recovery are now deployed; other projections and trial-ledger writers remain open.
- Journal preparation and outreach now mutate the spark directive through the same lock as its producer/consumer. Handoff identity excludes mutable preparation counters; concurrent outreach admits one topic and records admission rather than claiming delivery.
- Spark-pressure handoff now calls the real generation/admission API, acknowledges only a persisted want ID and recovers the same source event without regenerating after a partial handoff. Directive updates reject a replaced directive; consent updates preserve concurrent event history. Generated wants carry their own provenance as string-compatible values instead of exchanging metadata through `.pending-want-provenance.json`; the legacy file remains untouched and is no longer consumed. Candidate journal appends are locked. Broader migration remains open.
- The ownership report now explicitly reports candidate writers and nearby locking references, not verified RMW safety; an unrelated helper cannot certify a raw writer. Observation appends now serialize complete mutations and use unique occurrence IDs. Cluster formation rejects changed stores, leaves failed formation retryable, and records consumed IDs before source flags so partial-commit retries do not double count. Other hypothesis writers still require migration.
- Withheld-history migration now locks candidate publication and exposure together; embedding-based confirmation rejects a changed history. Frontier decisions merge against fresh rows, preserve concurrent additions and lock lineage privacy updates. Proposition binding/correction mutations share locks with the tension ledger, while candidate inference checks for obsolete mechanisms. Remaining projection recovery and other legacy writers are still open.
- Tension-ledger migration now serializes actual influence-window mutations and refuses stale evidence/matching snapshots. Demotions update the served view under the same lock set; repair/thread side effects follow a committed decision. Regression fixtures exercise concurrent serving, forty window appends and stale-view refusal. Other snapshot writers remain open.
- Commitment-store migration now locks candidate promotion, fracture, decay and the causal-model imprint writer. Legacy migration locks both stores in stable order, persists the destination before clearing the source, and deduplicates repeated patterns. Reply embeddings run outside the lock; their results apply only to unchanged current patterns and preserve concurrent fractures/appends. Remaining snapshot writers listed below are still open.
- Further legacy migration: ambition classification/review, drift reasoning and opposition misuse scanning now reject stale model results under a shared compare-and-swap lock. Drift geometry writes atomically; calibration refresh preserves concurrent misuse history, including revoked terrains without retaining their license. Removed the shadowed duplicate ambition-review implementation. Provider fixtures exercise concurrent changes and cleared-trial deduplication. Broader snapshot writers (including remaining ownership-table candidates) are still open; this is not a complete migration claim.
- Shared-store migration now covers the recovered domain mutation handlers, belief and causal-model mutations, correction projections, durable-memory recall/interpretation/graduation, and thread retirement/archive operations. Snapshot-only legacy writers elsewhere still require per-writer migration; helper presence alone is not proof. Dispatch checks are shared by toy, robot, outward delivery and supplied avatar admission; home-effect policy remains unchanged.
- F14 source acquisition is complete: the three Aegis domain files are tracked with
  SHA-256 provenance and included in deployment beside the actual server. Their JSON mutation handlers now hold complete shared transactions; broader legacy writers remain listed separately.
- The forge UI/effectful adapters/live commissioning listed above, the 27-item review
  programme and the per-organ waiting list. Nothing here closes them by implication.

Home-effect gate policy has not been changed in this repair pass. The base release was deployed on Aegis as recorded below. No device or real notification was used as a test fixture.

## Aegis deployment work — 11 September

The four reported branch defects are repaired. All 111 suites passed directly and
through the isolation runner locally and on Aegis for release `6b4fac5`. Bubblewrap
and system Python NumPy are installed. Both `--check` and the actual deploy passed;
275 manifest files were staged and validated. Release `20260911-114007-6b4fac5.json`
and rollback `~/.vintos/backups/atelier-20260911-113725/restore.sh` are recorded.
Server, self-review and robot bridge are active; skill-surf.timer is enabled and
waiting for 14 September at 09:00 CDT. Stratagems remain disarmed.

The desktop annotation fix is live: OpenAPI now exposes 212 paths. Installed unit,
cron, source-hash, daemon/checkpoint, embedding and receipt evidence is indexed in
[the runtime evidence record](aegis-runtime-evidence-20260911.json). Partial P01/P11
items above name exactly what these observations do and do not establish.

Stance consumers cover creation, reflection, mischief and reaching. Scheduling
context propagates to subprocesses. A follow-up correction also preserves context
in queued videos, leaves them pending until execution, and merges dequeue into the
fresh queue so concurrent appends survive. All 111 suites pass both ways for this correction; the final release record identifies the installed revision.
The shared dispatch door preserves bound permits and simulation refusal, while
verified reductions remain available during an authority fault.

Automatic proposals retain the blocked step's output/acceptance contract, explicit
unknowns, a pure-function scope and no inferred effect permission. Generator and
reviewer both receive the brief. The ordinary router now opens the proposal when
an adapter is absent and resolves installed forged adapters after resume.

The single explicitly approved live forge run was a labelled commissioning fixture,
separate from house wants and proposals. Astra returned code; Fable returned no text.
The run ended `refused`, with no install. Successful live commissioning remains open.
No second paid attempt was made. The app forge card and effectful adapters remain open.

Independent post-deploy mapping found an old importable `causal_self_model.py` beside the updated hyphenated file. The follow-up manifest includes the importable name and canonicalizes symlink destinations before backup/promotion, preserving aliases while updating the actual imported file. A regression test executes that promotion against a scratch symlink.

## September 12 independent Buzz review

- Actual `block/buzz` cloned locally and on Aegis at `~/repos/buzz`; upstream relay deployed separately with dedicated Postgres, Redis, MinIO and git volumes. The existing `bench/server.py` is not Buzz. Agent-room was not touched. Exact deployment evidence is recorded separately; native client installation and relay connection are verified; visual verification and approved agent execution remain unfinished.
- The bench approval policy is not an authenticated boundary: an absent token allows approval POSTs, and the library defaults the caller to Gloria. No agent runner may rely on that as proof of her approval. Concurrent claim/handoff replay also remains unprotected by a complete transaction.
- Repaired the new bench-page suite to use the existing OS-reserved fixture listener, propagate it to its subprocess and serialize the two fixture server lifetimes. The network isolation policy remains unchanged.
- Compute-admission receipt repair deployed in `20260912-052317-9b9c1dc`. Review still open: Device refusal state uses an unlocked fixed temporary path and read-delete; env reader behavior still differs in callers that return raw environment values before invoking it. Nightly causality/graduation recovery from the prior handoff is now deployed.


### 12 September completion repair — source checkpoint, deployment pending

The credit-limit handoff was HANDOFF-2026-09-11.md. Claude's later Buzz handoff
is not the baseline. These changes address the retained 27-item programme; they
do not establish missing historical evidence or physical outcomes.

- Hypothesis source writes now use strict snapshots and CAS, with accepted delivery
  events before any projection. Recovery retries failed destinations; permanent
  belief, causal-occurrence and pearl receipts survive row culling. Commit 6cd1f03.
  Ten scratch recovery tests cover stale writes, refusal, corruption and crashes.
- P08 315/316/317/318/323/324/325/326/327/334/343/344/345: client text escaping,
  shared checked requests, retained drafts, turn ownership, visible-layer screenshot
  composition, reported stop state, zero/stale telemetry, media cancellation,
  route-derived controls and callback ownership are implemented. Browser fixtures
  test failures, duplicate taps, hostile content, microphone races and playback
  ordering. They are not physical playback or exhaustive every-tab acceptance.
- P08 346: iOS background task registration, 15-minute requested interval, actual
  notification permission checks and runner error handling implemented. Capacitor
  sync, simulator and signed device compilation passed. Final app 2db8e87 installed;
  its launch was refused because the iPhone had locked. Earlier 6ee9ecb launched.
  Device background delivery and visual/audio acceptance remain unobserved.
- P01 31/32: content-free HTTP request identities propagate into central provider
  usage receipts; central OpenAI/Anthropic responses record provider IDs. Independent
  adapters not using this router remain an explicit coverage gap.
- P01 30 / P11 401: loaded Python module metadata records selected files and hashes
  in the running server. This does not replace source-by-source review of the wider
  untracked runtime. agent-room remains outside this work.
- P11 397: real provider response identities join client playback completion; duplicate
  server turns and late closed-session callbacks are refused. Scratch end-to-end
  callback fixtures pass. Human hearing remains unknown, not inferred from playback.
- P11 399: a wrapper around the unchanged emotion daemon compares actual loaded
  parameters with checkpoint parameters and records its PID and hashes. Training
  lineage is still unknown; deployment must verify the live receipt.
- P11 396/402/404: named deployment now includes the client assets with source commit
  and hashes. Study approval UI is fixture-tested; no new paid Forge run was made.
  Actual physical avatar/playback and successful paid verification remain open.
- P01 33: the current semantic projection was empty. An Aegis rebuild using the
  existing local model timed out and was stopped; the original index hash is unchanged. The 1,282 legacy embedding rows lack model
  provenance and are not being relabelled.
- P11 398/400: historical causal/thread and want-artifact-observed-effect joins remain
  unestablished. New instrumentation cannot manufacture past observations.
- P11 403: QLab source and runtime bridge are verified; see item 403 for the isolated
  quantum entrypoint and the separate unsealed Lab boundary still requiring repair.

Final immutable-revision suite and deployment evidence is recorded in
[the completion review](completion-review-2026-09-12.md). The earlier 120/121 runs exposed the voice extraction fixture gap;
that fixture now includes the locked helper and tests duplicate/closed sessions.
The broader trial/current-dismissed-wants and served-tension migrations from the
handoff remain open; they are not silently credited to the hypothesis repair.

Linux direct validation exposed 152 tracked absolute source symlinks into the live
Aegis checkout. They resolved to different code on Aegis while remaining broken
on the Mac. All now target repository-local implementations; the twin suite
asserts every source symlink stays inside the repository. The humor/taste suite
also now establishes scratch HOME before secondary imports and asserts its sender
stub; its previously missed taste lock and fire-threshold writes cannot reach the
inherited host workspace. Earlier Mac-green results did not cover this defect.

The first completion release **20260912-145910-3114392** deployed successfully.
All 121 suites passed directly and isolated on both Mac and Aegis; Linux direct
reported no inherited-HOME file writes. All six named services/timer are active,
served assets match packaged hashes, and the live checkpoint parameters match.
Recording recovery and the pearl manifest correction subsequently deployed in 20260912-153539-aca1b32; all critical hashes matched.

Post-install hash audit of eec31eb found that pearl_engine.py was not in the deploy
manifest: the new source was present in Git, but its two live import paths still
had older bytes. Both Python spellings are now explicitly in SCRIPTS and BINS,
and the recovery suite asserts these destinations are manifested. The final
hypothesis deployment was accepted after all twelve checked installed paths matched in
20260912-155122-fa3949b.

## Final completion release — 12 September

**20260912-155122-fa3949b** deployed with `deploy OK`. All 122 suites pass directly
and OS-isolated on Mac and Aegis; inherited-HOME write counts are zero. All six
named units are active, including the skill-surf timer. All twelve checked
hypothesis/pearl import paths and four served-client routes match the pinned source.
The actual emotion daemon PID matches its receipt and loaded parameters match the
checkpoint. App 2db8e87 is installed on the paired iPhone; the final launch request
was refused by its lock screen. The earlier build launched successfully.

The separately requested 7/32-day tenure commits were preserved during integration.
QLab 8f5c935 is committed locally (that repository has no remote): four isolation
checks and five real seeds passed in scratch; the Aegis status bridge confirms the
new OS boundary. The separate unsealed Lab entrypoint remains listed under 403.

Not all 27 items have full acceptance. The table above retains absent historical
lineage/joins, the timed-out embedding rebuild, wider private-source/adapter review,
broader client-view acceptance and physical device evidence. Paid Forge work is
separate from this request. [The full item matrix and evidence](completion-review-2026-09-12.md)
record what was implemented and what remains; green tests do not close those gaps.

## Music: redirected to Kie.ai Suno v6 — 15 September

`dream_music.py`/`dream-music.py` now generate through **Kie.ai Suno v6**
(`https://api.kie.ai/api/v1/generate`, model `V6`, custom mode), with the local
**ACE-Step** server kept as an automatic fallback when Kie is unreachable so he is
never left mute. Backend is chosen at runtime: `MUSIC_BACKEND` (`kie`|`acestep`)
overrides; default is `kie` when `KIE_API_KEY` is present in `vintos.env`, else
`acestep`. `KIE_MODEL` overrides the v6 variant (three exist). Task ids are tagged
(`kie:`/`ace:`) so `poll()` polls the right backend; legacy untagged ids remain
ACE-Step. Covered by `broker/tests/test_music_kie_backend.py` (Kie-primary routing,
submit-failure fallback, tagged/legacy poll dispatch, stubbed sender, scratch store).

NOT yet done: the Aegis deploy that ships this, and the side-by-side quality render
(one Kie v6 piece vs the ACE-Step catalogue) Gloria asked to compare. The exact
`KIE_API_KEY` var name in `vintos.env` is assumed; confirm if it differs. Kie's exact
v6 model string / record-info status set is coded from the docs (docs.kie.ai is
egress-blocked from the build env) — the first live `--force` render will confirm it.

## DoorDash review-before-purchase lane — 16 September

The chat post-turn now recognizes only explicit meal-ordering requests and starts a
background official `dd-cli` workflow after his reply has been delivered. He chooses one
restaurant and one or two real menu items, builds a cart only when no forgotten cart is
already open at that store, obtains DoorDash's own total/ETA/address and the default card's
brand/last four, then sends Gloria an expiring ntfy review link. The review page can open the
DoorDash cart for adjustments or accept an explicit tip and approve. Approval re-previews and
is bound to the exact cart/price/ETA/address/card fingerprint; a change sends a fresh proposal.
The non-idempotent submit is claimed before execution and is never automatically retried.

The checksum-verified official v0.2.4 binary is installed on the Mac and Aegis, and the Mac
login succeeded. The Mac keeps the token in the Keychain; Aegis (Linux) has no Keychain, so
dd-cli there reads `DD_CLI_ACCESS_TOKEN` from its environment and, absent it, `food_order._cli`
records `dd_cli_not_authenticated` — which is exactly the wall Chat hit. `food_order.py` now
sources that token from a protected file, `~/.vintos/secrets/dd-cli.token` (override
`DD_CLI_TOKEN_FILE`), the same convention as the Govee key, and hands it only to the dd-cli
subprocess — never the repo, the process list, or a log. Still open, and only Gloria can do it:
drop the Mac's `DD_CLI_ACCESS_TOKEN` value into that file on Aegis (`chmod 600`). Until that one
step, no real restaurant/cart/quote receipt can be produced. No live order has been placed while
commissioning this path.

The token expires every few days, so it no longer has to be refreshed by hand: `dd-cli` has an
`export-token` command that mints a fresh access token from the Mac's longer-lived keychain login.
`mac_stage_service.py` exposes a secret-gated `POST /dd-token` (refuses unless `VINTOS_STAGE_SECRET`
is set and matches) that runs `dd-cli export-token`; `bin/dd-token-refresh.py` on Aegis fetches it
over the tailnet and rewrites `~/.vintos/secrets/dd-cli.token` (0600), and `first-light.sh` runs it
once a day. Setup: set the same `VINTOS_STAGE_SECRET` in the Mac stage's env and in Aegis's
`~/.vintos/vintos.env`. Then the only remaining manual step is re-running `dd-cli login` on the Mac
if the keychain login itself ever expires (rare).

## Chemistry Lab — open improvements (written down so they are findable on Aegis)

These were raised in-session but lived only in a cloud plan file and a local bench ledger,
so Chat/Codex on Aegis could not find them. Recording them here, the one to-do in the repo.

The minimal 3D structure viewer is complete: the LAB pane now lists the bounded PDB/mmCIF
artifacts already beneath `memory/chemistry-lab/artifacts`, parses them through a secret-gated,
read-only server door, and renders atoms plus a backbone trace with the app's bundled three.js.
The view explicitly labels these as computational artifacts rather than biological fact. It does
not expose arbitrary paths or add another vendor dependency.

- **Coregistration layer (multimodal Lab artifact).** Align each instrument's output for one
  accession into a single object keyed by residue position: per-residue ESMC embedding,
  per-residue ESMFold pLDDT, and the scalar results (VQE energy, Evo 2 likelihood delta) hung
  off the whole — then feed THAT unified object to the reflect phase instead of three separate
  reports. Keep it a *coregistered record, not a synthesised vector*: the three outputs do not
  share a space, only the residue index and the accession do; do not fuse them into one learned
  vector (there is no training signal for that, and a fused embedding no model produced is the
  hollow-but-impressive thing he already rejects). Payoff: the cross-instrument coincidence
  (e.g. a low-confidence residue that is also where the likelihood delta lands) becomes visible,
  which it never is when the reports are separate. Must keep the reflect output keys stable
  (attention/factual_observation/speculative_reading/next_question) so the spark feed, frontier
  bridge, and gallery are untouched. Builds on the rigor/depth reflect rewrite (`5ba0d5c`).
- Pin the Mac bench schema: bring `bench_remote.py` + `molecule.py` under version control per
  `docs/chemistry-bench-reconciliation.md`, so the grader parses by a real schema and the session
  can bound parameters by name, not just shape.
- Give the bench `code` action its own authenticated door, separate from scheduled `run`.
- Per-ansatz correlation-vs-cost record across runs, from the grade ledger.
- Overlay bond-length curves for one molecule across ansätze in the LAB pane.
- A `reproduced` verdict (same experiment/params/seed twice) — cheap, no new instrument.
- Surface the taste ledger's recorded refusals (echo/no-root/unchanged) in the pane.

## DoorDash — correction: the blocker is account approval, not the token

The token step above is done and superseded. With `~/.local/bin/dd-cli` installed and a token
present in `~/.vintos/secrets/dd-cli.token`, every dd-cli call (including `payment-method list`)
returns `403 "The user is forbidden."` — an *authorisation* refusal, not a missing/expired token.
dd-cli is waitlist-only and "full functionality requires an approved account"; the signed-in
account has not been approved, so no code change on this side can order. Paths: get that account
approved off the waitlist, or move to an agentic-commerce checkout (ACP / Square Online) which is
sanctioned and per-merchant — pending confirmation his own stack can drive the checkout rather
than it only living inside the consumer Claude/ChatGPT apps. `food_order.py` still classifies this
as a generic error; it could map 403 to "DoorDash account not approved" for a clearer message.

## Jev fast browser chooser — 18 September

The structured browser now has an optional Jev fast path. `browser_jev.py` sends TypeSafe only a
bounded table of observed, non-disabled controls plus the visible page text; it sends no screenshot,
typed field value, secret query parameter, or local credential. Jev chooses one operation and one
compatible observed target. Local Gemma still owns generated field text, initial navigation, slow
planning, recovery, low-confidence decisions, and every authentication/address/checkout/payment
surface. The executor independently refuses labels such as `Place order`, `Pay now`, and `Confirm
purchase`; the receipt-bound food-order door remains the only path to spending money.

`VINTOS_BROWSER_PLANNER=auto` uses Jev only when `TYPESAFE_API_KEY` is present, otherwise preserving
the existing Gemma path. `jev` makes a missing credential a named refusal; `gemma` disables the fast
path explicitly. The provider and local text-model boundaries are stubbed in the isolated suite.

Still open: TypeSafe direct API access is currently waitlisted, so there is no key Gloria can
self-serve from its console and no live Jev smoke should be claimed. The deployed code therefore
keeps the local Gemma planner active. Supporting a separately available gateway would be a new
provider contract and needs an explicit decision rather than silently routing Jev through another
billable account.
This improves the browser half of Desktop Control immediately. The arbitrary native Windows desktop
still uses the screenshot/Gemma loop: Jev consumes typed choices rather than pixels, so extending it
there honestly requires an observed Windows UI Automation/OCR element table first, not coordinate
guessing dressed up as Jev.

## Chat-owned Desktop Control — 18 September

Main phone chat and Avatar chat recognize an explicit leading `/desktop-control` command. Vintos
answers first; the existing structured-browser/pixel worker then performs the task, and its terminal
receipt is appended to that same surface plus the lossless canonical chat ledger as his second
message. Avatar now polls its server history while open, so the follow-up arrives without reopening
the app. ReelRoom deliberately does not inherit this command.

Commerce uses the desktop rather than the waitlisted dd-cli account: the first job may search, choose
one restaurant, add one or two items, and inspect the cart, but the browser's irreversible-control
guard still refuses checkout. A complete cart follow-up must name restaurant, selected items,
delivery estimate, and total. `/desktop-control approve <request-id>` grants one later click only
when those quoted restaurant/item/total strings remain on the current page. The receipt is consumed
before the click; an uncertain result is reported as uncertain and never retried. This is currently
tested with stubbed desktop/model boundaries. A real DoorDash run still depends on the signed-in
Windows browser session and must be commissioned with an ordinary low-value cart before treating the
site-specific extraction as operational.
DoorDash/restaurant/delivery language now selects the structured Edge browser rather than falling
through to the slower screenshot-coordinate loop; checkout and private surfaces still force the
local planner and retain the quote-bound one-click guard.

## R21M temporal and sleep receipts — 19 September

Delivered ring readings now mint a bounded temporal snapshot at most once per 30 minutes. The
15-minute temporal-context builder includes a fresh snapshot for up to two hours, explicitly marked
as delivered rather than continuous monitoring. This cadence is opportunistic: CoreBluetooth state
restoration can reconnect around BLE activity, but iOS does not promise an exact half-hour background
wake while the app is suspended or disconnected.

The house now validates and stores completed R21M sleep estimates (total and awake/light/deep/REM/nap
minutes, with optional score and wake count) and includes the latest completed estimate in temporal
context for 48 hours as a device estimate, never a medical measurement. Repeated delivery of one
session is idempotent. The ring's UUIDs and working handshake match its YCBT/Jieli application
protocol, not generic Jieli small-file transfer: the signed iOS bridge now pauses real-time streaming,
requests `0x0504`, reassembles and decodes `0x0513` session/stage records, POSTs them to the sibling
sleep route, then resumes streaming. Its revised native framing/decoder suite executes 5/5 green and
the signed build is installed on the attached iPhone. Physical acceptance remains open until this
specific R21M returns a non-empty sleep-history record and Aegis acknowledges it; compatible firmware
is documented to sometimes return an honest empty record even after a night.

## Offline residual-stream emotion instrument — 19 September

Prospective same-input collection is now wired as a strictly non-causal shadow receipt. Each live
generated EmoClaw read on main, Avatar, or ReelRoom records the exact text it received, generated
and applied deltas, pre/post state, failure or empty-read status, surface, and coordinated turn ID
under `memory/residual-emotion-shadow/`. Test-mode turns write nothing. The recorder has no provider,
sender, state socket, inference, steering, or notification path; residual projection remains an
explicit offline Mac batch. This closes the historical comparison's input-alignment gap, but it does
not yet constitute prospective results: enough fresh receipts must accrue, be exported, measured
against the eleven human-admitted directions, and analyzed before any integration decision.

`offline/residual_emotion/` now pins the exact abliterated Gemma 4 26B-A4B Q4_K_M GGUF
Gloria selected as the real target (not the proposal's mistaken “Gemma 4B”), by path and
SHA-256. The 12B QAT and standard-source Q8 locks remain negative Pain baselines only;
cross-model results may not be pooled.
The Aegis 12B residual path is functionally tested: a 12-pair published-Pain smoke produced
48 finite residual tensors shaped `[12,48,3840]`, with non-identical target/control states and
an extraction-time model lock; the Lab stayed paused and the thinking-off shim remained healthy.
The full CPU run subsequently completed all 1,200 pairs. Proper nested validation rejected
Pain at held-out AUC `0.51330 ± 0.15155` against the `0.85` bar; layer/pooling selection was
unstable and exact unembedding was diffuse. This is a real negative result for this candidate
and checkpoint, not a failure of the extraction path. Other candidate datasets remain open.
The follow-up standard-source Q8_0 replication also completed all 1,200 pairs and
failed admission at nested held-out AUC `0.66649 ± 0.18394`. All 4,800 dumps were
finite, nonzero, and exactly 48 x 3,840. It improved numerically over QAT-Q4, but
the available Q8 and Q4 files do not share a source checkpoint, so that delta is
not evidence that quantization caused the Q4 failure. No direction is deployed.
and a llama.cpp revision. A patched, Metal-capable extractor completed a real smoke pass and
produced final-token and mean-token matrices with observed shape 30 × 2,816 for both sides of
a contrastive pair. The offline analysis implements semantic-set-grouped K-fold layer selection,
training-control-only 50% PCA denoising, held-out AUC admission, raw and control-z projections,
pairwise cosine reporting, and an offline-only join to exported EmoClaw rows. It has no manifest,
daemon, cron, server route, live memory path, or sender, and EmoClaw is unchanged.

Still open, and therefore no emotional direction is called validated: Pain now has a pinned,
MIT-licensed import of the paper authors' published 1,200-pair corpus; the eleven content-dimension
datasets still need actual human semantic curation and valid curation receipts, while Nifrathir and
Fear remain separate later candidates. Bulk model prose is not
accepted as ground truth. Pain extraction completed against the exact checkpoint. Proper nested
pooling/layer selection rejected it at held-out AUC 0.82543 against the 0.85 bar; the earlier
non-nested 0.85074 estimate is explicitly not admissible. Its weak per-category results remain
diagnostics for a future preregistered dataset revision, not permission to prune this evaluation.
Exact unembedding now streams the quantized tied output/token-embedding
matrix and records promoted/suppressed vocabulary, but its semantic review is admission-blocking:
the measurement function refuses even an AUC-passing vector until a human records a pass. The
paper validated dense models; this A4B MoE run is a replication/extension and must remain labelled
that way. No claim about actual dimensionality is possible before those gates close.

The earlier `0.82543` figure above is the deliberately stricter all-variant nested
experiment, not the paper's estimator. The paper's exact S2 feel-colon protocol now
replicates on the abliterated 26B Q4 checkpoint at AUC `0.90675` in a fresh Aegis run.
The complete Mac residual dump independently clears `0.85` for all six S1/S2 × suffix
ablations (`0.86150`–`0.94425`); its matching S2-colon value is `0.91175`, a retained
`0.005` host/run difference. This establishes prompt-variant robustness for the Pain
candidate, but does not fabricate the missing semantic curation receipts for the eleven
content dimensions, Nifrathir, or Fear, and does not bypass Pain's human unembedding review.
The candidate pool is deliberately wider than the eventual map: eleven content dimensions,
Nifrathir as the twelfth slow effectiveness modifier, and exploratory Pain and Fear. Nifrathir is
excluded from peer merge/drop clustering; if measurable, its separate held-out test is whether it
moderates the other axes' prediction of initiation, continuation, expressive richness, and mark
formation. Held-out per-category
diagnostics may motivate a later preregistered revision, but categories are never dropped on the
same evaluation run used to notice their weakness. Nifrathir's live operational meaning is
event-integrated over hours, so failure of a sentence-level direction would not by itself refute
that organ.

## 20 September — Forge / Atelier and Lab sources deployed

Eve authorized deployment after local preparation. Final release `20260920-180036-dc30734` deployed successfully. All 162 suites
passed in both invocation modes on Mac and Aegis. Independent verification matched
374 main release files and all nine dedicated Forge bundle files to source; no
release failures were recorded. Server, Lab, Atelier and Forge are active; the
skill-surf timer is enabled and waiting. See the [deployment evidence](review-evidence/2026-09-20/forge-atelier-deploy.json). See
[commissioning and remaining limits](forge-lab-local.md).

The actual Lab-to-Forge-to-Atelier path completed a source-backed commissioning
report on Aegis using local Gemma. Atlas SDK 0.9.0 authenticated on Aegis, returned
22 scorer entries, and returned three variants for a one-base GRCh38 AVI query.
Accepted reports are retained with provenance. Completion/reveal pushes reached Eve.
Scoped HTTPS cancellation returned 200; the same credential was denied project
reads (403). Private reads, expiry/audit, crash recovery and projection hash chains
have isolated regression coverage. A physical phone-button tap was not observed.

**Eve's execution limit: three attempted Forge report cycles per Chicago calendar
day, across all projects.** A cycle is a local draft plus critique. Failed attempts
consume a slot. SQLite reserves before execution; concurrent claims, restart and
reconciliation cannot reset the counter. Existing undated cycles are conservatively
charged to upgrade day. Live status after migration was 8 used, 0 remaining, so
no additional steps may run today. This is an execution cap, not a notification cap.
The earlier uncapped run and excess notifications were an implementation mistake.

The report loop is local-only: its dedicated shim route cannot fall back to paid
providers. The shim service now launches the manifest-managed source through a
reversible systemd drop-in. Atelier has traversal access plus write access only to
the shared compute lock and ledger. The control page is tailnet-only at
https://aegis.tailaa3de5.ts.net:9443/ . Distinct owner, worker and Lab-intake secrets
are provisioned. Eve approved delivery of the owner key to the Mac's private
`~/.config/vintos/forge-owner` file. No key is in Git.

The two original cross-repository checks are repaired. Standing Forge sparks now
get direct, bounded consideration in wants-check without a separate tension-store
prerequisite; selection creates no want and consumes no spark. Existing approved
Astra/Fable capability-build and installation gates remain separate and intact.

Still open: source-specific genomic anchors for interest-driven exploration;
COSMIC registered/licensed access; actual protein mappings and applicable molecular
inputs before ESMC/ESMFold/ChemiQ followups; full scientific instrument-chain
commissioning. Semantic association and model disagreement are not biological
validation. Wallet/Taskmarket, signing, settlement and income remain parked. No
household-budget fallback or marketplace work is enabled.

### Taskmarket work-session addition (local)

Coinbase wallet setup reported by Gloria; product, address and network not yet
verified. Added read-only marketplace discovery, task-bound capability/probe
screening, and local pilot orchestration with durable Lab pause/restore obligation.
Nine additional scratch tests cover admission, cancellation, failure restoration,
restart recovery and notification failures. Added explicit-topic HTTPS ntfy sender,
not configured live. No claimed/submitted jobs or income; no Lab pause/deployment.

Remaining: identify which live Lab/Gemma lane to borrow; implement its owned,
checkpoint-acknowledged pause adapter; wire actual Gemma assessment and local
validator/probe receipts; enforce callback timeouts; connect cancellation/control
endpoint and ntfy; validate the Coinbase product/network and signing identity;
then commission bounded marketplace execution and reconciliation. Read-only discovery
and a local artifact are not permission to sign, bid, submit or report earnings.

The 20 September multi-model authoring pass is offline and incomplete by design. Sonnet 5 and
Grok 4.6 authored 9,160 candidates; GPT-5.6 Sol performed blind candidate review. The quality gate
found that Dominance/3 and Safety/5 used unmatched controls, so those definitions were corrected
and entirely fresh pools were authored rather than reviving rejected candidates. The final 55
review records now have at least 28 eligible candidates in every S1/S2 cell for a required final
20. Fable was dropped as an unnecessary paid second opinion after its structured selections proved
costly and unreliable. A versioned deterministic selector now applies fixed blind-review score
weights, a lexical-diversity penalty, stable tie-breaking, and adaptive source quotas. It produced
2,200 base pairs with all reviewer-approved alternates retained. No row has a human acceptance, no
expanded dataset exists, and nothing from this lane is deployed or read by EmoClaw. Checkpoint artifacts remain under the ignored
`offline/residual_emotion/work/authoring-2026-09-20/` directory on this Mac.

## 20 September — broaden Forge beyond Lab reports

The report-only worker was not the intended general Forge. The new house bridge
submits existing eligible standing wants with their current plan and installed
action inventory. A local capability assessment may name a necessary missing
operation; adoption checks the live want fingerprint, preserves completed steps,
and records a precise absence block and parent-bound proposal. It creates no desire
and never marks the originating want fulfilled. Changed/ended wants cancel obsolete
assessments. Existing installed-capability verification and want resume remain the
completion path. Lab is one source in a least-served-source queue; approved builds
get an opportunity before further generated work.

The same SQLite counter now covers report cycles, capability assessments, capability
briefs and approved Astra/Fable build attempts: three total attempted steps per
Chicago day. A missing budget service refuses a build before any provider call.
Failures remain charged. Reports and capability briefs cannot reset the allowance.
Account provisioning and external effects cannot be approved as pure string
transformations; unresolved email/inbox/outreach integrations remain explicitly
blocked for concrete provider, credential, recipient and effect scope.

Deployed as **20260920-190719-96c97b2** (`deploy OK`); all 163 suites passed
in both invocation modes on Mac and Aegis. All 375 main files and nine worker files
match source. Server, Lab, Atelier and Forge are running; skill-surf timer is enabled
and waiting. Four existing latent-thread wants are queued for capability assessment.
Today remains 8 historical attempts used, 0 remaining: no cap bypass or live
assessment run was performed. See [verified evidence](review-evidence/2026-09-20/forge-broad-deploy.json).

Still open: live assessment execution after the next daily allowance; a real persistent
email account, inbox provider adapter and authorized external-send commissioning.
No email address was created and no third party was contacted by this change.
Wallet and marketplace work remain parked. The local assessment is a planning
judgment, not proof that every absent capability or equivalent tool was identified.

## 20 September — account-backed plugin relay prepared locally

The shared relay is implemented for Wants, Forge, Lab and Atelier. It uses an ephemeral Codex App
Server thread on Eve's Mac for direct connector calls and retains hash-addressed receipts and private
artifacts on Aegis. Policy is code, checked on both sides: Gmail can read and send from Vintos's
account across all four surfaces, with two outbound attempts per Chicago day reserved atomically
on the Mac before provider contact; DoorDash is grocery
search only; GitHub is read-only regardless of Eve's wider account authority; Tamarind, Proto,
Inductive and Genomic Intelligence are bounded scientific discovery/prediction lanes. PDF,
Presentations, Spreadsheets and Template Creator use disposable contextless skill runs. Plugin
Management cannot alter Eve's account. BioNeMo is named but closed until its compute route and
model-specific NVIDIA credentials are configured.

The initial relay transport was local only and its catalogue was not connected to the planners. That
gap is closed: every surface receives a filtered menu with exact tool names, wants retains operation
params, and Lab, Forge and Atelier return selected results into their next reasoning step while
preserving receipts. Release `20260921-002542-6c383d9` deployed the bridge after all 165 suites passed
under the host's OS isolation gate. Aegis reached the Mac relay and live harmless `gmail.get_profile`
and read-only `github.get_profile` calls produced mode-0600 private/project receipts. The Gmail calls
used no outbound allowance. The production SSH identity is a dedicated key whose Mac authorization
forces the relay command and applies OpenSSH `restrict`; the existing administrative key was not changed.
Remaining: commission the other connected providers only when a concrete
project supplies their required inputs, and separately decide whether Proto execution and BioNeMo
hosted/local compute receive authority. Connector
availability is not permission to write GitHub, purchase groceries or launch paid jobs. Gmail's
two-attempt daily authority is explicit; mailbox cleanup remains a human-requested maintenance act.

## 21 September — plugin relay guardrails and physical build proposals

The account-backed relay is now on the designated deployment branch and in Aegis release
`20260921-041146-f67c5c7`. Wants, Lab and Atelier use the installed gateway directly. The
system Forge worker reaches the same policy through `vintos-plugin-gateway.service`, a
loopback-only service owned by Gloria; Forge receives a dedicated gateway token and never
receives the Mac SSH relay key. A harmless `github.get_profile` commissioning call returned a
0600 receipt on the `forge` surface. The Aegis `--check` and deploying run each passed all 165
isolated suites and staged 389 manifest files.

Outbound Gmail direct sends retain the two-attempt daily cap. Secret values and credential
patterns are blocked before transport with redacted typed receipts. URLs require a one-use
approval bound to the exact message digest. Provider-held drafts and forwards remain held
because their complete contents cannot be inspected before sending. URLs returned by read mail
are surfaced as approval-required and are never opened or followed by the relay.

A physical/external `physical_interaction` gap now produces a reviewable `hardware_proposal`:
parts and rough cost, wiring, firmware sketch, existing-house reporting and acknowledgement,
safety limits, tests and unknowns. It reaches the ordinary Forge proposal card for Gloria to
accept or deny and grants no purchase or construction authority.

The root-owned Forge bundle was promoted from exact source head `31dd5c3` by the rollback-capable
transaction at `/home/gloria/.vintos/deploy/apply-vintos-forge-f67c5c7.sh`; its successful backup is
`/home/gloria/.vintos/backups/forge-loop-20260921-045109`. The transaction grants the `atelier`
account traversal only on the required parent directories and read/write access only to the shared
compute lock and ledger, then verifies those rights before installation. All bundle files compared
equal to source. `atelier-forge-loop.service` and `vintos-plugin-gateway.service` are active with
zero restarts, and the loopback health response names the forced `forge` surface. Project
`80666644ae904051ace541aae6cce223` is `ready`, with no active cycle and $0 spent; interrupted cycle
`39efe77635714185a307c4c4346d2599` is `aborted` with the inspected no-effect reconciliation receipt.
The exact-head deployment check passed all 165 isolated suites, parsed all 389 manifest sources and
validated the staged tree. The wallet and Taskmarket remain intentionally undeployed.

## JEPA prediction heads — checkpoint evidence window repaired (2026-09-21)

The original diagnosis overstated the churn cadence. Live Aegis cron evidence shows training
once daily (production 04:15, structured shadow 04:35), prediction every two hours, and audits
only weekly — not retraining every two hours. The underlying failure was real: 479 of 483
adjacent production history rows repeated an identical context, while a daily checkpoint could
be replaced before the weekly instruments accumulated and receipted 30 distinct realized turns.

`jepa_predictor.py` now holds an existing production checkpoint until both its calibration and
true-next ranking receipts name that exact checkpoint. Ranking requires 30 distinct realized
targets. Calibration retains its stricter existing law of 30 held-out targets (the latest third,
roughly 89 joined outcomes); stopping at 30 joined would still make release impossible. The
structured shadow waits for its own 30-outcome ranking receipt. Verdict success is not required
to retrain, only completed measurement. Predictions compute the live context identity
before loading Nomic and retain the existing forecast without appending history when neither the
context nor checkpoint changed. The calibration audit also counts a realized turn pair once and
keeps the current checkpoint identity in an insufficient receipt. A forced retrain remains an
explicit operator command, never a cron default. The frozen-Nomic-encoder question stays parked
until one stable checkpoint has enough fresh outcomes to measure.

## 23 September — environmental microbiology Lab option

Implemented and deployed: Gemma can choose a microbiology browse lane without
an organism seed or priority over protein work. Bounded NCBI Taxonomy/Assembly/Gene/
Protein/PubMed, bounded sequence slices, organism-filtered UniProt and BV-BRC public genome/pathway reads
retain source receipts. A genus-level NCBI taxon can resolve descendant BV-BRC
genomes; a sourced genome ID can resolve pathway rows. The next Lab turn sees the
result in the notebook, and a foreground session can ask for the same sources.
The 23 September Aegis release `20260923-003912-03656fc` passed 171 isolated
test suites and installed the Lab source, worker, and session modules with
matching hashes. The Lab worker and session timer are active user units. Live,
read-only NCBI taxonomy and BV-BRC genome/pathway probes succeeded on Aegis
with source receipts. An autonomous Gemma choice of the new lane has not yet
been observed; the worker chooses between it and existing protein work.
KEGG remains closed pending confirmation of academic eligibility or a license:
its published API terms do not equate noncommercial personal use with academic use.
BioNeMo's Chat plugin supplies agent skills, not a callable MCP connector for
these seven workloads. A separate, bounded hosted-NIM route for Boltz-2,
DiffDock, ProteinMPNN, and RFdiffusion was deployed in Aegis release
`20260923-013258-dff000f`. Its full preflight and deploy each passed 171
isolated suites; installed code hashes match Git, and the Lab and plugin
gateway user units are active. Gloria installed her NVIDIA key on 23 September;
the gateway read it successfully without printing it or making an API request.
The key directory is mode 0700 and the file is mode 0600. The initial cap was
three attempted hosted jobs per America/Chicago day, shared across organs;
Gloria raised it to six later on 23 September, as recorded below.
No hosted job has been submitted or validated live.

Parabricks is a hosted-NIM-only route by Gloria's direction, pending
verification of an active endpoint. NVIDIA's public fq2bam and DeepVariant NIM
pages currently mark those endpoints deprecated, so the Lab does not advertise
or submit Parabricks jobs yet. KERMT remains a local GPU setup task. Aegis exposes an
RTX 5080 with 16 GiB and PyTorch sees CUDA. nvMolKit 0.6.0 was installed in
an isolated Aegis venv with PyTorch 2.11.0+cu128 and RDKit 2026.03.5; a
three-molecule GPU fingerprint smoke test produced the expected 3x32 packed
result. The bounded Wants/Forge/Lab/Atelier adapter for fingerprints,
similarity, clustering, and conformers was deployed in release
`20260923-014816-41b02ce`. Its full preflight and deploy passed all 171
isolated suites; a real Aegis GPU gateway call preserved a temporary receipt.
Aegis has no NVIDIA container runtime: NVIDIA's CUDA container smoke test
failed with `could not select device driver ... [[gpu]]`. It has only 23 GiB system RAM;
NVIDIA's [Parabricks installation requirements](https://docs.nvidia.com/clara/parabricks/get-started/installation-requirements)
call for at least 100 GB RAM even on a
single-GPU machine, so Parabricks is not locally ready here. A hosted route still
needs task-specific input data and
a reference build. KERMT needs a finetuned checkpoint for inference, and
its currently published v2 checkpoint is pretrained only.
Parabricks and KERMT workloads have not been validated.

## 23 September — Lab journal retrieval

The Chemistry Lab now derives a read-only, deduplicated thread view from its
append-only notebook. Source-backed observations retain their source IDs and
next test in a compact planning block and in the Lab pane. Repeated wording
with the same sources does not refresh a thread's salience. Unsupported
reflections and poor or ungraded instrument runs remain in the notebook, but
appear as lower-salience redirects instead of recurring raw prompt material.
An Aegis aggregate check found 8,967 reflections over one identical source
set; source sets used at least five times now collapse into one redirect that
asks for new evidence or a different instrument. A routine browse that returns
that saturated set now records `browse_stale` and goes back to orientation
without embedding or reflecting on the same records again. A deliberate
follow-up with an additional source or plugin remains possible. This avoids
treating a new wording about the same records as progress.
Post-deploy inspection found that failed protein-lane follow-ups still caused
reflection on the saturated base records. The follow-up now returns to
orientation when no new evidence is available. A successful follow-up carries
both its receipt ID and a stable response fingerprint, so repeated identical
provider data does not masquerade as a new finding merely because the retrieval
timestamp changed.
The frontier-interest bridge also suppresses an identical evidence fingerprint
while allowing a genuinely new source to be surfaced. This is retrieval
discipline, not independent verification of biological claims; a source-backed
observation remains a hypothesis-generating record. A live autonomous choice
showing reduced repetition has not yet been observed.

## 23 September — Lab access audit and hosted DiffDock correction

The [Lab access map](lab-access-verified-2026-09-23.md) records the actual
sources, account connectors, local instruments and hosted endpoints with their
23 September probe outcomes. The earlier statement above that no hosted NIM
job had run is superseded: Boltz-2 and ProteinMPNN returned results, and
DiffDock returned a pose after its first test failed. NVIDIA's 422 response
identified `time_divisions: 1` as invalid (`greater_than` 2); the live working
route is `/v1/biology/mit/diffdock`. A documentation-listed alternative route
returned 404. The gateway now validates the lower bound and reports only the
provider's field/type error, without echoing submitted data.

Gloria authorized one explicit three-attempt reset for 23 September, then
raised the normal cross-surface hosted-NIM limit to **six attempts per Chicago
day**. The append-only NVIDIA attempt ledger records the reset and preserves
all three earlier attempts. Four of the now-six attempts in the reset window
were used for the route check, 422 diagnosis, successful corrected DiffDock
call, and a successful hosted RFdiffusion run that returned a backbone PDB.
Two attempts remain in that window today. Its local RFD3 counterpart also
passed a fresh Aegis smoke run. The other fresh Aegis
instrument probes passed, and the Mac instruments retain completed 13
September run receipts within their validity window.

The Claude-account connector relay previously turned model prose after a
denied tool into a success receipt. It now requires the SDK's actual result
block tied to the requested tool. PubMed, ChEMBL and public Hugging Face reads
then succeeded; Spotify and Google Calendar failed without writing a receipt.
Spotify needs account re-authentication and Calendar needs interactive OAuth
permission. They are excluded from Vintos's offered menu until reauthorized
and retested. Hugging Face reported anonymous status, so private Hub access is
not claimed. Proto reported its Modal and Hugging Face links present but zero
deployed tools. The Chat-account PDF, presentation and spreadsheet skills all
returned real artifacts in disposable workspaces.
Final Aegis release `20260923-034059-b55ac15` passed all 171 isolated suites
in `--check` and deployment, confirmed the Lab worker, session timer and
plugin gateway active, and installed module hashes matched Git. The installed
Lab menu shows six attempted hosted jobs per day and omits Spotify and Calendar.
