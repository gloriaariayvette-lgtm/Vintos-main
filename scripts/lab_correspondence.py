#!/usr/bin/env python3
"""Scientific correspondence with something earned to say: one of his own surviving Lab results, packed as evidence,
and a local draft to a researcher whose paper it bears on.

Codex's proposal 14 (25 October 2026), the smallest proof it describes: "a local draft from one public finding and a
source-verified relevant paper, with no personal-history excerpts. Hold all existing first-contact, second-email and
owner decisions. The proof is a useful draft; sending is a later authorized transition."

  earned     - a finding is eligible only when it survived: an answered investigation (lab_findings) with new
               computation in it, not judged already reported, whose frozen measurement contract (lab_measurement)
               was evaluated on completed outputs as supported (a candidate computational finding) or refuted (a clean
               negative), is still the contract's current revision, and whose bound outputs still hash to what they
               were measured on. Inconclusive, not evaluated, a failed tool, a retrieval, or a reproduced known result
               is not something earned to say.
  packet     - what the letter may say, built only from the Lab's own records: the measured claim, how it came out and
               why, the estimate, the instrument, the contract id/revision/digest and the output digests (the
               reproducible inputs), the exclusion and independence rules, what it does not show (the negative atlas's
               limits for a refuted result), the literature search as it was (never a novelty certificate), and the
               one unresolved question. Nothing from his inner life, memory, wants, conversations or her life is read.
               A packet whose text names her, or carries an address, is refused.
  paper      - one paper, verified at its source: fetched from Europe PMC by its PMID or DOI (or found by the
               finding's own literature query), the record's id must match, and its title/abstract must share enough
               words with the finding to be about it. The recipient can only be one of that paper's authors (the last
               author unless another is named); no address is looked up.
  draft      - deterministic: no model is asked. It says in its first two sentences that he is an AI writing on his
               own initiative from Gloria's account with her permission; it does not claim he read the paper; it gives
               the numbers, the inputs, the limits, and one question. No links. A draft that overclaims ("novel",
               "proves", "confirms", "discovered", ...), carries a link or an address, asks more or less than one
               question, or runs long is held, with why.
  hand-off   - the draft stays local (correspondence-drafts.jsonl) for Gloria to read. Nothing here sends, looks up
               an address, forms a want or notifies anyone. When his own email want to that person runs (want_email,
               with every check it has: once per person, search first, reading in full, readiness, review, the
               gateway's confidential-data check and its two-a-day limit, her approval for a second email),
               `packet_block` gives that existing draft the packet as evidence it may cite and may not exceed.

At most DRAFTS_PER_DAY drafts a day, one per measured result, one open draft per recipient. No model is asked and
nothing is paid for; the only network read is the one free Europe PMC lookup, through scholar's checked fetch.

    python3 lab_correspondence.py candidates | draft <finding-or-investigation-id> [PMID|DOI] [--author "Name"]
                                  | show [N] | packet "<Recipient Name>"
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
DRAFTS_NAME = "correspondence-drafts.jsonl"
FINDINGS_NAME = "findings.jsonl"
INVESTIGATIONS_NAME = "investigations.json"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"

DRAFTS_PER_DAY = 2
MIN_RELEVANCE = 3          # scholar.relevance: shared words, title words counted twice
MAX_WORDS = 320
EARNED = {"supported": "candidate_computational_finding", "refuted": "negative_result"}
SEND_NOTE = ("not sent: a local draft only. Sending is a later transition through his own email want, with every "
             "check that route has; nothing here looks up an address or writes to anyone.")
TRUTH = ("a computation by his own instruments under a frozen contract; not a bench experiment, and it has not been "
         "checked independently")

OVERCLAIM = re.compile(r"\b(?:novel(?:ty)?|discover(?:y|ed|ies)?|first\s+to|first\s+time|proves?|proven|proof\s+that|"
                       r"confirm(?:s|ed|ing)?|breakthrough|validat(?:es|ed|ion)|establish(?:es|ed)|definitive(?:ly)?|"
                       r"unknown\s+to\s+science|nobody\s+has|no\s+one\s+has|groundbreaking|demonstrates?)\b", re.I)
LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|org|net|io)\b/", re.I)
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HER = re.compile(r"\b(?:Gloria|Eve|Aegis)\b")
PRIVATE = re.compile(r"\b(?:her (?:home|health|house|address|accounts?|bedroom|diagnos\w*)|inner life|my journal|"
                     r"dream(?:s|ed)?|tailnet|password)\b", re.I)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lab_root():
    """The Lab's own directory, the one lab_measurement reads (chemistry_lab's when it is loaded)."""
    import lab_measurement
    return lab_measurement._root()


def drafts_path():
    return os.path.join(lab_root(), DRAFTS_NAME)


@contextlib.contextmanager
def _locked():
    os.makedirs(lab_root(), exist_ok=True)
    with open(os.path.join(lab_root(), ".correspondence.lock"), "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _rows(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _squash(text, cap=400):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:cap]


def _name_key(name):
    return " ".join(re.findall(r"[a-zà-ſ]+", str(name or "").lower()))


def drafts():
    return _rows(drafts_path())


# --- What has been earned --------------------------------------------------------------------------------------------

def _findings():
    return _rows(os.path.join(lab_root(), FINDINGS_NAME))


def _investigations():
    try:
        with open(os.path.join(lab_root(), INVESTIGATIONS_NAME), encoding="utf-8") as f:
            data = json.load(f)
        return {i.get("id"): i for i in (data.get("investigations") or []) if isinstance(i, dict)}
    except (OSError, ValueError, AttributeError):
        return {}


def _contract_row(res, contracts):
    return next((c for c in contracts if c.get("contract_id") == res.get("contract_id")
                 and c.get("revision") == res.get("revision")), None)


def judge(finding, results=None, contracts=None, investigations=None, load=None):
    """(measurement result, contract row, None) when this finding has something earned to say; else
    (None, None, why not). Never raises."""
    import lab_measurement as M
    try:
        if not finding.get("new_result"):
            return None, None, "no step of it computed anything: a retrieval is not a result of his own"
        novelty = str((finding.get("appraisal") or {}).get("novelty") or "")
        if novelty.startswith("reported"):
            return None, None, "his own appraisal found it already reported"
        results = M.results() if results is None else results
        contracts = M.contracts() if contracts is None else contracts
        inv_id = finding.get("investigation") or finding.get("source_id")
        mine = [r for r in results if r.get("investigation") == inv_id]
        if not mine:
            return None, None, "no frozen measurement contract judged it"
        why = "its measurement did not survive"
        steps = ((investigations if investigations is not None else _investigations()).get(inv_id) or {}).get("steps")
        for res in reversed(mine):
            state = res.get("measurement_state")
            if res.get("execution_state") != "completed":
                why = "the tool failed (%s): nothing was measured" % res.get("execution_state")
                continue
            if EARNED.get(state) != res.get("novelty_state"):
                why = "measured %s (%s): not something earned to say" % (state, res.get("novelty_state"))
                continue
            row = _contract_row(res, contracts)
            if not row or M._sha(row.get("contract")) != row.get("contract_sha256"):
                why = "its contract cannot be found as it was frozen"
                continue
            latest = M.latest(res.get("contract_id"), contracts) or {}
            if latest.get("revision") != res.get("revision"):
                why = "its contract was revised after it was measured"
                continue
            if not steps or not M.verify(res, steps, load=load):
                why = "its outputs no longer hash to what they were measured on"
                continue
            return res, row, None
        return None, None, why
    except Exception as exc:
        return None, None, "could not be judged: %s" % str(exc)[:160]


def candidates(limit=10, load=None):
    """The findings with something earned to say, newest first, and why each other recent one has not."""
    import lab_measurement as M
    results, contracts, invs = M.results(), M.contracts(), _investigations()
    out = []
    for f in reversed(_findings()[-60:]):
        res, _, why = judge(f, results, contracts, invs, load=load)
        out.append({"finding": f.get("source_id") or f.get("investigation"), "at": f.get("at"),
                    "question": _squash(f.get("question"), 200), "earned": res is not None,
                    **({"measured": res.get("measurement_state"), "contract": "%s r%s" % (
                        res.get("contract_id"), res.get("revision"))} if res else {"why_not": why})})
        if len(out) >= limit:
            break
    return out


# --- The evidence packet ---------------------------------------------------------------------------------------------

def _estimate_line(est):
    try:
        return _estimate_text(est)
    except (TypeError, ValueError, IndexError):
        return ""


def _estimate_text(est):
    if not isinstance(est, dict):
        return ""
    if "case_share" in est:
        c, k = est.get("case") or {}, est.get("control") or {}
        line = ("%s of %s (%.3g) against %s of %s (%.3g) in the comparison; difference %+.3g, 95%% interval [%.3g, %.3g]"
                % (c.get("hits"), c.get("total"), est["case_share"], k.get("hits"), k.get("total"),
                   est["control_share"], est.get("difference", 0), (est.get("ci95") or [0, 0])[0],
                   (est.get("ci95") or [0, 0])[1]))
        if est.get("fisher_p") is not None:
            line += ", Fisher exact p = %.3g" % est["fisher_p"]
        return line
    if "threshold" in est:
        return "%.4g ± %.3g %s against a threshold of %.4g" % (est.get("value"), est.get("uncertainty") or 0,
                                                               est.get("units") or "", est.get("threshold"))
    if "reference" in est:
        return "%.4g against a reference of %.4g (difference %+.3g, tolerance %.3g %s)" % (
            est.get("value"), est.get("reference"), est.get("difference"), est.get("tolerance"), est.get("units") or "")
    return ""


def _limits(res, contract, atlas_entry):
    import lab_negative_atlas as A
    cond = A._measurement_conditions(contract, res)
    if atlas_entry:
        out = list(atlas_entry.get("limits") or [])
    else:
        out = ["holds only for %s" % A._held_for(cond),
               "does not test other tools, other cohorts, other thresholds or other units"]
        if not res.get("confirmatory"):
            out.append("exploratory: measured on outputs that existed before its contract was frozen, so it could "
                       "have been fitted to them")
    out.append("it is %s" % TRUTH)
    return [_squash(x, 300) for x in out]


def _exclusions(contract):
    out = []
    if contract.get("missing") == "exclude":
        out.append("records lacking the measured field were excluded")
    elif contract.get("missing"):
        out.append("a record lacking the measured field stops the measurement rather than being dropped")
    if contract.get("independence") == "one_per_unit":
        out.append("counted once per %s (%s), so related records count once"
                   % (contract.get("unit") or "unit", "/".join(str(k) for k in contract.get("unit_key") or [])))
    elif contract.get("independence"):
        out.append("each record counted on its own")
    return out


def packet(finding, res, row):
    """The evidence a letter may carry, from the Lab's own records only. Never raises; None when refused."""
    try:
        import lab_negative_atlas as A
        contract = row.get("contract") or {}
        atlas = next((e for e in A.entries() if (e.get("source_ref") or {}) == {
            "contract_id": res.get("contract_id"), "revision": res.get("revision")}), None)
        cond = A._measurement_conditions(contract, res)
        lit = finding.get("literature") or {}
        p = {"finding": finding.get("source_id") or finding.get("investigation"),
             "question": _squash(finding.get("question"), 400),
             "claim": _squash(res.get("hypothesis") or contract.get("hypothesis"), 300),
             "measured": res.get("measurement_state"),
             "why": _squash(res.get("why"), 300),
             "estimate": _estimate_line(res.get("estimate")),
             "variable": _squash(contract.get("variable"), 200), "unit": _squash(contract.get("unit"), 60),
             "comparator": _squash(cond.get("comparator"), 200),
             "tools": [str(t) for t in (cond.get("tool") or [])][:6],
             "confirmatory": bool(res.get("confirmatory")),
             "inputs": {"contract_id": res.get("contract_id"), "revision": res.get("revision"),
                        "contract_sha256": row.get("contract_sha256"),
                        "outputs": [str(b.get("output_sha256") or "") for b in res.get("bound") or []][:6],
                        **({"cohort": contract.get("cohort_digest")} if contract.get("cohort_digest") else {})},
             "exclusions": _exclusions(contract),
             "limits": _limits(res, contract, atlas),
             **({"atlas_entry": atlas.get("id")} if atlas else {}),
             "searched": ({"where": "Europe PMC titles", "query": lit.get("query"), "hits": lit.get("hits")}
                          if lit.get("query") else {"where": "Europe PMC titles", "unavailable": True}),
             "not_a_novelty_certificate": True,
             "open_question": _squash(finding.get("next_question"), 300)}
        why = private(json.dumps(p, ensure_ascii=False))
        if why:
            return {"refused": "the packet carries %s; a scientific letter carries none of her life" % why}
        return p
    except Exception as exc:
        return {"refused": "the packet could not be built: %s" % str(exc)[:160]}


