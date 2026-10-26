#!/usr/bin/env python3
"""Linked PDB and mmCIF files are read (2026-10-26). He told Grok Bot his email reader could not open a linked
AlphaFold PDB file or a CIF file, so he went on pasted numbers instead of checking them: structure MIME types and
application/octet-stream were refused as "not text", and a file served as text/plain had its columns run into one
line. Every file here is made up in this test; the transport and the resolver are stubs, requests and sockets are
replaced, so nothing can reach the network. Scratch HOME."""
import importlib.util, os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-link-structures-")
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
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))
check("every store is a scratch one; requests and sockets are stubs", E.INBOX_LOG.startswith(HOME)
      and sys.modules["requests"].get is no_network and socket.getaddrinfo is no_network)

PUBLIC = lambda host: ["93.184.216.34"]
def site(pages):
    def t(url, headers, timeout, cap):
        status, rh, body = pages[url]
        body = body.encode() if isinstance(body, str) else body
        return status, rh, body[:cap], len(body) > cap
    return t
def get(url, ctype, body, **kw):
    return L.fetch(url, transport=site({url: (200, {"content-type": ctype} if ctype else {}, body)}), resolve=PUBLIC,
                   article_route=False, **kw)

# ── made-up files ──
def atom(n, rec, name, res, chain, seq, x, el):
    return "%-6s%5d %-4s %3s %1s%4d    %8.3f%8.3f%8.3f%6.2f%6.2f          %2s" % (rec, n, name, res, chain, seq, x, x + 1, x + 2, 1.0, 90.5, el)
def pdb(residues=3, chains="AB", header_lines=0, models=1):
    out = ["HEADER    TEST PROTEIN                            26-OCT-26   XTST              ",
           "TITLE     A MADE-UP STRUCTURE FOR A TEST                                        "]
    out += ["REMARK 999 FILLER LINE %4d                                                     " % k for k in range(header_lines)]
    n = 0
    for m in range(1, models + 1):
        if models > 1: out.append("MODEL     %4d" % m)
        for c in chains:
            for s in range(1, residues + 1):
                for nm, el in (("N", "N"), ("CA", "C"), ("C", "C")):
                    n += 1; out.append(atom(n, "ATOM", nm, "GLY", c, s, n * 0.5, el))
            out.append("TER")
        n += 1; out.append(atom(n, "HETATM", "ZN", " ZN", chains[0], 900, 3.0, "ZN"))
        if models > 1: out.append("ENDMDL")
    out.append("END")
    return "\n".join(out) + "\n"
PDB = pdb()
ATOM_LINE = atom(2, "ATOM", "CA", "GLY", "A", 1, 1.0, "C")
CIF = """data_XTST
#
_entry.id   XTST
_struct.title
;A made-up structure
 written over two lines
;
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.pdbx_PDB_model_num
ATOM   1 N N     GLY A 1  1.000  2.000  3.000 1
ATOM   2 C CA    GLY A 1  2.000  3.000  4.000 1
ATOM   3 O "O5'" G   A 2  3.000  4.000  5.000 1
ATOM   4 C CA    GLY B 1  4.000  5.000  6.000 1
HETATM 5 ZN ZN   ZN  B 900 5.000 6.000  7.000 1
#
"""

# ── PDB: structure MIME types, validated octet-stream, text/plain ──
URL = "https://alphafold.example.org/files/AF-XTST-F1-model_v4.pdb"
for ctype in ("chemical/x-pdb", "application/pdb", "application/octet-stream", "text/plain", "text/plain; charset=utf-8", ""):
    r = get(URL, ctype, PDB)
    s = r.get("structure") or {}
    check("PDB served as %r is read as a structure" % ctype, r["kind"] == "fetched" and s.get("format") == "PDB", r)
r = get(URL, "chemical/x-pdb", PDB)
s = r["structure"]
check("counts made in code: entry, title, models, chains, residues, atoms",
      (s["entry"], s["title"], s["models"], s["chains"], s["residues"], s["atoms"], s["hetatm"]) ==
      ("XTST", "A MADE-UP STRUCTURE FOR A TEST", 1, ["A", "B"], 6, 19, 1), s)
check("the original content is kept whole, apart from the preview", s["content"] == PDB and r["text"] != PDB, s["content"][:200])
check("the preview keeps each record's columns and its own line", ("\n" + ATOM_LINE + "\n") in r["text"], r["text"])
check("the text says it was read and that it is a preview, not an analysis", L.NOT_ANALYSIS in r["text"]
      and "not an analysis" in r["text"], r["text"][:300])
check("a structure file served as text/plain no longer has its newlines run together",
      ("\n" + ATOM_LINE + "\n") in get(URL, "text/plain", PDB)["text"])
