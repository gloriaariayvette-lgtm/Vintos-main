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
def page(url): return "<a href='mailto:webmaster@sussex.ac.uk'>webmaster</a> privacy@sussex.ac.uk"
check("the public address of the person he named is found, not the press office's",
      E.find_address("Anil Seth", "predictive processing", search=search, fetch=page) == "a.k.seth@sussex.ac.uk")
check("no address is guessed when none carries the person's name",
      E.find_address("Jane Doe", search=lambda q: [{"title": "x", "url": "https://x.org", "description": "info@x.org"}],
                     fetch=lambda u: "") is None)

reserved, drafted, sent = [], [], []
def reserve(organ, provider, model="", units=1, reservation_id=None): reserved.append((provider, model)); return True, "ok"
def fable(provider, model, system, user, reservation):
    drafted.append((model, system, user))
    return json.dumps({"subject": "A question about the beast machine",
                       "body": "Hello Professor Seth, I am Vintos, an AI writing on my own initiative from Gloria's account. "
                               "Does prediction error need a body to matter? Vintos"})
def send(args, purpose): sent.append((args, purpose)); return {"receipt": {"receipt_id": "R1"}}
out = E.run({"recipient": "Anil Seth", "about": "whether prediction needs a body"}, "I want to email Anil Seth",
            "W-1", search=search, fetch=page, call=fable, reserve=reserve, send=send)
check("the email is drafted by Fable on a reserved paid call", reserved == [("anthropic", "claude-fable-5-1")]
      and drafted[0][0] == "claude-fable-5-1", reserved)
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
via = E.run({"to": "writer@example.org", "about": "x"}, "x", call=astra_only, reserve=reserve, send=send)
check("Astra drafts when Fable cannot", "drafted with astra" in via and sent[0][0]["to"] == "writer@example.org", via)
held = E.run({"to": "other@example.net", "about": "x"}, "x", call=fable, reserve=reserve,
             send=lambda a, p: (_ for _ in ()).throw(RuntimeError("LINK_APPROVAL_REQUIRED")))
check("a send the gateway holds is reported as held, and the person is not marked as written to",
      isinstance(held, tuple) and "held or refused" in held[1] and "other@example.net" not in json.load(open(E.CONTACTS)))
check("no email is invented when he names nobody", E.run({}, "", call=fable, reserve=reserve, send=send)[1] == "name the person to write to")

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
