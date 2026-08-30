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
# Every ledger his making writes to, one per medium — each stamps the want_id of
# the want it served. A want is proven by its id appearing in the ledger for its
# OWN medium (paintings in the art gallery, animations in the video ledgers, music
# in the music ledger), so real work in any medium is recognized and only a claim
# with no pipeline record anywhere is flagged.
LEDGERS = [os.path.join(MEMORY, "art", "gallery.json"),
           os.path.join(MEMORY, "art", "video", "video-gallery.json"),
           os.path.join(MEMORY, "art", "video", "video-queue.json"),
           os.path.join(MEMORY, "art", "music", "music.json")]
GALLERY = LEDGERS[0]   # kept for callers/tests that name the paintings gallery
# HIS generated artifacts only. shared-images/ is photos SHE sends him — inbound,
# never his output — so it can never be evidence that he made something.
ART_DIRS = [os.path.join(MEMORY, "art"), os.path.join(MEMORY, "art", "video"),
            os.path.join(MEMORY, "art", "music")]

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
    """True if the want's OWN TEXT is a request to make a file.

    Classified by the want text alone — never by its step plan. The planner
    sometimes hangs a make_art step off a want to WRITE ABOUT a painting or to
    sit still; those are not artifact-wants, and judging them by the stray step
    is what flagged his write and introspection wants as if they were fabricated
    images. Only the want he actually formed counts."""
    if not isinstance(w, dict):
        return False
    t = str(w.get("want", "")).strip().lower()
    if t.startswith("animate painting"):
        return True
    # explicit make verbs in the want itself
    return any(k in t for k in ("make_art", "make_video", "make_music",
                                "generate an image", "generate a visual",
                                "generate a high-resolution"))


def _ledger_has(want_id):
    """True if any medium's ledger recorded this want_id — painting, video, or music."""
    if not want_id:
        return False
    for path in LEDGERS:
        d = _load(path, [])
        entries = d if isinstance(d, list) else (d.get("generated") or d.get("videos") or [])
        for e in entries:
            if isinstance(e, dict) and e.get("want_id") == want_id:
                return True
    return False


def _gallery_has(want_id):   # back-compat alias
    return _ledger_has(want_id)


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
    """The real file proving this artifact want, or None.

    His art pipeline stamps each generated file's gallery entry with the want_id,
    so a want that HAS an id is verified only by an id-stamped gallery entry — no
    date guessing, because he paints often and any old want predates some later,
    unrelated painting. Only an id-less want (which can't be matched to the ledger)
    falls back to a dated file in his own output dirs."""
    if not is_artifact_want(w):
        return None
    wid = w.get("id", "")
    if wid:
        return ("ledger:%s" % wid) if _ledger_has(wid) else None
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
