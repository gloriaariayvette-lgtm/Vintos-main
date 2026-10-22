# Vintos infrastructure security audit

Audit date: 22 October 2026. Scope: read-only Aegis inspection from the local Mac, source review, and offline alarm development. Review branch: `codex/security-alarms`. Source/deployed release observed: `e502b389c77e815086a5d9a6047c950ead0d8ec9`, receipt `20261022-010546-e502b38.json`, 561 recorded files, no recorded deployment failures. These are snapshots, not permanent claims.

**Production has not been hardened by this branch. The alarm is a review candidate, not installed or active.** No credential rotation, restart, firewall/Tailscale change, deployment, provider purchase, test notification or Slack post was performed. Atelier content, seals and owner-exclusion rules were not inspected or changed.

## Executive summary: five most important improvements

1. Replace the **accepted source-default application credential** through a coordinated client migration, then remove the fallback. A wrong credential returned 403; the default from the installed source returned 200 on the same protected read-only route.
2. Authenticate public app reads, WebSockets and realtime-token minting. Tailscale Funnel enables public app exposure; an unauthenticated telemetry upgrade returned 101. The installed voice-token handler can mint paid sessions and returns private instructions without authentication.
3. Install the reviewed provider-attempt alarm and pause control, then close the remaining cross-host/SDK coverage gaps. Add provider-owned caps immediately from a trusted device. Existing daily reservations and success-only usage files are incomplete attempt accounting.
4. Separate network-facing and experimental workloads from Gloria's administrative identity and writable Docker socket, adding measured resource limits. Preserve background autonomy, local inference, and task-specific tool authority.
5. Add an independent off-host security heartbeat, immutable logs and recoverable encrypted state backups. Existing fault/deploy records and rollback copies share the host and credentials they would need to survive.

## Evidence and method

Evidence lives in `audit/aegis/`: `discovery.json` (listeners, permissions, schedules, service controls, accounting aggregates); `verification.json` (running script identities and safe protocol results); `boundaries.json` (credential acceptance, actual server paths, package backports and access limitations); `final-evidence.json` (active units, actual imported versions, SSH/usage summaries and log settings). The four collector scripts are saved beside the evidence for reproducibility. They are **read-only probes, not programs to run as a blanket approval for future changes**.

Inspection avoided environment dumps, command-line dumps, message bodies, private keys and sealed stores. HTTP response contents were discarded; only status and size were retained. One local WebSocket upgrade was immediately closed. No token minting, malformed production request, load test, device action or privileged exploit was attempted. Authentication testing used one protected read-only status route; the credential itself is absent from evidence output.

`audit/source-secret-scan.json` records a bounded source/config scan and history-pattern search. `audit/paid-transport-sites.json` inventories modified egress sites. `audit/regression-results.json` and individual logs record offline tests. A test pass does not prove installation or live enforcement.

## Confirmed inventory and exposure map

Full unit, timer, cron and socket inventories are in the JSON evidence; historical repository units are not automatically counted as active. There were **183 active user crontab entries**. Recurring Lab and subconscious work is intentional, not an intrusion finding. Some generic user-unit discovery output was capped; the final dedicated services/timers/socket/path inventory avoids the device-unit noise.

