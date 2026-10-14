#!/usr/bin/env python3
"""Europe PMC full text read as an article (2026-10-14). On 12-13 October Gantsova et al. (PMC10742211) could not be
read: a verification wall, an unreadable PDF, and fullTextXML returned as stripped markup or a dropped connection. A
PMC, PubMed, Europe PMC or doi.org link is now read first from Europe PMC's open-access JATS XML, with headings,
identifiers and figure captions kept, and every failure named in the receipt.

Isolation: the network is a scripted transport and DNS a fixed public address; nothing is sent. The fixture is
structural only (the identifiers of PMC10742211, placeholder text)."""
import json, os, socket, sys, types
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
socket.getaddrinfo = no_network; socket.create_connection = no_network
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import europepmc as E, link_fetch as L

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("requests and sockets are stubs; nothing here can reach Europe PMC",
      sys.modules["requests"].get is no_network and socket.getaddrinfo is no_network and socket.create_connection is no_network)

XML = open(os.path.join(REPO, "broker", "tests", "fixtures", "epmc_PMC10742211_structure.xml"), "rb").read()
PUBLIC = lambda host: ["193.62.193.80"]
SEARCH_OK = json.dumps({"resultList": {"result": [{"pmid": "38132452", "pmcid": "PMC10742211", "isOpenAccess": "Y"}]}}).encode()

def net(routes):
    """A scripted network: url prefix -> (status, ctype, body) or an exception; every request recorded."""
    asked = []
    def transport(url, headers, timeout, max_bytes):
        asked.append(url)
        assert set(headers) == {"User-Agent"}, headers          # no credentials, ever
        for prefix, answer in routes:
            if url.startswith(prefix):
                if isinstance(answer, Exception): raise answer
                status, ctype, body = answer
                return status, {"content-type": ctype}, body[:max_bytes], len(body) > max_bytes
        return 404, {"content-type": "text/plain"}, b"not found", False
    return transport, asked

# which article a link names
for url, want in (("https://pmc.ncbi.nlm.nih.gov/articles/PMC10742211/", {"pmcid": "PMC10742211"}),
                  ("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10742211", {"pmcid": "PMC10742211"}),
                  ("https://europepmc.org/article/PMC/PMC10742211", {"pmcid": "PMC10742211"}),
                  ("https://europepmc.org/article/MED/38132452", {"pmid": "38132452"}),
                  ("https://pubmed.ncbi.nlm.nih.gov/38132452/", {"pmid": "38132452"}),
                  ("https://doi.org/10.3390/ijms242417435", {"doi": "10.3390/ijms242417435"}),
                  ("https://www.mdpi.com/1422-0067/24/24/17435", {})):
    check("ids_in_url(%s)" % url, E.ids_in_url(url) == want, E.ids_in_url(url))

# the article as an article
a = E.parse_jats(XML)
check("identifiers kept", a["ids"] == {"pmid": "38132452", "pmcid": "PMC10742211", "doi": "10.0000/fixture.38132452"}, a["ids"])
check("title kept", a["title"].startswith("FIXTURE TITLE"), a["title"])
check("abstract kept, the graphical abstract left out", "sentence two" in a["abstract"] and "graphical" not in a["abstract"])
heads = [s["heading"] for s in a["sections"]]
check("section headings kept, nested ones with their parent", heads == ["Introduction", "Materials and methods > Animals",
      "Materials and methods > Immunohistochemistry", "Results", "Results > Pendrin expression", "Discussion"], heads)
check("figure and table captions kept", [f["label"] for f in a["figures"]] == ["Figure 1", "Table 1"]
      and "figure 1 caption" in a["figures"][0]["caption"], a["figures"])
text = E.render(a)
check("rendered with headings and ids, no markup", "## Results > Pendrin expression" in text and "PMCID PMC10742211" in text
      and "<sec" not in text and "<p>" not in text, text[:300])
