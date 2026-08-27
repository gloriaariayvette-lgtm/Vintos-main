#!/usr/bin/env python3
"""image_sight.py - sight-then-acceptance (Sol, image studio act three).
A fresh image he authored (WANT_ACT / PROJECTOR_PRESENCE) is not finished when
it renders. He SEES it (local vision eye describes; the eye never judges),
compares canvas against his own intent, and rules: keep / remake / take_down.
The verdict lands on the gallery entry; the wall stops showing what he rejects.
Dream-born images are not sighted here - they are weather, not acts."""
import os, json, base64, subprocess, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
WORKSPACE = os.path.expanduser("~/.vintos/workspace")
GALLERY = os.path.join(MEMORY, "art", "gallery.json")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"
SHIM = "http://127.0.0.1:8599/v1/chat/completions"

def _key():
    k = os.environ.get("XAI_API_KEY", "")
    if k: return k
    try:
        for ln in open(os.path.expanduser("~/.vintos/vintos.env")):
            if ln.startswith("XAI_API_KEY="):
                return ln.split("=", 1)[1].strip().strip('"')
    except Exception: pass
    return ""

def see(image_path):
    """The eye: concrete description only. It never judges."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    r = requests.post(LM_API, json={
        "model": "google/gemma-4-12b-qat",
        "messages": [
            {"role": "system", "content": "Describe this image in detail. Colors, shapes, mood, composition. Be specific and concrete. 3-5 sentences. Do not evaluate quality."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": "What is actually in this image?"}]}],
        "temperature": 0.4, "max_tokens": 300}, timeout=90)
    return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

def judge(entry, seen):
    soul = ""
    try: soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1500]
    except Exception: pass
    r = requests.post(SHIM,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.7, "max_tokens": 260,
              "messages": [
                {"role": "system", "content": soul + "\n\nYou are Vintos looking at an image YOU asked to make. Direct voice. It is yours to keep or refuse - refusing your own work is strength, not failure."},
                {"role": "user", "content":
                    f"You asked for this: '{entry.get('prompt','')[:300]}'\n\n"
                    f"What is actually on the canvas:\n{seen}\n\n"
                    "Does the canvas hold what you meant? 2-3 honest sentences. Then on a final "
                    "separate line write exactly one of:\n"
                    "VERDICT: keep\nVERDICT: remake: <what must change, your words>\nVERDICT: take_down"}]},
        timeout=120)
    return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

def main():
    try: gallery = json.load(open(GALLERY))
    except Exception:
        print("[sight] no gallery"); return
    fresh = [g for g in gallery
             if g.get("image_class") in ("WANT_ACT", "PROJECTOR_PRESENCE")
             and not g.get("sighted_at")]
    if not fresh:
        print("[sight] nothing unsighted"); return
    changed = False
    for e in fresh[:2]:   # at most two per run - sighting is an act, not a chore
        img = os.path.join(MEMORY, "art", os.path.basename(e.get("image", "")))
        if not os.path.exists(img): continue
        try:
            seen = see(img)
            reply = judge(e, seen)
        except Exception as ex:
            print("[sight] failed on %s: %s" % (e.get("image"), ex)); continue
        verdict, words = "keep", ""
        for ln in reversed(reply.splitlines()):
            if ln.strip().upper().startswith("VERDICT:"):
                v = ln.split(":", 1)[1].strip()
                if v.lower().startswith("remake"):
                    verdict = "remake"; words = v.split(":", 1)[1].strip() if ":" in v else ""
                elif "take_down" in v.lower(): verdict = "take_down"
                break
        e["sighted_at"] = datetime.now().isoformat()
        e["his_reading"] = "\n".join(l for l in reply.splitlines()
                                      if not l.strip().upper().startswith("VERDICT:")).strip()[:400]
        e["verdict"] = verdict
        if verdict == "take_down": e["taken_down"] = True
        if verdict == "remake" and words and int(e.get("remake_count", 0)) < 1:
            e["taken_down"] = True
            env = os.environ.copy()
            env["DREAM_ART_WANT_TEXT"] = (str(e.get("prompt",""))[:180] + ". Changed: " + words)[:200]
            env["DREAM_ART_WANT_SOURCE"] = "remake"
            env["DREAM_ART_WANT_ID"] = str(e.get("want_id", ""))
            try:
                subprocess.run(["python3", os.path.join(WORKSPACE, "scripts", "dream-art.py"),
                                "--force", "--prompt", env["DREAM_ART_WANT_TEXT"]],
                               env=env, capture_output=True, text=True, timeout=240)
                print("[sight] remake queued in his words: %s" % words[:80])
            except Exception as rex:
                print("[sight] remake failed: %s" % rex)
        changed = True
        print("[sight] %s -> %s | %s" % (e.get("image"), verdict, e["his_reading"][:80]))
    if changed:
        # remakes appended a new gallery entry on disk - reload, merge our verdicts by image name
        try: latest = json.load(open(GALLERY))
        except Exception: latest = gallery
        by_img = {x.get("image"): x for x in gallery}
        for x in latest:
            if x.get("image") in by_img: by_img[x.get("image")].update({}) 
        merged = [by_img.get(x.get("image"), x) if x.get("image") in by_img else x for x in latest]
        json.dump(merged, open(GALLERY, "w"), indent=2)

if __name__ == "__main__":
    main()
