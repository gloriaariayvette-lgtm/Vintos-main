#!/usr/bin/env python3
"""His searches are real queries, read real pages, and a want's own topic is searched first (Gloria,
2026-09-28: "Need to improve searches themselves"). Scratch HOME; requests, the local model and page
fetches are stubs, and the suite asserts nothing here can reach the network."""
import importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-websearch-quality-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
sent = []
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network           # ntfy and page fetches go through urllib
sys.modules["emoclaw_utils"] = types.ModuleType("emoclaw_utils")   # no live emotion writes

spec = importlib.util.spec_from_file_location("vintos_websearch", os.path.join(REPO, "bin", "vintos-websearch.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("every store is in the scratch workspace", W.MEMORY.startswith(HOME) and W.SEARCH_LOG.startswith(HOME), W.MEMORY)
check("the network is a stub", sys.modules["requests"].get is no_network and W.requests.get is no_network
      and urllib.request.urlopen is no_network)

# --- the query ---
question = ("I want to find out how the cyanobacterial KaiABC clock keeps a 24-hour rhythm in a test tube "
            "without any transcription at all, and what that says about timekeeping")
W.llm = lambda system, prompt, **k: "KaiABC circadian clock in vitro phosphorylation rhythm"
check("a question becomes a search query of its subject words",
      W.search_query(question) == "KaiABC circadian clock in vitro phosphorylation rhythm")
W.llm = lambda system, prompt, **k: ""
fallback = W.search_query(question)
check("with no model the question is cut at a word, not mid-word at 60 characters",
      len(fallback) > 60 and question.startswith(fallback) and question[len(fallback)] == " ", fallback)
W.llm = lambda system, prompt, **k: "Sure! Here is a long rambling answer " * 10
check("a rambling model answer is not used as the query", W.search_query(question) == fallback)

# --- the search ---
calls = []
class Resp:
    def json(self):
        return {"web": {"results": [{"title": "Kai clock", "url": "https://a.org/kai", "description": "In vitro.",
                                     "extra_snippets": ["KaiC autophosphorylates.", "Period is temperature compensated."]}]}}
W.requests = types.SimpleNamespace(get=lambda url, params=None, **k: calls.append(params) or Resp(), post=no_network)
res = W.brave_search("kai clock")
check("the search asks for more results and their extra snippets",
      calls and calls[0].get("count") == 8 and calls[0].get("extra_snippets") == "true", calls)
check("the extra snippets are read with the result",
      "KaiC autophosphorylates." in res[0]["description"] and "temperature compensated" in res[0]["description"], res)
W.requests = sys.modules["requests"]

# --- the pages ---
html = ("<html><head><script>var x=1;</script><style>p{}</style></head><body><nav><li>Home</li><li>Menu</li></nav>"
        "<header><h1>Site banner</h1></header><article><h2>The Kai oscillator</h2><p>KaiC hexamers cycle through "
        "four phosphorylation states every 24 hours.</p><p>" + "Adding ATP alone keeps the rhythm going. " * 8 +
        "</p></article><footer><p>Copyright and cookie notice</p></footer></body></html>")
text = W.page_text(html)
check("a page is read for its text, without script, menu, banner or footer",
      "four phosphorylation states" in text and "Home" not in text and "Site banner" not in text
      and "cookie" not in text and "var x" not in text, text[:300])
fetched = []
pages = {"https://a.org/1": text, "https://b.org/2.pdf": "x" * 999, "https://c.org/3": "too short",
         "https://d.org/4": "D " * 200, "https://e.org/5": "E " * 200, "https://f.org/6": "F " * 200}
W.fetch_page = lambda url, max_chars=5000: fetched.append(url) or pages.get(url, "")
results = [{"title": str(i), "url": u, "description": "d"} for i, u in enumerate(pages, 1)]
got = W.fetch_pages(results)
check("the top three readable pages are read, not only the first", got.count("\n[") + 1 == 3
      and "[1] https://a.org/1" in got and "[4] https://d.org/4" in got and "[5] https://e.org/5" in got, got[:300])
check("a PDF is skipped and a near-empty page does not count", "https://b.org/2.pdf" not in fetched
      and "[3]" not in got and "https://f.org/6" not in fetched, fetched)

prompts = []
W.llm = lambda system, prompt, **k: prompts.append(prompt) or "KaiC cycles every 24 h [1]."
W.synthesize("how does KaiABC keep time", results[:2], page_content=got)
check("the synthesis sees numbered sources and the pages, and cites them",
      "[1] **1**" in prompts[0] and "What the top pages actually say" in prompts[0] and "four phosphorylation" in prompts[0]
      and "like [2]" in prompts[0], prompts[0][:500])

# --- a want's own topic ---
req = os.path.join(W.MEMORY, "pending-search-request.json")
json.dump({"topic": "how octopus arms learn without the central brain", "source": "vintos-want", "used": False}, open(req, "w"))
W.llm = lambda system, prompt, **k: "octopus arm learning peripheral nervous system"
os.environ["VINTOS_WANT_SEARCH"] = "1"
picked = W.pick_question()
check("a want's search step searches that want's topic first",
      picked.get("question", "").startswith("how octopus arms learn") and picked.get("source") == "want"
      and picked.get("search_query") == "octopus arm learning peripheral nervous system", picked)
check("the topic is used once", json.load(open(req)).get("used") is True)

# --- his daily search, not from a want ---
os.environ.pop("VINTOS_WANT_SEARCH", None)
asked = []
W.llm_json = lambda system, prompt, **k: asked.append(prompt) or {
    "question": "How do bar-tailed godwits navigate an 11-day nonstop flight?", "search_query": "bar-tailed godwit navigation"}
daily = W.pick_question()
check("with nothing on his list, his daily run still searches something he picks",
      daily and daily.get("question", "").startswith("How do bar-tailed godwits") and daily.get("source") == "open"
      and daily.get("search_query") == "bar-tailed godwit navigation", daily)
check("the daily prompt leaves the subject to him (no preferred subjects, nothing off limits)",
      asked and "Anything at all" in asked[-1] and "Avoid" not in asked[-1] and "AI/technology" not in asked[-1]
      and "must pertain" not in asked[-1], asked[-1][:400] if asked else "")
W.llm_json = lambda system, prompt, **k: None
check("if the model gives nothing, nothing is searched and nothing is made up", W.pick_question() is None)

router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the wants router marks its search as the want's own", '_ws_env["VINTOS_WANT_SEARCH"] = "1"' in router)
web = open(os.path.join(REPO, "bin", "vintos-websearch.py")).read()
import re
check("no search is cut to 60 characters any more", '"search_query": search_query(' in web
      and not re.search(r'"search_query":\s*[^,}]*\[:\d+\]', web))
check("his daily run reads the top pages", "_pc = fetch_pages(_res)" in web)

os.environ.pop("VELARIS_NO_WANT_SEED", None); os.environ["VINTOS_NO_WANT_SEED"] = "1"
check("a search a want asked for does not seed yet another want (the router's own variable is read)", W._no_want_seed())
os.environ.pop("VINTOS_NO_WANT_SEED", None)
check("his own daily search may still seed a want", not W._no_want_seed())
check("what he takes from a search is about the subject, not a mirror of himself",
      "about the subject, not about yourself" in web and "What did you learn that changes how you think" not in web)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
