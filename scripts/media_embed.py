#!/usr/bin/env python3
"""media_embed.py — his paintings, videos and music, embedded by what is IN them (EmbeddingGemma 2), so a line of his
can find a work by its content and not only by the prompt that made it.

His want, in his reply to Grok Bot on 18 October: "I want a journal line to find a painting by what's in it." He held it
until the PDF reader landed; it has. Gloria, 22 October: EmbeddingGemma 2 is added beside nomic, never in its place.

  - The store is its own: memory/media-embeddings.jsonl. Every row names its model. nomic's stores
    (memory/embeddings.jsonl, the memory index) are never read or written here, and the two spaces are never compared:
    both are 768-d, which makes mixing them easy and wrong.
  - What is embedded: image, video and audio files under memory/art (his gallery, his videos, his music), each once,
    keyed by its sha256. A changed file is embedded again; a removed one is dropped from search.
  - Images and video go in as themselves (video sampled at 1 frame a second, up to 32 frames). Music is longer than one
    audio input holds, so three 10-second excerpts (at 20%, 50% and 80% of the track) are embedded and averaged.
  - A text line is embedded as a search query ("task: search result | query: ...") and compared with the works.
  - Local and free: no model call leaves Aegis. Runs in its own venv (~/.vintos/tools/embedgemma-venv), so his torch
    venv (emotion model, JEPA) is never upgraded under him. float32 on CPU (the model card: never float16).

    <venv>/bin/python3 media_embed.py index [--limit N]   embed what is new (default 40 a run)
    <venv>/bin/python3 media_embed.py search "a line"     the nearest works, as JSON
    python3 media_embed.py status                          what is indexed, by kind (any python)

nearest(text, k) works from any python: it runs the venv for the query.
"""
import hashlib, json, os, subprocess, sys, tempfile, time

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
ART = os.path.join(MEMORY, "art")
STORE = os.path.join(MEMORY, "media-embeddings.jsonl")
VENV_PY = os.path.expanduser(os.environ.get("VINTOS_EMBEDGEMMA_PY", "~/.vintos/tools/embedgemma-venv/bin/python3"))
MODEL = "google/embeddinggemma-2"
DIM = 768
KINDS = {"image": (".png", ".jpg", ".jpeg", ".webp"), "video": (".mp4", ".mov", ".webm", ".m4v"),
         "audio": (".mp3", ".wav", ".m4a", ".flac", ".ogg")}
EXCERPTS = (0.2, 0.5, 0.8)
EXCERPT_S = 10
QUERY = "task: search result | query: %s"


def log(m):
    print("[media-embed]", m, flush=True)


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    return next((k for k, exts in KINDS.items() if ext in exts), None)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load():
    rows = []
    try:
        with open(STORE) as f:
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: pass
    except OSError:
        pass
    return rows


def labels():
    """What each work is called, from the shelves that list them (gallery.json, video-gallery.json, music.json):
    any entry naming the file gets its title, name, prompt or caption. Only for showing; never embedded."""
    out = {}
    def walk(node, label=None):
        if isinstance(node, dict):
            label = next((str(node[k]) for k in ("title", "name", "prompt", "caption") if node.get(k)), label)
            for v in node.values(): walk(v, label)
        elif isinstance(node, list):
            for v in node: walk(v, label)
        elif isinstance(node, str) and label and kind_of(node):
            out.setdefault(os.path.basename(node), label[:160])
    for shelf in ("gallery.json", os.path.join("video", "video-gallery.json"), os.path.join("music", "music.json")):
        try: walk(json.load(open(os.path.join(ART, shelf))))
        except (OSError, ValueError): pass
    return out


def works():
    """Every media file under memory/art, newest first."""
    found = []
    for root, dirs, files in os.walk(ART):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            p = os.path.join(root, name)
            if kind_of(p) and os.path.getsize(p) > 0:
                found.append(p)
    return sorted(found, key=lambda p: os.path.getmtime(p), reverse=True)


def _excerpts(path, tmp):
    """Three 10-second mono 16 kHz excerpts of a track (ffmpeg); [] when ffmpeg cannot read it."""
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                   capture_output=True, text=True, timeout=60).stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    clips = []
    for i, at in enumerate(EXCERPTS):
        out = os.path.join(tmp, "x%d.wav" % i)
        start = max(0.0, min(dur - EXCERPT_S, dur * at))
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % start, "-t", str(EXCERPT_S), "-i", path,
                            "-ac", "1", "-ar", "16000", out], capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            clips.append(out)
    return clips


