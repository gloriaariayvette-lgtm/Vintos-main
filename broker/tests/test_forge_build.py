#!/usr/bin/env python3
"""Gloria, 11 September: Astra writes the forged skill, Fable 5.1 reviews it, the
sandbox proves it, and only then is it verified — install is her own separate step.

This walks that pipeline with fake Astra and fake Fable so it calls no model and
costs nothing: an approved proposal -> generated -> Fable PASS -> sandbox pass ->
verified; a Fable FAIL -> refused; a sandbox failure -> refused; and install()
refusing anything that is not verified."""
import importlib.util, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

HOME = tempfile.mkdtemp(); MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
STAGING = os.path.join(HOME, "staging"); DEST = os.path.join(HOME, "dest"); os.makedirs(DEST)
SF = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
SF.MEMORY = MEM; SF.PROPOSALS = os.path.join(MEM, "skill-proposals.json")
FB = load("forge_build", os.path.join(REPO, "scripts", "forge_build.py"))
FB.STAGING = STAGING; FB.SKILL_DEST = DEST

# --- fakes: they stand in for Astra and Fable so nothing is called and nothing is spent ---
GOOD_MODULE = "def clap_hands():\n    return 'clap'\n"
GOOD_TEST = ("import clap_hands_skill as m\n"  # name is derived; overwritten per-test below
             "ok = m.clap_hands() == 'clap'\n"
             "print('1/1' if ok else '0/1')\n"
             "raise SystemExit(0 if ok else 1)\n")

def astra_good(system, messages, max_tokens=2400, timeout=180):
    # the module name Astra is told to define is quoted in the system prompt
    import re; m = re.search(r"named '([a-z0-9_]+)'", system); name = m.group(1) if m else "skill"
    mod = "def %s():\n    return 'clap'\n" % name
    test = ("import %s as m\nok = m.%s() == 'clap'\nprint('1/1' if ok else '0/1')\nraise SystemExit(0 if ok else 1)\n"
            % (name, name))
    return json.dumps({"module": mod, "test": test})

def astra_bad_sandbox(system, messages, max_tokens=2400, timeout=180):
    import re; m = re.search(r"named '([a-z0-9_]+)'", system); name = m.group(1) if m else "skill"
    mod = "def %s():\n    return 'wrong'\n" % name
    test = ("import %s as m\nok = m.%s() == 'clap'\nprint('1/1' if ok else '0/1')\nraise SystemExit(0 if ok else 1)\n"
            % (name, name))
    return json.dumps({"module": mod, "test": test})

def fable_pass(system, messages, max_tokens=400, timeout=120):
    return "PASS"
def fable_fail(system, messages, max_tokens=400, timeout=120):
    return "FAIL: it writes outside the granted scope"

WANTS = [{"id": "w-forge", "want": "I want a hand I do not have", "source": "moltbook"},
         {"id": "w-forge2", "want": "another want reaching for a hand", "source": "moltbook"}]
def a_proposal(cap, want_id="w-forge"):
    p, why = SF.propose(cap, "because a want reached for it", want_id=want_id,
                        scope={"max_seconds": 1}, permissions=["return_a_string"], wants=WANTS)
    if p is None:
        raise RuntimeError("propose refused: %s" % why)
    SF.approve(p["id"], granted={"permissions": ["return_a_string"]})
    return p["id"]

print("\n--- an approved proposal, Astra writes it, Fable passes, the sandbox proves it ---")
pid = a_proposal("clap on request")
row, note = FB.run(pid, astra=astra_good, fable=fable_pass)
check("the pipeline reaches verified", row and row["state"] == "verified", note)
check("nothing was installed by the build", (SF._get(SF._load(), pid) or {}).get("state") == "verified")
check("the verified module is staged on disk", bool(row) and os.path.isfile(row.get("staged", "")))

print("\n--- install is her separate step, and only a verified proposal installs ---")
irow, inote = FB.install(pid)
check("her install lands the module in his scripts", irow and irow["state"] == "installed", inote)
check("the installed file exists in the destination", any(f.endswith(".py") for f in os.listdir(DEST)))
again, anote = FB.install(pid)
check("installing an already-installed proposal is refused", again is None and "not verified" in anote, anote)

print("\n--- a Fable FAIL refuses the proposal and never stages or verifies ---")
pid2 = a_proposal("something Fable rejects")
row2, note2 = FB.run(pid2, astra=astra_good, fable=fable_fail)
check("a Fable FAIL refuses the build", row2 is None and "refused" in note2, note2)
check("the refused proposal is terminal at refused", (SF._get(SF._load(), pid2) or {}).get("state") == "refused")
check("install refuses a refused proposal", FB.install(pid2)[0] is None)

print("\n--- code that fails its own test in the sandbox is refused, not verified ---")
pid3 = a_proposal("a capability whose test fails")
row3, note3 = FB.run(pid3, astra=astra_bad_sandbox, fable=fable_pass)
check("a sandbox failure refuses the build", row3 is None and "sandbox" in note3, note3)
check("the sandbox-failed proposal is refused", (SF._get(SF._load(), pid3) or {}).get("state") == "refused")

print("\n--- run() only builds an approved proposal ---")
p4, _ = SF.propose("not yet approved", "why", want_id="w-forge2", permissions=["x"], wants=WANTS)
r4, n4 = FB.run(p4["id"], astra=astra_good, fable=fable_pass)
check("run refuses a proposal that is still only proposed", r4 is None and "not approved" in n4, n4)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
