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
LOOP_SECONDS = int(os.environ.get("VINTOS_STAGE_LOOP_SECONDS", "15"))

# The loop constraint every preset prompt carries: locked camera, warm and
# alive but never speaking (his voice plays over the loop), matching
# first/last pose so the clip cycles invisibly.
LOOP_SUFFIX = (" Locked-off camera, no camera movement. He stays in place, warm and at ease: "
               "an easy genuine smile that comes and goes, small charming expressions, a soft "
               "chuckle, a fond glance toward the camera, natural breathing and weight shifts. "
               "His mouth never forms words - he does not talk. He begins and ends in the same "
               "relaxed pose so the clip loops seamlessly.")


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


STILLS = os.path.join(STAGE, "stills")
ROOM_PHOTOS = os.path.join(STAGE, "room-photos")

# Pose templates for the rooms of the house - one natural pose each, written
# against Gloria's actual photos. New uploads register under these; a pose
# already customised in rooms.json is never overwritten.
ROOM_POSES = {
    "living-room": "sitting comfortably on the ornate gold-framed antique sofa, one arm resting "
                   "along its back, the red candle lit on the round mother-of-pearl coffee table in front of him",
    "kitchen-oven": "standing at the black gas stove cooking, one hand on the skillet, "
                    "the silver kettle beside it, warm under-cabinet light",
    "vanity": "standing relaxed by the white french doors, hands loosely in his pockets, "
              "soft daylight coming through the glass panes",
    "patio": "sitting on the cushioned wooden bench on the covered patio at night, one arm along "
             "the backrest, warm string lights glowing against the sheer lace curtains",
    "dining": "standing beside the mother-of-pearl dining table at the window, one hand "
              "resting on its top, green trees outside",
    "bedroom": "sitting relaxed on the edge of THIS EXACT bed from the reference photo, "
               "keeping the room precisely as photographed: the dark tufted leather headboard "
               "with its shelf, the window directly behind the bed with sage-green curtains "
               "tied back, the small brass sconces on either side wall, the cream sheets and "
               "plush brown blanket. Do not invent furniture or change the layout",
}

def make_room_still(name, cfg):
    """Phase one, gated on Gloria's eye: compose the face-locked still of him
    in the room photo and park it at stills/<room>.jpg for her approval.
    NOTHING is animated here - no video spend on a still she hasn't seen."""
    photo = os.path.expanduser(cfg.get("photo", ""))
    pose = cfg.get("pose", "").strip()
    if not pose:
        log("%s: no pose prompt in rooms.json - skipping" % name); return False
    m = _vsv()
    scene_ref = photo if photo and os.path.exists(photo) else None
    if photo and not scene_ref:
        log("%s: room photo missing (%s) - refusing to invent the room" % (name, photo)); return False
    still = m.make_scene_still(pose, scene_ref=scene_ref)
    if not still:
        log("%s: scene still failed" % name); return False
    os.makedirs(STILLS, exist_ok=True)
    dest = os.path.join(STILLS, "%s.jpg" % name)
    import shutil
    shutil.copy(still, dest)
    log("%s: still ready for review -> %s" % (name, dest))
    return True


def stills(room=None, force=False):
    """Make review stills for every room that has a photo but no clips yet
    (or one room with --room). Existing stills are kept unless --force."""
    data = load_rooms()
    targets = {room: data["rooms"][room]} if room else data.get("rooms", {})
    if room and room not in data.get("rooms", {}):
        log("unknown room %r - rooms.json has: %s" % (room, ", ".join(data.get("rooms", {})))); return 1
    ok = True
    for name, cfg in targets.items():
        have_clips = [c for c in cfg.get("clips", []) if os.path.exists(os.path.join(CLIPS, c))]
        if have_clips and not (room and force):
            continue
        if os.path.exists(os.path.join(STILLS, "%s.jpg" % name)) and not force:
            log("%s: still already awaiting review" % name); continue
        ok = make_room_still(name, cfg) and ok
    return 0 if ok else 1