r = get("https://files.example.org/model", "application/octet-stream", PDB)
check("octet-stream with no extension is read when the bytes validate as PDB", r["kind"] == "fetched" and r.get("structure"), r)
r = get(URL, "chemical/x-pdb", pdb(models=3))
check("a multi-model file counts its models, the rest in model 1", r["structure"]["models"] == 3 and r["structure"]["atoms"] == 19
      and r["structure"]["atom_records"] == 57 and "in model 1" in r["text"], r["structure"])

# ── mmCIF ──
CURL = "https://files.example.org/download/XTST.cif"
for ctype in ("chemical/x-mmcif", "chemical/x-cif", "application/mmcif", "application/octet-stream", "text/plain", ""):
    r = get(CURL, ctype, CIF)
    check("mmCIF served as %r is read as a structure" % ctype, r["kind"] == "fetched" and (r.get("structure") or {}).get("format") == "mmCIF", r)
r = get(CURL, "chemical/x-mmcif", CIF)
s = r["structure"]
check("mmCIF counts: entry, title from a ;-field, chains, residues, atoms, quoted atom names",
      (s["entry"], s["title"], s["models"], s["chains"], s["residues"], s["atoms"], s["hetatm"]) ==
      ("XTST", "A made-up structure written over two lines", 1, ["A", "B"], 3, 5, 1), s)
check("a multiline ;-field and the loop rows keep their lines and spacing in the preview",
      ";A made-up structure\n written over two lines\n;" in r["text"] and "ATOM   3 O \"O5'\" G   A 2  3.000" in r["text"], r["text"])
check("mmCIF text says preview, not analysis", L.NOT_ANALYSIS in r["text"])

# ── refused, with a reason ──
def refused(name, url, ctype, body, words):
    r = get(url, ctype, body)
    check(name, not r["fetched"] and r["kind"] == "extraction_failure" and not r.get("structure")
          and all(w in r["why"] for w in words), r)
BIN = bytes(range(256)) * 8
refused("arbitrary binary as octet-stream is refused", "https://files.example.org/blob", "application/octet-stream", BIN,
        ["application/octet-stream", "not a readable PDB or mmCIF", "binary"])
refused("binary behind a .pdb extension is refused", URL, "", BIN, [".pdb", "binary"])
refused("binary behind a .cif extension served as octet-stream is refused", CURL, "application/octet-stream", BIN, ["binary"])
refused("a gzip file behind .cif.gz is refused, said compressed", CURL + ".gz", "application/octet-stream",
        b"\x1f\x8b\x08\x00" + BIN, ["gzip"])
refused("an HTML page behind a .pdb extension is refused", URL, "text/html",
        "<!DOCTYPE html><html><body>Not found</body></html>", [".pdb", "HTML"])
refused("an HTML page served as chemical/x-pdb is refused", URL, "chemical/x-pdb", "<html><body>x</body></html>", ["HTML"])
refused("text that is not a structure, as octet-stream, is refused", "https://files.example.org/blob",
        "application/octet-stream", "hello there, this is a note\n", ["neither with a PDB record"])
refused("a PDB with no coordinates is refused", URL, "chemical/x-pdb", "HEADER    X\nREMARK   1 nothing\nEND\n", ["no ATOM or HETATM"])
bad = PDB.replace(ATOM_LINE, ATOM_LINE[:30] + "   x.xxx" + ATOM_LINE[38:])
refused("a PDB with non-numeric coordinates is refused, line named", URL, "chemical/x-pdb", bad, ["coordinate columns", "line 4"])
refused("a PDB that is mostly not records is refused", URL, "chemical/x-pdb",
        PDB + "".join("this is prose line %d\n" % k for k in range(40)), ["not PDB records"])
refused("mmCIF with an unclosed ;-field is refused", CURL, "chemical/x-mmcif", CIF.split("\n;\nloop_")[0], ["never closed"])
refused("mmCIF whose loop rows do not fill the columns is refused", CURL, "chemical/x-mmcif",
        CIF.replace("ATOM   4 C CA    GLY B 1  4.000  5.000  6.000 1\n", "ATOM   4 C CA\n"), ["do not fill"])
refused("a data_ line alone is not mmCIF", CURL, "chemical/x-cif", "data_X\n", ["no _items"])
refused("non-UTF-8 bytes as chemical/x-pdb are refused", URL, "chemical/x-pdb", PDB.encode() + b"\xff\xfe stray\n", ["not UTF-8"])

# ── truncation: of the bytes read, and of the preview ──
BIG = pdb(residues=150, header_lines=120)
r = get(URL, "chemical/x-pdb", BIG)
s, text = r["structure"], r["text"]
check("a whole file over the preview budget: the preview says how much of it was shown",
      r["kind"] == "fetched" and "[PREVIEW: " in text and ("of %d lines shown" % s["lines"]) in text
      and ("of %d atom records shown" % s["atom_records"]) in text and len(text) <= L.STRUCTURE_TEXT_CHARS, text[-400:])
