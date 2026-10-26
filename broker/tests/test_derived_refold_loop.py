#!/usr/bin/env python3
"""A sequence his own design instruments made, refolded and compared, without pretending it is natural.

Scratch HOME, scratch workspace, scratch Lab: every path this suite touches is under a temporary
directory and is asserted to be. Nothing sends, nothing reaches the network, no model is loaded: the
fold lane is a stub, `requests` and the plugin gateway raise, and sockets are closed off.
"""
import json, math, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-derived-refold-")
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

import lab_derived_sequences as D
import chemistry_esmfold as E
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
check("the Lab, its derived records and its pilot ledger are all in the scratch workspace",
      str(D.LAB).startswith(HOME) and str(D.DERIVED).startswith(HOME) and str(D.LEDGER).startswith(HOME)
      and str(E.DERIVED_ARTIFACTS).startswith(HOME), (D.LAB, D.LEDGER, E.DERIVED_ARTIFACTS))
check("nothing in this suite can send or fetch",
      sys.modules["requests"].get is _no_network and sys.modules["plugin_gateway"].run_skill is _no_network)
check("the fold lane's length ceiling is the one the adapter bounds candidates by",
      D.MAX_LENGTH == E.MAX_LENGTH, (D.MAX_LENGTH, E.MAX_LENGTH))
check("the loop's bounds are the ones the proposal set: two candidates, two folds, one pilot a day",
      (D.MAX_CANDIDATES, D.MAX_FOLDS_PER_PILOT, D.PILOTS_PER_DAY) == (2, 2, 1))

# ---------------------------------------------------------------- fixtures: a sourced backbone and a design artifact
AA = "ACDEFGHIKLMNPQRSTVWY"
THREE = {"A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY", "H": "HIS", "I": "ILE",
         "K": "LYS", "L": "LEU", "M": "MET", "N": "ASN", "P": "PRO", "Q": "GLN", "R": "ARG", "S": "SER",
         "T": "THR", "V": "VAL", "W": "TRP", "Y": "TYR"}
N = 48
PARENT_SEQ = "".join(AA[(i * 7) % 20] for i in range(N))
CAND_A = "".join(AA[(i * 11 + 3) % 20] for i in range(N))
CAND_B = "".join(AA[(i * 13 + 5) % 20] for i in range(N))


def trace(i):
    return (2.3 * math.cos(i * 1.75), 2.3 * math.sin(i * 1.75), 1.5 * i)


def write_pdb(path, sequence, coords):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for i, aa in enumerate(sequence, 1):
            x, y, z = coords(i)
            f.write("ATOM  %5d  CA  %3s A%4d    %8.3f%8.3f%8.3f  1.00 90.00           C\n"
                    % (i, THREE[aa], i, x, y, z))
        f.write("END\n")


PARENT_REL = "artifacts/esmfold/P12345-aabbccddeeff.pdb"
DESIGN_REL = "artifacts/protein_mpnn/0123456789abcdef/seqs/P12345.fa"
write_pdb(str(D.LAB / PARENT_REL), PARENT_SEQ, trace)
os.makedirs(os.path.dirname(str(D.LAB / DESIGN_REL)), exist_ok=True)
FASTA = (">P12345, score=1.8, global_score=1.8, model_name=v_48_020, seed=37\n%s\n"
         ">T=0.1, sample=1, score=0.91, seq_recovery=0.31\n%s\n"
         ">T=0.1, sample=2, score=0.95, seq_recovery=0.29\n%s\n" % (PARENT_SEQ, CAND_A, CAND_B))
open(str(D.LAB / DESIGN_REL), "w").write(FASTA)


def receipt(**over):
    body = {"ok": True, "instrument": "protein_mpnn", "operation": "sequence.design",
            "inputs": [{"file": PARENT_REL, "sha256": D._sha256(D.LAB / PARENT_REL)}],
            "files": [{"file": DESIGN_REL, "sha256": D._sha256(D.LAB / DESIGN_REL)}],
            "truth_status": "computed_model_output_not_biological_validation"}
    body.update(over)
    return body


