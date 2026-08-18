#!/usr/bin/env python3
"""
voice_kokoro.py — Text-to-speech via Kokoro (local) or fallback.
Handles voice output for Vintos when voice mode is active.
"""
import os, sys, subprocess, tempfile

VOICE_MODEL = os.environ.get("VINTOS_VOICE_MODEL", "am_adam")
VOICE_SPEED = float(os.environ.get("VINTOS_VOICE_SPEED", "1.0"))
KOKORO_PATH = os.path.expanduser("~/.vintos/kokoro")

def speak(text, voice=None, speed=None):
    """Synthesize and play speech."""
    voice = voice or VOICE_MODEL
    speed = speed or VOICE_SPEED
    text = text.strip()
    if not text: return False
    # Try Kokoro python API
    try:
        import sys
        sys.path.insert(0, KOKORO_PATH)
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code="a")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
            audio_chunks.append(audio)
        if audio_chunks:
            import numpy as np
            import soundfile as sf
            audio = np.concatenate(audio_chunks)
            sf.write(out_path, audio, 24000)
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
