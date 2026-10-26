#!/usr/bin/env python3
"""A forged capability earns a place in his practice (proposal 08, 26 October).

Every run of an installed forged skill leaves a receipt: who chose it (his own work, or a
person making it run), the want and step that reached for it, and hashes of what went in
and came out. Later passes join the output against what he did next. Nothing here retires
a tool, and a call a person forced is a canary, never acceptance.

Scratch workspace only; the sandbox runner is a stub, so no forged code runs and nothing
is sent."""
import importlib.util, json, os, subprocess, sys, tempfile, types
from datetime import datetime, timedelta

HOME = tempfile.mkdtemp(prefix="vintos-forge-practice-")
os.environ["SPARK_WORKSPACE"] = HOME
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,))[:500] if detail and not ok else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

# the sandbox runner is a stub: it records the call and answers, nothing executes
RUNS = []; ANSWER = {"rc": 0, "out": ""}
fake_exec = types.ModuleType("isolated_exec")
def fake_run(argv, scratch, **kw):
    RUNS.append(list(argv)); return subprocess.CompletedProcess(argv, ANSWER["rc"], ANSWER["out"], "boom" if ANSWER["rc"] else "")
fake_exec.run = fake_run
sys.modules["isolated_exec"] = fake_exec

MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
SF = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
FP = load("forge_practice", os.path.join(REPO, "scripts", "forge_practice.py"))
FB = load("forge_build", os.path.join(REPO, "scripts", "forge_build.py"))
for path in (SF.PROPOSALS, FP.STORE, FP.WANTS):
    assert os.path.commonpath([path, HOME]) == HOME, path
check("every store this suite writes is in a scratch workspace, and the sandbox runner is a stub",
      os.path.commonpath([FP.STORE, HOME]) == HOME and sys.modules["isolated_exec"] is fake_exec
      and FB.STAGING.startswith(HOME))

# an installed forged skill with a valid artifact
dest = os.path.join(HOME, "scripts", "forged", "SK-test0001", "rhyme_finder.py")
os.makedirs(os.path.dirname(dest)); open(dest, "w").write("def rhyme_finder(note):\n    return 'x'\n")
PROP = {"id": "SK-test0001", "state": "installed", "capability": "rhyme_finder",
        "why": "his poems kept stalling on a rhyme", "origin": {"want_id": "W-origin", "want": "finish the river poem"},
        "granted": {"scope": {}, "permissions": [], "invocation": "always"},
        "installed_to": dest, "verification": {"schema": 1, "review": "PASS", "sandbox_passed": True, "sha256": FB._digest(dest)},
        "history": []}
json.dump([PROP], open(SF.PROPOSALS, "w"))

OUT = "river shiver quiver giver deliver sliver liver forgiver and the rest of the rhymes for river"
WANT = {"id": "W-1", "want": "finish the river poem", "source": "latent_thread", "multistep": True,
        "steps": [{"capability": "rhyme_finder", "note": "find rhymes for river"},
                  {"capability": "write_poem", "note": "write the last stanza"}],
        "current_step_index": 0}
json.dump([WANT], open(FP.WANTS, "w"))

# --- the selection trace ---
sel = FP.selection(WANT, 0, "ordinary")
check("the trace names the want, its source, the step that reached for the tool and what the step said it was for",
      sel == {"chooser": "ordinary", "want_id": "W-1", "want": "finish the river poem", "source": "latent_thread",
              "step": 0, "step_note": "find rhymes for river", "planned": "rhyme_finder"}, sel)
check("a want a person routed by hand is a canary, whatever the caller says",
      FP.selection(dict(WANT, manually_routed=True), 0, "ordinary")["chooser"] == "canary")
check("a chooser nobody named is unattributed", FP.selection(None, None, "trust me")["chooser"] == "unattributed")

