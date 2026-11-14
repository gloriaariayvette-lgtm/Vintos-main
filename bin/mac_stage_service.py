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
# His ears for the Local call (Gloria, 4 November): Gemma 4 E4B, audio-native at 25 tokens a second, chosen over
# Gemma 3n E2B / E4B and Qwen2-Audio on the same clips: the best words, the gasp and the pause heard, nothing invented.
EARS_MODEL = os.environ.get("VINTOS_EARS_MODEL", "google/gemma-4-E4B-it")
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
    """Gemma 4 E4B, the complete multimodal checkpoint (transformers on the Mac's GPU); the LM Studio GGUF is text-only."""
    global _ears_pipe
    with _ears_lock:
        if _ears_pipe is None:
            import torch
            from transformers import AutoProcessor, AutoModelForMultimodalLM
            proc = AutoProcessor.from_pretrained(EARS_MODEL)
            model = AutoModelForMultimodalLM.from_pretrained(EARS_MODEL, dtype=torch.bfloat16).to("mps").eval()
            _ears_pipe = (proc, model)
            # The GPU's first audio pass took ~15 s (4 November); spend it here, at the ring, not on her first words.
            try:
                import numpy as np
                warm = [{"role": "user", "content": [{"type": "text", "text": "Transcribe."},
                         {"type": "audio", "audio": (np.random.default_rng(0).standard_normal(16000) * 1e-3).astype("float32")}]}]
                inp = proc.apply_chat_template(warm, tokenize=True, return_dict=True, return_tensors="pt",
                                               add_generation_prompt=True).to("mps")
                with torch.inference_mode():
                    model.generate(**inp, max_new_tokens=4, do_sample=False)
            except Exception as exc:
                log("ears warm-up skipped: %s" % str(exc)[:120])
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

# Google's audio guide (ai.google.dev/gemma/docs/capabilities/audio): the instruction first, then the audio; 16 kHz
# mono float32 in [-1, 1], resampled with a Fourier method; at most 30 s. No name list in the request: given one, the
# model answers with the list instead of what was said (4 November tests). His prompt already hears "Ventos" as him.
HEAR_REQUEST = ("Listen to this recording carefully. Answer in exactly three lines:\n"
    "WORDS: the exact words spoken, nothing else\n"
    "SOUNDS: every non-speech vocal sound you hear (laughter, sigh, breath, gasp, moan, cough, whimper) and where it "
    "happens, and every noticeable pause; or none\n"
    "TONE: the speaker's tone and emotion, in a few words\n"
    "Only report what is audible.")

def _heard_fields(text):
    """WORDS / SOUNDS / TONE lines, tolerant of markdown; the words are required, the rest may be empty."""
    text = str(text or "").replace("**", "").strip()
    out = {}
    for key in ("WORDS", "SOUNDS", "TONE"):
        m = re.search(r"(?im)^\s*[*-]?\s*%s\s*:\s*(.+?)\s*$" % key, text)
        v = m.group(1).strip() if m else ""
        out[key] = v[1:-1].strip() if len(v) > 1 and v[0] == v[-1] == '"' else v   # quoted whole, not a quote inside
    if not out["WORDS"]:
        # Gemma 4 often answers the three lines in order without their labels; exactly three lines are read so,
        # anything else (one line of refusal, an essay) is not taken as her words
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) == 3 and not any(re.match(r"(?i)(words|sounds|tone)\s*:", l) for l in lines):
            out = dict(zip(("WORDS", "SOUNDS", "TONE"), (l.strip('"') if l[:1] == l[-1:] == '"' else l for l in lines)))
    if not out["WORDS"]:
        raise ValueError("the ears gave no words line")
    return out

def _pauses(y, sr=16000):
    """Pauses measured from the waveform itself (no model): silences of 0.4 s or more between sounds."""
    import librosa
    iv = librosa.effects.split(y, top_db=35, frame_length=1024, hop_length=256)
    return [((a1 - b0) / sr, b0 / sr) for (a0, b0), (a1, b1) in zip(iv[:-1], iv[1:]) if (a1 - b0) / sr >= 0.4]