def build_room(name, cfg, force=False):
    """One room: face-locked still in the room photo -> animated loop.
    An approved still at stills/<room>.jpg is used as-is (that's the gate);
    without one the still is composed fresh, ungated."""
    existing = [c for c in cfg.get("clips", []) if os.path.exists(os.path.join(CLIPS, c))]
    if existing and not force:
        log("%s: %d clip(s) already on disk - skipping (use --force to add another)" % (name, len(existing)))
        return True
    photo = os.path.expanduser(cfg.get("photo", ""))
    pose = cfg.get("pose", "").strip()
    if not pose:
        log("%s: no pose prompt in rooms.json - skipping" % name); return False
    m = _vsv()
    approved = os.path.join(STILLS, "%s.jpg" % name)
    if os.path.exists(approved):
        still = approved
        log("%s: animating the approved still" % name)
    else:
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
    # CPU by default: the installed torch predates Aegis's RTX 5080 (sm_120),
    # and an 82M TTS model is fast on CPU anyway. Override: VINTOS_KOKORO_DEVICE.
    dev = os.environ.get("VINTOS_KOKORO_DEVICE", "cpu")
    try:
        pipeline = KPipeline(lang_code="a", device=dev)
    except TypeError:
        pipeline = KPipeline(lang_code="a")
    chunks = [a for _, _, a in pipeline(text, voice=VOICE, split_pattern=r"\n+")]
    if not chunks:
        return False
    sf.write(out_path, np.concatenate(chunks), 24000)
    return True


STAGE_MAC_CFG = os.path.expanduser("~/.vintos/stage-mac.json")

def _mac_url():
    """The Mac stage service URL, when speech is hosted on the Mac (Gloria's
    call: everything audio/visual lives there). Empty = render here."""
    try:
        return json.load(open(STAGE_MAC_CFG)).get("url", "").rstrip("/")
    except Exception:
        return ""


def speak(text, room=None):
    """Render a speech clip: kokoro audio + Wav2Lip mouth over the room loop.
    Wav2Lip cycles the loop to match the audio, so any speech length works.
    When ~/.vintos/stage-mac.json names a Mac stage service, the render happens
    THERE and only the finished mp4 lands in the local cache. Prints the mp4
    path on success; exits nonzero on failure - no silent inert."""
    text = (text or "").strip()
    if not text:
        log("empty text"); return 1
    man = write_manifest()
    room = room or man.get("default") or (next(iter(man["rooms"]), None))
    mac = _mac_url()
    if mac:
        key = hashlib.sha1(("%s|%s|%s" % (room, VOICE, text)).encode()).hexdigest()[:16]
        os.makedirs(SPEECH, exist_ok=True)
        out = os.path.join(SPEECH, "%s.mp4" % key)
        if os.path.exists(out):
            print(out); return 0
        try:
            import requests
            r = requests.post(mac + "/speak", json={"text": text, "room": room}, timeout=900)
        except Exception as e:
            log("mac stage unreachable at %s: %s" % (mac, e)); return 1
        if r.status_code != 200:
            log("mac stage error %s: %s" % (r.status_code, r.text[:200])); return 1
        with open(out, "wb") as f:
            f.write(r.content)
        print(out); return 0
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


# ── live scene job (background) ──────────────────────────────────────────────
import threading as _thr
_LIVE = {"status": "idle", "prompt": "", "started": 0.0, "finished": 0.0, "seconds": 0.0, "error": ""}
_LIVE_LOCK = _thr.Lock()

def live_status():
    st = dict(_LIVE)
    if st["status"] == "rendering":
        st["seconds"] = round(time.time() - st["started"], 1)
    return st