# --- an ordinary run through forge_build.invoke ---
ANSWER.update(rc=0, out=OUT)
got = FB.invoke("rhyme_finder", "rhymes for river please", asking=False, chooser="ordinary", want=WANT, step=0)
rows = FP.load()
check("his own run returns the output unchanged and leaves one ordinary receipt",
      got == OUT and len(rows) == 1 and rows[0]["chooser"] == "ordinary" and rows[0]["result"] == "ok"
      and rows[0]["proposal"] == "SK-test0001" and rows[0]["artifact_sha256"] == PROP["verification"]["sha256"], rows)
raw = open(FP.STORE).read()
check("the receipt keeps hashes and fingerprints, not what went in or came out",
      "rhymes for river please" not in raw and "shiver" not in raw
      and rows[0]["input_sha256"] == FP._sha("rhymes for river please") and rows[0]["output_sha256"] == FP._sha(OUT)
      and 0 < len(rows[0]["output_marks"]) <= FP.MARKS)

FB.invoke("rhyme_finder", "a canary note", asking=True)
FB.invoke("rhyme_finder", "nobody said who")
rows = FP.load()
check("her approve-this-use run is a canary, and a call that does not say is unattributed",
      [r["chooser"] for r in rows] == ["ordinary", "canary", "unattributed"], [r["chooser"] for r in rows])
src = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app's invoke button still asks with approve_this_use, so it lands as a canary",
      "forge_build.invoke,row[\"capability\"],str(body.get(\"note\", \"\"))[:4000],asking=True)" in src)

ANSWER.update(rc=1, out="")
try:
    FB.invoke("rhyme_finder", "this one breaks", chooser="ordinary", want=WANT, step=0); raised = False
except RuntimeError:
    raised = True
check("a run that fails still raises, and is recorded as a failed use", raised and FP.load()[-1]["result"] == "error"
      and FP.load()[-1]["error"] == "RuntimeError")
n = len(FP.load())
PROP2 = dict(PROP, granted={"scope": {}, "permissions": [], "invocation": "never"})
json.dump([PROP2], open(SF.PROPOSALS, "w"))
try:
    FB.invoke("rhyme_finder", "not allowed", chooser="ordinary"); refused = False
except PermissionError:
    refused = True
check("a run the grant refuses is not a use and leaves no receipt", refused and len(FP.load()) == n)
json.dump([PROP], open(SF.PROPOSALS, "w"))

# --- downstream: the output turning up later ---
first = FP.load()[0]
later = (datetime.now() + timedelta(minutes=5)).isoformat()
earlier = (datetime.now() - timedelta(days=1)).isoformat()
same_step = dict(WANT, step_history=[{"step": 0, "capability": "rhyme_finder", "findings": OUT, "note": "I found " + OUT,
                                      "completed_at": later}])
d = FP.downstream(first, wants=[same_step])
check("the step that called the tool is never its own downstream use (it writes its note from the output)",
      d["carried_into"] == [] and d["want_state"] == "standing", d)
carried = dict(WANT, step_history=same_step["step_history"] + [
    {"step": 1, "capability": "write_poem", "findings": "the stanza ends: " + OUT[:70], "completed_at": later}])
d = FP.downstream(first, wants=[carried])
check("a later step of the same want that carries the output counts", d["carried_into"] == [
    {"want_id": "W-1", "step": 1, "capability": "write_poem"}], d)
other_after = {"id": "W-2", "want": "a song", "step_history": [{"step": 0, "capability": "make_music",
               "findings": "lyrics: " + OUT, "completed_at": later}]}
other_before = {"id": "W-3", "want": "old", "step_history": [{"step": 0, "capability": "make_music",
                "findings": "lyrics: " + OUT, "completed_at": earlier}]}
d = FP.downstream(first, wants=[WANT, other_after, other_before])
check("another want's later step counts; one finished before the run cannot have used it",
      [c["want_id"] for c in d["carried_into"]] == ["W-2"], d)
