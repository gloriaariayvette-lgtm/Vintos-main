#!/usr/bin/env python3
"""A question asks what a record can state (14 October). Of 30 reviews after the 9:55 restart none answered; 17
failed only on a trailing 'and how do these features facilitate ...' clause, a mechanism no database record states.
The clause is removed before the question is asked and kept as asked_as. Scratch HOME; no socket; no model."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-record-scope-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)
vdac = ("What are the specific structural features of the human Voltage-Dependent Anion Channel 1 (VDAC1) pore and its "
        "associated selectivity filter, and how do these features facilitate metabolite exchange?")
check("the mechanism clause is removed", C._record_scope(vdac) ==
      "What are the specific structural features of the human Voltage-Dependent Anion Channel 1 (VDAC1) pore and its associated selectivity filter?")
plain = "What are the specific amino acid residues in human HMOX1 (P09601) that coordinate the heme iron?"
check("a question with no mechanism clause is unchanged", C._record_scope(plain) == plain)
check("a question that is only a mechanism is left as it is", C._record_scope("How does X work?") == "How does X work?")
check("idempotent", C._record_scope(C._record_scope(vdac)) == C._record_scope(vdac))
inq = C._inquiry({"question": vdac, "uniprot_query": "gene:VDAC1 AND organism_id:9606 AND reviewed:true"})
check("the inquiry carries the scoped question and the original as asked_as",
      inq["question"] == C._record_scope(vdac) and inq.get("asked_as") == vdac, {k: inq.get(k) for k in ("question", "asked_as")})
check("the identity hash is of the question that is asked",
      inq["identity_context"]["question_sha256"] == __import__("hashlib").sha256(inq["question"].encode()).hexdigest())
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the planner is told to ask what a record can state", "a mechanism is not in a record" in src)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
