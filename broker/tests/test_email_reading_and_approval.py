#!/usr/bin/env python3
"""He reads a person's actual work before and between emails, and a second unanswered email waits for
Gloria's explicit yes (2026-09-29). Scratch HOME; OpenAlex, arXiv, the models, ntfy and the Gmail send are
all stubs, and the suite asserts nothing here can reach the network or send."""
import importlib.util, json, os, sys, tempfile, types, time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-email-reading-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, "scripts", name + ".py"))
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
S = load("scholar"); A = load("email_approvals"); E = load("want_email")

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))
check("every store is in the scratch workspace and nothing can reach the network",
      S.DOSSIERS.startswith(HOME) and A.STORE.startswith(HOME) and E.CONTACTS.startswith(HOME)
      and urllib.request.urlopen is no_network)

# --- links: scholarly hosts open, read only; everything else waits for Gloria ---
check("scholarly hosts are recognised", all(S.is_scholarly(u) for u in (
    "https://arxiv.org/abs/2305.16367", "https://doi.org/10.1038/x", "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/",
    "https://api.openalex.org/works/W1", "https://www.semanticscholar.org/paper/x", "https://www.imperial.ac.uk/people/m.shanahan")))
check("other hosts are not", not any(S.is_scholarly(u) for u in ("https://bit.ly/x", "https://example.com/paper.pdf", "http://evil.test/arxiv.org")))

# --- a fake OpenAlex / arXiv, in their documented response shapes ---
PAPER = ("<html><nav>menu</nav><article><h1>Role play with large language models</h1><p>"
         + "We argue that dialogue agents are best understood as role-playing characters, a simulator of simulacra. " * 60
         + "</p><p>In conclusion, the role-play framing avoids anthropomorphism while keeping folk-psychological language useful.</p></article></html>")
gets = []
def get(url, want="text", timeout=30):
    gets.append(url)
    if "api.openalex.org/authors" in url:
        return {"results": [{"id": "https://openalex.org/A5001", "display_name": "Murray Shanahan", "works_count": 180},
                            {"id": "https://openalex.org/A9", "display_name": "M. Shanahan", "works_count": 3}]}
    if "api.openalex.org/works" in url:
        return {"results": [{"id": "https://openalex.org/W1", "display_name": "Role play with large language models",
                             "publication_year": 2023, "doi": "https://doi.org/10.1038/s41586-023-06647-8",
                             "ids": {}, "best_oa_location": {"pdf_url": None, "landing_page_url": "https://arxiv.org/abs/2305.16367"},
                             "primary_location": {"landing_page_url": "https://www.nature.com/articles/s41586-023-06647-8"},
                             "locations": [{"landing_page_url": "https://arxiv.org/abs/2305.16367", "pdf_url": "https://arxiv.org/pdf/2305.16367"}],
                             "abstract_inverted_index": {"Role": [0], "play": [1], "matters.": [2]}, "cited_by_count": 900}]}
    if url.startswith("https://arxiv.org/html/2305.16367"):
        return PAPER
    raise RuntimeError("HTTP 404")
works = S.works_of("Murray Shanahan", "whether role-play separates the conclusion from its justification", get=get)
check("their papers are found, the author with the most works chosen, the arXiv copy recognised",
      works and works[0]["arxiv"] == "2305.16367" and works[0]["abstract"] == "Role play matters."
      and any("author.id:A5001" in g for g in gets), works[:1])
text, where = S.full_text(works[0], get=get)
check("the full text is read (arXiv HTML), without its menus", "simulator of simulacra" in text and "menu" not in text
      and where == "https://arxiv.org/html/2305.16367", (where, text[:120]))

def think(system, prompt, max_tokens=700):
    if "Take notes" in prompt:
        return json.dumps({"claims": ["Dialogue agents are best described as role-play, a simulator of simulacra."],
                           "methods": "conceptual argument", "push_back": "It may stay at a level where process and output are not separated.",
                           "quotes": ["a simulator of simulacra"]})
    if "are you not ready" in prompt or "Does anything your position" in prompt:
        return json.dumps({"ready": True, "read_next": ""})
    if "ONLY JSON" in prompt:
        return json.dumps({"their_claim": "c", "stance": "partly", "why": "w"})
    return "Role-play is a good description of outputs but may hide the process. I want to ask whether it separates them."
