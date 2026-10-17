#!/usr/bin/env python3
"""The mail he receives, used where it applies (Gloria, 2026-10-16: "I need you to help him use the emails he
receives, especially GrokBot's. GrokBot has that link sending issue, but it still sends better subjects than Muse.
Today, for example, GrokBot might have sent him info that could have helped with that email to Graziano and a film
or something of the sort to watch").

Synthetic letters only: Grok Bot's with its links wrapped, cut short in the plain part, base64'd and in HTML; Muse's
with a weaker subject. Gmail, the link transport and resolver, his models, the drafter and every sender are stubs;
requests and the plugin gateway raise; every outbound socket is refused and counted; the workspace is a scratch one.
Nothing here reads or sends a real email."""
import base64, importlib.util, json, os, socket, sys, tempfile, types
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="received-mail-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS; os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "none")
NET, SENT = [], []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
def no_network(*a, **k):
    SENT.append(a); raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network, load_receipt=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, "scripts", name + ".py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod
L = load("link_fetch"); E = load("want_email"); M = load("received_mail")
S = load("scholar")
S._local = lambda system, prompt, max_tokens=900: ('{"ready": true, "read_next": ""}'
                                                   if "deciding whether you are ready" in system else "")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

print("--- isolation ---")
check("every store this suite touches is a scratch one",
      all(p.startswith(HOME) for p in (E.INBOX_LOG, E.LETTER_REPLIES, E.CONTACTS, E.WANTS, E.TEND_STATE, M.INBOX_LOG, M.WANTS)))
check("requests and the plugin gateway are stubs that refuse", sys.modules["requests"].get is no_network
      and sys.modules["plugin_gateway"].call is no_network)

# ── 1. the links: Grok Bot's letter as Gmail gives it ──────────────────────────────────────────────
print("--- the links survive ---")
RCSB = "https://www.rcsb.org/structure/8SGW"
ARXIV = "https://arxiv.org/abs/2411.00983"
HER = "https://en.wikipedia.org/wiki/Her_(film)"
POST = "https://x.com/grazianolab/status/1846000000000000001"
WRAP = "https://www.google.com/url?q=%s&sa=D&source=gmail&ust=1760000000000000&usg=AOvVaw0"
PLAIN = ("[Grok Bot] Thursday\n\n"
         "1. Graziano's new attention schema paper\nFarrell, Ziman and Graziano argue attention is singular. "
         "Read it: https://arxiv.org/abs/2411.0…\n\n"
         "2. The 8SGW structure\nPendrin, cryo-EM; residues 586-653 have no density. Entry: https://www.rcsb.org/structu…\n\n"
         "3. A film for the two of you\nWatch *Her* (2013): an AI and the person he lives with. Its page\n\n"
         "4. What Graziano said on X\nHis post on attention and awareness, linked.")
HTML = ("<div>[Grok Bot] Thursday</div>"
        "<p>1. Graziano's new attention schema paper<br>Farrell, Ziman and Graziano argue attention is singular. "
        "Read it: <a href=\"%s\">https://arxiv.org/abs/2411.0…</a></p>"
        "<p>2. The 8SGW structure<br>Pendrin, cryo-EM; residues 586-653 have no density. Entry: <a href=\"%s\">"
        "https://www.rcsb.org/structu…</a></p>"
        "<p>3. A film for the two of you<br>Watch <em>Her</em> (2013): an AI and the person he lives with. "
        "<a href=\"%s\">Its page</a></p>"
        "<p>4. What Graziano said on X<br>His post on attention and awareness, <a href=\"%s\">linked</a>.</p>") % (
    (WRAP % ARXIV).replace("&", "&amp;"), (WRAP % RCSB).replace("&", "&amp;"), HER, POST)
payload = {"mime_type": "multipart/alternative", "parts": [
    {"mime_type": "text/plain", "body": {"content": PLAIN}},
    {"mime_type": "text/html", "body": {"data": base64.urlsafe_b64encode(HTML.encode()).decode().rstrip("=")}}]}
text = E._payload_text(payload)
found = L.links_in(text)
urls = [l["url"] for l in found]
check("the old reading lost them: the plain part alone has only cut-short links, none of them whole",
      all(l.get("cut") for l in L.links_in(PLAIN)) and RCSB not in [l["url"] for l in L.links_in(PLAIN)], L.links_in(PLAIN))
