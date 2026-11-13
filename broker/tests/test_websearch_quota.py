#!/usr/bin/env python3
"""A search Brave refuses (monthly quota, rate limit) is said as such and is not 'no results' (13 November: the
quota ran out about 6 November and every search since went to curiosity debt as unanswered). Stubs only."""
import ast, os, sys, types
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
src = open(os.path.join(REPO, "scripts", "vintos-websearch.py")).read()
tree = ast.parse(src)
want = {"SearchUnavailable", "brave_search", "ddg_search", "web_search", "DDG_ENDPOINT", "DDG_UA", "searx_search", "SEARXNG_ENDPOINT"}
nodes = [n for n in tree.body if getattr(n, "name", None) in want
         or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in want for t in n.targets))]
logged = []
class Resp:
    def __init__(self, code, body): self.status_code, self._b = code, body
    def json(self): return self._b
reply = []
ns = {"os": os, "__file__": "vintos-websearch.py", "RuntimeError": RuntimeError, "log": logged.append, "BRAVE_ENDPOINT": "https://example.test", "BRAVE_API_KEY": "k",
      "requests": types.SimpleNamespace(get=None),
      "paid_http": types.SimpleNamespace(send=lambda *a, **k: reply[0])}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "ws", "exec"), ns)
reply[:] = [Resp(429, {"type": "ErrorResponse", "error": {"code": "QUOTA_LIMITED", "meta": {"plan": "Free", "quota_limit": 2000, "quota_current": 2001}}})]
try:
    ns["brave_search"]("q"); check("a quota refusal raises", False)
except ns["SearchUnavailable"] as e:
    check("a quota refusal raises SearchUnavailable with the plan and count", "QUOTA_LIMITED" in str(e) and "2001 of 2000" in str(e), e)
reply[:] = [Resp(200, {"web": {"results": [{"title": "t", "url": "u", "description": "d"}]}})]
check("results still come back", len(ns["brave_search"]("q")) == 1)
reply[:] = [Resp(200, {"web": {"results": []}})]
check("a real empty answer is still empty, not refused", ns["brave_search"]("q") == [])
DDG_HTML = ('<div class="result results_links results_links_deep web-result "><h2><a rel="nofollow" class="result__a" '
            'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fpage&amp;rut=x">An <b>Example</b></a></h2>'
            '<a class="result__snippet" href="x">A short <b>snippet</b>.</a></div>')
posted = []
def ddg_post(url, data=None, headers=None, timeout=None):
    posted.append(data["q"]); return types.SimpleNamespace(status_code=200, text=DDG_HTML)
def searx_down(*a, **k): raise OSError("refused")
ns["requests"] = types.SimpleNamespace(get=searx_down, post=ddg_post)
reply[:] = [Resp(429, {"type": "ErrorResponse", "error": {"code": "QUOTA_LIMITED", "meta": {"quota_limit": 2000, "quota_current": 2001}}})]
got = ns["web_search"]("lucier")
check("Brave refusing falls through to DuckDuckGo", posted == ["lucier"] and got == [{"title": "An Example", "url": "https://example.org/page", "description": "A short snippet."}], got)
check("the refusal is logged, not hidden", any("searching DuckDuckGo instead" in str(x) for x in logged), logged)
reply[:] = [Resp(200, {"web": {"results": [{"title": "t", "url": "u", "description": "d"}]}})]
posted.clear()
check("Brave answering means DuckDuckGo is not asked", len(ns["web_search"]("q")) == 1 and not posted)
def ddg_down(*a, **k): return types.SimpleNamespace(status_code=503, text="")
ns["requests"] = types.SimpleNamespace(get=searx_down, post=ddg_down)
reply[:] = [Resp(429, {"type": "ErrorResponse", "error": {"code": "QUOTA_LIMITED"}})]
try:
    ns["web_search"]("q"); check("both refusing raises", False)
except ns["SearchUnavailable"]:
    check("both refusing raises SearchUnavailable", True)
class SR:
    status_code = 200
    def json(self): return {"results": [{"title": "S", "url": "https://s.example", "content": "c"}]}
ns["requests"] = types.SimpleNamespace(get=lambda *a, **k: SR(), post=ddg_post)
posted.clear(); reply[:] = []
check("SearXNG answering is used first: no Brave, no DuckDuckGo", ns["web_search"]("q") == [{"title": "S", "url": "https://s.example", "description": "c"}] and not posted)
check("the search loop uses web_search", "_res = web_search(_aq)" in src)
check("the search loop returns before debt on a refusal",
      "except SearchUnavailable as _su:" in src and src.index("except SearchUnavailable as _su:") < src.index('if _ses["outcome"] == "HELD_UNANSWERED":'))
check("the scripts copy is the bin file", os.path.realpath(os.path.join(REPO, "scripts", "vintos-websearch.py")) == os.path.realpath(os.path.join(REPO, "bin", "vintos-websearch.py")))
sys.exit(0 if all(R) else 1)
