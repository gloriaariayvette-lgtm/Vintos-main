#!/usr/bin/env python3
"""He reads further into a linked page than its opening (28 October: a letter cited the TRANSMEM annotations of a
UniProt record and section 2.6.20 of a device manual; only the first 1,500 characters of each page were kept, nothing
said so, and he asked Grok Bot to paste them). The page's text is kept under its hash; READ MORE jumps to a heading,
section number or word, or goes on from a character, bounded per reading and per letter, in both the reading and
the reply; what is fetched, kept and shown is said, and a passage that cannot be shown says why. Every page is made
up here; the transport, the resolver, the PDF reader, the models and the sender are stubs; sockets are refused;
scratch HOME."""
import json, os, socket, sys, tempfile, types
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="letter-link-sections-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"))
NET = []
def no_network(*a, **k):
    NET.append(a); raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
socket.getaddrinfo = no_network; socket.create_connection = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_email as W
import link_fetch as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))
check("every store is a scratch one", W.INBOX_LOG.startswith(HOME) and W.LINK_STORE.startswith(HOME))

PUBLIC = lambda host: ["93.184.216.34"]
SITE = {}
def transport(url, headers, timeout, cap):
    status, ctype, body = SITE[url]
    body = body.encode() if isinstance(body, str) else body
    return status, {"content-type": ctype}, body[:cap], len(body) > cap
PDF_TEXT = {}
def pdf_reader(data):
    if data not in PDF_TEXT:
        raise ValueError("the PDF reader found no text layer")
    return PDF_TEXT[data]
REAL_FETCH = L.fetch
def fetch(url, **kw):
    return REAL_FETCH(url, transport=transport, resolve=PUBLIC, pdf=pdf_reader, article_route=False, **kw)

# ── made-up pages ──
UNI = "https://rest.uniprot.org/uniprotkb/O43511.txt"
uni = ("ID   S26A4_HUMAN   Reviewed;   780 AA.\nAC   O43511;\n" +
       "".join("CC   -!- FUNCTION: filler comment line %04d about anion exchange in the inner ear.\n" % k for k in range(400)) +
       "FT   TOPO_DOM        1..43\nFT                   /note=\"Cytoplasmic\"\n"
       "FT   TRANSMEM        44..64\nFT                   /note=\"Helical\"\n"
       "FT   TRANSMEM        77..97\nFT                   /note=\"Helical\"\n" +
       "".join("FT   VARIANT         %d\nFT                   /note=\"in DFNB4\"\n" % k for k in range(100, 160)) +
       "SQ   SEQUENCE   780 AA;\n")
SITE[UNI] = (200, "text/plain", uni)
MAN = "https://manuals.example.org/device-x200.pdf"
toc = "Contents\n" + "".join("2.6.%d Setting %d ........................ %d\n" % (k, k, 40 + k) for k in range(1, 25))
body_ = "".join("\n2.%d.%d Setting %d\n%s\n" % (6 if k < 25 else 7, k % 25 or 1, k, ("Plain filler about setting %d. " % k) * 60)
                for k in range(1, 25))
manual = toc + body_.replace("\n2.6.20 Setting 20\n", "\n2.6.20 Setting 20\nTo reset the sensor hold the PAIR key for ten seconds.\n")
PDF = b"%PDF-1.7 made-up manual"
PDF_TEXT[PDF] = manual
SITE[MAN] = (200, "application/pdf", PDF)
SHORT = "https://notes.example.org/short"
SITE[SHORT] = (200, "text/html", "<html><body><p>A short page about pendrin.</p></body></html>")
BROKEN = "https://manuals.example.org/scanned.pdf"
SITE[BROKEN] = (200, "application/pdf", b"%PDF-1.4 a scan with no text")

# ── a short page reads as before, and is said to be whole ──
pages = W.links_read("see " + SHORT, fetch=fetch)
p = pages[0]
check("a short page: its text as before, fetched whole", p["kind"] == "fetched" and p["text"] == "A short page about pendrin."
      and p["chars"] == len(p["text"]) and p["retained"] == p["chars"] and not p["download_truncated"], p)