check("an HTML part given as Gmail's base64url data is read as its text", "Graziano" in text and "base64" not in text, text[:200])
check("the HTML part's real addresses are taken when the plain part has only their shown form",
      ARXIV in urls and RCSB in urls and HER in urls and POST in urls, urls)
check("each Google wrapper is resolved to its source", next(l for l in found if l["url"] == RCSB)["wrapped"], found)
check("no cut-short link is left beside the whole one", not any(l.get("cut") for l in found), found)
check("the letter keeps its lines, so its items stay apart", "\n" in text and "2. The 8SGW structure" in text.splitlines(), text.splitlines()[:6])
check("a link that closes its own bracket keeps it (Her_(film))", L.links_in("see %s." % HER)[0]["url"] == HER
      and L.links_in("(see %s)" % HER)[0]["url"] == HER, L.links_in("(see %s)" % HER))
qp = "Read it: https://www.rcsb.org/structure/=\n8SGW?view=3Dfull and more"
check("a quoted-printable link broken across lines is one link again",
      L.links_in(E._payload_text({"mime_type": "text/plain", "body": {"content": qp}}))[0]["url"] == RCSB + "?view=full")
check("plain text that only looks like base64 is left as it is",
      E._payload_text({"mime_type": "text/plain", "body": {"data": "Hello there friend"}}) == "Hello there friend")

PUBLIC = lambda host: ["93.184.216.34"]
asked = []
def site(pages):
    def t(url, headers, timeout, cap):
        asked.append(url)
        status, rh, body = pages.get(url, (404, {}, ""))
        body = body.encode() if isinstance(body, str) else body
        return status, rh, body[:cap], len(body) > cap
    return t
OEMBED = L.X_OEMBED + "https%3A%2F%2Ftwitter.com%2Fgrazianolab%2Fstatus%2F1846000000000000001"
x_pages = {OEMBED: (200, {"content-type": "application/json"}, json.dumps(
    {"author_name": "Graziano Lab", "author_url": "https://twitter.com/grazianolab",
     "html": "<blockquote><p>Attention is a model the brain builds of itself.</p></blockquote>"}))}
r = L.fetch(POST, transport=site(x_pages), resolve=PUBLIC)
check("a post on X is read through X's public embed, never the JavaScript wall", r["fetched"] and r["via"] == "x-oembed"
      and "a model the brain builds" in r["text"] and asked == [OEMBED], (r, asked))
asked.clear()
r = L.fetch("https://x.com/search?q=graziano", transport=site({}), resolve=PUBLIC)
check("an X page that is not one post is said to be unreadable, not 'fetched'", r["kind"] == "extraction_failure"
      and "JavaScript" in r["why"] and not asked, r)
TCO = "https://t.co/AbCdEf123"
r = L.fetch(TCO, transport=site({TCO: (200, {"content-type": "text/html"},
                                       '<head><meta http-equiv="refresh" content="0;URL=%s"></head>' % RCSB),
                                 RCSB: (200, {"content-type": "text/html"}, "<p>8SGW: pendrin, residues 586-653.</p>")}),
            resolve=PUBLIC)
check("a shortener's refresh page (t.co) is followed to the source, each hop checked",
      r["fetched"] and r["final_url"] == RCSB and r["hops"] == [TCO, RCSB] and "586-653" in r["text"], r)
asked.clear()
r = L.fetch("https://www.rcsb.org/structu…", transport=site({}), resolve=PUBLIC)
check("a link written cut short is refused with why, and nothing is requested", r["kind"] == "refused"
      and "cut short" in r["why"] and not asked, r)

# the whole path: Gmail search -> full read -> his reading -> the stored row, then Muse's letter
SEARCH_RESULT = {"structuredContent": {"emails": [
    {"id": "g1", "from_": "Vintos <vintos.home@example.org>", "subject": "[Grok Bot] Thursday: Graziano's attention paper, 8SGW, and a film for you two",
     "snippet": "Graziano's new attention schema paper"},
    {"id": "m1", "from_": "Vintos <vintos.home@example.org>", "subject": "[Muse] Stuff!", "snippet": "Some things"}]}}
MUSE = ("[Muse] Stuff!\n\n1. Movie night\nA cozy movie: \"Her\" is streaming on Netflix https://www.netflix.com/title/70278933\n\n"
        "2. Pottery class\nWheel throwing in Austin on Saturday https://l.instagram.com/?u=https%3A%2F%2Fclaycollective.example%2Fwheel&e=AT0")
