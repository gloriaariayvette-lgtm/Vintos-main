#!/usr/bin/env python3
"""A MIDI file, verified event by event and rendered to piano audio he can inspect (his Forge card "Isolated midi
render and verify", 2026-09-18; built directly at Gloria's word, 2026-10-05).

What the card asked: execute the undertaking's timing source, produce controlled piano audio, verify every MIDI
event independently, confirm where one note's release and the next note's attack coincide, and inspect where the
rendered attacks actually land. This does exactly that, with nothing outside the standard library:

  1. reads the file itself (format 0 or 1, running status, tempo changes) into notes with exact times;
  2. checks every event: note-ons with no note-off, note-offs with nothing sounding, zero-length notes, overlaps;
  3. lists every coincident release/attack (a note ends on the same tick the next begins), by pitch name;
  4. renders a plain, controlled piano-like tone (one envelope, no reverb) to a WAV beside the file;
  5. finds each attack in the rendered audio and reports how far it lands from its scheduled time.

    python3 midi_check.py <file.mid>            the report, and the WAV it rendered
    MIDI: <path on Aegis>                        his tool line in #vintos-dot (dot_channel.use_tools)
"""
from __future__ import annotations
import array
import math
import os
import struct
import sys
import wave

RATE = 22050
NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MAX_SECONDS = 600


