# October 7 software campaign: prepared changes, not deployed

**Historical preparation snapshot.** Later owner-installed Forge quota and independently installed, paused Study
quota supersede the deployment status below. `local-completion.md` records the subsequent source fixes and
validation. Source was subsequently committed and fast-forwarded into the shared checkout, with unrelated
untracked files preserved; the preparation statements below describe the earlier snapshot only.

Base checkout: b304baf8f28bdce69d0db96c6af78904e65dbe66. Shared checkout and live runtime files have not been edited. Detached worktree lives in the authorized Windows task directory.

## Quota design and self-review

- New `software_quota.py` reads a bounded JSON document beside the installed module. The reviewed document remains here as `software-quota-override.json`; it has NOT been activated in any live scripts directory.
- Exact authorized date is 2026-10-07, America/Chicago. Limits accept integer 3..10 only, reject bool/float, duplicate fields, oversized/malformed config, wrong dates/timezones/authorization and extra schema fields. Missing/invalid/expired configuration gives the ordinary limit of three.
- No counter is reset. Existing Forge SQLite reservations remain authoritative, including failed attempts and all project categories. Claims and legacy builds share the same cap. The quota grants no capability, spending authority, private-content access or project authorization.
- Study counts every submission on the campaign date regardless of a legacy reset receipt, even if the override is malformed; reset is refused for that day. Requests serialize count/check/append. Worker progress preserves requests added while it was working, preventing stale queue snapshots from erasing usage. The existing legacy reset test is pinned to October 5 to verify that contract separately.
- Study timestamps retain their existing naive format but explicitly use Chicago time. The override expires at 2026-10-08 00:00 CDT (05:00 UTC), with no cleanup job.
- Both deployment manifests include the helper dependency. Configuration activation must copy the reviewed JSON beside the helper only after deployment scope is resolved. No blanket service/deployment command has been run.

## Deployment boundary

The only normal deployment script is broad: `scripts/deploy-atelier.sh`. Its Forge section targets `/home/atelier/forge-loop` and `atelier-forge-loop.service`; its other sections copy many unrelated files and can restart other services. The parent has explicitly clarified that the shared Forge runtime code/service and its required restart ARE authorized; the Atelier exclusion concerns private marked conversations/projects/records. No private records or `/home/atelier/forge-loop-config.json` were accessed.

The remaining host blocker is privilege: the normal installer's preflight `sudo -n true` returned exit 1, `sudo: a password is required`. No alternate privilege route was attempted. The service remains active. Additionally, `resonance-pulse.py` differs substantially between checkout and deployment; a broad deployment could overwrite unrelated work. Any privileged installation must be confined to these reviewed quota files and its required Forge restart, preserve counters and original file ownership, and verify the existing target hashes before replacement. No blanket deployment or automatic Study submission is cleared by the unit-test result alone.

Required quota runtime files: install `software_quota.py` and the reviewed `software-quota-override.json` beside BOTH consumers; update house `study_fix.py` and Forge `forge_loop.py`. Keep the repository manifests in sync. The existing Forge installer uses root-owned mode 0644 for bundle files, a backup and confirmed restart; retain that supported procedure. No changes to the Forge config, token files, security controls or effect-authority grants are needed. The installed-hash marker for the baseline Forge `forge_loop.py` was `d6deb1d9832378c4b0dfbfeae072106447e3d482db682bf41140ea2bc62f577b`; verify the actual target before replacement rather than trusting a potentially stale marker.

After an authorized scoped install, GET `/api/budget` must report October 7/Chicago, limit 10, used at least the pre-install value (3 at inventory), and remaining `max(0,10-used)`. Study must retain all today's submissions (0 at inventory), including any arriving meanwhile. At Chicago midnight the effective limit returns to three with prior records retained. A service restart is not a counter reset.

## Cost evidence

The local `claude_cache.py` estimate uses Fable rates of $10/M input tokens, $50/M output, $0.25/M cache read and $12.50/M cache write. Five historical October 5 calls total approximately **$4.7395**. This is not current spend or a per-request forecast; the prior two/ten-request extrapolations are withdrawn. Forge preliminary investigation uses Fable orchestration and direct xAI API Grok subagents; automated Study fix uses Fable directly. Those paths must not be conflated.

`study_fix.py` permits up to three planning calls and two repair calls per submission, each requesting at most 16,000 output tokens. Ten submissions could therefore make up to 50 Fable calls. Input lengths, cache reuse and repair frequency vary. Its `claude_cache.ask` path does not invoke `compute_admission.reserve_paid`. The general compute default is 400 provider reservations/day; three Anthropic reservations were counted today, but that guard does not bound this Study path. No models have been invoked or substituted. No account billing ceiling was established from the available non-secret metadata.

## Remaining prepared software

`study-requests.json` contains two bounded, deduplicated requests: atomic home_presence writes and original/repaired parser evidence. They are not queued because the Study timer can immediately invoke models and later the broad deploy. Sensor freshness commit 658b295 is already deployed and excluded from these requests.

`mmwave_presence.py` is a software-only preparation with an independent explicit state path, no hardware/network calls, no dispatch, no emotion nudge and no identity claim. It validates exact booleans, preserves unknown state, rejects future/out-of-order inputs, applies proposed 30-second freshness and one-second debounce, suppresses the first recovered baseline, limits returned events to two/hour, and serializes atomic independent-store updates. It is not in deployment manifests, has no live consumer and alters no authority grants. Shared sensor_reactions integration/serialization and physical commissioning remain separate work; this module must not be presented as a commissioned live sensor.

## Verification completed

All tests used the repository's `run_isolated_test.py` OS boundary, scratch stores and blocked/stubbed effects: quota integration 7/7, existing Study suite 64/64, Forge plain cards 4/4, Forge deployment-bundle suite 14/14, prepared mmWave intake 5/5. `git diff --cached --check` passed. The legacy Study JSON helpers emitted ResourceWarnings for pre-existing unclosed file handles; there were no failing assertions. No live provider, deployment or sensor was called by these tests.
