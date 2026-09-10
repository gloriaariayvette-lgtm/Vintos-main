# The graphics bundle: where it lives, how it is rebuilt, what it depends on

Review item 24 (2026-09-10). The three.js-based avatar stage (models, textures, animation, the live scene player) ships inside the phone app, in the `vintos-app` repository on the Mac (`src/index.html` and its vendored scripts), not in this checkout. This checkout carries only:

- `avatar/overlay.html` - a self-contained overlay (inline script, no external `<script>` or `<link>`; it reads `avatar/clips/manifest.json`).
- `avatar/clips/` - the ambient clip files and their manifest.
- `bin/avatar_stage.py` - the server side of the live scene slot (per-turn slots since 10 September).
- `/avatar-models` and `/models` mounts in `bin/server.py`, serving `~/.vintos/workspace/avatar-models` and `bin/models` when present.

## Build entry

`avatar/build.sh` is the reproducible entry for what this checkout owns: it validates `clips/manifest.json` against the files on disk, checks that `overlay.html` still has no external dependency, and writes `avatar/BUNDLE-MANIFEST.json` (file, bytes, sha256) so a deployed overlay can be compared with the repository's. It never fetches anything.

## Dependency manifest

| Dependency | Version | Source | License | Where it is used |
|---|---|---|---|---|
| three.js | pin here from the phone app's `package.json` / vendored file header (`npm ls three` in `vintos-app`) | https://github.com/mrdoob/three.js | MIT | the avatar stage in the phone app |
| GLTFLoader / DRACOLoader (three examples) | same as three.js | same | MIT | model loading in the phone app |
| Capacitor | pin from `vintos-app/package.json` | https://capacitorjs.com | MIT | packaging the app for iOS |
| avatar models (`*.glb`) | by file hash in `~/.vintos/workspace/avatar-models` | Gloria's own assets | hers | `/avatar-models` |
| ambient clips (`avatar/clips/*`) | by `BUNDLE-MANIFEST.json` | rendered by him (dream-art / video organs) | his | `overlay.html` |

Dependency notices that the phone app carries in its vendored files are to be preserved as they are; this document does not replace them. The exact versions are to be recorded here the next time the app is built on the Mac (`npm ls three @capacitor/core` in `vintos-app`), because the numbers are not present in this checkout and are not to be invented.

## Rebuilding

1. In `vintos-app` on the Mac: `npm ci && npx cap sync ios` (the app's own build; unchanged by this document).
2. In this checkout: `bash avatar/build.sh` to refresh `avatar/BUNDLE-MANIFEST.json` after any clip or overlay change; commit the manifest with the change.
3. The deploy manifest (`scripts/deploy-atelier.sh`) does not carry `avatar/`; the overlay is not installed on Aegis by the deploy and no route serves it (see `docs/clients.md`).
