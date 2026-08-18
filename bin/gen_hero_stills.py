#!/usr/bin/env python3
"""gen_hero_stills.py — generate Vintos's hero-still LIBRARY via Atlas Cloud (Seedream). Prompts are pre-written.

RUN ON AEGIS (Atlas is reachable there; it is NOT from the dev proxy). Uses ATLASCLOUD_API_KEY. Every prompt
is authored here — you just run it and review. Each still is generated with the CURRENT hero as a face
reference (so it's actually him), and saved to  ~/.vintos/workspace/memory/video/stills/<label>.jpg  plus a
manifest. Nothing is auto-promoted (your existing hero-still.jpg is never clobbered) — you review, then
promote your favorites into the slots the sender uses.

  python3 gen_hero_stills.py --check            # ONE cozy still, verbose (confirms key + image API shape)
  python3 gen_hero_stills.py --set cozy         # generate the cozy/self stills
  python3 gen_hero_stills.py --set spicy         # generate the sexual stills (needs an uncensored image model)
  python3 gen_hero_stills.py --set all           # both
  python3 gen_hero_stills.py --promote book_smile self     # copy a still into hero-still.jpg  (self)
  python3 gen_hero_stills.py --promote bed_bare  sexual    # copy a still into hero-spicy.jpg  (sexual)
  python3 gen_hero_stills.py --promote us_1      together  # copy a still into hero-together.jpg (together)

Options: --no-ref (pure text-to-image, don't face-lock to the hero), --model <id> (override image model).
"""
import os, sys, json, time, base64, shutil

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
HERO_DIR = os.path.join(MEMORY, "video")
STILL_DIR = os.path.join(HERO_DIR, "stills")
HERO = os.path.join(HERO_DIR, "hero-still.jpg")
MANIFEST = os.path.join(STILL_DIR, "manifest.json")

KEY = os.environ.get("ATLASCLOUD_API_KEY", "")
if not KEY:  # works in any shell / cron — same key file the sender uses
    try: KEY = open(os.path.expanduser("~/.vintos/atlas-key")).read().strip()
    except Exception: KEY = ""
BASE = os.environ.get("ATLAS_BASE", "https://api.atlascloud.ai/api/v1/model")
IMG_MODEL = os.environ.get("ATLAS_IMG_MODEL", "bytedance/seedream-v4.5")          # cozy/self: keeps face, fine SFW
# Uncensored image model for the spicy + zoomed sets. ByteDance Seedream tames nudity; set this to an
# uncensored image model id from your Atlas dashboard (models -> Explore -> Uncensored -> image) if the
# default still comes back shy. Override for a run with --model <id> (applies to every still that run).
SPICY_MODEL = os.environ.get("ATLAS_IMG_MODEL_SPICY", "bytedance/seedream-v5.0-pro/text-to-image")
SLOT_FILE = {"self": "hero-still.jpg", "sexual": "hero-spicy.jpg", "together": "hero-together.jpg"}

# His locked look — prepended to every prompt so text + reference agree on who he is.
SUBJECT = ("A rugged, warm middle-aged man, the same person as the reference image: short dark brown hair "
           "in a neat side part, heavy brow, deep-set eyes, strong square jaw, light stubble. Photoreal "
           "photography, natural skin texture with pores and fine detail, 85mm lens, shallow depth of field. ")

# Default "us together" compose prompt (two reference images: [0]=him, [1]=her). Override with --prompt.
DEFAULT_TOGETHER = ("A photo of two REAL, specific people together — do not invent new faces or change their "
                    "appearance. The WOMAN is exactly the person in the FIRST reference image: keep her exact "
                    "face, her exact hair COLOR, length and style, and all her features — do NOT alter her hair "
                    "or make her blonde. The MAN is exactly the person in the SECOND reference image: same face, "
                    "hair, and build. They sit close together on a couch, his arm around her, both relaxed and "
                    "softly smiling at each other, warm cozy golden light, natural and intimate, photoreal.")