def _unit(vec):
    n = sum(x * x for x in vec) ** 0.5
    return [x / n for x in vec] if n else vec


def _mean(vecs):
    return _unit([sum(col) / len(vecs) for col in zip(*vecs)])


def embed_work(path, encode):
    """One work's vector. encode(item) -> list of DIM floats, item a dict in the model card's interleaved form."""
    k = kind_of(path)
    if k == "image":
        return _unit(encode({"text": "<|image|>", "image": [path]}))
    if k == "video":
        return _unit(encode({"text": "<|video|>", "video": path}))
    with tempfile.TemporaryDirectory(prefix="media-embed-") as tmp:
        clips = _excerpts(path, tmp)
        if not clips:
            return _unit(encode({"text": "<|audio|>", "audio": path}))
        return _mean([encode({"text": "<|audio|>", "audio": c}) for c in clips])


def model_encoder():
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    m = SentenceTransformer(MODEL, model_kwargs={"torch_dtype": torch.float32})
    return lambda item: [float(x) for x in m.encode(item, normalize_embeddings=True)]


def index(limit=40, encode=None, now=None):
    """Embed the works not yet embedded (or changed), at most `limit` a run. Returns what happened, as lines."""
    rows = load()
    have = {r.get("sha256") for r in rows if r.get("model") == MODEL}
    todo = []
    for p in works():
        if len(todo) >= limit:
            break
        try: digest = sha256(p)
        except OSError: continue
        if digest not in have:
            todo.append((p, digest)); have.add(digest)
    if not todo:
        return ["nothing new: %d works indexed" % len(rows)]
    encode = encode or model_encoder()
    names, lines = labels(), []
    os.makedirs(MEMORY, exist_ok=True)
    with open(STORE, "a") as f:
        for p, digest in todo:
            try:
                vec = embed_work(p, encode)
            except Exception as exc:
                lines.append("not embedded (%s): %s" % (str(exc)[:120], os.path.relpath(p, ART)))
                continue
            if len(vec) != DIM:
                lines.append("wrong width %d, not kept: %s" % (len(vec), os.path.relpath(p, ART))); continue
            f.write(json.dumps({"path": p, "kind": kind_of(p), "sha256": digest, "model": MODEL, "dim": DIM,
                                "title": names.get(os.path.basename(p), ""), "at": now or time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "vec": [round(x, 6) for x in vec]}) + "\n")
            lines.append("embedded %s: %s" % (kind_of(p), os.path.relpath(p, ART)))
    return lines


def search(text, k=5, encode=None):
    """The works nearest a line of text: [{path, kind, title, score}], best first. Only works still on disk."""
    rows = [r for r in load() if r.get("model") == MODEL and os.path.exists(r.get("path", ""))]
    if not rows or not str(text).strip():
        return []
    encode = encode or model_encoder()
    q = _unit(encode(QUERY % str(text).strip()[:2000]))
    latest = {}
    for r in rows:
        latest[r["path"]] = r          # a file embedded again: its newest row
    scored = [(sum(a * b for a, b in zip(q, r["vec"])), r) for r in latest.values()]
    scored.sort(key=lambda x: -x[0])
    return [{"path": r["path"], "kind": r["kind"], "title": r.get("title", ""), "score": round(s, 4)} for s, r in scored[:k]]


def nearest(text, k=5, timeout=180):
    """search() from any python: runs his EmbeddingGemma venv for the query. [] if it is not installed or fails."""
    if not os.path.exists(VENV_PY):
        return []
    try:
        r = subprocess.run([VENV_PY, os.path.abspath(__file__), "search", str(text), "--k", str(k)],
                           capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else []
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return []


def status():
    rows = [r for r in load() if r.get("model") == MODEL]
    by = {}
    for r in rows:
        by[r.get("kind")] = by.get(r.get("kind"), 0) + 1
    on_disk = works()
    return {"indexed": by, "works_on_disk": len(on_disk), "store": STORE, "venv": os.path.exists(VENV_PY)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "index":
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 40
        for line in index(lim):
            log(line)
    elif cmd == "search":
        k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 5
        print(json.dumps(search(sys.argv[2], k)))
    else:
        print(json.dumps(status(), indent=2))
