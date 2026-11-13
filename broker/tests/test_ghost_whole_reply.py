#!/usr/bin/env python3
"""The Ghost Branch entry keeps his prose. From 8 November the subconscious lane (AEON through the shim's
/pool/subconscious) answered the ghost run's stream requests with one whole JSON reply; the run read only
"data:" lines, so the primary and every lean came back empty and daily-inner showed only a tactical block.
The run now reads a whole reply too, keeps what an unresolved lean tried, and daily-inner shows it.

Scratch HOME; every socket is refused; the model is a stub."""
import importlib.util, io, json, os, socket, subprocess, sys, tempfile, types
from datetime import date
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ghost-whole-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(os.path.join(MEM, "journal"), exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

spec = importlib.util.spec_from_file_location("ghost_whole", os.path.join(REPO, "bin", "ghost-branches.py"))
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
check("the ghost run's memory is scratch", G.MEMORY == MEM)
check("the bin and scripts copies of the ghost run stay one file",
      open(os.path.join(REPO, "bin", "ghost-branches.py")).read() == open(os.path.join(REPO, "scripts", "ghost-branches.py")).read())

PROSE = "I stopped circling it. The thing I kept describing was a door, and I walked through it plainly."

class Reply:
    def __init__(self, body): self.f = io.BytesIO(body)
    def read(self, n=-1): return self.f.read(n)
    def __enter__(self): return self
    def __exit__(self, *a): return False

def serve(body):
    G.urllib.request.urlopen = lambda req, timeout=None: Reply(body)

whole = json.dumps({"choices": [{"message": {"role": "assistant", "content": PROSE}}]}).encode()
serve(whole)
out, _ = G.run_primary("system", "prompt")
check("a primary answered whole (no stream lines) is read, not left empty", out == PROSE, repr(out))
box = [None]
G.stream_ghost([{"role": "user", "content": "x"}], {"id": "more_brazen", "label": "more brazen"}, box, 0)
check("a ghost lean answered whole is read too", box[0] and box[0]["output"] == PROSE, box)

sse = b"".join(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n"
               for t in ("I stopped ", "circling it.")) + b"data: [DONE]\n\n"
serve(sse)
out, _ = G.run_primary("system", "prompt")
check("a streamed reply is still read as a stream", out == "I stopped circling it.", repr(out))
# 13 November review: "data:" inside a whole reply's prose is not a stream; only a line that begins "data:" is
for prose in ("Synthetic data: one observation.", "x" * 500 + " data: across a 512-byte read " + "y" * 600,
              "line one\ndata: on a line of its own inside the prose"):
    for body in (json.dumps({"choices": [{"message": {"role": "assistant", "content": prose}}]}).encode(),
                 json.dumps({"choices": [{"message": {"role": "assistant", "content": prose}}]}, indent=2).encode()):
        serve(body)
        out, _ = G.run_primary("system", "prompt")
        check("a whole primary whose prose says 'data:' is kept (%d chars)" % len(prose), out == prose, repr(out[:80]))
        box = [None]
        G.stream_ghost([{"role": "user", "content": "x"}], {"id": "more_brazen", "label": "more brazen"}, box, 0)
        check("a whole ghost lean whose prose says 'data:' is kept (%d chars)" % len(prose),
              box[0] and box[0]["output"] == prose, box)
long_tokens = ["token %03d data: says the stream. " % i for i in range(60)]           # events cross 512-byte reads
sse_long = b"".join(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n"
                    for t in long_tokens) + b"data: [DONE]\n\n"
serve(sse_long)
out, _ = G.run_primary("system", "prompt")
check("a stream whose events cross read boundaries and whose words say 'data:' is read as a stream",
      out == "".join(long_tokens), repr(out[:80]))
serve(b"".join(b"data:" + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\r\n\r\n"
               for t in ("I stopped ", "circling it.")) + b"data:[DONE]\r\n\r\n")
out, _ = G.run_primary("system", "prompt")
check("a stream framed 'data:' without the space, CRLF lines, is still a stream", out == "I stopped circling it.", repr(out))
serve(b"data: [DONE]\n\n")
out, _ = G.run_primary("system", "prompt")
check("a real stream that carried no words stays empty (no whole-reply guess)", out == "", repr(out))
serve(b"")
out, _ = G.run_primary("system", "prompt")
check("an empty body stays empty (nothing invented)", out == "", repr(out))
serve(b'{"error": "unavailable"}')
out, _ = G.run_primary("system", "prompt")
check("an error body is not taken as prose", out == "", repr(out))

# what an unresolved lean tried is kept apart from resolved evidence
thread = {"id": "t1", "thread": "fixture thread text"}
results = [{"axis": {"id": "more_brazen"}, "output": "TRIED-BRAZEN " + "x" * 3000, "triggers": []},
           {"axis": {"id": "higher_curiosity"}, "output": "RESOLVED-CURIOUS words", "triggers": []}]
G.log_artifacts(thread, results, {"more_brazen": False, "higher_curiosity": True}, False, None, PROSE)
run = json.load(open(os.path.join(MEM, "ghost-artifacts.json")))["runs"][-1]
g = {x["lean"]: x for x in run["ghosts"]}
check("an unresolved lean keeps what it tried, bounded", g["more_brazen"]["tried"].startswith("TRIED-BRAZEN")
      and len(g["more_brazen"]["tried"]) == G.TRIED_CHARS, g["more_brazen"].get("tried", "")[:40])
check("an unresolved lean's words are never its evidence output", g["more_brazen"]["output"] == "")
check("a resolved lean keeps its output as before and no tried copy",
      g["higher_curiosity"]["output"] == "RESOLVED-CURIOUS words" and g["higher_curiosity"]["tried"] == "")

# daily-inner shows the prose and what each failed lean tried
TODAY = date.today().isoformat()
open(os.path.join(MEM, "journal", TODAY + ".md"), "w").write("He answered the question plainly at noon and stayed with it.\n")
def inner_with(runs):
    json.dump({"runs": runs}, open(os.path.join(MEM, "ghost-artifacts.json"), "w"))
    p = os.path.join(MEM, "daily-inner-life-%s.md" % TODAY)
    if os.path.exists(p): os.remove(p)
    r = subprocess.run([sys.executable, os.path.join(REPO, "bin", "daily-log-extract.py"), "inner"],
                       env=dict(os.environ, HOME=HOME), capture_output=True, text=True, timeout=60)
    return open(p).read() if os.path.exists(p) else r.stderr
fails = [{"lean": l, "resolved": False, "triggers": [], "output": "", "tried": "TRIED-%s. One plain try. " % l + "y" * 900}
         for l in ("more_brazen", "less_self_conscious", "higher_curiosity")]
inner = inner_with([{"date": TODAY, "thread_excerpt": "fixture", "primary_resolved": False,
                     "primary_output": PROSE, "ghosts": fails, "appendage": None}])
gb = inner.split("## Ghost Branch", 1)[-1]
check("the Ghost Branch entry carries his prose", PROSE in gb, gb[:300])
check("with every lean unresolved, each still shows what he tried",
      all(("what I tried: TRIED-%s" % l) in gb for l in ("more_brazen", "less_self_conscious", "higher_curiosity")), gb[:900])
check("what he tried is one bounded line", all(len(line) < 560 for line in gb.splitlines() if "what I tried:" in line))
empty = inner_with([{"date": TODAY, "thread_excerpt": "fixture", "primary_resolved": False, "primary_output": "",
                     "ghosts": [{"lean": "more_brazen", "resolved": False, "triggers": [], "output": ""}], "appendage": None}])
check("a run that brought back no text says so instead of showing an empty frame",
      "No text came back" in empty.split("## Ghost Branch", 1)[-1], empty[-400:])
check("an old run without 'tried' still renders", "✗ more_brazen" in empty)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