# ---------------------------------------------------------------- the candidates it reads
found = D.candidates(FASTA)
check("ProteinMPNN's restatement of the backbone's own sequence is not a candidate",
      [s for _, s in found] == [CAND_A, CAND_B], found)
check("a FASTA with no sample headers offers every record after the first",
      [s for _, s in D.candidates(">in\n%s\n>out\n%s\n" % (PARENT_SEQ, CAND_A))] == [CAND_A])

# ---------------------------------------------------------------- registration keeps the parent's identity the parent's
records = D.register(receipt())
check("one record per candidate, each with a derived id of its own",
      [r["sequence"] for r in records] == [CAND_A, CAND_B]
      and all(D.DERIVED_ID.fullmatch(r["derived_id"]) for r in records)
      and len({r["derived_id"] for r in records}) == 2, records)
check("registering the same design artifact again mints the same ids",
      [r["derived_id"] for r in D.register(receipt())] == [r["derived_id"] for r in records])
one = records[0]
check("the record carries both parent hashes and the design artifact it came out of",
      one["parent_structure"] == PARENT_REL and one["parent_sha256"] == D._sha256(D.LAB / PARENT_REL)
      and one["design_artifact"] == DESIGN_REL and one["design_sha256"] == D._sha256(D.LAB / DESIGN_REL)
      and one["instrument"] == "protein_mpnn" and "sample=1" in one["design_header"], one)
check("the accession stays the parent's and the sequence is never called natural",
      one["parent_accession"] == "P12345" and one["natural_accession"] is None
      and one["is_natural_sequence"] is False and one["truth_status"].startswith("designed_sequence_derived"), one)
check("how far the candidate is from the backbone's own sequence is recorded",
      0.0 <= one["identity_to_parent_sequence"] < 1.0, one["identity_to_parent_sequence"])
check("the record is on disk under its own id and reads back",
      (D.DERIVED / (one["derived_id"] + ".json")).is_file()
      and D.record(one["derived_id"])["sequence"] == CAND_A)

refuses("a receipt whose design artifact has changed underneath it",
        lambda: D.register(receipt(files=[{"file": DESIGN_REL, "sha256": "0" * 64}])))
refuses("a receipt whose parent structure has changed underneath it",
        lambda: D.register(receipt(inputs=[{"file": PARENT_REL, "sha256": "0" * 64}])))
refuses("a receipt from an instrument that designs nothing",
        lambda: D.register(receipt(instrument="openmm", operation="structure.relax_ca")))
refuses("a failed native run", lambda: D.register(receipt(ok=False)))
refuses("a design artifact outside the Lab's artifact store",
        lambda: D.register(receipt(files=[{"file": "../../../etc/passwd", "sha256": "0" * 64}])))
refuses("a record that was never registered", lambda: D.record("DRV-000000000000"))
refuses("something that is not a derived id at all", lambda: D.record("P12345"))

THIRD = "artifacts/protein_mpnn/0123456789abcdef/seqs/three.fa"
open(str(D.LAB / THIRD), "w").write(FASTA + ">T=0.1, sample=3, score=1.1\n%s\n" % PARENT_SEQ)
refuses("more candidates than a pilot may carry",
        lambda: D.register(receipt(files=[{"file": THIRD, "sha256": D._sha256(D.LAB / THIRD)}])))
BAD = "artifacts/protein_mpnn/0123456789abcdef/seqs/bad.fa"
open(str(D.LAB / BAD), "w").write(">T=0.1, sample=1\n%s\n" % ("XBZ" * 20))
refuses("a candidate that is not standard amino acids",
        lambda: D.register(receipt(files=[{"file": BAD, "sha256": D._sha256(D.LAB / BAD)}])))

# ---------------------------------------------------------------- the fold request carries no accession
request = D.fold_request(one["derived_id"])
check("a derived fold request has no accession field of any kind",
      not any(k in request for k in ("accession", "sequence_source", "hp_mapping"))
      and request["derived_id"] == one["derived_id"] and request["sequence"] == CAND_A
      and request["is_natural_sequence"] is False, request)
