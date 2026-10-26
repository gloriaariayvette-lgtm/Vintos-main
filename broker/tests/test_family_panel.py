#!/usr/bin/env python3
"""A family question frozen first, then measured across instruments on readings he already had.

Scratch HOME, scratch workspace, scratch Lab: every path this suite touches is under a temporary directory
and is asserted to be. Nothing sends, nothing reaches the network, no model is loaded and nothing is folded:
the structures are written here by hand, `requests` and the plugin gateway raise, and sockets are closed off.
"""
import json, math, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-family-panel-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_ESMFOLD_PYTHON"] = os.path.join(HOME, "no-such-python")


def _no_network(*a, **k):
    raise AssertionError("a test must never reach the network")


def _no_socket(self, *a, **k):
    raise AssertionError("a test must never open a socket")


socket.socket.connect = _no_socket
sys.modules["requests"] = types.SimpleNamespace(get=_no_network, post=_no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=_no_network, call=_no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import lab_family_panel as F
import lab_instruments as L

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))


def refuses(name, call, kinds=(ValueError,)):
    try:
        call()
        check("refused: " + name, False, "it was allowed")
    except kinds as exc:
        check("refused: " + name, True, exc)
    except Exception as exc:                     # noqa: BLE001 - a wrong error type is a failure, not a pass
        check("refused: " + name, False, "%s: %s" % (type(exc).__name__, exc))


# ---------------------------------------------------------------- isolation
check("the Lab, the panel store and the result store are all in the scratch workspace",
      str(F.LAB).startswith(HOME) and str(F.PANELS).startswith(HOME) and str(F.PANEL_RESULTS).startswith(HOME),
      (F.LAB, F.PANELS, F.PANEL_RESULTS))
check("nothing in this suite can send or fetch",
      sys.modules["requests"].get is _no_network and sys.modules["plugin_gateway"].run_skill is _no_network)
check("the panel is the size the proposal set: three homologs and one comparator",
      F.FAMILY_SIZE == 3)

# ---------------------------------------------------------------- fixtures: retained structures, written by hand
AA = "ACDEFGHIKLMNPQRSTVWY"
THREE = {"A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY", "H": "HIS", "I": "ILE",
         "K": "LYS", "L": "LEU", "M": "MET", "N": "ASN", "P": "PRO", "Q": "GLN", "R": "ARG", "S": "SER",
         "T": "THR", "V": "VAL", "W": "TRP", "Y": "TYR"}
N = 60
ANCHOR_SEQ = "".join(AA[(i * 7) % 20] for i in range(N))


def mutate(seq, every):
    return "".join(AA[(AA.index(c) + 5) % 20] if i % every == 0 else c for i, c in enumerate(seq))


NEAR_SEQ = mutate(ANCHOR_SEQ, 10)        # ~90% identical to the anchor: a close homolog
FAR_SEQ = mutate(ANCHOR_SEQ, 3)          # ~67% identical: a relative, not a member


def helix(i):
    return (2.3 * math.cos(i * 1.75), 2.3 * math.sin(i * 1.75), 1.5 * i)


