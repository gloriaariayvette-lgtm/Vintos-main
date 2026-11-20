# Shirt loop validation — November 19

Source change: `525067f6d4269e623bb7f9db872ea35fab3fddc3`, based on fetched deploy-branch commit `49dca25b392ff900cb409857ff430575cb18419b`.

## Shirt checks

Fifteen offline shirt checks pass, also through `scripts/run_isolated_test.py broker/tests/test_haptic_shirt_loops.py`. These cover exact 180-second loop duration, deadline-clamped sample leases, Stop cancelling renewal without restart, disconnect termination, repeated signals, exclusive playback ownership, route mapping, disc budget, and live-only context.

The fake-clock duration check exposed a floating-point sample-boundary stall. A small boundary tolerance fixed the scheduler edge; all cases were rerun successfully. No firmware change is needed for host-side looping.

Previously confirmed physical behavior: the usual chest wave works over Bluetooth on battery power with USB absent; off produces zero context characters and on restores fresh context without re-pairing. The new 180-second physical run could not start because the shirt was not advertising. **Three-minute physical acceptance remains pending.** No queued loop will automatically replay when it reconnects.

## Whole repository run

Every one of 756 broker suites was attempted through the required isolated runner on Python 3.12. The initial base-Python run passed 615 and failed 141; many failures were missing dependencies. A separate workspace test environment supplied the missing Python packages, and every failed suite was rechecked. Combined results across the initial run and dependency-corrected retries: 739 passed, 17 still failed. This is not a single all-green full-suite run.

Each persistent failure was also run against the unchanged fetched base using the same test environment and isolation boundary. All also failed there; no persistent feature-only failure was observed. This does not make the repository deployment-ready.

| Suite | Feature exit | Unchanged base exit |
| --- | --- | --- |
| test_dream_shadow.py | 1 | 1 |
| test_dream_identity_context.py | 1 | 1 |
| test_mail_attachments.py | 1 | 1 |
| test_media_embed.py | 1 | 1 |
| test_media_embed_places.py | 1 | 1 |
| test_old_systems_repair.py | 1 | 1 |
| test_aegis_house_model.py | 1 | 1 |
| test_paper_print.py | 1 | 1 |
| test_outreach_feeling_triggers.py | 1 | 1 |
| test_reference_compare.py | 1 | 1 |
| test_study_reading.py | 1 | 1 |
| test_lab_bench.py | 1 | 1 |
| test_wants_panel.py | 1 | 1 |
| test_outreach_postcards.py | 1 | 1 |
| test_world_model_shadow.py | 5 | 5 |
| test_workbench.py | 1 | 1 |
| test_study_fix.py | 1 | 1 |

Observed baseline issues include unavailable Linux shell/tools and fonts on this Mac, fixed temporary paths blocked by OS isolation, missing scientific-runtime dependencies, existing fixture expectation failures, and tests reaching their 180-second limit. No unrelated production code or test bar was changed to make these pass. Detailed private diagnostics remain local; no notification destinations, credentials, or runtime logs are published here.

## Publication scope

Firmware, adapters, prompt generator, map, source pattern table, setup docs, and offline tests are published under `hardware/haptic_shirt/`. Pairing material, generated firmware images, runtime state, local logs, and virtual environments are excluded. Live Vintos context/action integration, merge, and deployment remain pending the normal review route.