| Surface | Running evidence / address | Exposure and security observations |
|---|---|---|
| Main app | PID script `/home/gloria/Vintos/server.py`; `0.0.0.0:8500`; byte-identical to checkout `bin/server.py` | Local/all host interfaces; Funnel maps public HTTPS 8443 here. Default credential accepted; sampled robot/desktop reads reject no credential; telemetry WS accepts none. |
| Provider shim | `/home/gloria/Vintos-main/bin/vintos_claude_shim.py`; `127.0.0.1:8599` | Loopback only, no caller authentication or body bound in installed handler. Local same-user compromise can spend through it. |
| Atelier broker | system `vintos-atelier.service`, user `atelier`; `127.0.0.1:8611` | Separate UID, strict system protection, private tmp. Public health is intentional metadata. Visit/export/house capabilities exist; sealed content was not accessed. |
| Forge runtime | active system `atelier-forge-loop.service`; `/home/atelier/forge-loop/forge_loop_runtime.py` | Active separate account, not the nonexistent/inactive `vintos-forge.service` queried initially. Generated-skill build/invoke code uses `isolated_exec`; no exploit against it was attempted. |
| Chemistry Lab | active user service; installed workspace script | Strict filesystem sandbox and `NoNewPrivileges`, but unlimited MemoryMax/CPUQuota and broad workspace writes. Minute loop is local/free. |
| Plugin gateway | active user service, `127.0.0.1:8624` | Token-authenticated POST envelope, 128 KiB body bound, loopback bind; unauthenticated health is available. Relay crosses to another host/account's connected apps. |
| MCP endpoint | workspace `vintos_mcp.py`, `127.0.0.1:8625` | Public Funnel 443 `/` proxies here. Local unauthenticated health returned 401. Installed source has authentication, 64 KiB request bound and process-global request limiter. Tool-specific authorization still matters. |
| Forge controls | `127.0.0.1:8612`; HTTPS 9443 proxy | Tailnet HTTPS mapping; no AllowFunnel entry for 9443 in snapshot. Full owner/control audit not completed. |
| Robot bridge | workspace `robot_bridge.py`, `0.0.0.0:8404` | Local unauthenticated state read returned 401. No direct Funnel mapping to this port; authenticated app routes proxy robot requests. |
| Door / Alexa / speech | `0.0.0.0:8400`, proxy targets 8401 | Funnel 443 maps `/api/door` to 8400, `/alexa` and `/speak` to 8401. No 8401 listener appeared in the socket snapshot: configured route can be inactive. No device action tested. |
| Other robot / scenes | `0.0.0.0:8403`, `0.0.0.0:8501` | Active scripts `velaris-robot-bridge.py`, `scenes_server.py`; bind exposure confirmed, inbound network reachability and auth not certified. |
| Bench | `/home/gloria/repos/vintos/bench/server.py`, `0.0.0.0:8791` | Separate checkout/runtime; token scopes and remote ingress not fully verified. |
| Other applications | `0.0.0.0:8788`, `:8001`, `:8123`, `:18789`, `*:18555` | Node service, Python model service, automation/camera/gateway surfaces; owner mapping partly available in `listener_owners`. No blanket claim of safe authentication or public exposure. |
| Local auxiliaries | loopback 6390, 8079, 8787, 18792, 18554, emulator 5554/5555/5037/7681/6402/41507/46701/8554 | Redis, Node, emulator/ADB/gateway endpoints. Loopback limits inbound access; it does not isolate same-user processes. |
| SSH | `0.0.0.0:22`, `[::]:22` | Read-only tailnet SSH succeeded as Gloria. Effective `sshd -T` unavailable without host-key access; password/root-login policy remains unverified. |
| Discovery/media UDP | all-interface 1900/5353 and dynamic ports; DNS loopback/WSL interfaces | Service-discovery traffic observed. Router/Windows firewall, multicast scopes and external reachability not independently verified. |

**Proxy map:** the live `tailscale serve/funnel status --json` configuration is authoritative: **8443 proxies to `127.0.0.1:8500`**, 443 maps the MCP and named door/Alexa/speech paths, and 9443 maps 8612. The robot on 8404 is reachable through authenticated app proxy routes, not a direct Funnel 8443 mapping. A bind to `0.0.0.0` alone proves neither LAN nor internet reachability on this WSL host. Public configuration was observed, but no scan or separate public-client reachability test was made. Firewall rules could not be read unprivileged (`nft` rc 1, `iptables` rc 4).

