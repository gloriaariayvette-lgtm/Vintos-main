#!/usr/bin/env python3
"""A video Gloria sends him in the avatar chat (2026-09-30: "I'd like to send him videos there").

The clip is taken apart the way the music share takes a song apart: its sound is pulled out with ffmpeg
at a fixed rate, mono, then Whisper hears any words and sound_read measures how the sound is built
(the same reading the music share uses, tempo as measured, never halved). Frames are cut from across the
whole clip, in order, for his eyes; the server looks at them, because the eyes live there.

Run apart from the server (Whisper loads torch, and a CPU transcription takes minutes):

    python3 video_share.py CLIP --frames-dir DIR     prints one line: RESULT {json}
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

AUDIO_RATE = 22050     # librosa's own rate; Whisper resamples from the file itself
HEAR_SECONDS = 300     # words from the first five minutes; a longer clip is still seen whole
FRAME_EVERY = 5.0
FRAMES_MIN, FRAMES_MAX = 3, 8
NO_SPEECH = 0.6


def log(msg):
    print("[VideoShare] " + msg, file=sys.stderr, flush=True)


def _run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(clip):
    """(duration seconds, has an audio track)."""
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
              "-of", "json", clip], timeout=60)
    d = json.loads(r.stdout or "{}")
    dur = float((d.get("format") or {}).get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in d.get("streams") or [])
    return dur, has_audio


def extract_audio(clip, out_wav, seconds=HEAR_SECONDS):
    """The sound track as mono WAV at AUDIO_RATE; None when there is none."""
    r = _run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", clip, "-vn", "-ac", "1", "-ar", str(AUDIO_RATE),
              "-t", str(seconds), "-f", "wav", out_wav])
    return out_wav if r.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000 else None


def frame_times(duration):
    n = max(FRAMES_MIN, min(FRAMES_MAX, int(round(duration / FRAME_EVERY)) or FRAMES_MIN))
    return [round((i + 0.5) * duration / n, 2) for i in range(n)]


def extract_frames(clip, duration, out_dir):
    """[(t, path)] across the whole clip, in order, 768 px wide (the phone's rotation already applied)."""
    frames = []
    for i, t in enumerate(frame_times(duration)):
        p = os.path.join(out_dir, "frame-%02d.jpg" % i)
        r = _run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(t), "-i", clip, "-frames:v", "1",
                  "-vf", "scale=768:-2", "-q:v", "3", p], timeout=60)
        if r.returncode == 0 and os.path.exists(p):
            frames.append((t, p))
    return frames


def hear(wav, loaded=None):
    """The words spoken, or "" when none: segments Whisper itself marks as likely not speech are dropped,
    since on music or room noise it writes lines nobody said."""
    model = loaded or __import__("sound_read").load_whisper(log=log)
    out = model.transcribe(wav, fp16=False, condition_on_previous_text=False)
    kept = [s.get("text", "").strip() for s in out.get("segments") or []
            if float(s.get("no_speech_prob") or 0) < NO_SPEECH]
    return " ".join(t for t in kept if t)[:2500]


def watch(clip, frames_dir, measure=None, whisper=None):
    """Everything the clip gives him except sight: duration, words, the sound's build, and the frames."""
    dur, has_audio = probe(clip)
    result = {"duration": round(dur, 1), "has_audio": has_audio, "speech": "", "sound": "", "quiet": False,
              "frames": [{"t": t, "path": p} for t, p in extract_frames(clip, dur, frames_dir)]}
    if not has_audio:
        return result
    tmp = tempfile.mkdtemp(prefix="video-sound-")
    try:
        wav = extract_audio(clip, os.path.join(tmp, "sound.wav"))
        if not wav:
            log("the audio track would not extract"); return result
        try:
            line, f = (measure or __import__("sound_read").measure)(wav)
            result["quiet"] = f["energy"] < __import__("sound_read").QUIET_RMS
            if not result["quiet"]:
                result["sound"] = line
        except Exception as e:
            log("sound reading failed: %s" % e)
        if not result["quiet"]:
            try:
                result["speech"] = hear(wav, loaded=whisper)
            except Exception as e:
                log("whisper failed: %s" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def compose(watched, seen, message):
    """The turn he receives: what his eyes saw, what he heard, and her words, each marked for what it is."""
    parts = ["[Gloria sent you a video, %.0f seconds long.]" % watched.get("duration", 0)]
    parts.append("[What your eyes saw, across the clip:]\n" + (seen.strip() or "(the frames could not be seen)"))
    if not watched.get("has_audio"):
        parts.append("[It has no sound.]")
    elif watched.get("quiet"):
        parts.append("[Its sound is near silent.]")
    else:
        if watched.get("speech"):
            parts.append("[Words heard in it (a transcription, may mishear):] " + watched["speech"])
        else:
            parts.append("[No words heard in it.]")
        if watched.get("sound"):
            parts.append("[How its sound is built (measured):] " + watched["sound"])
    parts.append("[Gloria's message with the video:] " + str(message or ""))
    return "\n\n".join(parts)


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[2] != "--frames-dir":
        print(__doc__); sys.exit(2)
    print("RESULT " + json.dumps(watch(sys.argv[1], sys.argv[3])), flush=True)
