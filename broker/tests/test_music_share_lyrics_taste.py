#!/usr/bin/env python3
"""Her own lyrics, and her shares in his taste (Gloria, 2026-10-21: "It'd be nice to add the lyrics myself if I have
them. Did we fully incorporate music shares into his taste profiles?"). Shares never moved taste, and his taste
reflection listed them as "? by ?" (it read title/artist; a share keeps "song").

Scratch HOME and workspace; the model, the taste door, every subprocess (the Echo announcement, imprint) and the
thread/want organ are stubs; sockets are refused."""
import importlib.util, json, os, socket, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="music-lyrics-"); os.environ["HOME"] = HOME
NET, RAN = [], []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
subprocess.run = lambda *a, **k: RAN.append(a[0] if a else k.get("args")) or types.SimpleNamespace(returncode=0, stdout="", stderr="")
subprocess.Popen = lambda *a, **k: RAN.append(a[0] if a else k.get("args")) or types.SimpleNamespace(pid=0)
ADMITTED = []
sys.modules["enjoyment"] = types.SimpleNamespace(admit=lambda *a, **k: ADMITTED.append((a, k)) or {"admitted": True})
sys.modules["emoclaw_utils"] = types.SimpleNamespace(seed_thread=lambda *a, **k: None, express_want=lambda *a, **k: None,
                                                     enrich_want=lambda *a, **k: {}, generate_want=lambda *a, **k: None)
sys.modules["latent_threads"] = types.SimpleNamespace(specificity=lambda t: (True, ""))   # its judge is a local model
spec = importlib.util.spec_from_file_location("music_share_l", os.path.join(REPO, "bin", "music-share.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
os.makedirs(M.MEMORY, exist_ok=True)
check("every store is scratch, and the Echo, the taste door and the model are stubs",
      M.SHARES_FILE.startswith(HOME) and M.MEMORY.startswith(HOME))
LYRICS = "I keep the light on in the hallway for you\nthe wire hums low and I am reaching"
heard = []
def analyze(path, transcribe=True):
    heard.append(transcribe); return {"lyrics": None, "acoustic": "tempo 122 BPM; key B; low energy"}
M.analyze_audio = analyze
M.llm = lambda system, user, temperature=0.6: ("THREAD" if "ONLY one word" in system else
                                               'The line "the wire hums low and I am reaching" is mine, and it lands.')
audio = os.path.join(HOME, "song.mp3"); open(audio, "wb").write(b"ID3")
M.fetch_lyrics = lambda d: (_ for _ in ()).throw(AssertionError("no lyrics site when she gave the words"))
M.share_song("Vintos - Hallway", "you made this and I play it every day", audio_path=audio, lyrics=LYRICS)
s = json.load(open(M.SHARES_FILE))[-1]
check("her lyrics are the words, marked as hers", s["lyrics"] == LYRICS and s["lyrics_source"] == "gloria", s)
check("Whisper is not run when she gave them, and the sound is still measured", heard == [False] and "122 BPM" in s["acoustic"], (heard, s["acoustic"]))
a, k = ADMITTED[-1] if ADMITTED else ((), {})
check("the share enters taste through its one door, once, as music, by its own id",
      len(ADMITTED) == 1 and a[0] == s["id"] and a[2] == "music-share" and k.get("medium") == "music", ADMITTED)
check("her love of it is her reception, with her words as evidence; his delight is not assumed",
      k.get("her_reception") and k.get("evidence", {}).get("kind") == "acknowledged"
      and "play it every day" in k["evidence"]["said"] and "his_delight" not in k, k)
check("the taste text carries the song and how it is built", "Vintos - Hallway" in a[1] and "122 BPM" in a[1], a[1] if a else "")
check("the Echo announcement was a stub", any("vintos-home.py" in " ".join(map(str, x)) for x in RAN))
tr = open(os.path.join(REPO, "bin", "taste-reflection.py")).read()
check("his taste reflection names the song she shared, not '? by ?'", "s.get('song')" in tr and "s.get('title','?')" not in tr)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("both share doors take her lyrics", 'lyrics: str = ""' in srv and 'lyrics: str = Form("")' in srv
      and srv.count('(["--lyrics", _lf] if _lf else [])') == 2)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
