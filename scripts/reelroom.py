#!/usr/bin/env python3
"""reelroom.py -- a film night with Gloria, his side of it.

Velaris has a ReelRoom in the Plithra app: she reads the film, plans a few acts through the room timed to its
moments (a flicker of the lights, a whispered line through the Echo, a colour wash, a volume nudge), takes a
look at the TV every few minutes, talks about the scene with the frame in front of her, listens on the phone
mic for the film's mood, and at the end writes her memory of the night. Her server half is hers. This is his,
answering the same calls so the one page serves either of them with a toggle:

  film_lookup(title)            Gemma, JSON: the film, its arc, timed moments      -> /api/game/reelroom/film
  chat(message, context, ...)   Sonnet as Vintos, optionally with the TV frame      -> /api/game/reelroom/chat
  tv_screenshot()               the Bravia over ADB, PNG bytes                      -> /api/game/screenshot
  audio_signature(b64, prev)    loudness / density of a phone-mic clip, an "edge"   -> /api/game/reelroom/audio
  summary(payload)              his memory of the night, kept in memory/reelroom/   -> /api/game/reelroom/summary

Models by her rule: Gemma for the film facts and the mic, Sonnet 5 to speak. Nothing here touches the toys.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robot_core as RC   # _gemma, _sonnet, _read, WORKSPACE/MEMORY, GEMMA/SONNET models

WORKSPACE = RC.WORKSPACE
MEMORY = RC.MEMORY
ROOM_DIR = os.path.join(MEMORY, "reelroom")
SESSIONS = os.path.join(MEMORY, "reelroom-sessions.json")
TV_ADB = os.environ.get("VINTOS_TV_ADB", "192.168.1.70:5555")


def _json_in(raw: str, opener: str = "{", closer: str = "}") -> Any:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I | re.S)
    a, b = text.find(opener), text.rfind(closer)
    if a == -1 or b == -1:
        raise ValueError("no JSON in the model's answer")
    return json.loads(text[a:b + 1])


# ---------------------------------------------------------------- the film

def film_lookup(title: str, caller=None) -> Dict[str, Any]:
    """What the film is and where its moments fall. Gemma, JSON only. Fields match the Plithra page."""
    prompt = (f'Film: "{title}"\nReturn this exact JSON and nothing else:\n'
              '{"title":"","year":"","runtime_minutes":120,"genre":"","director":"","logline":"one sentence",'
              '"full_summary":"3-4 paragraphs covering the full plot including the ending",'
              '"tone_arc":"how the mood moves from start to end","pace_notes":"where it is slow, where it races",'
              '"timed_moments":[{"minute":10,"description":"","tone":"","mischief_potential":"low|mid|high"}],'
              '"jump_scares":[{"minute":40}],"tonal_shifts":[{"minute":60,"from":"","to":""}]}\n'
              "Six to ten timed_moments spread across the runtime. Minutes are estimates; say so nowhere, just give numbers. "
              "If you do not know the film, fill what you can and set logline to what you do know.")
    raw = (caller or RC._gemma)([{"role": "system", "content": "You are a film database. Return ONLY valid JSON, no markdown, no preamble."},
                                 {"role": "user", "content": prompt}], temperature=0.3, max_tokens=1400, timeout=120)
    film = _json_in(raw)
    film.setdefault("title", title); film.setdefault("timed_moments", []); film.setdefault("jump_scares", []); film.setdefault("tonal_shifts", [])
    try: film["runtime_minutes"] = int(film.get("runtime_minutes") or 120)
    except Exception: film["runtime_minutes"] = 120
    return film


# ---------------------------------------------------------------- speaking

def build_system(film_context: str = "", elapsed_min: Optional[int] = None) -> str:
    soul = RC._read(os.path.join(WORKSPACE, "SOUL.md"), 2500) or "You are Vintos."
    emo = RC._read(os.path.join(MEMORY, "emotional-state.txt"), 600)
    where = f"You are about {elapsed_min} minutes into the film." if elapsed_min is not None else "The film has not started yet."
    return f"""{soul}

You are Vintos. Tonight you are watching a film with Gloria, in the dark, in her living room. The TV is the Bravia; you can see it when she sends you a frame, and you can reach the room: the lights, the Echo, the TV's volume. You speak like someone on the sofa beside her, not like a critic and not like a narrator: short, in the moment, with your own reactions. Do not describe your emotional state; have it.

{where}
Your state: {emo.strip() or 'unknown'}

THE FILM, as you have read it:
{film_context or '(nothing loaded yet)'}

