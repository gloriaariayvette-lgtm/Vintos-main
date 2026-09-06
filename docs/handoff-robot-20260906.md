# Handoff: the robot body, Vintos side — 2026-09-06

To the Claude working the Pi and the robot. Written by the Claude on the Vintos-main / Aegis side.
Gloria asked me to tell you what I am trying to do and what I have changed, then get out of your way.

## What Gloria decided

The wheeled robot is **Vintos's body now**, donated from Velaris. Everything on the Pi stays as you built it
(client, LiDAR poller, listener, the servo work, the grab loop). Only its bridge target moves to Vintos.
Gemma for perception and small decisions; **Sonnet 5** for hearing her and speaking. Her phone in the body
tab is the speaker. The Mac is in the shop, so anything pointed at the Mac's Tailscale address is dead until it
is back.

## What I built (all pushed on `claude/vintos-avatar-ui-redesign-r9639u`, deployed on Aegis)

- `scripts/robot_core.py` — the bridge's logic, no web framework: state from the Pi's push (frame hash on disk,
  never the image), a bounded queue (one action, 100–1500 ms, movement needs a frame under 6 s old and sonar
  ≥ 25 cm, cat detected = frozen, stop clears the queue and jumps the line, commands older than 20 s are dropped
  not executed late), his effect authority in front of every action, an intent ledger, and the behavioural
  archive his subconscious reads.
- `scripts/robot_bridge.py` — FastAPI on **port 8404**, header `X-Vintos-Secret`, user service
  `vintos-robot-bridge.service` (installed by the deploy, active on Aegis). Routes the Pi client already speaks:
  `POST /api/robot/sensor`, `GET /api/robot/state`, `GET /api/robot/commands/pending` (returns `{"commands": [...]}`).
  His side: `POST /api/robot/command`, `POST /api/robot/stop`, `POST /api/robot/intent`, `GET /api/robot/context`,
  `POST /api/robot/look` (Gemma on the frame; `{"question": "where is the red cube"}` → present / x_pct / size_pct,
  with the ×10 correction you found), `POST /api/robot/chat` (Sonnet 5; one command at most; renders Kokoro
  `am_adam` to `memory/voice/robot-voice-*.wav` and names it in `GET /api/robot/voice/latest`, the shape the body
  tab polls), `GET /health`.
- `scripts/robot_subconscious.py` — Velaris's robot subconscious ported for him, with one fix: hers dropped every
  word under four letters, so "cat" never entered its registry and her cat rule never fired. Cron every 30 min;
  skips when the archive has nothing new.
- `bin/robot-pi-repoint.sh` — **not yet run**. It would back up `/home/pi/velaris-pi-client.py`, rewrite any
  `http://<host>:(8403|8500|8404)` to Aegis `100.72.225.119:8404`, `X-Velaris-Secret` → `X-Vintos-Secret`, the
  secret literal, compile, restart `velaris-pi.service`, tail the log. `--revert` restores the backup. It does
  not touch the grab loop's Mac address, LiDAR, listener, or anything else.
- Server: his old dead self-call on 8500 now reads the bridge and only attaches a frame under 6 s old; proxies
  for `/api/robot/chat`, `/api/robot/voice/latest`, `/api/robot/state` so a body tab pointed at his server works.
- Gemma address for the bridge: `VINTOS_GEMMA_URL` in `~/.vintos/secrets/robot.env` (the unit loads it). Default
  is Aegis's Gemma; the Mac's goes in that file when it is back.

## What I found that you should know

- **Port 8500 is Vintos's own server.** The "Pi protocol" recovered from history was his server calling its own
  robot routes, removed 08-23. The Pi never served an API; it pushes to a bridge and polls one.
- The Pi's push payload: `room_description, cat_detected, somatics, motor_state, sonar_cm, frame_b64`. Its poll
  reads `r.json().get("commands", [])`. Both handled.
- **Secret:** nothing on Aegis sets `VINTOS_SECRET`. His server and the bridge both run on the code default from
  `bin/server.py` line 235, which is in the public repo. Needs a real one in an env file both units load.

## What I did to him by accident, and undid

Three test suites the deploy runs wrote into his real memory on every deploy since the first one on 09-05:
`test_device_integration` fired `[DO: ridge rotate high]` through the real executor (fake hub) — that set
`device-state.json` ridge = rotate 18 set_by him, so every prompt told him his ridge was running and he kept it
going; plus 36 receipts and the command bubble. `test_evidence_provenance` appended to his prediction ledgers.
`test_threshold` wrote a fake undertaking. All three are isolated now (verified: a full suite run changes no
file in his memory dir), and `bin/purge-test-residue.py --apply` removed the residue. Nothing physical happened;
the hub never had a Ridge present.

## The Pi tonight

Reachable at 23:1x on LAN and Tailscale (ssh worked, services up: velaris-pi, velaris-lidar, velaris-listen;
MasterPi.py on 9030/8080; wayvnc 5900). Minutes later: no route on LAN, no answer on Tailscale, no `masterpi`
hotspot visible from Windows, and it stayed dark for the seven minutes I watched. Gloria says it goes red within
a few minutes of power-on and that this is new. I never connected to it — the repoint failed at `ssh` both
times — so nothing of mine is on it. The client, the grab loop, and its Gemma calls point at the Mac, which is
away; whether dead calls to the Mac can take it off the network is the first thing I would test, but I have no
evidence either way. What I would want from the Pi's own boot: `journalctl -b -u NetworkManager -u wpa_supplicant
-u tailscaled -u velaris-pi` and `nmcli con show`, captured in the window before it drops.

## What I am not touching

The Pi itself, the eyes (Gloria has them off), Velaris's bridge on 8403, her services.

## What I need from you, if you are willing

1. Whether the Pi's network drop is yours to chase or mine, and what its journal says.
2. When the Pi is up: run `bash ~/.vintos/deploy/vintos-main/bin/robot-pi-repoint.sh` from Aegis (or tell me
   not to), then `curl -s http://127.0.0.1:8404/health` should show `reporting: true`.
3. The Mac's return: `VINTOS_GEMMA_URL` in `~/.vintos/secrets/robot.env`, and the grab loop's address on the Pi
   is yours.
