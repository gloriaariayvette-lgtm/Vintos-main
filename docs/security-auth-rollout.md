> **Superseded on 25 October by [house-auth-cutover.md](house-auth-cutover.md).** The design below
> (enrollment, sessions, tickets, Watch media) is kept and completed there; the prepare/activate/finalize
> scripts and the deploy preflight were removed, because fail-closed startup makes them unnecessary.
> This page is kept for its companion-app reference and design notes.

# AUTH-01 — one coordinated change for Gloria's approval

**Prepared in review source only. Do not run this cutover before main-thread review and Gloria's yes.** No live credential has been generated or rotated by this audit. No service was restarted. Funnel stays on, including the Watch's existing public house URL. The existing `/api/voice/token` fix from `a6e28e9e` is merged unchanged.

Review package: main repository `codex/security-auth-cutover`, built on standalone `codex/security-alarms` (contains alarm commit `3a1a3624` and merged deploy source), plus companion [vintos-app `6056939`](https://github.com/gloriaariayvette-lgtm/vintos-app/commit/6056939). Both require one coordinated approval; pushing either branch does not deploy it.

## Proposed behavior and files

| Boundary / caller | Reviewed change | Operator acceptance |
|---|---|---|
| `bin/server.py`, `scripts/house_auth.py`, `bin/house_auth.py` | Refuse missing, short, whitespace-padded or source-default identity before serving. All GET/HEAD reads require owner identity except the explicit public assets/capabilities and existing scoped capabilities. `/ws/telemetry` and `/ws/events` require owner header or a 60-second audience-bound ticket before accept. | Anonymous private GET/HEAD → 401; anonymous socket closes 4401; correct enrolled clients work. |
| `scripts/robot_bridge.py` | Environment-only required identity; no source fallback. | Existing independent physical STOP/reduction behavior stays; no physical actions in tests. |
| `bin/wants-router.py` (import aliases), `bin/server_domains/humor_wants.py` | Same identity from environment; cron callers use existing `env_file` parser to load canonical environment when absent. | Autonomous wants/humor continue with canonical file, with no new model calls or model changes. |
| `clients/mobile/index.html`, `clients/mobile/house_auth_client.js`; app `vintos-app/src/index.html`, `src/house_auth_client.js` | Runtime host environment or owner enrollment; authenticate existing HTTP calls, refresh session/tickets, reconnect sockets, sign media links. Long-lived identity never put in URL. | Browser/native foreground normal use; disconnected or stale enrollment prompts renewal. |
| App `vintos-app/src/runners/outreach.js` | Its environment first, otherwise foreground-enrolled native CapacitorKV; no fallback. | Owner enrollment must reach background runner; background outreach reads succeed without test notifications. |
| `scripts/watch_routes.py` | Keep the independent Watch bearer. Sign only the media links already offered to that authorized Watch; exact path, one-hour expiry. No Watch key/build/endpoint changes. | Existing Watch data, voice authorization and offered media continue; unauthenticated media fails. |
| `scripts/deploy-atelier.sh` | Manifest helpers and actual running server/client/domain destinations; explicit cutover preflight after dry-run and tests; activate environment/drop-ins only for an approved cutover. | Deployment receipt hashes include identity drop-ins; no automatic first rotation. |
| `scripts/house_auth_rollout.py`, `scripts/house_server_guard.py` (removed 25 October) | Owner-run on-Aegis random generation, private snapshots, transactional environment configuration, persistent guard and guarded rollback. | Files 0600, directories 0700; secret never printed; failed activation restores previous configuration. |
| `bin/robot-pi-repoint.sh` | Additional discovered remote caller: receive credential over SSH stdin, use environment rather than embed it in Python; install Pi environment/drop-in only when owner explicitly runs script. | Pi configuration/runtime was not inspected or changed. Its enrollment is a separate required hardware acceptance step if that caller is active. |

The app repository also contains inactive top-level server/wants copies and HTML backups inside Capacitor's `src` directory. Only the known source-default literal was removed there, because those backup assets otherwise get packaged publicly. Git history still contains the old default; deleting history is not a substitute for rotation.

Browsers cannot read Aegis's process environment. Aegis generates the random value, Python services receive `VINTOS_SECRET` through environment files, and owner enrollment supplies the same runtime value to foreground/native-background clients. Do **not** publish a generated `config.js` containing it. Browser enrollment uses localStorage and native runner enrollment uses CapacitorKV; these remain sensitive to same-origin script compromise/device access. Dedicated per-client revocable identities are a subsequent improvement, not silently bundled into this migration.

Both streams check admission at connection establishment. Tickets expire after 60 seconds for new connections; existing authenticated connections stay responsive. Reconnect obtains a fresh ticket. Read cookies expire after an hour (Secure, HttpOnly, SameSite Strict); explicit authenticated fetch renews them and media tickets. Owner media tickets last 15 minutes and are confined to media paths. Watch media links last an hour and bind one path. Query capabilities are stripped before application/access logging; subprotocol tickets never enter URLs. Do not enable raw header/debug dumps. All protected GET/HEAD responses are marked private, no-store before they leave the guard.

The complete GET list and response descriptions are in [security-public-get-routes.md](security-public-get-routes.md). This is source evidence with live registration caveats, not a claim that every conditional subsystem is currently mounted.

## Rollout and rollback

See [house-auth-cutover.md](house-auth-cutover.md).