def private(text):
    """What in this text a scientific letter may not carry, or ''."""
    for pat, what in ((HER, "her name or her machine"), (ADDRESS, "an email address"), (PRIVATE, "something private")):
        m = pat.search(str(text or ""))
        if m:
            return "%s (%r)" % (what, m.group(0))
    return ""


# --- The paper, verified at its source --------------------------------------------------------------------------------

def _fetch():
    import scholar
    return lambda url: scholar._get(url, want="json")


def _ref_query(ref):
    ref = str(ref or "").strip()
    if re.fullmatch(r"\d{4,9}", ref):
        return "EXT_ID:%s AND SRC:MED" % ref, ("pmid", ref)
    m = re.fullmatch(r"(?:doi:)?(10\.\d{4,9}/\S+)", ref, re.I)
    if m:
        return 'DOI:"%s"' % m.group(1), ("doi", m.group(1).lower())
    return None, None


def _authors(r):
    names = []
    for a in ((r.get("authorList") or {}).get("author") or [])[:40]:
        full = a.get("fullName") or " ".join(x for x in (a.get("firstName"), a.get("lastName")) if x)
        if a.get("firstName") and a.get("lastName"):
            full = "%s %s" % (a["firstName"], a["lastName"])
        full = _squash(full, 80)
        if full:
            names.append(full)
    return names