def write_pdb(rel, residues, low=()):
    """residues: [(number, one-letter)]. `low` numbers get a pLDDT of 55, everything else 92."""
    path = os.path.join(str(F.LAB), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        for serial, (number, aa) in enumerate(residues, 1):
            x, y, z = helix(serial)
            handle.write("ATOM  %5d  CA  %3s A%4d    %8.3f%8.3f%8.3f  1.00%6.2f           C\n"
                         % (serial, THREE[aa], number, x, y, z, 55.0 if number in set(low) else 92.0))
        handle.write("END\n")
    return rel


def numbered(seq, start=1):
    return [(start + i, aa) for i, aa in enumerate(seq)]


LOW = (20, 30)
A1 = write_pdb("artifacts/esmfold/P00001-aaaaaaaaaaaa.pdb", numbered(ANCHOR_SEQ), LOW)
A2 = write_pdb("artifacts/esmfold/P00002-bbbbbbbbbbbb.pdb", numbered(NEAR_SEQ), LOW)
# a member whose numbering is shifted by a three-residue extension: the panel must find the position by sequence
A3 = write_pdb("artifacts/esmfold/P00003-cccccccccccc.pdb", numbered("MGS" + NEAR_SEQ, 1), (23, 33))
COMP = write_pdb("artifacts/esmfold/P00004-dddddddddddd.pdb", numbered(FAR_SEQ), ())
CARRIER = write_pdb("artifacts/esmfold/P00007-eeeeeeeeeeee.pdb", numbered(FAR_SEQ), LOW)
# a member with five residues missing across one of the positions, its own numbering left as deposited
GAPPED = write_pdb("artifacts/esmfold/P00006-ffffffffffff.pdb",
                   [(n, aa) for n, aa in numbered(NEAR_SEQ) if not 28 <= n <= 32], (20,))
OBSERVED = write_pdb("artifacts/reference/9XYZ.pdb", numbered(FAR_SEQ), ())

two_chain = os.path.join(str(F.LAB), "artifacts/esmfold/P00009-999999999999.pdb")
open(two_chain, "w").write(open(os.path.join(str(F.LAB), A1)).read().replace("END\n", "")
                           + "ATOM      1  CA  ALA B   1       0.000   0.000   0.000  1.00 92.00           C\nEND\n")

# ---------------------------------------------------------------- what a member may be read from
check("an accession resolves to the newest ESMFold model the Lab retained",
      F.member_structure("P00001") == A1, F.member_structure("P00001"))
refuses("a member the Lab has no retained structure of (folding it is a separate run to commission)",
        lambda: F.member_structure("Q99999"))
refuses("a member given as a path outside the Lab's artifacts",
        lambda: F.member_structure("../../../etc/passwd.pdb"))
refuses("a structure holding more than one chain, so chains cannot be mixed",
        lambda: F.read_member("artifacts/esmfold/P00009-999999999999.pdb"))

read = F.read_member(A1)
check("one member's readings are two instruments' readings on one residue index, kept apart",
      read["residues"][19]["number"] == 20 and read["residues"][19]["confidence"] == 55.0
      and read["residues"][19]["secondary_structure"] == "H"
      and read["residues"][40]["confidence"] == 92.0
      and set(read["residues"][0]) == {"number", "amino_acid", "confidence", "secondary_structure"},
      read["residues"][19])
check("a retained ESMFold model is a prediction and the reference entry is an observed structure",
      read["kind"] == "prediction" and F.read_member(OBSERVED)["kind"] == "observed")

# ---------------------------------------------------------------- the frozen question
QUESTION = "does the low-confidence helical position hold across these three homologs and go missing in the relative"
BASE = {"question": QUESTION, "family": ["P00001", "P00002", "P00003"], "comparator": "P00004",
        "anchor": "P00001", "positions": list(LOW),
        "feature": [{"reading": "confidence", "below": 70}, {"reading": "secondary_structure", "is": "H"}]}

refuses("a panel of two members", lambda: F.declare(dict(BASE, family=["P00001", "P00002"]), today="2026-10-26"))
refuses("the same protein twice in the family",
        lambda: F.declare(dict(BASE, family=["P00001", "P00001", "P00002"]), today="2026-10-26"))
refuses("a comparator that is also a family member",
        lambda: F.declare(dict(BASE, comparator="P00002"), today="2026-10-26"))
refuses("an anchor that is not in the family", lambda: F.declare(dict(BASE, anchor="P00004"), today="2026-10-26"))
refuses("a panel with no question to answer", lambda: F.declare(dict(BASE, question="why"), today="2026-10-26"))
refuses("more positions than a small panel measures",
        lambda: F.declare(dict(BASE, positions=list(range(1, F.MAX_POSITIONS + 2))), today="2026-10-26"))
refuses("a feature clause on a reading no instrument here produces",
        lambda: F.declare(dict(BASE, feature=[{"reading": "binding_affinity", "below": 1}]), today="2026-10-26"))
refuses("a confidence clause with both bounds",
        lambda: F.declare(dict(BASE, feature=[{"reading": "confidence", "below": 70, "above": 50}]),
                          today="2026-10-26"))
refuses("a confidence clause read off an observed structure's temperature factor",
        lambda: F.declare(dict(BASE, comparator="artifacts/reference/9XYZ.pdb"), today="2026-10-26"))

panel = F.declare(BASE, today="2026-10-26")
check("the question, the members and every artifact digest are frozen in one record",
      F.PANEL_ID.fullmatch(panel["panel_id"]) and panel["question"] == QUESTION
      and [m["structure"] for m in panel["members"]] == [A1, A2, A3, COMP]
      and all(len(m["sha256"]) == 64 for m in panel["members"])
      and [m["role"] for m in panel["members"]] == ["family", "family", "family", "comparator"], panel)
check("what would support it and what would oppose it are written down before it is measured",
      "all 3 family members" in panel["supports"] and "not family-specific" in panel["opposes"]
      and panel["truth_status"].startswith("a cross-protein comparison"), panel)
check("declaring the same question again returns the same panel, not a second one",
      F.declare(BASE, today="2026-10-26")["panel_id"] == panel["panel_id"] and len(F.panels()) == 1)

# ---------------------------------------------------------------- the measurement: a feature that persists
out = F.evaluate(panel["panel_id"])["result"]
check("the family carries the feature at both positions and the comparator carries it at neither",
      out["measurement_state"] == "supported"
      and [p["state"] for p in out["positions"]] == ["persists", "persists"], out["display"])
shifted = next(m for m in out["positions"][1]["members"] if m["name"] == "P00003")
check("a member whose numbering is shifted is read at its own residue, found by sequence not by number",
      shifted["mapped_position"] == 33 and shifted["feature"] is True, shifted)
comparator = next(m for m in out["positions"][0]["members"] if m["role"] == "comparator")
check("the comparator's readings are reported, not just its verdict",
      comparator["readings"]["confidence"] == 92.0 and comparator["readings"]["secondary_structure"] == "H"
      and comparator["feature"] is False, comparator)
check("alignment uncertainty is kept with the result: identity, aligned share and the window at each position",
      0.6 < out["identity_to_anchor"]["P00004"] < 0.8 and out["identity_to_anchor"]["P00002"] > 0.85
      and all(m["correspondence"]["aligned_fraction"] >= F.MIN_ALIGNED for m in out["members"])
      and all(a["correspondence"]["window"] == [p["position"] - F.WINDOW, p["position"] + F.WINDOW]
              for p in out["positions"] for a in p["members"] if a["name"] != "P00001"),
      out["identity_to_anchor"])
check("the readings stay two readings on one residue and are never fused into one vector",
      "never fused" in out["method"] and set(out["positions"][0]["members"][0]["readings"]) == set(F.READINGS))
check("the result names every member as prediction or observed",
      {m["kind"] for m in out["members"]} == {"prediction"} and all(m["chain"] == "A" for m in out["members"]))
check("the display says plainly what the comparison is not",
      any("no claim about function, stability or flexibility" in line for line in out["display"]), out["display"])
check("the measurement is kept whichever way it came out",
      F.results(panel["panel_id"])[-1]["measurement_state"] == "supported"
      and "display" not in F.results(panel["panel_id"])[-1])

# ---------------------------------------------------------------- a position no alignment places is undecidable
gapped = F.declare(dict(BASE, family=["P00001", "P00002", "P00006"]), today="2026-10-26")
out_gap = F.evaluate(gapped["panel_id"])["result"]
missing = next(m for m in out_gap["positions"][1]["members"] if m["name"] == "P00006")
check("a residue missing from a member makes that position undecidable, never 'the feature is absent'",
      out_gap["measurement_state"] == "inconclusive"
      and [p["state"] for p in out_gap["positions"]] == ["persists", "inconclusive"]
      and missing["mapped_position"] is None and missing["feature"] is None
      and missing["correspondence"]["decidable"] is False, out_gap["display"])
check("the display says undecidable rather than absent",
      any("undecidable, not absent" in line for line in out_gap["display"]))

refuses("a third panel on the same day", lambda: F.declare(dict(BASE, positions=[25]), today="2026-10-26"),
        kinds=(PermissionError,))

# ---------------------------------------------------------------- a comparator that carries it too is a refutation
carrier = F.declare(dict(BASE, comparator="P00007"), today="2026-10-27")
out_carrier = F.evaluate(carrier["panel_id"])["result"]
check("the feature in the comparator refutes the family-level question and is kept",
      out_carrier["measurement_state"] == "refuted"
      and set(p["state"] for p in out_carrier["positions"]) == {"not_family_specific"}
      and F.results(carrier["panel_id"])[-1]["measurement_state"] == "refuted", out_carrier["display"])

observed = F.declare({"question": QUESTION, "family": ["P00001", "P00002", "P00003"], "anchor": "P00001",
                      "comparator": "artifacts/reference/9XYZ.pdb", "positions": [20],
                      "feature": [{"reading": "secondary_structure", "is": "H"}]}, today="2026-10-27")
out_observed = F.evaluate(observed["panel_id"])["result"]
check("mixing a predicted and an observed structure is allowed but said out loud",
      out_observed["measurement_state"] == "refuted"
      and any("predicted and observed" in w for w in out_observed["warnings"])
      and any(m["kind"] == "observed" for m in out_observed["members"]), out_observed["warnings"])

# ---------------------------------------------------------------- a member closer than the family is called out
odd = F.declare({"question": QUESTION, "family": ["P00001", "P00004", "P00007"], "anchor": "P00001",
                 "comparator": "P00002", "positions": [20],
                 "feature": [{"reading": "secondary_structure", "is": "H"}]}, today="2026-10-28")
out_odd = F.evaluate(odd["panel_id"])["result"]
check("a comparator closer to the anchor than the family is is reported, not compared silently",
      any("not comparing a family against an outsider" in w for w in out_odd["warnings"]), out_odd["warnings"])

# ---------------------------------------------------------------- a structure that changed is not re-measured
open(os.path.join(str(F.LAB), COMP), "a").write("REMARK  touched after the panel was declared\n")
refuses("measuring a frozen question against a structure that changed underneath it",
        lambda: F.evaluate(panel["panel_id"]))
check("a panel whose artifacts no longer match is not offered to him",
      panel["panel_id"] not in [p["panel_id"] for p in F.ready()]
      and carrier["panel_id"] in [p["panel_id"] for p in F.ready()])
refuses("evaluating a panel that was never declared", lambda: F.evaluate("FAM-0000000000"))

# ---------------------------------------------------------------- the door he reaches it through
menu = L.menu_block()
check("the panel is offered once it is declared and readable, and says what it does not claim",
      "family_panel" in menu and carrier["panel_id"] in menu and "undecidable, not absent" in menu
      and "nothing about function, stability or flexibility" in menu, menu)
run = L.run({"skill": "family_panel", "operation": "structure.compare_family", "files": [],
             "panel": carrier["panel_id"], "question": "does this feature hold across the family or not"})
record = run["receipt"]["records"][0]
check("the Lab runs it on his own retained artifacts and records a receipt",
      run["receipt"]["source"] == "instrument:family_panel" and "refuted" in record["summary"]
      and carrier["panel_id"] in record["summary"], record)
refuses("an operation this instrument does not offer",
        lambda: L.validate({"skill": "family_panel", "operation": "structure.compare",
                            "files": [], "question": "compare this family for me"}))

# ---------------------------------------------------------------- it reaches Aegis only if the deploy names it
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy manifest names the panel", "lab_family_panel.py" in deploy)
check("nothing here asked for a fold, a model or a paid request",
      "esmfold.fold" not in open(os.path.join(REPO, "scripts", "lab_family_panel.py")).read()
      and "urllib" not in open(os.path.join(REPO, "scripts", "lab_family_panel.py")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
