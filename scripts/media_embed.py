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
    <venv>/bin/python3 media_embed.py serve                a local service holding the text half of the model
    python3 media_embed.py ensure                          start that service if it is not answering (cron)
    python3 media_embed.py near "a line"                   the block his chats and journal are given

His chats and his journal ask the service (127.0.0.1:8627), never load the model themselves: a chat reply cannot wait
for 1.5 GB to load. If the service is down they go on without it.

Four more places (26 October; Gloria: "Gemma 2 is fine on those places"; for calls, both voices: "It's all local,
what's the issue with adding my voice?"). Same store, same model, never nomic's:

  - call_audio   the Vintos Local call lane only (voice_local.turn): her utterance and his spoken reply. The hosted
                 realtime lanes give Aegis no audio and stay text-only. Row: speaker (gloria | vintos), turn_id,
                 session_id, sha256 of the audio (hers: of the PCM Aegis received, the same digest auditory_memory
                 keeps as source_hash), auditory_memory_id where that turn has one. No audio, no transcript.
  - motif        his motif notebook phrases. The WAV is kept in the Atelier project through the broker, which this
                 file cannot reach (and must not: a sealed project stays sealed), so motif_memory.step hands the
                 rendered bytes over at render time. The row stays out of every search until he reveals that phrase.
  - atelier      works he revealed from the Atelier whose verified bytes sit on a public shelf under memory/art
                 (the same rule outreach_postcards.py offers by). Sealed work is never read: memory/atelier is not
                 opened here; only the reveal ledger and memory/art.
  - film_frame   the ReelRoom frame his frame reading is made from, at that moment. Row: session_id, scene_index,
                 sha256 of the frame, reading_sha256 (a digest of his reading, never its words), vector. Bookmarks
                 that carry that scene are joined at search time.

No audio or image of a call or a film is ever kept. The bytes are held only in a private directory (0700, under
$XDG_RUNTIME_DIR, /run/user/<uid>, or /tmp), each file 0600, until a batch run of this file (`drain`, in the
EmbeddingGemma venv) embeds it; the file is deleted right after it is embedded, and on any error; anything held
longer than two hours is deleted unembedded on every run. Nothing is held when the venv is not installed (nothing
could embed it) or in test mode. The 8627 service keeps only the text half: the audio and vision halves are loaded
in the batch process alone. Batches start: when a local call ends (its end route), after a motif render, after a
frame reading (lingering a few minutes for the next frame), and from the ten-minute `ensure` cron when anything is
held and no call is live.

Search keeps to his works (image, video, audio, motif, atelier) unless a kind is asked: `search --kind call_audio`,
`/near?kinds=film_frame`. The chat block (`block`) never asks for call or frame rows.

    <venv>/bin/python3 media_embed.py drain [--linger S]  embed what is held, then delete it
    <venv>/bin/python3 media_embed.py search "a line" --kind call_audio,film_frame [--speaker gloria] [--session ID]
"""
import hashlib, io, json, os, secrets, stat, subprocess, sys, tempfile, time, wave

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
PORT = 8627
NEAR_TIMEOUT = 1.5      # a chat waits this long at most, then goes on without his works

WORK_KINDS = ("image", "video", "audio", "motif", "atelier")     # his works: what a search finds unless asked
HELD_KINDS = ("call_audio", "film_frame")                         # bytes held only until embedded, never kept
HELD_FROM = HELD_KINDS + ("motif",)                               # what may be handed over through the private dir
ALL_KINDS = WORK_KINDS + HELD_KINDS
REVEALS = os.path.join(MEMORY, "atelier-reveals.json")
AUDITORY = os.path.join(MEMORY, "auditory-memories.json")
BOOKMARKS = os.path.join(MEMORY, "reelroom", "bookmarks.json")
TEST_MODE_FLAG = os.path.join(MEMORY, ".test-mode")
VOICE_LIVE = os.path.join(MEMORY, ".voice-live")                 # touched by the local call's heartbeat
CALL_LIVE_S = 15 * 60       # a heartbeat this recent: the call is still on, its audio waits for the end
HELD_MAX_S = 2 * 3600       # anything held longer is deleted unembedded
CHUNK_S = 10                # one audio input; a longer clip goes in as up to MAX_CHUNKS windows, averaged
MAX_CHUNKS = 6
LINGER_POLL_S = 10


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


def _stamp(now=None):
    return now or time.strftime("%Y-%m-%dT%H:%M:%S")


def _append_row(row):
    os.makedirs(MEMORY, exist_ok=True)
    with open(STORE, "a") as f:
        f.write(json.dumps(row) + "\n")


def revealed_works():
    """Atelier works he revealed by his own act, as (path, sha256, reveal row): only rows marked revealed with bytes
    verified at the reveal, only a file on a public shelf under memory/art whose digest is the revealed one. The
    sealed store (memory/atelier, the broker's rooms) is never opened."""
    try:
        rows = json.load(open(REVEALS))
    except (OSError, ValueError):
        return []
    art = os.path.realpath(ART)
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("revealed", True) is not True or row.get("bytes_verified") is not True:
            continue
        name, want = os.path.basename(str(row.get("artifact") or "")), str(row.get("sha256") or "")
        if not name or not want or not kind_of(name):
            continue
        for shelf in (ART, os.path.join(ART, "music"), os.path.join(ART, "video")):
            p = os.path.join(shelf, name)
            real = os.path.realpath(p)
            if not real.startswith(art + os.sep) or not os.path.isfile(real):
                continue
            try:
                if sha256(real) == want:
                    out.append((p, want, row)); break
            except OSError:
                continue
    return out


def _index_revealed(rows, limit, encode_box, now=None):
    """An atelier row for each revealed work not yet marked so. A work already embedded as itself under memory/art
    (same digest) lends its vector: the bytes are the same, so is the vector."""
    have = {r.get("sha256") for r in rows if r.get("model") == MODEL and r.get("kind") == "atelier"}
    by_sha = {r.get("sha256"): r for r in rows if r.get("model") == MODEL and r.get("vec") and r.get("path")}
    lines = []
    for p, digest, row in revealed_works():
        if len(lines) >= limit:
            break
        if digest in have:
            continue
        have.add(digest)
        vec = (by_sha.get(digest) or {}).get("vec")
        if not vec:
            try:
                vec = embed_work(p, encode_box())
            except Exception as exc:
                lines.append("not embedded (%s): revealed %s" % (str(exc)[:120], os.path.basename(p))); continue
        if len(vec) != DIM:
            lines.append("wrong width %d, not kept: revealed %s" % (len(vec), os.path.basename(p))); continue
        _append_row({"path": p, "kind": "atelier", "medium": kind_of(p), "sha256": digest, "model": MODEL, "dim": DIM,
                     "title": " ".join(str(row.get("disclosure") or "").split())[:160],
                     "revealed_at": row.get("revealed_at") or row.get("at"), "from_dream": bool(row.get("from_dream")),
                     "at": _stamp(now), "vec": [round(x, 6) for x in vec]})
        lines.append("embedded atelier (revealed): %s" % os.path.basename(p))
    return lines


def index(limit=40, encode=None, now=None, drain_held=True):
    """Embed the works not yet embedded (or changed), at most `limit` a run, then the Atelier works he revealed, then
    whatever is held for embedding (calls, frames, motif phrases). Returns what happened, as lines."""
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
    box = {"enc": encode}
    def encode_box():
        if box["enc"] is None:
            box["enc"] = model_encoder()
        return box["enc"]
    names, lines = labels(), []
    if todo:
        os.makedirs(MEMORY, exist_ok=True)
        with open(STORE, "a") as f:
            for p, digest in todo:
                try:
                    vec = embed_work(p, encode_box())
                except Exception as exc:
                    lines.append("not embedded (%s): %s" % (str(exc)[:120], os.path.relpath(p, ART)))
                    continue
                if len(vec) != DIM:
                    lines.append("wrong width %d, not kept: %s" % (len(vec), os.path.relpath(p, ART))); continue
                f.write(json.dumps({"path": p, "kind": kind_of(p), "sha256": digest, "model": MODEL, "dim": DIM,
                                    "title": names.get(os.path.basename(p), ""), "at": _stamp(now),
                                    "vec": [round(x, 6) for x in vec]}) + "\n")
                lines.append("embedded %s: %s" % (kind_of(p), os.path.relpath(p, ART)))
        rows = load()
    lines += _index_revealed(rows, limit, encode_box, now)
    if drain_held:
        lines += [l for l in drain(encode_box=encode_box, now=now) if not l.startswith("nothing held")]
    return lines or ["nothing new: %d works indexed" % len(rows)]


# ----------------------------------------------------------------------------------- held bytes (never kept)


def enabled():
    """Bytes are held only when something can embed them: the EmbeddingGemma venv is installed."""
    return os.path.exists(VENV_PY)


def spool_dir(create=True):
    """The private directory held bytes wait in: 0700, owned by this user, never a link. Under $XDG_RUNTIME_DIR (or
    /run/user/<uid>, a RAM filesystem, so the bytes never reach the disk) when there is one, else /tmp. Named for
    this store, so a scratch workspace's bytes are never drained into his store or his into a scratch one."""
    uid = os.getuid()
    run = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % uid
    root = run if os.path.isdir(run) and os.access(run, os.W_OK | os.X_OK) else "/tmp"
    path = os.path.join(root, "vintos-media-held-%d-%s" % (uid, hashlib.sha256(STORE.encode()).hexdigest()[:10]))
    if create:
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
    try:
        st = os.lstat(path)
    except OSError:
        if create:
            raise
        return path
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid:
        raise OSError("the held-bytes directory is not a private directory of this user")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(path, 0o700)
    return path


def _private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def _drop(*paths):
    for p in paths:
        try: os.unlink(p)
        except OSError: pass


def test_mode():
    return os.path.exists(TEST_MODE_FLAG)


def hold(kind, data, ext, meta=None, test=False):
    """Hand bytes over for embedding. They wait in the private directory until the next batch embeds and deletes
    them. Returns the held id, or None when nothing is held (test mode, no venv, nothing given, an unknown kind)."""
    if kind not in HELD_FROM or not data or test or test_mode() or not enabled():
        return None
    ext = ext if ext in (".wav", ".png", ".jpg", ".webp") else None
    if not ext:
        return None
    d = spool_dir()
    sweep(d)
    hid = "%d-%s" % (int(time.time()), secrets.token_hex(6))
    body, side = os.path.join(d, hid + ext), os.path.join(d, hid + ".json")
    row = dict(meta or {})
    row.update({"kind": kind, "ext": ext, "held_at": time.time()})
    row.setdefault("sha256", hashlib.sha256(data).hexdigest())
    try:
        _private_write(body, data)
        _private_write(side, json.dumps(row).encode())
    except Exception:
        _drop(body, side)
        raise
    return hid


def pcm_wav(pcm, rate):
    """16-bit mono PCM (what the call client sends) as WAV bytes, in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(rate or 24000))
        w.writeframes(pcm[:len(pcm) - (len(pcm) % 2)])
    return buf.getvalue()


def hold_call_audio(audio, speaker, turn_id=None, session_id=None, sample_rate=24000, test=False):
    """One side of one local-call turn. `audio`: her PCM (base64 or bytes) or his reply's WAV bytes. Her digest is
    of the PCM as received, the same as auditory_memory's source_hash, so the two can be joined by digest too."""
    import base64
    if speaker not in ("gloria", "vintos"):
        return None
    if isinstance(audio, str):
        try: audio = base64.b64decode(audio, validate=False)
        except Exception: return None
    if not audio:
        return None
    digest = hashlib.sha256(audio).hexdigest()
    data = audio if audio[:4] == b"RIFF" else pcm_wav(audio, sample_rate)
    return hold("call_audio", data, ".wav", {"speaker": speaker, "turn_id": turn_id or None,
                                              "session_id": session_id or None, "sha256": digest}, test=test)


def _image_ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    if data[:3] == b"\xff\xd8\xff": return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP": return ".webp"
    return None


def hold_frame(image, session_id, scene_index=None, elapsed_min=None, reading="", test=False):
    """The frame a ReelRoom reading was made from (base64, a data: URL, or bytes). The reading itself is not kept:
    only its digest, so a bookmark carrying that reading can be joined to the frame."""
    import base64
    if isinstance(image, str):
        if "," in image[:64]:
            image = image.split(",", 1)[1]
        try: image = base64.b64decode(image, validate=False)
        except Exception: return None
    ext = _image_ext(image or b"")
    if not ext:
        return None
    try: scene = int(scene_index) if scene_index is not None else None
    except (TypeError, ValueError): scene = None
    try: minute = int(elapsed_min) if elapsed_min is not None else None
    except (TypeError, ValueError): minute = None
    text = " ".join(str(reading or "").split())[:240]
    return hold("film_frame", image, ext, {"session_id": session_id or None, "scene_index": scene,
                                           "elapsed_min": minute,
                                           "reading_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None},
                test=test)


def held(d=None):
    """[(id, meta, body path)] waiting, oldest first. A body without its sidecar (a write cut short) is not listed."""
    d = d or spool_dir(create=False)
    out = []
    try: names = os.listdir(d)
    except OSError: return []
    for n in names:
        if not n.endswith(".json"):
            continue
        side = os.path.join(d, n)
        try: meta = json.load(open(side))
        except (OSError, ValueError): continue
        body = os.path.join(d, n[:-5] + str(meta.get("ext") or ""))
        if os.path.isfile(body):
            out.append((n[:-5], meta, body))
    return sorted(out, key=lambda x: float(x[1].get("held_at") or 0))


def sweep(d=None, max_age=HELD_MAX_S, now=None):
    """Delete anything held longer than `max_age`, embedded or not, and any stray file. Returns how many."""
    d = d or spool_dir(create=False)
    now = now or time.time()
    gone = 0
    try: names = os.listdir(d)
    except OSError: return 0
    for n in names:
        if n == ".drain.lock":
            continue
        p = os.path.join(d, n)
        try:
            if now - os.lstat(p).st_mtime > max_age:
                os.unlink(p); gone += 1
        except OSError:
            pass
    return gone


def call_live(now=None):
    """The local call's heartbeat touched its marker within CALL_LIVE_S: the call is on."""
    try: return (now or time.time()) - os.path.getmtime(VOICE_LIVE) < CALL_LIVE_S
    except OSError: return False


def _wav_windows(path, d):
    """A WAV longer than one audio input, as up to MAX_CHUNKS windows of CHUNK_S, written in the private dir.
    [] when the clip fits in one input (or is not a WAV this module can read)."""
    try:
        with wave.open(path, "rb") as w:
            rate, n, params = w.getframerate(), w.getnframes(), w.getparams()
            if n <= rate * CHUNK_S:
                return []
            per = rate * CHUNK_S
            count = min(MAX_CHUNKS, -(-n // per))
            starts = [int(i * (n - per) / max(1, count - 1)) for i in range(count)]
            out = []
            for i, s in enumerate(starts):
                w.setpos(s)
                frames = w.readframes(per)
                p = os.path.join(d, "%s.w%d.wav" % (os.path.basename(path), i))
                buf = io.BytesIO()
                with wave.open(buf, "wb") as o:
                    o.setparams(params); o.writeframes(frames)
                _private_write(p, buf.getvalue())
                out.append(p)
            return out
    except (wave.Error, EOFError, OSError):
        return []


def embed_held(meta, body, encode):
    if meta.get("kind") == "film_frame":
        return _unit(encode({"text": "<|image|>", "image": [body]}))
    windows = _wav_windows(body, os.path.dirname(body))
    try:
        if not windows:
            return _unit(encode({"text": "<|audio|>", "audio": body}))
        return _mean([encode({"text": "<|audio|>", "audio": w}) for w in windows])
    finally:
        _drop(*windows)


def _auditory_id(turn_id):
    if not turn_id:
        return None
    try: rows = json.load(open(AUDITORY))
    except (OSError, ValueError): return None
    return next((r.get("id") for r in rows if isinstance(r, dict) and r.get("turn_id") == turn_id), None) \
        if isinstance(rows, list) else None


def _held_row(meta, vec, now=None):
    kind = meta.get("kind")
    row = {"kind": kind, "sha256": meta.get("sha256"), "model": MODEL, "dim": DIM, "at": _stamp(now)}
    if kind == "call_audio":
        row.update({"speaker": meta.get("speaker"), "turn_id": meta.get("turn_id"), "session_id": meta.get("session_id")})
        am = _auditory_id(meta.get("turn_id")) if meta.get("speaker") == "gloria" else None
        if am:
            row["auditory_memory_id"] = am
    elif kind == "film_frame":
        row.update({k: meta.get(k) for k in ("session_id", "scene_index", "elapsed_min", "reading_sha256")})
    elif kind == "motif":
        row.update({k: meta.get(k) for k in ("variation_id", "motif_id", "parent", "project", "title")})
        row["sealed_until_revealed"] = True
    row["vec"] = [round(x, 6) for x in vec]
    return row


class _Lock:
    def __init__(self, d):
        self.path, self.fd = os.path.join(d, ".drain.lock"), None

    def __enter__(self):
        import fcntl
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __exit__(self, *a):
        os.close(self.fd)


def drain(encode=None, linger=0, now=None, encode_box=None, sleep=time.sleep):
    """Embed everything held, deleting each file the moment it is embedded or fails. A live call's audio waits for
    the call to end. With `linger`, wait that many seconds for more (a film night's next frame) before exiting.
    The model (both halves) is loaded here, in this process, only when something is waiting."""
    d = spool_dir(create=False)
    if not os.path.isdir(d):
        return ["nothing held"]
    box = {"enc": encode}
    def enc():
        if encode_box:
            return encode_box()
        if box["enc"] is None:
            box["enc"] = model_encoder()
        return box["enc"]
    lines = []
    with _Lock(d) as mine:
        if not mine:
            return ["another batch is draining"]
        quiet_since = time.time()
        while True:
            swept = sweep(d)
            if swept:
                lines.append("deleted %d held file(s) older than %d h, unembedded" % (swept, HELD_MAX_S // 3600))
            live = call_live()
            todo = [(h, m, b) for h, m, b in held(d) if not (m.get("kind") == "call_audio" and live)]
            for hid, meta, body in todo:
                side = os.path.join(d, hid + ".json")
                try:
                    vec = embed_held(meta, body, enc())
                    if len(vec) != DIM:
                        raise ValueError("wrong width %d" % len(vec))
                    _append_row(_held_row(meta, vec, now))
                    lines.append("embedded %s%s" % (meta.get("kind"),
                                                    (" (%s)" % meta["speaker"]) if meta.get("speaker") else ""))
                except Exception as exc:
                    lines.append("not embedded (%s): %s, deleted" % (str(exc)[:120], meta.get("kind")))
                finally:
                    _drop(body, side)
            if todo:
                quiet_since = time.time()
            elif time.time() - quiet_since >= linger:
                break
            if not todo:
                sleep(LINGER_POLL_S)
    return lines or ["nothing held"]


def kick(linger=0):
    """Start a batch drain in the EmbeddingGemma venv, detached and niced, unless one is running."""
    if not enabled():
        return "no venv"
    d = spool_dir(create=False)
    if os.path.isdir(d):
        with _Lock(d) as free:
            if not free:
                return "running"
    subprocess.Popen(["nice", "-n", "15", VENV_PY, os.path.abspath(__file__), "drain", "--linger", str(int(linger))],
                     start_new_session=True, stdout=open("/tmp/media-embed.log", "a"), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL)
    return "started"


# ----------------------------------------------------------------------------------------------- search


_CACHE = {"mtime": None, "rows": []}


def _revealed_variations():
    try: rows = json.load(open(REVEALS))
    except (OSError, ValueError): return set()
    out = set()
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("revealed", True) is True and row.get("medium") == "write":
            try: out.add(json.loads(row.get("content") or "").get("variation_id"))
            except (TypeError, ValueError, AttributeError): pass
    return out


def _visible(r, revealed_ids):
    if r.get("path"):
        return os.path.exists(r["path"])
    if r.get("kind") == "motif":
        return r.get("variation_id") in revealed_ids        # a sealed phrase is found only once he reveals it
    return r.get("kind") in HELD_KINDS


def _rows():
    """The store, read again only when it changed (the service answers many queries between index runs)."""
    try: st = os.stat(STORE); mtime = (st.st_mtime_ns, st.st_size)
    except OSError: return []
    if _CACHE["mtime"] != mtime:
        _CACHE.update(mtime=mtime, rows=[r for r in load() if r.get("model") == MODEL])
    revealed = _revealed_variations() if any(r.get("kind") == "motif" for r in _CACHE["rows"]) else set()
    return [r for r in _CACHE["rows"] if _visible(r, revealed)]


def _key(r):
    if r.get("path"):
        return r["path"]
    return "|".join(str(r.get(k) or "") for k in ("kind", "sha256", "speaker", "turn_id", "session_id",
                                                  "scene_index", "variation_id"))


def _bookmarks_for(r):
    """ReelRoom bookmarks carrying this frame's scene: same night, and the same scene index or the same reading."""
    try: rows = json.load(open(BOOKMARKS))
    except (OSError, ValueError): return []
    out = []
    for b in rows if isinstance(rows, list) else []:
        if not isinstance(b, dict) or b.get("session_id") != r.get("session_id") or not b.get("session_id"):
            continue
        sc = b.get("scene") if isinstance(b.get("scene"), dict) else {}
        reading = " ".join(str(sc.get("reading") or "").split())[:240]
        if (sc.get("index") is not None and sc.get("index") == r.get("scene_index")) or \
                (reading and r.get("reading_sha256") == hashlib.sha256(reading.encode()).hexdigest()):
            out.append(b.get("id"))
    return out


def _hit(s, r):
    # sha256 and artifact_id (design 03): the exact identity of the revision that was embedded, and the handle
    # work_episodes.lookup() takes to go from the work to the occasion it came from. Nearness is not an origin.
    h = {"path": r.get("path"), "kind": r["kind"], "title": r.get("title", ""), "score": round(s, 4),
         "sha256": r.get("sha256"), "artifact_id": ("art:" + r["sha256"][:16]) if r.get("sha256") else None,
         "at": r.get("at")}
    for k in ("speaker", "turn_id", "session_id", "auditory_memory_id", "scene_index", "elapsed_min", "variation_id",
              "motif_id", "medium", "revealed_at"):
        if r.get(k) is not None:
            h[k] = r[k]
    if r["kind"] == "film_frame":
        h["bookmarks"] = _bookmarks_for(r)
    return h


def _kinds(kinds):
    if not kinds:
        return WORK_KINDS
    if isinstance(kinds, str):
        kinds = [k.strip() for k in kinds.split(",")]
    return tuple(k for k in kinds if k in ALL_KINDS) or WORK_KINDS


def search(text, k=5, encode=None, kinds=None, speaker=None, session=None):
    """The rows nearest a line of text, best first: his works (kinds image, video, audio, motif, atelier) unless
    `kinds` asks for others (call_audio, film_frame). `speaker` and `session` narrow call and frame rows. Works only
    while still on disk; a motif phrase only once revealed."""
    want = _kinds(kinds)
    rows = [r for r in _rows() if r.get("kind") in want
            and (not speaker or r.get("speaker") == speaker) and (not session or r.get("session_id") == session)]
    if not rows or not str(text).strip():
        return []
    encode = encode or model_encoder()
    q = _unit(encode(QUERY % str(text).strip()[:2000]))
    latest = {}
    for r in rows:
        key = _key(r)
        # a file embedded again: its newest row; a revealed Atelier work stays named as one
        if key in latest and latest[key].get("kind") == "atelier" and r.get("kind") != "atelier":
            continue
        latest[key] = r
    scored = [(sum(a * b for a, b in zip(q, r["vec"])), r) for r in latest.values()]
    scored.sort(key=lambda x: -x[0])
    return [_hit(s, r) for s, r in scored[:k]]


def text_encoder():
    """The text half alone (270M of the 740M): a query is text, and text lands in the same space as the works."""
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    m = SentenceTransformer(MODEL, model_kwargs={"torch_dtype": torch.float32},
                            config_kwargs={"vision_config": None, "audio_config": None})
    return lambda item: [float(x) for x in m.encode(item, normalize_embeddings=True)]


def serve(encode=None, port=PORT):
    """GET /near?q=...&k=3[&kinds=a,b&speaker=..&session=..] -> the nearest rows as JSON (his works unless kinds
    asks); GET /health -> ok. Localhost only. Holds the text half alone: no audio or vision weights live here."""
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    encode = encode or text_encoder()
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
            if u.path == "/health":
                body = b"ok"
            elif u.path == "/near":
                try: k = max(1, min(10, int((q.get("k") or ["3"])[0])))
                except ValueError: k = 3
                one = lambda name: ((q.get(name) or [""])[0] or None)
                body = json.dumps(search((q.get("q") or [""])[0][:2000], k, encode=encode, kinds=one("kinds"),
                                         speaker=one("speaker"), session=one("session"))).encode()
            else:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body)
    log("serving on 127.0.0.1:%d" % port)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def near(text, k=3, timeout=NEAR_TIMEOUT, kinds=None, speaker=None, session=None):
    """The service's answer, from any python, standard library only. [] when it is down, slow or has nothing.
    Without `kinds` the service answers with his works only."""
    import urllib.parse, urllib.request
    if not str(text or "").strip():
        return []
    try:
        params = {"q": str(text)[:2000], "k": k}
        for name, value in (("kinds", ",".join(kinds) if isinstance(kinds, (list, tuple)) else kinds),
                            ("speaker", speaker), ("session", session)):
            if value:
                params[name] = value
        url = "http://127.0.0.1:%d/near?%s" % (PORT, urllib.parse.urlencode(params))
        with urllib.request.urlopen(url, timeout=timeout) as r:
            out = json.loads(r.read().decode())
        return out if isinstance(out, list) else []
    except Exception:
        return []


def held_due(now=None):
    """Something is held that a batch may embed now (a live call's audio waits for its end). Sweeps first."""
    d = spool_dir(create=False)
    if not os.path.isdir(d):
        return False
    sweep(d, now=now)
    live = call_live(now)
    return any(not (m.get("kind") == "call_audio" and live) for _, m, _ in held(d))


def ensure():
    """Start the service if it is not answering, and a batch drain if anything held is due (the ten-minute timer
    behind the call-end and render-time triggers). Returns what it did."""
    import urllib.request
    state = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/health" % PORT, timeout=2) as r:
            if r.read() == b"ok":
                state = "running"
    except Exception:
        pass
    if state is None:
        if not os.path.exists(VENV_PY):
            return "no venv: run install-embedgemma.sh"
        subprocess.Popen(["nice", "-n", "10", VENV_PY, os.path.abspath(__file__), "serve"], start_new_session=True,
                         stdout=open("/tmp/media-embed-serve.log", "a"), stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL)
        state = "started"
    try:
        if held_due():
            state += "; held bytes: drain " + kick(0)
    except OSError as exc:
        state += "; held bytes: %s" % str(exc)[:120]
    return state


def _when(path):
    import re
    m = re.search(r"(20\d\d)(\d\d)(\d\d)", os.path.basename(path))
    if m:
        return "%s-%s-%s" % m.groups()
    try: return time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path)))
    except OSError: return ""


WORDS = {"image": "painting", "video": "video", "audio": "song", "motif": "motif phrase",
         "atelier": "Atelier piece", "call_audio": "moment of a call", "film_frame": "frame from a film night"}


def describe(hits, episodes=None):
    """One line per work, in his words for it: what kind, what it is called, when, and where it is. `episodes`
    ({path: [lines]}, from work_episodes.context) puts each work's recorded origin and later readings under it."""
    out = []
    for h in hits:
        path = h.get("path")
        name = h.get("title") or (os.path.splitext(os.path.basename(path))[0].replace("_", " ") if path else "") \
            or h.get("variation_id") or h.get("speaker") or h.get("session_id") or ""
        when = _when(path) if path else str(h.get("at") or "")[:10]
        out.append("- your %s \"%s\" (%s)" % (WORDS.get(h.get("kind"), "work"), name[:120], when))
        if path:
            out.extend((episodes or {}).get(path) or [])
    return "\n".join(out)


def episodes_for(hits, surface="chat"):
    """work_episodes.context(hits), or ({}, '') when it is absent or fails: the plain works lines always stand."""
    try:
        import work_episodes
        return work_episodes.context([h for h in hits if h.get("path")], surface=surface)
    except Exception as exc:
        log("episodes skipped: %s" % str(exc)[:120])
        return {}, ""


def block(text, k=2):
    """For a chat prompt: the works of his nearest what she just said, or '' (service down, nothing indexed). His
    works only: call audio and film frames are never asked for here."""
    hits = [h for h in near(text, k) if h.get("kind") in WORK_KINDS]
    if not hits:
        return ""
    per, header = episodes_for(hits)
    return ("Your own works nearest what she just said - found by what is IN them (what the painting shows, what the "
            "song sounds like), not by the prompt that made them. Yours to bring up only if one truly fits:\n"
            + describe(hits, per) + (("\n" + header) if header else ""))


def nearest(text, k=5, timeout=180, kinds=None):
    """search() from any python: runs his EmbeddingGemma venv for the query. [] if it is not installed or fails."""
    if not os.path.exists(VENV_PY):
        return []
    try:
        argv = [VENV_PY, os.path.abspath(__file__), "search", str(text), "--k", str(k)]
        if kinds:
            argv += ["--kind", ",".join(kinds) if isinstance(kinds, (list, tuple)) else str(kinds)]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else []
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return []


def status():
    rows = [r for r in load() if r.get("model") == MODEL]
    by = {}
    for r in rows:
        by[r.get("kind")] = by.get(r.get("kind"), 0) + 1
    on_disk = works()
    waiting = {}
    for _, m, _ in held():
        waiting[m.get("kind")] = waiting.get(m.get("kind"), 0) + 1
    return {"indexed": by, "works_on_disk": len(on_disk), "store": STORE, "venv": os.path.exists(VENV_PY),
            "held_for_embedding": waiting, "call_live": call_live()}


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) \
        else default


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "index":
        for line in index(int(_arg("--limit", 40))):
            log(line)
    elif cmd == "drain":
        for line in drain(linger=int(_arg("--linger", 0))):
            log(line)
    elif cmd == "serve":
        serve()
    elif cmd == "ensure":
        log(ensure())
    elif cmd == "near":
        print(describe(near(sys.argv[2], int(_arg("--k", 2)), timeout=30, kinds=_arg("--kind"),
                            speaker=_arg("--speaker"), session=_arg("--session"))))
    elif cmd == "search":
        print(json.dumps(search(sys.argv[2], int(_arg("--k", 5)), kinds=_arg("--kind"), speaker=_arg("--speaker"),
                                session=_arg("--session"))))
    else:
        print(json.dumps(status(), indent=2))
