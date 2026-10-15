#!/usr/bin/env python3
"""A structural question reads the deposited entries its records name, beside the source he chose (15 October).

39 of 77 questions after the 07:59 deploy ended partially supported, nearly all asking for a fold, helical
arrangements, hinge regions, loops or residue positions: things UniProt annotation does not hold and the PDB entries
his own records named do. The structure was opened only when he chose no other source, and only for one record.

Isolation: scratch HOME and workspace; the Lab's network door (lab_http) refuses; the PDB read is a stub that records
what it was asked; the embedder, the reading settler, admission and the review are stubs. No model, no network."""
import contextlib, importlib.util, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="lab-structure-reads-"); WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no_network(*a, **k): NET.append(a[:1]); raise AssertionError("this suite must never reach the network")
sys.modules["lab_http"] = types.SimpleNamespace(open_request=_no_network)
@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
sys.modules["chemistry_reading"] = types.SimpleNamespace(settle_one=lambda **k: None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); sys.modules["chemistry_lab"] = M; spec.loader.exec_module(M)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

ASKED = []
REPLY = {"mode": "ok"}
def pdb_stub(spec, question="", **k):
    ASKED.append(spec)
    if REPLY["mode"] == "cooldown": raise RuntimeError("source_cooldown_active")
    if REPLY["mode"] == "down": raise RuntimeError("PDB unreachable")
    return {"receipt": {"receipt_id": "rcpt-" + spec["entry_id"], "source": "pdb", "records": [{
        "entry_id": spec["entry_id"], "title": "Crystal structure of the STAS domain",
        "experimental_methods": ["X-RAY DIFFRACTION"], "resolution_angstroms": [2.1],
        "numbering": "PDB author residue numbering; not asserted to match UniProt",
        "geometry": {"method": "first deposited model", "chains": [{"chain": "A", "observed_residues": 180,
                     "author_residue_min": 535, "author_residue_max": 729}],
                     "inter_chain_contacts": [{"chains": ["A", "B"], "ca_pair_count": 12, "closest_pairs": [
                         {"chain_1": "A", "residue_1": 600, "chain_2": "B", "residue_2": 610, "ca_distance_angstroms": 5.2}]}]},
        "metal_sites": [], "secondary_structure_records": [
            "HELIX    1 AA1 SER A  560  LEU A  575  1                                  16"]}]}}
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=pdb_stub)
check("isolated: scratch Lab store, refusing network, stubbed PDB read",
      M.ROOT.startswith(HOME) and sys.modules["lab_http"].open_request is _no_network
      and sys.modules["chemistry_sources"].query is pdb_stub)

Q = ("What are the specific structural features of the human SLC26A4 (Pendrin) and SLC26A5 (Prestin) STAS domains, "
     "and how do their helical arrangements and hinge regions differ?")
def g(name): return [{"geneName": {"value": name}}]
recs = [{"accession": "Q9BXS9", "pdb_ids": ["1ABC"], "genes": g("SLC26A6")},
        {"accession": "O43511", "pdb_ids": ["7WK1", "7WL2"], "genes": g("SLC26A4")},
        {"accession": "P58743", "pdb_ids": ["7S8X"], "genes": g("SLC26A5")}]
lit = {"source": "pubmed", "terms": ["pendrin prestin STAS"]}
got = M.structure_reads({"question": Q, "source_query": lit}, recs)
check("a comparison reads one entry for each target the question names, ahead of a search's extra hit, beside his literature choice",
      [g["entry_id"] for g in got] == ["7WK1", "7S8X"] and [g["for_accession"] for g in got] == ["O43511", "P58743"], got)
check("a question that is not about structure reads none",
      M.structure_reads({"question": "What is the sequence length of human SLC26A4?"}, recs) == [])
check("the microbiology lane reads none",
      M.structure_reads({"question": Q, "browse_lane": "microbiology"}, recs) == [])
check("an entry he already chose is not read twice",
      [g["entry_id"] for g in M.structure_reads({"question": Q, "source_query": {"source": "pdb", "entry_id": "7WK1"}}, recs)]
      == ["7S8X"])
check("only entries the records name are read", M.structure_reads({"question": Q}, [{"accession": "X", "pdb_ids": []}]) == [])

print("--- the real step, from embed ---")
M._ensure(); json.dump({"enabled": True}, open(M.CONFIG, "w")); M.set_enabled(True)
EMBEDDED, SEEN = [], []
M._embed_records = lambda records: EMBEDDED.append(records) or {"ok": True, "model": "t", "device": "t", "embeddings": []}
M._gather_material = lambda state, inquiry, fresh_only=False: None
def reflect(context, inquiry, observations, records):
    SEEN.append(observations); return {"answers_question": "partly", "factual_observation": "x"}, {}
M._reflect_with_claim_evidence = reflect
state = {"phase": "embed", "turns": 3, "inquiry": {"question": Q, "source_query": lit, "uniprot_query": "gene:SLC26A4"},
         "records": recs[1:]}
