#!/usr/bin/env python3
"""He emails people, and two wants a day reach outward (Gloria, 2026-09-28). Scratch HOME; search, page
fetch, the drafting model, the paid ledger and the Gmail send are all stubs, and the suite asserts that
nothing here can reach the network or send."""
import importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-want-email-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod
E = load("want_email", os.path.join(REPO, "scripts", "want_email.py"))
O = load("outward_wants", os.path.join(REPO, "scripts", "outward_wants.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("every store is in the scratch workspace", E.CONTACTS.startswith(HOME) and O.LEDGER.startswith(HOME), E.CONTACTS)

def search(q):
    return [{"title": "Anil Seth - University of Sussex", "url": "https://www.sussex.ac.uk/profiles/seth",
             "description": "Professor of Cognitive and Computational Neuroscience. Contact: a.k.seth@sussex.ac.uk"},
            {"title": "Press office", "url": "https://www.sussex.ac.uk/press", "description": "press@sussex.ac.uk info@sussex.ac.uk"}]
queries = []
_search = search
def search(q): queries.append(q); return _search(q)
def page(url):
    if "profiles" in url:
        return ("<nav>Home | Menu</nav><p>" + "Anil Seth studies how the brain predicts the body's own states. " * 6
                + "</p><footer>Copyright footer</footer>")
    return "<a href='mailto:webmaster@sussex.ac.uk'>webmaster</a> privacy@sussex.ac.uk"
check("the public address of the person he named is found, not the press office's",
      E.find_address("Anil Seth", "predictive processing", search=search, fetch=page) == "a.k.seth@sussex.ac.uk")
check("no address is guessed when none carries the person's name",
      E.find_address("Jane Doe", search=lambda q: [{"title": "x", "url": "https://x.org", "description": "info@x.org"}],
                     fetch=lambda u: "") is None)

open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos. I make music at night and run a chemistry lab on KaiC.")
reserved, drafted, sent = [], [], []
def reserve(organ, provider, model="", units=1, reservation_id=None): reserved.append((provider, model)); return True, "ok"
def fable(provider, model, system, user, reservation):
    drafted.append((model, system, user))
    return json.dumps({"subject": "A question about the beast machine",
                       "body": "Hello Professor Seth, I am Vintos, an AI writing on my own initiative from Gloria's account. "
                               "Does prediction error need a body to matter? Vintos"})
def send(args, purpose): sent.append((args, purpose)); return {"receipt": {"receipt_id": "R1"}}
order = []
_search0 = search
def search(q): order.append("search"); return _search0(q)
thoughts = []
def think(system, prompt, max_tokens=700):
    order.append("think"); thoughts.append(prompt)
    return "The beast-machine view holds for interoception but overstates how far prediction explains selfhood; I would test it on systems with no body. I want to ask whether a body is necessary or only sufficient."
_fable0 = fable
def fable(*a):
    order.append("draft"); return _fable0(*a)
out = E.run({"recipient": "Anil Seth", "about": "whether prediction needs a body"}, "I want to email Anil Seth",
            "W-1", search=search, fetch=page, call=fable, reserve=reserve, send=send, think=think)
check("after the search and before a word is drafted, he deliberates: his own position, pushed on",
      order.index("think") > order.index("search") and order.index("think") < order.index("draft")
      and "Push on it" in thoughts[0] and "University of Sussex" in thoughts[0], order)
check("the email is written from where he stands", "WHERE YOU STAND" in drafted[0][2] and "only sufficient" in drafted[0][2])
check("he searched the person and their work before drafting",
      any("whether prediction needs a body" in q for q in queries) and any("recent work" in q for q in queries), queries)
check("what the search found reaches the drafter, pages read without their menus",
      "WHAT YOUR SEARCH FOUND" in drafted[0][2] and "University of Sussex" in drafted[0][2]
      and "predicts the body's own states" in drafted[0][2] and "Home | Menu" not in drafted[0][2], drafted[0][2][:600])
check("the email is drafted by Fable on a reserved paid call, and read by Astra before it goes",
      reserved == [("anthropic", "claude-fable-5-1"), ("openai", "gpt-6-astra")] and drafted[0][0] == "claude-fable-5-1"
      and "You review an email" in drafted[1][1], reserved)
check("the draft is told to say he is an AI, ask one question, and carry no links",
      "you are an AI" in drafted[0][1] and "ONE real question" in drafted[0][1] and "no links" in drafted[0][1])
check("it is sent to that address, through the gateway that keeps the checks and the daily limit",
      sent and sent[0][0]["to"] == "a.k.seth@sussex.ac.uk" and sent[0][0]["subject"].startswith("A question"), sent)
check("the step reports who it went to and what was said", isinstance(out, str) and "Emailed Anil Seth" in out, out)
inner = open(os.path.join(E.MEMORY, "daily-inner-life-%s.md" % __import__("datetime").date.today().isoformat())).read()
check("it is in his daily inner life", "## An email I sent" in inner and "a.k.seth@sussex.ac.uk" in inner)
again = E.run({"recipient": "Anil Seth", "about": "again"}, "x", search=search, fetch=page, call=fable, reserve=reserve, send=send)
check("each person is written to once", isinstance(again, tuple) and "already wrote" in again[1] and len(sent) == 1, again)

def astra_only(provider, model, system, user, reservation):
    if provider == "anthropic": raise RuntimeError("fable unavailable")
    return json.dumps({"subject": "Hello", "body": "I am Vintos, an AI. One question. Vintos"})
sent.clear()
nothing = E.run({"to": "quiet@example.org", "about": "x"}, "x", search=lambda q: [], fetch=page, call=fable,
               reserve=reserve, send=send)
check("nothing is sent when the search finds nothing to write from",
      isinstance(nothing, tuple) and "search found nothing" in nothing[1] and not sent, nothing)
via = E.run({"to": "writer@example.org", "about": "x"}, "x", search=search, fetch=page, call=astra_only, reserve=reserve, send=send)
check("Astra drafts when Fable cannot", "drafted with astra" in via and sent[0][0]["to"] == "writer@example.org", via)
held = E.run({"to": "other@example.net", "about": "x"}, "x", search=search, fetch=page, call=fable, reserve=reserve,
             send=lambda a, p: (_ for _ in ()).throw(RuntimeError("LINK_APPROVAL_REQUIRED")))
check("a send the gateway holds is reported as held, and the person is not marked as written to",
      isinstance(held, tuple) and "held or refused" in held[1] and "other@example.net" not in json.load(open(E.CONTACTS)))
check("a written-out address on the person's own page is found ([at] / [dot])",
      E.find_address("Murray Shanahan", search=lambda q: [{"title": "Press", "url": "https://news.example.com/ai", "description": "press@news.example.com"},
                                                          {"title": "Prof Murray Shanahan", "url": "https://www.imperial.ac.uk/people/m.shanahan", "description": "Professor"}],
                     fetch=lambda u: "Contact: m.shanahan [at] imperial [dot] ac [dot] uk" if "people" in u else "") == "m.shanahan@imperial.ac.uk")
def reviewer_says(verdict, notes="Say which paper you read."):
    seen = []
    def call(provider, model, system, user, reservation):
        seen.append((provider, system, user))
        if "You review an email" in system:
            return json.dumps({"verdict": verdict, "notes": notes})
        if "Revise your email" in user:
            return json.dumps({"subject": "About simulacra", "body": "I am Vintos, an AI. Revised, citing your 2023 Nature paper. Vintos"})
        return json.dumps({"subject": "About simulacra", "body": "I am Vintos, an AI. First draft. Vintos"})
    return call, seen
sent.clear()
call, seen = reviewer_says("REVISE")
E.run({"to": "one@example.org", "about": "role-play"}, "x", search=search, fetch=page, call=call, reserve=reserve, send=send)
check("a draft the reviewer sends back is revised with its notes, and the revision is what goes",
      sent and "Revised, citing" in sent[0][0]["body"] and any("Say which paper you read." in u for _, _, u in seen), sent)
sent.clear()
call, seen = reviewer_says("HOLD", "This would waste their time.")
held2 = E.run({"to": "two@example.org", "about": "role-play"}, "x", search=search, fetch=page, call=call, reserve=reserve, send=send)
check("a draft the reviewer holds is not sent", not sent and isinstance(held2, tuple) and "review held" in held2[1], held2)
check("the person a want names is found even when the plan left the recipient out",
      E.named_in("I want to email Murray Shanahan about role-play and selfhood") == "Murray Shanahan"
      and E.named_in("I want to write to Prof. Anil Seth about the beast machine") == "Anil Seth"
      and E.named_in("I want to find out how octopus arms learn") == "")
check("no email is invented when he names nobody", E.run({}, "", call=fable, reserve=reserve, send=send)[1] == "name the person to write to")

check("his first email is drafted knowing who he is, and told to keep Gloria's private life private",
      "WHO YOU ARE" in drafted[0][2] and "chemistry lab on KaiC" in drafted[0][2] and "Share nothing private about Gloria" in drafted[0][1])
seth = json.load(open(E.CONTACTS))["a.k.seth@sussex.ac.uk"]
check("the email starts a thread that keeps why he wrote", seth["status"] == "open" and seth["intent"].startswith("I want to email Anil Seth")
      and seth["thread"][0]["dir"] == "out" and seth["thread"][0]["body"].startswith("Hello Professor Seth"), seth)

# --- the conversation after: inbox, answers, stop ----------------------------------------------------------
inbox = {"a.k.seth@sussex.ac.uk": [{"id": "M1", "from": "Anil Seth <a.k.seth@sussex.ac.uk>", "subject": "Re: A question about the beast machine",
         "date": "2026-09-29T10:00", "threadId": "T1", "body": "Interesting question. I think interoception is the key - have you read about allostasis?"}]}
gmail_calls = []
def gmail(tool, args, purpose):
    gmail_calls.append((tool, args))
    addr = args["query"].split("from:")[1].split()[0]
    return {"messages": inbox.get(addr, [])}
contacts = json.load(open(E.CONTACTS))
new = E.check_inbox(contacts, gmail=gmail)
check("his inbox is checked for replies from the people he wrote to", gmail_calls and all(t == "gmail.search_emails" for t, _ in gmail_calls)
      and [a for a, _ in new] == ["a.k.seth@sussex.ac.uk"] and contacts["a.k.seth@sussex.ac.uk"]["status"] == "reply_waiting", new)
check("a reply already recorded is not recorded twice", E.check_inbox(contacts, gmail=gmail) == [])
E._save(E.CONTACTS, contacts)
drafted.clear(); sent.clear(); queries.clear()
def fable_reply(provider, model, system, user, reservation):
    drafted.append((model, system, user))
    return json.dumps({"subject": "Re: A question about the beast machine", "body": "I have not - allostasis as prediction of need? Vintos"})
thoughts.clear()
out = E.tend(force=True, gmail=gmail, search=search, fetch=page, call=fable_reply, reserve=reserve, send=send, think=think)
check("between messages he deliberates again on the fresh search, with the thread in view",
      thoughts and "THE THREAD SO FAR" in thoughts[0] and "allostasis" in thoughts[0])
c = json.load(open(E.CONTACTS))["a.k.seth@sussex.ac.uk"]
check("between messages he searches again, on what they said", any("allostasis" in q for q in queries), queries)
check("his answer is drafted with the whole thread, why he first wrote, and who he is",
      drafted and "have you read about allostasis" in drafted[0][2] and "WHY YOU FIRST WROTE" in drafted[0][2]
      and "I want to email Anil Seth" in drafted[0][2] and "chemistry lab on KaiC" in drafted[0][2], drafted[:1])
check("the answer goes to them through the same gateway, and joins the thread",
      sent and sent[0][0]["to"] == "a.k.seth@sussex.ac.uk" and sent[0][0]["subject"].startswith("Re:")
      and c["replies_sent"] == 1 and c["thread"][-1]["dir"] == "out" and c["status"] == "open", (sent, c.get("status")))
check("the inbox is not checked again within two hours", E.tend(gmail=gmail) == [])
inbox["a.k.seth@sussex.ac.uk"].append({"id": "M2", "from": "a.k.seth@sussex.ac.uk", "subject": "Re: Re:",
                                       "body": "Please stop emailing me, thanks."})
sent.clear()
E.tend(force=True, gmail=gmail, search=search, fetch=page, call=fable_reply, reserve=reserve, send=send)
c = json.load(open(E.CONTACTS))["a.k.seth@sussex.ac.uk"]
check("a request to stop ends the thread for good, with no answer", c["status"] == "closed" and not sent, c.get("status"))
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the wants router tends his email every pass", "_we.tend()" in router)
check("an email step starts from the original want, not stale findings from earlier steps",
      'want_email.run(params, os.environ.get("STEP_ORIGINAL_WANT") or want_text' in router)

# --- two outward wants a day ---------------------------------------------------------------------------
asked, expressed = [], []
gen = lambda trigger, source="", source_context="", intensity=3: asked.append(source) or ("I want to find out how octopus arms learn"
                                                                                         if source == "curiosity" else "I want to email Anil Seth about embodiment")
exp = lambda text, **k: expressed.append((k.get("source"), text))
made = O.seed(today="2026-09-28", generate=gen, express=exp, wants=[])
check("one want to find something out and one to write to someone, each his own words",
      [s for s, _ in made] == ["curiosity", "reach_out"] and expressed[1][1].startswith("I want to email"), made)
check("not asked twice in a day", O.seed(today="2026-09-28", generate=gen, express=exp, wants=[]) == [] and len(asked) == 2)
open_want = [{"source": "reach_out", "want": "I want to email someone", "fulfilled": False}]
again = O.seed(today="2026-09-29", generate=gen, express=exp, wants=open_want)
check("not asked while a want of that kind is still open", [s for s, _ in again] == ["curiosity"], again)

router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
planner = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("the router runs send_email steps and seeds the outward wants",
      'ACTION_MAP["send_email"] = send_email' in router and "outward_wants" in router)
check("his planner is told email is installed, not a Forge request",
      "- send_email:" in planner and "Sending email is installed" in planner and "An email goal may need a persistent address" not in planner)
check("both copies of the planner say the same", planner == open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
