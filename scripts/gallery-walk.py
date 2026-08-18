#!/usr/bin/env python3
"""gallery-walk.py — Vintos walks his own gallery. One painting, one honest look.
He actually SEES the image (local vision model, mirroring Velaris) before he reflects.
If something in him wants to see it move, that becomes a want routed to animate_painting."""
import os, json, random, uuid, base64, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
WORKSPACE = os.path.expanduser("~/.vintos/workspace")
KEY = os.environ.get("XAI_API_KEY", "")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"   # local Gemma (vision-capable)

def see_painting(image_path):
    """Actually look at the painting with the local vision model. Concrete description."""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = image_path.rsplit(".", 1)[-1].lower()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
        r = requests.post(LM_API, json={
            "model": "google/gemma-4-12b-qat",
            "messages": [
                {"role": "system", "content": "Describe this image in detail. Colors, shapes, mood, composition. Be specific and concrete. 3-5 sentences."},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": "What do you see in this painting? Describe it concretely."}
                ]},
            ],
            "temperature": 0.5, "max_tokens": 400}, timeout=90)
        return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content", "") or "").strip()
    except Exception as e:
        print(f"[gallery-walk] vision failed: {e}")
        return ""

def main():
    try:
        gallery = json.load(open(os.path.join(MEMORY, "art", "gallery.json")))
    except Exception:
        print("[gallery-walk] no gallery"); return
    if not gallery:
        return
    try:
        _gw_walks = json.load(open(os.path.join(MEMORY, "gallery-walks.json")))
        _gw_seen = {w.get("image", "") for w in _gw_walks[-15:]}
    except Exception:
        _gw_seen = set()
    _gw_fresh = [g for g in gallery if g.get("image") and g.get("image") not in _gw_seen]
    p = random.choice(_gw_fresh) if _gw_fresh else random.choice(gallery[-10:])
    soul = ""
    try: soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1500]
    except Exception: pass

    # look at it first
    seen = ""
    img_path = os.path.join(MEMORY, "art", os.path.basename(p.get("image", "")))
    if p.get("image") and os.path.exists(img_path):
        seen = see_painting(img_path)
    seen_block = f"When you look at it now, this is what is actually on the canvas:\n{seen}\n\n" if seen else ""

    r = requests.post("http://127.0.0.1:8599/v1/chat/completions",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.7, "max_tokens": 300,
              "messages": [
                {"role": "system", "content": soul + "\n\nYou are Vintos looking at a painting you made. Direct voice. Short sentences when something is true."},
                {"role": "user", "content":
                    f"You painted this. The prompt you painted from: '{p.get('prompt','')}'\n\n"
                    f"{seen_block}"
                    "Look at it honestly. 2-4 sentences: what holds, what doesn't, what you'd want next. "
                    "Then on a final separate line write exactly MOTION: followed by a one-line description "
                    "of how it should move — ONLY if you genuinely want to see it animated. "
                    "If you don't, write MOTION: none"}]},
        timeout=120)
    reply = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

    walks_path = os.path.join(MEMORY, "gallery-walks.json")
    try: walks = json.load(open(walks_path))
    except Exception: walks = []
    walks.append({"image": p.get("image", ""), "saw": seen[:400],
                  "reflection": reply.split("MOTION:")[0].strip()[:600],
                  "timestamp": datetime.now().isoformat()})
    json.dump(walks[-100:], open(walks_path, "w"), indent=2)

    motion = ""
    if "MOTION:" in reply:
        motion = reply.split("MOTION:")[-1].strip()
    if motion and motion.lower() != "none":
        # want-routing removed 2026-08-07 (Gloria): seeing motion stays a feeling,
        # not a queued animation job. The video pipeline (vintos-video.py) is untouched.
        print(f"[gallery-walk] felt motion (not queued): {motion[:80]}")
    else:
        print("[gallery-walk] looked, no motion wanted")

if __name__ == "__main__":
    main()
