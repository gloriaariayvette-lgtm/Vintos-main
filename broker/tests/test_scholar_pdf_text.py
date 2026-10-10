#!/usr/bin/env python3
"""A paper that arrives as a PDF is read, not emptied (Vintos, 2026-10). scholar._get told link_fetch a PDF was
the word 'pdf' and read_url judged PDF-ness from the address alone, so a PDF served from a doi or a landing page
went through the HTML stripper. Here a small genuine PDF is served by a stubbed transport under a non-.pdf
address and must come back as its sentences. requests and sockets are replaced; scratch HOME; no dossier is
written anywhere real."""
import importlib.util, os, re, shutil, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-scholar-pdf-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
socket.getaddrinfo = no_network; socket.create_connection = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, path))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
L = load("link_fetch", "scripts/link_fetch.py")
S = load("scholar", "scripts/scholar.py")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the dossier store is a scratch one; requests and sockets are stubs", S.DOSSIERS.startswith(HOME)
      and sys.modules["requests"].get is no_network and socket.getaddrinfo is no_network, S.DOSSIERS)

# ── a small real PDF: one page, uncompressed content stream, correct xref ──
LINES = ["Role play with large language models, section %d: the model is not the character it plays." % i for i in range(1, 41)]
def make_pdf(lines):
    content = "BT /F1 9 Tf 40 760 Td 11 TL " + " ".join("(%s) Tj T*" % l for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out)); out += ("%d 0 obj\n%s\nendobj\n" % (i, o)).encode()
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for off in offsets: out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return out
PDF = make_pdf(LINES)
check("the fixture is a real PDF", PDF.startswith(b"%PDF-") and b"endobj" in PDF)

# His reader needs pdftotext or pypdf. When the bench has neither, a tiny reader of this one uncompressed file
# stands in, so the wiring (read_url -> link_fetch -> the PDF reader) is still what is tested.
have_reader = bool(shutil.which("pdftotext")) or importlib.util.find_spec("pypdf") is not None
if not have_reader:
    print("note: neither pdftotext nor pypdf on this host; a minimal reader stands in for pdf_text")
    S.pdf_text = lambda data: "\n".join(m.decode() for m in re.findall(rb"\((.*?)\) Tj", data))
check("pdf_text reads the fixture's sentences", "section 7:" in S.pdf_text(PDF), S.pdf_text(PDF)[:200])

PUBLIC = lambda host: ["93.184.216.34"]
asked = []
def site(pages):
    def t(url, headers, timeout, cap):
        asked.append(url)
        status, rh, body = pages[url]
        body = body.encode() if isinstance(body, str) else body
        return status, rh, body[:cap], len(body) > cap
    return t

# ── the regression: a PDF served under an address with no '.pdf' in it ──
DOI = "https://doi.org/10.1000/roleplay"
text, where = S.read_url(DOI, transport=site({DOI: (200, {"content-type": "application/pdf"}, PDF)}), resolve=PUBLIC)
check("a PDF from a doi comes back with non-empty text", len(text) > 1500 and where == DOI, (len(text), where))
check("the text is the paper's sentences, not PDF markup",
      "section 7: the model is not the character it plays" in text and "endobj" not in text and " Tj" not in text and "%PDF" not in text, text[:300])
check("the source was asked once, nothing else", asked == [DOI], asked)

# ── a .pdf address still works, and HTML is untouched ──
asked.clear()
ARX = "https://arxiv.org/pdf/2305.16367.pdf"
text, where = S.read_url(ARX, transport=site({ARX: (200, {"content-type": "application/pdf"}, PDF)}), resolve=PUBLIC)
check("a .pdf address reads the same way", "section 12:" in text and "endobj" not in text, text[:200])
PAGE = "<html><body><p>" + " ".join(LINES) + "</p></body></html>"
HTM = "https://arxiv.org/abs/2305.16367"
text, where = S.read_url(HTM, transport=site({HTM: (200, {"content-type": "text/html"}, PAGE)}), resolve=PUBLIC)
check("an HTML page is still read as text", "section 3:" in text and "<p>" not in text, text[:200])
bad = "https://arxiv.org/abs/9999.99999"
text, why = S.read_url(bad, transport=site({bad: (404, {}, "gone")}), resolve=PUBLIC)
check("a failure still says why instead of ''", text == "" and "http_failure" in why, why)
check("a non-scholarly host is still not opened", S.read_url("https://example.com/x.pdf", transport=no_network)[0] == "")

# ── the raw-byte helper is unchanged; the text helper hands link_fetch his reader ──
src = open(os.path.join(REPO, "scripts", "scholar.py")).read()
check("_get still gives link_fetch the placeholder and returns bytes/json", 'pdf=lambda b: "pdf"' in src and 'if want == "bytes":' in src)
check("_read_text passes pdf=pdf_text", "pdf=pdf_text" in src)
check("no dossier was written", not os.path.exists(S.DOSSIERS) or not os.listdir(S.DOSSIERS))

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
