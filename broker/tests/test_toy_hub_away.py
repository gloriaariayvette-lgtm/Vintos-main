#!/usr/bin/env python3
"""The hub travels with her, so its address is not a constant (Gloria, 2026-10-14: "This one has to be able to
work while away from Aegis. That is the point. It's connected to my phone via Bluetooth."). One hardcoded LAN
address, probed once at import, meant every device read as switched off away from home. Here the address is
resolved from candidates, remembered, and a hub that cannot be reached is told apart from devices that are off.

Isolation: requests is a counting stub installed before the module is imported, so nothing leaves this process;
scratch HOME, so the remembered-address file is a throwaway."""
import importlib, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="toy-hub-away-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_ENV_FILE"] = os.path.join(HOME, "vintos.env")
for name in ("LOVENSE_TAILNET_HOST", "LOVENSE_HOST", "LOVENSE_PORT"):
    os.environ.pop(name, None)
def no_socket(*a, **k): raise AssertionError("a test must never open a socket")
socket.socket.connect = no_socket; socket.create_connection = no_socket

POSTS = []
ANSWERS = {}            # url -> status code
class Reply:
    def __init__(self, code, body=None): self.status_code = code; self._b = body or {}
    def json(self): return self._b
def post(url, json=None, timeout=None, **k):
    POSTS.append(url)
    code = ANSWERS.get(url)
    if code is None: raise OSError("[Errno 113] No route to host")
    return Reply(code, {"code": 200, "data": {"toys": {"18690acf2f39": {"id": "18690acf2f39", "status": "1"}}}})
sys.modules["requests"] = types.SimpleNamespace(post=post, get=post)

sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.modules.pop("toy_link", None)
before = len(POSTS)
import toy_link as T
import device_context as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("requests is a stub and HOME is scratch", T.requests.post is post and T.ENDPOINT.startswith(HOME))
check("importing the module opens nothing: the hub is not probed at import time", len(POSTS) == before, POSTS)

print("--- away from her network: the phone is reached on the tailnet ---")
PHONE = "http://her-phone:20010/command"
ANSWERS[PHONE] = 200
open(os.environ["VINTOS_ENV_FILE"], "w").write("LOVENSE_TAILNET_HOST=her-phone\n")
check("the tailnet name is tried before the home address", T.hosts() == ["her-phone", "192.168.1.66"], T.hosts())
check("an IP address is also tried in the vendor's own domain form, where its certificate is valid",
      "https://192-168-1-66.lovense.club:30010/command" in T.candidates(), T.candidates())
check("a name that is not an IP is tried as plain HTTP only",
      not any("her-phone" in u and u.startswith("https") for u in T.candidates()), T.candidates())
T._endpoint.update(url="", at=0.0)
check("the hub is found away from home", T.endpoint() == PHONE, (T.endpoint(), POSTS))
check("the home address was not needed first", POSTS and POSTS[0] == PHONE, POSTS)

n = len(POSTS)
check("the address that worked is remembered, so an ordinary call scans nothing", T.endpoint() == PHONE and len(POSTS) == n)
check("it is remembered across processes", json.load(open(T.ENDPOINT))["url"] == PHONE)
T._endpoint.update(url="", at=0.0); POSTS.clear()
check("a fresh process tries the remembered address first", T.endpoint() == PHONE and POSTS[0] == PHONE, POSTS)

print("--- the device she has with her is seen ---")
T._status_cache.update(t=0.0, map={})
check("a toy the hub reports is present away from home", T.connected("ferri", strict=True))
check("one it does not report is not", not T.connected("tenera", strict=True))
POSTS.clear()
T._post({"command": "Function", "action": "Stop", "timeSec": 0, "apiVer": 1})
check("a send goes to the address that answered", POSTS and all(u == PHONE for u in POSTS), POSTS)

print("--- the hub moved: it is found again without a restart ---")
MOVED = "http://her-phone:20011/command"
ANSWERS.clear(); ANSWERS[MOVED] = 200
POSTS.clear()
check("a send that fails re-resolves and still lands", T._post({"command": "GetToys", "apiVer": 1}).status_code == 200
      and MOVED in POSTS, POSTS)

print("--- the hub answers nowhere ---")
ANSWERS.clear()
T._endpoint.update(url="", at=0.0); T._status_cache.update(t=0.0, map={})
POSTS.clear()
import time as _t
_t0 = _t.monotonic()
check("no address answers", T.endpoint() == "" and not T.reachable())
check("every candidate was asked, and asked at once rather than one timeout after another",
      len(POSTS) >= len(T.candidates()) and _t.monotonic() - _t0 < 2.0, (len(POSTS), len(T.candidates())))
POSTS.clear()
check("a hub that is away is not re-scanned on every call", T.endpoint() == "" and not POSTS, POSTS)
raised = False
try:
    T._post({"command": "GetToys", "apiVer": 1})
except Exception:
    raised = True
check("a send fails loudly rather than silently doing nothing", raised)
check("presence is never claimed when the hub cannot be read", not T.connected("ferri", strict=True))
line = D.hands_line_idle()
check("he is told the hub is not answering, not that the device is off",
      "not answering" in line and "no device is switched on" not in line.lower(), line)
check("and is told not to say a device is off or absent", "do not tell her" in line.lower(), line)
import time as _tt
T._endpoint.update(url=PHONE, at=_tt.time())
check("with the hub reachable the ordinary idle line comes back", "no device is switched on" in D.hands_line_idle().lower())
src = open(os.path.join(REPO, "scripts", "toy_link.py")).read()
check("asking where the hub is sends no command: no-args is the diagnostic, not stop_all",
      'sys.argv[1] == "stop"' in src and src.count('print("stop_all:", stop_all())') == 1)
POSTS.clear(); T._endpoint.update(url="", at=0.0)
D.hands_line_idle()
check("building his prompt line never probes the hub", not POSTS, POSTS)
check("nothing opened a socket", socket.socket.connect is no_socket)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
