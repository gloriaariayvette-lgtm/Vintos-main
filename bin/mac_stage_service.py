#!/usr/bin/env python
"""mac_stage_service.py - Vintos's audio/visual stage, hosted on the Mac.

Renders his speech clips locally: kokoro (voice) + Wav2Lip (mouth) over the
room loops synced from Aegis into ~/VintosStage/clips. Aegis's server calls
POST /speak and gets the finished mp4 back; nothing renders on Aegis.

Runs under the Wav2Lip venv python (which has torch, kokoro, soundfile).
Started by the LaunchAgent com.vintos.stage (port 8511).
"""
import os, sys, json, hashlib, subprocess, base64, tempfile, wave, threading, gc, re
from http.server import HTTPServer, BaseHTTPRequestHandler

def _sg_write(_p, _o, _who="organ"):
    """review 46: this store has more than one writing organ; the write goes through the store lock."""
    try:
        import sys as _s, os as _o2
        _s.path.insert(0, _o2.path.dirname(_o2.path.abspath(__file__)))
        _s.path.insert(0, _o2.path.expanduser("~/.vintos/workspace/scripts"))
        from store_guard import write_json as _wj
        _wj(_p, _o, reader=_who); return True
    except Exception:
        return False


HOME = os.path.expanduser("~")
STAGE = os.path.join(HOME, "VintosStage")
CLIPS = os.path.join(STAGE, "clips")
CACHE = os.path.join(STAGE, "speech-cache")
MANIFEST = os.path.join(STAGE, "manifest.json")
W2L = os.path.join(HOME, "Wav2Lip")
W2L_PY = os.path.join(W2L, ".venv", "bin", "python")
W2L_CKPT = os.path.join(W2L, "checkpoints", "wav2lip_gan.pth")
VOICE = os.environ.get("VINTOS_KOKORO_FALLBACK_VOICE", "am_onyx")
PORT = int(os.environ.get("VINTOS_STAGE_PORT", "8511"))
LM_BASE = os.environ.get("VINTOS_MAC_LM_BASE", "http://127.0.0.1:1234").rstrip("/")
EARS_MODEL = os.environ.get("VINTOS_EARS_MODEL", "unsloth/gemma-3n-E2B-it")
LMS = os.path.expanduser("~/.lmstudio/bin/lms")
CHATTERBOX_MODEL = os.environ.get("VINTOS_CHATTERBOX_MODEL",
    os.path.expanduser("~/.lmstudio/models/mlx-community/chatterbox-turbo-4bit"))
CHATTERBOX_REFERENCE = os.environ.get("VINTOS_CHATTERBOX_REFERENCE",
    os.path.join(STAGE, "voice-reference-onyx.wav"))

# LaunchAgents don't inherit the shell PATH; Wav2Lip's last step shells out to
# ffmpeg, so make sure the common install dirs are reachable.
ENV = dict(os.environ)
ENV["PATH"] = ENV.get("PATH", "") + ":/usr/local/bin:/opt/homebrew/bin"
os.environ["PATH"] = ENV["PATH"]
import shutil as _sh
FFMPEG = _sh.which("ffmpeg") or "/usr/local/bin/ffmpeg"

_pipeline = None
_ears_pipe = None
_ears_lock = threading.RLock()
_chatterbox = None
_chatterbox_lock = threading.RLock()
_chatterbox_call_active = False

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

_CHATTERBOX_CUES = "laugh|chuckle|sigh|gasp|cough|clear throat|sniff|groan|shush"
_CHATTERBOX_CUE_SET = set(_CHATTERBOX_CUES.split("|"))

def _chatterbox_text(text):
    """Preserve only native Chatterbox controls; stage prose is never spoken."""
    out = str(text or "")
    # Accept the earlier Orpheus spelling while callers roll forward.
    out = re.sub(r"<(giggle|sniffle)\s*>",
                 lambda m: "[chuckle]" if m.group(1).lower() == "giggle" else "[sniff]",
                 out, flags=re.I)
    out = re.sub(r"<(%s)\s*>" % _CHATTERBOX_CUES,
                 lambda m: "[%s] " % m.group(1).lower(), out, flags=re.I)
    out = re.sub(r"</(?:%s|giggle|sniffle)\s*>", " ", out, flags=re.I)
    out = re.sub(r"\[(pause|beat)\]", ", ", out, flags=re.I)
    out = re.sub(r"\[(long[- ]pause)\]", "... ", out, flags=re.I)
    out = re.sub(r"\[(breath|inhale|exhale)\]", "[sigh]", out, flags=re.I)
    out = re.sub(r"\[([^\]\n]{1,240})\]",
                 lambda m: "[%s]" % m.group(1).lower()
                 if m.group(1).lower() in _CHATTERBOX_CUE_SET else " ", out)
    out = re.sub(r"</?[A-Za-z][^>\n]{0,80}>", " ", out)
    out = re.sub(r"\*+", "", out)
    out = " ".join(out.split())
    return re.sub(r"\s+([,.;!?])", r"\1", out)