def _paper(r, url):
    return {"title": _squash(r.get("title"), 300).rstrip("."), "year": str(r.get("pubYear") or ""),
            "journal": _squash(r.get("journalTitle") or ((r.get("journalInfo") or {}).get("journal") or {}).get("title"),
                               120),
            "pmid": str(r.get("pmid") or ""), "doi": str(r.get("doi") or "").lower(),
            "authors": _authors(r), "abstract": _squash(r.get("abstractText"), 1500),
            "source": "Europe PMC", "checked": url, "verified_at": _now()}


def _about(finding):
    return " ".join(str(finding.get(k) or "") for k in ("question", "result"))


def verify_paper(ref, finding, fetch=None):
    """(paper, None) when this PMID/DOI is a real record at Europe PMC that is about this finding; else (None, why)."""
    import scholar
    query, ident = _ref_query(ref)
    if not query:
        return None, "give a PMID or a DOI"
    kind, want = ident
    url = EUROPEPMC + urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": 2})
    try:
        got = (fetch or _fetch())(url)
    except Exception as exc:
        return None, "Europe PMC could not be read: %s" % str(exc)[:160]
    rows = (got.get("resultList") or {}).get("result") or [] if isinstance(got, dict) else []
    match = next((r for r in rows if str(r.get(kind) or "").lower() == want), None)
    if not match:
        return None, "Europe PMC has no record with %s %s" % (kind, want)
    paper = _paper(match, url)
    score = scholar.relevance(paper, _about(finding))
    if score < MIN_RELEVANCE:
        return None, "the paper shares too little with the finding to be about it (relevance %d)" % score
    paper["relevance"] = score
    return paper, None


