#!/usr/bin/env python3
"""
voice_kokoro.py — Text-to-speech via Kokoro (local) or fallback.
Handles voice output for Vintos when voice mode is active.
"""
import os, sys, subprocess, tempfile

VOICE_MODEL = os.environ.get("VINTOS_KOKORO_FALLBACK_VOICE", "am_michael")
VOICE_SPEED = float(os.environ.get("VINTOS_VOICE_SPEED", "1.0"))
KOKORO_PATH = os.path.expanduser("~/.vintos/kokoro")

def render_to_file(text, out_path, voice=None, speed=None):
    """Fallback renderer used only when the preferred Orpheus lane is unavailable."""
    voice = voice or VOICE_MODEL; speed = speed or VOICE_SPEED; text = str(text or "").strip()
    if not text: return False
    try:
        sys.path.insert(0, KOKORO_PATH)
        from kokoro import KPipeline
        import numpy as np, soundfile as sf
        chunks = [audio for _, _, audio in KPipeline(lang_code="a")(text, voice=voice, speed=speed, split_pattern=r"\n+")]
        if not chunks: return False
        sf.write(out_path, np.concatenate(chunks), 24000); return True
    except Exception: return False


def speak(text, voice=None, speed=None):
    """Synthesize and play speech."""
    voice = voice or VOICE_MODEL
    speed = speed or VOICE_SPEED
    text = text.strip()
    if not text: return False
    # review 170: a spoken line is foreground - it never waits, and it marks the machine live so
    # background renders yield. The wav path and playback are unchanged (review 173).
    try:
        import sys as _cas; _cas.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        from compute_admission import touch_foreground as _tf, record as _rec
        _tf(); _rec("voice-orpheus", "foreground", provider="local", model="orpheus", stage="speak")
    except Exception:
        pass
    # Compatibility entry point, preferred engine changed to Orpheus. Its own
    # fallback calls render_to_file above without recursing into speak().
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        import voice_orpheus
        receipt = voice_orpheus.speak_to_file(text, out_path, speed=speed, fallback=True)
        if receipt.get("ok"):
            subprocess.run(["aplay", out_path], check=False, capture_output=True)
            os.unlink(out_path)
            return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[voice-kokoro] Kokoro error: {e}", file=sys.stderr)
    # Fallback: espeak
    try:
        subprocess.run(["espeak", "-s", "150", "-v", "en+m3", text], check=False, capture_output=True)
        return True
    except: pass
    # Last resort: print
    print(f"[VOICE] {text}")
    return False

def speak_from_file(path):
    """Read and speak a file."""
    try:
        text = open(path).read().strip()
        if text:
            return speak(text)
    except Exception as e:
        print(f"[voice-kokoro] File error: {e}", file=sys.stderr)
    return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--file" and len(sys.argv) > 2:
            speak_from_file(sys.argv[2])
        else:
            speak(" ".join(sys.argv[1:]))
    else:
        # Read from stdin
        text = sys.stdin.read().strip()
        if text:
            speak(text)
