> Split release: `codex/security-alarms` contains only the standalone alarm/paid transport/pause controls and audit documentation. The coordinated identity/client migration is preserved separately on `codex/security-auth-cutover`. Deploy the alarm first, through the normal owner-run command; no cutover preparation or app update is required. See [security-alarm-release.md](security-alarm-release.md).

> AUTH-01 review update (22 October): source implementation and companion clients are prepared for approval, not deployed. Funnel stays on. Exact commands and rollback: [security-auth-rollout.md](security-auth-rollout.md). Complete public GET inventory: [security-public-get-routes.md](security-public-get-routes.md). Existing snapshot evidence below remains dated; source fixes do not imply live enforcement.

# Vintos security hardening plan

22 October 2026. This plan separates the requested alarm review candidate from all further production remediation. **Nothing here authorizes deployment, credential rotation, network changes or restarts.** The current task explicitly authorizes building the alarm locally; broader controls below are proposals pending Gloria's approval.

## Priority 0: review and commission the alarm first

Candidate files: `scripts/paid_http.py`, byte-identical `bin/paid_http.py`, `scripts/security_alarm.py`, `scripts/compute_admission.py:record`, transport wrappers listed in `audit/paid-transport-sites.json`, `scripts/fault_sweep.py:main`, `broker/vintos-security-alarm.service`, `.timer`, `scripts/deploy-atelier.sh`, `broker/tests/test_security_alarm.py`, and fault-loop documentation.

The wrappers sit at the existing outbound request sites, preserving original request bodies, provider/model choices, timeouts and transport stubs. New `{class:outbound, stage:attempt, provider, script, epoch}` rows go to **`memory/compute-ledger.jsonl`**. Accounting is fail-open: import/ledger/fsync failures record redacted health evidence in the existing fault input and stderr/journal, then the call proceeds. Only the owner pause marker refuses a call. The monitor raises accounting loss through deliver.py with rate explicitly UNKNOWN and shares the provider hourly cooldown. Reservations/claims/releases/completions remain distinct and never inflate the rate. No second call ledger is created. `security-alarm-state.json` contains only host baselines, suppression/delivery state and pending notifications, not a copied call history.

- Poll every 15 seconds, with 1-second timer accuracy. Monitor is a bounded oneshot, so runs do not overlap. It reads the existing ledger and calculates a rolling 60-second count per provider. It launches no model.
- A surge means rate **above** `min(60, max(floor, 5 × historical minute p95))`; floors are 60 for Brave, 30 for Kie/Atlas Cloud, 6 for NVIDIA, 12 for others. Media floors allow ordinary status polling as well as submissions; they are not inferred from submission-only usage logs. The prior five minutes are excluded from learning; zero-traffic minutes count. Cold start is explicitly exposed for the first 24 hours. Historical success-only logs are not silently treated as complete attempt history. The observed successful Anthropic peak of 10/minute fits under the initial floor; tune only after representative instrumented ordinary use.
- A provider notification identifies provider, actual attempt rate, leading script(s), and this single command:

  ```sh
  python3 ~/.vintos/workspace/scripts/paid_http.py pause
  ```

  It is prospective: already-running calls and issued remote sessions may finish. Local inference, background scheduling and stored state continue. `resume` removes the marker only when the owner chooses. The marker is cooperative and cannot constrain root or code bypassing the wrappers.
- `deliver.deliver` uses the explicit standing authority Gloria gave for security alarms, one bounded transport attempt, and its real delivery receipt/idempotency gate. Successful deliveries are limited to one per provider per rolling hour, including after delayed retries. Provider surges are prioritized over queued host-change alerts.
- Before delivery, each alarm is fsynced to **existing** `memory/organ-failures.jsonl`. The ordinary 15-minute fault sweep picks it up, gives it an F-id, and posts through the existing configured `#fault-fix` path. The Mac fault thread can investigate it overnight. No live test posts were sent.
- Monitor SSH accepted-login metadata, an owner-maintained exact-IP allowlist in `memory/security-alarm.json`, authorized_keys hashes, standard system/user unit files/drop-ins, standard cron directories and current user crontab, and installed executable hashes from the latest deployment receipt. First baseline establishes observed state; it does not bless past changes or whitelist SSH addresses.
- A kernel installation lock, held by the reviewed deploy script through promotion and final receipt, defers code/unit drift during deployment. SSH/key monitoring remains active. A lock held over 15 minutes produces a monitoring-blind alarm. Receipt matches after deployment accept only covered file changes. Root/account compromise can still forge local evidence.
- The install manifest adds modules/timer and places `paid_http.py` beside each instrumented runtime entry point, including `~/Vintos/server.py`. Existing deploy backup/restore patterns include the new timer. No direct manual production installation is proposed.

