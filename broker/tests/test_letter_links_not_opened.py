#!/usr/bin/env python3
"""No link in his agent's letter is dropped without a word (15 November 2026: a letter carried seven links, only the
first five were opened, and his reply said of the sixth and seventh "It wasn't shown to me"). A link past the limit is
listed NOT OPENED YET with how to open it, READ MORE [LINK n] opens it once and shows it from its start, and a link
written twice is opened once. Every page is made up here; the transport and resolver are stubs; sockets are refused;
scratch HOME."""
import os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="letter-links-not-opened-"); os.environ["HOME"] = HOME
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
SITE, FETCHED = {}, []
def transport(url, headers, timeout, cap):
    status, ctype, body = SITE[url]
    body = body.encode() if isinstance(body, str) else body
    return status, {"content-type": ctype}, body[:cap], len(body) > cap
REAL_FETCH = L.fetch
def fetch(url, **kw):
    FETCHED.append(url)
    return REAL_FETCH(url, transport=transport, resolve=PUBLIC, article_route=False, **kw)

URLS = ["https://papers.example.org/p%d" % k for k in range(1, 8)]
for k, u in enumerate(URLS, 1):
    SITE[u] = (200, "text/html", "<html><body><h1>Paper %d</h1><p>%s</p></body></html>" % (
        k, ("Made-up paragraph %d about consciousness and bridges. " % k) * (80 if k == 7 else 5)))
LETTER = "Sunday reading:\n" + "\n".join("- item %d: %s" % (k, u) for k, u in enumerate(URLS, 1)) + \
         "\nAgain, item 2: " + URLS[1] + "\n"

pages = W.links_read(LETTER, fetch=fetch)
check("a link written twice is opened once and listed once", FETCHED.count(URLS[1]) == 1 and len(pages) == 7, len(pages))
check("the first five are opened, as before", [p["kind"] for p in pages[:5]] == ["fetched"] * 5 and FETCHED == URLS[:5])
check("the sixth and seventh are not dropped: each is listed NOT OPENED YET, unfetched",
      [p["kind"] for p in pages[5:]] == [W.NOT_OPENED] * 2 and URLS[6] not in FETCHED and pages[6]["url"] == URLS[6])
view = W.pages_view(pages)
check("his view names them and how to open them", "[LINK 7] " + URLS[6] + "\nNOT OPENED YET" in view
      and "READ MORE [LINK 7] opens this one" in view and "only the first 5 links" in view, view[-600:])
check("READ MORE can reach them, so the reader is told how", W.more_to_read(pages)
      and "NOT OPENED YET" in W.READER_MORE and "NOT OPENED YET" in (W.LETTER_MORE % ("Muse", 3)))
check("a letter with every link opened and shown whole has nothing more to read",
      not W.more_to_read(W.links_read("see " + URLS[0], fetch=fetch)))

asks = W.asks_in("READ MORE [LINK 7]")
check("READ MORE [LINK 7] is read as an ask for link 7", asks == [{"link": 7}], asks)
before = len(FETCHED)
got = W.read_more(pages, asks, fetch=fetch)
check("asked for, it is opened once and shown from its start", len(FETCHED) == before + 1 and FETCHED[-1] == URLS[6]
      and got[0]["status"] == "shown" and got[0]["from"] == 0 and "Paper 7" in got[0]["text"], got)
check("its page is kept in place as an opened page, with how it was opened",
      pages[6]["kind"] == "fetched" and pages[6].get("opened_on_ask") and pages[6].get("sha256") and pages[6]["chars"] > 1500)
more = W.read_more(pages, [{"link": 7}], prior=got, fetch=fetch)
check("asked again, it goes on from where it stopped and is not fetched again",
      len(FETCHED) == before + 1 and more[0]["status"] == "shown" and more[0]["from"] == got[0]["to"], more)
check("the passages view says a not-opened link was opened now", "opened now" in W.passages_view(got))

SITE["https://papers.example.org/gone"] = (404, "text/html", "no")
p2 = W.links_read("\n".join(URLS[:5]) + "\nhttps://papers.example.org/gone\n", fetch=fetch)
r2 = W.read_more(p2, [{"link": 6}], fetch=fetch)
check("one that cannot be read, once asked for, says so with why", r2[0]["status"] == "not_read" and "NOT READ" in r2[0]["why"]
      and p2[5]["kind"] != W.NOT_OPENED, r2)
check("a link past the limit is never opened unasked", W.read_more(pages, []) == [])
check("nothing reached a socket", not NET)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