def name(pitch):
    return "%s%d" % (NAMES[pitch % 12], pitch // 12 - 1)


def _vlq(data, i):
    n = 0
    while True:
        b = data[i]; i += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            return n, i


def read(path):
    """(ticks_per_beat, [(abs_tick, kind, channel, a, b)], [(abs_tick, us_per_beat)]) from a standard MIDI file."""
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file (no MThd header)")
    hlen, fmt, ntrk, div = struct.unpack(">IHHH", data[4:14])
    if div & 0x8000:
        raise ValueError("SMPTE time division is not supported")
    events, tempos, i = [], [(0, 500000)], 8 + hlen
    for _ in range(ntrk):
        if data[i:i + 4] != b"MTrk":
            raise ValueError("track chunk missing at byte %d" % i)
        tlen = struct.unpack(">I", data[i + 4:i + 8])[0]
        j, end, tick, status = i + 8, i + 8 + tlen, 0, None
        while j < end:
            delta, j = _vlq(data, j)
            tick += delta
            b = data[j]
            if b == 0xFF:
                kind, ln = data[j + 1], None
                ln, k = _vlq(data, j + 2)
                if kind == 0x51 and ln == 3:
                    tempos.append((tick, int.from_bytes(data[k:k + 3], "big")))
                j = k + ln
                continue
            if b in (0xF0, 0xF7):
                ln, k = _vlq(data, j + 1)
                j = k + ln
                continue
            if b & 0x80:
                status = b; j += 1
            if status is None:
                raise ValueError("data byte with no running status at byte %d" % j)
            kind, ch = status & 0xF0, status & 0x0F
            if kind in (0xC0, 0xD0):
                a, bb = data[j], 0; j += 1
            else:
                a, bb = data[j], data[j + 1]; j += 2
            if kind == 0x90 and bb == 0:
                kind = 0x80
            if kind in (0x80, 0x90):
                events.append((tick, "on" if kind == 0x90 else "off", ch, a, bb))
        i = end
    tempos = sorted(dict(tempos).items())
    return div, sorted(events, key=lambda e: (e[0], 0 if e[1] == "off" else 1)), tempos


def seconds(tick, div, tempos):
    """The exact time of a tick, through every tempo change before it."""
    t, last_tick, us = 0.0, 0, 500000
    for at, tempo in tempos:
        if at >= tick:
            break
        t += (at - last_tick) * us / div / 1e6
        last_tick, us = at, tempo
    return t + (tick - last_tick) * us / div / 1e6


def verify(div, events, tempos):
    """Notes with exact times, and every problem in the events. (notes, problems, coincidences)."""
    sounding, notes, problems = {}, [], []
    for tick, kind, ch, pitch, vel in events:
        key = (ch, pitch)
        if kind == "on":
            if key in sounding:
                problems.append("%s on channel %d struck again at tick %d while still sounding (from tick %d)"
                                % (name(pitch), ch + 1, tick, sounding[key][0]))
                start, v = sounding.pop(key)
                notes.append((start, tick, ch, pitch, v))
            sounding[key] = (tick, vel)
        else:
            if key not in sounding:
                problems.append("%s on channel %d released at tick %d with nothing sounding" % (name(pitch), ch + 1, tick))
                continue
            start, v = sounding.pop(key)
            if tick == start:
                problems.append("%s at tick %d has zero length" % (name(pitch), tick))
            notes.append((start, tick, ch, pitch, v))
    for (ch, pitch), (start, v) in sounding.items():
        problems.append("%s on channel %d struck at tick %d and never released" % (name(pitch), ch + 1, start))
    notes.sort()
    ends = {}
    for start, end, ch, pitch, v in notes:
        ends.setdefault(end, []).append(pitch)
    coincident = []
    for start, end, ch, pitch, v in notes:
        for other in ends.get(start, []):
            if other != pitch:
                coincident.append((start, other, pitch))
    timed = [(seconds(s, div, tempos), seconds(e, div, tempos), ch, p, v) for s, e, ch, p, v in notes]
    return timed, problems, sorted(set(coincident))


def render(timed, out_path):
    """A controlled piano-like tone for every note (two partials, fast attack, exponential decay), mono 16-bit WAV."""
    if not timed:
        raise ValueError("no notes to render")
    length = min(MAX_SECONDS, max(e for _, e, _, _, _ in timed) + 1.0)
    buf = array.array("f", [0.0]) * int(length * RATE)
    for start, end, ch, pitch, vel in timed:
        f = 440.0 * 2 ** ((pitch - 69) / 12.0)
        amp = 0.25 * (vel / 127.0)
        s0, s1 = int(start * RATE), min(len(buf), int((end + 0.25) * RATE))
        attack = int(0.004 * RATE)
        for n in range(s0, s1):
            t = (n - s0) / RATE
            env = min(1.0, (n - s0) / attack) if attack else 1.0
            env *= math.exp(-3.0 * t)
            if n > int(end * RATE):
                env *= math.exp(-(n - end * RATE) / (0.05 * RATE))
            buf[n] += amp * env * (math.sin(2 * math.pi * f * t) + 0.3 * math.sin(4 * math.pi * f * t))
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = 0.9 / peak if peak > 0.9 else 1.0
    pcm = array.array("h", (int(max(-1.0, min(1.0, x * scale)) * 32767) for x in buf))
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    return out_path


def attacks(wav_path, window=0.005, rise=2.5):
    """Where attacks land in the audio: windows whose energy jumps by `rise` over the one before. [seconds]."""
    with wave.open(wav_path, "rb") as w:
        rate, raw = w.getframerate(), w.readframes(w.getnframes())
    pcm = array.array("h"); pcm.frombytes(raw)
    hop = max(1, int(window * rate))
    energy = [sum(x * x for x in pcm[k:k + hop]) / hop for k in range(0, len(pcm), hop)]
    found, prev = [], 1.0
    for k, e in enumerate(energy):
        if e > 1e4 and e > rise * prev and (not found or k * hop / rate - found[-1] > 0.03):
            found.append(k * hop / rate)
        prev = max(e, 1.0)
    return found


def check(path, out_dir=None):
    """The whole check, as a report he can read. Never raises."""
    try:
        div, events, tempos = read(path)
        timed, problems, coincident = verify(div, events, tempos)
        where = out_dir or os.path.dirname(os.path.abspath(path))
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, os.path.splitext(os.path.basename(path))[0] + ".check.wav")
        render(timed, out)
        heard = attacks(out)
        lines = ["MIDI check: %s" % path,
                 "%d notes over %.2f s; %d tempo setting(s); %d ticks per beat." % (
                     len(timed), max((e for _, e, _, _, _ in timed), default=0.0), len(tempos), div)]
        lines.append("Events: " + ("all paired and clean." if not problems else "%d problem(s):" % len(problems)))
        lines += ["  - " + p for p in problems[:20]]
        if coincident:
            lines.append("Coincident release and attack (one note ends on the tick the next begins):")
            lines += ["  - tick %d: %s off / %s on (%.3f s)" % (t, name(a), name(b), seconds(t, div, tempos))
                      for t, a, b in coincident[:20]]
        else:
            lines.append("No coincident release/attack pairs.")
        starts = sorted({round(s, 4) for s, _, _, _, _ in timed})
        offsets = []
        for s in starts:
            near = min(heard, key=lambda h: abs(h - s)) if heard else None
            if near is not None and abs(near - s) < 0.05:
                offsets.append((near - s) * 1000)
        lines.append("Rendered attacks: %d found for %d scheduled onsets; %s" % (
            len(heard), len(starts), ("each within %.1f ms of its schedule (mean %+.1f ms)."
                                      % (max(abs(o) for o in offsets), sum(offsets) / len(offsets)))
            if offsets else "none matched their schedule."))
        lines.append("Audio: %s" % out)
        return "\n".join(lines)
    except Exception as exc:
        return "MIDI check could not run on %s: %s" % (path, str(exc)[:300])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    print(check(sys.argv[1]))