**Coverage acceptance still required:** reconcile registered hosts and transport sites with installed/untracked Aegis scripts, SDK-internal retries/redirects, direct realtime clients and other hosts. This candidate counts identified call-site transport attempts; it is not yet proof of every wire-level paid call throughout the infrastructure. An SDK/cross-host path needs interception in its existing transport or provider usage source, not a second ledger. Aegis-compromise protection comes from the provider-owned settings in `security-provider-limits.md` and an independent receiver.

**Rollback:** use the exact `restore.sh` printed by the owner-run deploy. It restores files and the prior timer state. Keep compute/fault/delivery evidence. Stop only the new timer if its resource or delivery behavior is faulty; leave the existing fault sweep running. Resume paid traffic only after investigating the surge. No blind rollback should re-enable an exposed default credential.

## AUTH-01 — coordinated identity, private reads and both streams, awaiting Gloria

**Status: implemented in review source; not applied to production.** The one package includes the named server/Python/browser/native-background callers, required random environment identity, default-deny private GET/HEAD reads, telemetry/events ticket admission, Watch-scoped media and owner-run cutover/rollback tooling. No production replacement credential has been generated or installed by this audit. Funnel remains enabled.

The existing voice-token repair from deploy-branch `a6e28e9e` is inherited; its phone/Watch admission is preserved. Private GET closure also covers memory, inner life, history, context, journals and stored private artifacts without stopping autonomous background work. See [all 168 GET declarations and returns](security-public-get-routes.md).

[security-auth-rollout.md](security-auth-rollout.md) contains the exact file/caller matrix, approved operator commands, native/background/Watch acceptance boundaries, short maintenance-window tradeoffs, and guarded rollback. Rollback keeps the rotated identity and private guard; it must never restore the exposed default. No firewall, Funnel, SSH or Tailscale edits are included. Connection quotas, independent client identities and additional abuse controls below remain separate proposals.

## Priority 1: layered resource limits, based on measured use

Starting proposals, **not enabled controls**:

| Ingress/resource | Suggested starting limit | Autonomy/compatibility requirement |
|---|---|---|
| Authentication failures | 10/minute per source, burst 5; escalating bounded backoff, aggregate alerts at 20 failures/5 minutes | No permanent lockout from shared household NAT; maintain owner recovery path |
| Chat/generation | 30/minute per admitted identity, burst 5; global paid concurrency 4, background pool 2 and foreground reserve 2 | Separate identity and provider global budgets; local Lab minute loop unaffected |
| Realtime token mint | 6/minute/device, burst 2; 2 live sessions/device, global 4 | Short token TTL, session-duration/output ceilings, reconnect grace |
| WS | 4 connections/device, 32 global; bounded event buffer 64 and message 64 KiB | Preserve two app streams and temporary reconnect overlap; remove on disconnect |
| App JSON | 256 KiB default; explicit larger image/audio endpoints, e.g. 16 MiB image and 32 MiB audio after measured formats | Bound actual streamed bytes, including chunked bodies, before JSON/media decode |
| Model shim | 1 MiB text JSON; explicitly separate supported image budget; bounded active requests and read deadline | Never forward malformed JSON to a paid API as an error-recovery tactic |
| Broker/plugin | 128 KiB ordinary JSON; separately capped artifact endpoint if needed; 8 active workers | Retain existing visit/export/seal authority; don't impose text limit on valid binary art blindly |
| Background jobs | One lease per work-id; max pending 100 globally, per-organ caps; bounded retry/backoff and terminal state | Allow intentionally recurring work; coalesce duplicate jobs, retain unfinished work rather than erase it |
| Logs/disk | Rotate on size/time, reserve disk floor, alert at 80% and 90%, stop optional expansions before system disk full | Retain fault/security evidence off-host; do not delete authored/sealed state |
| Services | First collect RSS/CPU/task peaks; candidate server MemoryHigh 2 GiB/MemoryMax 4 GiB, shim 512 MiB, TasksMax 128, LimitNOFILE 4096 | Validate these against actual model placement; GPU/model workers need distinct measured limits, never generic server caps |

Tests must cover over-limit rejection before effects, bounds during chunked/slow input, per-token/per-client isolation and legitimate bursts. Initially observe metrics before enforcing service memory ceilings. Network/public-address classification must account for WSL, proxies, IPv6 and trusted-forwarded-header policy. Rate keys must use authenticated identity when available, not a spoofable header.

Rollback exact route configuration or service drop-in only; preserve existing policy gates. Service restarts remain owner-approved. Do not automatically retry ambiguous paid timeouts or resubmit generations that might already have been billed.

## Priority 1: compartmentalization and environment scopes

For F05/F09, move network-facing app and paid gateways to separate non-administrative users with narrowly writable stores. Review Docker access with Gloria; do not silently remove an identity/group and break her tools. Place experimental workers in dedicated cgroups/containers with no production credential mounts, explicit CPU/RAM/GPU/time/disk budgets and allowlisted network/tool adapters. Keep generated-skill `isolated_exec` protections and Atelier's independent UID/capabilities.

