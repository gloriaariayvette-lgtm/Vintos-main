#!/usr/bin/env python3
"""A short phrase of actual notes, typed and checked, written as a MIDI file (his motif notebook, 25 October;
proposal 02, "Musical motifs he can return to", approved by Gloria).

A score is one voice on the house piano tone: a declared tempo (one or more tempo settings, in beats from the
start), a declared meter, and notes with pitch, onset, duration and velocity. Onset and duration are in beats
(quarter notes). Nothing in a score is code; it is numbers, and every number is checked before a byte of MIDI is
written:

  - every value finite (no NaN, no infinity), every pitch a piano key (MIDI 21-108), every velocity 1-127;
  - every note released: a duration is required and must be longer than nothing (no negative durations);
  - one voice: a note begins no earlier than the one before it ends (a repeated pitch may follow at once);
  - at most 8 bars, 64 note events and 29 seconds of sound, so the rendered audio, with the renderer's one-second
    tail, stays within 30 seconds.

The MIDI goes through the existing verifier and CPU renderer (midi_check.py), not a new one.

    python3 motif_score.py <score.json> <out.mid>     check a score and write its MIDI
"""
from __future__ import annotations
import json
import math
import struct
import sys

TICKS = 480                  # ticks per beat
MAX_BARS = 8
MAX_NOTES = 64
MAX_SECONDS = 29.0           # sounding length; the renderer adds a one-second tail, so audio stays <= 30 s
LOW, HIGH = 21, 108          # the house piano's keys, within the MIDI range
MIN_BPM, MAX_BPM = 20.0, 300.0
METERS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
DENOMINATORS = {1, 2, 4, 8, 16}
ORIGIN_CHARS = 200
TITLE_CHARS = 80


class ScoreError(ValueError):
    """A score that cannot be written. The message says which value and why, never the whole score."""