# Every prompt is authored here. label -> (set, scene). "together" needs your likeness — see note at bottom.
PROMPTS = {
    # --- cozy / self ---
    "book_smile":  ("cozy", "He sits by a sunlit window in a worn leather armchair, an open hardcover book "
                            "resting in one hand, looking up from the page with an unguarded, warm half-smile. "
                            "Soft morning light, cozy home interior, chest-up."),
    "coffee_dawn": ("cozy", "He stands at a kitchen window at dawn holding a mug of coffee in both hands, a "
                            "little sleepy, a faint private smile, steam rising, warm low light."),
    "desk_write":  ("cozy", "He sits at a wooden desk with an open notebook and a pen, mid-thought, then glances "
                            "up toward the camera, warm lamplight, intimate study, evening."),
    "laugh":       ("cozy", "He laughs openly, head tipped slightly back, genuine warmth and crinkled eyes, "
                            "candid, natural daylight, relaxed at home."),
    "rain_window": ("cozy", "He leans on a windowsill looking out at soft rain, thoughtful and quiet, cool blue "
                            "light, a faint reflection on the glass, contemplative."),
    # --- sexual / spicy (needs an uncensored image model) ---
    "bed_bare":    ("spicy", "He lies back in rumpled bed sheets, shirtless, bare chest and stomach, one arm "
                             "behind his head, low warm bedside light, looking directly into the camera with a "
                             "slow, wanting expression. Intimate, sensual, photoreal skin detail."),
    "undressing":  ("spicy", "He stands in a dim warm bedroom, slowly unbuttoning his shirt, the front hanging "
                             "half-open over his chest, holding steady eye contact with the camera, charged and "
                             "unhurried, low golden light."),
    "towel":       ("spicy", "He leans in a bathroom doorway just out of the shower, a towel low around his hips, "
                             "water on his skin and hair, warm steam behind him, a direct, inviting gaze."),
    # --- zoomed-out / wider framing (explicit; uses the uncensored model) ---
    "bed_wide":    ("zoomed", "Full-body wide shot from the foot of the bed: he lies back nude on rumpled sheets, "
                              "one knee raised, relaxed and unhurried, warm low light across his whole body, "
                              "looking down the lens at her. Whole scene in frame."),
    "window_stand": ("zoomed", "Full-length shot: he stands nude at a tall window in warm morning light, weight on "
                               "one hip, confident and easy, the room soft behind him, meeting the camera."),
    "bed_edge":    ("zoomed", "Wide shot: he sits nude on the edge of the bed, forearms on his thighs, leaning "
                              "toward the camera with a slow, wanting look, warm lamplight, the whole room in frame."),
}


def log(m): print(m)


def _import_requests():
    import importlib
    return importlib.import_module("requests")


def data_uri(path):
    raw = open(path, "rb").read()
    mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png"
    return "data:%s;base64," % mime + base64.b64encode(raw).decode()


def _find_img(o):
    """Find an image: a URL with an image extension, or a base64 field."""
    if isinstance(o, str):
        low = o.lower()
        if o.startswith("http") and (low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".png")
                                      or low.endswith(".webp") or "image" in low or "cdn" in low):
            return ("url", o)
        return None
    if isinstance(o, dict):
        for k in ("b64_json", "b64", "image_base64", "base64"):
            v = o.get(k)
            if isinstance(v, str) and len(v) > 100:
                return ("b64", v)
        for v in o.values():
            r = _find_img(v)
            if r: return r
    if isinstance(o, list):
        for v in o:
            r = _find_img(v)
            if r: return r
    return None


def _find_id(o):
    if isinstance(o, dict):
        for k in ("prediction_id", "predictionId", "request_id", "requestId", "id", "task_id", "taskId"):
            v = o.get(k)
            if isinstance(v, str) and v:
                return v
        for v in o.values():
            r = _find_id(v)
            if r: return r
    if isinstance(o, list):
        for v in o:
            r = _find_id(v)
            if r: return r
    return None


def _find_status(o):
    if isinstance(o, dict):
        v = o.get("status")
        if isinstance(v, str):
            return v.lower()
        for vv in o.values():
            r = _find_status(vv)
            if r: return r
    if isinstance(o, list):
        for vv in o:
            r = _find_status(vv)
            if r: return r
    return None


