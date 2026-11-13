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
want = {"SearchUnavailable", "brave_search"}
nodes = [n for n in tree.body if getattr(n, "name", None) in want]
logged = []
class Resp:
    def __init__(self, code, body): self.status_code, self._b = code, body
    def json(self): return self._b
reply = []
ns = {"__file__": "vintos-websearch.py", "RuntimeError": RuntimeError, "log": logged.append, "BRAVE_ENDPOINT": "https://example.test", "BRAVE_API_KEY": "k",
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
check("the search loop returns before debt on a refusal",
      "except SearchUnavailable as _su:" in src and src.index("except SearchUnavailable as _su:") < src.index('if _ses["outcome"] == "HELD_UNANSWERED":'))
check("the scripts copy is the bin file", os.path.realpath(os.path.join(REPO, "scripts", "vintos-websearch.py")) == os.path.realpath(os.path.join(REPO, "bin", "vintos-websearch.py")))
sys.exit(0 if all(R) else 1)
