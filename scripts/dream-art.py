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


# Prefer the strongest cached image model, so a better one is used automatically when present.
_PIPE_RANK = (("FluxPipeline", 3), ("StableDiffusionXLPipeline", 2), ("StableDiffusion", 1))


def _rank_of(cls):
    return next((r for k, r in _PIPE_RANK if k in str(cls)), 0)


def _has_cuda():
    try:
        import torch
        if not torch.cuda.is_available(): return False
        return ("sm_%d%d" % torch.cuda.get_device_capability(0)) in set(torch.cuda.get_arch_list())
    except Exception:
        return False


def _find_local_model():
    """Find the BEST cached diffusion pipeline (Flux > SDXL > SD), offline. Returns (path, class).
    Without a usable GPU, Flux (8B) is too slow to finish, so the best CPU-practical model wins,
    and a turbo SDXL is preferred over a full one."""
    configured = os.environ.get("VINTOS_DREAM_LOCAL_MODEL", "").strip()
    if configured and os.path.isfile(os.path.join(configured, "model_index.json")):
        try:
            cls = str(json.load(open(os.path.join(configured, "model_index.json"))).get("_class_name", ""))
        except Exception:
            cls = ""
        return configured, cls
    gpu = _has_cuda()
    best = ("", "", 0)
    for manifest in sorted(glob.glob(os.path.expanduser("~/.cache/huggingface/hub/models--*/snapshots/*/model_index.json"))):
        try:
            cls = str(json.load(open(manifest)).get("_class_name", ""))
        except Exception:
            continue
        rank = _rank_of(cls)
        if not gpu and "Flux" in cls:
            continue
        if "turbo" in manifest.lower():
            rank += 0.5 if not gpu else 0
        if rank > best[2]:
            best = (os.path.dirname(manifest), cls, rank)
    return best[0], best[1]


def _local_render(prompt):
    """Return PNG bytes from the BEST cached local painter (Flux/SDXL/SD). Never contacts a provider."""
    model_path, model_cls = _find_local_model()
    if not model_path:
        print("[dream-art] no cached local image pipeline — dream held, no paid fallback")
        return None
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        import torch
        device, dtype = ("cuda", torch.float16) if _has_cuda() else ("cpu", torch.float32)
        # Load the pipeline class the cached model actually is, with class-appropriate settings.
        if "Flux" in model_cls:
            from diffusers import FluxPipeline
            pipe = FluxPipeline.from_pretrained(model_path, torch_dtype=dtype, local_files_only=True)
            steps, size, kw = 20, 1024, {"guidance_scale": 3.5}
        elif "XL" in model_cls:
            from diffusers import StableDiffusionXLPipeline
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_path, torch_dtype=dtype, local_files_only=True, use_safetensors=True)
            steps, size, kw = 30, 1024, {"guidance_scale": 7.0}
            if "turbo" in model_path.lower():   # distilled: 1-4 steps, no CFG, trained at 512
                steps, size, kw = 2, 512, {"guidance_scale": 0.0}
        else:
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained(
                model_path, torch_dtype=dtype, safety_checker=None,
                requires_safety_checker=False, local_files_only=True)
            steps, size, kw = 24, 512, {"guidance_scale": 7.0}
        try: pipe.enable_attention_slicing()
        except Exception: pass
        if device == "cuda":
            try: pipe.enable_model_cpu_offload()   # let big models (SDXL/Flux) fit smaller VRAM
            except Exception: pipe = pipe.to(device)
        else:
            pipe = pipe.to(device)
        image = pipe(prompt[:1000], num_inference_steps=steps, width=size, height=size, **kw).images[0]
        out = io.BytesIO()
        image.save(out, format="PNG")
        print("[dream-art] local painter used (%s, %s)" % (device, model_cls or "StableDiffusion"))
        return out.getvalue()
    except Exception as exc:
        print("[dream-art] local painter failed — dream held, no paid fallback: %s" % str(exc)[:180])
        return None

def _openai_render(prompt):
    """PNG bytes from OpenAI's image model, or None. The model is OPENAI_IMAGE_MODEL in vintos.env."""
    try:
        from env_file import value as _ev      # the one reader of ~/.vintos/vintos.env
        key, model = _ev("OPENAI_API_KEY"), _ev("OPENAI_IMAGE_MODEL", "gpt-image-1")
    except Exception:
        key, model = os.environ.get("OPENAI_API_KEY", ""), os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    if not key:
        print("[dream-art] no OPENAI_API_KEY — OpenAI painter unavailable")
        return None
    try:
        r = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt[:4000], "n": 1, "size": "1024x1024"},
            timeout=240)
        if r.status_code != 200:
            print(f"[dream-art] OpenAI image error {r.status_code}: {r.text[:300]}")
            return None
        png = base64.b64decode(r.json()["data"][0]["b64_json"])
        print(f"[dream-art] OpenAI painter used ({model})")
        return png
    except Exception as exc:
        print("[dream-art] OpenAI painter failed: %s" % str(exc)[:180])
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
    if not prompt.strip():
        print("[dream-art] no extracted scene — dream held"); return
    os.makedirs(ART_DIR, exist_ok=True)
    render_prompt = ((prompt + ", fully clothed, non-explicit, painterly")[:1000]
                     if "unclothed" not in prompt.lower() and "spicy" not in prompt.lower()
                     else prompt[:1000])
    if src == "dream":
        # Dreams paint through OpenAI's image model (Gloria, 2026-09-23); the free local painter is
        # the only fallback, and a dream never reaches grok-imagine.
        _png = _openai_render(render_prompt) or _local_render(render_prompt)
        revised_prompt = prompt
        if not _png:
            return
    else:
        _png = _openai_render(render_prompt)
        revised_prompt = prompt
        if not _png:
            # Want-born art keeps the paid renderer: OpenAI first, grok-imagine only when OpenAI refuses or fails.
            # ... on her SuperGrok subscription, never the API key (Gloria, 2026-09-25).
            import grok_subscription as _gs
            try:
                _png, _rev_p = _gs.image(render_prompt)
            except _gs.Unavailable as e:
                print(f"[dream-art] grok subscription: {e} — nothing painted"); return
            except Exception as e:
                print(f"[dream-art] grok error: {e}"); return
            revised_prompt = _rev_p or prompt
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
