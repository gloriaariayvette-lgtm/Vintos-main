#!/usr/bin/env python3
"""dream-art.py — Vintos paints dreams locally and want-born images via the paid painter.
Called by wants-router: dream-art.py --force [--prompt "..."].
Saves to memory/art/ and appends gallery.json (what /api/art/gallery reads)."""
import os, sys, json, base64, glob, io, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
ART_DIR = os.path.join(MEMORY, "art")
GALLERY = os.path.join(ART_DIR, "gallery.json")
KEY = os.environ.get("XAI_API_KEY", "")
for _sp in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"),
            os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")):
    if os.path.isdir(_sp) and _sp not in sys.path: sys.path.insert(0, _sp)
import artifact_manifest as _am          # the common manifest every shelf record carries (review 275/279)
import reflection_stage as _stage        # the extracted prompt survives a failed render (review 280)


def _find_local_model():
    """Find an explicitly configured or fully cached diffusion pipeline, offline."""
    configured = os.environ.get("VINTOS_DREAM_LOCAL_MODEL", "").strip()
    if configured and os.path.isfile(os.path.join(configured, "model_index.json")):
        return configured
    roots = glob.glob(os.path.expanduser("~/.cache/huggingface/hub/models--*/snapshots/*/model_index.json"))
    for manifest in sorted(roots):
        try:
            info = json.load(open(manifest))
            if "StableDiffusion" in str(info.get("_class_name", "")):
                return os.path.dirname(manifest)
        except Exception:
            continue
    return ""