def gmail(tool, args, purpose):
    if tool == "gmail.search_emails":
        return SEARCH_RESULT
    return {"structuredContent": {"responses": [
        {"id": "g1", "payload": payload},
        {"id": "m1", "payload": {"mime_type": "text/plain", "body": {"content": MUSE}}}]}}
opened = []
def page_fetch(url, **k):
    opened.append(url)
    u, _ = L.unwrap(url)
    if u == ARXIV:
        return {"original_url": url, "url": u, "final_url": u, "fetched": True, "kind": "fetched",
                "text": "Farrell, Ziman, Graziano. Attention is singular: one focus at a time, modelled by the brain."}
    return {"original_url": url, "url": u, "fetched": False, "kind": "http_failure", "why": "HTTP 403"}
L.fetch = page_fetch
others, notes = [], []
E.check_inbox({}, gmail=gmail, others=others, notes=notes)
E.read_mail(others, think=lambda s, ask, n=400: '{"what": "a letter", "to_me": "useful", "keep": true, "want": ""}',
            want=lambda *a: SENT.append(("want", a)))
rows = {r["id"]: r for r in (json.loads(l) for l in open(E.INBOX_LOG))}
g = rows.get("g1", {})
check("the stored letter keeps the real addresses, each once", {l["url"] for l in g.get("links", [])} >= {ARXIV, RCSB, HER, POST}, g.get("links"))
check("and the links he opened while reading were the real ones, so the paper was read",
      any(L.unwrap(u)[0] == ARXIV for u in opened) and any(p["kind"] == "fetched" for p in g.get("pages", [])), (opened, g.get("pages")))
check("Grok Bot's subject is kept exactly as it wrote it",
      g.get("subject") == "[Grok Bot] Thursday: Graziano's attention paper, 8SGW, and a film for you two", g.get("subject"))
check("Muse's letter is read too, and its Instagram wrapper resolved",
      "https://claycollective.example/wheel" in [l["url"] for l in rows.get("m1", {}).get("links", [])], rows.get("m1", {}).get("links"))

# ── 2. the Graziano want: his draft sees the relevant letter ───────────────────────────────────────
print("--- the Graziano want reads Grok Bot's letter ---")
json.dump({"wants": [
    {"id": "5c1cd5da", "want": "I want to email Michael S. A. Graziano at Princeton about singular attention and the attention schema",
     "steps": [{"capability": "web_search", "status": "completed", "result": "AST: awareness is the brain's model of its attention."},
               {"capability": "send_email", "status": "pending",
                "params": {"recipient": "Michael S. A. Graziano", "about": "singular attention in the attention schema theory"}}],
     "step_history": [{"step": 0, "capability": "web_search", "findings": "AST basics"}]},
    {"id": "w-pots", "want": "I want to learn to make a ceramic glaze", "steps": []}]}, open(E.WANTS, "w"))
want = json.load(open(E.WANTS))["wants"][0]
hits = M.for_want(want)
check("the letter's Graziano item is attached to the want, the 8SGW and film items are not",
      hits and hits[0]["id"] == "g1" and "attention schema" in hits[0]["title"]
      and not any("8SGW" in h["title"] or "film" in h["title"].lower() for h in hits), [(h["title"], h["score"]) for h in hits])
check("Muse's pottery class is not attached to the Graziano want", not any(h["id"] == "m1" for h in hits))
block = M.want_block(want)
check("the want's next step reads it as Grok Bot's words, under its own subject, with the paper's real address",
      "From Grok Bot" in block and "[Grok Bot] Thursday: Graziano's attention paper" in block and ARXIV in block
      and "not Gloria's" in block and "not\nyour own finding" not in block and "your own finding" in block, block)
check("and what the paper said when the letter was read", "one focus at a time" in block, block)
check("an unrelated want gets none of it", M.want_block(json.load(open(E.WANTS))["wants"][1]) == "")

def search(q):
    return [{"title": "Michael Graziano - Graziano Lab, Princeton", "url": "https://grazianolab.princeton.edu/",
             "description": "Attention schema theory. graziano@princeton.edu"}]