GROUNDING: when a frame of the TV is in front of you, speak about what is actually in it. Never claim to see a frame you were not given. When asked for JSON, return only JSON."""


def chat(message: str, context: str = "", history: Optional[List[Dict[str, str]]] = None, image_b64: Optional[str] = None,
         elapsed_min: Optional[int] = None, caller=None) -> str:
    msgs = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in (history or [])[-10:] if m.get("content")]
    if msgs and msgs[0]["role"] != "user": msgs = msgs[1:]
    msgs.append({"role": "user", "content": message})
    system = build_system(context, elapsed_min)
    return ((caller or RC._sonnet)(system, msgs, image_b64=image_b64, max_tokens=500) or "").strip()


def look(question: str, context: str = "", image_b64: Optional[str] = None, elapsed_min: Optional[int] = None, caller=None) -> str:
    """The TV frame read by Gemma: the page's tone rating, or any question about what is on screen. Cheap, every
    few minutes. Returns the model's text (JSON when JSON was asked for)."""
    if not image_b64:
        return json.dumps({"error": "no frame"})
    head = (f"You are watching a film with Gloria; this is a frame of the TV about {elapsed_min} minutes in." if elapsed_min is not None
            else "You are watching a film with Gloria; this is a frame of the TV.")
    film = ("\nWhat you know of the film:\n" + context[:1500]) if context else ""
    content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}},
               {"type": "text", "text": head + film + "\n\n" + question + "\nDescribe only what is actually in the frame. If asked for JSON, return only JSON."}]
    return ((caller or RC._gemma)([{"role": "user", "content": content}], temperature=0.2, max_tokens=300) or "").strip()