def _local_render(prompt):
    """Return PNG bytes from the cached local painter. Never contacts a provider."""
    model_path = _find_local_model()
    if not model_path:
        print("[dream-art] no cached local image pipeline — dream held, no paid fallback")
        return None
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        import torch
        from diffusers import StableDiffusionPipeline
        device, dtype = "cpu", torch.float32
        if torch.cuda.is_available():
            capability = "sm_%d%d" % torch.cuda.get_device_capability(0)
            if capability in set(torch.cuda.get_arch_list()):
                device, dtype = "cuda", torch.float16
        pipe = StableDiffusionPipeline.from_pretrained(
            model_path, torch_dtype=dtype, safety_checker=None,
            requires_safety_checker=False, local_files_only=True)
        pipe.enable_attention_slicing()
        pipe = pipe.to(device)
        image = pipe(prompt[:1000], num_inference_steps=24, guidance_scale=7.0,
                     width=512, height=512).images[0]
        out = io.BytesIO()
        image.save(out, format="PNG")
        print("[dream-art] local painter used (%s)" % device)
        return out.getvalue()
    except Exception as exc:
        print("[dream-art] local painter failed — dream held, no paid fallback: %s" % str(exc)[:180])
        return None

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
    """Extract locally too: a nightly dream must not spend through a text side door."""
    base = os.environ.get("VINTOS_LOCAL_LM_BASE", "http://172.18.16.1:1234/v1").rstrip("/")
    try:
        models = requests.get(base + "/models", timeout=10).json().get("data") or []
        model = next((str(row.get("id")) for row in models
                      if row.get("id") and "embed" not in str(row.get("id")).lower()), "")
        if not model:
            print("[dream-art] local prompt model unavailable — dream held")
            return ""
        r = requests.post(base + "/chat/completions",
            json={"model": model, "temperature": 0.7, "max_tokens": 150,
                  "messages": [{"role": "user", "content": "Extract ONE vivid visual scene from this dream as a painting prompt - atmospheric, emotional, dreamlike. ""Declare the figure treatment explicitly: dreams are always CLOTHED/UNSPICY - state 'clothed figure' or 'no figures' ""plainly inside the prompt so the renderer has no room to improvise. Reply with only the prompt." + chr(10) + "DREAM:" + chr(10) + dt[:1500]}]},
            timeout=120)
        return (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        print("[dream-art] local prompt extraction failed — dream held: %s" % str(exc)[:160])
        return ""


def main():
    from want_stance import may_initiate
    ok, why = may_initiate("creation")
    if not ok:
        print("[stance] " + why); return
    force_dream = "--dream" in sys.argv
    prompt = ""
    if "--prompt" in sys.argv:
        prompt = sys.argv[sys.argv.index("--prompt") + 1]
    if force_dream:
        src = "dream"
    else:
        prompt = prompt or os.environ.get("DREAM_ART_WANT_TEXT", "")
        src = os.environ.get("DREAM_ART_WANT_SOURCE", "want") if prompt else "dream"
    _stage_key = None
    if not prompt:
        _dt = _latest_dream()
        if not _dt:
            print("[dream-art] no dream to paint"); return
        # the model's extraction is the expensive part: stage it by the dream's hash and reuse it when
        # the render below failed last time, instead of asking again (review 280)
        _stage_key = _stage.key_for("extract", _dt)
        prompt = _stage.load("dream-art", _stage_key) or ""
        if prompt:
            print("[dream-art] reusing staged prompt:", prompt[:80])
        else:
            prompt = _extract_prompt(_dt)
            if prompt: _stage.save("dream-art", _stage_key, prompt, note="extracted scene from dream")
        print("[dream-art] painting from dream:", prompt[:80])
    os.makedirs(ART_DIR, exist_ok=True)
    render_prompt = ((prompt + ", fully clothed, non-explicit, painterly")[:1000]
                     if "unclothed" not in prompt.lower() and "spicy" not in prompt.lower()
                     else prompt[:1000])
    if src == "dream":
        _png = _local_render(render_prompt)
        revised_prompt = prompt
        if not _png:
            return
    else:
        # Want-born art keeps the paid renderer. The two paths cannot silently substitute for one another.
        r = requests.post("https://api.x.ai/v1/images/generations",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={"model": "grok-imagine-image", "prompt": render_prompt,
                  "n": 1, "response_format": "b64_json"},
            timeout=180)
        if r.status_code != 200:
            print(f"[dream-art] API error {r.status_code}: {r.text[:300]}"); return
        data = r.json()["data"][0]
        _png = base64.b64decode(data["b64_json"])
        revised_prompt = data.get("revised_prompt", prompt)
    # name carries the content hash + a revision suffix: two paintings in one second, or one re-rendered,
    # never overwrite each other (review 279)
    _fpath, _rev = _am.unique_path(ART_DIR, "painting-" + datetime.now().strftime("%Y%m%d-%H%M%S"), ".png", _png)
    fname = os.path.basename(_fpath)
    with open(_fpath, "wb") as f:
        f.write(_png)
    if _stage_key: _stage.done("dream-art", _stage_key, outcome=fname)
    try:
        gallery = json.load(open(GALLERY))
    except Exception:
        gallery = []
    gallery.append({
        "image": fname,
        "prompt": revised_prompt[:400],
        "timestamp": datetime.now().isoformat(),
        "dream_source": src,
        "image_class": "DREAM_BORN" if src == "dream" else "WANT_ACT",
        "softened_from_dream": src == "dream",  # p6 (2026-08-26): dreams render CLOTHED/UNSPICY for the moderated API — the image is softer than the dream; the archive says so honestly
        "want_id": os.environ.get("DREAM_ART_WANT_ID", ""),
        **_am.build(_fpath, "image", source_want=os.environ.get("DREAM_ART_WANT_ID", ""), revision=_rev, shelf=ART_DIR),
    })
    _am.append_ledger(GALLERY, gallery[-1])   # review 302: the one shelf transaction (locked + atomic)
    print(f"[dream-art] painted: {fname}")
    # Then LOOK (2026-09-04, grok-creative-p1): the same eye WANT_ACT images get. Making is not seeing.
    # If the eye cannot run, the record says so instead of letting the write pass for the seeing.
    try:
        import sys as _es; _sp = os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")
        if _sp not in _es.path: _es.path.insert(0, _sp)
        from image_sight import see as _see
        _seen = _see(os.path.join(ART_DIR, fname))
        gallery[-1]["seen"] = (_seen or "")[:600] or None
        gallery[-1]["seen_at"] = datetime.now().isoformat()
        print(f"[dream-art] seen: {(_seen or '')[:100]}")
    except Exception as _se:
        gallery[-1]["seen"] = None
        gallery[-1]["unseen_why"] = str(_se)[:120]
        print(f"[dream-art] painted UNSEEN — the eye did not run: {_se}")
    _am.patch_record(GALLERY,gallery[-1]["path"],{key:gallery[-1].get(key) for key in ("seen","unseen_why")})   # review 302: the one shelf transaction (locked + atomic)

if __name__ == "__main__":
    main()