def _chatterbox_load():
    """Keep the small MLX voice hot only for the lifetime of a local call."""
    global _chatterbox
    with _chatterbox_lock:
        if _chatterbox is None:
            if not os.path.isdir(CHATTERBOX_MODEL):
                raise FileNotFoundError("Chatterbox model is not installed")
            if not os.path.isfile(CHATTERBOX_REFERENCE):
                raise FileNotFoundError("Onyx voice reference is not installed")
            from mlx_audio.tts.utils import load_model
            _chatterbox = load_model(model_path=CHATTERBOX_MODEL)
            _chatterbox.prepare_conditionals(CHATTERBOX_REFERENCE)
        return _chatterbox

def _chatterbox_unload():
    global _chatterbox
    with _chatterbox_lock:
        _chatterbox = None
        gc.collect()
        try:
            import mlx.core as mx
            mx.clear_cache()
        except Exception: pass

def chatterbox_wav(text, out_path):
    """Local-call voice: Onyx timbre cloned once, native cues rendered in one pass."""
    import numpy as np, soundfile as sf
    with _chatterbox_lock:
        model = _chatterbox_load()
        chunks = [np.array(result.audio, dtype=np.float32) for result in model.generate(
            text=_chatterbox_text(text)[:5000], temperature=0.7, top_p=0.95,
            top_k=1000, repetition_penalty=1.2, max_tokens=800)]
    if not chunks: return {"ok": False, "engine": "chatterbox_turbo", "error": "no audio"}
    sf.write(out_path, np.concatenate(chunks), model.sample_rate, subtype="PCM_16")
    return {"ok": True, "engine": "chatterbox_turbo", "voice": "onyx-reference",
            "path": out_path}

def orpheus_wav(text, out_path, voice=None, speed=None):
    """Preferred voice. The Mac owns SNAC decoding; Kokoro is the outage fallback."""
    sys.path.insert(0, STAGE); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import voice_orpheus
    receipt = voice_orpheus.speak_to_file(text, out_path, voice=voice, speed=speed,
                                           local_decode=True, fallback=False)
    if receipt.get("ok"): return receipt
    if kokoro_wav(text, out_path):
        return {"ok": True, "engine": "kokoro_fallback", "path": out_path,
                "orpheus_error": receipt.get("error", "")}
    return receipt

def _ears_load():
    """Load a complete multimodal checkpoint; the LM Studio GGUF is text-only."""
    global _ears_pipe
    with _ears_lock:
        if _ears_pipe is None:
            import torch
            from transformers import pipeline
            _ears_pipe = pipeline("image-text-to-text", model=EARS_MODEL,
                                  device="mps", dtype=torch.bfloat16)
        return True

def _ears_unload():
    global _ears_pipe
    with _ears_lock:
        _ears_pipe = None
        gc.collect()
        try:
            import torch
            torch.mps.empty_cache()
        except Exception: pass

def _heard_fields(text):
    text = str(text or "").replace("```json", "").replace("```", "").strip()
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            value = json.loads(text[a:b+1])
            if value.get("transcript") and value.get("audio_reading"): return value
        except Exception: pass
    import re
    trans = re.search(r"(?is)transcription(?: of recording)?\s*:\s*[\"']?(.+?)[\"']?\s*(?:\n|$)", text)
    reading = re.search(r"(?is)speaker(?:'s)? delivery description\s*:\s*(.+)$", text)
    if not trans or not reading: raise ValueError("audio model omitted transcript or delivery reading")
    return {"transcript": trans.group(1).strip(" \t\r\n\"'"),
            "audio_reading": reading.group(1).strip()}

# Same transcription vocabulary the hosted lanes prime their transcriber with
# (server.py's OpenAI lane: "Expect these names and words: ..."). Copied here so the
# local ears reach for the same proper nouns instead of mangling them; kept as a
# literal copy for now (not yet a shared source — keep in sync with server.py).
VOICE_VOCAB = "Vintos, Velaris, Gloria, Eve, Kevin, Aegis, Velqan, Plithra, Thirveel"

def _hear_audio(wav_path):
    """Give the waveform itself to Gemma 3n's USM audio tower."""
    _ears_load()
    request = ('Listen to the recording itself. You may hear these names and words — '
        'transcribe them correctly when you hear them: ' + VOICE_VOCAB + '. Return JSON only as '
        '{"transcript":"exact words","audio_reading":"one concise sentence about audible '
        'inflection, tone, pace, emphasis, hesitation, laughter, or breath"}. Preserve '
        'explicit language. Do not infer anything that is not audible.')
    messages = [{"role":"user", "content":[{"type":"audio", "audio":wav_path},
                                             {"type":"text", "text":request}]}]
    last_error = None
    for attempt in range(2):
        with _ears_lock:
            # A live turn needs a transcript plus a compact delivery reading,
            # not an essay. Retry one malformed first generation while the
            # model is already warm; the old path exposed that parse miss as a
            # phone-visible 500 and made Gloria start the call over.
            result = _ears_pipe(text=messages, max_new_tokens=140 if not attempt else 180)
        generated = result[0]["generated_text"][-1]["content"]
        try: return _heard_fields(generated)
        except Exception as exc: last_error = exc
    raise last_error or ValueError("audio model returned no readable fields")