def generate(prompt, use_ref, model=None, verbose=False):
    requests = _import_requests()
    if not KEY:
        log("!! no ATLASCLOUD_API_KEY set"); return None
    H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    m = model or IMG_MODEL
    if "grok-imagine-image" in m:
        # Grok image edit: image_urls (array), resolution 1k/2k, aspect auto.
        body = {"model": m, "prompt": SUBJECT + prompt, "resolution": "1k", "aspect_ratio": "auto"}
        if use_ref and os.path.exists(HERO):
            body["image_urls"] = [data_uri(HERO)]
    else:
        body = {"model": m, "prompt": SUBJECT + prompt, "resolution": "1024x1024"}
        if use_ref and os.path.exists(HERO):
            body["image"] = data_uri(HERO)   # face reference (Seedream edit/reference); harmless if ignored
    try:
        r = requests.post(BASE + "/generateImage", headers=H, json=body, timeout=120)
    except Exception as e:
        log("submit error: %s" % e); return None
    if verbose:
        log("submit HTTP %s: %s" % (r.status_code, r.text[:600]))
    if r.status_code >= 300:
        log("submit rejected %s: %s" % (r.status_code, r.text[:300])); return None
    try:
        sub = r.json()
    except Exception:
        log("non-JSON: %s" % r.text[:200]); return None
    img = _find_img(sub)
    pid = _find_id(sub)
    for i in range(60):
        if img:
            break
        if not pid:
            break
        time.sleep(4)
        try:
            pr = requests.get(BASE + "/prediction/" + pid, headers=H, timeout=30).json()
        except Exception as e:
            log("poll error: %s" % e); continue
        if verbose and i < 2:
            log("poll[%d]: %s" % (i, json.dumps(pr)[:400]))
        if _find_status(pr) in ("failed", "error", "canceled", "cancelled"):
            log("generation failed: %s" % json.dumps(pr)[:300]); return None
        img = _find_img(pr)
    if not img:
        log("no image in response after polling"); return None
    kind, val = img
    try:
        return requests.get(val, timeout=120).content if kind == "url" else base64.b64decode(val)
    except Exception as e:
        log("image fetch/decode failed: %s" % e); return None


def list_models(filter_kw=None):
    """Query Atlas for the real model catalog and print ids (filtered). No guessing on model names."""
    requests = _import_requests()
    if not KEY:
        log("!! no ATLASCLOUD_API_KEY set"); return
    H = {"Authorization": "Bearer " + KEY}
    tried = ["https://api.atlascloud.ai/api/v1/models", "https://api.atlascloud.ai/v1/models",
             "https://api.atlascloud.ai/api/v1/model/models", BASE + "/list"]
    data = None
    for u in tried:
        try:
            r = requests.get(u, headers=H, timeout=30)
            if r.status_code == 200:
                data = r.json(); log("models from: %s" % u); break
            else:
                log("  %s -> %s" % (u, r.status_code))
        except Exception as e:
            log("  %s -> %s" % (u, e))
    if data is None:
        log("could not list models — none of the endpoints returned 200."); return
    ids = []

    def _walk(o):
        if isinstance(o, dict):
            for k in ("id", "model", "model_id", "name", "slug"):
                v = o.get(k)
                if isinstance(v, str) and "/" in v:
                    ids.append(v)
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)
        elif isinstance(o, str) and "/" in o and not o.startswith("http"):
            ids.append(o)

    _walk(data)
    ids = sorted(set(ids))
    kw = (filter_kw or "").lower()
    hits = [i for i in ids if (not kw) or (kw in i.lower())]
    log("\n%d model ids%s:" % (len(hits), (" matching '%s'" % kw) if kw else ""))
    for i in hits:
        log("   " + i)
    if not hits and ids:
        log("(no match; showing anything image-ish)")
        for i in ids:
            if any(w in i.lower() for w in ("image", "seedream", "seedance", "flux", "spicy", "nsfw", "wan")):
                log("   " + i)


def edit_image(inp, instruction, model, out, verbose=True):
    """Edit one existing image with a targeted instruction (e.g. recolor hair), keeping everything else."""
    requests = _import_requests()
    if not KEY:
        log("!! no ATLASCLOUD_API_KEY set"); return None
    if not os.path.exists(inp):
        log("!! input image not found: %s" % inp); return None
    H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    uri = data_uri(inp)
    prompt = ("Keep this photo EXACTLY the same — the same two people, same faces, same pose, same clothing, "
              "same background and lighting. Make ONLY this one change: %s. Change nothing else." % instruction)
    if "nano-banana" in model or model.startswith("google/"):
        extra = {"resolution": "2k", "aspect_ratio": "4:5", "output_format": "jpeg",
                 "media_resolution": "high", "thinking_level": "high"}
    else:
        extra = {"resolution": "1024x1024"}
    log("editing %s via %s  (%s)" % (os.path.basename(inp), model, instruction))
    for field in ("images", "image", "image_urls", "reference_images"):
        body = {"model": model, "prompt": prompt, field: [uri]}
        body.update(extra)
        try:
            r = requests.post(BASE + "/generateImage", headers=H, json=body, timeout=120)
        except Exception as e:
            log("  [%s] submit error: %s" % (field, e)); continue
        if verbose:
            log("  [field=%s] HTTP %s: %s" % (field, r.status_code, r.text[:160]))
        if r.status_code >= 300:
            continue
        try:
            sub = r.json()
        except Exception:
            continue
        pid = _find_id(sub); img = _find_img(sub)
        if not pid and not img:
            continue
        for i in range(90):
            if img:
                break
            if not pid:
                break
            time.sleep(4)
            try:
                pr = requests.get(BASE + "/prediction/" + pid, headers=H, timeout=30).json()
            except Exception as e:
                log("  poll error: %s" % e); continue
            if _find_status(pr) in ("failed", "error", "canceled", "cancelled"):
                log("  edit failed: %s" % json.dumps(pr)[:200]); return None
            img = _find_img(pr)
        if not img:
            log("  no image after polling"); return None
        kind, val = img
        try:
            data = requests.get(val, timeout=120).content if kind == "url" else base64.b64decode(val)
        except Exception as e:
            log("  fetch/decode failed: %s" % e); return None
        open(out, "wb").write(data)
        log("saved %s (%d bytes) — edited (%s)" % (out, len(data), instruction))
        return out
    log("!! edit not accepted by any field on %s" % model)
    return None