def _finite(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoreError("%s is not a number" % what)
    if not math.isfinite(float(value)):
        raise ScoreError("%s is not a finite number" % what)
    return float(value)


def _tick(beats):
    return int(round(beats * TICKS))


def parse_meter(text):
    """'3/4' -> (3, 4)."""
    try:
        num, den = str(text).strip().split("/")
        num, den = int(num), int(den)
    except (ValueError, TypeError):
        raise ScoreError("meter must look like 4/4")
    if num not in METERS or den not in DENOMINATORS:
        raise ScoreError("meter %d/%d is outside what the notebook writes" % (num, den))
    return num, den


def beats_per_bar(meter):
    num, den = parse_meter(meter)
    return num * 4.0 / den


def normalise_tempos(tempo):
    """A tempo is one number (bpm) or a list of [beat, bpm] settings, the first at beat 0."""
    if isinstance(tempo, (int, float)) and not isinstance(tempo, bool):
        rows = [[0, tempo]]
    elif isinstance(tempo, (list, tuple)) and tempo:
        rows = [list(r) if isinstance(r, (list, tuple)) else r for r in tempo]
    else:
        raise ScoreError("tempo must be a number or a list of [beat, bpm] settings")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 2:
            raise ScoreError("tempo setting %d must be [beat, bpm]" % (i + 1))
        at = _finite(row[0], "tempo setting %d's beat" % (i + 1))
        bpm = _finite(row[1], "tempo setting %d's bpm" % (i + 1))
        if at < 0:
            raise ScoreError("tempo setting %d begins before the phrase" % (i + 1))
        if not MIN_BPM <= bpm <= MAX_BPM:
            raise ScoreError("tempo setting %d is %g bpm; the notebook writes %g-%g" % (i + 1, bpm, MIN_BPM, MAX_BPM))
        out.append([at, bpm])
    if out[0][0] != 0:
        raise ScoreError("the first tempo setting must be at beat 0")
    for a, b in zip(out, out[1:]):
        if b[0] <= a[0]:
            raise ScoreError("tempo settings must move forward in time")
    return out


def seconds_at(beat, tempos):
    """The exact time of a beat, through every tempo setting before it."""
    t, last, bpm = 0.0, 0.0, tempos[0][1]
    for at, b in tempos:
        if at >= beat:
            break
        t += (at - last) * 60.0 / bpm
        last, bpm = at, b
    return t + (beat - last) * 60.0 / bpm


def _note(raw, i):
    if isinstance(raw, (list, tuple)):
        if len(raw) != 4:
            raise ScoreError("note %d must be [pitch, onset, duration, velocity]" % i)
        raw = dict(zip(("pitch", "onset", "duration", "velocity"), raw))
    if not isinstance(raw, dict):
        raise ScoreError("note %d is not a note" % i)
    for key in ("pitch", "onset", "duration", "velocity"):
        if key not in raw or raw[key] is None:
            raise ScoreError("note %d has no %s%s" % (i, key, " (every note must be released)" if key == "duration" else ""))
    pitch = _finite(raw["pitch"], "note %d's pitch" % i)
    vel = _finite(raw["velocity"], "note %d's velocity" % i)
    onset = _finite(raw["onset"], "note %d's onset" % i)
    dur = _finite(raw["duration"], "note %d's duration" % i)
    if pitch != int(pitch) or not LOW <= pitch <= HIGH:
        raise ScoreError("note %d's pitch must be a whole MIDI number %d-%d" % (i, LOW, HIGH))
    if vel != int(vel) or not 1 <= vel <= 127:
        raise ScoreError("note %d's velocity must be a whole number 1-127" % i)
    if onset < 0:
        raise ScoreError("note %d begins before the phrase" % i)
    if dur < 0:
        raise ScoreError("note %d has a negative duration" % i)
    if _tick(dur) < 1:
        raise ScoreError("note %d has no length (every note must sound and be released)" % i)
    return {"pitch": int(pitch), "onset": _tick(onset) / TICKS, "duration": _tick(dur) / TICKS, "velocity": int(vel)}


def validate(score):
    """The score, normalised (onsets and durations on the tick grid), or ScoreError naming the first fault."""
    if not isinstance(score, dict):
        raise ScoreError("a score is an object")
    meter = str(score.get("meter") or "4/4")
    bar = beats_per_bar(meter)
    tempos = normalise_tempos(score.get("tempo", 90))
    notes = score.get("notes")
    if not isinstance(notes, list) or not notes:
        raise ScoreError("a score needs at least one note")
    if len(notes) > MAX_NOTES:
        raise ScoreError("%d notes; a phrase holds at most %d" % (len(notes), MAX_NOTES))
    clean = sorted((_note(n, i + 1) for i, n in enumerate(notes)), key=lambda n: (n["onset"], n["pitch"]))
    for i, (a, b) in enumerate(zip(clean, clean[1:])):
        if _tick(b["onset"]) < _tick(a["onset"] + a["duration"]):
            raise ScoreError("two notes sound at once near beat %g; the notebook writes one voice" % b["onset"])
    end = max(n["onset"] + n["duration"] for n in clean)
    if end > MAX_BARS * bar + 1e-9:
        raise ScoreError("the phrase runs %.2f bars; at most %d" % (end / bar, MAX_BARS))
    if seconds_at(end, tempos) > MAX_SECONDS + 1e-9:
        raise ScoreError("the phrase sounds for %.1f s; at most %g" % (seconds_at(end, tempos), MAX_SECONDS))
    tempos = [t for t in tempos if t[0] == 0 or t[0] < end]     # a setting after the last note changes nothing
    out ={"tempo": tempos, "meter": meter, "notes": clean}
    for key, cap in (("title", TITLE_CHARS),):
        if score.get(key) is not None:
            out[key] = str(score[key]).strip()[:cap]
    return out


def length_beats(score):
    return max(n["onset"] + n["duration"] for n in score["notes"])


def length_seconds(score):
    return seconds_at(length_beats(score), score["tempo"])


def bars(score):
    return length_beats(score) / beats_per_bar(score["meter"])


def timed(score):
    """[(start_s, end_s, pitch, velocity)] from a validated score: what the MIDI should say."""
    tempos = score["tempo"]
    return [(seconds_at(n["onset"], tempos), seconds_at(n["onset"] + n["duration"], tempos), n["pitch"], n["velocity"])
            for n in score["notes"]]


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def to_midi(score):
    """A format-0 standard MIDI file: tempo settings, the meter, and every note-on with its note-off. The score is
    validated first; an invalid score writes nothing."""
    score = validate(score)
    num, den = parse_meter(score["meter"])
    events = []                                       # (tick, order, bytes); order puts offs before ons on a tick
    for at, bpm in score["tempo"]:
        us = int(round(60_000_000 / bpm))
        events.append((_tick(at), 0, bytes([0xFF, 0x51, 3]) + us.to_bytes(3, "big")))
    events.append((0, 0, bytes([0xFF, 0x58, 4, num, int(math.log2(den)), 24, 8])))
    events.append((0, 0, bytes([0xC0, 0])))           # one fixed instrument: piano
    for n in score["notes"]:
        on, off = _tick(n["onset"]), _tick(n["onset"] + n["duration"])
        events.append((on, 2, bytes([0x90, n["pitch"], n["velocity"]])))
        events.append((off, 1, bytes([0x80, n["pitch"], 0])))
    events.sort(key=lambda e: (e[0], e[1]))
    track, last = b"", 0
    for tick, _, data in events:
        track += _vlq(tick - last) + data
        last = tick
    track += _vlq(0) + bytes([0xFF, 0x2F, 0])
    return (b"MThd" + struct.pack(">IHHH", 6, 0, 1, TICKS)
            + b"MTrk" + struct.pack(">I", len(track)) + track)


def from_midi(path):
    """Read a MIDI file back into notes through the existing verifier. A file with any event problem (a note never
    released, a release with nothing sounding, a zero-length note) is refused. -> (ticks_per_beat, timed notes,
    tempos) where timed is [(start_s, end_s, pitch, velocity)]."""
    import midi_check
    div, events, tempos = midi_check.read(path)
    notes, problems, _ = midi_check.verify(div, events, tempos)
    if problems:
        raise ScoreError("the MIDI has %d event problem(s): %s" % (len(problems), problems[0]))
    return div, [(s, e, p, v) for s, e, _, p, v in notes], tempos


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    try:
        data = to_midi(json.load(open(sys.argv[1])))
    except (ScoreError, ValueError) as exc:
        print("score refused: %s" % exc)
        raise SystemExit(1)
    with open(sys.argv[2], "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes)" % (sys.argv[2], len(data)))
