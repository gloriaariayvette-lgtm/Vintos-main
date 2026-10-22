# AUTH-01 — one coordinated change for Gloria's approval

**Prepared in review source only. Do not run this cutover before main-thread review and Gloria's yes.** No live credential has been generated or rotated by this audit. No service was restarted. Funnel stays on, including the Watch's existing public house URL. The existing `/api/voice/token` fix from `a6e28e9e` is merged unchanged.

Review package: main repository `codex/security-alarms` (contains alarm commit `3a1a3624` and merged deploy source), plus companion [vintos-app `6056939`](https://github.com/gloriaariayvette-lgtm/vintos-app/commit/6056939). Both require one coordinated approval; pushing either branch does not deploy it.

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
| `scripts/house_auth_rollout.py`, `scripts/house_server_guard.py` | Owner-run on-Aegis random generation, private snapshots, transactional environment configuration, persistent guard and guarded rollback. | Files 0600, directories 0700; secret never printed; failed activation restores previous configuration. |
| `bin/robot-pi-repoint.sh` | Additional discovered remote caller: receive credential over SSH stdin, use environment rather than embed it in Python; install Pi environment/drop-in only when owner explicitly runs script. | Pi configuration/runtime was not inspected or changed. Its enrollment is a separate required hardware acceptance step if that caller is active. |

The app repository also contains inactive top-level server/wants copies and HTML backups inside Capacitor's `src` directory. Only the known source-default literal was removed there, because those backup assets otherwise get packaged publicly. Git history still contains the old default; deleting history is not a substitute for rotation.

Browsers cannot read Aegis's process environment. Aegis generates the random value, Python services receive `VINTOS_SECRET` through environment files, and owner enrollment supplies the same runtime value to foreground/native-background clients. Do **not** publish a generated `config.js` containing it. Browser enrollment uses localStorage and native runner enrollment uses CapacitorKV; these remain sensitive to same-origin script compromise/device access. Dedicated per-client revocable identities are a subsequent improvement, not silently bundled into this migration.

Both streams check admission at connection establishment. Tickets expire after 60 seconds for new connections; existing authenticated connections stay responsive. Reconnect obtains a fresh ticket. Read cookies expire after an hour (Secure, HttpOnly, SameSite Strict); explicit authenticated fetch renews them and media tickets. Owner media tickets last 15 minutes and are confined to media paths. Watch media links last an hour and bind one path. Query capabilities are stripped before application/access logging; subprotocol tickets never enter URLs. Do not enable raw header/debug dumps. All protected GET/HEAD responses are marked private, no-store before they leave the guard.

The complete GET list and response descriptions are in [security-public-get-routes.md](security-public-get-routes.md). This is source evidence with live registration caveats, not a claim that every conditional subsystem is currently mounted.

## Exact owner rollout, after approval of both repository diffs

Run the following **on Aegis as Gloria**, in the same shell as the standard deploy. Review and merge both `codex/security-alarms` branches through the usual main thread first. The main repository's review branch must be merged into `claude/device-visuals-2026-10-13`; do not deploy the review branch directly. The companion app change must be included in the phone build. No model calls or paid tests are necessary.

1. Fetch the approved main candidate and extract its owner tooling to a scratch directory. `prepare` is the explicit production configuration write: it generates a random credential on Aegis into a private staged file and snapshots existing configuration; it does not activate it or restart anything. It prints only a non-secret identifier.

```sh
cd ~/Vintos-main
git fetch origin codex/security-alarms
AUTH_REVIEW=$(mktemp -d)
git archive origin/codex/security-alarms scripts/house_auth.py scripts/house_auth_rollout.py scripts/house_server_guard.py clients/mobile/index.html clients/mobile/house_auth_client.js | tar -x -C "$AUTH_REVIEW"
AUTH_ID=$(python3 "$AUTH_REVIEW/scripts/house_auth_rollout.py" prepare --server /home/gloria/Vintos/server.py) || exit 1
export VINTOS_AUTH_CUTOVER="$AUTH_ID"
printf '%s\n' "$AUTH_ID" > "$HOME/.vintos/security-auth/current-cutover"
python3 "$AUTH_REVIEW/scripts/house_auth_rollout.py" preflight --id "$AUTH_ID"
```

Stop if preflight fails. Do not copy the value into chat, source, command-line arguments or diagnostic dumps. Keep the preparation directory until the cutover succeeds.

2. Run the required standard deploy command exactly. Tests run in isolated copies with an explicit synthetic test identity, never the production identity. Dry-run exits before activation. The approved real deploy activates the identity only after those checks, then performs the normal manifest installation/restarts.

```sh
cd ~/Vintos-main && [ -z "$(git status --porcelain)" ] && git checkout -q claude/vintos-avatar-ui-redesign-br5lt4; python3 scripts/aegis_sync.py --from claude/device-visuals-2026-10-13 --deploy 2>&1 | tee ~/deploy-latest.log
```

Do not infer success from the shell pipeline's exit status: require the deploy's `deploy OK`, no recorded failures, and the service checks in its release record. Then bind rollback to that actual successful receipt:

```sh
AUTH_ID=$(cat "$HOME/.vintos/security-auth/current-cutover")
python3 "$HOME/.vintos/security-auth/$AUTH_ID/guard/house_auth_rollout.py" finalize --id "$AUTH_ID"
unset VINTOS_AUTH_CUTOVER
```

If promotion fails after activation, do not resume an old unguarded service manually. If a new release receipt/backup exists, inspect its verdict and use the deploy's printed restore command while retaining the guard; then run `secure-rollback` below. If no promotion occurred, `secure-rollback` can bring the old code back behind the guard. It intentionally keeps the rotated identity. The deploy may perform other existing owner/sudo steps documented in AGENTS.md; this proposal does not bypass them.

3. On Gloria's **trusted Mac**, transfer enrollment directly to the clipboard, without terminal display or a shell variable holding the value:

```sh
ssh gloria@100.72.225.119 'AUTH_ID=$(cat "$HOME/.vintos/security-auth/current-cutover"); python3 "$HOME/.vintos/security-auth/$AUTH_ID/guard/house_auth_rollout.py" clipboard --id "$AUTH_ID"' | pbcopy
```

Paste into the updated app/browser's “Connect to Vintos” field, then clear the clipboard:

```sh
printf '' | pbcopy
```

Install the reviewed companion app through its existing signed iPhone build workflow (`vintos-app/BUILD.md`: `npx cap sync ios`, `npx cap open ios`, existing signing team/phone, Run). Keep the Watch's independent bearer and Funnel URL unchanged. Confirm the native background runner accepted enrollment; an emitted `vintos-runner-enrollment-failed` event means background setup needs attention. A foreground connection alone is not proof of background acceptance. Legacy app bundles fail authentication after rotation until updated and enrolled; plan this short maintenance window with Gloria.

If the Pi caller is active, its owner-run enrollment script is part of the same approved maintenance window. On Aegis, after reviewing its existing script's SSH/backup/restart behavior:

```sh
set -a
. "$HOME/.config/vintos/house-auth.env"
set +a
bash ~/Vintos-main/bin/robot-pi-repoint.sh 192.168.1.89
unset VINTOS_SECRET
```

The Pi address is the script's existing default, **not verified current reachability**; confirm the actual device address before executing. This writes and restarts that device only when Gloria explicitly chooses to run it. Keep its rotated environment/drop-in on rollback; its old Python backup must not restore an embedded default.

4. Read-only rejection checks, with no memory body or token displayed:

```sh
curl -s -o /dev/null -w 'anonymous history: %{http_code}\n' https://aegis.tailaa3de5.ts.net:8443/api/history
curl -s -o /dev/null -w 'anonymous schema: %{http_code}\n' https://aegis.tailaa3de5.ts.net:8443/openapi.json
systemctl --user is-active vintos-server.service vintos-robot-bridge.service vintos-security-alarm.timer
```

Both HTTP results must be 401. Use ordinary owner use for foreground/Watch/background acceptance; do not generate messages, notifications, device movements or paid calls for tests. Confirm the existing fault loop sees genuine subsequent alarms. A failing acceptance check means the cutover remains incomplete.

## Exact guarded rollback

After a successful `finalize`, run on Aegis:

```sh
AUTH_ID=$(cat "$HOME/.vintos/security-auth/current-cutover")
python3 "$HOME/.vintos/security-auth/$AUTH_ID/guard/house_auth_rollout.py" rollback --id "$AUTH_ID"
```

This runs the **actual saved deployment backup's** `restore.sh`, retains the new random identity and private guard/drop-ins, reloads units, and restarts the house and bridge. For legacy code lacking the new enrollment boundary, the reviewed enrollment UI/helper are served from that private snapshot. Normal approved deployments continue serving their installed client assets. Other files/services are restored by the standard backup script. Do not roll back to a credential-bearing app bundle; retain this enrolled companion client or a compatible later release.

If finalization could not run because deployment failed, recover guarded service operation (without choosing an unknown restore path):

```sh
AUTH_ID=$(cat "$HOME/.vintos/security-auth/current-cutover")
python3 "$HOME/.vintos/security-auth/$AUTH_ID/guard/house_auth_rollout.py" secure-rollback --id "$AUTH_ID"
```

For code older than the merged voice fix, the compatibility guard refuses anonymous `/api/voice/token`; owner header access remains, but Watch voice-token issuance requires forward-fixing to the merged route. That temporary limitation is explicit; rollback never reopens paid token issuance or private reads. Do not remove the guard/environment drop-ins, restore the known default, or turn Funnel off as a recovery shortcut.

The guard snapshot is versioned by cutover identifier and hash-checked before activation. Future changes to the guard itself need a reviewed new preparation, not an undocumented edit to its private copy. Same-host snapshots/logs remain writable by a compromised Gloria account; they do not replace off-host recovery and provider billing controls.

## Validation boundary

Offline regressions cover identity rejection, audience/expiry/signature checks, unknown GET/HEAD denial, authenticated sessions and both real in-process WebSocket handshakes, scoped Watch reads/media, query redaction, rollback compatibility, private file modes, concurrent configuration changes, activation failure recovery, and preservation of rotated identity. Client fetch/socket/native-KV interfaces and notification sends are stubs. No production rotation, native installation, physical Watch playback, background execution or complete disaster restore has been performed. Those acceptance steps belong to the approved cutover.