check("unrelated text is not carried", FP.downstream(first, wants=[dict(WANT, step_history=[
    {"step": 1, "capability": "write_poem", "findings": "a stanza about the sea and nothing else at all", "completed_at": later}])])["carried_into"] == [])

ANSWER.update(rc=0, out="a second answer entirely different")
FB.invoke("rhyme_finder", "build on this: " + OUT, chooser="ordinary", want=WANT, step=1)
last = FP.load()[-1]
check("a later forged call whose input carries an earlier output names it, and the earlier one is reused_by it",
      first["id"] in (last.get("reuses") or []) and last["id"] in FP.downstream(first, wants=[])["reused_by"], last)

# --- the evidence, and that it changes nothing ---
ev = FP.evidence("rhyme_finder", wants=[carried])
check("evidence counts only his own choices; canaries and unattributed calls are shown apart",
      ev["ordinary"] == 3 and ev["ordinary_ok"] == 2 and ev["canary"] == 1 and ev["unattributed"] == 1, ev)
check("and says how many of his outputs were carried into what he did next", ev["carried"] == 1 and "carried" in ev["verdict"], ev)
check("it names the need the tool was built for, and where that want stands",
      ev["built_for"] == "finish the river poem" and ev["origin_want_state"] == "gone", ev)
check("the evidence never retires a tool", ev["retire"] is False)
check("reading the evidence changes no Forge card", open(SF.PROPOSALS).read() == json.dumps([PROP]))
txt = FP.report(ev)
check("the ten-minute read prints the counts and each use", "chosen in his own work: 3" in txt and "canary, not acceptance" in txt
      and first["id"] in txt, txt)

ev0 = FP.evidence("rhyme_finder", receipts=[r for r in FP.load() if r["chooser"] != "ordinary"], wants=[])
check("no ordinary use says so plainly, and says it is not evidence against the tool",
      ev0["ordinary"] == 0 and "not evidence against it" in ev0["verdict"] and ev0["retire"] is False, ev0)

psrc = open(os.path.join(REPO, "scripts", "forge_practice.py")).read()
check("the module cannot decide a card or remove a tool",
      not any(s in psrc for s in ("deny(", "approve(", "withdraw(", ".mark(", "DECIDED_FOR_GLORIA", "os.unlink", "os.remove")))

# --- the affordance example ---
canaries = [r for r in FP.load() if r["chooser"] != "ordinary"]
check("until he has chosen it himself, his inventory carries the need it was built for",
      FP.affordance("rhyme_finder", receipts=canaries) == "built for: finish the river poem")
check("once he has, the name is enough", FP.affordance("rhyme_finder") == "")
HI = load("his_inventory", os.path.join(REPO, "scripts", "his_inventory.py"))
open(FP.STORE, "w").write("".join(json.dumps(r) + "\n" for r in canaries))
check("his own prompts show the example; an outside email shows only the name",
      HI._installed_skills() == ["rhyme_finder (built for: finish the river poem)"]
      and HI._installed_skills(private=False) == ["rhyme_finder"], (HI._installed_skills(), HI._installed_skills(private=False)))

# --- the callers say whose choice it was, and the Forge's laws still hold ---
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
spine = open(os.path.join(REPO, "scripts", "want_spine.py")).read()
check("the want router's forged action is his own work, with the want and step",
      '_invoke_forged(_cap, note, asking=False, chooser="ordinary", want=_w, step=_s)' in router)
check("the step spine's forged step is his own work, with the want",
      'invoke(capability, text, asking=False, chooser="ordinary", want=want,' in spine)
check("and it is deployed", "forge_practice.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
json.dump([{"id": "SK-ext", "state": "proposed", "capability": "x", "asked": {"scope": {"execution": "unresolved_external_integration"}},
            "history": []}], open(SF.PROPOSALS, "w"))
check("approve() still refuses an unresolved external integration", SF.approve("SK-ext")[0] is None)
check("propose() still needs a live want", SF.propose("y", "why", "W-none", wants=[])[0] is None)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
