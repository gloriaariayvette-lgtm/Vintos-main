# Avatar surface redesign

*Why the forge goes away, what replaces the Mixamo rig, and how to grow the new surface from one photo to a full clip library.*

## The gap this closes

The app today shows a stiff Mixamo-rigged character standing in a generic blacksmith scene — props that are not his, motion that is not his. The videos Vintos makes from a reference photo of the house are the opposite: natural light, the real rooms, the cat, him at ease. The redesign moves the app surface into that second register.

## The three realistic approaches, and the choice

1. **Upgraded 3D rig** — facial blendshapes, blended idle motion, gaze tracking, sitting IK. Free-form and real-time, but permanently "game engine": it can never look like the videos, and the modelling/rigging effort is the largest of the three.
2. **Photoreal clip library** *(chosen)* — a set of short looping videos of him in the home, generated with the already-proven photo-reference pipeline: an idle pool plus one pool per regularly-used emote tag. The app crossfades between clips as his emote changes. Least free-form, most on-brand, and it reuses the exact thing that already looks right.
3. **Real-time neural avatar** — audio-driven photoreal talking head. Most fluid, heaviest to run, quality unstable on-device today. Worth revisiting; a clip library is not wasted work if we later switch, because the same footage seeds it.

The clip library wins on honesty too: it *is* a library of him in the house, and it never pretends to be more. He only regularly uses a handful of emotes, so the library stays small — start with `idle`, `desk`, `warm`, `amused`, `tender`, `focused`, `listening`; everything unlisted falls back down a declared chain and lands on idle.

## What is in this repo

- `avatar/overlay.html` — the new self-contained avatar surface (no build step, no external libraries). Drop it next to `server.py` on Aegis and serve it in place of the current overlay page.
- `avatar/clips/manifest.json` — the clip manifest. The player reads it at load; adding a clip is: drop the file in `avatar/clips/`, add its filename to the right pool.

The old Three.js/Mixamo overlay lives on Aegis (this repo only carries the `server.py` symlink), so this is a parallel surface, not an edit of the old one — the old screen keeps working until the new one is wired and preferred.

### Degradation ladder (nothing ever breaks)

1. No manifest → warm dark-gradient scene, all UI still works.
2. Manifest with only `still` → one photo of him in the home, with a slow breathing scale so it reads as present, not frozen.
3. Idle clips exist → living idle, rotating every ~45 s so silence never freezes on one loop.
4. Emote pools filled in → full crossfading library.

### UI changes (as requested)

- **Model toggle off the telemetry bars.** The bars own the top-right corner alone. The model toggle lives in a right-edge drawer with a handle that slides the whole panel out on tap and tucks it away again.
- **Controls behind the drawer.** CALL and GCS are in the drawer too. DEVICE STOP additionally requires a 900 ms press-and-hold with a visible fill — a stray tap cannot trigger it.
- Caption strip and the say-something input bar stay where they are.

### Wiring (one adapter on Aegis)

The page exposes `window.VintosAvatar`: `setEmote(tag)` (route `[GESTURE]`/`[DO:…]` tags here), `setTelemetry({val:…, aro:…, …})` with values 0–1, `setCaption(text)`, `setModel(name)`, and `on(event, cb)` for `send`, `call`, `gcs`, `stop`, `close`, `camera`, `gallery`, `model-toggle`. Point the existing websocket handlers at these and delete nothing else.

## Generating the clips

Use the same video pipeline that made the kitchen clip, with a reference photo per room. Constraints that make clips loop-able and blend-able:

- 6–10 seconds, camera locked off (no pans — crossfades between clips must not jump).
- Same framing across all clips for a room: him roughly centered, mid-shot, consistent light and outfit per batch.
- Start and end near the same neutral pose so loops don't pop.
- One room per batch; the desk room is the priority since "sitting at a desk" was the wish.

Prompt template (fill the bracketed parts, attach the room reference photo):

> Using the attached photo of [room] as the exact setting, lighting, and camera position: a photorealistic 8-second locked-off shot of [Vintos's description — the man from the reference clip, dark hair, green t-shirt], [ACTION]. Natural light, no camera movement, he begins and ends in a relaxed neutral posture.

Actions per pool — `idle`: sitting at the desk, breathing, small weight shifts, glancing toward the window · `desk`/`focused`: writing or reading at the desk, absorbed · `warm`: looking up toward the camera with a soft smile · `amused`: a quiet laugh, shaking his head slightly · `tender`: leaning back, gaze steady toward the camera · `listening`: turned toward the camera, attentive, small nods.

Two or three clips per pool is enough to kill repetition; one is enough to start.
