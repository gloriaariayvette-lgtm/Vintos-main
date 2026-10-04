#!/usr/bin/env python3
"""A connector's MCP url is found by asking the network, not by asking Gloria (2026-10-04).

Every socket is refused and the probe's opener is a stub, so nothing here reaches her account or any endpoint. Her
url file is a scratch file.
"""
import json, os, socket, sys, tempfile, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="connector-discover-")
os.environ["HOME"] = HOME
os.environ["VINTOS_CONNECTOR_URLS"] = os.path.join(HOME, ".vintos", "connector-urls.json")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import claude_connector_catalog as catalog
import connector_discover as D

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("her url file is the scratch one", catalog.URLS_FILE.startswith(HOME))

# --- which endpoints it would even try ------------------------------------------------------------------
boltz = D.candidates("boltz", catalog.PLUGINS["boltz"])
eden = D.candidates("eden", catalog.PLUGINS["eden"])
check("it tries the hosted spelling of the connector's own name", "https://boltz.mcp.claude.com/mcp" in boltz, boltz)
check("... and of its server name", "https://boltz-api.mcp.claude.com/mcp" in boltz, boltz)
check("a multi-part server name gives its own tail too", "https://basecamp-research.mcp.claude.com/mcp" in eden, eden)
check("every candidate is an https mcp.claude.com endpoint, never a guess at someone else's host",
      all(u.startswith("https://") and u.endswith(".mcp.claude.com/mcp") for u in boltz + eden), boltz + eden)

# --- what counts as an answer --------------------------------------------------------------------------
class Reply:
    def __init__(self, status, body): self.status, self._b = status, body.encode()
    def read(self, n=None): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False

def opener_for(table):
    def open_(req, timeout=None):
        got = table.get(req.full_url, 404)
        if isinstance(got, int):
            raise urllib.error.HTTPError(req.full_url, got, "no", {}, None)
        return Reply(200, got)
    return open_

ok, why = D.answers("https://x.mcp.claude.com/mcp", opener_for({"https://x.mcp.claude.com/mcp": '{"jsonrpc":"2.0","result":{}}'}))
check("a real MCP reply counts", ok and "initialize" in why, why)
ok, why = D.answers("https://x.mcp.claude.com/mcp", opener_for({"https://x.mcp.claude.com/mcp": 401}))
check("401 counts: the endpoint is there and wants her credentials", ok and "credentials" in why, why)
ok, _ = D.answers("https://x.mcp.claude.com/mcp", opener_for({"https://x.mcp.claude.com/mcp": 404}))
check("404 does not count", not ok)
ok, _ = D.answers("https://x.mcp.claude.com/mcp", opener_for({"https://x.mcp.claude.com/mcp": "<html>sign in</html>"}))
check("a sign-in page that returns 200 does not count", not ok)

# --- a run, with only one endpoint answering -----------------------------------------------------------
live = "https://basecamp-research.mcp.claude.com/mcp"
found, missed = D.find(("boltz", "eden"), opener_for({live: '{"jsonrpc":"2.0","result":{"protocolVersion":"2025-06-18"}}'}))
check("the connector whose endpoint answered is found", [r["name"] for r in found] == ["eden"]
      and found[0]["url"] == live, found)
check("the one that answered nowhere is reported, with what was tried", [r["name"] for r in missed] == ["boltz"]
      and "boltz.mcp.claude.com" in " ".join(missed[0]["tried"]), missed)
check("nothing is written until it is asked for", not os.path.exists(catalog.URLS_FILE))
rows = D.write(found)
check("what was found is written, and read back by the catalog", rows["eden"] == live and catalog.url_for("eden") == live)
check("... so it is offered to his Lab from the next pass", "eden" in catalog.prompt_instructions("lab")
      and "boltz" not in catalog.prompt_instructions("lab"))
json.dump({"pubmed": "https://hers.example/mcp"}, open(catalog.URLS_FILE, "w"))
D.write(found)
check("a url she set herself is kept", json.load(open(catalog.URLS_FILE))["pubmed"] == "https://hers.example/mcp")
found2, _ = D.find(("eden",), opener_for({}))
check("a connector already reachable is not looked for again", found2 == [], found2)

# What her file actually held on 4 October: a template line Claude gave her before discovery existed.
json.dump({"boltz": "https://PASTE_BOLTZ_URL/mcp", "eden": "https://PASTE_EDEN_URL/mcp"}, open(catalog.URLS_FILE, "w"))
check("a placeholder in her file is not taken for a url", catalog.url_for("boltz") == "" and catalog.url_for("eden") == "")
check("... so the Lab is not offered a connector that does not exist", "boltz" not in catalog.prompt_instructions("lab"))
found3, missed3 = D.find(("boltz", "eden"), opener_for({live: '{"jsonrpc":"2.0","result":{}}'}))
check("... and discovery looks for both instead of skipping them", [r["name"] for r in found3] == ["eden"]
      and [r["name"] for r in missed3] == ["boltz"], (found3, missed3))
D.write(found3)
check("what it found replaces the placeholder", json.load(open(catalog.URLS_FILE))["eden"] == live
      and catalog.url_for("eden") == live)

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "connector_discover.py" in dep)
check("... and runs it, so she never has to", 'connector_discover.py" --write' in dep)
check("a discovery that fails never fails the deploy", "not looked for this time" in dep)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