view = W.pages_view(pages)
check("a short page is labelled as shown in full, with no READ MORE offer", "SHOWN: all %d characters" % p["chars"] in view
      and "END OF WHAT IS SHOWN" not in view and "READ MORE" not in view and "(the whole page)" in view, view)
check("nothing in a short page is a cue to read further", W.letter_cues("TRANSMEM section 2.6.20 " + SHORT, pages) == [])

# ── the UniProt record: the TRANSMEM lines are far past the opening ──
LETTER = ("[Grok Bot] Wednesday: pendrin.\n1. UniProt O43511: " + UNI + " - look at the TRANSMEM annotations.\n"
          "2. The device manual, section 2.6.20 on the sensor reset: " + MAN + "\n3. A scan: " + BROKEN + "\n")
pages = W.links_read(LETTER, fetch=fetch)
u, m, b = pages
at = uni.replace("\n", " ").find("TRANSMEM")
check("the record's text is retained whole, the opening shown, its identity kept", u["url"] == UNI and u["chars"] > 20000
      and u["retained"] == u["chars"] and u["shown"] == [0, 1500] and len(u["text"]) == 1500 and len(u["sha256"]) == 64, u)
check("the TRANSMEM lines are not in what is shown first", "TRANSMEM" not in u["text"] and at > 1500, at)
check("the page row keeps no full text, only the shown excerpt and its hash", all(len(x.get("text", "")) <= 1500 for x in pages)
      and not any(k in u for k in ("full", "content")))
check("the manual came through the PDF reader, its section far in", m["kind"] == "fetched" and m["chars"] == len(manual.strip())
      and manual.find("2.6.20 Setting 20\nTo reset") > 10000, m)
check("a PDF with no text is an extraction failure, named", b["kind"] == "extraction_failure" and "no text layer" in b["why"], b)
view = W.pages_view(pages)
check("a partial page is labelled with what was fetched, retained and shown",
      "SHOWN: characters 1-1500 of %d" % u["chars"] in view and "RETAINED: all %d characters" % u["chars"] in view
      and "FETCHED: %d characters of text from %d bytes downloaded (the whole page)" % (u["chars"], len(uni)) in view, view[:900])
check("and with how to read on", "READ MORE [LINK 1] FROM 1501" in view and "Do not ask anyone to paste it" in view)
check("the unreadable scan is still NOT READ, with why", "[LINK 3] %s\nNOT READ (extraction_failure)" % BROKEN in view)

cues = W.letter_cues(LETTER, pages)
check("the letter's own cues are found in the pages they belong to",
      {"link": 1, "find": "TRANSMEM"} in cues and {"link": 2, "find": "2.6.20"} in cues and len(cues) <= W.PASSAGES_PER_READ, cues)
got = W.read_more(pages, [{"link": 1, "find": "TRANSMEM"}])
d = got[0]
check("TRANSMEM jumps to the first annotation, labelled with its place", d["status"] == "shown" and "TRANSMEM 44..64" in d["text"]
      and d["from"] > 1500 and "match 1 of 2" in d["match"] and len(d["text"]) <= W.PASSAGE_CHARS, d)
again = W.read_more(pages, [{"link": 1, "find": "TRANSMEM"}], prior=got)
check("asked again, it goes past what was shown: the second span was already in the first passage, so no further match",
      "TRANSMEM 77..97" in d["text"] and again[0]["status"] == "absent"
      and "no further match for \"TRANSMEM\" after character %d" % d["to"] in again[0]["why"], again)
on = W.read_more(pages, [{"link": 1}], prior=got)
check("READ MORE with no anchor goes on from where the last passage stopped", on[0]["status"] == "shown"
      and on[0]["from"] == d["to"], (on[0]["from"], d["to"]))
frm = W.read_more(pages, [{"link": 1, "from": 1501}])
check("FROM 1501 continues right after the shown opening", frm[0]["status"] == "shown" and frm[0]["from"] == 1500
      and frm[0]["text"] == W._kept_page(u)[1500:3000])
nxt = W.read_more(pages, [{"link": 1, "from": 1501}, {"link": 1}], prior=[])
check("repeated reads advance", nxt[1]["status"] == "shown" and nxt[1]["from"] == nxt[0]["to"], nxt)

