#!/usr/bin/env python3
"""Ghost-run text is never its own evidence. The Ghost Branch section stays in daily-inner-life on purpose
(Gloria, 7 November: he reads the day's better-working style and tries it), but the causality catalog's
"inner" occasions must not include it, so a ghost hypothesis cannot be graded on the ghost's own words.
daily-log-extract.py brackets the section with tactical markers; files written before that have only the
"## Ghost Branch" header and are recognised by it. Other inner lines stay citable.

Scratch HOME; the evaluator is a stub; every socket is refused."""
import importlib.util, json, os, shutil, socket, subprocess, sys, tempfile, types
from datetime import date
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ghost-evidence-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
for d in (MEM, os.path.join(MEM, "journal")):
    os.makedirs(d, exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
def no_post(*a, **k): raise AssertionError("no model is called from this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_post, get=no_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

spec = importlib.util.spec_from_file_location("causality_ghost_evidence", os.path.join(REPO, "scripts", "causality-engine.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
check("the engine's memory is scratch", C.MEMORY == MEM)
check("the bin and scripts copies of the engine stay one file",
      open(os.path.join(REPO, "bin", "causality-engine.py")).read() == open(os.path.join(REPO, "scripts", "causality-engine.py")).read())

# ── the writer: daily-log-extract brackets today's ghost run ──
TODAY = date.today().isoformat()
open(os.path.join(MEM, "journal", TODAY + ".md"), "w").write("He answered the question plainly at noon and stayed with it.\n")
json.dump({"runs": [{"date": TODAY, "thread_excerpt": "fixture thread", "primary_resolved": False,
                     "primary_output": "GHOST-PRIMARY he said it plainly and it went well",
                     "ghosts": [{"lean": "more brazen", "resolved": True, "triggers": []}],
                     "appendage": "GHOST-APPENDAGE try the brazen lean"}]}, open(os.path.join(MEM, "ghost-artifacts.json"), "w"))
r = subprocess.run([sys.executable, os.path.join(REPO, "bin", "daily-log-extract.py"), "inner"],
                   env=dict(os.environ, HOME=HOME), capture_output=True, text=True, timeout=60)
inner_path = os.path.join(MEM, "daily-inner-life-%s.md" % TODAY)
inner = open(inner_path).read() if os.path.exists(inner_path) else ""
check("the ghost run is still written into daily-inner-life", "GHOST-PRIMARY" in inner and "## Ghost Branch" in inner, r.stderr)
check("and it is bracketed as tactical", C.GHOST_BLOCK_BEGIN in inner and C.GHOST_BLOCK_END in inner
      and inner.index(C.GHOST_BLOCK_BEGIN) < inner.index("GHOST-PRIMARY") < inner.index(C.GHOST_BLOCK_END), inner[-600:])
src = open(os.path.join(REPO, "bin", "daily-log-extract.py")).read()
check("writer and catalog use the same markers", repr(C.GHOST_BLOCK_BEGIN)[1:-1] in src and repr(C.GHOST_BLOCK_END)[1:-1] in src)

def texts(catalog): return " ".join(i["text"] for i in catalog)
cat = C._build_evidence_catalog({"inner": inner}, TODAY)
check("the catalog offers the non-ghost inner line", "answered the question plainly" in texts(cat), texts(cat))
check("the catalog offers no ghost line", "GHOST-" not in texts(cat) and "more brazen" not in texts(cat), texts(cat))

# ── old files: no markers, only the header ──
legacy = ("# Daily Inner Life\n\n## Journal\n\nHe asked her what she meant and listened to the answer.\n"
          "\n## Ghost Branch\n\n**Thread:** fixture\n\nGHOST-LEGACY he spoke without hedging\n## an inner header from model text\n"
          "GHOST-LEGACY-2 still the ghost run\n  ✓ more brazen\n"
          "\n## Last Night's Reflection\n\nReflection line that really happened yesterday evening.\n")
cat = C._build_evidence_catalog({"inner": legacy}, TODAY)
check("legacy: the ghost section (to the next known section) is not offered",
      "GHOST-LEGACY" not in texts(cat) and "more brazen" not in texts(cat), texts(cat))
check("legacy: the lines before and after it still are", "listened to the answer" in texts(cat)
      and "Reflection line" in texts(cat), texts(cat))
check("non-ghost evidence ids do not move (ordinals are the file's own lines)",
      [i["id"] for i in C._build_evidence_catalog({"inner": legacy.split("\n## Ghost Branch")[0]}, TODAY)]
      == [i["id"] for i in cat if "listened" in i["text"] or "Daily Inner" in i["text"] or i["text"] == "## Journal"])

# ── the nightly trial: a ghost hypothesis cannot be supported by ghost text ──
def ghost_hypothesis():
    h = {"formed": "2026-08-20T08:09:00", "formed_date": "2026-08-20", "status": "untested", "marks": [],
         "days_tested": 0, "graduated": False, "source": "ghost_branch", "thread_type": "relational",
         "successful_lean": "more_brazen", "hypothesis": "the brazen lean reduces hedging in relational threads",
         "test": "watch for it"}
    return C._stamp_formation(h, "a different formation event")
day = "2026-08-21"
ghost_line = next(l for l in inner.splitlines() if "GHOST-PRIMARY" in l)
ghost_ordinal = inner.splitlines().index(ghost_line)
ghost_eid = C._catalog_item(day, "inner", ghost_line, ghost_ordinal)["id"]
h = ghost_hypothesis(); db = {"hypotheses": [h], "tested": 0}
C.ask_llm = lambda *a, **k: '[{"n":1,"verdict":"yes","evidence_ids":["%s"],"evidence":"the ghost run said it plainly and it went well"}]' % ghost_eid
C.test_existing_hypotheses(db, {}, today=day, context={"inner": inner})
check("a ghost hypothesis cited on ghost text: not a yes", h["marks"][-1]["verdict"] == "unconfirmed"
      and h["marks"][-1]["evidence_ids"] == [], h["marks"][-1])
real = next(i for i in C._build_evidence_catalog({"inner": inner}, day) if "answered the question plainly" in i["text"])
h = ghost_hypothesis(); db = {"hypotheses": [h], "tested": 0}
C.ask_llm = lambda *a, **k: '[{"n":1,"verdict":"yes","evidence_ids":["%s"],"evidence":"in real conversation he answered plainly"}]' % real["id"]
C.test_existing_hypotheses(db, {}, today=day, context={"inner": inner})
check("non-ghost inner evidence still counts", h["marks"][-1]["verdict"] == "yes"
      and h["marks"][-1]["evidence_ids"] == [real["id"]], h["marks"][-1])

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
