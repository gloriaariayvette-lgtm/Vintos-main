# Clients: what talks to his server, where it lives, and whether it is active

Review item 25 (2026-09-10). Nothing here was moved or deleted; historical clients stay where they are until their activation is established. Status is what the code in this checkout and the server's routes say, not a plan.

| Client | Lives in | Entry point | Served by his server? | Status |
|---|---|---|---|---|
| The phone app (Capacitor, iOS) | `vintos-app` repository on the Mac (branch `claude/vintos-avatar-ui-redesign-r9639u`), not in this checkout | `src/index.html` → generated iOS resources | No; it calls `http://<aegis>:8500/api/*` with `X-Vintos-Secret` | **active** - chat, avatar, voice, calls, camera, Mischief tab, body tab, Study tab |
| The avatar overlay | `avatar/overlay.html` in this checkout | opened directly in a browser; reads `avatar/clips/manifest.json` | Not mounted by a route in `bin/server.py` (the server mounts `/static` from `bin/website`, `/avatar-models`, `/models`) | **archived / unknown** - no route serves it; keep until activation is established |
| The website static dir | `bin/website` (absent in this checkout) | `GET /` and `/static/*` in `bin/server.py` | Yes, when the directory exists on the host | **unknown** - the directory is not in the repository; the route registers only if it exists |
| The map page | `bin/server.py` `GET /map`, `GET /api/map/*` | in-server HTML | Yes | **active** |
| Plithra ReelRoom page | `plithra-app` repository on the Mac (`src/reel.html`), self-hosted | WHO toggle: Velaris (8400) / Vintos (8500) with the secret typed once | Yes - `/api/game/reelroom/*`, `/api/game/screenshot` | **active** (merged to main on the Mac by Gloria, 9 September) |
| The body tab / robot voice | phone app tab polling `/api/robot/voice/latest`; the Pi client at `~/vintos-pi` on the Pi | server proxies chat/state/voice to the bridge on 8404 | Yes (proxy) | **active on the server; the Pi still points at the Mac** until `bin/robot-pi-repoint.sh` is run |
| Legacy `/chat` and `/state` callers | none found in this checkout; the review named them in historical client code outside the repository | - | The server has no `/chat` or `/state` route; only `/api/...` | **retired at the server** - a historical client calling them gets 404 |
| Agent room window | `agent-room/window/index.html` served by `agent-room/static.mjs` on 8788 | browser | No (its own static server) | **active on review days** |
| Study tab | phone app → `/api/study/*` | - | Yes | **active** |

What is *not* here: the Mac render server for avatar scenes, the Kie/Suno and Gemini/Grok generation endpoints, and Home Assistant are services he calls, not clients of him. The vendor graphics bundle the avatar stage uses is packaged in the phone app repository; see `docs/graphics-bundle.md`.
