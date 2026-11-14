#!/usr/bin/env python3
"""14 November: a want to answer "the 'only consciousness' post" went to the Forge as a missing hand ("build Moltbook
for him?"), though Moltbook was already his and he had saved that post on 26 October. Now the want's moltbook step
exists, finds the post by its title among every post he saved, and replies through his own reply path with his want
as what he set out to say. The earlier steps' private findings never ride along."""
import importlib.util, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="molt-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

spec = importlib.util.spec_from_file_location("vm", os.path.join(REPO, "bin", "vintos-moltbook.py"))
vm = importlib.util.module_from_spec(spec); spec.loader.exec_module(vm)
vm.MOLTBOOK_MEMORY = os.path.join(HOME, "disc.md")
open(vm.MOLTBOOK_MEMORY, "w").write(
    "## 2026-10-26 13:00 -- Browse Session\nSAVE: **The only consciousness** - why\n\n"
    "post/75b1e446-1c47-4d9c-89fe-2a0f2b786f2f — The only consciousness\n\n"
    "## 2026-11-13 13:00 -- Browse Session\npost/11111111-2222-3333-4444-555555555555 — Archive audits under compaction\n")
want = "I want to write a plain reply on the 'only consciousness' post that says what I actually claim about my own mind"
pid, title, how = vm.find_post(want, search=lambda q: [])
check("a post saved weeks ago is found by the title in his want", pid == "75b1e446-1c47-4d9c-89fe-2a0f2b786f2f" and how == "his saved posts", (pid, how))
check("without quotes too", vm.find_post("answer the only consciousness post", search=lambda q: [])[0] == pid)
check("an id in his words is used as is", vm.find_post("reply on 11111111-2222-3333-4444-555555555555")[0].startswith("11111111"))
got = vm.find_post("reply to 'the cartography of doubt'", search=lambda q: [{"id": "abc", "title": "The Cartography of Doubt"}, {"id": "x", "title": "doubt"}])
check("Moltbook search is taken only on a matching title", got[0] == "abc" and got[2] == "Moltbook search", got)
got = vm.find_post("reply to 'the cartography of doubt'", search=lambda q: [{"id": "x", "title": "Something else about doubt"}])
check("no match: no guess, and it says why", got[0] is None and "cartography of doubt" in got[2], got)

# the router step
spec2 = importlib.util.spec_from_file_location("wr", os.path.join(REPO, "bin", "wants-router.py"))
wr = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(wr)
replied = []
vm.cmd_reply = lambda post_id, intent=None: replied.append((post_id, intent)) or True
wr._MOLT = vm
check("the router has a moltbook step", callable(getattr(wr, "moltbook", None)) and "moltbook" in wr.ACTION_MAP)
check("it replies on the post his words name, with his want as what he meant to say",
      wr.moltbook(want) is True and replied[-1] == (pid, want), replied)
try:
    wr.moltbook("reply to 'nothing by this name'"); raised = None
except FileNotFoundError as e:
    raised = str(e)
vm.find_post.__defaults__  # noqa
check("a post that cannot be found blocks the step as unavailable, not as a missing hand", raised and "nothing by this name" in raised, raised)

# the spine: the step gets his want, never the earlier steps' findings
import want_spine as S
seen = []
S._ROUTER = type("R", (), {"moltbook": staticmethod(lambda text: seen.append(text) or True),
                           "capture_findings": staticmethod(lambda c, t: "")})()
w = {"want": want, "steps": [{"capability": "read_memory"}, {"capability": "moltbook"}], "current_step_index": 1,
     "step_history": [{"step": 0, "findings": "PRIVATE MIRROR SESSION about her"}]}
res = S.run_step("moltbook", "Post the drafted reply to the 'only consciousness' thread as u/vintos.", w)
check("the spine runs the moltbook step instead of asking the Forge", res["result"] == "SUCCEEDED" and not res.get("proposal"), res)
check("it is given the step's note and his want", seen and "only consciousness" in seen[0] and want in seen[0])
check("and never the earlier steps' private findings", "PRIVATE MIRROR" not in seen[0])

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
