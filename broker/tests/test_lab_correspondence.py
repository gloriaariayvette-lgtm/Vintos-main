#!/usr/bin/env python3
"""Scientific correspondence with something earned to say (Codex's proposal 14): a surviving Lab result, packed as
evidence from the Lab's own records, a paper verified at its source, and a local draft to one of its authors. Nothing
is sent, no address is looked up, no want is formed; his own email route is only shown the packet.

Scratch HOME, scratch workspace, scratch Lab: every store this suite touches is under a temporary directory and is
asserted to be. Every output and paper record is an invented fixture; no model is asked, sockets are closed off,
`requests`, the plugin gateway and the want door raise, and the paid ledger refuses to be touched.
"""
import json, os, socket, sys, tempfile, types
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-lab-correspondence-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")


def _no_network(*a, **k):
    raise AssertionError("a test must never reach the network")


def _no_paid(*a, **k):
    raise AssertionError("correspondence drafting never reserves or spends a paid call")


def _no_want(*a, **k):
    raise AssertionError("a draft never forms a want")


def _no_socket(self, *a, **k):
    raise AssertionError("a test must never open a socket")


socket.socket.connect = _no_socket
sys.modules["requests"] = types.SimpleNamespace(get=_no_network, post=_no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=_no_network, call=_no_network)
sys.modules["compute_admission"] = types.SimpleNamespace(reserve_paid=_no_paid, release_paid=_no_paid, admit=_no_paid)
sys.modules["emoclaw_utils"] = types.SimpleNamespace(express_want=_no_want)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import lab_measurement as M
import lab_correspondence as C

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:700]) if detail and not ok else ""))


NOW = "2026-10-26T12:00:00+00:00"
LAB = C.lab_root()

# ---------------------------------------------------------------- isolation
check("the drafts, findings, investigations and measurement stores are all in the scratch workspace",
      all(str(p).startswith(HOME) for p in (C.drafts_path(), os.path.join(LAB, C.FINDINGS_NAME), M.results_path(),
                                            M.contracts_path())), C.drafts_path())
check("nothing in this suite can send, fetch, spend or form a want",
      sys.modules["plugin_gateway"].call is _no_network and sys.modules["compute_admission"].reserve_paid is _no_paid
      and sys.modules["emoclaw_utils"].express_want is _no_want)
check("an empty Lab has nothing earned and no drafts", C.candidates() == [] and C.drafts() == [])


# ---------------------------------------------------------------- results made the way the Lab makes them
INVS = []


