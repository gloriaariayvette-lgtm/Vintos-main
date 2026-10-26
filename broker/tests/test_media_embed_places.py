#!/usr/bin/env python3
"""EmbeddingGemma 2 in four more places (26 October): local-call audio (both voices), his motif phrases, revealed
Atelier works, ReelRoom frames. No audio or image survives: bytes wait in a private 0700 directory, are deleted the
moment a batch embeds them (or fails to), and anything older than two hours is swept. Test mode holds nothing.
Search keeps to his works unless a kind is asked; the chat block never asks. Sealed work is never embedded.

Offline: scratch HOME, workspace and runtime dir; the model is a stub (the real one is never loaded); the batch
process is never started (Popen is a recorder); sockets refused except the suite's own localhost service; all test
audio and images are synthesized here."""
import base64, hashlib, importlib.util, io, json, math, os, socket, stat, struct, sys, tempfile, time, wave, zlib

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="media-places-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
RUN = os.path.join(HOME, "run"); os.makedirs(RUN, mode=0o700); os.environ["XDG_RUNTIME_DIR"] = RUN
FAKE_VENV = os.path.join(HOME, "venv-python3"); open(FAKE_VENV, "w").close()
os.environ["VINTOS_EMBEDGEMMA_PY"] = FAKE_VENV
MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
NET = []
_ORIG_CONNECT = socket.socket.connect
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

import media_embed as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

KICKS = []
class _Popen:
    def __init__(self, argv, **kw): KICKS.append(argv)
M.subprocess.Popen = _Popen
LOADS = []
def _no_model(): LOADS.append(1); raise RuntimeError("the real model is never loaded in this suite")
M.model_encoder = _no_model; M.text_encoder = _no_model

SEEN = []
def encode(item):
    """Stub model: a query lands on axis 0; a file on axis 0 plus an axis from its bytes, so every row is near."""
    SEEN.append(item)
    v = [0.0] * M.DIM; v[0] = 1.0
    if not isinstance(item, str):
        p = next(x if isinstance(x, str) else x[0] for k, x in item.items() if k != "text")
        st = os.stat(p)
        SEEN_MODES.append((p, stat.S_IMODE(st.st_mode), stat.S_IMODE(os.stat(os.path.dirname(p)).st_mode)))
        v[1 + int(hashlib.sha256(open(p, "rb").read()).hexdigest(), 16) % (M.DIM - 1)] = 0.5
    return v
SEEN_MODES = []

def tone(seconds, rate=24000, freq=220.0):
    n = int(seconds * rate)
    return struct.pack("<%dh" % n, *[int(6000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)])