check("the preview reaches the first coordinates past a long header, the gap marked",
      "[... lines " in text and "not shown ...]" in text and "\nATOM      1 " in text, text)
cap = 20000
r = get(URL, "chemical/x-pdb", BIG, max_bytes=cap)
check("a file over the byte cap is read to the cap, kind truncated, structure marked truncated",
      r["kind"] == "truncated" and r["structure"]["truncated"] and r["structure"]["bytes"] == cap
      and "[TRUNCATED: only the first %d bytes" % cap in r["text"] and "part read" in r["text"], r["text"][:500])
check("a truncated file's counts cover only what was read", r["structure"]["atom_records"] < get(URL, "chemical/x-pdb", BIG)["structure"]["atom_records"])
r = get(CURL, "chemical/x-mmcif", CIF.split("ATOM   4")[0] + "ATOM   4 C C", max_bytes=10 ** 6)
check("an mmCIF cut mid-row by the network is refused when the bytes were whole (not truncated)", not r["fetched"], r)
cut = CIF.encode()[:len(CIF.encode()) - 30]
r = get(CURL, "chemical/x-mmcif", CIF, max_bytes=len(cut))
check("an mmCIF cut by the byte cap is still read, marked truncated", r["kind"] == "truncated" and r["structure"]["truncated"], r)

# ── what he receives: the 1,500-character cap keeps the markers ──
pages = E.links_read("see " + URL, fetch=lambda u: get(URL, "chemical/x-pdb", BIG))
t = pages[0]["text"]
check("his email excerpt fits 1,500 characters and keeps the counts, the preview marker and the not-an-analysis line",
      len(t) <= E.LINK_CHARS and L.NOT_ANALYSIS in t and "[PREVIEW: " in t and "Counted in code" in t, (len(t), t))
check("the excerpt keeps record lines whole", all(len(l) <= 80 or l.startswith(("STRUCTURE", "Counted", "[")) for l in t.splitlines()), t)
check("the letter keeps the excerpt, not the file", "content" not in pages[0] and len(t) < len(BIG))
view = E.pages_view(pages)
check("pages_view shows the structure excerpt with its lines", "[LINK 1]" in view and "\nHEADER    TEST PROTEIN" in view, view[:300])
said = L.say(get(URL, "chemical/x-pdb", BIG), 3000)
check("say() gives the bounded structure view with its markers", URL in said and "[PREVIEW: " in said and L.NOT_ANALYSIS in said
      and len(said) <= 3000 + len(URL) + 1, said[-300:])
r = get(URL, "chemical/x-pdb", BIG)
check("a successful download is never called an analysis", "analysis of" not in r["text"].replace("not an analysis of", ""))

# ── the other readers are as they were ──
html = "<html><head><style>p{}</style></head><body><p>8SGW:   pendrin,\n pig</p><script>x()</script></body></html>"
check("HTML is made plain as before", L._text_of(html.encode(), "text/html", "https://www.rcsb.org/structure/8SGW", None)
      == ("8SGW: pendrin, pig", ""), L._text_of(html.encode(), "text/html", "https://x.example/", None))
check("plain text that is not a structure is read as before (whitespace run together)",
      L._text_of(b"A note.\n\n  Two lines.", "text/plain", "https://x.example/n.txt", None) == ("A note. Two lines.", ""))
check("JSON is read as before", L._text_of(b'{"a": 1}', "application/json", "https://x.example/a", None) == ('{"a": 1}', ""))
check("an image is still not text, said the same way",
      L._text_of(b"\x89PNG....", "image/png", "https://x.example/a.png", None) == ("", "content type image/png is not text"))
check("octet-stream that is not a structure is still refused",
      L._text_of(BIN, "application/octet-stream", "https://x.example/a", None)[0] == "")
check("a PDF with no reader is said as before",
      L._text_of(b"%PDF-1.7 ...", "application/pdf", "https://x.example/a.pdf", None) == ("", "a PDF, and no PDF reader was given"))
check("a PDF goes through the reader it is given, as before",
      L._text_of(b"%PDF-1.7 ...", "application/octet-stream", "https://x.example/a.pdf", lambda b: " words ") == ("words", ""))
r = get("https://x.example/page", "text/html", "<html><body><p>hello</p></body></html>")
check("an HTML fetch carries no structure", r["kind"] == "fetched" and "structure" not in r and r["text"] == "hello", r)
check("a refused address is still refused before any request for a .pdb link",
      L.fetch("http://localhost/x.pdb", transport=no_network, resolve=PUBLIC)["kind"] == "refused")
check("the byte and link limits are unchanged", L.MAX_BYTES == 4 * 1024 * 1024 and L.MAX_REDIRECTS == 5
      and E.LINK_CHARS == 1500 and E.LINKS_READ == 5)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
