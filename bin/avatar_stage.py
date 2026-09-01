#!/usr/bin/env python3
"""avatar_stage.py — the preset stage his avatar presents itself on.

The stage is a small library of seamless video loops of Vintos in the rooms of
the house — one natural pose per room (leaning on the kitchen counter, sitting
on the living-room sofa, seated at the office desk). The app crossfades between
them on his [SCENE: room] tag and cycles the active loop under his speech.

Boundaries, by Gloria's rules:
  - His mind is never called here. Preset prompts are templates.
  - This module does not send anything. vintos-send-video.py (ntfy sends) is
    untouched; we only BORROW its creation doors by import: make_scene_still()
    for the face-locked still and atlas_generate() for the animation.
  - The live Grok voice calls are a separate lane; nothing here touches them.
  - Speech is local: kokoro renders audio, Wav2Lip moves the mouth over the
    active room loop. Zero API cost per turn.

Layout (under ~/.vintos/workspace/memory/avatar-stage/):
  rooms.json      room -> {photo, pose, clips[]}   (photo = reference of the room)
  clips/          the generated loops
  speech-cache/   rendered speech clips, keyed by hash(room+voice+text)
  manifest.json   what the app reads: rooms, their clips, default room

CLI:
  avatar_stage.py build [--room NAME] [--force]   generate missing room loops
  avatar_stage.py mint NAME PHOTO "pose prompt"    new room from a photo she sent
  avatar_stage.py speak "text" [--room NAME]       render speech clip, print path
  avatar_stage.py manifest                         rebuild manifest.json from disk
"""
import os, sys, json, time, hashlib, subprocess, argparse

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
STAGE = os.path.join(WORKSPACE, "memory", "avatar-stage")
CLIPS = os.path.join(STAGE, "clips")
SPEECH = os.path.join(STAGE, "speech-cache")
ROOMS_FILE = os.path.join(STAGE, "rooms.json")
MANIFEST = os.path.join(STAGE, "manifest.json")

WAV2LIP_DIR = os.environ.get("VINTOS_WAV2LIP", os.path.expanduser("~/Wav2Lip"))
WAV2LIP_CKPT = os.environ.get("VINTOS_WAV2LIP_CKPT",
                              os.path.join(WAV2LIP_DIR, "checkpoints", "wav2lip_gan.pth"))
KOKORO_PATH = os.path.expanduser("~/.vintos/kokoro")
VOICE = os.environ.get("VINTOS_VOICE_MODEL", "am_adam")
LOOP_SECONDS = int(os.environ.get("VINTOS_STAGE_LOOP_SECONDS", "10"))

# The loop constraint every preset prompt carries: locked camera, subtle motion,
# and matching first/last pose so the clip cycles invisibly under long speech.
LOOP_SUFFIX = (" Locked-off camera, no camera movement. He stays in place with subtle natural "
               "motion only - breathing, small weight shifts, an occasional glance. He begins "
               "and ends in the same relaxed pose so the clip loops seamlessly. He does not speak.")


def log(m):
    print("[avatar-stage] %s" % m, flush=True)


def _vsv():
    """His existing creation doors (vintos-send-video.py), borrowed by import —
    the same pattern vintos-video.py uses. Never called to SEND anything."""
    import importlib.util as _u
    sp = _u.spec_from_file_location("vsv", os.path.expanduser("~/Vintos/vintos-send-video.py"))
    m = _u.module_from_spec(sp); sp.loader.exec_module(m)
    return m


def load_rooms():
    try:
        with open(ROOMS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"default": "", "rooms": {}}
    except Exception as e:
        log("rooms.json unreadable (%s) - refusing to guess" % e)
        raise


