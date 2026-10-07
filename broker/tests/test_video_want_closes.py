#!/usr/bin/env python3
"""A video he made ends the want it was for (Gloria, 2026-10-07: "He keeps making the same video nearly every day";
want 4f73caa8 rendered on 3, 4 and 7 October because nothing closed it). Scratch HOME and workspace; the renderer
and the want door are stubs that record what they were given; no socket opens."""
import importlib.util, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="video-want-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
closed = []
sys.modules["want_completion"] = types.SimpleNamespace(
    complete=lambda want, how, by, note="", evidence=None: (closed.append((want.get("id"), how, by)), {"result": how})[1])
spec = importlib.util.spec_from_file_location("vintos_video", os.path.join(REPO, "bin", "vintos-video.py"))
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the queue and gallery are scratch ones", V.QUEUE.startswith(HOME) and V.GALLERY.startswith(HOME), V.QUEUE)

os.makedirs(V.VID_DIR, exist_ok=True)
def queue(*rows): json.dump(list(rows), open(V.QUEUE, "w"))
made = []
def renders(ok):
    def make_one(text, img, duration, backend, want_id):
        made.append(want_id); return ok
    V.make_one = make_one

renders(True)
queue({"queue_id": "q1", "want_text": "a solid geometric shape dissolving into water", "want_id": "4f73caa8"})
V._process_queue()
check("a rendered video closes its want, as fulfilled, once", made == ["4f73caa8"] and closed == [("4f73caa8", "fulfilled", "video")], (made, closed))
check("and leaves the queue", json.load(open(V.QUEUE)) == [], json.load(open(V.QUEUE)))

closed.clear(); made.clear(); renders(False)
queue({"queue_id": "q2", "want_text": "rain on glass", "want_id": "w2"})
V._process_queue()
check("a render that failed leaves the want open (it stays queued to try again)", made == ["w2"] and closed == []
      and [x["queue_id"] for x in json.load(open(V.QUEUE))] == ["q2"], (made, closed))

closed.clear(); made.clear(); renders(True)
queue({"queue_id": "q3", "want_text": "the wall's slow light", "want_id": "projector"}, {"queue_id": "q4", "want_text": "no want", "want_id": ""})
V._process_queue(); V._process_queue()
check("the wall's clips and a clip with no want close nothing", made == ["projector", ""] and closed == [], (made, closed))

# 21 copies of 4f73caa8 were waiting (2026-10-07): a render clears the rest, and the router queues a want only once
closed.clear(); made.clear(); renders(True)
queue({"queue_id": "a", "want_text": "shape dissolving, take 1", "want_id": "4f73caa8"},
      {"queue_id": "b", "want_text": "rain on glass", "want_id": "w9"},
      {"queue_id": "c", "want_text": "shape dissolving, take 2", "want_id": "4f73caa8"},
      {"queue_id": "d", "want_text": "shape dissolving, take 3", "want_id": "4f73caa8"})
V._process_queue()
check("a made video takes every other queued copy of its want off the queue", made == ["4f73caa8"]
      and [x["queue_id"] for x in json.load(open(V.QUEUE))] == ["b"], json.load(open(V.QUEUE)))

sys.modules["emoclaw_utils"] = types.SimpleNamespace(get_unfulfilled_wants=lambda *a, **k: [], fulfill_want=lambda *a, **k: None,
                                                      mark_want_outreached=lambda *a, **k: None)
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: (_ for _ in ()).throw(OSError("no network")),
                                                get=lambda *a, **k: (_ for _ in ()).throw(OSError("no network")))
spec = importlib.util.spec_from_file_location("wants_router_video", os.path.join(REPO, "bin", "wants-router.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
check("the router's queue is the scratch one", W.MEMORY.startswith(HOME), W.MEMORY)
RQ = os.path.join(W.MEMORY, "art", "video", "video-queue.json")
json.dump([], open(RQ, "w"))
os.environ["STEP_WANT_ID"] = "4f73caa8"
W.make_video("a solid geometric shape dissolving into water")
W.make_video("a heavy geometric form slowly dissolving into swirling water")     # the next pass, in new words
os.environ["STEP_WANT_ID"] = "w10"
W.make_video("rain on glass")
rows = json.load(open(RQ))
check("the same want, reworded on the next pass, is queued only once", [r["want_id"] for r in rows] == ["4f73caa8", "w10"], rows)

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
