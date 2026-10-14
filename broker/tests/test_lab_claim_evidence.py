#!/usr/bin/env python3
"""Full-text evidence for a review's unanswered claims (T-17420bd6, 2026-10-14). The whole question is kept; its
open claims are searched for in Europe PMC full text; passages are cited by PMCID and section; gaps are named with
what was searched and what would justify another attempt; identical searches are reused, not run again; a checker
failure is never a scientific "no"; and a fixed set of failed questions can be audited and replayed.

Isolation: scratch HOME and workspace; requests and sockets are stubs; Europe PMC is a scripted transport; the
model is a stub. Nothing is sent and no live store is touched."""
import json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-claim-evidence-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
socket.getaddrinfo = no_network; socket.create_connection = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_claim_evidence as LCE, chemistry_lab as C, lab_claim_replay as RP
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("every store is scratch; requests and sockets are stubs",
      LCE.LEDGER.startswith(HOME) and C.ROOT.startswith(HOME) and RP.DIR.startswith(HOME)
      and sys.modules["requests"].get is no_network and socket.getaddrinfo is no_network)

Q = ("What are the specific structural features of the human Ferritin Heavy Chain (FTH1) ferroxidase centre, and how "
     "do these features facilitate iron sequestration and storage?")
INQ = {"question": Q, "uniprot_query": "gene:FTH1 AND organism_id:9606 AND reviewed:true"}
PARTIAL = {"answers_question": "no: how these features facilitate iron sequestration",
           "entity_context_check": {"status": "consistent", "issues": [], "target_mapping": {"FTH1": "P02794"}},
           "coverage_check": {"answered": False, "missing": ["how the ferroxidase centre facilitates iron sequestration"],
                              "supports": [{"requirement": "ferroxidase centre residues", "quote": "Glu27, Glu62, His65",
                                            "source_citation": "UniProt P02794"}]}}

print("--- outcomes: research, the question, the Lab's own failures ---")
check("partial", LCE.outcome(PARTIAL)[0] == "partially_supported")
check("unsupported", LCE.outcome({"coverage_check": {"answered": False, "missing": ["x"], "supports": []}})[0]
      == "unsupported_by_available_evidence")
check("answered", LCE.outcome({"coverage_check": {"answered": True, "missing": [], "supports": [{"quote": "q"}]}})[0] == "answered")
check("a wrong alias is a flawed premise", LCE.outcome({"entity_context_check": {"issues": [
      "the question gives GLUT1 and SLC1A1 as one protein; the records say GLUT1=P11166 and SLC1A1=P43005"]}})[0] == "contradicted_premise")
check("an unestablished target is a wrong target", LCE.outcome({"entity_context_check": {"issues": [
      "no retrieved record establishes SOX10; established: SOX9=P48436"]}})[0] == "wrong_target")
inc = C._incomplete_assessment(INQ, {}, "", reason="source-address validation failed")
check("a checker failure is checker_failed, and its verdict is not a 'no'", LCE.outcome(inc)[0] == "checker_failed"
      and not inc["answers_question"].startswith("no:") and inc["answers_question"].startswith("not assessed"), inc["answers_question"])
check("context overflow is its own outcome", LCE.outcome({"coverage_deferred": True, "evidence_status": "deferred"})[0] == "context_overflow")
check("a deferred review's verdict is not a 'no' either", "'answers_question':'not assessed: ' + reason" in open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read())

print("--- the search, the passages, the ledger ---")
JATS = """<?xml version="1.0"?><article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1110001</article-id><article-id pub-id-type="pmid">999</article-id>
<title-group><article-title>Ferritin iron storage</article-title></title-group></article-meta></front>
<body><sec><title>Results</title>
<p>The ferroxidase centre of FTH1 oxidises ferrous iron, and the resulting ferric iron migrates into the cavity for sequestration as a mineral core; mutation of the centre abolishes iron storage in vitro.</p>
<p>An unrelated paragraph about crystallisation buffers and protein purification steps that has nothing to say here at all.</p>
</sec></body></article>"""
SEARCH_JSON = json.dumps({"resultList": {"result": [{"pmcid": "PMC1110001", "pmid": "999", "isOpenAccess": "Y"}]}})
calls = []
def fetch(url, **kw):
    calls.append(url)
    if "/search?" in url:
        return {"fetched": True, "kind": "fetched", "raw": SEARCH_JSON, "text": SEARCH_JSON}
    if url.endswith("PMC1110001/fullTextXML"):
        return {"fetched": True, "kind": "fetched", "raw": JATS, "text": "x", "http_status": 200}
    return {"fetched": False, "kind": "http_failure", "http_status": 404, "why": "HTTP 404"}