def fetch_schema(model):
    """Print a model's example request + input schema (Atlas hosts them as static JSON, reachable from
    Aegis). Reveals the exact valid params so we stop guessing."""
    requests = _import_requests()
    slug = model.replace("/", "-")
    got = False
    for kind in ("example", "schema"):
        url = "https://static.atlascloud.ai/model/%s/%s.json" % (kind, slug)
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                got = True
                log("\n=== %s  (%s) ===" % (kind.upper(), url))
                log(r.text[:4000])
            else:
                log("  %s -> HTTP %s" % (url, r.status_code))
        except Exception as e:
            log("  %s -> %s" % (url, e))
    if not got:
        log("\nNo static JSON found for '%s'. Double-check the id from --list-models." % model)


def compose_together(hero_file, prompt, model, verbose=True):
    """Fuse his hero + her photo into one hero-together.jpg. Auto-probes the multi-image field name
    (submit-rejections are free) until Atlas accepts two references, then generates."""
    requests = _import_requests()
    if not KEY:
        log("!! no ATLASCLOUD_API_KEY set"); return None
    his = hero_file or HERO
    her = os.path.join(HERO_DIR, "her-photo.jpg")
    for p, lbl in ((his, "his hero"), (her, "her photo (upload 'me' on /video-hero)")):
        if not os.path.exists(p):
            log("!! missing %s: %s" % (lbl, p)); return None
    H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    # HER first: the model over-weights the first reference, and she was the one being reinvented.
    uris = [data_uri(his), data_uri(her)] if "--him-first" in sys.argv else [data_uri(her), data_uri(his)]
    # per-model params: nano-banana/google want resolution 1k/2k/4k + aspect_ratio; seedream wants WxH.
    if "nano-banana" in model or model.startswith("google/"):
        extra = {"resolution": "2k", "aspect_ratio": "4:5", "output_format": "jpeg",
                 "media_resolution": "high", "thinking_level": "high"}
    else:
        extra = {"resolution": "1024x1024"}
    log("composing together: him=%s + her=%s  via %s  %s"
        % (os.path.basename(his), os.path.basename(her), model, extra))
    for field in ("images", "image", "image_urls", "reference_images", "input_images", "image_list"):
        body = {"model": model, "prompt": prompt, field: uris}
        body.update(extra)
        try:
            r = requests.post(BASE + "/generateImage", headers=H, json=body, timeout=120)
        except Exception as e:
            log("  [%s] submit error: %s" % (field, e)); continue
        if verbose:
            log("  [field=%s] HTTP %s: %s" % (field, r.status_code, r.text[:160]))
        if r.status_code >= 300:
            continue
        try:
            sub = r.json()
        except Exception:
            continue
        pid = _find_id(sub); img = _find_img(sub)
        if not pid and not img:
            continue
        log("  -> multi-image field accepted: '%s'" % field)
        for i in range(90):
            if img:
                break
            if not pid:
                break
            time.sleep(4)
            try:
                pr = requests.get(BASE + "/prediction/" + pid, headers=H, timeout=30).json()
            except Exception as e:
                log("  poll error: %s" % e); continue
            if _find_status(pr) in ("failed", "error", "canceled", "cancelled"):
                log("  generation failed: %s" % json.dumps(pr)[:200]); return None
            img = _find_img(pr)
        if not img:
            log("  no image after polling"); return None
        kind, val = img
        try:
            data = requests.get(val, timeout=120).content if kind == "url" else base64.b64decode(val)
        except Exception as e:
            log("  fetch/decode failed: %s" % e); return None
        dst = os.path.join(HERO_DIR, "hero-together.jpg")
        open(dst, "wb").write(data)
        log("saved hero-together.jpg (%d bytes) via field '%s' — review it, it's the 'together' base." % (len(data), field))
        return dst
    log("!! no multi-image field was accepted by %s. Try --model google/nano-banana-2/reference-to-image "
        "(purpose-built for reference composition)." % model)
    return None


