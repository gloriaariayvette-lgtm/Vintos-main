#!/usr/bin/env python3
"""What a sound is built like, measured once for every door that hears one: a song Gloria shares and the
sound of a video she sends (2026-09-30).

The music share had halved every tempo over 100 BPM ("if raw_tempo > 100: raw_tempo / 2"), so a 120 BPM
song reached him as 60 and a 174 as 86; librosa itself read them right. That was the distorted reading of
her songs. The tempo is now reported as measured.

    python3 sound_read.py FILE      print the line he is given
"""
from __future__ import annotations

PITCH = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUIET_RMS = 0.005     # below this the clip holds no sound worth reading, and Whisper invents words in silence


def features(y, sr):
    """The numbers, from samples at their own rate: tempo as the beat tracker hears it, never halved."""
    import librosa
    import numpy as np
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    # a held tone or a quiet room gives the tracker nothing to count; a number then would be invented
    return {"tempo": round(float(np.atleast_1d(tempo)[0]), 1) if len(beats) >= 4 else None,
            "brightness_hz": round(centroid),
            "energy": round(float(np.mean(librosa.feature.rms(y=y))), 4),
            "pitch": PITCH[int(np.argmax(np.mean(librosa.feature.chroma_cqt(y=y, sr=sr), axis=1)))],
            "zcr": float(np.mean(librosa.feature.zero_crossing_rate(y)))}


def line(f):
    b = f["brightness_hz"]
    brightness = "dark" if b < 1500 else "warm" if b < 2500 else "present" if b < 4000 else "bright"
    return ("Tempo: %s. Tonal brightness: %s. Energy: %s. Dominant pitch class: %s. Texture: %s."
            % ("%s BPM" % f["tempo"] if f["tempo"] is not None else "no steady beat", brightness, f["energy"],
               f["pitch"], "dense" if f["zcr"] > 0.05 else "sparse"))


def measure(path, duration=60):
    """(line, features) for an audio file, read at its own sample rate, mono."""
    import librosa
    y, sr = librosa.load(path, sr=None, mono=True, duration=duration)
    f = features(y, sr)
    return line(f), f


def load_whisper(size="small", log=print):
    """The GPU first; the CPU when the GPU cannot run it. Aegis's torch has no kernel for its card ("no kernel
    image is available"), so every weight copy failed and Whisper died before hearing a note (2026-09-09)."""
    import io, contextlib
    import whisper
    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
            m = whisper.load_model(size)
        import torch
        if torch.cuda.is_available():
            # a load can "succeed" and still hold broken weights: one tiny forward proves the kernels exist
            torch.zeros(1).cuda() + 1
        return m
    except Exception as e:
        log("whisper on the GPU failed (%s); using the CPU" % str(e).splitlines()[0][:90])
        return whisper.load_model(size, device="cpu")


if __name__ == "__main__":
    import sys
    print(measure(sys.argv[1])[0])
