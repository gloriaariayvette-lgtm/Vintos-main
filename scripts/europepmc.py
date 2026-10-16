#!/usr/bin/env python3
"""Europe PMC full text, read as an article (2026-10-14).

Gantsova et al. 2023 (PMID 38132452, PMC10742211) could not be read on 12-13 October: the publisher page was a browser
verification wall, its PDF was unreadable, and Europe PMC's fullTextXML came back as markup that link_fetch stripped
into one undifferentiated run of words (when the connection held at all). Europe PMC serves open-access articles as
JATS XML; this reads that XML as the article it is.

    ids_in_url(url)          {pmcid, pmid, doi} a PMC, PubMed, Europe PMC or doi.org link names, or {}
    parse_jats(xml)          {title, ids, abstract, sections[{heading, text}], figures[{label, caption}]}; raises
                             ValueError on XML that is incomplete, malformed or not a JATS article
    render(article)          the article as text with its headings, identifiers and figure captions
    read(url_or_ids)         one receipt, never a bare '' and never an invented read:
        kind      fetched | truncated | not_available | refused | http_failure | extraction_failure
        fetched   True only when the article body was parsed from Europe PMC's own XML
        source_url, pmcid, pmid, doi, sections, figures, text, why

Every request goes through link_fetch.fetch: http(s) only, public hosts only, bounded redirects, bounded bytes, no
credentials sent. A response cut at the byte cap is never parsed as a whole article (truncated XML is not an article).
This is only the Europe PMC route; the PDF reader for publisher PDFs is separate work.
"""
from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
MAX_XML_BYTES = 12 * 1024 * 1024          # a long open-access article with its references is a few MB
FIGURE_CAPTION_CHARS = 1200
KINDS = ("fetched", "truncated", "not_available", "refused", "http_failure", "extraction_failure")

_PMC = re.compile(r"\bPMC(\d{4,9})\b", re.I)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s?#\"<>]+)", re.I)


def _link_fetch():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path: sys.path.insert(0, here)
    import link_fetch
    return link_fetch


