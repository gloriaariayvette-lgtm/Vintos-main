#!/usr/bin/env python3
"""The house's route inventory (astra-server-a-p5 / b-p7 / c-p7, 2026-09-05).

Every mutating route in bin/server.py, every bin/server_domains/*.py router and scripts/watch_routes.py
is either guarded by its own credential check or listed in PUBLIC_MUTATIONS with the reason it is open.
An unlisted open door fails here, at the inventory, instead of being discovered by whoever finds it.
(Since 25 October the house guard, house_auth.py, also refuses every unlisted route whatever its
method; test_house_route_guard.py proves that against the assembled app. This inventory keeps the
handler-level check as the second layer.)"""
import os, re, sys, ast

HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.join(os.path.dirname(os.path.dirname(HERE)), "bin", "server.py")
src = open(SRV, errors="replace").read()

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

m = re.search(r"PUBLIC_MUTATIONS = \{(.*?)\n\}", src, re.S)
check("PUBLIC_MUTATIONS exists", bool(m))
public = {}
if m:
    for k, v in re.findall(r'"([^"]+)":\s*"([^"]+)"', m.group(1)): public[k] = v
check("every public mutation carries a reason", all(len(v) > 10 for v in public.values()), public)

ROOT = os.path.dirname(os.path.dirname(HERE))
SOURCES = [SRV, os.path.join(ROOT, "scripts", "watch_routes.py")] + sorted(
    f for f in __import__("glob").glob(os.path.join(ROOT, "bin", "server_domains", "*.py"))
    if os.path.basename(f) != "patch_humor_wants.py")   # an Aegis patcher, not a router
# Plain browser forms the house guard admits only with her HttpOnly session cookie (house_auth.COOKIE_FORM_WRITES).
GUARD_ONLY = {"/aq/answer", "/api/video/hero"}
routes = []
scanned = set()
for path_ in SOURCES:
    text = open(path_, errors="replace").read()
    for dm in re.finditer(r'^\s*@(?:app|router|routes)\.(post|put|delete|patch)\("([^"]+)"[^\n]*\n(.*?)(?=^\s*@(?:app|router|routes)\.|\Z)', text, re.S | re.M):
        head = dm.group(3)[:2500]
        guarded = (("_require_secret(" in head) or "_secret_ok(" in head
                   or ("X-Vintos-Secret" in head and ("APP_SECRET" in head or "_house_matches(" in head))
                   or "_voice_caller_ok(request)" in head            # the secret, or the Watch's own token
                   or "_owner(request)" in head                       # landings: the house credential
                   or re.search(r"\b(auth|phone)\(request\)", head) is not None)   # watch_routes: Watch bearer / phone
        routes.append((dm.group(2), guarded)); scanned.add(os.path.basename(path_))
check("routes were scanned in server.py, the domain routers and watch_routes",
      {"server.py", "watch_routes.py", "landings.py", "humor_wants.py"} <= scanned, scanned)
check("mutating routes were found", len(routes) > 20, len(routes))
open_unlisted = [r for r, g in routes if not g and r not in public and r not in GUARD_ONLY]
check("no unlisted open mutation", not open_unlisted, open_unlisted)
# Push-button doors: the handler takes the item's own token, or the credential from her app; listed so the
# house guard lets the token reach the handler.
TOKEN_OR_SECRET = {"/api/gloria/asks/{qid}/decide", "/api/lab/asks/{ask_id}/decide"}
listed_but_guarded = [r for r, g in routes if g and r in public and r not in TOKEN_OR_SECRET]
check("PUBLIC_MUTATIONS lists only doors that are actually open", not listed_but_guarded, listed_but_guarded)
check("the private mutations that were open are now guarded",
      all(g for r, g in routes if r in ("/api/proposals/{filename}/approve", "/api/proposals/{filename}/reject", "/api/debug/chat-message")))
_vt = src[src.index('async def voice_token'):][:1500]
check("the realtime-token door is closed: the secret or the Watch token, nothing else (22 October audit: it minted "
      "xAI/OpenAI sessions and handed out his instructions to anyone who reached it)",
      "if not _voice_caller_ok(request):" in _vt and '"/api/voice/token"' not in src[src.index("PUBLIC_MUTATIONS"):src.index("def _require_secret")]
      and '_secret_ok(request.headers.get("X-Vintos-Secret"))' in src[src.index("def _voice_caller_ok"):][:900])
check("the credential comes from the environment only, with no built-in value",
      'APP_SECRET = _house_secret()' in src and "from house_auth import configured_secret as _house_secret" in src)
check("handler checks compare in constant time and never match an unconfigured credential",
      "return _house_matches(supplied, APP_SECRET)" in src and not re.search(r"(==|!=) *APP_SECRET\b", src))
check("the house guard is installed with the public-write list",
      "_install_house_auth(app, APP_SECRET, public_writes=PUBLIC_MUTATIONS)" in src)
check("POST /api/landings (her notes feed his model of her) needs the credential",
      ("/api/landings", True) in routes)
ast.parse(src)
check("server still parses", True)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
