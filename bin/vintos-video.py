#!/usr/bin/env python3
"""vintos-video.py — Vintos makes video. grok-imagine-video-1.5 is image-to-video
only, so: given an image, animate it; given only text, paint a keyframe first
(grok-imagine-image) then animate it.
Usage:
  vintos-video.py "text" [/path/to/image]   # one-off
  vintos-video.py --queue                    # process the next item in video-queue.json
"""
import os, sys, json, time, base64, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
ART_DIR = os.path.join(MEMORY, "art")
VID_DIR = os.path.join(ART_DIR, "video")
GALLERY = os.path.join(VID_DIR, "video-gallery.json")
QUEUE = os.path.join(VID_DIR, "video-queue.json")
KEY = os.environ.get("XAI_API_KEY", "")
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
for _sp in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"),
            os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")):
    if os.path.isdir(_sp) and _sp not in sys.path: sys.path.insert(0, _sp)
import artifact_manifest as _am   # common manifest + collision-free names (review 275/279)

def data_uri(path):
    raw = open(path, "rb").read()
    mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(raw).decode()

import grok_subscription as _gs   # Grok Imagine on her SuperGrok subscription, never the API key (2026-09-25)

def paint_keyframe(text):
    try:
        _png, _ = _gs.image(text[:1000])
    except _gs.Unavailable as e:
        print(f"[video] grok subscription: {e} — no keyframe"); return None
    except Exception as e:
        print(f"[video] keyframe error: {e}"); return None
    os.makedirs(ART_DIR, exist_ok=True)
    path, _ = _am.unique_path(ART_DIR, f"keyframe-{datetime.now().strftime('%Y%m%d-%H%M%S')}", ".png", _png)
    fname = os.path.basename(path)
    open(path, "wb").write(_png)
    print(f"[video] keyframe painted: {fname}")
    return path

MAX_SECONDS = 110   # his call, up to just under two minutes.
GROK_MAX = 15       # x.ai's own limit; wan through Atlas takes the longer ones


def _atomic_json(path, obj):
    """Write-then-replace: a reader never sees a half-written store and a crash leaves the old one
    intact (astra-creative-p4, 2026-09-05)."""
    _tmp = path + ".tmp.%d" % os.getpid()
    with open(_tmp, "w") as _f: json.dump(obj, _f, indent=2)
    os.replace(_tmp, path)

def _atlas():
    """Borrow his existing Atlas routing rather than reimplementing it."""
    import importlib.util as _u
    _here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vintos-send-video.py")
    _cands = [_here, os.path.expanduser("~/Vintos/vintos-send-video.py"),
              os.path.expanduser("~/.vintos/workspace/scripts/vintos-send-video.py")]
    _fp = next((c for c in _cands if os.path.exists(c)), None)
    if not _fp:
        raise FileNotFoundError("vintos-send-video.py not found beside this file, in ~/Vintos, or in workspace/scripts")
    sp = _u.spec_from_file_location("vsv", _fp)
    m = _u.module_from_spec(sp); sp.loader.exec_module(m)
    return m

def make_one(text, img_path="", duration=6, backend="grok", want_id=""):
    if not img_path:
        img_path = paint_keyframe(text)
        if not img_path:
            return False
    os.makedirs(VID_DIR, exist_ok=True)
    try:
        duration = max(1, min(int(float(duration)), MAX_SECONDS))
    except Exception:
        duration = 6

    if backend == "wan":
        # Spicy Wan through Atlas - the same call he already uses.
        m = _atlas()
        blob = m.atlas_generate(text, img_path, model=m.ATLAS_MODEL, duration=duration)
        if not blob:
            print("[video] wan returned nothing"); return False
        _vpath, _rev = _am.unique_path(VID_DIR, f"video-{datetime.now().strftime('%Y%m%d-%H%M%S')}", ".mp4", blob)
        fname = os.path.basename(_vpath)
        open(_vpath, "wb").write(blob)
        try: gallery = json.load(open(GALLERY))
        except Exception: gallery = []
        gallery.append({"file": fname, "prompt": text[:300],
                        "source_image": os.path.basename(img_path),
                        "backend": "atlas-wan-spicy", "duration": duration,
                        "want_id": want_id, "for_wall": want_id == "projector",
                        "timestamp": datetime.now().isoformat(),
                        **_am.build(_vpath, "video", source_want=want_id, revision=_rev, shelf=VID_DIR)})
        _am.append_ledger(GALLERY, gallery[-1])   # review 302: the one shelf transaction
        print(f"[video] saved: {fname}")
        return True

    try:
        _blob = _gs.video(text[:600], img_path, duration=min(duration, 15))
    except _gs.Unavailable as e:
        print(f"[video] grok subscription: {e} — no video"); return False
    except Exception as e:
        print(f"[video] {e}"); return False
    _vpath, _rev = _am.unique_path(VID_DIR, f"video-{datetime.now().strftime('%Y%m%d-%H%M%S')}", ".mp4", _blob)
    fname = os.path.basename(_vpath)
    open(_vpath, "wb").write(_blob)
    try:
        gallery = json.load(open(GALLERY))
    except Exception:
        gallery = []
    gallery.append({"file": fname, "prompt": text[:300],
                    "source_image": os.path.basename(img_path),
                    "backend": "grok-imagine", "billing": "grok-subscription", "duration": duration,
                    "want_id": want_id, "for_wall": want_id == "projector",
                    "timestamp": datetime.now().isoformat(),
                    **_am.build(_vpath, "video", source_want=want_id, revision=_rev, shelf=VID_DIR)})
    _am.append_ledger(GALLERY, gallery[-1])   # review 302: the one shelf transaction
    print(f"[video] saved: {fname}")
    return True