Local model paths include the shim's Mac/Tailnet endpoint `100.79.177.103:1234` and Windows/WSL endpoint `172.18.16.1:1234`; these are model-routing configurations, not independently verified model-server authentication. Active local Lab accounting exists. External source paths name Anthropic, OpenAI, xAI, Google, Kie, Atlas Cloud, Brave, and hosted NVIDIA. OpenRouter/ElevenLabs support or historical references do not establish current use. Subscription-backed xAI and API-key billing must be distinguished in provider-side reviews.

## Findings

### F01 — Accepted default application credential

- **Classification / severity / exposure:** confirmed vulnerability, **Critical**, publicly configured app plus host interfaces.
- **Evidence:** `boundaries.json:default_credential_read_test`: wrong header 403, source default 200 on `/api/desktop/status`. `/home/gloria/Vintos/server.py` equals reviewed `bin/server.py`; app's `APP_SECRET` has a source default. No credential value is reproduced here.
- **Impact:** anyone possessing the source default can impersonate the app's shared authority, reaching sensitive control/data routes. No mutation or physical action was tested.
- **Remediation / files:** remove fallback in `bin/server.py`, align `scripts/robot_bridge.py`, app/mobile/device clients and service environment. Issue separate app/device/task credentials; maintain hardware STOP availability. Gloria must approve credential rotation and cutover.
- **Tradeoffs:** coordinated client migration avoids stranding legitimate automation; per-identity scopes allow continued autonomy.
- **Validation:** isolated tests for missing/default/wrong credentials; read-only production checks show rejection and existing valid clients still work, without printing credentials.
- **Rollback:** restore previous application release and client configuration through its rollback receipt; never restore an exposed default as a long-term recovery measure.

### F02 — Unauthenticated public realtime minting and private context

- **Classification / severity / exposure:** installed-source confirmed vulnerability, **Critical**, public app mapping. Exploit not executed.
- **Evidence:** installed `bin/server.py:voice_token` accepts no `Request`/credential, is explicitly in `PUBLIC_MUTATIONS`, and performs paid-provider token requests, private-context assembly, and a driver spawn. The purported LAN restriction is a comment/list reason, not an enforced check. The only HTTP middleware located is request correlation.
- **Impact:** obtaining paid realtime capabilities and personal instructions/context; repeated requests can generate sessions/process pressure. Aegis-side counting cannot observe subsequent direct phone-to-provider realtime traffic.
- **Remediation / files:** guard `/api/voice/token` with owner/device identity before any file/provider/process work; per-identity mint budget, session duration/output ceilings and concurrent-session cap; update mobile voice clients.
- **Tradeoffs:** device enrollment once; no restriction on normal speech or model choices.
- **Validation:** offline tests prove anonymous/invalid requests cause zero provider calls, zero context reads and zero spawns. Do not exercise this production route merely to test security.
- **Rollback:** revert route/client release together; retain provider-side financial caps throughout.

### F03 — WebSocket disclosure and unbounded clients

- **Classification / severity / exposure:** confirmed vulnerability, **High**, public app configuration.
- **Evidence:** one credential-free `/ws/telemetry` handshake returned 101. Installed telemetry/event handlers accept connections without auth. No per-identity connection quota was found. Event source paths reference private personal state; event payload contents were not read.
- **Impact:** private telemetry exposure; sustained clients consume connections, loop/file-watching work and bandwidth.
- **Remediation / files:** authenticate `/ws/telemetry`, `/ws/events` and their connection manager in `bin/server.py`; support short-lived, audience-bound WS tickets for browsers; add per-device/global connection caps and bounded outbound buffering.
- **Tradeoffs:** preserve normal app/device streams and reconnection bursts; avoid long-lived credentials in query strings.
- **Validation:** isolated anonymous/wrong-audience/expired rejection, known-device reconnect, connection-cap and disconnect cleanup tests.
- **Rollback:** restore server/mobile transport changes together through the deploy rollback.

### F04 — Provider attempts bypass shared reservations and monitoring

