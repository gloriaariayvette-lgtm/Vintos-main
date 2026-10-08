#!/usr/bin/env python3
"""A domain of a long protein is folded for real, numbered as the protein; the toy lattice never answers for a real
protein (Gloria, 2026-10-08: "Why is he still using the toy lattice?"). Replayed from 7 October 21:26: the plan was
experiment "fold" with {"protein_name": "ADGRG6", "region": "41-149", "target_accession": "Q86SQ4"}; the bench
answered with its 8-bead demo "HPHPPHHP". UniProt, ESMFold and the Mac bench are stubs that record what they were
given; nothing leaves this process."""
import os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="fold-region-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_mac as M
import chemistry_esmfold as E
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

AA = "ACDEFGHIKLMNPQRSTVWY"
CHAIN = "".join(AA[(i * 7 + i // 3) % 20] for i in range(1221))        # Q86SQ4 is about 1221 residues
CUB = "CRVVLSNPSGTFTSPCYPNDYPNSQACMWTLRAPTGYIIQITFNDFDIEEAPNCIYDSLSLDNGESQTKFCGATAKGLSFNSSANEMHVSFSSDFSIQKKGFNASYIRV"
CHAIN = CHAIN[:40] + CUB + CHAIN[149:]
assert len(CUB) == 109 and CHAIN[40:149] == CUB
RECORD = {"primaryAccession": "Q86SQ4", "uniProtkbId": "AGRG6_HUMAN", "sequence": {"value": CHAIN, "length": 1221},
          "genes": [{"geneName": {"value": "ADGRG6"}}],
          "proteinDescription": {"recommendedName": {"fullName": {"value": "Adhesion G-protein coupled receptor G6"}}}}
resolver = lambda acc: (RECORD, {"provider": "UniProtKB", "accession": acc, "receipt_id": "REC-UNI"})
MAC, FOLDED = [], []
def mac(body):
    MAC.append(body)
    return {"ok": True, "run": {"result": {"title": "HP lattice HPHPPHHP", "modeled_sequence": "HPHPPHHP"}}}
def worker(body):
    FOLDED.append(body); seq = body["sequence"]
    return {"ok": True, "result": {"title": "Folding %s (%d aa): %s" % (body["accession"], len(seq), seq),
                                   "requested_accession": body["accession"], "modeled_sequence": seq,
                                   "modeled_sequence_length": len(seq), "sequence_source": body["sequence_source"],
                                   "hp_mapping": body["hp_mapping"], "mean_plddt": 82.0}}

PLAN = {"protein_name": "ADGRG6", "region": "41-149", "region_label": "CUB domain",
        "sequence_source": "interpro Q86SQ4 feature slice, residues 41-149", "target_accession": "Q86SQ4"}
out = M.run("fold", dict(PLAN), resolver=resolver, transport=mac, esmfold_worker=worker)
check("7 Oct replayed: 'fold' with an accession is folded for real; the Mac's toy is never asked", not MAC and FOLDED, (MAC, out))
check("the CUB slice, residues 41-149 of the sourced chain (109 aa), is what folds",
      FOLDED and FOLDED[0]["sequence"] == CUB and FOLDED[0]["sequence_source"]["region"] == [41, 149]
      and FOLDED[0]["sequence_source"]["full_length"] == 1221, FOLDED and FOLDED[0]["sequence_source"])
check("the identity check passes on that slice, and the result carries it", out.get("ok")
      and out["sequence_check"]["outcome"] == "SEQUENCE_ACCESSION_MATCH" and out["sequence_check"]["modeled_sequence_length"] == 109
      and out["sequence_request"]["region"] == [41, 149], out.get("error") or out.get("sequence_check"))
for shape in ("41–149", "residues 41 to 149", [41, 149]):
    FOLDED.clear()
    M.run("protein", dict(PLAN, region=shape), resolver=resolver, transport=mac, esmfold_worker=worker)
    check("a region written as %r is read the same" % (shape,), FOLDED and FOLDED[0]["sequence"] == CUB)
out = M.run("protein", {"protein_name": "ADGRG6", "target_accession": "Q86SQ4"}, resolver=resolver, transport=mac, esmfold_worker=worker)
check("the whole 1221-residue chain is refused before folding, asking for a region (this morning's failure)",
      out.get("refused") == "chain_too_long" and "Name a region" in out.get("error", ""), out)
out = M.run("protein", dict(PLAN, region="1200-1300"), resolver=resolver, transport=mac, esmfold_worker=worker)
check("a region past the chain's end is refused with the accession and range", out.get("refused") == "region_out_of_range"
      and "Q86SQ4" in out["error"] and "1200-1300" in out["error"], out)
out = M.run("protein", dict(PLAN, region="149-41"), resolver=resolver, transport=mac, esmfold_worker=worker)
check("a backward region is refused", out.get("refused") == "region_unreadable", out)
MAC.clear()
out = M.run("fold", {"protein_name": "ADGRG6", "region": "41-149"}, resolver=resolver, transport=mac, esmfold_worker=worker)
check("'fold' naming a protein or region without an accession is refused, not answered by the toy",
      out.get("refused") == "not_a_toy_fold" and not MAC, (out, MAC))
M.run("fold", {"sequence": "HPHPPHHP"}, transport=mac)
check("the toy lattice still runs when it is asked for as a toy", len(MAC) == 1)

pdb = "".join("ATOM  %5d  CA  ALA A%4d    %8.3f%8.3f%8.3f  1.00 80.00           C\n" % (i, i, i, 0.0, 0.0) for i in range(1, 110))
moved = E.renumber(pdb, E.first_residue({"region": [41, 149]}))
nums = [int(l[22:26]) for l in moved.splitlines() if l.startswith("ATOM")]
check("the folded slice is numbered as the protein: 41-149, not 1-109", nums[0] == 41 and nums[-1] == 149 and len(nums) == 109, nums[:3])
check("a whole chain keeps its numbering", E.renumber(pdb, E.first_residue({})) == pdb)
src = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the planner is told how to ask for a region, and that fold is a toy", "parameters.region" in src
      and "toy lattice of a few beads" in src)
check("mean pLDDT is the per-residue mean, not the 37-atom-slot mean (8 Oct: 80.97 against 94.0)",
      E.per_residue_mean({"plddt_by_residue": [90.0, 94.0, 98.0]}, 80.97) == 94.0
      and E.per_residue_mean({"error": "unreadable"}, 80.97) == 80.97
      and '"mean_plddt_all_atom_slots": all_slots' in open(E.__file__).read())
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