check("its provenance is the parent's hashes",
      request["provenance"]["parent_sha256"] == one["parent_sha256"]
      and request["provenance"]["design_sha256"] == one["design_sha256"]
      and request["provenance"]["parent_accession"] == "P12345", request)
check("the adapter accepts its own request", D.verify_fold_request(request)["derived_id"] == one["derived_id"])
refuses("a designed sequence handed a natural accession to get through the fold lane",
        lambda: D.verify_fold_request(dict(request, accession="P12345")))
refuses("a designed sequence given a source block",
        lambda: D.verify_fold_request(dict(request, sequence_source={"accession": "P12345"})))
refuses("a designed sequence given an HP mapping",
        lambda: D.verify_fold_request(dict(request, hp_mapping=[{"residue": "A"}])))
refuses("a request whose sequence is not the one registered",
        lambda: D.verify_fold_request(dict(request, sequence=CAND_B)))
refuses("a request whose provenance hash does not match the record",
        lambda: D.verify_fold_request(dict(request, provenance=dict(request["provenance"], parent_sha256="0" * 64))))

# ---------------------------------------------------------------- the fold lane's two doors stay apart
check("the fold lane recognizes a derived request through the adapter",
      E.derived_identity(request)["derived_id"] == one["derived_id"])
check("an ordinary natural fold request is untouched by the derived door",
      E.derived_identity({"accession": "P12345", "sequence": PARENT_SEQ}) is None)
refuses("the fold lane taking a derived id beside an accession",
        lambda: E.derived_identity(dict(request, accession="P12345")))
refuses("the fold lane folding a designed sequence under a false accession",
        lambda: E.fold(dict(request, accession="P12345")))
check("that refusal happened before any model was loaded", "torch" not in sys.modules)
refuses("the natural lane still refusing a sequence with no accession",
        lambda: E._validate({"sequence": PARENT_SEQ}))

# ---------------------------------------------------------------- the loop's bounds
ids = [r["derived_id"] for r in records]
pilot = D.open_pilot(ids, today="2026-10-26")
check("a pilot holds one parent, its candidates and a fold budget",
      D.PILOT_ID.fullmatch(pilot["pilot_id"]) and pilot["parent_structure"] == PARENT_REL
      and pilot["derived"] == sorted(ids) and pilot["max_folds"] == 2
      and pilot["gpu_minutes_ceiling"] == D.GPU_MINUTES_CEILING, pilot)
check("opening the same pilot again is the same pilot, not a second one",
      D.open_pilot(ids, today="2026-10-26")["pilot_id"] == pilot["pilot_id"] and len(D.pilots()) == 1)
refuses("a second pilot on the same day", lambda: D.open_pilot(ids[:1], today="2026-10-26"), (PermissionError,))
refuses("a pilot with no candidate", lambda: D.open_pilot([], today="2026-10-27"))
refuses("a pilot with the same candidate twice",
        lambda: D.open_pilot([ids[0], ids[0]], today="2026-10-27"))

# a candidate whose parent is a different structure cannot join this pilot
OTHER_PARENT = "artifacts/esmfold/Q99999-112233445566.pdb"
OTHER_DESIGN = "artifacts/protein_mpnn/fedcba9876543210/seqs/Q99999.fa"
write_pdb(str(D.LAB / OTHER_PARENT), PARENT_SEQ, lambda i: trace(i + 1))
os.makedirs(os.path.dirname(str(D.LAB / OTHER_DESIGN)), exist_ok=True)
open(str(D.LAB / OTHER_DESIGN), "w").write(">T=0.1, sample=1\n%s\n" % CAND_A)
other = D.register({"ok": True, "instrument": "protein_mpnn", "operation": "sequence.design",
                    "inputs": [{"file": OTHER_PARENT, "sha256": D._sha256(D.LAB / OTHER_PARENT)}],
                    "files": [{"file": OTHER_DESIGN, "sha256": D._sha256(D.LAB / OTHER_DESIGN)}]})[0]