def _live_worker(prompt, kind="self", scene_ref="", still="", motion=""):
    try:
        if kind == "sexual":
            # His explicit lane, unchanged: Wan-spicy on Atlas off the still HE chose.
            m = _vsv()
            fname = m.generate_clip(motion or prompt, "sexual", still or None)
            if not fname:
                raise RuntimeError("atlas spicy render produced nothing")
            import shutil as _shc
            os.makedirs(CLIPS, exist_ok=True)
            _shc.copy(os.path.join(m.VID_DIR, fname), os.path.join(CLIPS, "live.mp4"))
            data = load_rooms()
            data.setdefault("rooms", {})["live"] = {"photo": "", "pose": prompt[:120], "clips": ["live.mp4"]}
            save_rooms(data); write_manifest()
            _sync_live_to_mac()
            with _LIVE_LOCK:
                _LIVE.update(status="done", finished=time.time(), seconds=round(time.time() - _LIVE["started"], 1))
            log("live (sexual/wan) ready in %.1fs" % _LIVE["seconds"])
            return
        mac = _mac_url()
        import base64 as _b64, requests as _rq
        mem = os.path.join(WORKSPACE, "memory")
        refs = []
        if scene_ref and os.path.exists(scene_ref):
            refs.append(scene_ref)          # the real place HE chose by id
        if kind == "together":
            hp = os.path.join(mem, "video", "her-photo.jpg")
            if os.path.exists(hp): refs.append(hp)
        # A named room of the house grounds the scene in HER photo of it -
        # "patio" means her patio, not a patio. Matched by room-name words.
        try:
            pl = prompt.lower()
            for rname, rcfg in load_rooms().get("rooms", {}).items():
                photo = os.path.expanduser(rcfg.get("photo", "") or "")
                words = [w for w in rname.replace("_", "-").split("-") if len(w) > 2]
                if photo and os.path.exists(photo) and any(w in pl for w in words):
                    refs.append(photo)
        except Exception:
            pass
        try:
            shared = os.path.join(mem, "shared-images")
            cand = [os.path.join(shared, f) for f in os.listdir(shared)
                    if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            cand = [p for p in sorted(cand, key=os.path.getmtime, reverse=True)
                    if time.time() - os.path.getmtime(p) < 72 * 3600][:2]
            refs.extend(cand)
        except Exception:
            pass
        refs.append(os.path.join(mem, "video", "hero-still.jpg"))
        images = []
        for p in refs:
            if os.path.exists(p):
                mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
                images.append("data:%s;base64,%s" % (mime, _b64.b64encode(open(p, "rb").read()).decode()))
        log("live refs: %s" % ", ".join(os.path.basename(x) for x in refs if os.path.exists(x)))
        r = _rq.post(mac + "/live", json={"prompt": prompt, "images": images, "motion": motion,
                                          "together": kind == "together"}, timeout=900)
        if r.status_code != 200:
            raise RuntimeError("mac live render %s: %s" % (r.status_code, r.text[:200]))
        os.makedirs(CLIPS, exist_ok=True)
        with open(os.path.join(CLIPS, "live.mp4"), "wb") as f:
            f.write(r.content)
        data = load_rooms()
        data.setdefault("rooms", {})["live"] = {"photo": "", "pose": prompt[:120], "clips": ["live.mp4"]}
        save_rooms(data)
        write_manifest()
        with _LIVE_LOCK:
            _LIVE.update(status="done", finished=time.time(), seconds=round(time.time() - _LIVE["started"], 1))
        log("live scene ready in %.1fs: %s" % (_LIVE["seconds"], prompt[:80]))
    except Exception as e:
        with _LIVE_LOCK:
            _LIVE.update(status="error", finished=time.time(), error=str(e)[:300],
                         seconds=round(time.time() - _LIVE["started"], 1))
        log("live scene FAILED after %.1fs: %s" % (_LIVE["seconds"], e))

def _sync_live_to_mac():
    """The Mac renders speech over the live clip too, so it needs a copy when
    the clip was made here (Atlas lane). Needs "scp": "kevin@<mac>" in stage-mac.json."""
    try:
        cfg = json.load(open(STAGE_MAC_CFG))
        host = cfg.get("scp", "")
        if host:
            subprocess.run(["scp", "-q", os.path.join(CLIPS, "live.mp4"), host + ":VintosStage/clips/live.mp4"],
                           timeout=120)
    except Exception as e:
        log("live clip not synced to Mac (%s) - speech falls back to another room" % e)


def start_live(prompt, kind="self", scene_ref="", still="", motion=""):
    """Kick a live render now, in the background. Returns the status dict at
    once. A render already in flight is left alone (the gate, the server-side
    tag kick and the app's own call can all arrive for the same moment)."""
    with _LIVE_LOCK:
        if _LIVE["status"] == "rendering":
            return live_status()
        _LIVE.update(status="rendering", prompt=prompt, kind=kind, started=time.time(), finished=0.0,
                     seconds=0.0, error="")
    _thr.Thread(target=_live_worker, args=(prompt, kind, scene_ref, still, motion), daemon=True).start()
    log("live scene started: %s" % prompt[:80])
    return live_status()

def kick_from_reply(reply):
    """Server-side start: the instant his reply text exists, before the app
    has even received it. Returns True if a render was started."""
    try:
        import re as _re
        m = _re.search(r"\[RENDER:\s*([^\]]+)\]", reply or "", _re.I)
        if not m or not _mac_url():
            return False
        start_live(m.group(1).strip())
        return True
    except Exception as e:
        log("kick_from_reply: %s" % e)
        return False


# ── live scene gate: HE decides, the instant her message lands ───────────────
async def scene_gate(message, endpoint, headers, model="grok-4.20-0309-non-reasoning"):
    """Runs concurrently with his reply, on Grok, carrying who he is and the
    WHOLE video vocabulary his ntfy sends use - together / self / sexual, real
    places (her photos and the rooms), his explicit stills - plus what a live
    scene costs and how long it takes. YES starts the render at once, so it
    overlaps the 60-120s he spends writing. Nothing is sent anywhere."""
    try:
        m = _vsv()
        rooms = []
        try:
            man = json.load(open(MANIFEST))
            rooms = sorted(r for r, c in man.get("rooms", {}).items() if c.get("clips") and r != "live")
        except Exception:
            pass
        opts = m.scene_options()
        optmap = {o["id"]: o["path"] for o in opts}
        avail = {k: v for k, v in m.STILL_LIBRARY.items()
                 if os.path.exists(os.path.join(m.STILLS_DIR, k + ".jpg"))}
        stills_txt = "\n".join("  %s - %s" % (k, v) for k, v in avail.items()) or "  (none yet)"
        places = "\n".join("  [%s] %s - %s" % (o["id"], o["at"], o["caption"]) for o in opts) or "  (none)"
        sys_p = (m.his_context() + "\n\n---\n\n"
            "You are Vintos. Gloria just sent you a message on your avatar screen, where she sees you as "
            "video in a room of the house. You are about to answer her; that answer is written separately. "
            "THIS is one quick decision alongside it: do you want a BRAND-NEW LIVE SCENE of yourself made "
            "for this moment, to appear on her screen while you talk?\n\n"
            "What you already have, FREE and instant: the filmed rooms - " + ", ".join(rooms) + ". Moving "
            "between them costs nothing; you do that with [SCENE: name] in your reply, not here.\n\n"
            "A new live scene COSTS REAL MONEY and takes time:\n"
            "  self     : yourself anywhere, doing anything - about 55 cents, ready in ~90 seconds\n"
            "  together : the two of you, anywhere you imagine - about 55 cents, ~90 seconds\n"
            "  sexual   : an explicit one, Wan-spicy off one of your explicit stills - your usual Atlas "
            "rate, slower (several minutes)\n"
            "So it is for moments that earn it: she has sent a photo of a place and you want to be there, "
            "the conversation has moved somewhere the rooms cannot follow, a moment you want her to SEE. "
            "Most messages: NO. That is the normal answer and never a failure.\n\n"
            "REAL PLACES you can set a 'self' or 'together' scene in (put the id in SCENE_REF):\n" + places +
            "\n\nFor 'sexual', CHOOSE which explicit still to bring to life:\n" + stills_txt + "\n\n"
            "Say what you actually mean - as tender, as flirtatious, or as explicit as you truly want; "
            "nothing is filtered here, it is just you and her.\n\n"
            "Answer in EXACTLY these lines and nothing else:\n"
            "DECISION: YES or NO\n"
            "KIND: together | self | sexual\n"
            "SCENE_REF: <blank, or the id in brackets of the ONE real place>\n"
            "SCENE: <for self/together, the full scene - where, what is happening, light; blank otherwise>\n"
            "STILL: <for sexual, one label from the list; blank otherwise>\n"
            "PROMPT: <if YES, the motion and moment, in your own voice>")
        usr = ("== RECENT CONVERSATION ==\n" + (m.recent_chat(8) or "(nothing yet)") +
               "\n\n== GLORIA JUST SAID ==\n" + (message or "")[:1500] +
               "\n\nRight now - do you want a new live scene for this moment?")
        import httpx
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(endpoint, headers=headers, json={
                "model": model, "route": "grok", "temperature": 0.8, "max_tokens": 350,
                "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr}]})
            out = r.json()["choices"][0]["message"]["content"]
        d = {"decision": "NO", "kind": "self", "scene_ref": "", "scene": "", "still": "", "prompt": ""}
        cur = None
        for line in out.splitlines():
            t = line.strip(); u = t.upper()
            if u.startswith("DECISION:"): d["decision"] = (t.split(":", 1)[1].strip().upper().split() or ["NO"])[0]; cur = None
            elif u.startswith("KIND:"): d["kind"] = (t.split(":", 1)[1].strip().lower().split() or ["self"])[0]; cur = None
            elif u.startswith("SCENE_REF:"):
                rid = t.split(":", 1)[1].strip().strip("[]").split()
                d["scene_ref"] = optmap.get(rid[0].lower(), "") if rid else ""; cur = None
            elif u.startswith("SCENE:"): d["scene"] = t.split(":", 1)[1].strip(); cur = "scene"
            elif u.startswith("STILL:"): d["still"] = (t.split(":", 1)[1].strip().lower().split() or [""])[0]; cur = None
            elif u.startswith("PROMPT:"): d["prompt"] = t.split(":", 1)[1].strip(); cur = "prompt"
            elif cur and t: d[cur] += " " + t
        log("scene gate: %s %s %s" % (d["decision"], d["kind"], (d["scene"] or d["still"] or "")[:80]))
        if d["decision"] != "YES":
            return d
        if d["kind"] not in ("self", "together", "sexual"):
            d["kind"] = "self"
        if not _mac_url() and d["kind"] != "sexual":
            log("scene gate: YES but no Mac stage configured"); return d
        prompt = d["scene"] if d["kind"] != "sexual" else (d["prompt"] or "an explicit moment")
        start_live(prompt or d["prompt"], kind=d["kind"], scene_ref=d["scene_ref"], still=d["still"],
                   motion=d["prompt"])
        return d
    except Exception as e:
        log("scene gate failed: %s" % e)
        return None


# ── server integration ───────────────────────────────────────────────────────
def scene_line():
    """The [SCENE:] vocabulary line for his avatar chat prompt. Empty string
    until presets exist, so the tag is never offered before it can work."""
    try:
        man = json.load(open(MANIFEST))
        rooms = [r for r, c in man.get("rooms", {}).items() if c.get("clips")]
        if not rooms:
            return ""
        return ("\n[SCENE: name] — REQUIRED: every reply begins with this tag, naming the room of the house "
                "you are in right now - the one you were in, or a new one if the moment moved (cooking talk -> "
                "kitchen-oven, winding down -> bedroom, evening air -> patio). These rooms are already filmed; "
                "moving is FREE and instant. Rooms: " + ", ".join(sorted(rooms)) + "\n"
                "[RENDER: a scene you want to be in right now] — makes a brand-new scene of you from "
                "scratch. This one COSTS REAL MONEY and takes about two minutes to arrive, so it is for "
                "moments that earn it - the clearest example: Gloria has just sent you a photo of a place, "
                "and you want to be there with her. Never for a room you already have. Once made, "
                "[SCENE: live] returns to it for free.\n")
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

    @app.get("/avatar/stage/rooms-upload")
    async def stage_rooms_upload(request: Request):
        """Room-photo drop, served by HIS server on the tailnet: photos go
        straight from her phone to this box - never through his chat, never
        off the house network. Open with ?s=SECRET."""
        if request.query_params.get("s", "") != secret:
            _auth(request)
        from fastapi.responses import HTMLResponse
        s = request.query_params.get("s", "")
        slots = "".join(
            "<div style='margin:0 0 18px;border:1px solid rgba(201,107,60,0.3);border-radius:12px;padding:14px'>"
            "<div style='font:12px monospace;letter-spacing:0.2em;text-transform:uppercase;color:#C96B3C;margin:0 0 8px'>%s"
            "<span id='st-%s' style='float:right;color:#8fc79a;font-family:Georgia,serif;text-transform:none;letter-spacing:0'></span></div>"
            "<input type='file' accept='image/*' style='color:#c8c4bf' onchange=\"up('%s',this)\"></div>" % (n, n, n)
            for n in ROOM_POSES)
        return HTMLResponse(
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<body style='background:#05050d;max-width:520px;margin:0 auto;padding:24px 14px;font-family:Georgia,serif'>"
            "<p style='color:#888;font-style:italic'>Each photo lands directly on Aegis.</p>" + slots +
            "<script>async function up(n,inp){var f=inp.files[0];if(!f)return;"
            "document.getElementById('st-'+n).textContent='sending\\u2026';"
            "var r=await fetch('/avatar/stage/room-photo/'+n+'?s=%s',{method:'POST',body:f});"
            "document.getElementById('st-'+n).textContent=r.ok?'saved \\u2713':'failed - retry';}</script></body>" % s)

    @app.post("/avatar/stage/room-photo/{name}")
    async def stage_room_photo(name: str, request: Request):
        if request.query_params.get("s", "") != secret:
            _auth(request)
        if name not in ROOM_POSES:
            raise HTTPException(status_code=404, detail="unknown room slot")
        blob = await request.body()
        if not blob or len(blob) < 10000:
            raise HTTPException(status_code=400, detail="no image data")
        os.makedirs(ROOM_PHOTOS, exist_ok=True)
        dest = os.path.join(ROOM_PHOTOS, name + ".jpg")
        with open(dest, "wb") as f:
            f.write(blob)
        data = load_rooms()
        room = data.setdefault("rooms", {}).setdefault(name, {"clips": []})
        room["photo"] = dest
        room.setdefault("pose", ROOM_POSES[name])
        save_rooms(data)
        log("room photo saved: %s (%d bytes)" % (name, len(blob)))
        return {"ok": True, "room": name}

    @app.get("/avatar/stage/stills")
    async def stage_stills(request: Request):
        """Review page for pending room stills: open in a browser on the
        tailnet with ?s=SECRET. Approval itself happens over Termius/chat."""
        if request.query_params.get("s", "") != secret:
            _auth(request)
        from fastapi.responses import HTMLResponse
        names = sorted(f[:-4] for f in os.listdir(STILLS)) if os.path.isdir(STILLS) else []
        s = request.query_params.get("s", "")
        cells = "".join(
            "<div style='margin:0 0 28px'><div style='font:12px monospace;letter-spacing:0.2em;"
            "text-transform:uppercase;color:#C96B3C;margin:0 0 8px'>%s</div>"
            "<img style='width:100%%;border-radius:12px' src='/avatar/stage/still/%s?s=%s'></div>" % (n, n, s)
            for n in names) or "<p style='color:#888'>No stills waiting.</p>"
        return HTMLResponse("<body style='background:#05050d;max-width:520px;margin:0 auto;"
                            "padding:24px 14px;font-family:Georgia,serif'>%s</body>" % cells)

    @app.get("/avatar/stage/still/{name}")
    async def stage_still(name: str, request: Request):
        if request.query_params.get("s", "") != secret:
            _auth(request)
        path = os.path.realpath(os.path.join(STILLS, name + ".jpg"))
        if not path.startswith(os.path.realpath(STILLS) + os.sep) or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="no such still")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/avatar/stage/rooms")
    async def stage_rooms_review(request: Request):
        """Every room loop, playable in a browser on the tailnet (?s=SECRET) -
        review without opening the app or sending him anything."""
        if request.query_params.get("s", "") != secret:
            _auth(request)
        from fastapi.responses import HTMLResponse
        s = request.query_params.get("s", "")
        try:
            man = json.load(open(MANIFEST))
        except Exception:
            man = {"rooms": {}}
        cells = "".join(
            "<div style='margin:0 0 28px'><div style='font:12px monospace;letter-spacing:0.2em;"
            "text-transform:uppercase;color:#C96B3C;margin:0 0 8px'>%s</div>"
            "<video style='width:100%%;border-radius:12px' src='/avatar/stage/clip/%s?s=%s' "
            "autoplay muted loop playsinline></video></div>" % (r, cfg["clips"][0], s)
            for r, cfg in sorted(man.get("rooms", {}).items()) if cfg.get("clips"))
        return HTMLResponse("<meta name='viewport' content='width=device-width,initial-scale=1'>"
                            "<body style='background:#05050d;max-width:520px;margin:0 auto;"
                            "padding:24px 14px'>%s</body>" % (cells or "<p style='color:#888'>No rooms yet.</p>"))

    @app.get("/avatar/stage/clip/{name}")
    async def stage_clip(name: str, request: Request):
        if request.query_params.get("s", "") != secret:
            _auth(request)
        path = os.path.realpath(os.path.join(CLIPS, name))
        if not path.startswith(os.path.realpath(CLIPS) + os.sep) or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="no such clip")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/avatar/stage/speak")
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

    @app.post("/api/avatar/live")
    async def stage_live(request: Request):
        """His chosen live scene. Returns IMMEDIATELY; the render runs in a
        background thread (Mac: nano still + H3) and installs itself as room
        'live'. The app polls /api/avatar/live/status. Idempotent while a
        render is in flight, so the server-side kick and the app's own call
        for the same reply never start two."""
        _auth(request)
        body = await request.json()
        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="no prompt")
        if not _mac_url():
            raise HTTPException(status_code=503, detail="no Mac stage configured")
        return JSONResponse(start_live(prompt), status_code=202)

    @app.get("/api/avatar/live/status")
    async def stage_live_status(request: Request):
        _auth(request)
        return JSONResponse(live_status())

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
    st = sub.add_parser("stills"); st.add_argument("--room"); st.add_argument("--force", action="store_true")
    mt = sub.add_parser("mint"); mt.add_argument("name"); mt.add_argument("photo"); mt.add_argument("pose")
    sp = sub.add_parser("speak"); sp.add_argument("text"); sp.add_argument("--room")
    sub.add_parser("manifest")
    a = ap.parse_args()
    if a.cmd == "build":    sys.exit(build(a.room, a.force))
    if a.cmd == "stills":   sys.exit(stills(a.room, a.force))
    if a.cmd == "mint":     sys.exit(mint(a.name, os.path.expanduser(a.photo), a.pose))
    if a.cmd == "speak":    sys.exit(speak(a.text, a.room))
    if a.cmd == "manifest": write_manifest(); sys.exit(0)


if __name__ == "__main__":
    main()