def _hear_audio(y):
    """Give the waveform itself (16 kHz float32) to Gemma 4's audio encoder."""
    import torch
    _ears_load()
    msgs = [{"role": "user", "content": [{"type": "text", "text": HEAR_REQUEST}, {"type": "audio", "audio": y}]}]
    last_error = None
    for attempt in range(2):
        with _ears_lock:
            proc, model = _ears_pipe
            inp = proc.apply_chat_template(msgs, tokenize=True, return_dict=True, return_tensors="pt",
                                           add_generation_prompt=True).to("mps")
            with torch.inference_mode():
                o = model.generate(**inp, max_new_tokens=160 if not attempt else 220, do_sample=False)
            generated = proc.decode(o[0][inp["input_ids"].shape[-1]:], skip_special_tokens=True)
        try: return _heard_fields(generated)
        except Exception as exc: last_error = exc
    raise last_error or ValueError("audio model returned no readable fields")

def hear_pcm(audio_b64, rate=24000):
    import numpy as np, librosa
    pcm = np.frombuffer(base64.b64decode(audio_b64), dtype="<i2").astype("float32") / 32768.0
    y = librosa.resample(pcm, orig_sr=int(rate), target_sr=16000, res_type="scipy") if int(rate) != 16000 else pcm
    y = np.clip(y[:30 * 16000], -1.0, 1.0).astype("float32")
    if len(y) < 1600:
        return {"ok": False, "error": "too short to hear"}
    heard = _hear_audio(y)
    gaps = _pauses(y)
    measured = ", ".join("%.1f s pause at %.1f s" % (d, at) for d, at in gaps) or "none"
    reading = "Sounds: %s. Tone: %s. Pauses measured in the recording: %s." % (
        heard["SOUNDS"] or "none", heard["TONE"] or "not said", measured)
    return {"ok": bool(heard["WORDS"]), "transcript": heard["WORDS"], "audio_reading": reading[:1200],
            "sounds": heard["SOUNDS"], "tone": heard["TONE"],
            "pauses": [{"seconds": round(d, 2), "at": round(at, 2)} for d, at in gaps],
            "ears": "gemma4-e4b-audio-native", "audio_native_gemma": True, "model": EARS_MODEL}

def voice_models(active, evict_ears=False, external_ears=False):
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
        if external_ears:
            if evict_ears:
                _ears_unload()
            actions.append({"model": "native-waveform-service", "ok": True, "detail": "external ears; not warmed here"})
        elif active:
            # Loading and warming the ears takes ~25 s cold: off this request, so the call opens as soon as his voice
            # is ready; a first turn that comes sooner waits on the ears' lock, never on a half-loaded model.
            def _bg():
                try: _ears_load()
                except Exception as exc: log("ears load failed: %s" % str(exc)[:160])
            threading.Thread(target=_bg, daemon=True).start()
        elif evict_ears: _ears_unload()
        if not external_ears:
            actions.append({"model": EARS_MODEL, "ok": True,
                            "detail": "audio-native model %s" %
                                      (("loaded" if _ears_pipe is not None else "loading") if active else
                                       ("evicted" if evict_ears else "kept warm"))})
    except Exception as exc:
        actions.append({"model": EARS_MODEL, "ok": False, "detail": str(exc)[:160]})
    receipt = {"ok": all(a["ok"] for a in actions), "active": bool(active), "actions": actions}
    if external_ears:
        receipt["external_ears"] = True
    return receipt

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
    key = hashlib.sha1(("chatterbox-onyx-v1|%s|%s" % (room, text)).encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, key + ".mp4")
    if os.path.exists(out):
        return out, None
    wav = os.path.join(CACHE, key + ".wav")
    transient_voice = not _chatterbox_call_active
    try:
        try:
            receipt = chatterbox_wav(text, wav)
        except Exception as voice_exc:
            receipt = ({"ok": True, "engine": "kokoro_fallback", "path": wav,
                        "chatterbox_error": str(voice_exc)[:200]}
                       if kokoro_wav(_chatterbox_text(text), wav)
                       else {"ok": False, "engine": "none", "error": str(voice_exc)[:240]})
        if not receipt.get("ok"):
            return None, "voice produced no audio: " + str(receipt.get("error", ""))
    finally:
        if transient_voice: _chatterbox_unload()
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