check("references are not read as body", "FIXTURE reference" not in text)
for bad, why in ((XML[:len(XML) // 2], "incomplete"), (b"<html><body>Just a moment...</body></html>", "not JATS"),
                 (b"<article><front/></article>", "empty")):
    try: E.parse_jats(bad); ok = False
    except ValueError: ok = True
    check("parse_jats refuses %s XML instead of inventing an article" % why, ok)

# a PubMed link, end to end through link_fetch: search -> fullTextXML -> the article
transport, asked = net([(E.API + "search?", (200, "application/json", SEARCH_OK)),
                        (E.API + "PMC10742211/fullTextXML", (200, "application/xml", XML))])
r = L.fetch("https://pubmed.ncbi.nlm.nih.gov/38132452/", transport=transport, resolve=PUBLIC)
check("a PubMed link is read from Europe PMC's full text", r["fetched"] and r.get("via") == "europepmc"
      and r["final_url"] == E.API + "PMC10742211/fullTextXML", {k: r.get(k) for k in ("kind", "via", "why", "final_url")})
check("the receipt names the article, its sections and captions", r["article"]["pmcid"] == "PMC10742211"
      and r["article"]["pmid"] == "38132452" and len(r["article"]["sections"]) == 6 and r["article"]["figures"] == 2, r.get("article"))
check("the publisher was never asked", all(u.startswith(E.API) for u in asked), asked)
check("say() tells him where the words came from", "read from Europe PMC's open-access full text PMC10742211" in L.say(r))

# failures are named, never a pretend read
def through(routes, url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10742211/", **kw):
    t, asked = net(routes)
    return L.fetch(url, transport=t, resolve=PUBLIC, **kw), asked
r, asked = through([(E.API + "PMC10742211/fullTextXML", (404, "text/plain", b"no")),
                    ("https://pmc.ncbi.nlm.nih.gov/", (200, "text/html", b"<html><body>Just a moment...</body></html>"))])
check("no open-access copy: the link is read as before, and the receipt says why Europe PMC could not",
      r["europepmc"]["kind"] == "not_available" and "HTTP 404" in r["europepmc"]["why"] and r.get("via") != "europepmc", r.get("europepmc"))
check("say() carries the Europe PMC reason", "Europe PMC full text not read - not_available" in L.say(r))
r, _ = through([(E.API + "PMC10742211/fullTextXML", ConnectionError("Connection reset by peer"))])
check("a dropped connection is an http_failure with its cause", r["europepmc"]["kind"] == "http_failure"
      and "Connection reset" in r["europepmc"]["why"], r.get("europepmc"))
art = E.read({"pmcid": "PMC10742211"}, fetch=lambda u, **kw: L.fetch(u, transport=net([(E.API, (200, "application/xml", XML))])[0],
                                                                       resolve=PUBLIC, keep_raw=True, article_route=False,
                                                                       **dict(kw, max_bytes=2000)))
check("a response over the byte cap is truncated and not parsed as an article", art["kind"] == "truncated"
      and not art["fetched"] and art["text"] == "", {k: art[k] for k in ("kind", "why")})
art = E.read({"pmcid": "PMC10742211"}, fetch=lambda u, **kw: L.fetch(u, transport=net([(E.API, (200, "application/xml", XML[:900]))])[0],
                                                                       resolve=PUBLIC, keep_raw=True, article_route=False, **kw))
check("incomplete XML is an extraction_failure", art["kind"] == "extraction_failure" and "incomplete" in art["why"], art["why"])
other = XML.replace(b"PMC10742211", b"PMC99999999")
art = E.read({"pmcid": "PMC10742211"}, fetch=lambda u, **kw: L.fetch(u, transport=net([(E.API, (200, "application/xml", other))])[0],
                                                                       resolve=PUBLIC, keep_raw=True, article_route=False, **kw))
check("XML for another article is not accepted", art["kind"] == "extraction_failure" and "PMC99999999" in art["why"], art["why"])
no_oa = json.dumps({"resultList": {"result": [{"pmid": "38132452"}]}}).encode()
art = E.read({"pmid": "38132452"}, fetch=lambda u, **kw: L.fetch(u, transport=net([(E.API + "search?", (200, "application/json", no_oa))])[0],
                                                                   resolve=PUBLIC, keep_raw=True, article_route=False, **kw))
check("no PMC copy listed: not_available, with the reason", art["kind"] == "not_available" and "no PMC full text" in art["why"], art["why"])
body_less = XML.split(b"<body>")[0] + b"</article>"
art = E.read({"pmcid": "PMC10742211"}, fetch=lambda u, **kw: L.fetch(u, transport=net([(E.API, (200, "application/xml", body_less))])[0],
                                                                       resolve=PUBLIC, keep_raw=True, article_route=False, **kw))
check("metadata and abstract with no body is not a full-text read", art["kind"] == "not_available" and not art["fetched"], art["why"])

# the URL safety rules still hold on this route
r, asked = through([], resolve_private=True) if False else (None, None)
t, asked = net([(E.API, (200, "application/xml", XML))])
r = L.fetch("https://pmc.ncbi.nlm.nih.gov/articles/PMC10742211/", transport=t, resolve=lambda h: ["10.0.0.5"])
check("a host resolving to a private address is still refused, Europe PMC included", not r["fetched"] and asked == []
      and r["europepmc"]["kind"] == "refused", r.get("europepmc"))
check("a bad PMC id is refused before any request", E.read({"pmcid": "PMC12x"})["kind"] == "refused")

# XML fetched any other way is read as an article too, not stripped markup
t, _ = net([("https://example.org/a.xml", (200, "application/xml", XML))])
r = L.fetch("https://example.org/a.xml", transport=t, resolve=PUBLIC)
check("JATS XML at any address is read with its headings", r["fetched"] and "## Discussion" in r["text"] and "<sec" not in r["text"], r["text"][:200])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