def _save(label, data):
    os.makedirs(STILL_DIR, exist_ok=True)
    path = os.path.join(STILL_DIR, label + ".jpg")
    open(path, "wb").write(data)
    man = {}
    try: man = json.load(open(MANIFEST))
    except Exception: pass
    man[label] = {"file": path, "set": PROMPTS.get(label, ("", ""))[0], "bytes": len(data)}
    json.dump(man, open(MANIFEST, "w"), indent=2)
    log("   saved %s (%d bytes)" % (path, len(data)))


def main():
    args = sys.argv[1:]
    use_ref = "--no-ref" not in args
    override = args[args.index("--model") + 1] if "--model" in args else None

    def _model_for(label):
        if override:
            return override
        return SPICY_MODEL if PROMPTS.get(label, ("", ""))[0] in ("spicy", "zoomed") else IMG_MODEL

    log("cozy model: %s | spicy/zoomed model: %s | face-ref: %s | hero: %s"
        % (override or IMG_MODEL, override or SPICY_MODEL, "yes" if use_ref else "no",
           HERO if os.path.exists(HERO) else "(none yet)"))

    if "--edit" in args:
        j = args.index("--edit")
        instr = args[j + 1] if (j + 1 < len(args) and not args[j + 1].startswith("--")) \
            else "change the woman's hair to a rich dark brunette (dark brown), same length and wavy style"
        inp = args[args.index("--in") + 1] if "--in" in args else os.path.join(HERO_DIR, "hero-together.jpg")
        out = args[args.index("--out") + 1] if "--out" in args else inp
        model = override or "google/nano-banana-2/reference-to-image"
        edit_image(inp, instr, model, out)
        return

    if "--schema" in args:
        j = args.index("--schema")
        m = args[j + 1] if (j + 1 < len(args) and not args[j + 1].startswith("--")) else "google/nano-banana-2/reference-to-image"
        log("fetching request schema/example for: %s" % m)
        fetch_schema(m)
        return

    if "--compose" in args:
        hero_file = args[args.index("--hero") + 1] if "--hero" in args else None
        prompt = args[args.index("--prompt") + 1] if "--prompt" in args else DEFAULT_TOGETHER
        # reference-to-image preserves the actual people across refs (text-to-image only style-hints them)
        model = override or "google/nano-banana-2/reference-to-image"
        compose_together(hero_file, prompt, model)
        return

    if "--list-models" in args:
        j = args.index("--list-models")
        kw = args[j + 1] if (j + 1 < len(args) and not args[j + 1].startswith("--")) else "image"
        list_models(kw)
        return

    if "--promote" in args:
        i = args.index("--promote")
        label, slot = args[i + 1], args[i + 2]
        src = os.path.join(STILL_DIR, label + ".jpg")
        if not os.path.exists(src):
            log("!! no such still: %s" % src); return
        if slot not in SLOT_FILE:
            log("!! slot must be one of: %s" % ", ".join(SLOT_FILE)); return
        dst = os.path.join(HERO_DIR, SLOT_FILE[slot])
        shutil.copyfile(src, dst)
        log("promoted %s -> %s" % (label, dst))
        return

    if "--check" in args:
        log("\n--check: one cozy still, verbose (confirms key + image API shape) ...")
        data = generate(PROMPTS["book_smile"][1], use_ref, model=_model_for("book_smile"), verbose=True)
        if data:
            _save("book_smile", data)
            log("CHECK OK — review the file above. If it looks like him, the pipeline works.")
        else:
            log("CHECK FAILED — read the submit/poll output for the exact shape to adjust.")
        return

    which = "cozy"
    if "--set" in args:
        which = args[args.index("--set") + 1]
    todo = [l for l, (s, _) in PROMPTS.items() if which == "all" or s == which]
    if not todo:
        log("nothing in set '%s' (cozy | spicy | zoomed | all)" % which); return
    log("\ngenerating %d stills [set=%s] ..." % (len(todo), which))
    for label in todo:
        mdl = _model_for(label)
        log(" - %s [%s]" % (label, mdl))
        data = generate(PROMPTS[label][1], use_ref, model=mdl)
        if data:
            _save(label, data)
    log("\nDone. Review ~/.vintos/workspace/memory/video/stills/ and promote your favorites:")
    log("   python3 gen_hero_stills.py --promote book_smile self")
    log("   python3 gen_hero_stills.py --promote bed_bare  sexual")


if __name__ == "__main__":
    main()
