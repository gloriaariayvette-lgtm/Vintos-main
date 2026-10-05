#!/usr/bin/env python3
"""A protein he looks up reaches his review whole (Gloria, 2026-10-05: "Do we know why what he searched for was
truncated"). SLC26A6 (Q9BXS9, 759 residues) read as truncated twice over: the Lab kept only the first 350 residues of
a browsed record, and the review read json.dumps(observations)[:14000], whose cut fell inside the UniProt sequence.

Scratch HOME; UniProt is a stub that answers from this file; every socket is refused.
"""
import io, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-sequence-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
sys.modules["lab_http"] = types.SimpleNamespace(open_request=lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))

import chemistry_lab as M

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("the Lab's store is a scratch one", M.ROOT.startswith(HOME), M.ROOT)

SEQ = ("MDLRRRDYHMERPLLNQEHLEELGRWGSAPRTHQWRTWLQCSRARAYALLLQHLPVLVWLPRYPVRDWLLGDLLSGLSVAI" * 10)[:759]
def uniprot_row(acc, seq):
    return {"primaryAccession": acc, "uniProtkbId": acc + "_HUMAN",
            "proteinDescription": {"recommendedName": {"fullName": {"value": "Solute carrier family 26 member 6"}}},
            "organism": {"scientificName": "Homo sapiens"}, "sequence": {"value": seq, "length": len(seq)},
            "comments": [{"commentType": "FUNCTION", "texts": [{"value": "Apical membrane anion exchanger. " * 20}]}],
            "uniProtKBCrossReferences": []}

class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
ROWS = [uniprot_row("Q9BXS9", SEQ)]
M.urllib.request.urlopen = lambda req, timeout=None: Resp(json.dumps({"results": ROWS}).encode())

got = M._browse("reviewed:true AND gene:SLC26A6", 1)
rec = got["records"][0]
check("a browsed 759-residue protein keeps all 759 residues", len(rec["sequence"]) == 759 and rec["sequence"] == SEQ
      and rec["length"] == 759 and "sequence_shown" not in rec, len(rec["sequence"]))
ROWS[:] = [uniprot_row("Q8WXI7", "A" * 6000)]
huge = M._browse("reviewed:true AND gene:MUC16", 1)["records"][0]
check("a protein longer than the Lab keeps says how much of it is shown",
      len(huge["sequence"]) == M.SEQUENCE_KEPT and huge["sequence_shown"] == "first %d residues" % M.SEQUENCE_KEPT)
ESMC = open(os.path.join(REPO, "scripts", "chemistry_esmc.py")).read()     # read, not imported: it needs torch
check("ESM-C still trims its own copy to the 350 residues it can read", "MAX_LENGTH = 350" in ESMC and "[:MAX_LENGTH]" in ESMC)

# --- what the review reads ------------------------------------------------------------------------------------------
raw = uniprot_row("Q9BXS9", SEQ)
raw["references"] = [{"citation": {"title": "A paper about anion exchange " * 6, "authors": ["A B"] * 12}}] * 30
payload = {"records": [{"accession": "Q9BXS9", "function": "Apical membrane anion exchanger. " * 36}] * 8,
           "esmc_receipts": [{"accession": "Q9BXS9", "embedding_head": [0.1234567] * 300}],
           "additional_source": {"receipt": {"source": "uniprot", "records": [raw]}},
           "LITERATURE": [{"pmid": "23833257", "abstract": "The STAS domain of SLC26A6 binds the first intracellular "
                                                         "loop of SLC13A3. " * 30}] * 4}
old = json.dumps(payload)[:14000]
check("the old cut fell inside the sequence (how he saw a whole record as truncated)",
      len(json.dumps(payload)) > 14000 and SEQ not in old)
shown = M.observed(payload)
check("the review now reads the sequence whole", SEQ in shown, len(shown))
check("... within its budget, as whole JSON", len(shown) <= M.OBSERVED and json.loads(shown)["LITERATURE"][0]["pmid"] == "23833257")
check("... and says what it shortened", "...[shortened]" in shown and "more items not shown" in shown)
small = {"records": [{"accession": "P1", "sequence": "MKV" * 20}]}
check("observations that fit are passed exactly as they were", M.observed(small) == json.dumps(small, ensure_ascii=False))
crowded = {"records": [{"accession": "P%d" % n, "sequence": "MKVL" * 1250} for n in range(3)]}
end = M.observed(crowded)
check("if it still cannot fit, it says the excerpt ends there and the records are complete",
      "EXCERPT ENDS HERE" in end and "do not report them as truncated" in end)
check("the review uses it", "observed(records)" in open(M.__file__).read() and "json.dumps(records)[:14000]" not in
      open(M.__file__).read().split("def _reflect(", 1)[1].split("def _reflect_genome", 1)[0])

check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