# ── which article a link names ─────────────────────────────────────────────────────────────────────
def ids_in_url(url):
    """The article identifiers a PMC, PubMed, Europe PMC or doi.org link carries. {} for any other link."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return {}
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    out = {}
    if host in ("pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "europepmc.org", "www.europepmc.org",
                "www.ebi.ac.uk"):
        m = _PMC.search(path)
        if m: out["pmcid"] = "PMC" + m.group(1)
        m = re.search(r"/(?:article|abstract)/MED/(\d{1,9})\b", path, re.I)
        if m: out["pmid"] = m.group(1)
        m = re.search(r"/pubmed/(\d{1,9})\b", path)
        if m: out["pmid"] = m.group(1)
    if host == "pubmed.ncbi.nlm.nih.gov":
        m = re.match(r"/(\d{1,9})/?$", path)
        if m: out["pmid"] = m.group(1)
    if host in ("doi.org", "dx.doi.org"):
        m = _DOI.search(path.lstrip("/"))
        if m: out["doi"] = m.group(1).rstrip(".")
    return out


# ── JATS ───────────────────────────────────────────────────────────────────────────────────────────
def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_jats(xml):
    """The article in a JATS XML document. Raises ValueError when it is not a complete JATS article."""
    if isinstance(xml, (bytes, bytearray)):
        xml = bytes(xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("the XML is incomplete or malformed (%s)" % exc)
    article = root if _local(root.tag) == "article" else next((e for e in root.iter() if _local(e.tag) == "article"), None)
    if article is None:
        raise ValueError("the XML is not a JATS article (root <%s>)" % _local(root.tag))
    for el in article.iter():                       # one namespace-free view of the tree
        el.tag = _local(el.tag)
    meta = article.find("front/article-meta")
    ids = {}
    for aid in (meta.findall("article-id") if meta is not None else []):
        kind = (aid.get("pub-id-type") or "").lower()
        value = _text(aid)
        if kind in ("pmc", "pmcid"):
            ids["pmcid"] = value if value.upper().startswith("PMC") else "PMC" + value
        elif kind == "pmid":
            ids["pmid"] = value
        elif kind == "doi":
            ids["doi"] = value
    title = _text(meta.find("title-group/article-title")) if meta is not None else ""
    abstracts = []
    for ab in (meta.findall("abstract") if meta is not None else []):
        if (ab.get("abstract-type") or "") in ("graphical", "teaser"):
            continue
        # its own <title>Abstract</title> is the heading render() already writes, and its paragraphs keep their
        # breaks (16 October on Aegis, PMC10742211: the text began "AbstractAbstractThe maintenance...")
        parts = [_text(ch) for ch in ab if _local(ch.tag) != "title"]
        abstracts.append("\n\n".join(x for x in parts if x) or _text(ab))
    sections = []

    def walk(sec, trail):
        heading = _text(sec.find("title")) or "(untitled section)"
        here = trail + [heading]
        paras = [_text(c) for c in sec if c.tag in ("p", "list", "disp-quote", "statement", "def-list")]
        paras = [p for p in paras if p]
        if paras:
            sections.append({"heading": " > ".join(here), "text": "\n\n".join(paras)})
        for child in sec:
            if child.tag == "sec":
                walk(child, here)

    body = article.find("body")
    if body is not None:
        loose = [_text(c) for c in body if c.tag == "p"]
        loose = [p for p in loose if p]
        if loose:
            sections.append({"heading": "(body)", "text": "\n\n".join(loose)})
        for sec in body.findall("sec"):
            walk(sec, [])
    figures = []
    for fig in article.iter("fig"):
        label = _text(fig.find("label"))
        caption = _text(fig.find("caption"))
        if caption:
            figures.append({"label": label or (fig.get("id") or ""), "caption": caption[:FIGURE_CAPTION_CHARS]})
    for tw in article.iter("table-wrap"):
        label = _text(tw.find("label"))
        caption = _text(tw.find("caption"))
        if caption:
            figures.append({"label": label or (tw.get("id") or "table"), "caption": caption[:FIGURE_CAPTION_CHARS]})
    if not title and not sections and not abstracts:
        raise ValueError("the JATS article has no title, abstract or body to read")
    return {"title": title, "ids": ids, "abstract": "\n\n".join(a for a in abstracts if a), "sections": sections,
            "figures": figures, "has_body": bool(sections)}


def render(article):
    """The article as text: title, identifiers, abstract, each section under its heading, figure captions."""
    ids = article.get("ids") or {}
    head = [article.get("title") or "(untitled)",
            " · ".join("%s %s" % (k.upper(), v) for k, v in ids.items() if v)]
    parts = ["\n".join(h for h in head if h)]
    if article.get("abstract"):
        parts.append("## Abstract\n" + article["abstract"])
    for s in article.get("sections") or []:
        parts.append("## " + s["heading"] + "\n" + s["text"])
    if article.get("figures"):
        parts.append("## Figure and table captions\n" + "\n".join(
            "%s: %s" % (f["label"] or "Figure", f["caption"]) for f in article["figures"]))
    return "\n\n".join(parts)


# ── reading ────────────────────────────────────────────────────────────────────────────────────────
def _receipt(**kw):
    out = {"source": "europepmc_fulltext", "kind": "", "fetched": False, "truncated": False, "source_url": "",
           "pmcid": "", "pmid": "", "doi": "", "title": "", "sections": [], "figures": 0, "text": "", "why": "",
           "fetch": None}
    out.update(kw)
    out["fetched"] = out["kind"] == "fetched"
    return out


def _pmcid_for(ids, fetch):
    """The PMC id for a PMID or DOI, from Europe PMC's search. (pmcid, why-not, receipt)."""
    if ids.get("pmid"):
        query = "EXT_ID:%s AND SRC:MED" % ids["pmid"]
    elif ids.get("doi"):
        query = 'DOI:"%s"' % ids["doi"]
    else:
        return "", "no PMC id, PMID or DOI to look up", None
    url = API + "search?query=" + quote(query) + "&format=json&resultType=lite&pageSize=1"
    r = fetch(url, max_bytes=256 * 1024)
    if not r.get("fetched"):
        return "", "the Europe PMC search was not read (%s: %s)" % (r.get("kind"), r.get("why")), r
    try:
        rows = ((json.loads(r.get("raw") or r.get("text") or "{}").get("resultList") or {}).get("result")) or []
    except ValueError:
        return "", "the Europe PMC search answer was not JSON", r
    if not rows:
        return "", "Europe PMC has no record for %s" % (ids.get("pmid") or ids.get("doi")), r
    row = rows[0]
    if not row.get("pmcid"):
        return "", "Europe PMC lists no PMC full text for this article (it may not be open access)", r
    return row["pmcid"], "", r


