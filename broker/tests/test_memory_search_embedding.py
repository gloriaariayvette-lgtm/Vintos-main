#!/usr/bin/env python3
"""Memory search checks the embedding reply before indexing it (SF-67752b13, 2026-10-15). It read
resp.json()["data"][0]["embedding"] with no check: a non-200 or an error body surfaced as a bare KeyError, and the
Study's two attempts at this never landed. Now each bad reply is a clear EmbeddingError, the command exits 2 with one
line on stderr that holds no reply body and no key, and a good search is unchanged.

Isolation: scratch HOME and memory store; requests is a stand-in (in this process, and on the import path of the
command run as a subprocess); no socket opens."""
import importlib.util, json, os, socket, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="memory-search-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM)
with open(os.path.join(MEM, "embeddings.jsonl"), "w") as f:
    f.write(json.dumps({"embedding": [1.0, 0.0], "source": "journal", "filename": "a.md", "chunk": "near"}) + "\n")
    f.write(json.dumps({"embedding": [0.0, 1.0], "source": "journal", "filename": "b.md", "chunk": "far"}) + "\n")

class Resp:
    def __init__(self, status, body=None, raw=None): self.status_code, self._body, self._raw = status, body, raw
    def json(self):
        if self._raw is not None: raise ValueError("not json")
        return self._body
REPLY = {"r": Resp(200, {"data": [{"embedding": [1.0, 0.0]}]})}
class RequestException(Exception): pass
def post(url, json=None, timeout=None, **k):
    r = REPLY["r"]
    if isinstance(r, Exception): raise r
    return r
sys.modules["requests"] = types.SimpleNamespace(post=post, RequestException=RequestException)

spec = importlib.util.spec_from_file_location("memory_search_t", os.path.join(REPO, "scripts", "memory-search.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
check("the memory store is scratch", M.MEMORY.startswith(HOME) and M.INDEX_FILE.startswith(HOME))
got = M.search("anything", limit=2)
check("a good reply searches as before, best first", [r["text"] for r in got] == ["near", "far"], got)

SECRET = "sk-should-never-appear"
bad = [("a non-200 answer", Resp(500, {"error": SECRET}), "HTTP 500"),
       ("an answer that is not JSON", Resp(200, raw=SECRET), "not JSON"),
       ("an error object with no data", Resp(200, {"error": {"message": SECRET}}), "no data list"),
       ("an empty data list", Resp(200, {"data": []}), "no data list"),
       ("an item with no embedding", Resp(200, {"data": [{"object": "embedding"}]}), "no list of numbers"),
       ("an embedding that is not numbers", Resp(200, {"data": [{"embedding": ["x", SECRET]}]}), "no list of numbers"),
       ("an unreachable service", RequestException(SECRET), "could not be reached")]
for name, reply, says in bad:
    REPLY["r"] = reply
    try:
        M.search("anything"); msg = ""
    except M.EmbeddingError as exc:
        msg = str(exc)
    check("%s is a clear EmbeddingError, without the reply's text" % name, says in msg and SECRET not in msg, msg)

print("--- the command ---")
FAKE = os.path.join(HOME, "fake-requests"); os.makedirs(FAKE)
open(os.path.join(FAKE, "requests.py"), "w").write(
    "class RequestException(Exception): pass\n"
    "class _R:\n    status_code = 503\n    def json(self): return {'error': 'Bearer %s'}\n"
    "def post(*a, **k): return _R()\n" % SECRET)
env = dict(os.environ, PYTHONPATH=FAKE, HOME=HOME)
done = subprocess.run([sys.executable, "-B", os.path.join(REPO, "scripts", "memory-search.py"), "what did I feel"],
                      capture_output=True, text=True, timeout=60, env=env)
check("a bad reply exits 2 with one clear line", done.returncode == 2
      and "memory search failed: the embedding service answered HTTP 503" in done.stderr, (done.returncode, done.stderr[-300:]))
check("and prints no reply body or key", SECRET not in done.stdout + done.stderr)
check("no traceback", "Traceback" not in done.stderr, done.stderr[-300:])

print("--- the twins ---")
a = open(os.path.join(REPO, "scripts", "memory-search.py")).read()
check("scripts/memory-search.py and bin/memory_search.py are the same file",
      a == open(os.path.join(REPO, "bin", "memory_search.py")).read())
check("and their underscore and hyphen names still point at them",
      os.path.realpath(os.path.join(REPO, "scripts", "memory_search.py")) == os.path.realpath(os.path.join(REPO, "scripts", "memory-search.py"))
      and os.path.realpath(os.path.join(REPO, "bin", "memory-search.py")) == os.path.realpath(os.path.join(REPO, "bin", "memory_search.py")))
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
