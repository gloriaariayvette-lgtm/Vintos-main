# House credential cutover (25 October)

Branch `claude/house-auth-cutover-2026-10-25`, built on the reviewed repairs and on the earlier
`codex/security-auth-cutover` candidate (merged, then completed). Nothing here has been deployed,
rotated or restarted. Gloria sets the credential and runs the deploy.

## What changed

- **One credential, from the environment only.** `VINTOS_SECRET` is read from the service
  environment (`~/.vintos/vintos.env`). There is no built-in value anywhere in the repository or in
  any served file. A value that is unset, shorter than 32 characters, padded with whitespace, or the
  retired value counts as unset.
- **Fail closed, still start.** With no usable credential the house server and the robot bridge still
  start and their public routes still answer; every private route answers 503 and the log has one line
  starting `[house] VINTOS_SECRET is ...`.
- **Every method, every router, every socket.** `house_auth.py` is installed as the outermost guard of
  the house app. It is default-deny: any route not on a reviewed public list needs the credential,
  whatever the method (GET, POST, PATCH, DELETE ...), including the `server_domains` routers
  (landings, journal, galleries, music, humor/wants), `watch_routes`, the `/static` mount, the API
  schema pages, and both WebSockets (`/ws/telemetry`, `/ws/events`), which close before accepting.
  A route added later is private until someone lists it.
- **Handler checks stay as a second layer**, now constant-time and never true without a credential.
  `POST /api/landings`, `/api/voice/session-end`, `/api/voice/call-log` and `/api/music/share` now
  check the credential in their handlers too. The stratagem owner controls (`/api/stratagem/owner/*`)
  add the owner token only after the real credential is presented in the header; a session cookie, a
  Watch bearer or a media ticket does not reach them.
- **How clients authenticate (from the candidate, unchanged in design).** The app shell
  (`/app/`) is public HTML/JS with no credential in it. On first use it shows "Connect to Vintos";
  the credential typed there is checked by `POST /api/auth/session` and kept on the device
  (browser `localStorage`, or the native app's key store). Every house request then carries the
  `X-Vintos-Secret` header. The session endpoint also returns a one-hour HttpOnly, Secure,
  SameSite=strict cookie for reads, 60-second tickets for the two WebSockets (sent as a
  subprotocol, never in the URL), and a 15-minute media ticket for `<audio>`/`<img>` links.
- **Links pushed to her phone.** A clip, a still, or an architecture question sent by push carries a
  ticket for exactly that one path (`access_token=`, valid 7 days). It opens that file or page and
  nothing else. The guard removes `access_token` from the request before it is logged.
- **Existing query credential kept, noted.** The avatar stage review pages on the tailnet
  (`/avatar/stage/...?s=`) still accept the credential in the query string, because those pages are
  opened that way. It reaches the access log; no new path uses it.
- **No deploy gate.** The candidate's prepare/activate/finalize tooling and its deploy preflight (which
  made every deploy refuse until a cutover was prepared) are removed: with fail-closed startup the
  deploy is safe to run before or after the credential is set.

## Public routes (the reviewed list)

