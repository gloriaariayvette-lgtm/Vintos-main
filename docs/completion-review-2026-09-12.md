# Credit-limit handoff completion repair — 12 September 2026

Baseline: our `HANDOFF-2026-09-11.md`, created when the user ran out of usage.
This is separate from Buzz and the paid Forge. No new paid Forge run was made.

## Verified deployment

`deploy OK` at **20260912-155122-fa3949b**. Both the predeployment check and actual
deploy ran all 122 suites successfully. Direct execution passed 122/122 on both
Mac and Aegis; OS-isolated execution passed 122/122 on both. The direct runs
reported zero inherited-HOME file writes.

| Unit | State |
|---|---|
| vintos-server | active / running |
| vintos-emoclaw | active / running |
| vintos-self-review | active / running |
| vintos-robot-bridge | active / running |
| vintos-atelier | active / running |
| vintos-skill-surf.timer | active / waiting |

The final source package is fa3949b, app 2db8e87, Plithra a801178. The documentation
commit after this release does not change the installed runtime.

## Source changes

- Vintos `6cd1f03`: strict hypothesis snapshots and CAS; accepted delivery outbox;
  retryable graduation destinations; permanent belief, causal-occurrence and pearl
  receipts. Source acceptance precedes effects. Ten recovery/manifest tests.
- App `2650c67`, `7148e64`, `6ee9ecb`: shared checked requests, safe text rendering, draft and
  turn ownership, actual visible-stage screenshot composition, room generation
  checks, voice callback/playback identities, media cancellation, capability
  availability, native background registration and notification permissions.
- Vintos `d5a90a6`, `3364149`: package the named client assets; checked voice
  persistence and closed-session receipts; request/provider correlation; loaded
  module identities; actual checkpoint parameter attestation and unit drop-in.
- Vintos `7ba2dd8`, `3114392`: replace all 152 absolute source symlinks with
  repository-local targets; prevent humor/taste lazy imports writing into the
  inherited HOME; test alias reporting in scratch instead of requiring a defect.

The alias repair matters: ordinary Linux execution previously imported older live
files through these links, whereas the Mac saw broken links and the isolated runner
copied a different source surface. The first ordinary Linux run was 118/121 and
also exposed two scratch-HOME writes. These were fixed, not waived.

## Validation

Final source revision: `fa3949b`; app `2db8e87`; Plithra `a801178`.
The integrated source preserves the separately requested 7/32-day tenure commits
`2b7161c` and `c20428a`; those are not claimed as this review's work.

- All 122 suites directly on macOS: PASS.
- All 122 suites under OS isolation on macOS: PASS.
- All 122 suites directly on Aegis: PASS; zero inherited-HOME file writes.
- Aegis `deploy-atelier.sh --check`: all suites, plan and staged validation PASS.
- Browser fixtures: failed request keeps draft; duplicate taps produce one request;
  hostile text does not create elements; Study approval is enforced; cancelled
  microphone grants release tracks; provider completion waits for audio end;
  duplicate callbacks do not double-record; screenshot pixels follow actual
  DOM order and group opacity; closed stage refuses capture.
- Four shared-client lifecycle unit tests PASS.
- `npx cap sync ios` PASS, including CocoaPods.
- Simulator `xcodebuild ... CODE_SIGNING_ALLOWED=NO build`: BUILD SUCCEEDED.
- Release 20260912-153539-aca1b32 deployed and verified: all six units active,
  twelve critical installed source paths and all four served client routes match.
  Final release **20260912-155122-fa3949b** also deployed successfully, including
  fragment draft and screen-sharing uncertainty fixes. Its final installed audit
  confirms all six active units, twelve matching critical paths, four matching
  served routes, and actual loaded checkpoint parameter equality.

- Final signed iPhone build succeeds; installed successfully with assets identical
  to app 2db8e87. The final launch request was refused because the iPhone was locked.
  Earlier app 6ee9ecb launched; physical visual/audio acceptance is still unobserved.
- QLab local commit 8f5c935: all remote generated/seed experiments run in OS isolation;
  source/helper hashes and unique receipts are retained by the parent. Four
  adversarial boundary tests and five real seed executions pass in scratch. The
  Aegis status bridge confirms the new boundary. The QLab repository has no remote;
  its existing modified palettes and untracked unsealed Lab files were preserved.
- App 2db8e87: delayed fragment acknowledgements preserve newer typing and duplicate
  submits are held. Failed screen-sharing stop/status remains visibly unknown.

## All 27 retained items: evidence boundaries