- **Classification / severity / exposure:** confirmed configuration/design weakness, **High**, local compromise and public routes capable of causing egress.
- **Evidence:** shared `compute_admission.reserve_paid` caps reservations per provider/day, not every network attempt or dollars. `claude_cache.ask`, shim passthrough and several direct paths do not reserve there. Completion logs exclude errors; retries can share one reservation. Observed historical successful Anthropic calls peaked at 10/minute in the last 24 hours, OpenAI at 1/minute; these are incomplete baselines, not maximum actual traffic.
- **Impact:** runaway spend before daily/retrospective fault detection; failure/retry storms undercounted.
- **Remediation / files:** this branch adds attempt metadata to **existing** `compute-ledger.jsonl` through `scripts/paid_http.py` at existing transports, the review alarm, manual pause, fault-loop input and deployment timer. See the transport-site inventory and remaining coverage limits below. Set provider-owned caps separately.
- **Tradeoffs:** synchronous durable accounting adds one append/fsync to paid sends; accounting failure holds that paid send. Local/free inference continues. No model changes or new paid analysis calls.
- **Validation:** isolated pause, failed-send accounting, retries, concurrency, cold-start/baseline limits, hourly delivery suppression and fault-loop tests; then owner-run isolated Aegis commissioning and ordinary-usage reconciliation.
- **Rollback:** deploy rollback restores transport sources and timer; preserve logs/receipts. Clearing a pause is a separate owner decision.

### F05 — Shared administrative identity and writable Docker socket

- **Classification / severity / exposure:** confirmed privilege weakness, **High**, local consequence of any Gloria-owned subsystem compromise.
- **Evidence:** `id` includes `docker` and `sudo`; `/var/run/docker.sock` is writable. Server, shim, Lab, plugin gateway, desktop tools and bench execute as uid 1000. Passwordless unrestricted sudo was not demonstrated.
- **Impact:** Docker daemon access ordinarily permits host-root-equivalent container operations; same-UID processes can access unrelated secrets/files or modify the monitor. No escalation was attempted.
- **Remediation / files/services:** isolate `vintos-server`, provider shim, plugin relay and experimental workers under dedicated identities; mediate narrowly scoped required operations. Review Docker membership/socket grants separately with Gloria. Keep Atelier's independent account/seals intact.
- **Tradeoffs:** allowlist the work Vintos actually needs; avoid a broad filesystem deny that cripples persistence or tools.
- **Validation:** dedicated scratch canaries across service identities; Docker socket inaccessible to network-facing services; normal admitted tool workflows still pass.
- **Rollback:** restore unit identity/mounts and scoped groups under explicit maintenance approval, with a verified interactive admin session retained.

### F06 — Missing resource and ingress limits

- **Classification / severity / exposure:** confirmed weakness, **High**, public app plus local APIs.
- **Evidence:** active server/shim have `MemoryMax=infinity`, `CPUQuotaPerSecUSec=infinity`, `NoNewPrivileges=no`, and no filesystem sandbox. Lab/plugin gateway have filesystem sandboxing but unlimited memory/CPU. Broker and shim read declared Content-Length without a maximum; broker uses `ThreadingHTTPServer`. WebSocket cap absent. No shared app ingress limiter was found.
- **Impact:** denial of service, disk/log growth, blocked responsiveness, background-spawn or paid-request amplification.
- **Remediation / files:** per-route/session limits in `bin/server.py`; body/time/concurrency bounds in `bin/vintos_claude_shim.py`, `broker/broker.py`; measured systemd drop-ins for listed active units; queue/lease limits for background creators.
- **Tradeoffs:** use separate foreground/background pools and generous bounded image/audio upload budgets; no blanket restriction of the local Lab minute loop. Proposed starting values are in the hardening plan, not enforced values.
- **Validation:** isolated malformed/chunked/oversize/slow-client and bounded concurrency tests, then ordinary-use peak measurements before service quotas are enabled.
- **Rollback:** remove only reviewed drop-ins or revert exact handler release; never disable existing gates to get a test through.

