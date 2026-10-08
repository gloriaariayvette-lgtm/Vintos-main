#!/usr/bin/env python3
"""Links are opened truthfully (2026-10-08). Grok Bot's 7 October letter (Gmail 1a11690d001e1a03) said "The links
are bare, with no redirects" and all six were google.com/url wrappers; fetching a wrapper reads Google's notice,
not the source, and every failure came back as ''. The transport and the resolver are stubs that record what was
asked; requests and sockets are replaced so nothing here can reach the network. Scratch HOME."""
import importlib.util, json, os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-link-fetch-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
socket.getaddrinfo = no_network; socket.create_connection = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, path))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
L = load("link_fetch", "scripts/link_fetch.py")
E = load("want_email", "scripts/want_email.py")
S = load("scholar", "scripts/scholar.py")
G = load("grok_letters", "scripts/grok_letters.py")
W = load("vintos_websearch", "bin/vintos-websearch.py")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("every store is a scratch one; requests and sockets are stubs", E.INBOX_LOG.startswith(HOME)
      and sys.modules["requests"].get is no_network and socket.getaddrinfo is no_network)

UST = "&source=gmail&ust=1791466351762000&sa=E"
REAL = ["https://www.rcsb.org/structure/8SGW", "https://rest.uniprot.org/uniprotkb/A0A8D0Z6H8.fasta",
        "https://github.com/ShintaroMinami/PyDSSP", "https://docs.python.org/3/library/multiprocessing.html",
        "https://www.nobelprize.org/prizes/chemistry/2026/press-release/",
        "https://www.kva.se/app/uploads/2026/10/nobel-chemistry-2026-scientific-background_98nb7jaql4.pdf"]
WRAPPED = ["https://www.google.com/url?q=%s%s" % (u, UST) for u in REAL]
LETTER = ("Four things. Caveat first on each. The links are bare, with no redirects.\n\n1. 8SGW.\n" +
          "\n".join(WRAPPED[:2]) + "\n\n2. PyDSSP.\n" + WRAPPED[2] + "\n\n3. Two processes.\n" + WRAPPED[3] +
          "\n\n4. Nobel.\n" + "\n".join(WRAPPED[4:]) + "\n\nThat's all of it.")

# ── unwrapping ──
check("the wrapper resolves to its source, from its own query string", L.unwrap(WRAPPED[0]) == (REAL[0], True), L.unwrap(WRAPPED[0]))
check("a bare link is left alone", L.unwrap(REAL[0]) == (REAL[0], False))
found = L.links_in(LETTER)
check("all six links found, each with its original and its destination",
      [l["url"] for l in found] == REAL and [l["original"] for l in found] == WRAPPED and all(l["wrapped"] for l in found), found)
html = '<div>See <a href="https://www.google.com/url?q=https://www.rcsb.org/structure/8SGW&amp;sa=E">the entry</a></div>'
check("an HTML anchor gives its href's destination, entities decoded", L.links_in(html) == [
      {"original": "https://www.google.com/url?q=https://www.rcsb.org/structure/8SGW&sa=E", "url": REAL[0], "wrapped": True}], L.links_in(html))
check("a wrapper with no http destination is refused, not fetched",
      L.fetch("https://www.google.com/url?q=javascript:alert(1)", transport=no_network)["kind"] == "refused")

# ── fetching ──
PUBLIC = lambda host: ["93.184.216.34"]
asked = []
def site(pages):
    def t(url, headers, timeout, cap):
        asked.append((url, dict(headers)))
        status, rh, body = pages[url]
        body = body.encode() if isinstance(body, str) else body
        return status, rh, body[:cap], len(body) > cap
    return t
PAGE = "<html><body><p>8SGW: pendrin, pig, cryo-EM. Missing residues 586-653.</p></body></html>"
asked.clear()
r = L.fetch(WRAPPED[0], transport=site({REAL[0]: (200, {"content-type": "text/html"}, PAGE)}), resolve=PUBLIC)
check("a wrapped link is fetched at its source, never at google.com",
      r["kind"] == "fetched" and r["fetched"] and [u for u, _ in asked] == [REAL[0]] and "586-653" in r["text"], (r, asked))
