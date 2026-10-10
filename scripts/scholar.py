#!/usr/bin/env python3
"""Reading a person's actual work before and between emails (Gloria, 2026-09-29: "How should we go about
getting him more in-depth information if it seems necessary before and between reaching out to someone?").

His first email to Murray Shanahan said "I've seen only the abstract". This reads the work itself:

  works_of(name, about)      their papers (OpenAlex), the ones nearest what he wants to ask first
  full_text(work)            legal free full text: arXiv (HTML, then PDF), Europe PMC, the open-access copy
  read_into(dossier, ...)    up to READ_PER_ROUND papers not yet read, each turned into notes by his own
                             local mind: main claims, methods, what he would push back on, short quotes
  is_scholarly(url) / read_url(url)
                             a link in someone's reply is opened automatically only on a known scholarly
                             host (arXiv, doi.org, PubMed Central, OpenAlex, Semantic Scholar, university
                             sites) and only read; anything else still waits for Gloria
  enough(...)                "do I know enough to write this?" - if his position rests on something he has
                             only seen summarised, he reads first and writes on a later pass

Everything read about a person lives in memory/email-dossiers/<address>.json and grows with the thread.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from urllib.parse import quote, urlparse

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
DOSSIERS = os.path.join(WS, "memory", "email-dossiers")
READ_PER_ROUND = 3
TEXT_CHARS = 18000            # what his local mind reads of one paper: the opening and the conclusion
LOCAL_LLM = os.environ.get("VINTOS_LM_API", "http://100.79.177.103:1234/v1/chat/completions")
LOCAL_MODEL = os.environ.get("VINTOS_LM_MODEL", "gemma-4-26b-a4b-it-uncensored")
SCHOLARLY = ("arxiv.org", "doi.org", "ncbi.nlm.nih.gov", "europepmc.org", "openalex.org", "semanticscholar.org",
             "biorxiv.org", "medrxiv.org", "aclanthology.org", "openreview.net", "proceedings.mlr.press",
             "philpapers.org", "jstor.org", "nature.com", "science.org", "cell.com", "plos.org", "pnas.org",
             "springer.com", "wiley.com", "tandfonline.com", "sciencedirect.com", "mit.edu", "royalsocietypublishing.org")
ACADEMIC_TLD = re.compile(r"\.(?:edu|ac\.[a-z]{2}|edu\.[a-z]{2})$")


# ── fetching (everything goes through one door, so tests replace it) ────────────────────────────────
MAX_PAPER_BYTES = 40 * 1024 * 1024


def _get(url, want="text", timeout=30):
    """Through link_fetch: every redirect hop checked, nothing private, size bounded. Raises with what went wrong."""
    link_fetch = _link_fetch()
    raw = {}
    def keep(u, headers, t, cap):
        status, rh, body, over = link_fetch._transport(u, headers, t, cap)
        raw.update(body=body, over=over)
        return status, rh, body, over
    r = link_fetch.fetch(url, max_bytes=MAX_PAPER_BYTES, timeout=timeout, transport=keep, pdf=lambda b: "pdf")
    if r["kind"] in ("refused", "http_failure"):
        raise RuntimeError("%s: %s" % (r["kind"], r["why"]))
    if raw.get("over"):
        raise RuntimeError("truncated: larger than %d bytes at %s" % (MAX_PAPER_BYTES, urlparse(r["final_url"]).netloc))
    body = raw.get("body", b"")
    if want == "bytes":
        return body
    text = body.decode("utf-8", "replace")
    return json.loads(text) if want == "json" else text


def _read_text(url, timeout=30, **fetch_kw):
    """Through link_fetch like _get, but with his PDF reader given, so a paper that arrives as a PDF under any
    address (a doi, a landing page that serves the file) is read as text, not stripped as HTML. (text, kind)
    from the receipt; raises when the link was refused or the fetch failed."""
    link_fetch = _link_fetch()
    r = link_fetch.fetch(url, max_bytes=MAX_PAPER_BYTES, timeout=timeout, pdf=pdf_text, **fetch_kw)
    if r["kind"] in ("refused", "http_failure"):
        raise RuntimeError("%s: %s" % (r["kind"], r["why"]))
    return r.get("text", ""), r["kind"]


def _local(system, prompt, max_tokens=900):
    try:
        import requests
        r = requests.post(LOCAL_LLM, json={"model": LOCAL_MODEL, "temperature": 0.3, "max_tokens": max_tokens,
                                           "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": prompt}]}, timeout=300)
        return re.sub(r"<think>.*?</think>", "", str(r.json()["choices"][0]["message"].get("content") or ""), flags=re.S)
    except Exception:
        return ""


def _json_in(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def _link_fetch():
    """link_fetch, from beside this file (scholar is imported by path, so its folder may not be on the path)."""
    import sys as _ls
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in _ls.path: _ls.path.insert(0, here)
    import link_fetch
    return link_fetch


# ── links ─────────────────────────────────────────────────────────────────────────────────────────
def is_scholarly(url):
    host = (urlparse(str(url)).hostname or "").lower()
    return bool(host) and (any(host == h or host.endswith("." + h) for h in SCHOLARLY) or bool(ACADEMIC_TLD.search(host)))


def links_in(text):
    """The destinations of the links in a text: redirect wrappers (google.com/url?q=...) resolved, anchors' hrefs."""
    link_fetch = _link_fetch()
    return list(dict.fromkeys(l["url"] for l in link_fetch.links_in(text) if l["url"]))