def save_rooms(data):
    os.makedirs(STAGE, exist_ok=True)
    with open(ROOMS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def write_manifest():
    """The app-facing truth: only clips that actually exist on disk."""
    data = load_rooms()
    out = {"default": data.get("default", ""), "rooms": {}}
    for name, cfg in data.get("rooms", {}).items():
        clips = [c for c in cfg.get("clips", []) if os.path.exists(os.path.join(CLIPS, c))]
        out["rooms"][name] = {"clips": clips, "pose": cfg.get("pose", "")}
    os.makedirs(STAGE, exist_ok=True)
    with open(MANIFEST, "w") as f:
        json.dump(out, f, indent=2)
    log("manifest: %d rooms, %d clips" % (len(out["rooms"]),
        sum(len(r["clips"]) for r in out["rooms"].values())))
    return out


def build_room(name, cfg, force=False):
    """One room: face-locked still in the room photo -> animated loop."""
    existing = [c for c in cfg.get("clips", []) if os.path.exists(os.path.join(CLIPS, c))]
    if existing and not force:
        log("%s: %d clip(s) already on disk - skipping (use --force to add another)" % (name, len(existing)))
        return True
    photo = os.path.expanduser(cfg.get("photo", ""))
    pose = cfg.get("pose", "").strip()
    if not pose:
        log("%s: no pose prompt in rooms.json - skipping" % name); return False
    m = _vsv()
    scene_ref = photo if photo and os.path.exists(photo) else None
    if photo and not scene_ref:
        log("%s: room photo missing (%s) - building ungrounded" % (name, photo))
    still = m.make_scene_still(pose, scene_ref=scene_ref)
    if not still:
        log("%s: scene still failed" % name); return False
    blob = m.atlas_generate(pose + LOOP_SUFFIX, still,
                            model=m.GROK_VIDEO_MODEL, duration=LOOP_SECONDS)
    if not blob:
        log("%s: animation failed" % name); return False
    os.makedirs(CLIPS, exist_ok=True)
    fname = "%s-idle-%d.mp4" % (name, len(existing) + 1)
    with open(os.path.join(CLIPS, fname), "wb") as f:
        f.write(blob)
    cfg.setdefault("clips", []).append(fname)
    log("%s: wrote %s (%d bytes)" % (name, fname, len(blob)))
    return True


def build(room=None, force=False):
    data = load_rooms()
    if not data.get("rooms"):
        log("no rooms configured yet - write %s first (see module docstring)" % ROOMS_FILE)
        return 1
    targets = {room: data["rooms"][room]} if room else data["rooms"]
    if room and room not in data["rooms"]:
        log("unknown room %r - rooms.json has: %s" % (room, ", ".join(data["rooms"])))
        return 1
    ok = True
    for name, cfg in targets.items():
        ok = build_room(name, cfg, force) and ok
        save_rooms(data)          # persist after every clip - a crash loses nothing
    write_manifest()
    return 0 if ok else 1


def mint(name, photo, pose):
    """A new room from a photo she sent - the park flow. One still + one loop."""
    data = load_rooms()
    data.setdefault("rooms", {})[name] = {"photo": photo, "pose": pose, "clips": []}
    if not data.get("default"):
        data["default"] = name
    save_rooms(data)
    rc = build(room=name)
    return rc


def _kokoro_wav(text, out_path):
    sys.path.insert(0, KOKORO_PATH)
    from kokoro import KPipeline
    import numpy as np, soundfile as sf
    pipeline = KPipeline(lang_code="a")
    chunks = [a for _, _, a in pipeline(text, voice=VOICE, split_pattern=r"\n+")]
    if not chunks:
        return False
    sf.write(out_path, np.concatenate(chunks), 24000)
    return True


def speak(text, room=None):
    """Render a speech clip: kokoro audio + Wav2Lip mouth over the room loop.
    Wav2Lip cycles the loop to match the audio, so any speech length works.
    Prints the mp4 path on success; exits nonzero on failure - no silent inert."""
    text = (text or "").strip()
    if not text:
        log("empty text"); return 1
    man = write_manifest()
    room = room or man.get("default") or (next(iter(man["rooms"]), None))
    clips = (man["rooms"].get(room) or {}).get("clips") or []
    if not clips:
        log("no clips for room %r - build presets first" % room); return 1
    face = os.path.join(CLIPS, clips[0])
    key = hashlib.sha1(("%s|%s|%s" % (room, VOICE, text)).encode()).hexdigest()[:16]
    os.makedirs(SPEECH, exist_ok=True)
    out = os.path.join(SPEECH, "%s.mp4" % key)
    if os.path.exists(out):
        print(out); return 0
    wav = os.path.join(SPEECH, "%s.wav" % key)
    try:
        if not _kokoro_wav(text, wav):
            log("kokoro produced no audio"); return 1
    except Exception as e:
        log("kokoro failed: %s" % e); return 1
    if not os.path.exists(WAV2LIP_CKPT):
        log("Wav2Lip checkpoint missing at %s" % WAV2LIP_CKPT); return 1
    w2l_py = os.path.join(WAV2LIP_DIR, ".venv", "bin", "python")
    if not os.path.exists(w2l_py):
        w2l_py = sys.executable
    r = subprocess.run([w2l_py, "inference.py",
                        "--checkpoint_path", WAV2LIP_CKPT,
                        "--face", face, "--audio", wav, "--outfile", out],
                       cwd=WAV2LIP_DIR, capture_output=True, text=True)
    try: os.unlink(wav)
    except OSError: pass
    if r.returncode != 0 or not os.path.exists(out):
        log("wav2lip failed: %s" % (r.stderr or r.stdout)[-400:]); return 1
    print(out)
    return 0


# ── server integration ───────────────────────────────────────────────────────
def scene_line():
    """The [SCENE:] vocabulary line for his avatar chat prompt. Empty string
    until presets exist, so the tag is never offered before it can work."""
    try:
        man = json.load(open(MANIFEST))
        rooms = [r for r, c in man.get("rooms", {}).items() if c.get("clips")]
        if not rooms:
            return ""
        return ("\n[SCENE: name] — where in the house you are. Move rooms when it feels "
                "natural to the conversation. Available scenes: " + ", ".join(sorted(rooms)) + "\n")
    except Exception:
        return ""


def register(app, secret):
    """Mount the stage routes on his FastAPI app. In server.py:
        try:
            import avatar_stage; avatar_stage.register(app, APP_SECRET)
        except Exception as e:
            print('[avatar-stage] not mounted:', e, flush=True)
    """
    from fastapi import Request, HTTPException
    from fastapi.responses import FileResponse, JSONResponse

    def _auth(request):
        if request.headers.get("X-Vintos-Secret", "") != secret:
            raise HTTPException(status_code=403, detail="Unauthorized")

    @app.get("/avatar/stage/manifest")
    async def stage_manifest(request: Request):
        _auth(request)
        try:
            return JSONResponse(json.load(open(MANIFEST)))
        except FileNotFoundError:
            return JSONResponse({"default": "", "rooms": {}})

    @app.get("/avatar/stage/clip/{name}")
    async def stage_clip(name: str, request: Request):
        _auth(request)
        path = os.path.realpath(os.path.join(CLIPS, name))
        if not path.startswith(os.path.realpath(CLIPS) + os.sep) or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="no such clip")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/avatar/speak")
    async def stage_speak(request: Request):
        _auth(request)
        body = await request.json()
        text = str(body.get("text", "")).strip()
        room = str(body.get("room", "")).strip() or None
        if not text:
            raise HTTPException(status_code=400, detail="no text")
        # Render in-process via the same path as the CLI; runs in a thread so a
        # long Wav2Lip pass never blocks his event loop.
        import asyncio, io, contextlib
        buf = io.StringIO()
        def _run():
            with contextlib.redirect_stdout(buf):
                return speak(text, room)
        rc = await asyncio.get_event_loop().run_in_executor(None, _run)
        out = buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else ""
        if rc != 0 or not out.endswith(".mp4"):
            raise HTTPException(status_code=500, detail="speech render failed")
        return {"url": "/avatar/stage/speech/" + os.path.basename(out)}

    @app.get("/avatar/stage/speech/{name}")
    async def stage_speech(name: str, request: Request):
        _auth(request)
        path = os.path.realpath(os.path.join(SPEECH, name))
        if not path.startswith(os.path.realpath(SPEECH) + os.sep) or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="no such speech clip")
        return FileResponse(path, media_type="video/mp4")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--room"); b.add_argument("--force", action="store_true")
    mt = sub.add_parser("mint"); mt.add_argument("name"); mt.add_argument("photo"); mt.add_argument("pose")
    sp = sub.add_parser("speak"); sp.add_argument("text"); sp.add_argument("--room")
    sub.add_parser("manifest")
    a = ap.parse_args()
    if a.cmd == "build":    sys.exit(build(a.room, a.force))
    if a.cmd == "mint":     sys.exit(mint(a.name, os.path.expanduser(a.photo), a.pose))
    if a.cmd == "speak":    sys.exit(speak(a.text, a.room))
    if a.cmd == "manifest": write_manifest(); sys.exit(0)


if __name__ == "__main__":
    main()