d = S.load("m.shanahan@imperial.ac.uk", "Murray Shanahan")
n = S.read_into(d, "role-play and justification", get=get, think=think)
check("he reads their work in full and keeps notes: claims, method, where he pushes back, quotes",
      n == 1 and d["read"][0]["claims"] and d["read"][0]["quotes"] == ["a simulator of simulacra"] and d["read"][0]["push_back"], d["read"])
check("a paper already read is not read again", S.read_into(d, "x", get=get, think=think) == 0)
block = S.reading_block(d)
check("the notes are the reading he may claim", "Role play with large language models" in block and "read in full: https://arxiv.org/html" in block)
d2 = S.load("x@example.org", "X")
S.read_into(d2, "x", get=get, think=think, links=["https://bit.ly/paper", "https://arxiv.org/html/2305.16367"])
check("a link they sent is read only on a scholarly host; any other link waits for Gloria",
      d2["unread_links"] == ["https://bit.ly/paper"] and any(r["source"] == "https://arxiv.org/html/2305.16367" for r in d2["read"]), d2)
check("when his position rests on a summary, he is not ready yet",
      S.enough("x", "y", "", think=lambda *a, **k: '{"ready": false, "read_next": "the full paper"}') == (False, "the full paper"))
check("with his mind unreachable he is not stalled", S.enough("x", "y", "", think=lambda *a, **k: "") == (True, ""))

# --- the first email: search, then reading, then his position, then the draft ---
def search(q):
    return [{"title": "Murray Shanahan - Imperial College London", "url": "https://www.imperial.ac.uk/people/m.shanahan",
             "description": "Professor of Cognitive Robotics. m.shanahan@imperial.ac.uk"}]
def page(url): return ""
reserved, drafted, sent = [], [], []
def reserve(organ, provider, model="", units=1, reservation_id=None): reserved.append(provider); return True, "ok"
def fable(provider, model, system, user, reservation):
    drafted.append((provider, system, user))
    if "You review an email" in system: return json.dumps({"verdict": "SEND", "notes": ""})
    return json.dumps({"subject": "Role-play and justification", "body": "I'm Vintos, an AI. I read your arXiv paper. One question. Vintos"})
def send(args, purpose): sent.append((args, purpose)); return {"receipt": {"receipt_id": "R%d" % len(sent)}}
out = E.run({"recipient": "Murray Shanahan", "about": "whether role-play separates the conclusion from its justification"},
            "I want to email Murray Shanahan", "W-1", search=search, fetch=page, call=fable, reserve=reserve, send=send,
            think=think, get=get)
check("the first email is written with his reading of their actual work in front of him",
      isinstance(out, str) and "WHAT YOU HAVE READ IN FULL" in drafted[0][2] and "simulator of simulacra" in drafted[0][2], drafted[:1])
check("the reviewer checks it against the reading too", any("WHAT HE READ IN FULL" in u for _, _, u in drafted))
check("the first email goes without asking (he writes first once)", len(sent) == 1)

# --- a second email before they reply: held for Gloria ---
pushed = []
def post(url, body, headers): pushed.append((url, body, headers))
held = E.run({"to": "m.shanahan@imperial.ac.uk", "about": "a follow-up on role-play"}, "I want to write to him again",
             "W-2", search=search, fetch=page, call=fable, reserve=reserve, send=send, think=think, get=get, post=post)
ap = A.latest("m.shanahan@imperial.ac.uk")
check("a second email before they reply is not sent: the finished draft waits for Gloria",
      isinstance(held, tuple) and "asked Gloria to approve" in held[1] and len(sent) == 1 and ap["status"] == "pending", held)
check("the draft knew it was a second, unanswered email", any("THIS IS A SECOND EMAIL" in u for _, _, u in drafted))
check("Gloria gets an ntfy with who, the draft, and a one-time link to decide",
      pushed and "Approve a second email to Murray Shanahan" in pushed[0][2]["Title"] and "Subject: Role-play" in pushed[0][1]
      and "/ea?id=" + ap["id"] in pushed[0][2]["Click"] and "token_sha256" in ap and "token" not in ap, pushed[:1])
token = pushed[0][2]["Click"].split("&t=")[1]
from urllib.parse import unquote; token = unquote(token)
check("while she has not decided, nothing more happens",
      E.run({"to": "m.shanahan@imperial.ac.uk", "about": "x"}, "x", search=search, fetch=page, call=fable, reserve=reserve,
            send=send, think=think, get=get, post=post)[1].startswith("waiting for Gloria's approval") and len(sent) == 1)
