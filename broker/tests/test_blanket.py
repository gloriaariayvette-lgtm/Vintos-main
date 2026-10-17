#!/usr/bin/env python3
"""The heated blanket (Gloria, 17 October): a Linkind Matter plug shared into Home Assistant. In the avatar and
ReelRoom chats he writes [HOME: blanket_on] or [HOME: blanket_off]; on is two hours, only while she is home, and the
server switches it off when the time is up. Scratch HOME; Home Assistant and presence are stubs; nothing is switched."""
import ast, importlib.util, json, os, sys, tempfile, time, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="blanket-"); os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

spec = importlib.util.spec_from_file_location("vh", os.path.join(REPO, "scripts", "vintos-home.py"))
VH = importlib.util.module_from_spec(spec); spec.loader.exec_module(VH)
check("the house config and blanket state are throwaway", VH.CONFIG_FILE.startswith(HOME) and VH.BLANKET_STATE.startswith(HOME))
SENT = []
VH.ha_request = lambda endpoint, payload: (SENT.append((endpoint, payload["entity_id"])), (200, ""))[1]
VH.ha_state = lambda ent: {"state": "off"}
HOME_NOW = [True]
VH._she_is_home = lambda: HOME_NOW[0]
json.dump({"url": "http://ha.test", "token": "t", "rooms": {}}, open(VH.CONFIG_FILE, "w"))
check("no plug configured: it says so and switches nothing", VH.blanket_on() == (False, "the blanket's plug is not in the house config") and not SENT)
json.dump({"url": "http://ha.test", "token": "t", "rooms": {}, "devices": {"blanket": "switch.linkind_plug"}}, open(VH.CONFIG_FILE, "w"))
HOME_NOW[0] = False
check("she is not home: not switched on", VH.blanket_on() == (False, "Gloria is not home") and not SENT)
HOME_NOW[0] = True
ok, why = VH.blanket_on()
st = json.load(open(VH.BLANKET_STATE))
check("she is home: on, for two hours", ok and SENT[-1] == ("switch/turn_on", "switch.linkind_plug")
      and 7190 < st["on_until"] - time.time() <= 7200, (ok, why, st))
check("before its time, the timer leaves it on", VH.blanket_expire() is False and SENT[-1][0] == "switch/turn_on")
check("when two hours are up, the timer switches it off", VH.blanket_expire(now=time.time() + 7201)
      and SENT[-1] == ("switch/turn_off", "switch.linkind_plug") and not os.path.exists(VH.BLANKET_STATE))
check("with nothing running, the timer does nothing", VH.blanket_expire(now=time.time() + 9e9) is False)
check("off works whether or not she is home", (HOME_NOW.__setitem__(0, False), VH.blanket_off())[1][0] and SENT[-1][0] == "switch/turn_off")
src = open(os.path.join(REPO, "scripts", "vintos-home.py")).read()
check("status from the command line never switches it", "elif w == \"status\": print(device_state(\"blanket\")" in src)

srv = open(os.path.join(REPO, "bin", "server.py")).read()
fns = {n.name: n for n in ast.parse(srv).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
ns = {"os": os, "WORKSPACE": os.path.join(HOME, "ws")}
exec(compile(ast.Module([fns["_home_tags"], fns["_blanket_line"]], []), "srv", "exec"), ns)
CALLS = []
fake = types.SimpleNamespace(blanket_on=lambda: (CALLS.append("on"), (True, "on until 23:10"))[1],
                             blanket_off=lambda: (CALLS.append("off"), (True, "off"))[1],
                             named_device=lambda n: "switch.linkind_plug", device_state=lambda n: "off")
ns["_vintos_home"] = lambda: fake
reply, done = ns["_home_tags"]("Let me warm the bed for you. [HOME: blanket_on] Come here.")
check("[HOME: blanket_on] in his reply switches it and leaves his words clean",
      CALLS == ["on"] and reply == "Let me warm the bed for you. Come here." and "ok: on until 23:10" in done[0], (reply, done))
reply, done = ns["_home_tags"]("[HOME: lights_flicker] boo")
check("a tag that is not the blanket switches nothing here", CALLS == ["on"] and reply == "boo", (reply, CALLS))
check("he is told the blanket is there and how to switch it", "[HOME: blanket_on]" in ns["_blanket_line"]() and "two hours" in ns["_blanket_line"]())
fake.named_device = lambda n: None
check("no plug configured: he is told nothing", ns["_blanket_line"]() == "")
av = srv[srv.index("async def avatar_chat("):srv.index("async def avatar_latest_imprint(")]
check("the avatar route (ReelRoom too) acts on his tags, and a test turn only strips them",
      "reply, _home_done = _home_tags(reply)" in av and "if _test_turn or (_prov_envelope and not _prov_envelope.get(\"may_witness\")):" in av)
check("the avatar prompt carries the blanket line", "_bl = _blanket_line()" in av)
check("the server keeps the two hours", "async def start_blanket_timer" in srv and "blanket_expire()" in srv)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
