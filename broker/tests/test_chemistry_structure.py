#!/usr/bin/env python3
"""Structure artifacts become bounded view data. Scratch HOME; no model, network, or sender."""
import gzip
import importlib.util
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
HOME = pathlib.Path(tempfile.mkdtemp(prefix="vintos-chem-structure-"))
WS = HOME / ".vintos" / "workspace"
ART = WS / "memory" / "chemistry-lab" / "artifacts"
ART.mkdir(parents=True)
os.environ["HOME"] = str(HOME); os.environ["SPARK_WORKSPACE"] = str(WS)

spec = importlib.util.spec_from_file_location("chemistry_structure_test", REPO / "scripts" / "chemistry_structure.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:180]) if detail and not ok else ""))

check("test is isolated from the live Lab", str(M.ROOT).startswith(str(HOME.resolve())) and "/home/gloria" not in str(M.ROOT), M.ROOT)

pdb = ("ATOM      1  N   MET A   1      11.104  13.207   9.317  1.00 20.00           N  \n"
       "ATOM      2  CA  MET A   1      12.560  13.300   9.500  1.00 20.00           C  \n"
       "ATOM      3  C   MET A   1      13.100  12.000  10.100  1.00 20.00           C  \n")
(ART / "fold.pdb").write_text(pdb)
cif = """data_x
#
loop_
_atom_site.group_PDB
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM C CA ALA A 1 1.0 2.0 3.0
ATOM N N ALA A 1 2.0 3.0 4.0
#
"""
with gzip.open(ART / "made.cif.gz", "wt") as handle: handle.write(cif)
(ART / "ignore.npy").write_bytes(b"not a structure")
outside = HOME / "outside.pdb"; outside.write_text(pdb)
try: (ART / "escape.pdb").symlink_to(outside)
except OSError: pass

rows = M.inventory(1000)
check("only bounded PDB and mmCIF artifacts are listed", len(rows) == 2 and {r["kind"] for r in rows} == {"pdb", "mmcif"}, rows)
check("inventory exposes opaque ids and relative provenance, never absolute paths",
      all(len(r["artifact_id"]) == 20 and not r["source"].startswith("/") for r in rows), rows)
check("computational provenance is explicit", all("not_biological_fact" in r["truth_status"] for r in rows))

by_kind = {r["kind"]: r for r in rows}
p = M.structure(by_kind["pdb"]["artifact_id"]); c = M.structure(by_kind["mmcif"]["artifact_id"])
check("PDB coordinates parse into finite display atoms", p["ok"] and p["atom_count"] == 3 and p["atoms"][1]["name"] == "CA", p)
check("gzipped RFD3-style mmCIF coordinates parse", c["ok"] and c["atom_count"] == 2 and c["atoms"][0]["element"] == "C", c)
check("view rows remain computational claims", "not_biological_fact" in c["truth_status"], c)
check("unknown ids cannot become arbitrary paths", M.structure("../../outside.pdb")["ok"] is False)

source = (REPO / "scripts" / "chemistry_structure.py").read_text()
check("module has no network or write surface", "requests" not in source and "httpx" not in source and not any(x in source for x in ("_atomic(", "_append(", "deliver(")))
check("atom and byte bounds are code-level", "MAX_ATOMS" in source and "MAX_TEXT_BYTES" in source and "MAX_COMPRESSED_BYTES" in source)

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
