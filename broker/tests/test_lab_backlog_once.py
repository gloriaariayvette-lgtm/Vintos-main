#!/usr/bin/env python3
"""The deferred-review backlog grades a question on its evidence once (19 October, live on Aegis: 138 of 207 reviews
in six hours were one GCLC question; 97 backlog snapshots of it, every one with the same evidence fingerprint, each
graded "no", and 41 graded twice because "already graded" was read from only the notebook's last 2 MB).

Scratch HOME and workspace; sockets refused; no model is asked."""
import hashlib, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-backlog-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
C._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model in this suite"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and C.GRADED.startswith(HOME))

DIR = os.path.join(C.ROOT, "coverage-deferred"); os.makedirs(DIR, exist_ok=True)
GCLC = "What are the specific structural hallmarks of the human Glutathione-Cysteine Ligase (GCLC) catalytic domain?"
RECORD = {"accession": "P48506", "protein_name": "Glutamate--cysteine ligase catalytic subunit", "organism": "Homo sapiens",
          "function": "Catalyzes the first step of glutathione biosynthesis."}
def snapshot(question, record, n, at):
    payload = {"inquiry": {"question": question, "uniprot_query": "gene:GCLC", "deferred_at": "pass %d" % n},
               "observations": {"records": [record], "LITERATURE": []}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = os.path.join(DIR, digest + ".json")
    json.dump(payload, open(path, "w"))
    os.utime(path, ns=(at, at))
    return digest
copies = [snapshot(GCLC, RECORD, n, 10**18 + n) for n in range(3)]           # the old loop's copies, newest last
other = snapshot("What does PRKCA's C1 domain bind?", dict(RECORD, accession="P17252"), 9, 10**18 - 5)
evidence = C._snapshot_evidence({"records": [RECORD], "LITERATURE": []})
check("every copy has the one evidence fingerprint", evidence and len({evidence}) == 1)

# One copy was graded this morning; a day of reviews since has pushed its row out of the notebook's last 2 MB.
with open(C.NOTEBOOK, "w") as f:
    f.write(json.dumps({"kind": "reflection", "at": "2026-10-19T15:26:38+00:00", "inquiry": {"question": GCLC},
                        "coverage_retry_sha256": copies[2], "evidence_sha256": evidence, "answers_question": "no: x"}) + "\n")
    pad = json.dumps({"kind": "reflection", "at": "2026-10-19T16:00:00+00:00", "inquiry": {"question": "other work"},
                      "evidence_sha256": "e" * 64, "note": "n" * 7800})
    for _ in range(300): f.write(pad + "\n")
check("the graded row is older than the last 2 MB", not any(r.get("coverage_retry_sha256") == copies[2]
      for r in C._tail_jsonl(C.NOTEBOOK, nbytes=2*1024*1024)))

picked = C._next_fitting_deferred_coverage()
check("a copy graded before the window is not graded again, nor its twins: the next question is", picked
      and picked["coverage_retry_sha256"] == other, picked and picked.get("question"))
skipped = [r for r in C._jsonl(C.GRADED) if r.get("same_as_graded")]
check("the twins are written down as the same review, so they are passed over at once next time",
      sorted(r["snapshot"] for r in skipped) == sorted(copies[:2]), skipped)

# Grading the other question records it, and then nothing is left.
C._note_graded({"kind": "reflection", "inquiry": {"question": picked["question"]},
                "coverage_retry_sha256": other, "evidence_sha256": "f" * 64})
check("a finished review is recorded where it does not scroll away", C._next_fitting_deferred_coverage() is None)
C._note_graded({"kind": "reflection", "coverage_deferred": True, "inquiry": {"question": "q"}, "coverage_retry_sha256": "d" * 64})
check("a review deferred again is not counted as graded", "d" * 64 not in C._graded()[0])

new = snapshot(GCLC, dict(RECORD, function="Catalyzes it, with a new cited structure."), 20, 10**18 + 50)
picked = C._next_fitting_deferred_coverage()
check("the same question on changed evidence is still reviewed", picked and picked["coverage_retry_sha256"] == new,
      picked and picked.get("coverage_retry_sha256"))
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("every notebook reflection goes through the graded record", "_note_graded(note)" in src)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
