# Standalone alarm release, followed by the coordinated identity change

The review is split into two main-repository branches. Merge and deploy **(a) first**:

| Release | Branch | Dependencies / operator boundary |
|---|---|---|
| (a) Provider/host alarm, existing compute-ledger attempt accounting, owner pause command | `codex/security-alarms` | Standard owner-run deployment; no identity cutover, random-secret preparation, new auth startup check, WebSocket admission gate or client change. Existing merged voice-token repair is retained. |
| (b) Coordinated identity, private reads and telemetry/events admission | `codex/security-auth-cutover` | Built on (a). One later approval with the companion app `codex/security-alarms` at `6056939`; use its `docs/security-auth-rollout.md`. Do not merge it just to deploy the alarm. |

Nothing was deployed, rotated, restarted or sent by this revision. Funnel stays on. The alarm still needs owner deployment and ordinary-use installed acceptance.

## Failure behavior

`paid_http` observes existing call paths and uses **only `compute-ledger.jsonl`** for call attempts. `compute_admission.record` uses strict persistence so errors are observable, but every accounting/import error is caught before returning to the original transport. Recording loss does not become a chat/generation admission rule. The **owner-created pause marker is the only instrumentation refusal**; local inference is unaffected.

Redacted accounting failures contain provider, script, exception class and timestamp; never request URL/query, credentials, prompt/body or exception message. They go to existing `organ-failures.jsonl` and a structured stderr/journal fallback, at most once per provider/minute/process. They are health events, not another call ledger. The monitor reads both sources, reports the rate as UNKNOWN, uses `deliver.py`, and records the alarm into the normal fault loop. Accounting-loss/surge alerts share the one-provider-per-hour cooldown. The structured journal source allows evidence to survive a fault-file write error. Total loss of writable state/journal/delivery infrastructure still requires independent/off-host monitoring; these controls do not promise notification through a failed host.

The diagnostic preview's urllib adapter counts at `AbstractHTTPHandler.do_open`, with context-local attribution. Real HTTP attempts and redirects count; a supplied preview transport that never opens HTTP does not write the ledger. It also honors the owner pause before transport. Other existing sync/async/curl transports retain their original inputs/results and error behavior. No model choice, prompt, retry or timeout is changed.

Production import repairs keep the three reported suites unchanged: the video handler and preview function import their own transport dependency; standalone inline outreach resolves either the installed helper or a single identified local checkout. There is no test-mode bypass of accounting or of the pause marker.

## Owner deployment after review and approval

The main thread reviews and merges **only `origin/codex/security-alarms`** into `claude/device-visuals-2026-10-13`. Gloria then runs the standard command exactly:

```sh
cd ~/Vintos-main && [ -z "$(git status --porcelain)" ] && git checkout -q claude/vintos-avatar-ui-redesign-br5lt4; python3 scripts/aegis_sync.py --from claude/device-visuals-2026-10-13 --deploy 2>&1 | tee ~/deploy-latest.log
```

No `VINTOS_AUTH_CUTOVER`, generated identity or client rollout is needed for (a). The deploy runs its normal complete isolated broker suite before promotion, installs the alarm/helper/timer via its manifest, and leaves its exact printed `restore.sh` rollback. Require `deploy OK` and service checks, not the pipeline's exit code alone. The later cutover remains a separate approval.

Owner pause and resume:

```sh
python3 ~/.vintos/workspace/scripts/paid_http.py pause
python3 ~/.vintos/workspace/scripts/paid_http.py status
# Resume only after investigating the alarm:
python3 ~/.vintos/workspace/scripts/paid_http.py resume
```

## Reproducing validation without a live store or sender

Every suite is invoked through the repository's existing runner, which creates a copied checkout/scratch HOME, places `scripts/` on the path, installs its HTTP fixture, and enforces the OS sandbox. No tests were changed to mask the three reported failures. External network remains denied; do not bypass the OS boundary to make a test pass.

```sh
for suite in broker/tests/test_*.py; do
  python3 scripts/run_isolated_test.py "$suite" || exit 1
done
```

The review run invokes every suite and continues after failures to record the complete matrix. See `audit/security-alarm-full-suite.json` for exact interpreter, baseline, totals, suite names and remaining failures. The full local run is not a claim that Aegis's deployment suite or installed alarm has passed; those stay in the owner deployment gate.