# The shapes the still composer accepts; a live scene is composed in the one nearest his filmed rooms,
# so it fills her screen the way the rooms do (2026-09-28: a 16:9 render sat small at the top).
RATIOS = ("21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16")


def nearest_ratio(aspect):
    try:
        a = float(aspect)
    except (TypeError, ValueError):
        return None
    if a <= 0: return None
    return min(RATIOS, key=lambda r: abs(a - int(r.split(":")[0]) / int(r.split(":")[1])))


def fit_aspect(path, aspect):
    """Centre-crop a clip to width/height = aspect (a no-op crop when it already is), even dimensions."""
    try:
        a = float(aspect)
    except (TypeError, ValueError):
        return False
    if a <= 0: return False
    tmp = path + ".fit.mp4"
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-vf",
                        "crop='if(gt(iw/ih,%.5f),ih*%.5f,iw)':'if(gt(iw/ih,%.5f),ih,iw/%.5f)',"
                        "scale=trunc(iw/2)*2:trunc(ih/2)*2" % (a, a, a, a),
                        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp], env=ENV, capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        return False
    os.replace(tmp, path)
    return True


def live_render(prompt, images=None, motion="", together=False, aspect=None):
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
        body = {"prompt": still_prompt, "image_urls": image_urls, "num_images": 1}
        if nearest_ratio(aspect): body["aspect_ratio"] = nearest_ratio(aspect)
        resp = _fal("fal-ai/nano-banana-2/edit", body)
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
    if aspect: fit_aspect(out, aspect)       # exactly the rooms' shape, before it is installed or returned
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
            self._send(200, json.dumps({"ok": True, "clips": n, "external_ears": True}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/voice/models":
            try: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except Exception: body = {}
            self._send(200, json.dumps(voice_models(bool(body.get("active")),
                bool(body.get("evict_ears")), bool(body.get("external_ears")))).encode()); return
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
        if self.path == "/dd-token":
            # Mint a fresh DoorDash access token from this Mac's keychain login, for Aegis (which
            # has no keychain). Secret-gated: with no VINTOS_STAGE_SECRET set it refuses, never open.
            secret = os.environ.get("VINTOS_STAGE_SECRET", "")
            if not secret or self.headers.get("X-Vintos-Stage-Secret", "") != secret:
                self._send(403, b'{"ok":false,"error":"forbidden"}'); return
            dd = os.path.expanduser(os.environ.get("DD_CLI_BIN", "~/.local/bin/dd-cli"))
            try:
                proc = subprocess.run([dd, "export-token"], capture_output=True, text=True, timeout=180, env=ENV)
                tok = (proc.stdout or "").strip()
                if tok.startswith("{"):
                    try: tok = str((json.loads(tok) or {}).get("access_token") or (json.loads(tok) or {}).get("token") or "").strip()
                    except Exception: pass
                if proc.returncode != 0 or not tok:
                    self._send(502, json.dumps({"ok": False, "error": (proc.stderr or proc.stdout or "no token")[:200]}).encode()); return
                self._send(200, json.dumps({"ok": True, "token": tok}).encode())
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)[:200]}).encode())
            return
        if self.path == "/live":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                prompt = str(body.get("prompt", "")).strip()
                images = body.get("images") or []
                motion = str(body.get("motion", "") or ""); together = bool(body.get("together"))
                aspect = body.get("aspect")
            except Exception:
                self._send(400, b'{"error":"bad json"}'); return
            if not prompt:
                self._send(400, b'{"error":"no prompt"}'); return
            data, err = live_render(prompt, images, motion, together, aspect)
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