check("the open claim is the coverage check's missing item", LCE.claims(PARTIAL) == ["how the ferroxidase centre facilitates iron sequestration"])
check("the protein is the established target", LCE.entities(INQ, PARTIAL)[0] == "FTH1", LCE.entities(INQ, PARTIAL))
qs = LCE.claim_queries(["FTH1"], "how the ferroxidase centre facilitates iron sequestration")
check("a query is the protein AND the claim's own words, open access", qs and qs[0].startswith('("FTH1") AND ')
      and "ferroxidase" in qs[0] and "OPEN_ACCESS:y" in qs[0] and "facilitate" not in qs[0], qs)
g = LCE.gather(INQ, PARTIAL, None, fetch=fetch)
check("a passage that bears on the claim comes back, cited by PMCID and section",
      len(g["FULLTEXT"]) == 1 and g["FULLTEXT"][0]["pmcid"] == "PMC1110001" and g["FULLTEXT"][0]["section"] == "Results"
      and "sequestration" in g["FULLTEXT"][0]["text"], g)
check("the unrelated paragraph is not handed over", not any("crystallisation" in p["text"] for p in g["FULLTEXT"]))
check("the question is not changed", INQ["question"] == Q)
n = len(calls)
g2 = LCE.gather(INQ, PARTIAL, None, fetch=fetch)
check("the same search for the same question is reused, not run again, and the article not read again",
      len(calls) == n and g2["reused"] and not g2["searches"] and len(g2["FULLTEXT"]) == 1, (calls[n:], g2))
check("the Lab's ledger is the scratch one this suite reads", C._claim_ledger() == LCE.LEDGER, (C._claim_ledger(), LCE.LEDGER))
check("an imported Lab does not search Europe PMC: only its own daemon wires the fetch in",
      C.CLAIM_FULLTEXT_FETCH is None and LCE.gather(INQ, PARTIAL, None).get("skipped") == "full-text search is not wired into this process")
check("a flawed premise is not searched", LCE.gather(INQ, {"entity_context_check": {"issues": ["as one protein"]}}, None,
      fetch=no_network).get("skipped", "").startswith("contradicted_premise"))

after = {"coverage_check": {"answered": False, "missing": ["how the ferroxidase centre facilitates iron sequestration"],
                            "supports": PARTIAL["coverage_check"]["supports"]}}
mem = LCE.remember(Q, after, g)
gap = mem["gaps"][0] if mem["gaps"] else {}
check("an open claim is named with its searches and what would justify another attempt",
      gap.get("claim", "").startswith("how the ferroxidase") and gap.get("searched") and "PMC1110001" in gap.get("would_justify", ""), mem)
check("supported quotes are carried forward as prior evidence", LCE.prior_supports(Q) and LCE.prior_supports(Q)[0]["quote"] == "Glu27, Glu62, His65")
check("a question whose every open claim has been searched waits", LCE.unchanged(Q))

print("--- the checker reads and cites full text ---")
obs = {"records": [], "LITERATURE": [], "FULLTEXT": g["FULLTEXT"]}
prepared = C._coverage_request(INQ, obs)
evidence, strings, addresses, request = prepared
check("a passage's text has a PMCID address", any(a.startswith("PMC1110001/text") for a in addresses), list(addresses)[:6])
check("its metadata is not quotable", not any(p.endswith((".pmcid", ".title", ".section", ".claim", ".source_url"))
                                                for p in addresses.values()), list(addresses.values()))
address = next(a for a in addresses if a.startswith("PMC1110001/text"))
reply = json.dumps({"answered": False, "missing": ["structural features of the centre"],
                    "supports": [{"requirement": "iron sequestration", "address": address,
                                  "quote": "the resulting ferric iron migrates into the cavity for sequestration"}]})
saved_ask = C._ask; C._ask = lambda *a, **k: reply
try:
    att = C._coverage_attempt(INQ, evidence, strings, addresses, request, None, "")
finally:
    C._ask = saved_ask
check("a quoted passage is cited as PMCID and section", att.get("supports") and att["supports"][0].get("source_citation") == "PMC1110001, Results", att)

print("--- the review step: the whole question, reviewed again with the passages ---")
seen = []
def fake_reflect(context, inquiry, observations, _validation_attempt=0):
    seen.append((inquiry["question"], bool(observations.get("FULLTEXT")), len(observations.get("prior_validated_evidence") or [])))
    if observations.get("FULLTEXT"):
        return {"answers_question": "yes: both source-coverage assessments support the original question",
                "coverage_check": {"answered": True, "missing": [], "supports": PARTIAL["coverage_check"]["supports"] + att["supports"]},
                "evidence_status": "answered"}
    return dict(PARTIAL)