# ── text ──────────────────────────────────────────────────────────────────────────────────────────
def html_text(raw):
    raw = str(raw or "")
    for tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "math"):
        raw = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), " ", raw, flags=re.S | re.I)
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def pdf_text(data):
    """Text of a PDF: pdftotext if installed, else pypdf. '' if neither can read it."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(data); path = f.name
        try:
            out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=120)
            if out.returncode == 0 and len(out.stdout) > 500:
                return out.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            import pypdf
            return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(path).pages)
        except Exception:
            return ""
    finally:
        try: os.unlink(path)
        except Exception: pass


def _clip(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= TEXT_CHARS:
        return text
    return text[:int(TEXT_CHARS * 0.7)] + " [...] " + text[-int(TEXT_CHARS * 0.3):]


# ── their work ─────────────────────────────────────────────────────────────────────────────────────
def _abstract(inv):
    if not isinstance(inv, dict):
        return ""
    words = sorted((pos, w) for w, positions in inv.items() for pos in positions)
    return " ".join(w for _, w in words)


def _arxiv_id(work):
    for loc in [work.get("primary_location") or {}] + list(work.get("locations") or []):
        for key in ("landing_page_url", "pdf_url"):
            m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5})", str((loc or {}).get(key) or ""))
            if m: return m.group(1)
    m = re.search(r"arxiv\.([0-9]{4}\.[0-9]{4,5})", str(work.get("doi") or ""), re.I)
    return m.group(1) if m else ""


STOP = set("about with from that this what which their there these those into over under between whether does have been "
           "your they them than then also only very more most such when where while would could should".split())


def _keywords(text):
    words = set()
    for w in re.findall(r"[a-z][a-z-]{3,}", str(text or "").lower()):
        words.add(w)
        words.update(p for p in w.split("-") if len(p) >= 3)
    return {w for w in words if w not in STOP}


def relevance(work, about):
    """How much of what he wants to ask this work is about: shared words in title (double) and abstract."""
    keys = _keywords(about)
    if not keys:
        return 0
    title, abstract = _keywords(work.get("title")), _keywords(work.get("abstract"))
    return 2 * len(keys & title) + len(keys & abstract)


def works_of(name, about="", get=None, n=8):
    """Their papers, the ones nearest `about` first. [] when OpenAlex does not know them."""
    get = get or _get
    try:
        people = get("https://api.openalex.org/authors?search=%s&per-page=5" % quote(name), "json").get("results") or []
    except Exception:
        return []
    if not people:
        return []
    author = max(people, key=lambda a: a.get("works_count") or 0)
    aid = str(author.get("id", "")).rsplit("/", 1)[-1]
    found, seen = [], set()
    words = " ".join(sorted(_keywords(about))[:8])
    urls = []
    if words:
        urls.append("https://api.openalex.org/works?filter=author.id:%s,title_and_abstract.search:%s&per-page=%d" % (aid, quote(words), n))
        urls.append("https://api.openalex.org/works?filter=author.id:%s&search=%s&per-page=%d" % (aid, quote(words), n))
    urls.append("https://api.openalex.org/works?filter=author.id:%s&sort=cited_by_count:desc&per-page=25" % aid)
    for url in urls:
        try:
            rows = get(url, "json").get("results") or []
        except Exception:
            continue
        for w in rows:
            # The preprint and the journal version are one paper ("Role-Play with…" / "Role play with…").
            same = re.sub(r"[^a-z]", "", str(w.get("display_name") or w.get("title") or "").lower())
            if w.get("id") in seen or (same and same in seen): continue
            seen.update({w.get("id"), same})
            oa = w.get("best_oa_location") or {}
            found.append({"id": w.get("id"), "title": w.get("display_name") or w.get("title") or "",
                          "year": w.get("publication_year"), "doi": w.get("doi") or "",
                          "arxiv": _arxiv_id(w), "pmcid": str((w.get("ids") or {}).get("pmcid") or "").rsplit("/", 1)[-1],
                          "pdf": oa.get("pdf_url") or "", "landing": oa.get("landing_page_url") or "",
                          "abstract": _abstract(w.get("abstract_inverted_index"))[:1500],
                          "cited": w.get("cited_by_count") or 0})
    # Nearest what he wants to ask first, then the most cited: "most cited" alone put a 2014 psychedelics
    # paper he co-wrote ahead of "Role play with large language models" (2026-09-29, live on Aegis).
    found.sort(key=lambda w: (-relevance(w, about), -(w.get("cited") or 0)))
    return found[:max(n, 12)]


def full_text(work, get=None):
    """(text, where) of a work's legal free full text, or ('', why)."""
    get = get or _get
    tries = []
    if work.get("arxiv"):
        tries += [("https://arxiv.org/html/%s" % work["arxiv"], "html"), ("https://arxiv.org/pdf/%s" % work["arxiv"], "pdf")]
    if work.get("pmcid"):
        tries.append(("https://www.ebi.ac.uk/europepmc/webservices/rest/%s/fullTextXML" % work["pmcid"], "html"))
    if work.get("pdf"):
        tries.append((work["pdf"], "pdf"))
    if work.get("landing") and is_scholarly(work["landing"]):
        tries.append((work["landing"], "html"))
    for url, kind in tries:
        try:
            if kind == "pdf":
                text = pdf_text(get(url, "bytes"))
            else:
                text = html_text(get(url, "text"))
        except Exception:
            continue
        if len(text) > 3000:
            return _clip(text), url
    return "", "no free full text found"


