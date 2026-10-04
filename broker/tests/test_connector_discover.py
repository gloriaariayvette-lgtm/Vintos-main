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

# The probe through her Claude login is the one thing here that could reach her account: stubbed for the whole suite.
PROBED = []
LOGIN_HAS = set()
def _probe_stub(name):
    PROBED.append(name)
    return (True, "answered through her Claude login (stub)") if name in LOGIN_HAS else (False, "stub: no login here")
D.account_probe = _probe_stub

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

# --- Boltz and EDEN have no address: they are reached through her Claude login (2026-10-04) ------------------------
check("the login probe in this suite is the stub", D.account_probe is _probe_stub)
os.remove(catalog.URLS_FILE)
found4, missed4 = D.find(("boltz", "eden"), opener_for({}))
check("with no address and no answer through the login, neither is offered, and it says what it tried",
      found4 == [] and all(any("her Claude login" in t for t in m["tried"]) for m in missed4), missed4)
LOGIN_HAS.update({"boltz", "eden"})
found5, _ = D.find(("boltz", "eden"), opener_for({}))
check("a connector that answers its free call through her login is found", sorted(r["name"] for r in found5) == ["boltz", "eden"]
      and all(r["url"] == catalog.ACCOUNT for r in found5), found5)
D.write(found5)
check("... written, and read back as reachable", catalog.url_for("boltz") == catalog.ACCOUNT and catalog.url_for("eden") == catalog.ACCOUNT)
lab_menu = catalog.prompt_instructions("lab")
check("... and offered to his Lab from the next pass", "boltz.boltz_estimate_structure_and_binding" in lab_menu
      and "eden.predict_immunogenicity" in lab_menu, lab_menu[:300])
n = len(PROBED); D.find(("boltz", "eden"), opener_for({}))
check("once found it is not probed again on every deploy", len(PROBED) == n)
check("the probe is one free read-only call and nothing else", catalog.PLUGINS["boltz"]["probe"] == ("boltz_get_guidance", {})
      and catalog.PLUGINS["eden"]["probe"] == ("list_datasets", {}))
try:
    catalog.probe_policy("boltz", "boltz_start_protein_design"); probe_refused = False
except PermissionError:
    probe_refused = True
check("the probe door opens for the probe tool only, never a paid one", probe_refused
      and catalog.probe_policy("boltz", "boltz_get_guidance")["tools"] == frozenset(("boltz_get_guidance",)))

# --- the relay: through her login there is no address to configure --------------------------------------------------
import asyncio, types
SDK_CALLS = []
class Opts:
    def __init__(self, **kw): self.kw = kw; SDK_CALLS.append(kw)
class SystemMessage:
    def __init__(self, tools): self.subtype = "init"; self.data = {"subtype": "init", "tools": tools}
class ToolUseBlock:
    def __init__(self, i, n): self.id, self.name = i, n
class ToolResultBlock:
    def __init__(self, i, c): self.tool_use_id, self.content, self.is_error = i, c, False
class Msg:
    def __init__(self, blocks): self.content = blocks
LOGIN_TOOLS = ["mcp__claude_ai_Boltz_API__boltz_get_guidance", "mcp__claude_ai_PubMed__search_articles"]
def fake_query(prompt, options):
    async def gen():
        yield SystemMessage(LOGIN_TOOLS)
        name = next((t for t in LOGIN_TOOLS if t in options.kw["allowed_tools"] and t.endswith("__boltz_get_guidance")), None)
        if name and "boltz_get_guidance" in prompt:
            yield Msg([ToolUseBlock("u1", name)])
            yield Msg([ToolResultBlock("u1", '{"guidance": "validate first"}')])
    return gen()
sys.modules["claude_agent_sdk"] = types.SimpleNamespace(query=fake_query, ClaudeAgentOptions=Opts)
import claude_connector_relay as relay
out = asyncio.run(relay._run("Boltz_API", "boltz_get_guidance", {}, catalog.ACCOUNT))
check("through her login the relay configures no address and gets the tool's own result",
      "mcp_servers" not in SDK_CALLS[-1] and out["result"] == {"guidance": "validate first"}, (SDK_CALLS[-1], out))
check("... and allows only that one tool, under the names her account gives it",
      "mcp__claude_ai_Boltz_API__boltz_get_guidance" in SDK_CALLS[-1]["allowed_tools"]
      and all(t.endswith("__boltz_get_guidance") for t in SDK_CALLS[-1]["allowed_tools"]), SDK_CALLS[-1]["allowed_tools"])
try:
    asyncio.run(relay._run("EDEN_by_Basecamp_Research", "list_datasets", {}, catalog.ACCOUNT)); said = ""
except RuntimeError as exc:
    said = str(exc)
check("a login without that connector says so, naming the connectors it does have",
      "has no EDEN_by_Basecamp_Research connector" in said and "claude_ai_Boltz_API" in said, said)
try:
    asyncio.run(relay._run("PubMed", "search_articles", {}, "https://pubmed.mcp.claude.com/mcp"))
except RuntimeError:
    pass
check("a connector with an address is still configured by its address",
      SDK_CALLS[-1].get("mcp_servers") == {"PubMed": {"type": "http", "url": "https://pubmed.mcp.claude.com/mcp"}})
ok = relay.connector({"plugin": "boltz", "surface": "probe", "tool": "boltz_get_guidance", "arguments": {}, "probe": True})
check("the probe goes through the relay's own door", ok["ok"] and ok["result"] == {"guidance": "validate first"}, ok)
try:
    relay.connector({"plugin": "boltz", "surface": "probe", "tool": "boltz_start_protein_design", "arguments": {}, "probe": True}); smuggled = True
except PermissionError:
    smuggled = False
check("a paid tool cannot ride in as a probe", not smuggled)
import claude_connector_gateway as G
check("the gateway's probe reports an answer, and a failure as a reason, never a crash",
      G.probe("boltz", transport=lambda r: {"ok": True, "result": {}})[0] is True
      and G.probe("eden", transport=lambda r: {"ok": False, "detail": "no login"}) == (False, "claude connector relay refused or failed: no login"))
del sys.modules["claude_agent_sdk"]

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "connector_discover.py" in dep)
check("... and runs it, so she never has to", 'connector_discover.py" --write' in dep)
check("a discovery that fails never fails the deploy", "not looked for this time" in dep)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