saved = (C._reflect, C.CLAIM_FULLTEXT_FETCH); C._reflect = fake_reflect; C.CLAIM_FULLTEXT_FETCH = fetch
try:
    os.remove(LCE.LEDGER)
    reflection, fields = C._reflect_with_claim_evidence("", INQ, {"records": []}, [])
finally:
    C._reflect, C.CLAIM_FULLTEXT_FETCH = saved
check("both reviews were of the whole original question", [s[0] for s in seen] == [Q, Q], seen)
check("the second had the passages", seen[1][1], seen)
check("the outcome is recorded with the passages used", fields["review_outcome"] == "answered"
      and fields["fulltext_passages"][0]["pmcid"] == "PMC1110001" and reflection.get("first_review", {}).get("outcome") == "partially_supported", fields)
def failing_second(context, inquiry, observations, _validation_attempt=0):
    if observations.get("FULLTEXT"):
        return C._incomplete_assessment(inquiry, {}, "", reason="checker answer invalid")
    return dict(PARTIAL)
saved = (C._reflect, C.CLAIM_FULLTEXT_FETCH); C._reflect = failing_second; C.CLAIM_FULLTEXT_FETCH = fetch
try:
    os.remove(LCE.LEDGER)
    reflection, fields = C._reflect_with_claim_evidence("", INQ, {"records": []}, [])
finally:
    C._reflect, C.CLAIM_FULLTEXT_FETCH = saved
check("a second review that fails as software does not replace the first, and is recorded as such",
      fields["review_outcome"] == "partially_supported" and fields["claim_evidence"]["second_review"]["outcome"] == "checker_failed", fields)

print("--- the fixed set: audit and replay ---")
os.makedirs(C.ROOT, exist_ok=True)
with open(RP.NOTEBOOK, "w") as f:
    f.write(json.dumps({"kind": "reflection", "at": "2026-10-14T16:00:00", "inquiry": INQ, **PARTIAL}) + "\n")
    f.write(json.dumps({"kind": "reflection", "at": "2026-10-14T16:01:00",
                        "inquiry": {"question": "What are the extracellular loops of the human GLUT1 (SLC1A1) transporter?"},
                        "answers_question": "no: the question gives GLUT1 and SLC1A1 as one protein",
                        "entity_context_check": {"issues": ["the question gives GLUT1 and SLC1A1 as one protein; the records say GLUT1=P11166 and SLC1A1=P43005"]}}) + "\n")
    f.write(json.dumps({"kind": "reflection", "at": "2026-10-14T16:02:00", "inquiry": {"question": "Q3"},
                        **inc}) + "\n")
items = RP.pick(10)
check("the fixed set holds the failed questions, whole", len(items) == 3 and items[-1]["inquiry"]["question"] == Q)
check("the set is fixed: picking again returns the same set", RP.pick(1) == items)
kinds = {a["outcome"]: a["kind"] for a in RP.audit(items)}
check("the audit separates missing evidence, a flawed premise and a Lab failure",
      kinds.get("partially_supported") == "missing evidence" and kinds.get("contradicted_premise") == "question or target"
      and kinds.get("checker_failed") == "Lab failure, not judged", kinds)
asked = []
def coverage(inquiry, observations):
    asked.append((inquiry["question"], len(observations["FULLTEXT"]), len(observations["prior_validated_evidence"])))
    return {"answered": True, "missing": [], "supports": [{"quote": "q", "source_citation": "PMC1110001, Results"}] * 2}
res = RP.run(items, fetch=fetch, coverage=coverage, ledger_path=os.path.join(RP.DIR, "t-ledger.json"))
check("the replay asks the checker the whole question, with passages and the earlier quotes", asked == [(Q, 1, 1)], asked)
check("only questions missing evidence are searched", [r["after"] for r in res] == ["checker_failed", "contradicted_premise", "answered"][::-1]
      or sorted(r["after"] for r in res) == ["answered", "checker_failed", "contradicted_premise"], res)
s = RP.summary(res)
check("the summary counts before and after", s["missing_evidence"] == 1 and s["answered_after"] == 1 and s["not_searchable"] == 2, s)
check("the live claim ledger is not the replay's", not os.path.exists(os.path.join(RP.DIR, "claim-evidence.json")))
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