def hear_pcm(audio_b64, rate=24000):
    pcm = base64.b64decode(audio_b64)
    fd, raw_path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    fd, wav_path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        with wave.open(raw_path, "wb") as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(int(rate)); out.writeframes(pcm)
        # The audio tower needs enough frames for its convolutional subsampler.
        # Normalize to its documented 16 kHz mono input and pad short turns only.
        subprocess.run([FFMPEG,"-y","-loglevel","error","-i",raw_path,
            "-af","apad=whole_dur=4","-t","30","-ar","16000","-ac","1",wav_path],
            check=True, timeout=20, env=ENV)
        heard = _hear_audio(wav_path); transcript = str(heard.get("transcript", "")).strip()
        reading = str(heard.get("audio_reading", "")).strip()[:1200]
        return {"ok": bool(transcript), "transcript": transcript,
                "audio_reading": reading, "ears": "gemma3n-audio-native-mlx-vlm",
                "audio_native_gemma": True, "model": EARS_MODEL}
    finally:
        for path in (raw_path, wav_path):
            try: os.unlink(path)
            except OSError: pass

def voice_models(active, evict_ears=False):
    """The live voice is call-scoped; the ears stay warm unless a heavy bench evicts them."""
    global _chatterbox_call_active
    actions = []
    try:
        if active:
            _chatterbox_load(); _chatterbox_call_active = True
        else:
            _chatterbox_call_active = False; _chatterbox_unload()
        actions.append({"model": "chatterbox-turbo-4bit", "ok": True,
                        "detail": "MLX voice %s" % ("loaded" if active else "unloaded")})
    except Exception as exc:
        actions.append({"model": "chatterbox-turbo-4bit", "ok": False,
                        "detail": str(exc)[:160]})
    try:
        if active: _ears_load()
        elif evict_ears: _ears_unload()
        actions.append({"model": EARS_MODEL, "ok": True,
                        "detail": "audio-native model %s" %
                                  ("loaded" if active else ("evicted" if evict_ears else "kept warm"))})
    except Exception as exc:
        actions.append({"model": EARS_MODEL, "ok": False, "detail": str(exc)[:160]})
    return {"ok": all(a["ok"] for a in actions), "active": bool(active), "actions": actions}

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
        receipt = orpheus_wav(text, wav)
        if not receipt.get("ok"):
            return None, "voice produced no audio: " + str(receipt.get("error", ""))
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
    (_sg_write(MANIFEST, man, "mac_stage_service.py") or json.dump(man, open(MANIFEST, "w"), indent=2))
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
        if self.path == "/voice/models":
            try: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except Exception: body = {}
            self._send(200, json.dumps(voice_models(bool(body.get("active")),
                bool(body.get("evict_ears")))).encode()); return
        if self.path == "/listen":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                result = hear_pcm(str(body.get("audio", "")), int(body.get("sample_rate", 24000)))
                self._send(200 if result.get("ok") else 422, json.dumps(result).encode())
            except Exception as exc: self._send(500, json.dumps({"ok":False,"error":str(exc)[:300]}).encode())
            return
        if self.path == "/tts":
            transient_voice = not _chatterbox_call_active
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                fd, out = tempfile.mkstemp(suffix=".wav"); os.close(fd)
                try:
                    receipt = chatterbox_wav(str(body.get("text", "")), out)
                except Exception as voice_exc:
                    receipt = ({"ok": True, "engine": "kokoro_fallback", "path": out,
                                "chatterbox_error": str(voice_exc)[:200]}
                               if kokoro_wav(_chatterbox_text(str(body.get("text", ""))), out)
                               else {"ok": False, "engine": "none", "error": str(voice_exc)[:240]})
                if not receipt.get("ok"): self._send(500, json.dumps(receipt).encode()); return
                data = open(out,"rb").read(); os.unlink(out)
                self.send_response(200); self.send_header("Content-Type","audio/wav")
                self.send_header("X-Vintos-Voice", receipt.get("engine","unknown")); self.send_header("Content-Length",str(len(data)))
                self.end_headers(); self.wfile.write(data)
            except Exception as exc: self._send(500, json.dumps({"ok":False,"error":str(exc)[:300]}).encode())
            finally:
                if transient_voice: _chatterbox_unload()
            return
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