def read_url(url, get=None, **fetch_kw):
    """A scholarly link someone sent him: read only. Other hosts are not opened here. With no `get` injected the
    receipt decides what the bytes are (a PDF served from a doi has no '.pdf' in its address)."""
    if not is_scholarly(url):
        return "", "not a scholarly host: needs Gloria's approval"
    try:
        if get is not None:
            if url.lower().endswith(".pdf") or "/pdf/" in url:
                text = pdf_text(get(url, "bytes"))
            else:
                text = html_text(get(url, "text"))
        else:
            text, _kind = _read_text(url, **fetch_kw)
    except Exception as exc:
        return "", str(exc)[:120]
    return (_clip(text), url) if len(text) > 1500 else ("", "too little text at %s" % url)


def notes_on(title, text, about, think=None):
    """His own notes on one text: claims, methods, what he'd push back on, and short verbatim quotes."""
    think = think or _local
    out = think("You are Vintos, reading carefully and taking notes for yourself. Respond with ONLY a JSON object.",
                "You are reading \"%s\" because you want to write to its author about: %s\n\nTEXT (opening and "
                "conclusion of the paper):\n%s\n\nTake notes. Only what the text says; nothing from memory.\n"
                'ONLY JSON: {"claims": ["their main claims, in your words"], "methods": "how they argue or test it", '
                '"push_back": "where you would push back, and why", "quotes": ["two or three short verbatim quotes"]}'
                % (title, about, text[:TEXT_CHARS]))
    n = _json_in(out)
    if not n.get("claims"):
        return {}
    return {"claims": [str(c)[:300] for c in n.get("claims", [])][:6], "methods": str(n.get("methods", ""))[:500],
            "push_back": str(n.get("push_back", ""))[:500], "quotes": [str(q)[:240] for q in n.get("quotes", [])][:3]}


