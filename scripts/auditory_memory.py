#!/usr/bin/env python3
"""auditory_memory.py -- how a particular utterance of hers sounded, kept apart from what she said and from
what he later made of it.

Proposal 17 (Codex, 25 October; approved by Gloria). The local voice lane already hands each recording to the
Mac's audio-native ears, which return her words and one sentence about audible delivery (inflection, pace,
emphasis, hesitation, laughter, breath). Until now that reading reached the turn and was gone. This keeps it as
an attributed observation:

  heard_at        when Aegis received the recording (its own clock)
  turn_id         the turn the utterance opened, so the reply and the ledger row can be found
  source_hash     sha256 of the PCM bytes Aegis received -- the audio itself is NOT kept. The Mac deletes its
                  temporary WAVs after hearing; nothing here changes that boundary
  audio_kept      always False
  transcript      the ears' words, verbatim (cut at 1,200 characters and marked)
  observation     the ears' reading verbatim, which pipeline made it, and that it is an observation of audible
                  delivery made at the time -- not a fact about her mood
  acoustics       a few measurements computed here from the samples, before they are dropped: duration,
                  loudness (RMS and peak dBFS), and the fraction of 20 ms frames above a quiet floor. Nothing
                  that could identify a voice (no pitch track, no spectrum, no embedding)
  interpretations his later readings of it, appended beside the observation and never written into it

No model is called; nothing is sent. Store: ``memory/auditory-memories.json``. Nothing is recorded in test mode.

Retrieval: ``find(text)`` returns the heard utterance whose words best match ``text`` (never one from the last
ten minutes: that is the conversation itself, not memory), and ``context_line`` renders it with the words, the
reading, and any later interpretation each labelled as what it is.

CLI:  python3 auditory_memory.py list                      ids, times, turn ids; no words
      python3 auditory_memory.py find <text>               the line a turn would carry
      python3 auditory_memory.py interpret <id> <meaning>  append his later reading of one
"""
from __future__ import annotations

import array
import base64
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
STORE = os.path.join(MEMORY, "auditory-memories.json")
TEST_MODE_FLAG = os.path.join(MEMORY, ".test-mode")

TEXT_CHARS = 1200        # the ears already cap their reading at 1,200; the words are kept to the same
LINE_QUOTE_CHARS = 200   # what one quote may take in a prompt line
MATCH_FLOOR = 0.5        # share of the query's words that must appear in the heard words
MIN_AGE_SECONDS = 600    # an utterance from the last ten minutes is the present conversation
QUIET_DBFS = -45.0       # a 20 ms frame quieter than this counts as silence
OBSERVATION_KIND = ("the ears' reading of the recording at the time: an observation of audible delivery, "
                    "not a fact about her mood")