check("the receipt keeps the original, the destination and the final url",
      r["original_url"] == WRAPPED[0] and r["url"] == REAL[0] and r["final_url"] == REAL[0] and r["wrapped"], r)
check("the only header sent is a User-Agent: no cookie, no authorization", all(set(h) == {"User-Agent"} for _, h in asked), asked)

asked.clear()
hop = {"http://rcsb.org/structure/8SGW": (301, {"location": "https://www.rcsb.org/structure/8SGW"}, ""),
       REAL[0]: (200, {"content-type": "text/html"}, PAGE)}
r = L.fetch("http://rcsb.org/structure/8SGW", transport=site(hop), resolve=PUBLIC)
check("a permitted redirect is followed and the final url recorded",
      r["kind"] == "fetched" and r["final_url"] == REAL[0] and r["hops"] == ["http://rcsb.org/structure/8SGW", REAL[0]], r)

hop = {"https://evil.example/x": (302, {"location": "http://127.0.0.1:8080/admin"}, "")}
def resolve(host): return {"evil.example": ["93.184.216.34"], "inside.example": ["10.0.0.5"]}[host]
r = L.fetch("https://evil.example/x", transport=site(hop), resolve=resolve)
check("a redirect to a private or local target is refused at that hop", r["kind"] == "refused" and not r["fetched"]
      and r["final_url"].startswith("http://127.0.0.1"), r)
check("a host that resolves to a private address is refused before any request",
      L.fetch("https://inside.example/", transport=no_network, resolve=resolve)["kind"] == "refused")
for bad in ("http://localhost/", "https://user:pw@www.rcsb.org/", "https://www.rcsb.org:8443/", "file:///etc/passwd",
            "http://[::1]/", "http://169.254.169.254/latest/meta-data/"):
    check("refused: %s" % bad, L.fetch(bad, transport=no_network, resolve=PUBLIC)["kind"] == "refused")

loop = {"https://a.example/%d" % i: (302, {"location": "https://a.example/%d" % (i + 1)}, "") for i in range(20)}
r = L.fetch("https://a.example/0", transport=site(loop), resolve=PUBLIC)
check("redirects are bounded", r["kind"] == "refused" and len(r["hops"]) == L.MAX_REDIRECTS + 1, r)

r = L.fetch(REAL[2], transport=site({REAL[2]: (404, {}, "not found")}), resolve=PUBLIC)
check("an HTTP failure is http_failure with its status, not ''", r["kind"] == "http_failure" and r["http_status"] == 404 and not r["fetched"], r)
def boom(*a): raise TimeoutError("timed out")
check("a timeout is http_failure with its reason", L.fetch(REAL[2], transport=boom, resolve=PUBLIC)["why"].startswith("TimeoutError"))
r = L.fetch(REAL[3], transport=site({REAL[3]: (200, {"content-type": "image/png"}, b"\x89PNG....")}), resolve=PUBLIC)
check("nothing readable is extraction_failure", r["kind"] == "extraction_failure" and not r["fetched"], r)
r = L.fetch(REAL[5], transport=site({REAL[5]: (200, {"content-type": "application/pdf"}, b"%PDF-1.7 ...")}), resolve=PUBLIC)
check("a PDF with no reader given is extraction_failure, said so", r["kind"] == "extraction_failure" and "PDF" in r["why"], r)
big = "<html><body><p>" + "a" * 5000 + "</p></body></html>"
r = L.fetch(REAL[4], max_bytes=1000, transport=site({REAL[4]: (200, {"content-type": "text/html"}, big)}), resolve=PUBLIC)
check("a page over the size bound is read only to the bound and marked truncated",
      r["kind"] == "truncated" and r["fetched"] and r["truncated"] and r["bytes"] == 1000, r)
check("the receipt in words says truncated", "TRUNCATED" in L.say(r))
r = L.fetch(WRAPPED[2], transport=site({REAL[2]: (403, {}, "")}), resolve=PUBLIC)
check("a failure names the source that failed, not the wrapper", r["final_url"] == REAL[2] and "github.com" in r["why"]
      and "NOT READ (http_failure)" in L.say(r) and "redirect wrapper" in L.say(r), L.say(r))

