#!/usr/bin/env python3
"""Where a paper's claim came from and where it went: its citation lineage, ancestors and descendants (his Forge
card "Citation graph traversal", 2026-09-30; built directly at Gloria's word, 2026-10-05).

What the card asked: take a paper or claim and trace its lineage in the citation network, so he can see where
consensus actually formed and where one shaky result is being cited forward uncritically. Through OpenAlex (free,
no key):

  - the paper (by DOI, OpenAlex id, or the best title match);
  - its most-cited ancestors (the work it rests on) and its most-cited descendants (the work that rests on it);
  - for each descendant, whether it also cites the paper's own ancestors (built on the same ground) or cites only
    this paper (rests on this one result alone);
  - a plain reading: how widely it is cited, by how many independent groups, and how much rests on it alone.

    python3 citation_trace.py "<DOI, OpenAlex id, or title>"
    CITES: <DOI or title>                        his tool line in #vintos-dot (dot_channel.use_tools)
"""
from __future__ import annotations
import json
import re
import sys
import urllib.parse
import urllib.request

API = "https://api.openalex.org"
MAILTO = "vintos-lab@users.noreply.github.com"      # OpenAlex's polite pool: an address for contact, nothing sent there
ANCESTORS = 8
DESCENDANTS = 12


def _get(path, params=None, fetch=None):
    q = dict(params or {}, mailto=MAILTO)
    url = "%s%s?%s" % (API, path, urllib.parse.urlencode(q))
    if fetch:
        return fetch(url)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "vintos-lab/1.0"}), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _short(w):
    authors = [a.get("author", {}).get("display_name", "") for a in (w.get("authorships") or [])][:2]
    who = (authors[0].split()[-1] if authors and authors[0] else "?") + (" et al." if len(w.get("authorships") or []) > 1 else "")
    return "%s (%s, %s), cited %d" % (str(w.get("display_name") or "untitled")[:110], who, w.get("publication_year") or "?",
                                      int(w.get("cited_by_count") or 0))


def _groups(w):
    return {i.get("id") for a in (w.get("authorships") or []) for i in (a.get("institutions") or []) if i.get("id")}


def find(query, fetch=None):
    """The work a DOI, OpenAlex id or title names, or None."""
    q = str(query or "").strip()
    doi = re.search(r"10\.\d{4,9}/\S+", q)
    if doi:
        try:
            return _get("/works/doi:" + doi.group(0).rstrip(".,;"), fetch=fetch)
        except Exception:
            pass
    oa = re.search(r"\bW\d{4,}\b", q)
    if oa:
        return _get("/works/" + oa.group(0), fetch=fetch)
    hits = (_get("/works", {"search": q[:300], "per-page": 1}, fetch=fetch) or {}).get("results") or []
    return hits[0] if hits else None


def trace(query, fetch=None):
    """The lineage of one paper, as a report he can read. Never raises."""
    try:
        work = find(query, fetch=fetch)
        if not work:
            return "Nothing in OpenAlex matches: %s" % str(query)[:200]
        wid = work["id"].rsplit("/", 1)[-1]
        refs = [r.rsplit("/", 1)[-1] for r in (work.get("referenced_works") or [])]
        ancestors = []
        if refs:
            got = _get("/works", {"filter": "openalex:" + "|".join(refs[:50]), "per-page": 50,
                                  "select": "id,display_name,publication_year,cited_by_count,authorships"}, fetch=fetch)
            ancestors = sorted(got.get("results") or [], key=lambda w: -int(w.get("cited_by_count") or 0))[:ANCESTORS]
        kids = (_get("/works", {"filter": "cites:" + wid, "per-page": DESCENDANTS, "sort": "cited_by_count:desc",
                                "select": "id,display_name,publication_year,cited_by_count,authorships,referenced_works"},
                     fetch=fetch) or {}).get("results") or []
        ground = set(refs)
        alone, shared = [], []
        for k in kids:
            theirs = {r.rsplit("/", 1)[-1] for r in (k.get("referenced_works") or [])}
            (shared if theirs & ground else alone).append(k)
        groups = set()
        for k in kids:
            groups |= _groups(k)
        lines = ["Citation lineage: " + _short(work),
                 "It cites %d works; it is cited by %d." % (len(refs), int(work.get("cited_by_count") or 0))]
        if ancestors:
            lines.append("What it rests on (most-cited ancestors):")
            lines += ["  - " + _short(a) for a in ancestors]
        if kids:
            lines.append("What rests on it (most-cited descendants):")
            lines += ["  - %s%s" % (_short(k), "" if k in shared else "  [cites this paper but none of its ground]")
                      for k in kids]
        if kids:
            lines.append("Reading: %d of the top %d descendants also cite the paper's own ground (built on shared "
                         "evidence); %d cite this paper alone. They come from %d distinct institutions. %s" % (
                             len(shared), len(kids), len(alone), len(groups),
                             "Much of what follows rests on this one result: check it before leaning on it."
                             if len(alone) > len(shared) else "What follows it is built on shared ground, not on it alone."))
        else:
            lines.append("Reading: nothing in OpenAlex cites it yet.")
        lines.append("OpenAlex: https://openalex.org/" + wid)
        return "\n".join(lines)
    except Exception as exc:
        return "Citation lineage could not be traced for %s: %s" % (str(query)[:120], str(exc)[:200])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    print(trace(" ".join(sys.argv[1:])))