def _process_queue():
    from store_guard import transaction
    with transaction(QUEUE):
        try:
            q = json.load(open(QUEUE))
            import re as _apre  # _ap_gate: only hero videos, never animate-painting
            # A named refusal, not a silent filter (fable-creative-p3, 2026-09-05): an animate-painting item
            # is marked blocked with its reason and written back, so want-reconciliation / want_spine see
            # BLOCKED instead of a want that quietly never ran.
            _kept, _changed = [], False
            for x in q:
                _blob = x if isinstance(x, str) else json.dumps(x)
                if _apre.search(r"animate paint", _blob, _apre.I):
                    if isinstance(x, dict) and not x.get("blocked"):
                        x["blocked"] = {"reason": "animate-painting disabled: the video path is for hero clips; a painting stays still until an animation backend for it exists",
                                        "at": datetime.now().isoformat()}
                        _changed = True
                        print(f"[video] BLOCKED (named): {str(x.get('want_text') or x.get('prompt') or '')[:60]}")
                        try:   # the want itself learns it is BLOCKED (same shape want_spine.apply_result writes)
                            if x.get("want_id"):
                                _wp = os.path.expanduser("~/.vintos/workspace/memory/current-wants.json")
                                _wraw = json.load(open(_wp)); _wl = _wraw if isinstance(_wraw, list) else _wraw.get("wants", [])
                                for _w in _wl:
                                    if _w.get("id") == x["want_id"] and not _w.get("blocked"):
                                        _w["blocked"] = {"cause": x["blocked"]["reason"], "blocked_step": "make_video", "at": time.time()}
                                json.dump(_wraw, open(_wp, "w"), indent=2)
                        except Exception as _wse:
                            print(f"[video] want not marked blocked: {_wse}")
                        _kept.append(x)   # stays on the queue as a visible BLOCKED item, skipped below
                    elif isinstance(x, dict):
                        _kept.append(x)
                    continue
                _kept.append(x)
            if _changed:
                try: _atomic_json(QUEUE, _kept)
                except Exception: pass
            _blocked = [x for x in _kept if isinstance(x, dict) and x.get("blocked")]
            q = [x for x in _kept if not (isinstance(x, dict) and x.get("blocked"))]
        except Exception:
            _blocked = []
            q = []
    if not q:
        print("[video] queue empty"); return
    item = q[0] if isinstance(q[0], dict) else {}
    text = (item.get("want_text") or item.get("prompt") or item.get("text")
            or (q[0] if isinstance(q[0], str) else "subtle living motion"))
    img = item.get("image") or item.get("source_image") or ""
    print(f"[video] queue: processing 1 of {len(q)}: {str(text)[:70]}")
    from want_stance import action_context, may_initiate
    with action_context(item):
        allowed, why = may_initiate("creation")
        if not allowed:
            print("[stance] " + why); return
        ok = make_one(str(text), img, item.get("duration", 6), item.get("backend", "grok"), item.get("want_id", ""))
    selected = q[0]
    from store_guard import locked_update
    def finish(current):
        # A producer may have appended while rendering. Change only the selected
        # row in the fresh queue, never replace it with the pre-render snapshot.
        for index, row in enumerate(current):
            same = (isinstance(row, dict) and isinstance(selected, dict) and selected.get("queue_id") and row.get("queue_id") == selected["queue_id"]) or row == selected
            if same:
                entry = current.pop(index)
                if not ok: current.append(entry)
                return current
        return None
    locked_update(QUEUE, finish, reader="vintos-video.process_queue")


def process_queue():
    from store_guard import transaction
    # One consumer, while producers only hold QUEUE's short mutation lock.
    with transaction(QUEUE + ".consumer"):
        return _process_queue()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--queue":
        process_queue(); return
    from want_stance import may_initiate
    ok, why = may_initiate("creation")
    if not ok:
        print("[stance] " + why); return
    text = sys.argv[1] if len(sys.argv) > 1 else "subtle living motion"
    img_path = sys.argv[2] if len(sys.argv) > 2 else ""
    make_one(text, img_path)

if __name__ == "__main__":
    main()
