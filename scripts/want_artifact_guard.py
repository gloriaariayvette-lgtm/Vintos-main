#!/usr/bin/env python3
"""want_artifact_guard.py — a want that claims an artifact is fulfilled only when
the artifact exists.

The house law: evidence cannot generate itself. A want to WRITE something is
proven by his words — the transcript is the artifact. But a want to MAKE an
image, a video, a piece of music is proven by a FILE, and his sentence "I ran
make_video and it rendered..." is not that file. Reconciliation was accepting
the sentence: several wants sit in fulfilled-wants.json whose 'fulfillment
note' is just the step instruction ("Generate a visual of...") or a first-person
claim, with nothing on disk behind it.

This module is the single place that answers, for one want: is it artifact-class,
and if so, did the artifact actually land? Ground truth is memory/art/gallery.json
(every real painting, stamped with its want_id) and the output directories
themselves. No network, no model call — a fact check, not a judgement.
"""
import json, os, re
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
GALLERY = os.path.join(MEMORY, "art", "gallery.json")
ART_DIRS = [os.path.join(MEMORY, "art"), os.path.join(MEMORY, "shared-images"),
            os.path.join(MEMORY, "videos"), os.path.join(MEMORY, "music")]

# The capabilities whose fulfillment is a file, not a sentence.
ARTIFACT_CAPS = {"make_art", "make_video", "make_music", "make_image", "animate",
                 "generate_image", "create_visual"}
# Phrases a want/step uses when it means "produce a file".
ARTIFACT_HINTS = ("generate a visual", "generate an image", "generate a high-resolution",
                  "make_art", "make_video", "make_music", "animate painting",
                  "create a visual", "visual sequence", "render", "an image of",
                  "a painting of", "a picture of")


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def is_artifact_want(w):
    """True if fulfilling this want should leave a file on disk."""
    if not isinstance(w, dict):
        return False
    for s in (w.get("steps") or []):
        if isinstance(s, dict) and str(s.get("capability", "")).strip() in ARTIFACT_CAPS:
            return True
    blob = " ".join(str(w.get(k, "")) for k in ("want", "fulfillment_note", "reasoning")).lower()
    # 'animate painting ...' titles and explicit make_* mentions are unambiguous;
    # the softer hints only count alongside a make_* capability, never alone, so a
    # want to WRITE ABOUT a painting is never mistaken for a want to make one.
    if blob.startswith("animate painting") or "make_art" in blob or "make_video" in blob or "make_music" in blob:
        return True
    return False


def _gallery_has(want_id):
    g = _load(GALLERY, [])
    if not isinstance(g, list):
        return False
    return any(isinstance(e, dict) and want_id and e.get("want_id") == want_id for e in g)


def _file_after(ts_iso):
    """Any artifact file newer than the want's own timestamp. Coarse, but a real file."""
    try:
        born = datetime.fromisoformat(str(ts_iso).replace("Z", "")).timestamp()
    except Exception:
        born = 0
    for d in ART_DIRS:
        try:
            for fn in os.listdir(d):
                if fn.endswith((".png", ".jpg", ".jpeg", ".mp4", ".webm", ".mp3", ".wav")):
                    if os.path.getmtime(os.path.join(d, fn)) >= born - 1:
                        return os.path.join(d, fn)
        except Exception:
            pass
    return None


def artifact_evidence(w):
    """The real file proving this artifact want, or None. Prefers an id-stamped
    gallery entry; falls back to any output file dated at/after the want."""
    if not is_artifact_want(w):
        return None
    wid = w.get("id", "")
    if wid and _gallery_has(wid):
        return "gallery:%s" % wid
    return _file_after(w.get("fulfilled_at") or w.get("timestamp") or "")


def verify(w):
    """(ok, why). Non-artifact wants pass — words witness words. Artifact wants pass
    only with a file behind them."""
    if not is_artifact_want(w):
        return True, "not artifact-class"
    ev = artifact_evidence(w)
    if ev:
        return True, "artifact present (%s)" % ev
    return False, "artifact claimed, none found on disk"