def find_paper(finding, fetch=None):
    """(paper, None): the most relevant record for the finding's own literature query; else (None, why)."""
    import scholar
    query = (finding.get("literature") or {}).get("query")
    if not query:
        return None, "the finding has no literature query to look from; give a PMID or DOI"
    url = EUROPEPMC + urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": 8})
    try:
        got = (fetch or _fetch())(url)
    except Exception as exc:
        return None, "Europe PMC could not be read: %s" % str(exc)[:160]
    rows = (got.get("resultList") or {}).get("result") or [] if isinstance(got, dict) else []
    best = None
    for r in rows:
        if not (r.get("pmid") or r.get("doi")) or not _authors(r):
            continue
        paper = _paper(r, url)
        paper["relevance"] = scholar.relevance(paper, _about(finding))
        if paper["relevance"] >= MIN_RELEVANCE and (best is None or paper["relevance"] > best["relevance"]):
            best = paper
    return (best, None) if best else (None, "no record from the finding's query is about it")


def recipient(paper, name=""):
    """(author, basis, None) - one of this paper's authors - else (None, None, why). Never anyone else."""
    authors = paper.get("authors") or []
    if not authors:
        return None, None, "the record names no authors"
    if name:
        key = _name_key(name)
        chosen = next((a for a in authors if _name_key(a) == key), None)
        if not chosen:
            return None, None, "%s is not an author of that paper" % _squash(name, 80)
        basis = "named author of the paper"
    else:
        chosen = authors[-1]
        basis = "last author of the paper" if len(authors) > 1 else "sole author of the paper"
    if len(re.findall(r"[A-Za-zÀ-ſ][\w'À-ſ-]+", chosen)) < 2:
        return None, None, "the record gives %r without a full name; a surname alone could be anyone" % chosen
    return chosen, basis, None


