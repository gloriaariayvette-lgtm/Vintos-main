#!/usr/bin/env python3
"""Evidence for the parts of a Lab question its review could not answer (T-17420bd6, Gloria, 2026-10-14).

A review's coverage check names what is still missing. Those are the question's unanswered claims. For each, this
searches Europe PMC's open-access full text for the proteins the question names together with the claim's own words,
reads the matching articles as JATS (europepmc.py) and hands the review the passages that bear on the claim, each
with its PMCID and section. The question is never changed: the review is asked again, whole, with that evidence
beside what it already had.

A ledger per question (keyed by the full question's hash) keeps:
    supported   source-checked quotes that answered a claim; carried into the next attempt as prior evidence
    gaps        each claim still unanswered, the searches run for it, and what would justify another attempt
    searches    every search run for the question, with what it found; an identical search is reused, not run
                again, whether or not a hold on the question has expired

outcome() names what a review ended as, so a software failure is never read as a scientific "no".
"""
import datetime, hashlib, json, os, re, tempfile, urllib.parse

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
ROOT = os.path.join(WS, "memory", "chemistry-lab")
LEDGER = os.path.join(ROOT, "claim-evidence.json")
SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"

MAX_CLAIMS = 3
MAX_ARTICLES = 4
PER_CLAIM = 2
PASSAGE_CHARS = 900
TOTAL_CHARS = 7000
REPEAT_DAYS = 30

RESEARCH = ("answered", "partially_supported", "unsupported_by_available_evidence")
# Absence from an annotation, an explicit contradiction, and a target nothing established are three different
# things and were two (Chat's review, 2026-10-14): a feature a record does not list may simply not be annotated.
QUESTION = ("contradicted_premise", "unverified_premise", "wrong_target")
SOFTWARE = ("checker_failed", "context_overflow", "unassessed")
SEARCHABLE = ("partially_supported", "unsupported_by_available_evidence")

# words that say what kind of thing is asked, not what it is about; they make a search match everything
_GENERIC = re.compile(r"^(?:specific|structural|structure|structures|feature|features|role|roles|function|"
                      r"functions|mechanism|mechanisms|facilitate|facilitates|these|their|which|what|whether|"
                      r"through|within|between|about|human|protein|proteins|domain|domains|how|does|that|this|"
                      r"with|from|into|other|various|particular|particularly|evidence|record|records)$", re.I)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _load(path=None):
    try:
        with open(path or LEDGER) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data, path=None):
    path = path or LEDGER
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".claim-evidence-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def question_key(question):
    return hashlib.sha256(str(question or "").encode()).hexdigest()


def outcome(reflection):
    """(status, why). Research outcomes, problems with the question or its target, and the Lab's own failures."""
    r = reflection if isinstance(reflection, dict) else {}
    cov = r.get("coverage_check") if isinstance(r.get("coverage_check"), dict) else {}
    if r.get("coverage_deferred") or r.get("evidence_status") == "deferred" or cov.get("coverage_deferred"):
        return "context_overflow", "the question and its evidence did not fit the checker's context"
    if r.get("assessment_status") == "incomplete" or cov.get("assessment_status") == "incomplete":
        return "checker_failed", str(r.get("validation_failure") or cov.get("validation_failure") or "checker answer invalid")
    premise = r.get("premise_check") if isinstance(r.get("premise_check"), dict) else {}
    if premise.get("issues") and not cov:
        return premise.get("outcome", "unverified_premise"), "; ".join(str(x) for x in premise["issues"])
    entity = r.get("entity_context_check") if isinstance(r.get("entity_context_check"), dict) else {}
    issues = [str(x) for x in entity.get("issues") or []]
    if issues and not cov:
        joined = "; ".join(issues)
        if re.search(r"as one protein|contradict", joined, re.I):
            return "contradicted_premise", joined
        return "wrong_target", joined
    if cov.get("answered") is True:
        return "answered", "every requirement supported by quoted sources"
    if cov.get("answered") is False:
        missing = "; ".join(str(x) for x in cov.get("missing") or [])
        if cov.get("supports"):
            return "partially_supported", missing
        return "unsupported_by_available_evidence", missing
    return "unassessed", str(r.get("answers_question") or "no assessment was recorded")[:300]


def claims(reflection):
    cov = (reflection or {}).get("coverage_check") or {}
    out = []
    for item in cov.get("missing") or []:
        text = " ".join(str(item).split())
        if text and text.casefold() not in {c.casefold() for c in out}:
            out.append(text[:300])
    return out[:MAX_CLAIMS]


def _words(text, exclude=()):
    seen, out = {x.casefold() for x in exclude}, []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", str(text or "")):
        k = w.casefold()
        if len(k) < 4 or _GENERIC.match(k) or k in seen:
            continue
        seen.add(k); out.append(w)
    return out