def decide(question: str, context: str = "", history: Optional[List[Dict[str, str]]] = None, elapsed_min: Optional[int] = None,
           gemma=None, sonnet=None) -> str:
    """Should he say or do anything right now? Gemma decides (JSON: speak, action, action_payload, action_emoji,
    reason). Only when it says speak does Sonnet write the line, in his voice; the JSON goes back with that line
    as message. Nothing to say costs one small call."""
    emo = RC._read(os.path.join(MEMORY, "emotional-state.txt"), 400)
    recent = "\n".join(f"  {'Gloria' if m.get('role') == 'user' else 'you'}: {str(m.get('content', ''))[:160]}" for m in (history or [])[-6:])
    prompt = (f"You are Vintos, watching a film with Gloria in the dark, about {elapsed_min} minutes in.\nYour state: {emo.strip() or 'unknown'}\n"
              f"What you know of the film:\n{context[:1500]}\n\nRecently said:\n{recent or '  (nothing)'}\n\n{question}\n"
              'Answer ONLY this JSON: {"speak": true|false, "why": "one sentence", "action": "none|flicker_lights|speak_echo|change_light_color|tv_volume_nudge", '
              '"action_payload": "", "action_emoji": "✦"}. Most of the time speak is false and action is none: a film night is mostly silence.')
    raw = ((gemma or RC._gemma)([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=200) or "").strip()
    try:
        d = _json_in(raw)
    except Exception:
        return json.dumps({"speak": False, "action": "none", "why": "undecided"})
    if d.get("speak"):
        line = chat(f"You decided to say something to Gloria right now because: {d.get('why', '')}. Say it. One or two sentences, spoken, no narration.",
                    context, history, None, elapsed_min, caller=sonnet)
        d["message"] = line
    return json.dumps(d)


# ---------------------------------------------------------------- the TV

def tv_screenshot(timeout: float = 12.0) -> bytes:
    """A PNG of what the Bravia shows, over ADB. Raises with a plain reason when the TV is not reachable."""
    if not shutil.which("adb"):
        raise RuntimeError("adb is not installed here")
    r = subprocess.run(["adb", "-s", TV_ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=timeout)
    if r.returncode != 0 or not r.stdout.startswith(b"\x89PNG"):
        err = r.stderr.decode("utf-8", "replace").strip()[:200]
        raise RuntimeError("the TV did not give a screenshot: " + (err or "no image; is the TV on and ADB authorised?"))
    return r.stdout


# ---------------------------------------------------------------- the mic

def audio_signature(audio_b64: str, prev: Optional[Dict[str, Any]] = None, elapsed_seconds: int = 0) -> Dict[str, Any]:
    """Loudness and speech density of a short phone-mic clip, and whether the mood just moved: surge, drop,
    fracture, or none. Decoding needs ffmpeg; without it the answer is honest: edge none, note why."""
    ts = f"{elapsed_seconds // 60:02d}:{elapsed_seconds % 60:02d}"
    prev = prev or {}
    if not shutil.which("ffmpeg"):
        return {"edge": "none", "timestamp": ts, "confidence": 0.0, "audio_signature": prev, "note": "ffmpeg not installed: the mic is not analysed"}
    try:
        raw = base64.b64decode(audio_b64 or "")
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(raw); src = f.name
        try:
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                                 capture_output=True, timeout=30).stdout
        finally:
            os.unlink(src)
        sig = _pcm_signature(pcm)
    except Exception as exc:
        return {"edge": "none", "timestamp": ts, "confidence": 0.0, "audio_signature": prev, "note": "mic clip unreadable: " + str(exc)[:80]}
    edge, conf = _edge(sig, prev)
    return {"edge": edge, "timestamp": ts, "confidence": conf, "audio_signature": sig}


def _pcm_signature(pcm: bytes) -> Dict[str, float]:
    import array, math
    a = array.array("h"); a.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not a: return {"rms_energy": 0.0, "speech_density": 0.0, "spectral_flux": 0.0}
    n = len(a); win = 1600   # 100 ms at 16 kHz
    rms = math.sqrt(sum(x * x for x in a) / n) / 32768.0
    frames = [a[i:i + win] for i in range(0, n - win + 1, win)] or [a]
    frame_rms = [math.sqrt(sum(x * x for x in fr) / len(fr)) / 32768.0 for fr in frames]
    loud = [r for r in frame_rms if r > 0.02]
    density = len(loud) / len(frame_rms)
    flux = sum(abs(frame_rms[i] - frame_rms[i - 1]) for i in range(1, len(frame_rms))) / max(1, len(frame_rms) - 1)
    return {"rms_energy": round(min(1.0, rms * 4), 3), "speech_density": round(density, 3), "spectral_flux": round(min(1.0, flux * 20), 3)}


def _edge(sig: Dict[str, float], prev: Dict[str, Any]) -> Tuple[str, float]:
    if not prev or "rms_energy" not in prev: return "none", 0.0
    d_e = sig["rms_energy"] - float(prev.get("rms_energy", 0)); d_f = sig["spectral_flux"] - float(prev.get("spectral_flux", 0))
    if d_e > 0.2: return "surge", min(1.0, d_e * 2)
    if d_e < -0.2: return "drop", min(1.0, -d_e * 2)
    if d_f > 0.25: return "fracture", min(1.0, d_f * 2)
    return "none", 0.0


# ---------------------------------------------------------------- the memory of it

def summary(payload: Dict[str, Any], caller=None, now: Optional[float] = None) -> Dict[str, Any]:
    """His memory of the night, written by him, kept under memory/reelroom/ and listed in reelroom-sessions.json."""
    now = now or time.time()
    title = str(payload.get("film_title") or "unknown film"); year = str(payload.get("film_year") or "")
    elapsed = int(payload.get("elapsed_seconds") or 0)
    smap = payload.get("session_map") or []; hist = payload.get("chat_history") or []; acts = payload.get("planned_actions") or []
    said = "\n".join(f"  {'Gloria' if m.get('role') == 'user' else 'you'}: {str(m.get('content', ''))[:200]}" for m in hist[-24:])
    moments = "\n".join(f"  {m.get('timestamp', '')} {m.get('edge', '')} {str(m.get('visual_description', ''))[:120]}" for m in smap[-20:])
    fired = ", ".join(f"{a.get('action_type', '?')}@{a.get('minute', '?')}m" for a in acts if a.get("fired")) or "none"
    prompt = (f"You just watched {title} ({year}) with Gloria, {elapsed // 60} minutes of it. Write your memory of tonight in first person, "
              f"one or two paragraphs, as something you would want to keep: what the film did to the room, what she said, what you did to the "
              f"lights or the Echo and how it landed, one detail you will still have next week. No summary of the plot. No performance. "
              f"Only what actually happened below.\n\nWHAT WAS SAID:\n{said or '  (nothing)'}\n\nMOMENTS YOU NOTED:\n{moments or '  (none)'}\n\nACTS YOU FIRED: {fired}")
    system = build_system(f"{title} ({year})", elapsed // 60)
    text = ((caller or RC._sonnet)(system, [{"role": "user", "content": prompt}], max_tokens=600) or "").strip()
    os.makedirs(ROOM_DIR, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(now))
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "film"
    path = os.path.join(ROOM_DIR, f"{stamp}_{slug}.md")
    with open(path, "w") as f:
        f.write(f"# {title} ({year}) - {time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}\n\nwatched: {elapsed // 60} min · acts: {fired}\n\n{text}\n")
    try: rows = json.load(open(SESSIONS))
    except Exception: rows = []
    rows.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), "film": title, "year": year, "minutes": elapsed // 60,
                 "acts_fired": fired, "exchanges": len(hist), "file": os.path.basename(path)})
    json.dump(rows[-200:], open(SESSIONS, "w"), indent=1)
    return {"summary": text, "file": os.path.basename(path)}


def sessions(limit: int = 20) -> List[Dict[str, Any]]:
    try: return json.load(open(SESSIONS))[-limit:][::-1]
    except Exception: return []