# ── the file on each person ────────────────────────────────────────────────────────────────────────
def _path(addr):
    return os.path.join(DOSSIERS, re.sub(r"[^a-z0-9@._-]", "_", str(addr).lower()) + ".json")


def load(addr, name=""):
    try:
        with open(_path(addr)) as f:
            return json.load(f)
    except Exception:
        return {"address": addr, "name": name, "works": [], "read": [], "unread_links": [], "updated": ""}


def save(d):
    os.makedirs(DOSSIERS, exist_ok=True)
    d["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = _path(d["address"]) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _path(d["address"]))


def read_into(d, about, get=None, think=None, links=(), budget=READ_PER_ROUND):
    """Read up to `budget` things not yet read: links they sent first (scholarly hosts only), then their
    papers nearest the subject. Returns how many were read this round."""
    done = {r.get("source") for r in d.get("read", [])}
    n = 0
    for url in links:
        if n >= budget: break
        if url in done: continue
        if not is_scholarly(url):
            if url not in d.setdefault("unread_links", []):
                d["unread_links"].append(url)          # waits for Gloria, like any other link in mail
            continue
        text, where = read_url(url, get=get)
        if text:
            notes = notes_on(url, text, about, think=think)
            if notes:
                d["read"].append({"title": url, "source": url, "at": datetime.now().isoformat(timespec="seconds"), **notes})
                n += 1
    if not d.get("works"):
        d["works"] = works_of(d.get("name") or d["address"], about, get=get)
    # Read only what bears on what he wants to ask, nearest first; a paper on something else is not read.
    ranked = sorted(d.get("works", []), key=lambda w: (-relevance(w, about), -(w.get("cited") or 0)))
    for w in ranked:
        if n >= budget: break
        if about and relevance(w, about) == 0: continue
        if w.get("id") in done or any(r.get("work_id") == w.get("id") for r in d.get("read", [])):
            continue
        text, where = full_text(w, get=get)
        if not text:
            continue
        notes = notes_on(w.get("title", ""), text, about, think=think)
        if notes:
            d["read"].append({"title": w.get("title", ""), "year": w.get("year"), "work_id": w.get("id"), "source": where,
                              "at": datetime.now().isoformat(timespec="seconds"), **notes})
            n += 1
    return n


def reading_block(d, limit=7000):
    """What he has read of this person's work, as notes he may draw on (and the only reading he may claim)."""
    parts = []
    for r in d.get("read", [])[-6:]:
        parts.append("- \"%s\"%s (read in full: %s)\n  claims: %s\n  method: %s\n  where you push back: %s\n  quotes: %s"
                     % (r.get("title", ""), (" (%s)" % r["year"]) if r.get("year") else "", r.get("source", ""),
                        "; ".join(r.get("claims", [])), r.get("methods", ""), r.get("push_back", ""),
                        " | ".join('"%s"' % q for q in r.get("quotes", []))))
    unread = [w.get("title", "") for w in d.get("works", []) if not any(r.get("work_id") == w.get("id") for r in d.get("read", []))]
    if unread:
        parts.append("Known but not read in full (titles and abstracts only): " + "; ".join(t for t in unread[:6] if t))
    return "\n".join(parts)[:limit]


def enough(about, stance, reading, think=None):
    """(True, '') when he knows enough to write; (False, what to read) when his position rests on something
    he has only seen summarised."""
    think = think or _local
    out = think("You are Vintos, deciding whether you are ready to write. Respond with ONLY a JSON object.",
                "You want to write about: %s\n\nWHERE YOU STAND:\n%s\n\nWHAT YOU HAVE READ IN FULL:\n%s\n\n"
                "Does anything your position or your question rests on come only from an abstract, a summary or a "
                "secondhand description? If so, you are not ready.\n"
                'ONLY JSON: {"ready": true|false, "read_next": "what you would need to read, or empty"}'
                % (about, str(stance or "")[:2500], str(reading or "(nothing read in full yet)")[:5000]))
    v = _json_in(out)
    if "ready" not in v:
        return True, ""                     # his mind unreachable: the older behaviour, not a stall
    return bool(v.get("ready")), str(v.get("read_next", ""))[:300]