refuses("candidates of two different backbones in one pilot",
        lambda: D.open_pilot([ids[0], other["derived_id"]], today="2026-10-27"))

# ---------------------------------------------------------------- the refolds, recorded
FOLD_A = "artifacts/esmfold-derived/%s-aaa111bbb222.pdb" % ids[0]
FOLD_B = "artifacts/esmfold-derived/%s-ccc333ddd444.pdb" % ids[1]
write_pdb(str(D.LAB / FOLD_A), CAND_A, lambda i: trace(i))                     # keeps the backbone exactly
write_pdb(str(D.LAB / FOLD_B), CAND_B,
          lambda i: (trace(i)[0] * 1.35, trace(i)[1] * 1.35, trace(i)[2] * 1.2))   # drifts from it
D.note_fold(pilot["pilot_id"], ids[0], FOLD_A)
row = D.note_fold(pilot["pilot_id"], ids[1], FOLD_B)
check("each refold is recorded against its candidate with the structure's hash",
      [f["derived_id"] for f in row["folds"]] == ids
      and row["folds"][0]["sha256"] == D._sha256(D.LAB / FOLD_A), row["folds"])
refuses("the same candidate refolded twice in one pilot",
        lambda: D.note_fold(pilot["pilot_id"], ids[0], FOLD_A))
refuses("a refold of a sequence this pilot never registered",
        lambda: D.note_fold(pilot["pilot_id"], other["derived_id"], FOLD_A))
refuses("a refold structure that is not a Lab artifact",
        lambda: D.note_fold(pilot["pilot_id"], ids[0], "/etc/hosts"))

# ---------------------------------------------------------------- the comparison
out = D.compare_pilot(pilot["pilot_id"])
result = out["result"]
check("the refold that keeps the backbone's geometry comes first",
      result["closest_to_parent"] == ids[0] and result["candidates"][0]["drmsd_A"] < 0.01
      and result["candidates"][1]["drmsd_A"] > 1.0, [(c["derived_id"], c["drmsd_A"]) for c in result["candidates"]])
check("the comparison needs no superposition, so a rotated model scores the same",
      "no superposition" in result["method"], result["method"])
ROT = "artifacts/esmfold-derived/%s-eee555fff666.pdb" % ids[0]


def rotated(i):
    x, y, z = trace(i)
    a = 0.7
    return (x * math.cos(a) - y * math.sin(a) + 11.0, x * math.sin(a) + y * math.cos(a) - 4.0, z + 7.0)


write_pdb(str(D.LAB / ROT), CAND_A, rotated)
spun = D.compare_refolds(PARENT_REL, [{"derived_id": ids[0], "structure": ROT, "sha256": D._sha256(D.LAB / ROT)}])
check("a refold moved and turned in space is scored as the same shape",
      spun["result"]["candidates"][0]["drmsd_A"] < 0.01, spun["result"]["candidates"][0]["drmsd_A"])
check("every compared residue is accounted for, and the two refolds are also compared with each other",
      result["candidates"][0]["compared_residues"] == N and result["between_candidates"]["pair"] == ids
      and result["parent_residues"] == N, result["between_candidates"])
check("the comparison says what it is not",
      result["truth_status"] == D.COMPARE_TRUTH
      and any("Not affinity" in line for line in result["display"])
      and result["pilot_id"] == pilot["pilot_id"], result["display"])
check("the pilot's GPU ceiling travels with the result",
      result["gpu_minutes_ceiling"] == D.GPU_MINUTES_CEILING)
SHORT = "artifacts/esmfold-derived/short.pdb"
write_pdb(str(D.LAB / SHORT), CAND_A[:5], trace)
refuses("a comparison with too few residues to be fair",
        lambda: D.compare_refolds(PARENT_REL, [{"derived_id": ids[0], "structure": SHORT}]))