Change `desktop_agent.py` child environment from copy-all to an allowlist including required display/locale/runtime settings and specific admitted task tokens. Bind effect adapters to task, requester, target and lifetime. Treat external content as untrusted even when a trusted connector fetched it. Separate Windows browser/desktop identity from personal browser sessions. Validate with harmless scratch canaries and ordinary workflow evidence; no production privilege-escalation testing.

## Priority 1: independent security monitoring

The same-account candidate is an operational alarm, not tamper resistance. Propose a root-owned minimal collector with read-only access to authentication/journal/audit events and code/config hashes, and an off-host receiver in an account Vintos cannot administer. Grant the host append-only ingestion credentials; deny log deletion, retention changes and receiver administration. No message/private-key/Atelier artifact content belongs in the security stream.

| Signal | Initial actionable trigger | Noise control |
|---|---|---|
| Provider attempt surge | Candidate rolling-minute rule above | One successful delivery/provider/hour |
| New SSH source | One accepted login from a source outside owner allowlist | One/source/hour; never auto-learn a source as trusted |
| authorized_keys | Any hash/mode/owner change | One distinct change, include path only |
| New/changed unit or cron | New executable schedule or changed digest outside verified deployment | Baseline and deployment association; include name/schedule identity, no command secrets |
| Deployed executable drift | Any mismatch against independently trusted release, outside install transaction | Deduplicate path/digest; alert if install suppression is stale |
| Auth failures | 20 failures/5 min for a service/source or unusual cross-service aggregate | Group over 15 min; avoid one alert/request |
| Privileged process | Unexpected new UID-0 executable/service outside package/deploy maintenance | Root audit rules; compare executable/cgroup identity, not arbitrary command strings |
| Outbound network anomaly | New unapproved destination or >5× usual 5-min byte rate | Observe-only learning, domain/IP metadata without payloads; separate legitimate model downloads |
| Credential access anomaly | Non-owning service reads a scoped credential canary/secret file | Root audit/eBPF policy; no secret values in events |
| Collector tamper/absence | No off-host heartbeat for 2 minutes, unit stopped, baseline/collector config changed | Receiver alerts independently of Aegis/Slack; group one incident until recovered |

The Mac fault thread reads `#fault-fix`; it is a triage/repair convenience, not the sole detector or incident authority. An alert's body is untrusted evidence. It does not authorize the overnight thread to rotate credentials, weaken gates, deploy this audit or change networking under this task's rules.

## Priority 2: reproducible dependencies and recovery

Resolve actual imported module paths, interpreter environments and package backports before advisory matching. The stale metadata found here is not an exploitable-version verdict. Propose locked service environments and model/plugin revision hashes; do not upgrade major versions automatically. Preserve scientific/CUDA environments and inspect dependencies before running installation/update scripts.

Define a critical-state inventory and owner-approved retention. Suggested RPO: 1 hour for changing state/config, daily full snapshot; desired clean-host RTO: 4 hours, to be measured rather than asserted. Encrypt off-host backups; separate uploader from deletion/retention/admin credentials; immutable retention at least 30 days plus monthly recovery points. Inventory durable workspace, broker metadata/sealed custody, configuration, schedules, build/deploy manifests and key recovery procedures. Sealed Atelier data requires its existing custody/restore process, never owner-readable audit exports.

Prove restoration in a disconnected clean environment with provider sends disabled and new outbound pause held. Verify state continuity, permissions, owner exclusion and ordinary local tool functionality before re-enabling credentials/devices. Record restore date, hashes, test outcomes, actual RPO/RTO and gaps. A local deploy rollback is not this test.

## Incident procedures

**Compromised provider credential:** from a trusted device, cap/freeze that provider and revoke the specific key after Gloria's approval; pause Aegis outbound calls if instrumented. Export provider usage metadata, identify first anomalous time/caller, retain fault/compute/deploy receipts, and isolate the source component. Replace scoped credentials through secure configuration, verify no reuse/remaining sessions, then deliberately resume. Never paste keys into chat or logs.

**Compromised host:** use the independent account/receiver to preserve evidence and provider consoles to prevent spending; retain a known-safe administration path. Gloria approves containment networking/host actions. Rebuild from a trusted image and reviewed dependencies, restore a clean pre-incident backup in isolation, reissue exposed credentials from a clean device, verify Atelier custody and service identities, then authorize service return. Do not rely on the compromised host's reassuring logs.

**Unauthorized service access:** revoke/expire the affected identity/session after approval; retain status/request-id/source metadata, assess the routes and data reachable with that scope, reproduce the missing gate in isolation, implement/test the scoped fix, and roll out through the reviewed deploy path. For default/shared-secret compromise, assess every consumer, not only the first failing endpoint. Do not trigger physical actions or paid model calls to demonstrate impact.