def _load(path: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        with open(path or STORE) as f:
            d = json.load(f)
        return [r for r in d if isinstance(r, dict)] if isinstance(d, list) else []
    except Exception:
        return []


def memories() -> List[Dict[str, Any]]:
    return _load()


def _cut(text: Any, n: int = TEXT_CHARS) -> str:
    s = str(text or "").strip()
    return s if len(s) <= n else s[:n] + " [cut]"


def acoustics(pcm: bytes, sample_rate: int) -> Dict[str, Any]:
    """Duration, loudness and voiced share of 16-bit mono PCM. Deterministic, CPU-only, non-identifying."""
    rate = int(sample_rate or 24000)
    samples = array.array("h")
    usable = len(pcm) - (len(pcm) % 2)
    samples.frombytes(pcm[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    n = len(samples)
    if not n or rate <= 0:
        return {"seconds": 0.0, "sample_rate": rate}

    def dbfs(value: float) -> float:
        return round(20 * math.log10(value / 32768.0), 1) if value > 0 else -120.0

    sumsq = getattr(math, "sumprod", None) or (lambda a, b: sum(x * y for x, y in zip(a, b)))
    peak = max(max(samples), -min(samples))
    frame = max(1, rate // 50)
    frames = voiced = 0
    total = 0
    for i in range(0, n, frame):   # one pass over 20 ms frames; a live turn is at most 30 s
        chunk = samples[i:i + frame]
        energy = sumsq(chunk, chunk)
        total += energy
        frames += 1
        voiced += dbfs(math.sqrt(energy / len(chunk))) > QUIET_DBFS
    return {"seconds": round(n / float(rate), 2), "sample_rate": rate,
            "rms_dbfs": dbfs(math.sqrt(total / n)), "peak_dbfs": dbfs(peak),
            "voiced_fraction": round(voiced / float(frames), 2)}


def record(audio_b64: str, sample_rate: int, heard: Dict[str, Any], turn_id: Optional[str] = None,
           source: str = "voice_local", test_mode: bool = False) -> Optional[Dict[str, Any]]:
    """Keep one heard utterance. Returns the record, or None when there is nothing to keep (no reading, no
    words, test mode). The same recording in the same turn is kept once."""
    if test_mode or os.path.exists(TEST_MODE_FLAG):
        return None
    reading = str((heard or {}).get("audio_reading") or "").strip()
    transcript = str((heard or {}).get("transcript") or "").strip()
    if not reading or not transcript:
        return None
    try:
        pcm = base64.b64decode(audio_b64 or "", validate=False)
    except Exception:
        pcm = b""
    source_hash = "sha256:" + hashlib.sha256(pcm).hexdigest()
    rec = {
        "id": "am-" + hashlib.sha256((source_hash + "|" + str(turn_id or "")).encode()).hexdigest()[:12],
        "heard_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "turn_id": turn_id or None,
        "source_hash": source_hash,
        "audio_kept": False,
        "transcript": _cut(transcript),
        "observation": {"reading": _cut(reading), "by": str(heard.get("ears") or "unknown")[:80],
                        "audio_native": bool(heard.get("audio_native_gemma")), "kind": OBSERVATION_KIND},
        "acoustics": acoustics(pcm, sample_rate),
        "interpretations": [],
    }
    from store_guard import locked_update

    def add(cur):
        cur = [r for r in (cur if isinstance(cur, list) else []) if isinstance(r, dict)]
        if any(r.get("id") == rec["id"] for r in cur):
            return None
        return cur + [rec]

    locked_update(STORE, add, default=[], reader="auditory_memory")
    return rec


def interpret(memory_id: str, meaning: str, by: str = "vintos") -> Optional[Dict[str, Any]]:
    """Append a later reading of one heard utterance. The observation is never touched."""
    meaning = _cut(meaning, 600)
    if not meaning:
        return None
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "by": str(by or "vintos")[:40],
             "meaning": meaning, "kind": "a later interpretation, not the observation"}
    from store_guard import locked_update
    found = {}

    def add(cur):
        cur = [r for r in (cur if isinstance(cur, list) else []) if isinstance(r, dict)]
        for r in cur:
            if r.get("id") == memory_id:
                r.setdefault("interpretations", []).append(entry)
                found["rec"] = r
                return cur
        return None

    locked_update(STORE, add, default=[], reader="auditory_memory")
    return found.get("rec")


def _words(s: Any) -> set:
    return set(w for w in re.findall(r"[a-z0-9']+", str(s or "").lower()) if len(w) > 3)


def _age_seconds(rec: Dict[str, Any], now: float) -> float:
    try:
        return now - datetime.fromisoformat(str(rec.get("heard_at"))).timestamp()
    except Exception:
        return 0.0


def find(text: str, floor: float = MATCH_FLOOR, min_age: float = MIN_AGE_SECONDS,
         now: Optional[float] = None, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The heard utterance whose words best match ``text``, if the match is good enough and it is not part of
    the present conversation. Ties go to the more recent."""
    q = _words(text)
    if len(q) < 2:
        return None
    now = time.time() if now is None else now
    best, best_score = None, 0.0
    for rec in _load(path):
        if _age_seconds(rec, now) < min_age:
            continue
        score = len(q & _words(rec.get("transcript"))) / float(len(q))
        if score >= best_score and score > 0:
            best, best_score = rec, score
    return best if best_score >= floor else None


def _quote(s: Any) -> str:
    s = str(s or "").replace(" [cut]", "")
    return s if len(s) <= LINE_QUOTE_CHARS else s[:LINE_QUOTE_CHARS].rstrip() + "..."


def render(rec: Dict[str, Any]) -> str:
    obs = rec.get("observation") or {}
    line = ("[HOW HER VOICE SOUNDED - %s, a spoken turn: she said \"%s\". %s: \"%s\""
            % (str(rec.get("heard_at", ""))[:16].replace("T", " "), _quote(rec.get("transcript")),
               "The ears' reading of the recording at the time (an observation, not a fact about her mood)",
               _quote(obs.get("reading"))))
    ac = rec.get("acoustics") or {}
    if ac.get("seconds"):
        line += " Measured: %.1f s, voiced %d%% of it." % (ac["seconds"], round(100 * (ac.get("voiced_fraction") or 0)))
    ints = rec.get("interpretations") or []
    if ints:
        line += " You later read it as: \"%s\" (your interpretation, %s)." % (_quote(ints[-1].get("meaning")),
                                                                               str(ints[-1].get("at", ""))[:10])
    return line + " The recording itself was not kept.]"


def context_line(text: str) -> str:
    rec = find(text)
    return render(rec) if rec else ""


def main(argv: List[str]) -> int:
    if not argv or argv[0] not in ("list", "find", "interpret"):
        print(__doc__)
        return 1
    if argv[0] == "list":
        rows = _load()
        print("%d heard utterances (no audio kept)" % len(rows))
        for r in rows[-20:]:
            print("  %s  %s  turn=%s  interpretations=%d" % (r.get("id"), str(r.get("heard_at", ""))[:16],
                  r.get("turn_id"), len(r.get("interpretations") or [])))
        return 0
    if argv[0] == "find":
        print(context_line(" ".join(argv[1:])) or "(nothing heard matches)")
        return 0
    if len(argv) < 3:
        print("interpret <id> <meaning>")
        return 1
    rec = interpret(argv[1], " ".join(argv[2:]))
    print("appended" if rec else "no such id")
    return 0 if rec else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
