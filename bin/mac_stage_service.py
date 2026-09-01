#!/usr/bin/env python
"""mac_stage_service.py - Vintos's audio/visual stage, hosted on the Mac.

Renders his speech clips locally: kokoro (voice) + Wav2Lip (mouth) over the
room loops synced from Aegis into ~/VintosStage/clips. Aegis's server calls
POST /speak and gets the finished mp4 back; nothing renders on Aegis.

Runs under the Wav2Lip venv python (which has torch, kokoro, soundfile).
Started by the LaunchAgent com.vintos.stage (port 8511).
"""
import os, sys, json, hashlib, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

HOME = os.path.expanduser("~")
STAGE = os.path.join(HOME, "VintosStage")
CLIPS = os.path.join(STAGE, "clips")
CACHE = os.path.join(STAGE, "speech-cache")
MANIFEST = os.path.join(STAGE, "manifest.json")
W2L = os.path.join(HOME, "Wav2Lip")
W2L_PY = os.path.join(W2L, ".venv", "bin", "python")
W2L_CKPT = os.path.join(W2L, "checkpoints", "wav2lip_gan.pth")
VOICE = os.environ.get("VINTOS_VOICE_MODEL", "am_adam")
PORT = int(os.environ.get("VINTOS_STAGE_PORT", "8511"))

# LaunchAgents don't inherit the shell PATH; Wav2Lip's last step shells out to
# ffmpeg, so make sure the common install dirs are reachable.
ENV = dict(os.environ)
ENV["PATH"] = ENV.get("PATH", "") + ":/usr/local/bin:/opt/homebrew/bin"
import shutil as _sh
FFMPEG = _sh.which("ffmpeg") or "/usr/local/bin/ffmpeg"

_pipeline = None

def log(m):
    print("[mac-stage] %s" % m, flush=True)

def kokoro_wav(text, out_path):
    global _pipeline
    from kokoro import KPipeline
    import numpy as np, soundfile as sf
    if _pipeline is None:
        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    chunks = [a for _, _, a in _pipeline(text, voice=VOICE, split_pattern=r"\n+")]
    if not chunks:
        return False
    sf.write(out_path, np.concatenate(chunks), 24000)
    return True

def face_for(room):
    try:
        man = json.load(open(MANIFEST))
    except Exception:
        man = {"rooms": {}, "default": ""}
    room = room or man.get("default") or next(iter(man.get("rooms", {})), "")
    clips = (man.get("rooms", {}).get(room) or {}).get("clips") or []
    clips = [c for c in clips if os.path.exists(os.path.join(CLIPS, c))]
    if not clips:
        any_clips = sorted(os.listdir(CLIPS)) if os.path.isdir(CLIPS) else []
        any_clips = [c for c in any_clips if c.endswith(".mp4")]
        return (os.path.join(CLIPS, any_clips[0]), "unknown") if any_clips else (None, room)
    return os.path.join(CLIPS, clips[0]), room

def face_box(face):
    """The close-up camera is locked off, so the face never moves: detect it
    ONCE per clip, cache the box, and Wav2Lip skips per-frame detection -
    that's most of the render time gone."""
    cache = face + ".box.json"
    try:
        return json.load(open(cache))
    except Exception:
        pass
    frame = face + ".frame.png"
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", face,
                        "-frames:v", "1", frame], env=ENV, capture_output=True)
    if r.returncode != 0 or not os.path.exists(frame):
        return None
    code = (
        "import sys, json, cv2, numpy as np, face_detection\n"
        "img = cv2.imread(sys.argv[1])\n"
        "d = face_detection.FaceAlignment(face_detection.LandmarksType._2D,\n"
        "                                 flip_input=False, device='cpu')\n"
        "p = d.get_detections_for_batch(np.array([img]))[0]\n"
        "if p is None: raise SystemExit('no face')\n"
        "x1, y1, x2, y2 = [int(v) for v in p]\n"
        "pad = 12\n"
        "print(json.dumps([max(0, y1 - pad), y2 + pad, max(0, x1 - pad), x2 + pad]))\n")
    r = subprocess.run([W2L_PY, "-c", code, frame], cwd=W2L, env=ENV,
                       capture_output=True, text=True)
    try: os.unlink(frame)
    except OSError: pass
    if r.returncode != 0:
        log("box detect failed: %s" % (r.stderr or r.stdout)[-200:])
        return None
    try:
        box = json.loads(r.stdout.strip().splitlines()[-1])
        json.dump(box, open(cache, "w"))
        return box
    except Exception:
        return None