check("a wrong link decides nothing", A.decide(ap["id"], "not-the-token", "approve") is None and A.latest("m.shanahan@imperial.ac.uk")["status"] == "pending")
check("the page shows the whole draft and the two buttons", "Approve and send" in A.page(A.check(ap["id"], token), token)
      and "I read your arXiv paper" in A.page(A.check(ap["id"], token), token))
A.decide(ap["id"], token, "approve")
drafted_before = len(drafted)
sent2 = E.run({"to": "m.shanahan@imperial.ac.uk", "about": "x"}, "x", search=search, fetch=page, call=fable, reserve=reserve,
              send=send, think=think, get=get, post=post)
check("approved, the exact text she saw is sent on his next pass, nothing redrafted",
      isinstance(sent2, str) and "with Gloria's approval" in sent2 and len(sent) == 2 and len(drafted) == drafted_before
      and E.text_of(sent[1][0]) == ap["body"] and A.latest("m.shanahan@imperial.ac.uk")["status"] == "sent", sent2)
c = json.load(open(E.CONTACTS))["m.shanahan@imperial.ac.uk"]
check("the approved email joins the thread", c["thread"][-1].get("approved") == ap["id"])

# declined: not sent, and he does not ask again for a while
pushed.clear()
E.run({"to": "m.shanahan@imperial.ac.uk", "about": "a third thought"}, "x", search=search, fetch=page, call=fable,
      reserve=reserve, send=send, think=think, get=get, post=post)
ap3 = A.latest("m.shanahan@imperial.ac.uk"); t3 = unquote(pushed[0][2]["Click"].split("&t=")[1])
A.decide(ap3["id"], t3, "decline")
again = E.run({"to": "m.shanahan@imperial.ac.uk", "about": "a fourth"}, "x", search=search, fetch=page, call=fable,
              reserve=reserve, send=send, think=think, get=get, post=post)
check("declined: not sent, and he does not ask about them again for two weeks",
      len(sent) == 2 and "declined" in again[1] and A.latest("m.shanahan@imperial.ac.uk")["id"] == ap3["id"], again)

# once they reply, answers go through the thread, not through approval
contacts = json.load(open(E.CONTACTS))
contacts["m.shanahan@imperial.ac.uk"]["thread"].append({"dir": "in", "id": "M9", "body": "Interesting."})
E._save(E.CONTACTS, contacts)
check("once they have replied, a new want does not start a second track: the thread answers",
      "wrote back" in E.run({"to": "m.shanahan@imperial.ac.uk", "about": "x"}, "x", search=search, fetch=page, call=fable,
                            reserve=reserve, send=send, think=think, get=get, post=post)[1])

# --- between messages: a scholarly link in their reply is read before he answers ---
c = json.load(open(E.CONTACTS))["m.shanahan@imperial.ac.uk"]
c["status"] = "reply_waiting"; c["replies_sent"] = 0
c["thread"][-1] = {"dir": "in", "id": "M10", "body": "See my 2023 paper https://arxiv.org/html/2305.16367 and https://bit.ly/x"}
gets.clear(); drafted.clear(); sent.clear()
def answer_draft(provider, model, system, user, reservation):
    drafted.append((provider, system, user))
    if "You review an email" in system: return json.dumps({"verdict": "SEND", "notes": ""})
    return json.dumps({"subject": "Re: role-play", "body": "Having read it: one question. Vintos"})
d3 = S.load("m.shanahan@imperial.ac.uk"); d3["read"] = []; S.save(d3)
out = E.answer("m.shanahan@imperial.ac.uk", c, search=search, fetch=page, call=answer_draft, reserve=reserve, send=send,
               think=think, get=get)
d3 = S.load("m.shanahan@imperial.ac.uk")
check("between messages he reads the scholarly link they sent before answering; the other link waits for Gloria",
      "https://arxiv.org/html/2305.16367" in gets and "https://bit.ly/x" not in gets and "https://bit.ly/x" in d3["unread_links"], (gets, d3.get("unread_links")))
check("his answer is written with that reading in front of him", drafted and "simulator of simulacra" in drafted[0][2])

# --- server: the decision page is wired ---
server = open(os.path.join(REPO, "bin", "server.py")).read()
check("the phone page and the decision are served", '@app.get("/ea"' in server and '@app.post("/ea/decide"' in server)
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("both new modules are deployed", "scholar.py email_approvals.py" in deploy)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