def wav(pcm, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()

def png(rgb=(200, 40, 40)):
    raw = b"".join(b"\x00" + bytes(rgb) * 4 for _ in range(4))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

def media_files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        out += [os.path.join(dp, f) for f in fn if f.lower().endswith((".wav", ".png", ".jpg", ".webp"))]
    return out

# ------------------------------------------------------------------ isolation
check("the store is scratch and is not nomic's", M.STORE.startswith(HOME) and M.STORE.endswith("media-embeddings.jsonl"))
d = M.spool_dir()
check("bytes wait under the scratch runtime dir, in a 0700 directory of this user",
      d.startswith(RUN + os.sep) and stat.S_IMODE(os.stat(d).st_mode) == 0o700 and os.stat(d).st_uid == os.getuid(), d)
check("the batch process is a recorder here, and the real model is never loaded",
      M.subprocess.Popen is _Popen and not LOADS)

# ------------------------------------------------------------------ 1. live calls, through the Vintos Local lane
AM = load("auditory_memory", os.path.join(REPO, "scripts", "auditory_memory.py"))
VL = load("voice_local", os.path.join(REPO, "scripts", "voice_local.py"))
import stratagem as _sg_client, turn_coordinator as _sg_coordinator
_sg_client._post = lambda *a, **k: {}
_sg_coordinator._post = lambda *a, **k: {"ok": True}
REPLY_WAV = wav(tone(0.4, freq=330))
def post(url, body, timeout):
    if url.endswith("/listen"):
        return json.dumps({"ok": True, "transcript": "the lanterns by the river", "audio_reading": "quiet, unhurried",
                           "ears": "stub", "audio_native_gemma": True}).encode(), {}
    if url.endswith("/chat/completions"):
        return json.dumps({"choices": [{"message": {"content": "I remember them."}}]}).encode(), {}
    if url.endswith("/voice/models"):
        return b'{"ok": true}', {}
    return REPLY_WAV, {"X-Vintos-Voice": "stub"}
VL._post = post
her = tone(0.5)
VL.models(True)
call = VL.call_id()
t0 = time.time()
res = VL.turn(base64.b64encode(her).decode(), 24000, "SOUL", "")
took = time.time() - t0
check("the voice turn still answers", res.get("ok") and res.get("reply") == "I remember them.", res)
H = M.held()
check("both voices of the turn are held, and nothing is embedded during the turn",
      sorted(m["speaker"] for _, m, _ in H) == ["gloria", "vintos"] and not SEEN and not LOADS and not M.load(), H)
turn_id = next(m["turn_id"] for _, m, _ in H)
check("held with the turn id and the call's id",
      all(m["turn_id"] == turn_id and m["session_id"] == call and call.startswith("lc-") for _, m, _ in H), H)
check("each held file is 0600 in the 0700 directory",
      all(stat.S_IMODE(os.stat(b).st_mode) == 0o600 and os.path.dirname(b) == d for _, _, b in H))
check("her digest is of the PCM received, the same as auditory memory's source_hash",
      next(m for _, m, _ in H if m["speaker"] == "gloria")["sha256"] == hashlib.sha256(her).hexdigest()
      and any(r["source_hash"] == "sha256:" + hashlib.sha256(her).hexdigest() for r in AM.memories()))

open(M.VOICE_LIVE, "w").close()
out = M.drain(encode=encode, sleep=lambda s: None)
check("while the call is live its audio waits for the end", len(M.held()) == 2 and not M.load(), out)
check("ensure's timer sees nothing due during a live call", M.held_due() is False)
os.unlink(M.VOICE_LIVE)
check("after the call, the held audio is due", M.held_due() is True)
KICKS.clear()
VL.end_call()
check("the call's end starts one batch drain in the venv, niced, and closes the call's id",
      len(KICKS) == 1 and KICKS[0][:3] == ["nice", "-n", "15"] and KICKS[0][3] == FAKE_VENV and "drain" in KICKS[0]
      and VL._CALL["id"] is None, KICKS)
out = M.drain(encode=encode, sleep=lambda s: None)
rows = [r for r in M.load() if r["kind"] == "call_audio"]
check("the batch embeds both voices", sorted(r["speaker"] for r in rows) == ["gloria", "vintos"], out)
check("files were embedded from the private directory, 0600 in 0700",
      SEEN_MODES and all(p.startswith(d) and fm == 0o600 and dm == 0o700 for p, fm, dm in SEEN_MODES), SEEN_MODES)
check("a call row carries no audio, no transcript, no path",
      all(not ({"audio", "transcript", "path", "reading", "text"} & set(r)) for r in rows) and
      all(set(r) <= {"kind", "speaker", "turn_id", "session_id", "sha256", "model", "dim", "at", "vec",
                     "auditory_memory_id"} for r in rows), rows[0].keys() if rows else rows)
am_id = next((m["id"] for m in AM.memories() if m["turn_id"] == turn_id), None)
check("her row links to the auditory memory of that turn", am_id and
      next(r for r in rows if r["speaker"] == "gloria").get("auditory_memory_id") == am_id, am_id)
check("no audio file survives anywhere", not M.held() and not media_files(HOME) and
      set(os.listdir(d)) <= {".drain.lock"}, media_files(HOME))

# a failure deletes the bytes too
M.hold_call_audio(base64.b64encode(tone(0.2)).decode(), "gloria", "t-x", "lc-x")
def broken(item):
    if isinstance(item, str): return encode(item)
    raise RuntimeError("model fault")
out = M.drain(encode=broken, sleep=lambda s: None)
check("an embedding failure still deletes the held audio, and keeps no row",
      not M.held() and not media_files(HOME) and any("not embedded" in l and "deleted" in l for l in out), out)

# a long reply goes in as windows, and the windows are deleted too
before = len(SEEN)
M.hold_call_audio(wav(tone(25.0, rate=8000), rate=8000), "vintos", "t-long", "lc-y")
M.drain(encode=encode, sleep=lambda s: None)
check("a reply longer than one input goes in as windows of ten seconds, averaged, none left behind",
      len(SEEN) - before == 3 and not media_files(HOME) and set(os.listdir(d)) <= {".drain.lock"}, len(SEEN) - before)

# the sweep
M.hold_call_audio(base64.b64encode(tone(0.2)).decode(), "gloria", "t-old", "lc-z")
for f in os.listdir(d):
    if f != ".drain.lock":
        os.utime(os.path.join(d, f), (time.time() - 3 * 3600, time.time() - 3 * 3600))
n_rows = len(M.load())
out = M.drain(encode=encode, sleep=lambda s: None)
check("anything held over two hours is deleted unembedded on the next run",
      not M.held() and len(M.load()) == n_rows and any("older than 2 h" in l for l in out), out)

# test mode, and no venv
open(M.TEST_MODE_FLAG, "w").close()
check("test mode holds nothing", M.hold_call_audio(her, "gloria", "t-t", "lc-t") is None and not M.held())
VL.turn(base64.b64encode(tone(0.3, freq=440)).decode(), 24000, "SOUL", "")
check("a voice turn in test mode holds nothing", not M.held())
os.unlink(M.TEST_MODE_FLAG)
check("a turn marked test holds nothing", M.hold_call_audio(her, "gloria", "t-t", "lc-t", test=True) is None)
M.VENV_PY = os.path.join(HOME, "nowhere")
check("with no venv installed nothing is held (nothing could embed it)",
      M.hold_call_audio(her, "gloria", "t-n", "lc-n") is None and not M.held() and M.kick() == "no venv")
M.VENV_PY = FAKE_VENV
check("an unknown speaker is not held", M.hold_call_audio(her, "someone", "t-u", "lc-u") is None)
vsrc = open(os.path.join(REPO, "scripts", "voice_local.py")).read()
check("the lane holds her audio and his played reply, and never embeds in the turn",
      '_hold_audio(audio_b64, "gloria"' in vsrc and '_hold_audio(voice_raw, "vintos"' in vsrc
      and "model_encoder" not in vsrc and "drain(" not in vsrc)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
wr = open(os.path.join(REPO, "scripts", "watch_routes.py")).read()
end = srv[srv.index('@app.post("/api/voice/local/end")'):][:900]
check("both local-call end routes start the batch", "_vl.end_call()" in end and "voice_local.end_call()" in wr)
hosted = srv[srv.index('if provider == "openai":'):srv.index('@app.post("/api/voice/local/turn")')]
check("the hosted realtime lanes hold nothing", "hold_call_audio" not in hosted and "media_embed" not in hosted)

# ------------------------------------------------------------------ 4. ReelRoom frames
frame = png()
hid = M.hold_frame("data:image/png;base64," + base64.b64encode(frame).decode(), "rr-1", scene_index=1,
                   elapsed_min=31, reading="a woman at a window, green neon")
check("a frame reading's frame is held", hid and len(M.held()) == 1)
M.drain(encode=encode, sleep=lambda s: None)
fr = [r for r in M.load() if r["kind"] == "film_frame"]
check("the frame is embedded as itself and deleted; no image kept", fr and not media_files(HOME)
      and any(i.get("text") == "<|image|>" for i in SEEN if isinstance(i, dict)), fr)
check("a frame row: session, scene index, digest of the frame, digest of the reading, never the reading",
      fr[0]["session_id"] == "rr-1" and fr[0]["scene_index"] == 1 and fr[0]["sha256"] == hashlib.sha256(frame).hexdigest()
      and fr[0]["reading_sha256"] and "green neon" not in json.dumps(fr[0]))
os.makedirs(os.path.join(MEM, "reelroom"), exist_ok=True)
json.dump([{"id": "bm-1", "session_id": "rr-1", "scene": {"reading": "a woman at a window, green neon",
                                                          "whose": "his reading of a frame"}},
           {"id": "bm-2", "session_id": "rr-1", "scene": {"reading": "something else", "index": 1}},
           {"id": "bm-3", "session_id": "rr-2", "scene": {"reading": "a woman at a window, green neon", "index": 1}}],
          open(M.BOOKMARKS, "w"))
hits = M.search("a window", k=10, encode=encode, kinds="film_frame")
check("a frame hit carries the bookmarks of that night that carry its scene (by index or by reading)",
      hits and sorted(hits[0]["bookmarks"]) == ["bm-1", "bm-2"], hits)
look = srv[srv.index('if mode == "look" and image:'):][:1200]
check("the ReelRoom look route holds the frame at reading time and starts a lingering batch",
      "hold_frame(image" in look and "reading=reply" in look and "kick(420)" in look)
check("bad bytes are not held", M.hold_frame(base64.b64encode(b"not an image").decode(), "rr-1") is None)

# ------------------------------------------------------------------ 2. motif phrases
MMsrc = open(os.path.join(REPO, "scripts", "motif_memory.py")).read()
check("a kept phrase is handed over at render time, after the room keeps it",
      MMsrc.index("\n        _hold_for_index(pid, rec, rendered)\n") > MMsrc.index(".keep(rec, rendered)\n"))
MM = load("motif_memory", os.path.join(REPO, "scripts", "motif_memory.py"))
KICKS.clear()
MM._hold_for_index("p123", {"variation_id": "vaaaaaaaaaaaa", "motif_id": "mbbbbbbbbbbbb", "parent": None},
                   {"wav": wav(tone(2.0, freq=262))})
check("the motif hook holds the WAV and starts a batch", len(M.held()) == 1 and len(KICKS) == 1)
M.drain(encode=encode, sleep=lambda s: None)
mo = [r for r in M.load() if r["kind"] == "motif"]
check("a motif row names the phrase and its project, no audio", mo and mo[0]["variation_id"] == "vaaaaaaaaaaaa"
      and mo[0]["project"] == "p123" and mo[0]["sealed_until_revealed"] and not media_files(HOME), mo)
check("a sealed phrase is found by no search", not M.search("a phrase", k=20, encode=encode, kinds="motif")
      and all(h["kind"] != "motif" for h in M.search("a phrase", k=20, encode=encode)))

# ------------------------------------------------------------------ 3. revealed Atelier works
os.makedirs(os.path.join(M.ART, "music"), exist_ok=True); os.makedirs(os.path.join(MEM, "atelier"), exist_ok=True)
shelf = os.path.join(M.ART, "revealed_piece.png"); open(shelf, "wb").write(png((10, 200, 10)))
sealed = os.path.join(MEM, "atelier", "sealed_piece.png"); open(sealed, "wb").write(png((10, 10, 200)))
hidden = os.path.join(MEM, "atelier", "unshelved.png"); open(hidden, "wb").write(png((90, 90, 90)))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
motif_rec = {"type": "motif-score", "variation_id": "vaaaaaaaaaaaa"}
json.dump([{"revealed": True, "bytes_verified": True, "medium": "image", "artifact": "revealed_piece.png",
            "sha256": sha(shelf), "revealed_at": "2026-10-25T20:00:00", "disclosure": "the green one"},
           {"revealed": False, "bytes_verified": True, "medium": "image", "artifact": "sealed_piece.png", "sha256": sha(sealed)},
           {"revealed": True, "bytes_verified": True, "medium": "image", "artifact": "unshelved.png", "sha256": sha(hidden)},
           {"revealed": True, "medium": "write", "artifact": "x_write.json", "content": json.dumps(motif_rec)}],
          open(M.REVEALS, "w"))
before = len(SEEN)
M.index(encode=encode)
at = [r for r in M.load() if r["kind"] == "atelier"]
check("a revealed work on a public shelf is embedded as an Atelier piece", len(at) == 1 and at[0]["path"] == shelf
      and at[0]["title"] == "the green one", at)
check("its vector is the shelf image's own (embedded once)", len(SEEN) - before == 1
      and at[0]["vec"] == next(r for r in M.load() if r["kind"] == "image" and r["path"] == shelf)["vec"])
check("sealed work is never embedded: not unrevealed, not off the shelf, nothing under memory/atelier",
      not any("/memory/atelier/" in str(r.get("path")) for r in M.load()))
hits = M.search("green", k=10, encode=encode)
check("the work is found once, named as an Atelier piece", [h["kind"] for h in hits if h["path"] == shelf] == ["atelier"], hits)
check("a revealed motif phrase is found", any(h["kind"] == "motif" and h["variation_id"] == "vaaaaaaaaaaaa" for h in hits), hits)

# ------------------------------------------------------------------ search kinds and filters
kinds = {h["kind"] for h in M.search("anything", k=50, encode=encode)}
check("search keeps to his works unless asked", kinds and kinds <= set(M.WORK_KINDS), kinds)
calls = M.search("anything", k=50, encode=encode, kinds="call_audio")
check("call rows come when asked", calls and {h["kind"] for h in calls} == {"call_audio"}, calls)
check("filters: speaker and session", {h["speaker"] for h in M.search("x", 50, encode, "call_audio", speaker="gloria")} == {"gloria"}
      and {h["session_id"] for h in M.search("x", 50, encode, ["call_audio", "film_frame"], session="rr-1")} == {"rr-1"})
check("an unknown kind falls back to his works", {h["kind"] for h in M.search("x", 50, encode, "nonsense")} <= set(M.WORK_KINDS))
check("describe words for the new kinds", 'your moment of a call "gloria"' in M.describe([calls[0] | {"speaker": "gloria"}])
      and "Atelier piece" in M.describe([h for h in hits if h["kind"] == "atelier"]))

# ------------------------------------------------------------------ the chat block, through the local service
import threading
def _local_only(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr[0] == "127.0.0.1":
        return _ORIG_CONNECT(self, addr, *a, **k)
    NET.append(addr); raise OSError("this suite reaches nothing")
socket.socket.connect = _local_only
probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
M.PORT = port
threading.Thread(target=M.serve, kwargs={"encode": encode, "port": port}, daemon=True).start()
time.sleep(0.5)
plain = M.near("anything at all", 10)
check("the service answers with his works only when no kind is asked", plain and {h["kind"] for h in plain} <= set(M.WORK_KINDS), plain)
asked = M.near("anything at all", 10, kinds=["call_audio", "film_frame"])
check("and with call or frame rows when asked", asked and {h["kind"] for h in asked} <= {"call_audio", "film_frame"}, asked)
blk = M.block("anything at all", k=10)
check("the chat block carries no call or frame rows", blk and "moment of a call" not in blk and "frame from a film" not in blk, blk)
check("the chat route still asks the block as before", "return _wn.block(str(getattr(msg, \"message\", \"\") or \"\")[-1500:])" in srv)
msrc = open(os.path.join(REPO, "scripts", "media_embed.py")).read()
blocksrc = msrc[msrc.index("def block("):msrc.index("def nearest(")]
check("block() never asks for other kinds", "kinds" not in blocksrc.split('"""')[2] and "near(text, k)" in blocksrc)
check("the service holds only the text half; the batch alone loads the audio and vision halves",
      'config_kwargs={"vision_config": None, "audio_config": None}' in msrc and "encode = encode or text_encoder()" in msrc
      and "model_encoder()" in msrc[msrc.index("def drain("):msrc.index("def kick(")])
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("everything touched is in the deploy manifest", all(n in deploy for n in ("media_embed.py", "voice_local.py",
      "motif_memory.py", "reelroom_bookmarks.py", "watch_routes.py")))
socket.socket.connect = _no
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