def render(text, room):
    face, room = face_for(room)
    if not face:
        return None, "no room clips synced to the Mac yet"
    # Speech uses the room's CLOSE-UP variant when one exists: lip-sync only
    # works on a big face, so speaking cuts closer, idle stays wide.
    close = os.path.join(CLIPS, "%s-close.mp4" % room)
    if os.path.exists(close):
        face = close
    key = hashlib.sha1(("%s|%s|%s" % (room, VOICE, text)).encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, key + ".mp4")
    if os.path.exists(out):
        return out, None
    wav = os.path.join(CACHE, key + ".wav")
    try:
        if not kokoro_wav(text, wav):
            return None, "kokoro produced no audio"
    except Exception as e:
        return None, "kokoro failed: %s" % e
    # DEFAULT: voice-over - his voice plays instantly over the living close-up,
    # no mouth edit (Gloria's call: charm over lip-flap). Wav2Lip runs only if
    # the file ~/VintosStage/mouth-on exists (touch/rm to toggle).
    if not os.path.exists(os.path.join(STAGE, "mouth-on")):
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                            "-stream_loop", "-1", "-i", face, "-i", wav,
                            "-map", "0:v", "-map", "1:a", "-shortest",
                            "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", out],
                           env=ENV, capture_output=True, text=True)
        try: os.unlink(wav)
        except OSError: pass
        if r.returncode != 0 or not os.path.exists(out):
            return None, "voice-over mux failed: %s" % (r.stderr or "")[-200:]
        return out, None
    # Per-frame tracking, cached: the patched inference.py stores every frame's
    # face box beside the clip (<clip>.boxes.npy) on the first render, so the
    # mouth follows his head AND later renders skip detection entirely.
    cmd = [W2L_PY, "inference.py", "--checkpoint_path", W2L_CKPT,
           "--face", face, "--audio", wav, "--outfile", out]
    r = subprocess.run(cmd, cwd=W2L, env=ENV, capture_output=True, text=True)
    try: os.unlink(wav)
    except OSError: pass
    if r.returncode != 0 or not os.path.exists(out):
        return None, "wav2lip failed: %s" % (r.stderr or r.stdout)[-300:]
    return out, None