### F07 — Security detection depends on the monitored account

- **Classification / severity / exposure:** confirmed architectural weakness, **High**, host compromise.
- **Evidence:** active failure-watch and 15-minute fault-sweep timers exist; no dedicated active security/audit monitor found in sampled units/tools. Relevant audit/fail2ban/aide commands were absent. Rsyslog/journald exist, but inspected configs showed no enabled remote-forwarding action. This is not proof that no external security service exists.
- **Impact:** compromised account can modify call ledgers, disable alarms or erase local evidence. Overnight Mac fault thread depends on its app/session and ephemeral schedule.
- **Remediation / files/services:** reviewed `security_alarm.py`/timer covers new SSH addresses, key hashes, unit/cron changes and deployed-code drift, recording first to existing organ failures. Add root-owned independent host agent plus off-host append-only ingestion/heartbeat with credentials unavailable to Vintos.
- **Tradeoffs:** only actionable changes/rate anomalies notify; no repeated model investigation or unsolicited ordinary-activity alerts.
- **Validation:** local fixtures; missing-heartbeat alarm from a separate host; receiver retention/delete-denial tests. Do not send live test notifications without approval.
- **Rollback:** disable only the new monitor timer or remote forwarding integration under approval; retain existing fault sweep and collected evidence.

### F08 — Recoverability beyond deployment rollback is unverified

- **Classification / severity / exposure:** configuration weakness/unverified recovery, **High**, host loss or destructive compromise.
- **Evidence:** current release receipt names rollback and many local `.vintos/backups` entries exist; sampled deploy backups contain `restore.sh`. No full Vintos-state restore test, independently controlled encrypted off-host backup, immutable retention or independent credentials was verified. A dashboard snapshot is not a system-state backup.
- **Impact:** local rollback cannot recover a lost/corrupted host or guarantee recovery of agent state. A same-account attacker can threaten both production and local copies.
- **Remediation / files/services:** owner-approved backup inventory covering live workspace state, configurations, broker metadata, code manifests and recovery secrets, with Atelier sealing/custody preserved and content never exposed to this audit. Establish immutable off-host copies and a separate clean-host restore drill.
- **Tradeoffs:** backup IO scheduled away from interactive peaks; retain provider pause and sends disabled during recovery.
- **Validation:** independently restore to a disconnected clean environment, verify hashes/permissions/state continuity, measure RPO/RTO, and record date/result. Do not test by restoring over production.
- **Rollback:** backup addition is reversible; retain old backups until the replacement restore is proved. Never delete the last known good copy.

### F09 — Experimental/desktop child inherits broad environment

- **Classification / severity / exposure:** confirmed source weakness with unverified exploitability, **Medium**, authorized desktop/tool execution.
- **Evidence:** `scripts/desktop_agent.py:start` uses `child_env=os.environ.copy()`; default control runs as Gloria and can cross Windows desktop/browser boundaries. This differs from Lab wrappers that deliberately allowlist environment variables and from `isolated_exec` used by generated skills.
- **Impact:** a compromised planner/worker could gain credentials unrelated to the current task. Untrusted web/Slack/tool content reaching planning is not authorization to administer production.
- **Remediation / files:** allowlist child environment in `desktop_agent.py`; scoped task receipts and explicit target bindings for privileged adapters; isolated browser profile and Windows user for agent work. Verify actual desktop runtime before changing it.
- **Tradeoffs:** preserve display/runtime variables and required connector access; no removal of ordinary desktop autonomy.
- **Validation:** scratch sentinel secrets absent from child env; intended display/browser and stop/reduction actions remain available.
- **Rollback:** revert exact child environment list with no unrelated permission changes.

### F10 — Dependency inventory can report the wrong installed version