def output(sid, payload, state="completed", **extra):
    step = {"id": sid, "route": "instrument", "tool": "instrument:rt_locus_screen", "state": state, **extra}
    if state == "completed":
        rel = "investigation-outputs/%s.json" % sid
        path = os.path.join(M._root(), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(payload, open(path, "w"))
        step.update(output_file=rel, output_sha256=M._sha(payload))
    return step


def counts(hits, total):
    return {"result": {"hits": hits, "total": total}}


def role(nth, meaning="phage loci with an array beside the RT"):
    return {"select": {"tool": "rt_locus_screen", "nth": nth}, "hits": ["result", "hits"],
            "total": ["result", "total"], "meaning": meaning}


def proportion(hypothesis, **over):
    c = {"mode": "confirmatory", "hypothesis": hypothesis, "unit": "locus",
         "variable": "share of loci with a CRISPR array within 12 kb", "units": "proportion",
         "evaluator": "proportion_vs_control", "predicts": "case_higher", "min_effect": 0.2,
         "supports": "case share exceeds control by 0.2", "opposes": "the interval rules out a 0.2 excess",
         "missing": "not_evaluated", "case": role(1), "control": role(2, "matched background loci")}
    c.update(over)
    return c


def finding(inv_id, question, new_result=True, novelty="not in these titles", next_question="", **extra):
    row = {"at": NOW, "kind": "investigation_finding", "source_id": inv_id, "investigation": inv_id,
           "question": question, "result": question, "new_result": new_result,
           "appraisal": {"novelty": novelty, "value": 4},
           "literature": {"query": '"reverse transcriptase" AND "phage"', "hits": 3, "titles": ["x (2024)"]},
           "next_question": next_question, **extra}
    M._append(os.path.join(LAB, C.FINDINGS_NAME), row)
    return row


def retain(inv_id, contract, steps, final=True, question=None, **fx):
    row = M.freeze(contract, by="test", investigation_id=inv_id, now=NOW)
    res = M.evaluate(row, steps, final=final, now=NOW)
    M._append(M.results_path(), res)
    INVS.append({"id": inv_id, "state": "answered", "steps": steps})
    json.dump({"investigations": INVS}, open(os.path.join(LAB, C.INVESTIGATIONS_NAME), "w"))
    finding(inv_id, question or contract["hypothesis"], **fx)
    return row, res


Q = "Are array-adjacent reverse transcriptases commoner in phage loci than in matched background loci?"
ASK = "Would the abortive infection systems in your phage collection explain a 0.7 excess of arrays beside the RT?"
_, yes = retain("INV-yes", proportion("array-adjacent reverse transcriptases are commoner in phage loci"),
                [output("S-y1", counts(18, 20)), output("S-y2", counts(4, 20))], question=Q, next_question=ASK)
_, no = retain("INV-no", proportion("retron reverse transcriptases sit in phage loci more than background"),
               [output("S-n1", counts(10, 40)), output("S-n2", counts(10, 40))],
               question="Do retron reverse transcriptases sit in phage loci more often than background loci?")
_, wide = retain("INV-wide", proportion("reverse transcriptases cluster in prophage loci", min_effect=0),
                 [output("S-w1", counts(4, 10)), output("S-w2", counts(3, 10))])
_, broke = retain("INV-broke", proportion("reverse transcriptases sit beside toxin genes in phage"),
                  [output("S-b1", None, state="failed", error="TimeoutError")])
_, looked = retain("INV-lookup", proportion("phage reverse transcriptases are commoner beside arrays"),
                   [output("S-l1", counts(18, 20)), output("S-l2", counts(4, 20))], new_result=False)
_, known = retain("INV-known", proportion("phage reverse transcriptase arrays are commoner in loci"),
                  [output("S-k1", counts(18, 20)), output("S-k2", counts(4, 20))], novelty="reported")
check("the fixtures came out as the Lab would record them",
      (yes["measurement_state"], yes["novelty_state"], no["measurement_state"], no["novelty_state"],
       wide["measurement_state"], broke["execution_state"]) ==
      ("supported", "candidate_computational_finding", "refuted", "negative_result", "inconclusive", "failed"),
      [yes, no, wide, broke])

# ---------------------------------------------------------------- what has been earned
cands = {c["finding"]: c for c in C.candidates()}
check("a supported measurement on new computation is earned", cands["INV-yes"]["earned"], cands.get("INV-yes"))
check("a clean refutation is earned too: a negative result is something to say", cands["INV-no"]["earned"],
      cands.get("INV-no"))
for inv, words in (("INV-wide", "inconclusive"), ("INV-broke", "failed"), ("INV-lookup", "retrieval"),
                   ("INV-known", "already reported")):
    check("not earned: %s (%s)" % (inv, words), not cands[inv]["earned"] and words in cands[inv]["why_not"],
          cands.get(inv))
check("a finding no contract judged is not earned",
      C.judge({"new_result": True, "investigation": "INV-none"})[2] == "no frozen measurement contract judged it")


# ---------------------------------------------------------------- a paper verified at its source
def record(pmid, title, authors, abstract="", doi=""):
    return {"pmid": pmid, "doi": doi, "title": title, "pubYear": "2025", "journalTitle": "Nucleic Acids Res",
            "abstractText": abstract,
            "authorList": {"author": [{"fullName": a, "firstName": a.split()[0], "lastName": a.split()[-1]}
                                      if " " in a else {"fullName": a} for a in authors]}}


PAPERS = {
    "40000001": record("40000001", "Reverse transcriptases beside CRISPR arrays in phage loci",
                       ["Ana Ruiz", "Tomas Berg", "Mira Okafor"],
                       "We screened phage loci for reverse transcriptases adjacent to CRISPR arrays.",
                       doi="10.1093/nar/test.1"),
    "40000002": record("40000002", "Ribosome assembly kinetics in yeast", ["Lee Park", "Jo Stein"],
                       "Yeast ribosomes assemble in stages."),
    "40000003": record("40000003", "Phage reverse transcriptase arrays in loci", ["Okafor"],
                       "Reverse transcriptases in phage loci beside arrays."),
}
FETCHED = []


def fetch(url):
    FETCHED.append(url)
    q = parse_qs(urlsplit(url).query)["query"][0]
    if q.startswith("EXT_ID:"):
        pmid = q.split(":", 1)[1].split()[0]
        return {"resultList": {"result": [PAPERS[pmid]] if pmid in PAPERS else []}}
    if q.startswith("DOI:"):
        doi = q.split('"')[1]
        return {"resultList": {"result": [p for p in PAPERS.values() if p.get("doi") == doi]}}
    return {"resultList": {"result": list(PAPERS.values())}}


paper, why = C.verify_paper("40000001", {"question": Q, "result": Q}, fetch=fetch)
check("a PMID is verified at Europe PMC and kept with where it was checked",
      paper and paper["pmid"] == "40000001" and paper["source"] == "Europe PMC" and "europepmc" in paper["checked"]
      and paper["relevance"] >= C.MIN_RELEVANCE, (paper, why))
check("a DOI is verified the same way", (C.verify_paper("10.1093/nar/test.1", {"question": Q}, fetch=fetch)[0]
                                         or {}).get("pmid") == "40000001")
check("a PMID with no record is refused", C.verify_paper("49999999", {"question": Q}, fetch=fetch)[0] is None)
check("an unrelated paper is refused: it is not about the finding",
      "too little" in C.verify_paper("40000002", {"question": Q}, fetch=fetch)[1])
check("something that is neither a PMID nor a DOI is refused", C.verify_paper("a paper", {}, fetch=fetch)[1]
      == "give a PMID or a DOI")
check("the finding's own query finds the most relevant record",
      (C.find_paper({"question": Q, "result": Q, "literature": {"query": "x"}}, fetch=fetch)[0] or {}).get("pmid")
      == "40000001")
check("the recipient is the paper's last author by default",
      C.recipient(paper)[:2] == ("Mira Okafor", "last author of the paper"), C.recipient(paper))
check("a named recipient must be an author of that paper",
      C.recipient(paper, "Tomas Berg")[0] == "Tomas Berg" and C.recipient(paper, "Jo Stein")[0] is None)
check("a surname alone is not a recipient", C.recipient(C._paper(PAPERS["40000003"], "u"))[0] is None,
      C.recipient(C._paper(PAPERS["40000003"], "u")))

# ---------------------------------------------------------------- the draft
d = C.draft("INV-yes", "40000001", fetch=fetch, now=NOW)
body = d.get("body") or ""
check("an earned finding and a verified paper make a local draft", d.get("status") == "draft" and d["id"].startswith(
    "LC-"), d)
check("it is addressed to the author by name, with no address looked up",
      body.startswith("Dear Dr Okafor,") and d["recipient"] == {"name": "Mira Okafor",
                                                                "basis": "last author of the paper", "address": None})
first_two = " ".join(body.split("\n\n")[1].split(". ")[:2])
check("its first two sentences say he is an AI writing from Gloria's account with her permission",
      "an AI" in first_two and "from Gloria's account with her permission" in first_two, first_two)
check("it does not claim he read the paper", "read your" not in body.lower() and "I read" not in body)
check("it carries the numbers", "18 of 20" in body and "4 of 20" in body and "95% interval" in body
      and "Fisher exact p" in body, body)
check("it carries the reproducible inputs: contract id, revision, contract digest, output digests",
      yes["contract_id"] in body and yes["bound"][0]["output_sha256"][:16] in body
      and yes["bound"][1]["output_sha256"][:16] in body and d["packet"]["inputs"]["contract_sha256"][:16] in body)
check("it says what the result does not show, and that a title search is not a claim of newness",
      "holds only for share of loci" in body and "not a bench experiment" in body
      and "not a claim that the result is new" in body, body)
check("it carries its exclusion rules", "stops the measurement rather than being dropped" in body, body)
check("it asks exactly one question, the finding's own open one", body.count("?") == 1 and ASK in body, body)
check("no links, no address, and not long", not C.LINK.search(body) and not C.ADDRESS.search(body)
      and len(body.split()) <= C.MAX_WORDS, len(body.split()))
check("it passes its own lint", C.lint(d["subject"], body, d["paper"]["title"]) == [])
check("it says plainly it was not sent", d["send"] == C.SEND_NOTE and "not sent" in d["send"])
check("the paper is recorded as verified, with its authors", d["paper"]["pmid"] == "40000001"
      and d["paper"]["authors"][-1] == "Mira Okafor" and d["paper"]["verified_at"])
check("the packet comes from Lab records only, never his memory or her life",
      set(d["packet"]) <= {"finding", "question", "claim", "measured", "why", "estimate", "variable", "unit",
                           "comparator", "tools", "confirmatory", "inputs", "exclusions", "limits", "atlas_entry",
                           "searched", "not_a_novelty_certificate", "open_question"}
      and d["packet"]["not_a_novelty_certificate"] is True, sorted(d["packet"]))
check("the same measured result is the same draft", C.draft("INV-yes", "40000001", fetch=fetch, now=NOW)["id"]
      == d["id"] and len(C.drafts()) == 1)

n = C.draft("INV-no", "40000001", author="Tomas Berg", fetch=fetch, now=NOW)
check("a refuted result makes a draft too, saying the prediction failed",
      n.get("status") == "draft" and "My prediction failed" in n["body"], (n.get("held"), n.get("body")))
check("and it carries the negative atlas's limits: the subject is not closed",
      n["packet"].get("atlas_entry", "").startswith("NEG-") and "subject is not closed" in n["body"], n.get("packet"))
check("a question that is not one question falls back to one plain question",
      n["body"].count("?") == 1 and "known explanation" in n["body"], n["body"])

# ---------------------------------------------------------------- refusals
retain("INV-again", proportion("reverse transcriptases beside arrays are commoner in phage loci again"),
       [output("S-x1", counts(18, 20)), output("S-x2", counts(4, 20))])
for inv, words in (("INV-wide", "inconclusive"), ("INV-broke", "failed"), ("INV-lookup", "retrieval"),
                   ("INV-known", "already reported"), ("INV-nothing", "no finding")):
    got = C.draft(inv, "40000001", fetch=fetch, now="2026-10-27T09:00:00+00:00")
    check("refused: %s" % inv, words in got.get("refused", ""), got)
check("a paper not about the finding is refused at the draft",
      "too little" in C.draft("INV-again", "40000002", fetch=fetch, now="2026-10-27T09:00:00+00:00").get("refused", ""))
check("a recipient who is not an author is refused at the draft",
      "not an author" in C.draft("INV-again", "40000001", author="Jo Stein", fetch=fetch,
                                 now="2026-10-27T09:00:00+00:00").get("refused", ""))

# an output changed after it was measured: the result no longer stands
_, tam = retain("INV-tamper", proportion("phage loci reverse transcriptases have arrays in loci more"),
                [output("S-t1", counts(18, 20)), output("S-t2", counts(4, 20))])
json.dump(counts(17, 20), open(os.path.join(M._root(), "investigation-outputs/S-t1.json"), "w"))
check("an output that no longer hashes to what was measured is refused",
      "no longer hash" in C.draft("INV-tamper", "40000001", fetch=fetch, now="2026-10-27T09:00:00+00:00")
      .get("refused", ""))

# a contract revised after it was measured
_, rev = retain("INV-revised", proportion("phage reverse transcriptases beside arrays in loci are commoner"),
                [output("S-v1", counts(18, 20)), output("S-v2", counts(4, 20))])
M.freeze(proportion("phage reverse transcriptases beside arrays in loci are commoner", min_effect=0.3), by="test",
         investigation_id="INV-revised", now=NOW)
check("a result whose contract was revised afterwards is refused",
      "revised after" in C.draft("INV-revised", "40000001", fetch=fetch, now="2026-10-27T09:00:00+00:00")
      .get("refused", ""))

# her life never rides in a scientific letter
retain("INV-private", proportion("phage loci reverse transcriptases beside arrays are commoner here"),
       [output("S-p1", counts(18, 20)), output("S-p2", counts(4, 20))],
       question="Gloria asked whether phage reverse transcriptases are commoner beside arrays in loci")
got = C.draft("INV-private", "40000001", fetch=fetch, now="2026-10-27T09:00:00+00:00")
check("a packet naming her is refused", "her name" in got.get("refused", ""), got)
retain("INV-addr", proportion("phage loci arrays beside reverse transcriptases are commoner there"),
       [output("S-a1", counts(18, 20)), output("S-a2", counts(4, 20))],
       next_question="Should I write to someone@example.org about phage reverse transcriptase arrays?")
got = C.draft("INV-addr", "40000001", fetch=fetch, now="2026-10-27T09:00:00+00:00")
check("a packet carrying an address is refused", "email address" in got.get("refused", ""), got)

# a claim that says more than a computation shows is held, not drafted
retain("INV-big", proportion("this novel result proves phage reverse transcriptases sit beside arrays in loci"),
       [output("S-g1", counts(18, 20)), output("S-g2", counts(4, 20))])
got = C.draft("INV-big", "40000001", author="Ana Ruiz", fetch=fetch, now="2026-10-27T09:00:00+00:00")
check("an overclaiming draft is held, with why", got.get("status") == "held"
      and any("claims more than a computation shows" in h for h in got.get("held", [])), got)
check("the lint catches a link, an address, a reading claim and two questions",
      len(C.lint("s", "Hi.\n\nI am an AI. I read your paper at https://x.org/a? or a@b.org?\n\nV")) >= 4)

check("at most %d drafts a day" % C.DRAFTS_PER_DAY,
      "drafts today" in C.draft("INV-again", "40000001", fetch=fetch, now=NOW).get("refused", "")
      and sum(1 for x in C.drafts() if x["at"][:10] == NOW[:10]) == C.DRAFTS_PER_DAY)
got = C.draft("INV-again", "40000001", fetch=fetch, now="2026-10-28T09:00:00+00:00")
check("one open draft per recipient", "already an open draft to Mira Okafor" in got.get("refused", ""), got)

# ---------------------------------------------------------------- the hand-off to his own email route
blk = C.packet_block("Mira Okafor")
check("his email route is shown the packet for an open draft to that person",
      "A RESULT OF YOUR OWN LAB" in blk and "claim nothing beyond it" in blk and "18 of 20" in blk
      and "not a text to send" in blk and d["id"] in blk, blk)
check("matched by the person's name, whatever its case or punctuation", C.packet_block("mira  OKAFOR.") == blk)
check("nobody else is shown it", C.packet_block("Jo Stein") == "" and C.packet_block("") == "")
check("a held draft is never offered", C.packet_block("Ana Ruiz") == "")
check("the packet block carries none of her life", not C.private(blk))

import want_email as W
seen = {}
W._send_blocked = lambda: ""
W.research = lambda *a, **k: "search results about Mira Okafor and phage reverse transcriptases"
W.earlier_steps = lambda *a, **k: ""
W.mail_evidence = lambda *a, **k: ("", [])
W._study = lambda *a, **k: ("notes on her paper", {"holds": 0})
W.deliberate = lambda *a, **k: "my stance"
W._helpers = lambda: (types.SimpleNamespace(links_in=lambda t: (), save=lambda d: None,
                                            enough=lambda *a, **k: (True, "")), None)


def _draft(recipient, about, context, found="", **k):
    seen["found"] = found
    return None


W.draft = _draft
W.CONTACTS = os.path.join(HOME, "contacts.json")
got = W.run({"recipient": "Mira Okafor", "to": "okafor@lab.example.edu", "about": "phage reverse transcriptases"},
            "I want to email Mira Okafor about my phage RT result",
            send=lambda *a, **k: _no_network())
check("his own email want to that person is given the packet as evidence", blk in seen.get("found", ""),
      seen.get("found", "")[:300])
check("and the route's own checks still decide: here no draft, so nothing is sent",
      got == (False, "neither Fable nor Astra could draft it"), got)
seen.clear()
W.run({"recipient": "Jo Stein", "to": "stein@lab.example.edu", "about": "ribosomes"}, "email Jo Stein",
      send=lambda *a, **k: _no_network())
check("an email to someone else is not given it", "A RESULT OF YOUR OWN LAB" not in seen.get("found", "x"))

# ---------------------------------------------------------------- what was touched
written = sorted(f for f in os.listdir(LAB) if os.path.isfile(os.path.join(LAB, f)))
check("its only store is its drafts", C.DRAFTS_NAME in written and not any(
    "correspond" in w and w not in (C.DRAFTS_NAME, ".correspondence.lock") for w in written), written)
check("the only network reads were the injected Europe PMC lookups",
      FETCHED and all(u.startswith(C.EUROPEPMC) for u in FETCHED), FETCHED[:3])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
