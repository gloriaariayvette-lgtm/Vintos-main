#!/usr/bin/env python3
"""The commissioned relay instruments can be called from his Lab turn, on demand, only on artifacts the Lab
really holds (2026-09-29: they were wired and receipted, but nothing in the Lab could reach them). Scratch
HOME; the relay runner is a stub; nothing reaches the network."""
import importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-instruments-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=no_network, call=no_network)
spec = importlib.util.spec_from_file_location("lab_instruments", os.path.join(REPO, "scripts", "lab_instruments.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("the Lab and its ledger are in the scratch workspace", str(L.LAB).startswith(HOME) and str(L.LEDGER).startswith(HOME))
menu = L.menu_block()
check("with no artifacts, only the sequence-free instrument is offered", "structure_viewer" not in menu and "sequence_viewer" not in menu and "biohub_esm" in menu, menu)
rel = L.save_fasta("WP_012345678.1", "MKT" * 40, 1, 120, "protein")
check("a sequence the Lab fetched is kept as a FASTA artifact", rel.endswith(".fasta") and (L.LAB / rel).read_text().startswith(">WP_012345678.1:1-120"), rel)
(L.ARTIFACTS / "structures").mkdir(parents=True, exist_ok=True)
(L.ARTIFACTS / "structures" / "1abc.pdb").write_text("ATOM\n")
menu = L.menu_block()
check("the menu names only artifacts the Lab really holds", "artifacts/structures/1abc.pdb" in menu and rel in menu, menu)
for bad, why in (({"skill": "adaptyv_bio", "operation": "estimate_cost", "files": [], "question": "how much would this cost"}, "Adaptyv is not offered"),
                 ({"skill": "structure_viewer", "operation": "structure.analyze", "files": ["../../etc/passwd"], "question": "what contacts are there"}, "an unlisted file"),
                 ({"skill": "structure_viewer", "operation": "structure.export", "files": ["artifacts/structures/1abc.pdb"], "question": "export this please"}, "an operation not offered"),
                 ({"skill": "sequence_viewer", "operation": "sequence.run_analysis", "files": [], "question": "find the open reading frames"}, "no artifact")):
    try: L.validate(bad); ok = False
    except ValueError: ok = True
    check("refused: " + why, ok)
calls = []
def runner(surface, skill, instruction, operation=None, input_files=None):
    calls.append((surface, skill, operation, input_files)); return {"receipt": {"receipt_id": "abc"}, "summary": "63 contacts", "files": ["/x/render.png"]}
out = L.run({"skill": "structure_viewer", "operation": "structure.analyze", "files": ["artifacts/structures/1abc.pdb"],
             "question": "which residues make the interface contacts"}, runner=runner)
check("an instrument runs on the Lab's own file, from the Lab surface, and returns a receipt the Lab records",
      calls and calls[0][0] == "lab" and calls[0][3] == [str(L.LAB / "artifacts/structures/1abc.pdb")]
      and out["receipt"]["records"][0]["summary"] == "63 contacts" and out["receipt"]["source"] == "instrument:structure_viewer", out)
for _ in range(2): L.run({"skill": "biohub_esm", "operation": "atlas.search", "files": [], "question": "near neighbours of P69905 in the atlas"}, runner=runner)
try: L.run({"skill": "biohub_esm", "operation": "atlas.search", "files": [], "question": "one more search please"}, runner=runner); capped = False
except PermissionError: capped = True
check("three runs a day at most, and the menu goes quiet", capped and L.menu_block() == "")
lab = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("his Lab turn can ask for one, and the sources phase runs it",
      '"instrument_query": (value.get("instrument_query")' in lab and "lab_instruments.run(sent_query)" in lab
      and "from lab_instruments import menu_block" in lab)
check("a fetched sequence is saved for the instruments", "lab_instruments.save_fasta(" in lab)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
