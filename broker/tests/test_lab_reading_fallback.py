#!/usr/bin/env python3
"""A finished Lab experiment is read by the next frontier lens when its planner returns no reading (7 October, 20:26:
Grok's run completed and the whole session was held as "frontier lens returned no reading"). Scratch stores; the
frontier models and the Mac are stubs; sockets are refused."""
import contextlib, importlib.util, json, os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="lab-reading-fallback-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
sys.modules["chemistry_mac"] = types.SimpleNamespace(status=lambda: {"ok": True}, run=lambda *a: {"ok": True}, reading=lambda *a: {"ok": True})
@contextlib.contextmanager
def admitted(*a, **k): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
S = load("chemistry_session_fallback", os.path.join(REPO, "scripts", "chemistry_session.py"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's stores are scratch ones", lab.ROOT.startswith(HOME), lab.ROOT)

asked = []
READING = json.dumps({"reading": "the CUB packs like 6V55", "what_surprised_me": "", "prediction_vs_result": "matched",
                      "next_question": "SLC26A4 STAS", "keep": ""})
def frontier(replies):
    async def _frontier(lens, system, prompt):
        asked.append(lens)
        r = replies.get(lens, "")
        if isinstance(r, Exception): raise r
        return r
    return _frontier
S._frontier = frontier({"grok": "", "claude": READING})
out = S._reading("ctx", {"experiment": "fold"}, {"ok": True}, lens="grok")
check("grok wrote nothing: the next lens reads the finished run", out["reading"] == "the CUB packs like 6V55" and out["read_by"] == "claude", out)
check("grok was asked first, once", asked[:2] == ["grok", "claude"], asked)
asked.clear()
S._frontier = frontier({"grok": RuntimeError("timeout"), "claude": "", "sol": READING})
out = S._reading("ctx", {}, {"ok": True}, lens="grok")
check("an error is not the end either", out["read_by"] == "sol" and asked == ["grok", "claude", "sol"], (out, asked))
S._frontier = frontier({})
try:
    S._reading("ctx", {}, {"ok": True}, lens="grok"); raised = ""
except RuntimeError as e:
    raised = str(e)
check("only when no lens reads it is it held, saying who was tried", "tried grok, claude, sol" in raised, raised)
asked.clear()
S._frontier = frontier({"claude": READING})
out = S._reading("ctx", {}, {"ok": True}, lens="claude")
check("a planner that reads its own run costs one call, as before", asked == ["claude"] and out["read_by"] == "claude", asked)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