def _fal(model, body, timeout=600):
    import urllib.request
    key = open(os.path.join(STAGE, "fal-key")).read().strip()
    req = urllib.request.Request("https://fal.run/" + model,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Key " + key, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _find_media_url(o, ext):
    if isinstance(o, dict):
        for v in o.values():
            u = _find_media_url(v, ext)
            if u: return u
    elif isinstance(o, list):
        for v in o:
            u = _find_media_url(v, ext)
            if u: return u
    elif isinstance(o, str) and o.startswith("http") and (ext == "*" or ext in o):
        return o
    return None


def live_render(prompt, images=None, motion="", together=False):
    """His chosen live scene: nano-banana composes a full-body still of him in
    the described scene (~4c), H3 animates it at 768P (~50c). Aegis sends his
    references along: Gloria's recent photos first (setting/context), his hero
    still LAST (the face lock) - the same recipe his video sends use. Falls
    back to the local hero.jpg when none arrive. Returns mp4 bytes or (None, error)."""
    import base64 as b64mod, urllib.request
    image_urls = [u for u in (images or []) if isinstance(u, str) and u.startswith("data:")]
    if not image_urls:
        hero = os.path.join(STAGE, "hero.jpg")
        if not os.path.exists(hero):
            return None, "no reference images sent and hero.jpg missing on the Mac"
        image_urls = ["data:image/jpeg;base64," + b64mod.b64encode(open(hero, "rb").read()).decode()]
    who = ("Show the man from the LAST reference image AND the woman from the reference photo "
           "of her, together, in this scene: " if together else
           "Show the man from the LAST reference image in this scene: ")
    still_prompt = (who + prompt.strip() +
                    ". Keep his EXACT face, hair, and build from that last reference. "
                    "Any earlier reference images are real photos of the setting or of the "
                    "woman in his life - use them for the scene's setting, objects, or her "
                    "presence ONLY when the scene calls for it. WIDE full-length shot: his "
                    "entire body clearly in frame - head, torso, legs, and feet all "
                    "visible, nothing cropped. Photoreal, natural light.")
    try:
        resp = _fal("fal-ai/nano-banana-2/edit",
                    {"prompt": still_prompt, "image_urls": image_urls, "num_images": 1})
    except Exception as e:
        return None, "still compose failed: %s" % e
    still_url = _find_media_url(resp, "*")
    if not still_url:
        return None, "no still url from compose"
    still_path = os.path.join(STAGE, "live-still.jpg")
    urllib.request.urlretrieve(still_url, still_path)
    img = b64mod.b64encode(open(still_path, "rb").read()).decode()
    try:
        resp = _fal("minimax/h3/image-to-video",
                    {"prompt": (motion.strip() + " Locked-off camera." if motion.strip() else
                                "Subtle natural idle motion only: breathing, small weight "
                                "shifts. Locked-off camera. He begins and ends in the same pose."),
                     "image_url": "data:image/jpeg;base64," + img,
                     "resolution": "768P"}, timeout=900)
    except Exception as e:
        return None, "animation failed: %s" % e
    vid_url = _find_media_url(resp, ".mp4")
    if not vid_url:
        return None, "no video url from animation"
    out = os.path.join(STAGE, "live-latest.mp4")
    urllib.request.urlretrieve(vid_url, out)
    # Install locally too: speech renders on THIS box, and it needs the clip
    # plus a close-up crop for the mouth. Stale tracking caches are cleared.
    os.makedirs(CLIPS, exist_ok=True)
    live_clip = os.path.join(CLIPS, "live.mp4")
    live_close = os.path.join(CLIPS, "live-close.mp4")
    import shutil as shm
    shm.copy(out, live_clip)
    for stale in (live_clip + ".boxes.npy", live_close + ".boxes.npy"):
        try: os.unlink(stale)
        except OSError: pass
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", live_clip,
                    "-vf", "crop=iw*0.72:ih*0.55:(iw-iw*0.72)/2:ih*0.02,"
                           "scale=trunc(iw*2/2)*2:trunc(ih*2/2)*2:flags=lanczos",
                    "-an", live_close], env=ENV, capture_output=True)
    try:
        man = json.load(open(MANIFEST))
    except Exception:
        man = {"default": "", "rooms": {}}
    man.setdefault("rooms", {})["live"] = {"clips": ["live.mp4"], "pose": prompt[:120]}
    json.dump(man, open(MANIFEST, "w"), indent=2)
    return open(out, "rb").read(), None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log(fmt % args)

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            n = len([c for c in os.listdir(CLIPS) if c.endswith(".mp4")]) if os.path.isdir(CLIPS) else 0
            self._send(200, json.dumps({"ok": True, "clips": n}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/live":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                prompt = str(body.get("prompt", "")).strip()
                images = body.get("images") or []
                motion = str(body.get("motion", "") or ""); together = bool(body.get("together"))
            except Exception:
                self._send(400, b'{"error":"bad json"}'); return
            if not prompt:
                self._send(400, b'{"error":"no prompt"}'); return
            data, err = live_render(prompt, images, motion, together)
            if err:
                log(err); self._send(500, json.dumps({"error": err}).encode()); return
            self._send(200, data, "video/mp4"); return
        if self.path != "/speak":
            self._send(404, b'{"error":"not found"}'); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            text = str(body.get("text", "")).strip()
            room = str(body.get("room", "")).strip()
        except Exception:
            self._send(400, b'{"error":"bad json"}'); return
        if not text:
            self._send(400, b'{"error":"no text"}'); return
        out, err = render(text, room)
        if err:
            log(err)
            self._send(500, json.dumps({"error": err}).encode()); return
        data = open(out, "rb").read()
        self._send(200, data, "video/mp4")

if __name__ == "__main__":
    os.makedirs(CLIPS, exist_ok=True)
    log("serving on port %d (clips: %s)" % (PORT, CLIPS))
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