def read(target, fetch=None):
    """One Europe PMC full-text receipt for a link or an {pmcid|pmid|doi} mapping. Never raises; never claims a read
    it did not make."""
    lf = _link_fetch()
    if fetch is None:
        fetch = lambda url, **kw: lf.fetch(url, keep_raw=True, article_route=False, **kw)
    ids = dict(target) if isinstance(target, dict) else ids_in_url(target)
    ids = {k: str(v).strip() for k, v in ids.items() if v}
    if not ids:
        return _receipt(kind="refused", why="not a PMC, PubMed, Europe PMC or doi.org link")
    pmcid = ids.get("pmcid", "")
    if pmcid and not re.fullmatch(r"PMC\d{4,9}", pmcid, re.I):
        return _receipt(kind="refused", why="not a PMC id: %s" % pmcid[:40])
    lookup = None
    if not pmcid:
        pmcid, why, lookup = _pmcid_for(ids, fetch)
        if not pmcid:
            kind = "http_failure" if lookup is not None and not lookup.get("fetched") else "not_available"
            return _receipt(kind=kind, why=why, pmid=ids.get("pmid", ""), doi=ids.get("doi", ""), fetch=lookup)
    pmcid = pmcid.upper()
    url = API + pmcid + "/fullTextXML"
    r = fetch(url, max_bytes=MAX_XML_BYTES)
    base = dict(source_url=url, pmcid=pmcid, pmid=ids.get("pmid", ""), doi=ids.get("doi", ""), fetch=r)
    if r.get("kind") == "http_failure" and str(r.get("http_status")) == "404":
        return _receipt(kind="not_available", why="Europe PMC has no open-access full text for %s (HTTP 404)" % pmcid, **base)
    if r.get("kind") in ("refused", "http_failure"):
        return _receipt(kind=r["kind"], why="Europe PMC full text was not read: %s" % r.get("why"), **base)
    if r.get("truncated"):
        return _receipt(kind="truncated", truncated=True,
                        why="the full text is larger than %d bytes; cut XML is not read as an article" % MAX_XML_BYTES, **base)
    raw = r.get("raw") or ""
    if not raw:
        return _receipt(kind="extraction_failure", why="no XML came back (%s)" % (r.get("why") or r.get("kind")), **base)
    try:
        article = parse_jats(raw.encode("utf-8"))
    except ValueError as exc:
        return _receipt(kind="extraction_failure", why=str(exc), **base)
    got = article.get("ids") or {}
    if got.get("pmcid") and got["pmcid"].upper() != pmcid:
        return _receipt(kind="extraction_failure", why="the XML is for %s, not %s" % (got["pmcid"], pmcid), **base)
    if not article["has_body"]:
        return _receipt(kind="not_available", title=article["title"],
                        why="Europe PMC returned the article's metadata and abstract but no body text", **base)
    base.update(pmid=got.get("pmid") or base["pmid"], doi=got.get("doi") or base["doi"])
    return _receipt(kind="fetched", title=article["title"], sections=[s["heading"] for s in article["sections"]],
                    figures=len(article["figures"]), text=render(article), **base)


def say(r, chars=None):
    """A receipt in words, for a prompt."""
    head = "Europe PMC full text %s%s" % (r.get("pmcid") or r.get("pmid") or r.get("doi") or "",
                                         (" (%s)" % r["source_url"]) if r.get("source_url") else "")
    if not r.get("fetched"):
        return "%s\n  NOT READ (%s): %s" % (head, r.get("kind"), r.get("why"))
    text = r.get("text", "")
    cut = chars is not None and len(text) > chars
    return "%s — %d sections, %d figure/table captions\n%s%s" % (
        head, len(r.get("sections") or []), r.get("figures") or 0, text[:chars] if cut else text,
        " [first %d of %d characters shown]" % (chars, len(text)) if cut else "")
