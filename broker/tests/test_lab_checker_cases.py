#!/usr/bin/env python3
"""The adjudicator itself, against known cases (T-09c7e8ff; Chat's review, 2026-10-14: "better retrieval may still
be measured by an unreliable adjudicator"). A verbatim quote at an exact address establishes traceability, not
entailment, and these are the cases where the two come apart. The checker's model is a stub answering a scripted
verdict: what is tested is the protocol around it — what it accepts, what it refuses, and what it cannot express.

Isolation: scratch HOME and workspace, sockets refused, _ask replaced. No model is called and nothing is sent."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-checker-cases-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def denied(*a, **k): raise AssertionError("this suite reaches nothing")
socket.socket.connect = denied; socket.create_connection = denied
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
C.urllib.request.urlopen = denied
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is denied)

QUESTION = "Which residues coordinate the iron in human ferritin heavy chain, and in which organism is that recorded?"
OBS = {"records": [{"accession": "P02794", "protein_name": "Ferritin heavy chain", "organism": "Homo sapiens",
                    "taxon_id": 9606, "length": 183,
                    "function": "Stores iron in a soluble, non-toxic form. The ferroxidase centre is formed by "
                                "Glu27, Tyr34, Glu62, His65 and Glu107 in the heavy chain."}],
       "LITERATURE": [{"pmid": "900001", "title": "Ferritin iron",
                       "abstract": "The ferroxidase site binds two iron atoms. Catalysis requires an intact site."}]}

def run(verdict, sufficiency=None, inquiry=None, observations=None):
    """One coverage check with a scripted checker answer. Returns (result, prompts)."""
    prompts = []
    def ask(system, prompt, **k):
        prompts.append((system, prompt))
        if "Independently assess" in system:
            return json.dumps(sufficiency or {"sufficient": True, "missing": [], "rationale": "scripted"})
        return json.dumps(verdict(prompts[-1][1]) if callable(verdict) else verdict)
    saved = C._ask; C._ask = ask
    try:
        return C._coverage_check(inquiry or {"question": QUESTION}, observations or OBS), prompts
    finally:
        C._ask = saved

def address_for(prompt, ends):
    tree = json.loads(prompt.split("\nEVIDENCE:\n", 1)[1])
    found = []
    def walk(v, path):
        if isinstance(v, dict) and set(v) == {"address", "text"}: found.append((path, v["address"], v["text"]))
        elif isinstance(v, dict):
            for k, c in v.items(): walk(c, path + "." + str(k))
        elif isinstance(v, list):
            for i, c in enumerate(v): walk(c, path + "." + str(i))
    walk(tree, "evidence")
    return next((a for p, a, _ in found if p.endswith(ends)), None)

print("--- supported: a real quote at its real address ---")
def supported(prompt):
    return {"answered": True, "missing": [],
            "supports": [{"requirement": "coordinating residues", "address": address_for(prompt, "records.0.function"),
                          "quote": "Glu27, Tyr34, Glu62, His65 and Glu107"},
                         {"requirement": "organism", "address": address_for(prompt, "records.0.organism"),
                          "quote": "Homo sapiens"}]}
got, _ = run(supported)
check("a verbatim quote at its own address is accepted", got["answered"] and len(got["supports"]) == 2, got)
check("each support is cited to the record it came from",
      all(s.get("source_citation") == "UniProt P02794" for s in got["supports"]), got["supports"])

print("--- unsupported: the checker says no, with what is missing ---")
got, _ = run({"answered": False, "missing": ["the organism is not stated"], "supports": []})
check("a negative verdict with its missing list is kept as given",
      got["answered"] is False and got["missing"] == ["the organism is not stated"], got)
got, _ = run({"answered": False, "missing": [], "supports": []})
check("a negative verdict that names nothing missing is refused, not recorded as a scientific no",
      got["assessment_status"] == "incomplete", got)

print("--- contradictory: the two halves of the answer disagree ---")
got, _ = run({"answered": True, "missing": ["the organism is not stated"], "supports": [{"requirement": "r", "address": "x", "quote": "y"}]})
check("answered true with a missing list is refused", got["assessment_status"] == "incomplete", got)
got, _ = run({"answered": True, "missing": [], "supports": []})
check("answered true with no support at all is refused", got["assessment_status"] == "incomplete", got)
def wrong_address(prompt):
    return {"answered": True, "missing": [], "supports": [{"requirement": "r", "address": "source/not.a.real.address",
                                                           "quote": "Glu27, Tyr34, Glu62, His65 and Glu107"}]}
got, _ = run(wrong_address)
check("a true quote at an address that does not exist is refused", got["assessment_status"] == "incomplete", got)
def wrong_source(prompt):
    return {"answered": True, "missing": [], "supports": [{"requirement": "r", "address": address_for(prompt, "LITERATURE.0.abstract"),
                                                           "quote": "Glu27, Tyr34, Glu62, His65 and Glu107"}]}
got, _ = run(wrong_source)
check("a real quote cited to a source that does not contain it is refused", got["assessment_status"] == "incomplete", got)
def invented(prompt):
    return {"answered": True, "missing": [], "supports": [{"requirement": "r", "address": address_for(prompt, "records.0.function"),
                                                           "quote": "Glu27, Tyr34, Glu62, His65, Glu107 and Asp131"}]}
got, _ = run(invented)
check("a quote with a residue added to it is refused", got["assessment_status"] == "incomplete", got)

print("--- the second opinion can only lower the verdict ---")
got, _ = run(supported, sufficiency={"sufficient": False, "missing": ["the organism is not stated"], "rationale": "r"})
check("an independent no turns an answered verdict into partial, keeping its quotes",
      got["answered"] is False and got["missing"] == ["the organism is not stated"] and got["supports"], got)
got, _ = run({"answered": False, "missing": ["m"], "supports": []},
             sufficiency={"sufficient": True, "missing": [], "rationale": "r"})
check("an independent yes cannot raise a negative verdict", got["answered"] is False, got)
got, _ = run(supported, sufficiency={"sufficient": True, "missing": ["m"], "rationale": "r"})
check("a self-contradicting second opinion is refused", got["assessment_status"] == "incomplete", got)

print("--- what the protocol cannot express, named rather than assumed ---")
# Chat's point: a quote proves the text is there, not that the claim follows from it. A conclusion that needs a
# comparison or a calculation has no single passage to quote, so it cannot be supported however sound it is.
counted = "How many iron-coordinating residues does the human ferritin heavy chain record list?"
def arithmetic(prompt):
    return {"answered": True, "missing": [], "supports": [{"requirement": "the count is five",
                                                           "address": address_for(prompt, "records.0.function"),
                                                           "quote": "five"}]}
got, _ = run(arithmetic, inquiry={"question": counted})
check("a conclusion the evidence entails but never states cannot be supported by a quote",
      got["assessment_status"] == "incomplete", got)
check("and that refusal is recorded as the checker failing, not as the science being unsupported",
      str(got.get("validation_failure") or "").startswith("source-address validation failed"), got.get("validation_failure"))
import lab_claim_evidence as LCE
check("so it is told apart from a research outcome", LCE.outcome({"coverage_check": got})[0] == "checker_failed")
# The method string is the standing admission of what this instrument does and does not establish.
ok, _ = run(supported)
check("a passing check says in its own record that it is quote integrity, not proof",
      "not_scientific_proof" in ok["method"] and "integrity" in ok["method"], ok["method"])

print("--- the request the checker reads ---")
_, prompts = run(supported)
first = prompts[0][1]
check("the original question reaches the checker unchanged", QUESTION in first)
check("the checker is given the evidence addresses to cite", "\nEVIDENCE:\n" in first)
check("the second opinion is not shown the first verdict or its requirements",
      not any("coordinating residues" in p for s, p in prompts if "Independently assess" in s), [s[:40] for s, _ in prompts])
check("nothing reached the network", True)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
