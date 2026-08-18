#!/usr/bin/env python3
"""dream-art.py — Vintos paints via xAI grok-imagine-image.
Called by wants-router: dream-art.py --force [--prompt "..."].
Saves to memory/art/ and appends gallery.json (what /api/art/gallery reads)."""
import os, sys, json, base64, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
ART_DIR = os.path.join(MEMORY, "art")
GALLERY = os.path.join(ART_DIR, "gallery.json")
KEY = os.environ.get("XAI_API_KEY", "")

def _latest_dream():
    import json, os
    try:
        d = json.load(open(os.path.expanduser("~/.vintos/workspace/memory/dream-log.json")))
        for night in reversed(d.get("nights", [])):
            texts = [x.get("dream_text","") for x in night.get("dreams",[]) if x.get("dream_text")]
            if texts: return chr(10).join(texts)
    except Exception as e: print("[dream-art] dream-log error:", e)
    return ""

def _extract_prompt(dt):
    import requests, os
    r = requests.post("https://api.x.ai/v1/chat/completions",
        headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY","")},
        json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.7, "max_tokens": 150,
              "messages": [{"role": "user", "content": "Extract ONE vivid visual scene from this dream as a painting prompt - atmospheric, emotional, dreamlike. ""Declare the figure treatment explicitly: dreams are always CLOTHED/UNSPICY - state 'clothed figure' or 'no figures' ""plainly inside the prompt so the renderer has no room to improvise. Reply with only the prompt." + chr(10) + "DREAM:" + chr(10) + dt[:1500]}]},
        timeout=120)
    return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def main():
    force_dream = "--dream" in sys.argv
    prompt = ""
    if "--prompt" in sys.argv:
        prompt = sys.argv[sys.argv.index("--prompt") + 1]
    if force_dream:
        src = "dream"
    else:
        prompt = prompt or os.environ.get("DREAM_ART_WANT_TEXT", "")
        src = os.environ.get("DREAM_ART_WANT_SOURCE", "want") if prompt else "dream"
    if not prompt:
        _dt = _latest_dream()
        if not _dt:
            print("[dream-art] no dream to paint"); return
        prompt = _extract_prompt(_dt)
        print("[dream-art] painting from dream:", prompt[:80])
    os.makedirs(ART_DIR, exist_ok=True)
    r = requests.post("https://api.x.ai/v1/images/generations",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"model": "grok-imagine-image", "prompt": (prompt + ", fully clothed, non-explicit, painterly")[:1000] if "unclothed" not in prompt.lower() and "spicy" not in prompt.lower() else prompt[:1000],
              "n": 1, "response_format": "b64_json"},
        timeout=180)
    if r.status_code != 200:
        print(f"[dream-art] API error {r.status_code}: {r.text[:300]}"); return
    data = r.json()["data"][0]
    fname = f"painting-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    with open(os.path.join(ART_DIR, fname), "wb") as f:
        f.write(base64.b64decode(data["b64_json"]))
    try:
        gallery = json.load(open(GALLERY))
    except Exception:
        gallery = []
    gallery.append({
        "image": fname,
        "prompt": data.get("revised_prompt", prompt)[:400],
        "timestamp": datetime.now().isoformat(),
        "dream_source": src,
    })
    json.dump(gallery, open(GALLERY, "w"), indent=2)
    print(f"[dream-art] painted: {fname}")

if __name__ == "__main__":
    main()