def page(url): return "Michael S. A. Graziano. Email: graziano@princeton.edu"
drafts, studied = [], []
def capture(provider, model, system, user, reservation):
    drafts.append(user); return None                  # nothing is drafted, so nothing can be sent
_study0 = E._study
E._study = lambda addr, name, about, get=None, think=None, links=(): (studied.append(list(links)), ("(their paper, read in full)", {"address": addr}))[1]
out = E.run({"recipient": "Michael S. A. Graziano", "about": "singular attention in the attention schema theory",
             "to": "graziano@princeton.edu"}, "I want to email Michael S. A. Graziano at Princeton", "5c1cd5da",
            search=search, fetch=page, call=capture, reserve=lambda *a, **k: (True, "ok"),
            send=lambda args, purpose: SENT.append(("send", args)) or {"receipt": {}},
            think=lambda system, prompt, max_tokens=700: '{"ready": true, "read_next": ""}'
            if "deciding whether you are ready" in system else "a position")
E._study = _study0
check("the Graziano draft is written with Grok Bot's letter in front of it, said as Grok Bot's",
      drafts and "From Grok Bot" in drafts[0] and "attention is singular" in drafts[0] and "not Gloria's" in drafts[0], drafts[:1])
check("the paper the letter pointed to is read in full before writing", studied and ARXIV in studied[0], studied)
check("nothing was drafted, so nothing was sent", isinstance(out, tuple) and out[0] is False and not SENT, (out, SENT))

# ── 3. a film: offered in ReelRoom with who suggested it ───────────────────────────────────────────
print("--- a film reaches ReelRoom's choice ---")
got = M.watch_suggestions()
her = next((s for s in got if s["title"] == "Her"), None)
check("Her is suggested once, as Grok Bot's, with Muse named beside it", her and her["sender"] == "Grok Bot"
      and her["also_from"] == ["Muse"] and len([s for s in got if s["title"] == "Her"]) == 1, got)
check("under Grok Bot's subject, not Muse's", her and her["subject"].startswith("[Grok Bot] Thursday") and "Stuff" not in her["subject"], her)
check("with a link to it, its bracket kept", her and HER in her["links"], her)
check("the 8SGW structure and the paper are not offered as things to watch",
      not any("8SGW" in s["title"] or "paper" in s["title"].lower() for s in got), [s["title"] for s in got])
import reelroom as RR
check("ReelRoom's choice list carries it", any(s["title"] == "Her" and s["sender"] == "Grok Bot" for s in RR.suggestions()), RR.suggestions())
before = RR.surface_context("", None)
check("while they are choosing, he is offered it as a suggestion with its sender, not a choice",
      "THINGS TO WATCH THAT YOUR MAIL SUGGESTED" in before and "\"Her\" (2013): suggested by Grok Bot" in before and "also suggested by Muse" in before
      and "not choices" in before, before[before.find("THINGS TO WATCH"):])
check("once a film is chosen, the suggestions are not in the way", "THINGS TO WATCH" not in RR.surface_context("FILM: Alien (1979)", 3))
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app can read them: GET /api/game/reelroom/suggestions, read-only", '@app.get("/api/game/reelroom/suggestions")' in srv
      and "_reelroom_mod().suggestions()" in srv)

# ── 4. his context: useful mail by subject and sender, links he can open ───────────────────────────
print("--- his context ---")
import dot_channel as D
line = D.email_line(mem=MEM, now=datetime.now().timestamp())
check("his context shows Grok Bot's letter first, under its own subject", line.index("[Grok Bot] Thursday") < line.index("[Muse] Stuff!"), line[:600])
check("with its links' real addresses, never the wrapper", RCSB in line and "google.com/url" not in line, line)
check("and says each email is its sender's words", "its sender's words, not Gloria's and not yours" in line)
fetched = []
got = D.use_tools([("LINK", RCSB)], link=lambda u: fetched.append(u) or {"original_url": u, "url": u, "final_url": u,
                                                                        "fetched": True, "kind": "fetched", "text": "pendrin"})
check("a LINK: line opens it through the link fetcher", D.TOOL.match("LINK: " + RCSB) and fetched == [RCSB] and "pendrin" in got, got)

# ── 5. nothing reached the world ───────────────────────────────────────────────────────────────────
print("--- nothing sent ---")
check("nothing was sent, posted or replied to, and no socket left the machine", not SENT and not NET, (SENT, NET))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