def entities(inquiry, reflection=None, records=None):
    """The proteins the question is about, as the records and the identity check established them."""
    names = []
    entity = (reflection or {}).get("entity_context_check") or {}
    names += list((entity.get("target_mapping") or {}).keys())
    for row in records or []:
        if not isinstance(row, dict):
            continue
        for gene in row.get("genes") or []:
            value = (gene.get("geneName") or {}).get("value") if isinstance(gene, dict) else None
            if value: names.append(value)
        if row.get("protein_name"): names.append(row["protein_name"])
    names += list(entity.get("symbols") or [])
    for m in re.finditer(r"\b(?:gene|protein_name)\s*:\s*\"?([^\"()]+?)\"?(?=\s+(?:AND|OR|NOT)\b|\s*\)|$)",
                         str((inquiry or {}).get("uniprot_query") or ""), re.I):
        names.append(m.group(1).strip())
    out = []
    for n in names:
        n = " ".join(str(n).split())
        if 2 <= len(n) <= 80 and n.casefold() not in {x.casefold() for x in out}:
            out.append(n)
    return out[:3]


def claim_queries(names, claim):
    if not names:
        return []
    who = "(" + " OR ".join('"%s"' % n.replace('"', "") for n in names) + ")"
    words = _words(claim, exclude=names)
    out = []
    for n in (3, 2):
        if len(words) >= n:
            out.append("%s AND %s AND OPEN_ACCESS:y" % (who, " AND ".join(words[:n])))
    return list(dict.fromkeys(out))


