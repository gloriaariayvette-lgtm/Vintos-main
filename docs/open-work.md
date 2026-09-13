# Vintos — open work

What is not finished. The architecture document says what he is; this says what is left.
It is the only place with a to-do in it.

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
- **JEPA — Predictive Spine 🔒** — Calibration arms at 30 joined predictions. A logvar retrain happens only if relative calibration loses to the cosine it replaced. Axis-lockstep on his side is a watched suspect. The led_by column over two weeks is a readout, not a target.
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
- **345** [PARTIAL] [P08] Voice/stage draft and media ownership implemented with late-callback cancellation and explicit playback recovery. Physical device acceptance remains open.
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