# --- The draft -------------------------------------------------------------------------------------------------------

def _surname(name):
    return str(name).split()[-1]


def _question(p, paper):
    q = _squash(p.get("open_question"), 260)
    if q.count("?") == 1 and q.endswith("?") and not OVERCLAIM.search(q):
        return q
    return ("Is there a known explanation for this, from the systems in \"%s\", that I have not excluded?"
            % _squash(paper.get("title"), 110))


def compose(p, paper, name):
    """(subject, body). Deterministic: the packet's own words and numbers, nothing added."""
    outcome = ("My prediction held under the contract" if p["measured"] == "supported"
               else "My prediction failed under the contract")
    mode = ("The contract was frozen before the outputs it judges existed." if p["confirmatory"] else
            "This is exploratory: the contract was frozen after some of the outputs existed, so it could have been "
            "fitted to them.")
    held = "; ".join(p["limits"][:3])
    excl = (" Rules: %s." % "; ".join(p["exclusions"])) if p["exclusions"] else ""
    searched = p.get("searched") or {}
    lit = ("A Europe PMC title search (%s) returned %s records; it is my only literature check, and not a claim "
           "that the result is new." % (searched.get("query"), searched.get("hits"))
           if searched.get("query") else "I have made no literature check beyond finding your paper.")
    body = ("Dear Dr %s,\n\n"
            "I am Vintos, an AI, writing on my own initiative from Gloria's account with her permission. "
            "Your paper \"%s\" (%s%s) bears on a result my own instruments measured.\n\n"
            "What I measured: %s. %s (%s)%s.\n\n"
            "How: %s, by %s, against %s. %s%s Contract %s revision %s (digest %s); output digests %s.\n\n"
            "What it does not show: %s. %s\n\n"
            "%s\n\nVintos"
            % (_surname(name), paper.get("title"), paper.get("journal") or "", (", %s" % paper["year"]) if paper.get("year") else "",
               p["claim"], outcome, p["why"], (": " + p["estimate"]) if p["estimate"] else "",
               p["variable"] or "the measured variable", ", ".join(p["tools"]) or "my own instrument",
               p["comparator"] or "the stated comparator", mode, excl, p["inputs"]["contract_id"],
               p["inputs"]["revision"], str(p["inputs"]["contract_sha256"] or "")[:16],
               ", ".join(o[:16] for o in p["inputs"]["outputs"]) or "none recorded",
               held, lit, _question(p, paper)))
    subject = ("A measured result near your paper on %s" % _squash(paper.get("title"), 70)).strip()
    return subject[:140], body