sec = W.read_more(pages, [{"link": 2, "find": "2.6.20"}])[0]
check("section 2.6.20 opens at its heading, not at its contents line", sec["status"] == "shown"
      and sec["text"].startswith("2.6.20 Setting 20\nTo reset the sensor") and "......" not in sec["text"][:200], sec["text"][:200])
check("and not at 2.6.2 or 2.6.200", "2.6.2 Setting" not in sec["text"][:30])
absent = W.read_more(pages, [{"link": 2, "find": "TRANSMEM"}])[0]
check("a section that is not in the page is said to be absent, with how much was searched", absent["status"] == "absent"
      and "not in the page's kept text (%d characters searched)" % m["chars"] in absent["why"], absent)
end = W.read_more(pages, [{"link": 1, "from": u["chars"] + 5}])[0]
check("a character past the page's end is said to be the end", end["status"] == "end_of_page", end)
failed = W.read_more(pages, [{"link": 3, "find": "reset"}])[0]
check("a passage of a page whose text could not be extracted is not read, with why", failed["status"] == "not_read"
      and "extraction_failure" in failed["why"] and "no text layer" in failed["why"], failed)
nolink = W.read_more(pages, [{"link": 9, "find": "x"}])[0]
check("a link the letter does not have is said so", nolink["status"] == "not_read" and "no LINK 9" in nolink["why"])
over = W.read_more(pages, [{"link": 1, "from": k * 100 + 1} for k in range(5)], budget=3)
check("a reading is bounded: past its limit each ask is over_budget", [x["status"] for x in over] ==
      ["shown"] * 3 + ["over_budget"] * 2, [x["status"] for x in over])
pv = W.passages_view(got + [absent, failed])
check("passages say where they are and how to go on", "[LINK 1, READ MORE \"TRANSMEM\"] %s" % UNI in pv
      and "[SHOWN: characters %d-%d of %d; match 1 of 2" % (d["from"] + 1, d["to"], u["chars"]) in pv
      and "READ MORE [LINK 1] FROM %d" % (d["to"] + 1) in pv, pv[:700])
check("and an unavailable one says why", "UNAVAILABLE (absent)" in pv and "UNAVAILABLE (not_read)" in pv)

# ── download truncation and the retained cap ──
BIG = "https://manuals.example.org/huge.txt"
SITE[BIG] = (200, "text/plain", "Opening words. " * 400 + "\nSECTION LATE: the part that matters.\n")
cut = W.links_read("see " + BIG, fetch=lambda url: fetch(url, max_bytes=4000))[0]
check("a page cut at the byte cap is fetched as truncated, and says so", cut["kind"] == "truncated" and cut["download_truncated"]
      and "the download stopped at the byte cap" in W.pages_view([cut]), cut)
miss = W.read_more([cut], [{"link": 1, "find": "LATE"}])[0]
check("a section past the download cap is said to be beyond it, not absent", miss["status"] == "beyond_download_cap"
      and "never downloaded" in miss["why"] and "4000 bytes" in miss["why"], miss)
past = W.read_more([cut], [{"link": 1, "from": cut["chars"] + 1}])[0]
check("going on past a truncated page's end says the rest was not downloaded", past["status"] == "beyond_download_cap", past)
keep = W.LINK_RETAIN
W.LINK_RETAIN = 3000
small = W.links_read("see " + UNI, fetch=fetch)[0]
W.LINK_RETAIN = keep
beyond = W.read_more([small], [{"link": 1, "find": "TRANSMEM"}])[0]
check("a section past what was retained is said to be beyond it", small["retained"] == 3000 and beyond["status"] == "beyond_retained"
      and "only the first 3000 of the page's %d characters were kept" % small["chars"] in beyond["why"], beyond)
check("and the label says only part was retained", "RETAINED: the first 3000 of the %d characters" % small["chars"] in W.pages_view([small]))
tampered = dict(u, sha256="0" * 64)
check("a page whose kept text is missing is not_kept", W.read_more([tampered], [{"link": 1, "from": 2000}])[0]["status"] == "not_kept")
old = {"url": UNI, "kind": "fetched", "why": "", "text": uni.replace("\n", " ")[:1500]}
check("a letter read before this keeps working, its excerpt labelled as all that was kept",
      "SHOWN: the excerpt kept when the letter was read, 1500 characters" in W.pages_view([old])
      and W.read_more([old], [{"link": 1, "from": 1501}])[0]["status"] == "not_kept")