- **Classification / severity / exposure:** confirmed inventory weakness, **Medium**, supply-chain management.
- **Evidence:** distribution enumeration showed old duplicates (requests 2.31.0, urllib3 2.0.7, cryptography 41.0.7). **Actual imports** resolve user-site requests **2.34.2**, urllib3 **2.7.0**, cryptography **48.0.0**. Apt packages independently have security backports. Do not turn the older metadata into false exploitable CVE findings.
- **Impact:** false vulnerability claims or missed shadowed packages; system-wide/user-site environments are hard to reproduce. Repo has some pinned scientific dependencies, but not a complete locked production dependency set. `trust_remote_code=True` embedding paths exist without explicit revision in sampled source; this is execution trust, not a demonstrated malicious model.
- **Remediation / files:** inventory each service interpreter's resolved module files/version and distro revisions; generate hash-locked service environments/SBOM; pin model/code revisions; verify deploy receipts against an independently trusted manifest. No automatic major upgrades.
- **Tradeoffs:** validate CUDA/scientific compatibility separately; don't disturb an operating model stack merely to satisfy a scanner.
- **Validation:** clean locked-environment rebuild, import identity checks and relevant regressions; compare against authoritative advisories and reachable conditions.
- **Rollback:** keep prior environment/weights and deployment receipt; switch service interpreter back under approval.

Relevant reviewed examples: [requests TLS-session advisory](https://github.com/psf/requests/security/advisories/GHSA-9wx4-h78v-vm56), [requests netrc advisory](https://github.com/psf/requests/security/advisories/GHSA-9hjg-9r4m-mvj7), [urllib3 compressed-stream advisory](https://github.com/urllib3/urllib3/security/advisories/GHSA-2xpw-w6gg-jr37), [Ubuntu backport notice](https://ubuntu.com/security/notices/USN-8379-1). None is declared exploitable here merely from the stale metadata; `.netrc` was absent and a vulnerable TLS-session usage path was not proved.

## Existing protections that were actually observed

- Sampled credential files are 0600; `.ssh` and `.config/vintos` directories are 0700. This protects against other ordinary UIDs, not compromised processes using Gloria's identity.
- Sampled desktop and robot GETs rejected absent credentials; the protected-route default-credential finding remains independently serious.
- Plugin gateway has a token gate/body ceiling; public MCP health rejected anonymous access. Source controls still require isolated boundary regression and deployment identity verification per service.
- Atelier broker uses an independent service account and capability routes. Owner-exclusion behavior is a requirement, not a defect to bypass. No content-based validation was performed.
- Forge generated-skill test/invoke code routes through OS isolation and verification hashes. These are positive source findings, not proof every experimental runtime is isolated; active Forge is a distinct service from the initial generic unit probe.
- Deployment has manifests, pre-install tests, source hashing, receipt and rollback machinery. Receipt files are locally mutable and truncated hashes are not signatures.

## Audit completeness and unresolved boundaries

This is a substantive verified first-pass audit, **not certification of every endpoint, host or account**. Root SSH/firewall effective settings, root crontab, Windows host firewall/tasks/Defender, Mac services/launch agents, router forwarding, complete tailnet ACLs, installed app scopes/provider billing settings, off-host storage policy, full Git-history secret absence, all model/plugin provenance, and a clean-host restore remain unverified. No account-owner settings were changed.

The alarm counts identified Python and shell transport invocations to the registered provider hosts, including errors, explicit retries and polling. It does not constitute a packet meter for SDK-internal retries/redirects, separately installed/untracked scripts, the browser's direct realtime session after token minting, other hosts, or a root-compromised machine. These coverage gaps must be reconciled against provider-side usage before claiming **every outbound paid call** is covered. The paused marker holds instrumented Aegis calls; it cannot revoke already-issued remote sessions or stop a caller bypassing the instrumented path. Provider-owned caps and scoped non-admin runtime identities remain necessary.