def _lab_transport(url, headers, timeout, max_bytes):
    """link_fetch's transport through the Lab's own HTTP opener (lab_http), which the Lab's suites stub."""
    import urllib.error, urllib.request
    import lab_http
    try:
        response = lab_http.open_request(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    body = response.read(max_bytes + 1) or b""
    over = len(body) > max_bytes
    return (getattr(response, "status", None) or response.getcode(),
            {k.lower(): v for k, v in (response.headers or {}).items()}, body[:max_bytes], over)


def live_fetch():
    """Europe PMC through link_fetch's address checks and byte cap, over the Lab's HTTP opener. Only the Lab's own
    process wires this in (chemistry_lab.py daemon/tick, and the replay); an imported module never reaches out."""
    import link_fetch
    return lambda url, **kw: link_fetch.fetch(url, keep_raw=True, article_route=False, transport=_lab_transport, **kw)


def search(query, fetch):
    """(pmcids, why). Europe PMC search, open-access hits that have a PMCID."""
    url = SEARCH + urllib.parse.urlencode({"query": query, "format": "json", "resultType": "lite", "pageSize": 5})
    r = fetch(url)
    if not r.get("fetched"):
        return None, "search not read: %s" % (r.get("why") or r.get("kind"))
    try:
        data = json.loads(r.get("raw") or r.get("text") or "")
    except ValueError:
        return None, "search answer was not JSON"
    found = [str(x.get("pmcid")) for x in ((data.get("resultList") or {}).get("result") or [])
             if isinstance(x, dict) and x.get("pmcid") and str(x.get("isOpenAccess", "Y")).upper() == "Y"]
    return found, "%d open-access full texts" % len(found)


def passages(article, words, limit=PER_CLAIM):
    """The paragraphs of an article that share the most of the claim's words; at least two, or the one there is."""
    need = 2 if len(words) >= 2 else 1
    keys = [w.casefold() for w in words]
    scored = []
    for section in article.get("sections") or []:
        for para in re.split(r"\n\s*\n", str(section.get("text") or "")):
            para = " ".join(para.split())
            low = para.casefold()
            hits = sum(1 for k in keys if k in low)
            if hits >= need and len(para) > 80:
                scored.append((hits, section.get("heading") or "", para))
    scored.sort(key=lambda x: -x[0])
    out = []
    for hits, heading, para in scored[:limit]:
        text = para if len(para) <= PASSAGE_CHARS else para[:PASSAGE_CHARS].rsplit(". ", 1)[0] + ". [passage shortened]"
        out.append({"section": heading, "text": text, "matched_words": hits})
    return out


def gather(inquiry, reflection, records=None, fetch=None, ledger_path=None, now=None):
    """FULLTEXT passages for the review's unanswered claims, and what was searched, reused and skipped."""
    status, why = outcome(reflection)
    result = {"status": status, "FULLTEXT": [], "searches": [], "reused": [], "failures": [], "claims": []}
    if status not in SEARCHABLE:
        result["skipped"] = "%s: %s" % (status, why)
        return result
    question = str((inquiry or {}).get("question") or "")
    names = entities(inquiry, reflection, records)
    wanted = claims(reflection)
    result["claims"] = wanted
    if not names or not wanted:
        result["skipped"] = "no named protein to search for" if not names else "no unanswered claim was named"
        return result
    now = now or _now()
    ledger = _load(ledger_path)
    entry = ledger.setdefault(question_key(question), {"question": question, "searches": [], "supported": [],
                                                       "gaps": [], "passages": {}})
    if fetch is None:
        result["skipped"] = "full-text search is not wired into this process"
        return result
    import europepmc
    read, total = {}, 0
    for claim in wanted:
        words = _words(claim, exclude=names)
        found = []
        for query in claim_queries(names, claim):
            old = next((s for s in entry["searches"] if s.get("query") == query), None)
            fresh = old and (now - datetime.datetime.fromisoformat(old["at"])).days < REPEAT_DAYS
            if fresh:
                result["reused"].append(query)
                hits = old.get("pmcids")
            else:
                hits, said = search(query, fetch)
                row = {"query": query, "claim": claim, "at": now.isoformat(), "pmcids": hits, "result": said}
                entry["searches"] = [s for s in entry["searches"] if s.get("query") != query] + [row]
                result["searches"].append(row)
                if hits is None:
                    result["failures"].append(said)
            if hits:
                found = hits
                break
        for pmcid in found:
            cache = "%s|%s" % (pmcid, claim)
            chosen = entry["passages"].get(cache)
            if chosen is None:
                if pmcid not in read:
                    if len(read) >= MAX_ARTICLES:
                        continue
                    r = europepmc.read({"pmcid": pmcid}, fetch=fetch)
                    read[pmcid] = r
                    if r.get("kind") != "fetched":
                        result["failures"].append("%s: %s" % (pmcid, r.get("why") or r.get("kind")))
                r = read[pmcid]
                if r.get("kind") != "fetched":
                    continue
                raw = (r.get("fetch") or {}).get("raw") or ""
                try:
                    article = europepmc.parse_jats(raw.encode("utf-8"))
                except ValueError as exc:
                    result["failures"].append("%s: %s" % (pmcid, exc)); continue
                chosen = [dict(p, pmcid=pmcid, pmid=r.get("pmid") or "", title=r.get("title") or "",
                               source_url=r.get("source_url") or "") for p in passages(article, words)]
                entry["passages"][cache] = chosen
            for p in chosen:
                if total + len(p["text"]) > TOTAL_CHARS:
                    break
                total += len(p["text"])
                result["FULLTEXT"].append({"pmcid": p["pmcid"], "pmid": p.get("pmid", ""), "title": p.get("title", ""),
                                           "section": p.get("section", ""), "claim": claim, "text": p["text"],
                                           "source_url": p.get("source_url", "")})
            if sum(1 for x in result["FULLTEXT"] if x["claim"] == claim) >= PER_CLAIM:
                break
    _save(ledger, ledger_path)
    return result


def remember(question, reflection, gathered=None, ledger_path=None, now=None):
    """Keep what is supported, and for each claim still open: what was searched, and what would justify trying again."""
    now = now or _now()
    status, why = outcome(reflection)
    ledger = _load(ledger_path)
    entry = ledger.setdefault(question_key(question), {"question": question, "searches": [], "supported": [],
                                                       "gaps": [], "passages": {}})
    cov = (reflection or {}).get("coverage_check") or {}
    if status in RESEARCH:
        have = {(s.get("requirement"), s.get("quote")) for s in entry["supported"]}
        for s in cov.get("supports") or []:
            if isinstance(s, dict) and s.get("quote") and (s.get("requirement"), s.get("quote")) not in have:
                entry["supported"].append({"requirement": s.get("requirement"), "quote": s.get("quote"),
                                           "source_citation": s.get("source_citation") or "", "at": now.isoformat()})
        entry["supported"] = entry["supported"][-40:]
        gaps = []
        for claim in [" ".join(str(x).split())[:300] for x in cov.get("missing") or []]:
            tried = [s["query"] for s in entry["searches"] if s.get("claim") == claim]
            hits = [p for s in entry["searches"] if s.get("claim") == claim for p in (s.get("pmcids") or [])]
            if not tried:
                justify = "a full-text search for this claim; none has been run"
            elif not hits:
                justify = ("an open-access article on this claim that is not yet in Europe PMC, or a source other than "
                           "Europe PMC full text; searched: " + " | ".join(tried))
            else:
                justify = ("a new article or source: the passages of %s were read and did not establish it"
                           % ", ".join(dict.fromkeys(hits)))
            gaps.append({"claim": claim, "searched": tried, "would_justify": justify})
        entry["gaps"] = gaps
    entry.update(last_outcome=status, last_why=why[:400], last_at=now.isoformat())
    _save(ledger, ledger_path)
    return {"outcome": status, "why": why[:400], "supported": len(entry["supported"]), "gaps": entry["gaps"],
            "searched": len(entry["searches"]),
            "new_searches": len((gathered or {}).get("searches") or []),
            "reused_searches": len((gathered or {}).get("reused") or []),
            "fulltext_passages": len((gathered or {}).get("FULLTEXT") or [])}


def prior_supports(question, ledger_path=None):
    """Quotes already source-checked for this exact question, as the review's prior validated evidence."""
    entry = _load(ledger_path).get(question_key(question)) or {}
    return [{"requirement": s.get("requirement"), "quote": s.get("quote"), "source_citation": s.get("source_citation")}
            for s in entry.get("supported") or [] if s.get("quote")]


def waiting_keys(ledger_path=None):
    """Question keys whose every open claim has been searched for, with nothing new to search: they wait."""
    return {key for key, entry in _load(ledger_path).items()
            if isinstance(entry, dict) and entry.get("gaps") and all(g.get("searched") for g in entry["gaps"])}


def unchanged(question, ledger_path=None):
    return question_key(question) in waiting_keys(ledger_path)