refuses("a comparison of a refold that changed since it was recorded",
        lambda: D.compare_refolds(PARENT_REL, [{"derived_id": ids[0], "structure": FOLD_A, "sha256": "0" * 64}]))

# ---------------------------------------------------------------- the fold is asked for inside the budget
calls = []


def fold_runner(result_artifact, accession=None, derived=None):
    def run(argv, input=None, text=None, capture_output=None, timeout=None):
        calls.append(json.loads(input))
        body = {"ok": True, "result": {"derived_id": derived, "requested_accession": accession,
                                       "structure_artifact": "memory/chemistry-lab/" + result_artifact}}
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(body) + "\n", stderr="")
    return run


FRESH = "artifacts/esmfold-derived/%s-999888777666.pdb" % other["derived_id"]
write_pdb(str(D.LAB / FRESH), CAND_A, trace)
second = D.open_pilot([other["derived_id"]], today="2026-10-27")
got = D.fold_candidate(second["pilot_id"], other["derived_id"],
                       run=fold_runner(FRESH, derived=other["derived_id"]), admit=False)
check("a refold through the fold lane is recorded against its pilot",
      got["derived_id"] == other["derived_id"]
      and [f["derived_id"] for f in D.pilot(second["pilot_id"])["folds"]] == [other["derived_id"]])
check("the body it sent carries no accession",
      calls and "accession" not in calls[-1] and calls[-1]["derived_id"] == other["derived_id"], calls)
third = D.open_pilot([ids[0]], today="2026-10-28")
refuses("a receipt that files a designed sequence under a natural accession",
        lambda: D.fold_candidate(third["pilot_id"], ids[0],
                                 run=fold_runner(FOLD_A, accession="P12345", derived=ids[0]), admit=False),
        (RuntimeError,))


def must_not_run(*a, **k):
    raise AssertionError("the GPU must not be asked for when the fold is refused")


refuses("a candidate already refolded in this pilot, with the GPU never asked for",
        lambda: D.fold_candidate(pilot["pilot_id"], ids[0], run=must_not_run, admit=False), (ValueError,))
check("a pilot never holds more refolds than its budget",
      all(len(p.get("folds") or []) <= p.get("max_folds", D.MAX_FOLDS_PER_PILOT) for p in D.pilots()))
admitted = []
sys.modules["compute_admission"] = types.SimpleNamespace(
    admit=lambda cls, organ="", stage="", **k: admitted.append((cls, organ, stage)))
FOURTH = "artifacts/esmfold-derived/%s-123123123123.pdb" % ids[1]
write_pdb(str(D.LAB / FOURTH), CAND_B, trace)
fourth = D.open_pilot([ids[1]], today="2026-10-29")
D.fold_candidate(fourth["pilot_id"], ids[1], run=fold_runner(FOURTH, derived=ids[1]))
check("foreground use is admitted before the GPU is asked for",
      admitted == [("background", "lab-derived-refold", "esmfold")], admitted)

# ---------------------------------------------------------------- the door he reaches it through
menu = L.menu_block()
check("the comparison is offered only once a refold exists, and says what it does not claim",
      "derived_compare" in menu and pilot["pilot_id"] in menu and "nothing about affinity" in menu, menu)
out = L.run({"skill": "derived_compare", "operation": "structure.compare_refolds", "files": [],
             "pilot": pilot["pilot_id"], "question": "did either design keep the backbone I folded it on"})
rec = out["receipt"]["records"][0]
check("the Lab runs it on his own artifacts and records a receipt",
      out["receipt"]["source"] == "instrument:derived_compare" and ids[0] in rec["summary"]
      and "dRMSD" in rec["summary"], rec)
refuses("an operation this instrument does not offer",
        lambda: L.validate({"skill": "derived_compare", "operation": "structure.compare",
                            "files": [], "question": "compare these refolds for me"}))

# ---------------------------------------------------------------- it reaches Aegis only if the deploy names it
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy manifest names the adapter", "lab_derived_sequences.py" in deploy)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
