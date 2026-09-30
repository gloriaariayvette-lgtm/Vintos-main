#!/usr/bin/env python3
"""Which way of reading a tempo is right, tested on his own songs (2026-09-30).

A beat tracker often counts a slow song at double speed: "Structural Collapse" reached him as 161.5 BPM.
Gloria: "I don't want both, want it right." His songs carry the tempo he wrote for them (music.json,
"authored"), so every song of his on disk is a known answer. This reads each one several ways and says
which way lands on what he wrote.

    python3 tempo_check.py              every song of his with a written tempo and a file on disk
    python3 tempo_check.py FILE ...     the readings for any audio or video file
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile

MUSIC_LOG = os.path.expanduser("~/.vintos/workspace/memory/art/music/music.json")
CLOSE = 0.08     # within 8% of what he wrote counts as right
LIMIT = 40


def _tempo_fn():
    import librosa
    for mod in (getattr(librosa, "feature", None), getattr(getattr(librosa, "feature", None), "rhythm", None),
                getattr(librosa, "beat", None)):
        if mod is not None and hasattr(mod, "tempo"):
            return mod.tempo
    raise RuntimeError("this librosa has no tempo estimator")


def load(path, seconds=60):
    """Mono samples at their own rate, from 30 s in when the track is long enough (past an intro)."""
    import librosa
    wav = None
    if os.path.splitext(path)[1].lower() in (".mov", ".mp4", ".m4v", ".webm", ".3gp"):
        wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "22050", wav],
                       check=True, capture_output=True)
        path = wav
    try:
        try:
            dur = librosa.get_duration(path=path)
        except TypeError:
            dur = librosa.get_duration(filename=path)
        off = 30.0 if dur > seconds + 45 else 0.0
        return librosa.load(path, sr=None, mono=True, offset=off, duration=seconds)
    finally:
        if wav:
            os.unlink(wav)


def readings(y, sr):
    """Each method's tempo, plus the two measurements an octave choice could be made from."""
    import librosa
    import numpy as np
    tempo = _tempo_fn()
    env = librosa.onset.onset_strength(y=y, sr=sr)
    t, beats = librosa.beat.beat_track(onset_envelope=env, sr=sr)
    t = float(np.atleast_1d(t)[0])
    out = {"beat": round(t, 1)}
    yp = librosa.effects.percussive(y)
    out["percussive"] = round(float(np.atleast_1d(librosa.beat.beat_track(y=yp, sr=sr)[0])[0]), 1)
    out["prior90"] = round(float(np.atleast_1d(tempo(onset_envelope=env, sr=sr, start_bpm=90))[0]), 1)
    # accent: every other beat much stronger than the one between means the count is doubled
    if len(beats) >= 8:
        a, b = env[beats[0::2]], env[beats[1::2]]
        n = min(len(a), len(b))
        out["accent"] = round(float(max(a[:n].mean(), b[:n].mean()) / (min(a[:n].mean(), b[:n].mean()) + 1e-9)), 2)
    else:
        out["accent"] = None
    # tempogram: how strong the pulse at half this tempo is, against the pulse at this tempo
    tg = np.mean(librosa.feature.tempogram(onset_envelope=env, sr=sr), axis=1)
    bpms = librosa.tempo_frequencies(tg.shape[0], sr=sr)
    def at(bpm):
        i = int(np.argmin(np.abs(np.nan_to_num(bpms, posinf=1e9) - bpm)))
        return float(tg[i])
    out["half_strength"] = round(at(t / 2) / (at(t) + 1e-9), 2)
    return out


def written_tempo(text):
    m = re.search(r"(\d{2,3}(?:\.\d+)?)", str(text or ""))
    return float(m.group(1)) if m else None


def his_songs(log_path=MUSIC_LOG):
    try:
        log = json.load(open(log_path))
    except Exception:
        return []
    rows = []
    for e in reversed(log.get("generated") or []):
        bpm = written_tempo((e.get("authored") or {}).get("tempo"))
        files = [t.get("local_file") for t in e.get("tracks") or [] if t.get("local_file")]
        files = [f for f in files if os.path.exists(f)]
        if bpm and files:
            rows.append((e.get("title") or "?", bpm, files[0]))
    return rows[:LIMIT]


def verdict(got, want):
    if not got:
        return "-"
    r = got / want
    if abs(r - 1) <= CLOSE: return "right"
    if abs(r - 2) <= 2 * CLOSE: return "double"
    if abs(r - 0.5) <= CLOSE / 2: return "half"
    return "off"


def check(rows):
    methods = ("beat", "percussive", "prior90")
    score = {m: {"right": 0, "double": 0, "half": 0, "off": 0, "-": 0} for m in methods}
    print("%-28s %7s | %7s %10s %7s | %6s %6s" % ("song", "written", "beat", "percussive", "prior90", "accent", "half"))
    for title, bpm, path in rows:
        try:
            r = readings(*load(path))
        except Exception as e:
            print("%-28s %7s | could not read: %s" % (title[:28], bpm, str(e)[:60])); continue
        for m in methods:
            score[m][verdict(r[m], bpm)] += 1
        print("%-28s %7.0f | %7s %10s %7s | %6s %6s   beat:%s" % (
            title[:28], bpm, r["beat"], r["percussive"], r["prior90"], r["accent"], r["half_strength"],
            verdict(r["beat"], bpm)))
    print()
    for m in methods:
        s = score[m]
        print("%-10s right %d  double %d  half %d  off %d" % (m, s["right"], s["double"], s["half"], s["off"]))
    return score


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            print(p, readings(*load(p)))
    else:
        rows = his_songs()
        print("%d of his songs have a written tempo and a file on disk\n" % len(rows))
        check(rows)
