#!/usr/bin/env python3
"""Sealed image and music material for the Atelier.

The house renderers are reused below their public shelves: this module returns
bytes to the caller and writes no gallery, journal, activity log, or notification.
Only the broker may keep those bytes, inside the active project.
"""
from __future__ import annotations
import importlib.util, os, socket, tempfile

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
SCRIPTS = os.path.join(WS, "scripts")


def _load(name, filename):
    path = os.path.join(SCRIPTS, filename)
    if not os.path.isfile(path): return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1): return True
    except OSError: return False


def status():
    art = _load("atelier_dream_art", "dream-art.py")
    music = _load("atelier_dream_music", "dream-music.py")
    try: image_model = art._find_local_model() if art else ""
    except Exception: image_model = ""
    ace = bool(music and _port_open("127.0.0.1", 8001))
    return {
        "image": {"configured": bool(art and image_model), "ok": bool(art and image_model),
                  "outage": "" if art and image_model else "no cached local image renderer"},
        "music": {"configured": bool(music), "ok": ace,
                  "outage": "" if ace else ("ACE-Step is unreachable" if music else "music renderer is not installed")},
    }


def render_image(prompt):
    art = _load("atelier_dream_art", "dream-art.py")
    if not art: return {"ok": False, "configured": False, "error": "image renderer is not installed"}
    try: data = art._local_render(str(prompt or "")[:1200])
    except Exception as exc: return {"ok": False, "configured": True, "error": "image renderer failed: %s" % str(exc)[:180]}
    if not data: return {"ok": False, "configured": True, "error": "image renderer returned no bytes"}
    return {"ok": True, "kind": "image", "ext": "png", "mime_type": "image/png",
            "bytes": data, "size": len(data)}


def render_music(title, style, description="", duration=120, instrumental=True):
    music = _load("atelier_dream_music", "dream-music.py")
    if not music: return {"ok": False, "configured": False, "error": "music renderer is not installed"}
    duration = max(15, min(180, int(duration or 120)))
    try:
        tid = music.generate(str(title or "untitled")[:120], str(style or "open")[:500],
                             str(description or "")[:2500], bool(instrumental), duration)
        tracks = music.poll(tid) if tid else None
        first = tracks[0] if tracks else {}
        url = first.get("audio_url") or first.get("url") or first.get("file_url") or ""
        if not url: return {"ok": False, "configured": True, "error": "music renderer returned no track URL"}
        fd, path = tempfile.mkstemp(prefix="atelier-music-", suffix=".wav"); os.close(fd)
        try:
            if not music.dl(url, path): return {"ok": False, "configured": True, "error": "music track could not be retrieved"}
            with open(path, "rb") as source: data = source.read()
        finally:
            try: os.unlink(path)
            except OSError: pass
        if not data: return {"ok": False, "configured": True, "error": "music renderer returned empty bytes"}
        return {"ok": True, "kind": "music", "ext": "wav", "mime_type": "audio/wav",
                "bytes": data, "size": len(data), "task_id": str(tid)[:120]}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": "music renderer failed: %s" % str(exc)[:180]}