Reads: `/` and `/app/` (shell), `/app/manifest.json`, the client scripts
(`stratagem_voice.js`, `client_lifecycle.js`, `avatar-bundle.js`, `house_auth_client.js`),
`/avatar-models/*` and `/models/*` (3D model files), `/api/client/capabilities` (route names only),
`/ea` (one-time hashed link), `/api/food-order/review/{token}` and `/api/gloria/asks/{qid}`
(each item's own expiring token, checked by its handler).

Writes: `/api/auth/session` (checks the credential itself), `/ea/decide`,
`/api/food-order/review/{token}/approve`, `/api/gloria/asks/{qid}/decide`,
`/api/lab/asks/{ask_id}/decide` (each item's own token), `/api/guestbook/witness` (presence only),
`/api/gcs`, `/api/gcs/clear`, `/api/hardware/button` (her hardware buttons, which carry no header),
`/api/ring/live`, `/api/ring/sleep` (ring bridge with its own optional bearer,
`~/.vintos/.ring-token`; create that file to close them).

Watch paths (`/api/watch/*` except `/api/watch/live`, plus `/api/voice/token` and
`/api/voice/framing`) take the Watch's own bearer instead of the credential.
Browser forms `/aq/answer` and `/api/video/hero` also take her session cookie.
`broker/tests/test_house_route_guard.py` fails if this surface changes without review.

## Which clients need the credential

| Client | What it needs | How it gets it |
|---|---|---|
| Web app (`/app/` over Funnel) | the credential once per browser | "Connect to Vintos" dialog; paste it |
| iPhone app (Capacitor, `vintos-app`) | a build with the enrollment client | rebuild from the companion branch named in `docs/security-auth-rollout.md` (vintos-app `6056939`), then the same dialog. Older builds get 401 until rebuilt. Not verified in this branch. |
| Apple Watch | nothing new | keeps its own bearer; media links it is offered are signed for it |
| Mac ReelRoom helper (`dev.vintos.reelroom-cast`) | the new value | it reads the server's running environment over SSH **once at start** and keeps it in memory. It does not re-read. **Restart it after the house server has restarted.** |
| Robot bridge (`vintos-robot-bridge`) | the same value | reads `VINTOS_SECRET` from its environment (`robot.env`), else from `~/.vintos/vintos.env`. Nothing to add unless `robot.env` already names it (then it must match). |
| Pi robot client | the same value | `bin/robot-pi-repoint.sh` (only if the Pi is in use), sent over SSH stdin |
| Cron and local callers (wants-router, the server's own calls) | the same value | read `~/.vintos/vintos.env` through `env_file` |
| MCP `:8625` | unchanged | its own bearer |
| Browser pages (`/dashboard`, `/map`, `/calendar`, `/aq`, `/video-hero`, ...) | an enrolled browser | open `https://aegis.tailaa3de5.ts.net:8443/app/` and connect first (the session cookie lasts an hour, https only). Buttons on those pages that post without the header will be refused; not reworked here. |

## Gloria's steps

All on Aegis unless marked Mac. Nothing below prints the credential.

1. **Back up the env file, then write a new credential into it** (mode 600, value never shown):

   ```sh
   cp -p ~/.vintos/vintos.env ~/.vintos/vintos.env.bak-$(date +%Y%m%d-%H%M%S) && chmod 600 ~/.vintos/vintos.env.bak-*
   python3 - <<'PY'
   import os, re, secrets
   p = os.path.expanduser("~/.vintos/vintos.env")
   keep = [l for l in open(p).read().splitlines() if not re.match(r"\s*(export\s+)?VINTOS_SECRET=", l)]
   tmp = p + ".new"
   fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
   with os.fdopen(fd, "w") as f:
       f.write("\n".join(keep + ["VINTOS_SECRET=" + secrets.token_urlsafe(48)]) + "\n")
   os.replace(tmp, p); os.chmod(p, 0o600)
   print("VINTOS_SECRET written; %d other lines kept" % len(keep))
   PY
   ```

2. **Deploy** (after this branch is reviewed and merged into the deploy branch), exactly:

   ```sh
   cd ~/Vintos-main && [ -z "$(git status --porcelain)" ] && git checkout -q claude/vintos-avatar-ui-redesign-br5lt4; python3 scripts/aegis_sync.py --from claude/device-visuals-2026-10-13 --deploy 2>&1 | tee ~/deploy-latest.log
   ```

   It runs every suite, installs, and restarts the house server (`vintos-server`) and the robot bridge
   (`vintos-robot-bridge`) among its usual units; both then read the new value. If the deploy runs
   before step 1, the private routes answer 503 until step 1 is done and the two units restart:
   `systemctl --user restart vintos-server vintos-robot-bridge`.

3. **Mac: restart the ReelRoom helper** so it fetches the new value:

   ```sh
   launchctl kickstart -k gui/$(id -u)/dev.vintos.reelroom-cast
   ```

   (Its script still carries its own fallback to the retired value; that fallback is now simply
   refused. Remove it on the Mac when convenient.)

4. **Enroll the phone.** On the Mac, copy the value to the clipboard without showing it, paste it into
   "Connect to Vintos" on the phone (Universal Clipboard), then clear the clipboard:

   ```sh
   ssh gloria@100.72.225.119 "sed -n 's/^VINTOS_SECRET=//p' ~/.vintos/vintos.env" | tr -d '\n' | pbcopy
   printf '' | pbcopy     # after pasting
   ```

   For the iPhone app, install the rebuilt companion app first (its existing Xcode workflow).

5. **Pi, only if the robot client is in use:**

   ```sh
   VINTOS_SECRET="$(sed -n 's/^VINTOS_SECRET=//p' ~/.vintos/vintos.env)" bash ~/Vintos-main/bin/robot-pi-repoint.sh 192.168.1.89
   ```

   Confirm the Pi's address first; the script backs up and restarts that one client.

6. **Verify, status codes only:**

   ```sh
   H=https://aegis.tailaa3de5.ts.net:8443
   for p in /api/chat/history /api/inner-life /api/memory/search /api/voice/pending-speech /openapi.json /static/app.html; do
     curl -s -o /dev/null -w "$p %{http_code}\n" "$H$p"; done                               # each 401
   curl -s -o /dev/null -w "POST landings %{http_code}\n" -X POST -H 'Content-Type: application/json' -d '{}' "$H/api/landings"   # 401
   curl -s --http1.1 -o /dev/null -w "ws events %{http_code}\n" -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
     -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$H/ws/events"   # 403, not 101
   curl -s -o /dev/null -w "app shell %{http_code}\n" "$H/app/"                              # 200
   curl -s -o /dev/null -w "with credential %{http_code}\n" \
     -H @<(printf 'X-Vintos-Secret: %s\n' "$(sed -n 's/^VINTOS_SECRET=//p' ~/.vintos/vintos.env)") http://127.0.0.1:8500/api/chat/history   # 200
   journalctl --user -u vintos-server -n 200 --no-pager | grep -c '\[house\] VINTOS_SECRET is'   # 0
   ```

   Then ordinary use: the app connects, the Watch checks in, a ReelRoom cast reaches the house. No test
   messages, notifications or paid calls are needed.

## Rollback

- **Preferred: roll forward.** A client that fails needs the credential (steps 3-5), not the old code.
- **Code rollback:** `bash ~/.vintos/deploy/<backup>/restore.sh`, printed in the deploy log. Keep the new
  `VINTOS_SECRET` line: the previous code also reads it, so its guarded writes stay behind the new
  value. Be aware the previous code serves its private reads and sockets without a credential again;
  roll forward as soon as the cause is fixed.
- **Credential rollback:** restore the env backup from step 1 and restart `vintos-server` and
  `vintos-robot-bridge`. With this branch deployed that makes every private route answer 503 (it
  never falls back to a built-in value). Do not reintroduce the retired value.

The retired value is in public git history; rotating to a new random value is the fix, and history
does not need rewriting.