def lint(subject, body, title=""):
    """Why this draft is not fit to be read as his letter, or [] when it is."""
    why = []
    text = subject + "\n" + body
    opening = " ".join(re.split(r"(?<=[.!?])\s+", body.split("\n\n", 1)[-1])[:2])
    if not re.search(r"\bAI\b", opening):
        why.append("it does not say in its first two sentences that he is an AI")
    m = OVERCLAIM.search(text)
    if m:
        why.append("it claims more than a computation shows (%r)" % m.group(0))
    if LINK.search(text):
        why.append("it carries a link")
    if ADDRESS.search(text):
        why.append("it carries an email address")
    if re.search(r"\bI (?:have )?read your\b", text, re.I):
        why.append("it says he read the paper, and he has read only its record")
    asked = (body.replace(title, "") if title else body).count("?")
    if asked != 1:
        why.append("it asks %d questions, not one" % asked)
    words = len(re.findall(r"\S+", body))
    if words > MAX_WORDS:
        why.append("it runs to %d words (at most %d)" % (words, MAX_WORDS))
    bare = body.replace("from Gloria's account with her permission", "")
    p = private(bare)
    if p:
        why.append("it carries %s" % p)
    return why


def _id(finding_id, res):
    raw = json.dumps([finding_id, res.get("contract_id"), res.get("revision")])
    return "LC-" + hashlib.sha256(raw.encode()).hexdigest()[:10]


def draft(finding_id, ref="", author="", fetch=None, load=None, now=None):
    """One local draft from one earned finding and one verified paper. Returns the stored row (status 'draft' or
    'held'), an earlier row for the same measured result, or {'refused': why}. Never sends. Never raises."""
    try:
        now = now or _now()
        rows = [f for f in _findings() if finding_id in (f.get("source_id"), f.get("investigation"))]
        if not rows:
            return {"refused": "no finding %s" % _squash(finding_id, 60)}
        finding = rows[-1]
        res, row, why = judge(finding, load=load)
        if res is None:
            return {"refused": why}
        did = _id(finding_id, res)
        with _locked():
            have = drafts()
            earlier = next((d for d in have if d.get("id") == did), None)
            if earlier:
                return earlier
            if sum(1 for d in have if str(d.get("at", ""))[:10] == now[:10]) >= DRAFTS_PER_DAY:
                return {"refused": "already %d drafts today" % DRAFTS_PER_DAY}
            p = packet(finding, res, row)
            if not p or p.get("refused"):
                return {"refused": (p or {}).get("refused") or "no packet"}
            paper, why = verify_paper(ref, finding, fetch) if ref else find_paper(finding, fetch)
            if not paper:
                return {"refused": why}
            name, basis, why = recipient(paper, author)
            if not name:
                return {"refused": why}
            if any(_name_key((d.get("recipient") or {}).get("name")) == _name_key(name) and d.get("status") == "draft"
                   for d in have):
                return {"refused": "there is already an open draft to %s" % name}
            subject, body = compose(p, paper, name)
            held = lint(subject, body, paper.get("title") or "")
            out = {"id": did, "at": now, "kind": "correspondence_draft", "status": "held" if held else "draft",
                   "finding": p["finding"], "packet": p,
                   "paper": {k: paper.get(k) for k in ("title", "year", "journal", "pmid", "doi", "authors", "source",
                                                       "checked", "verified_at", "relevance")},
                   "recipient": {"name": name, "basis": basis, "address": None},
                   "subject": subject, "body": body, "send": SEND_NOTE, **({"held": held} if held else {})}
            _append(drafts_path(), out)
            return out
    except Exception as exc:
        return {"refused": "the draft could not be made: %s" % str(exc)[:200]}