M._atomic(M.STATE, state)
REPLY["mode"] = "cooldown"
first = M.tick()
st = json.load(open(M.STATE))
check("with PDB on its one-a-minute hold, the step waits rather than dropping the read",
      first.get("state") == "waiting_for_source" and len(st.get("structure_pending") or []) == 2 and not EMBEDDED, (first, st.get("structure_pending")))
REPLY["mode"] = "ok"
a = M.tick(); b = M.tick()
check("each target's entry is read, one per pass", a.get("kind") == "structure_read" and b.get("kind") == "structure_read"
      and [x["entry_id"] for x in ASKED[-2:]] == ["7WK1", "7S8X"], (a, b, ASKED))
check("the read sends only the PDB request's own fields", all(set(x) == {"source", "entry_id", "operation"} for x in ASKED))
c = M.tick()
check("then the record is embedded as before", c.get("kind") == "protein_representation" and EMBEDDED, c)
M.tick()
check("the review receives the structures beside his own source", SEEN and len(SEEN[-1].get("STRUCTURE") or []) == 2,
      SEEN[-1].keys() if SEEN else None)
seen = M.review_observations({"question": Q}, SEEN[-1])
text = json.dumps(seen.get("STRUCTURE"))
check("the review reads chain ranges, contacts and helix records as sentences it can quote",
      "chain A: author residues 535 to 729 observed" in text and "chains A and B: 12 C-alpha pairs" in text
      and "HELIX    1 AA1 SER A  560" in text, text[:300])
st = json.load(open(M.STATE))
check("the question's structures are cleared once it is reviewed",
      not st.get("structure_evidence") and not st.get("structure_pending") and not st.get("structure_for"), st)

print("--- a source that is down costs the question nothing ---")
M._atomic(M.STATE, {"phase": "embed", "turns": 9, "inquiry": {"question": Q}, "records": recs[1:2]})
REPLY["mode"] = "down"; EMBEDDED.clear()
d = M.tick(); e = M.tick()
check("an unreachable PDB is noted and the question goes on", d.get("kind") == "structure_read"
      and e.get("kind") == "protein_representation", (d, e))
notes = [json.loads(x) for x in open(M.NOTEBOOK) if x.strip()]
failed = [n for n in notes if n.get("kind") == "structure_read" and n.get("failure")]
check("the failure is written down, not hidden", failed and "unreachable" in failed[-1]["failure"], failed[-1:] if failed else notes[-3:])

print("--- a question left midway hands nothing to the next ---")
M._atomic(M.STATE, {"phase": "embed", "turns": 9, "inquiry": {"question": "What is the fold of human AQP5?"},
                    "records": [{"accession": "P55064", "pdb_ids": ["3D9S"]}],
                    "structure_for": Q, "structure_pending": [{"source": "pdb", "entry_id": "7WK1", "operation": "structure_evidence"}],
                    "structure_evidence": [{"entry_id": "7WK1"}]})
REPLY["mode"] = "ok"; ASKED.clear()
M.tick()
st = json.load(open(M.STATE))
check("the new question reads its own entry, not the old one's", [x["entry_id"] for x in ASKED] == ["3D9S"]
      and [x.get("entry_id") for x in st.get("structure_evidence") or []] == ["3D9S"], (ASKED, st.get("structure_evidence")))
print("--- a saved or resumed step that goes straight to the review still reads it ---")
REPLY["mode"] = "ok"; ASKED.clear(); SEEN.clear()
Q2 = "How do the helical arrangements of the human SLC26A4 and SLC26A5 STAS domains compare?"
M._atomic(M.STATE, {"phase": "reflect", "turns": 12, "inquiry": {"question": Q2, "source_query": lit},
                    "records": [dict(r, length=700 + i) for i, r in enumerate(recs[1:])]})
x, y, z = M.tick(), M.tick(), M.tick()
check("from the review step, each target's entry is read first", [x.get("kind"), y.get("kind")] == ["structure_read", "structure_read"]
      and [a["entry_id"] for a in ASKED] == ["7WK1", "7S8X"], (x, y, ASKED))
check("then the review runs with the structures", z.get("kind") == "reflection" and len(SEEN[-1].get("STRUCTURE") or []) == 2,
      (z, SEEN[-1].keys() if SEEN else None))
notes = [json.loads(l) for l in open(M.NOTEBOOK) if l.strip()]
reads = [n for n in notes if n.get("kind") == "structure_read"][-2:]
check("each structure read names its question", len(reads) == 2 and all(n.get("question") == Q2 for n in reads), reads)

ASKED.clear()
M._atomic(M.STATE, {"phase": "reflect", "turns": 13, "inquiry": {"question": Q}, "records": recs[1:],
                    "coverage_retry_observations": {"records": recs[1:], "LITERATURE": []}})
M.tick()
check("a retry of a review that overflowed keeps its fixed evidence and reads nothing new", not ASKED, ASKED)

check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