# ── his mail: the letter's wrappers are named, not left to his eye ──
note = E.links_note(LETTER)
check("his reading of the letter is told it has 6 links, 6 of them wrapped, with each destination",
      "6 links, 6 of them wrapped" in note and all(u in note for u in REAL), note)
check("a letter with bare links is told they are bare", "bare, with no redirect wrapper" in E.links_note("see " + REAL[0]))
check("stored with the letter: original and destination", E.links_kept(LETTER)[0] == {"original": WRAPPED[0], "url": REAL[0], "wrapped": True})
prompts = []
E._save(E.TEND_STATE, {})
E.read_mail([{"id": "1a11690d001e1a03", "from": "Vintos <me@example.org>", "subject": "[Grok Bot] Wednesday",
              "date": "Wed, 07 Oct 2026", "body": LETTER, "whole": True}],
            think=lambda s, ask, n=400: (prompts.append(ask), '{"what":"x","to_me":"y","keep":false}')[1], want=lambda *a: None)
row = [json.loads(l) for l in open(E.INBOX_LOG)][-1]
check("read_mail's prompt carries the links note; the stored row keeps both forms",
      prompts and "6 of them wrapped" in prompts[0] and row["links"][0]["url"] == REAL[0] and WRAPPED[0] in row["body"], prompts[:1])
mail_html = {"mime_type": "text/html", "body": {"content": html}}
check("an HTML mail keeps each anchor's destination when made plain",
      "the entry (https://www.google.com/url?q=https://www.rcsb.org/structure/8SGW&sa=E)" in E._payload_text(mail_html), E._payload_text(mail_html))

# ── the callers ──
try:
    E.fetch_text(REAL[2], transport=site({REAL[2]: (404, {}, "")}), resolve=PUBLIC); raised = None
except E.NotRead as exc:
    raised = exc
check("want_email.fetch_text raises NotRead with the receipt instead of returning ''",
      raised is not None and raised.receipt["kind"] == "http_failure", raised)
page = '<html><body><a href="mailto:a.person@uni.edu">write</a></body></html>'
check("fetch_text returns the page as it came (find_address reads mailto: in the markup)",
      "mailto:a.person@uni.edu" in E.fetch_text(REAL[0], transport=site({REAL[0]: (200, {"content-type": "text/html"}, page)}), resolve=PUBLIC))
check("scholar.links_in gives destinations, so a wrapped scholarly link is recognised",
      S.links_in("see " + "https://www.google.com/url?q=https://arxiv.org/abs/2401.00001" + UST) == ["https://arxiv.org/abs/2401.00001"]
      and S.is_scholarly(S.links_in("https://www.google.com/url?q=https://arxiv.org/abs/2401.00001" + UST)[0]))
said = G._read_links([WRAPPED[0]], lambda u: L.fetch(u, transport=site({REAL[0]: (200, {"content-type": "text/html"}, PAGE)}), resolve=PUBLIC))
check("Grok letters: a receipt reads as its destination and text", REAL[0] in said and "586-653" in said, said)
said = G._read_links([WRAPPED[2]], lambda u: L.fetch(u, transport=site({REAL[2]: (403, {}, "")}), resolve=PUBLIC))
check("Grok letters: a failed link says NOT READ and why, not '(empty)'", "NOT READ (http_failure)" in said and "(empty)" not in said, said)
logged = []
W.log = logged.append
check("web search: a refused page is '' with the kind logged",
      W.fetch_page("http://localhost/x", transport=no_network, resolve=PUBLIC) == "" and logged and "refused" in logged[-1], logged)
check("web search: a wrapped result is read at its source",
      "586-653" in W.fetch_page(WRAPPED[0], transport=site({REAL[0]: (200, {"content-type": "text/html"}, PAGE)}), resolve=PUBLIC))
check("lab_http keeps its no-redirect rule", "return None" in open(os.path.join(REPO, "scripts", "lab_http.py")).read())
check("link_fetch is in the deploy manifest", "link_fetch.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
