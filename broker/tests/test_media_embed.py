#!/usr/bin/env python3
"""His media index (EmbeddingGemma 2 beside nomic, 22 October): works under memory/art embedded once each by content,
a changed file again, a removed one never found; a text line finds the nearest; nomic's stores untouched; nothing
leaves the machine. Scratch workspace; the model is a stub; ffmpeg is not called; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="media-embed-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
_ORIG_CONNECT = socket.socket.connect
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import media_embed as M
M._excerpts = lambda path, tmp: []                      # no ffmpeg here
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("its store is scratch, and is not nomic's", M.STORE.startswith(HOME) and not M.STORE.endswith("/embeddings.jsonl"))

art = M.ART
os.makedirs(os.path.join(art, "video")); os.makedirs(os.path.join(art, "music"))
def put(rel, data):
    p = os.path.join(art, rel); open(p, "wb").write(data); return p
sea = put("sea.png", b"red sky over water"); room = put("video/room.mp4", b"a dark room, a door")
song = put("music/song.mp3", b"slow piano"); put("notes.md", b"not media")
json.dump([{"path": sea, "prompt": "Sea at dusk"}], open(os.path.join(art, "gallery.json"), "w"))
nomic = os.path.join(M.MEMORY, "embeddings.jsonl"); open(nomic, "w").write("nomic row\n")

# the stub model: a vector per concept, read from the file's bytes or the query's words
CONCEPTS = ["sky", "room", "piano"]
SEEN = []
def encode(item):
    SEEN.append(item)
    text = item if isinstance(item, str) else open(next(v if isinstance(v, str) else v[0] for k, v in item.items() if k != "text"), "rb").read().decode()
    v = [1.0 if c in text else 0.0 for c in CONCEPTS] + [0.0] * (M.DIM - len(CONCEPTS))
    return v if any(v) else [0.0] * (M.DIM - 1) + [1.0]

out = M.index(encode=encode)
rows = M.load()
check("each work is embedded once, by kind, and nothing that is not media", sorted(r["kind"] for r in rows) == ["audio", "image", "video"]
      and not any(r["path"].endswith(".md") for r in rows), out)
check("each row names its model and width", all(r["model"] == "google/embeddinggemma-2" and r["dim"] == 768 and len(r["vec"]) == 768 for r in rows))
check("the work goes in as itself, in the model card's form", any(i == {"text": "<|image|>", "image": [sea]} for i in SEEN)
      and any(i == {"text": "<|video|>", "video": room} for i in SEEN))
check("a shelf's title is kept for showing", next(r for r in rows if r["path"] == sea)["title"] == "Sea at dusk")
check("run again, nothing is embedded twice", M.index(encode=encode) == ["nothing new: 3 works indexed"])
hits = M.search("the piano she played", encode=encode)
check("a line finds the work by what is in it", hits and hits[0]["path"] == song and hits[0]["kind"] == "audio", hits)
check("and is asked as a search query", any(isinstance(i, str) and i.startswith("task: search result | query: ") for i in SEEN))
open(room, "wb").write(b"a dark room, a door, and sky")
M.index(encode=encode)
check("a changed file is embedded again", sum(1 for r in M.load() if r["path"] == room) == 2)
os.remove(sea)
check("a removed work is never found", all(h["path"] != sea for h in M.search("sky", k=5, encode=encode)))
check("nomic's store is untouched", open(nomic).read() == "nomic row\n")
check("with no venv, nearest() is empty, not an error", M.nearest("anything") == [] or os.path.exists(M.VENV_PY))
# the service his chats and journal ask: a real localhost server on a free port, the model a stub
import threading, time as _t
def _local_only(self, addr, *a, **k):     # localhost for this service, nothing else
    if isinstance(addr, tuple) and addr[0] == "127.0.0.1":
        return _ORIG_CONNECT(self, addr, *a, **k)
    NET.append(addr); raise OSError("this suite reaches nothing")
socket.socket.connect = _local_only
probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
M.PORT = port
threading.Thread(target=M.serve, kwargs={"encode": encode, "port": port}, daemon=True).start()
_t.sleep(0.5)
hits = M.near("the piano again", 2)
check("the service answers a line with his nearest works", hits and hits[0]["path"] == song, hits)
blk = M.block("the piano again")
check("the chat block names the work in his words, kind and date, and says it is his to bring up only if it fits",
      'your song "song"' in blk and "only if one truly fits" in blk and "found by what is IN them" in blk, blk)
M.PORT = port + 1 if port < 65535 else port - 1
check("with the service down, the chat goes on without it", M.block("anything") == "" and M.near("anything") == [])
srv = open(os.path.join(REPO, "bin", "server.py")).read()
_av = srv.index("{_works_near(msg)}", srv.index("async def avatar_chat"))
check("all four chat prompts carry it; in the avatar chat after the cache split, so the cached start is unchanged",
      srv.count("{_works_near(msg)}") == 4 and srv.rindex("[[CACHESPLIT]]", 0, _av) > srv.index("async def avatar_chat"))
jr = open(os.path.join(REPO, "scripts", "idle-journal.sh")).read()
check("his journal entry is followed by the works it is nearest", "media_embed.near(" in jr and "Near this, among my own works" in jr)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