| Item | Implemented or verified now | Still required for full acceptance |
|---|---|---|
| P01 30 | Repository-local source aliases; loaded-module file/hash inventory | Source-by-source review of wider untracked runtime |
| P01 31 | HTTP turn identity and central provider receipt correlation | Complete context/writer tracing for every independent route |
| P01 32 | Central OpenAI/Anthropic provider IDs and usage join; voice provider IDs | Independent adapter coverage |
| P01 33 | Current index and 1,282 legacy rows inspected; local rebuild attempted | Local embedding service timed out; historical model provenance absent |
| P08 315 | Safe rendering patches and adversarial browser fixtures across major active views | Exhaustive every-tab acceptance is not claimed |
| P08 316 | Shared checked HTTP/application-error helper for application requests | — |
| P08 317 | Text/photo/Study/avatar drafts kept until acknowledgement; voice transcript retained | — |
| P08 318 | Shared pending-turn identity; stale history, room and callback guards | Physical rapid-switch acceptance remains unobserved |
| P08 323 | Visible-stage composition, DOM ordering and group opacity, verified by pixel test | — |
| P08 324 | Stop status uses returned Boolean; failures remain failures | Physical stop effect is not inferred from UI state |
| P08 325 | Escaping, zero preservation and stale telemetry indicator | Exhaustive malformed telemetry/view combinations remain untested |
| P08 326 | Close/background cancels capture/calls/animation and pauses media | Device-specific background behavior remains unobserved |
| P08 327 | Draft persistence, shared turn ownership, explicit playback evidence | Physical cross-surface continuity remains unobserved |
| P08 334 | Late microphone cleanup; audio-context cleanup; surfaced playback rejection | All legacy pending-speech paths remain unproven |
| P08 343 | Shared request helper; active duplicate dismiss/close handlers removed | — |
| P08 344 | Mounted-route availability controls | Broader capability rendering beyond the named controls remains open |
| P08 345 | Generation checks and media/draft cleanup | Physical voice/stage lifecycle remains unobserved |
| P08 346 | Native task registration, requested 15-minute interval, permission checks; sync/build pass | Actual iOS background delivery remains unobserved |
| P11 396 | Repeated manifest refresh; stale room/media rejection; screenshot pixel evidence | User-visible avatar/cache/audio acceptance on device |
| P11 397 | Response IDs, played completion, interruption uncertainty and duplicate/closed-session rejection | Live provider/hardware acknowledgment join, without manufacturing a call |
| P11 398 | 67 recorded nights inspected by schema; no run IDs | Historical causal/thread joins cannot be reconstructed from missing fields |
| P11 399 | Parameter-versus-checkpoint comparison wrapper; checkpoint inspected | Training provenance absent from checkpoint metadata |
| P11 400 | Actual delivery/effect stores located; five effect receipts inspected by schema | No want/artifact/observation join in those effect receipts |
| P11 401 | Live selected-module metadata, excluding agent-room | Wider untracked-source review remains open |
| P11 402 | Study rendering and explicit approval gate fixture-tested | A new paid Forge run is outside this request and was not attempted |
| P11 403 | /Users/kevin/qlab source and Aegis bridge verified; remote execution isolated with parent-owned receipts; four isolation tests and all five real seeds pass in scratch | Separate unsealed bench_remote.py remains outside this repaired entrypoint |
| P11 404 | Three repository revisions verified; named client deployment and acceptance checks | Whole-system physical acceptance remains incomplete |

The current semantic index was preserved unchanged when the local embedding
service timed out. A later model-list request succeeded, but a static embedding
probe still timed out after 45 seconds. Legacy rows were not relabelled, and no historical provenance,
human hearing, observed effect or paid verification was invented.

Other handoff categories—trial-ledger migration, current/dismissed-wants mutation
migration, and durable served-tension recovery—remain listed in open-work and are
not credited to the hypothesis outbox repair.

Automatic approval review refused copying private emotion-model source into the
local workspace. Live PID, file-hash and parameter comparison were used instead;
this does not establish a complete review of that private source.

## Evidence files

- [Full deployment output](review-evidence/2026-09-12/aegis-deploy-final.txt)
- [Predeployment check](review-evidence/2026-09-12/aegis-check-final.txt)
- [Installed units, file hashes and checkpoint](review-evidence/2026-09-12/installed-final.json)
- [Linux direct suite results](review-evidence/2026-09-12/aegis-direct-final.json)
- [Mac direct suite results](review-evidence/2026-09-12/mac-direct-final.json)
- [Mac isolated suite results](review-evidence/2026-09-12/mac-isolated-final.json)
- [Browser fixtures](review-evidence/2026-09-12/client-browser-fixtures.json)
- [Quantum seed checks](review-evidence/2026-09-12/qlab-five-seed-check.json)