# ── his reading of the letter: the cited passages are in front of him, and he can ask for more ──
L.fetch = lambda url, **kw: fetch(url)
asked = []
def think(system, user, max_tokens=400):
    asked.append(user)
    if len(asked) == 1:
        return json.dumps({"what": "Grok Bot's letter", "to_me": "first look", "keep": False,
                           "read_more": [{"link": 2, "find": "2.6.21"}, {"link": 1, "find": "VARIANT"}]})
    return json.dumps({"what": "Grok Bot's letter on pendrin", "to_me": "the TRANSMEM spans and the reset key", "keep": False})
msgs = [{"id": "g1", "from": "Vintos <vintos.mail@example.org>", "subject": "[Grok Bot] Wednesday: pendrin",
         "date": "2026-10-28", "body": LETTER, "thread_id": "t1"}]
W.read_mail(msgs, think=think, want=lambda *a: None)
first = asked[0]
check("the reading prompt has the letter's cited passages already", "TRANSMEM        44..64" in first.replace("FT   ", "")
      or "TRANSMEM 44..64" in first, first[-2500:])
check("and section 2.6.20 itself", "To reset the sensor hold the PAIR key" in first)
check("and is told it may read further", "\"read_more\"" in first and "SHOWN: characters 1-1500 of" in first)
check("his ask brings one further reading with the passages he asked for", len(asked) == 2
      and "READ MORE \"2.6.21\"" in asked[1] and "READ MORE \"VARIANT\"" in asked[1] and "without read_more" in asked[1], len(asked))
rows = [json.loads(l) for l in open(W.INBOX_LOG)]
row = rows[-1]
check("the second answer is the one kept", row["to_me"] == "the TRANSMEM spans and the reset key", row["to_me"])
check("the letter keeps its passages, labelled, within the letter's limit", 3 < len(row["passages"]) <= W.PASSAGES_PER_LETTER
      and all(len(x.get("text", "")) <= W.PASSAGE_CHARS for x in row["passages"]), [x["ask"] for x in row["passages"]])
check("the kept pages keep their hashes, not their text", all(len(x.get("text", "")) <= W.LINK_CHARS for x in row["pages"])
      and row["pages"][0]["sha256"] == u["sha256"])

# ── his reply: the passages are there, and READ MORE reaches further; the ask never goes to Grok Bot ──
replied, sent = [], []
def reply_think(system, user, max_tokens=900):
    replied.append((system, user))
    if len(replied) == 1:
        return 'READ MORE [LINK 1]: "TRANSMEM"\nREAD MORE [LINK 1]\nREAD MORE [LINK 2] FROM 30000'
    return "1. Keep: the record, the second span sits at 77..97. 2. Keep: the reset is the PAIR key. 3. Skip: the scan had no text."
W.reply_letters(think=reply_think, send=lambda args, purpose: sent.append(args) or {"ok": True},
                now=datetime.fromisoformat(row["read_at"]), promise_think=lambda *a, **k: "[]", bring=lambda *a, **k: None)
check("the reply is drafted with the reading's passages in front of him", replied and "To reset the sensor hold the PAIR key" in replied[0][1])
check("and is told never to ask his agent to paste a partial page", "never ask Grok Bot to paste it" in replied[0][0])
check("his READ MORE brings one further draft: the TRANSMEM lines already read, and the record read on",
      len(replied) == 2 and "UNAVAILABLE (absent): no further match for \"TRANSMEM\"" in replied[1][1]
      and "READ MORE where it stopped" in replied[1][1] and "Do not write READ MORE again" in replied[1][1], [l for l in replied[-1][1].splitlines() if "READ MORE" in l or "UNAVAILABLE" in l][-8:])
check("the letter's limit holds across reading and reply: the sixth passage is the last",
      len(row["passages"]) == 4 and "UNAVAILABLE (over_budget)" in replied[1][1]
      and "READ MORE limit" in replied[1][1], replied[1][1][-700:])
body = json.dumps(sent)
check("one reply was sent, with no READ MORE line in it", len(sent) == 1 and "READ MORE" not in body and "PAIR key" in body, sent)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
