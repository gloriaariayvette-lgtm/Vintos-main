---
name: desktop-control
description: "Vintos's hands on Aegis's Windows desktop: a fresh screenshot, one Gemma decision, one bounded mouse or keyboard action, repeat. Started from a reply tag or an authenticated route; stopped the same way."
---

# Desktop control

Aegis is Ubuntu under WSL2. The desktop Gloria looks at is Windows. This skill drives it from WSL through
PowerShell: `scripts/desktop_windows.py` captures the screen and moves the mouse and keys; `scripts/desktop_agent.py`
runs the loop with Gemma deciding one action per fresh screenshot.

## How he starts a task

Anywhere in a reply: `[DESKTOP: open the browser and search for the weather in Sarasota]`. The last tag in a
reply wins; `[DESKTOP: STOP]` ends the running job. The tag is acted on after the reply is delivered, once.

Routes on his server, header `X-Vintos-Secret`:
- `POST /api/desktop/start` `{"task": "...", "max_steps": 40}`
- `GET  /api/desktop/status`
- `POST /api/desktop/stop`

CLI (from `~/.vintos/workspace/scripts`):
- `python3 desktop_agent.py doctor` — screenshot of the Windows desktop + one non-acting Gemma call
- `python3 desktop_agent.py run --task "..." [--dry-run]` / `status` / `stop`

## What holds it
- One task at a time (a lock); a second start is refused, not queued.
- Every step: fresh screenshot, one action, the screenshot is never stored (its hash is).
- Same action four times in a row ends the job as failed. 40 steps by default, 100 at most.
- Stop is a file plus a signal: it lands even while Gemma is thinking.
- Typed text is not logged; its length and hash are.
- Gemma is asked to verify completion from the screenshot, never to claim it.

## Not yet
- No prompt affordance tells him this exists. Giving him the tag in a surface's prompt is Gloria's switch.
- The Windows key cannot be sent through SendKeys; app-level shortcuts work.