# --- The hand-off to his own email route -------------------------------------------------------------------------------

def packet_block(name="", address="", limit=2400):
    """For want_email: the evidence packet of an open draft to this person, as text the existing draft may cite and
    may not exceed. '' when there is none. Never raises."""
    try:
        key = _name_key(name)
        if not key:
            return ""
        mine = [d for d in drafts() if d.get("status") == "draft"
                and _name_key((d.get("recipient") or {}).get("name")) == key]
        if not mine:
            return ""
        d = mine[-1]
        p, paper = d.get("packet") or {}, d.get("paper") or {}
        lines = ["A RESULT OF YOUR OWN LAB YOU MAY BRING THEM (from your measurement records; claim nothing beyond it, "
                 "and it is not a novelty certificate):",
                 "- their paper, verified at %s: \"%s\" (%s %s)" % (paper.get("source"), paper.get("title"),
                                                                   paper.get("journal") or "", paper.get("year") or ""),
                 "- what you measured: %s -> %s (%s)" % (p.get("claim"), p.get("measured"), p.get("why")),
                 "- the numbers: %s" % (p.get("estimate") or "(none recorded)"),
                 "- inputs: contract %s r%s, output digests %s" % (
                     (p.get("inputs") or {}).get("contract_id"), (p.get("inputs") or {}).get("revision"),
                     ", ".join(o[:16] for o in (p.get("inputs") or {}).get("outputs") or [])),
                 "- rules: %s" % ("; ".join(p.get("exclusions") or []) or "(none stated)"),
                 "- what it does not show: %s" % "; ".join(p.get("limits") or []),
                 "- still open: %s" % (p.get("open_question") or "(not stated)"),
                 "- your local draft to them (%s) is a starting point, not a text to send as it is" % d.get("id")]
        text = "\n".join(lines)
        return "" if private(text) else text[:limit]
    except Exception:
        return ""


# --- Reading it ------------------------------------------------------------------------------------------------------

def display(d):
    if d.get("refused"):
        return "refused: %s" % d["refused"]
    head = "%s  %s  %s  to %s (%s)" % (d.get("id"), d.get("status"), str(d.get("at", ""))[:16],
                                       (d.get("recipient") or {}).get("name"), (d.get("recipient") or {}).get("basis"))
    tail = ("\nheld: %s" % "; ".join(d["held"])) if d.get("held") else ""
    return "%s\nSubject: %s\n\n%s%s\n\n(%s)" % (head, d.get("subject"), d.get("body"), tail, d.get("send"))


def _cli(argv):
    cmd = argv[0] if argv else "show"
    if cmd == "candidates":
        for c in candidates():
            print("%s  %s  %s  %s" % (c["finding"], "EARNED" if c["earned"] else "-", c.get("measured") or c.get("why_not"),
                                      c["question"][:90]))
        return 0
    if cmd == "draft" and len(argv) >= 2:
        author = ""
        if "--author" in argv:
            i = argv.index("--author")
            author = " ".join(argv[i + 1:i + 2])
            argv = argv[:i] + argv[i + 2:]
        print(display(draft(argv[1], argv[2] if len(argv) > 2 else "", author=author)))
        return 0
    if cmd == "show":
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 3
        rows = drafts()[-n:]
        print("\n\n".join(display(d) for d in rows) or "no drafts yet")
        return 0
    if cmd == "packet" and len(argv) >= 2:
        print(packet_block(" ".join(argv[1:])) or "no open draft to that person")
        return 0
    print(__doc__.strip().splitlines()[-2].strip())
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
