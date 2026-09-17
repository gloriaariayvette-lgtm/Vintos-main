#!/usr/bin/env python3
"""The daily DoorDash token refresh writes a 0600 token from the Mac stage and never reaches the
Mac in a suite: the HTTP boundary is stubbed and the token file is a scratch path."""
import importlib.util, io, json, os, stat, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vintos-ddtoken-")
os.environ["HOME"] = HOME
os.environ["VINTOS_STAGE_SECRET"] = "stage-secret"
os.environ["DD_CLI_TOKEN_FILE"] = os.path.join(HOME, ".vintos", "secrets", "dd-cli.token")

spec = importlib.util.spec_from_file_location("dd_token_refresh", os.path.join(ROOT, "bin", "dd-token-refresh.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

# No suite may reach the Mac: assert the boundary is a stub, then stub it.
check("the refresher exposes an HTTP boundary tests can replace", hasattr(M, "OPEN"))
sent = {}
class _Resp:
    def __init__(self, payload): self._b = json.dumps(payload).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _fake_open(req, timeout=None):
    sent["url"] = req.full_url; sent["secret"] = req.headers.get("X-vintos-stage-secret")
    return _Resp({"ok": True, "token": "tok-XYZ-123"})
M.OPEN = _fake_open

# scratch path, secret set
M.TOKEN_FILE = os.environ["DD_CLI_TOKEN_FILE"]
M.SECRET = "stage-secret"
rc = M.main()
check("a returned token is written and the run succeeds", rc == 0 and open(M.TOKEN_FILE).read() == "tok-XYZ-123")
check("the token file is 0600", stat.S_IMODE(os.stat(M.TOKEN_FILE).st_mode) == 0o600, oct(stat.S_IMODE(os.stat(M.TOKEN_FILE).st_mode)))
check("the request carried the stage secret to the Mac stage /dd-token", sent.get("secret") == "stage-secret" and sent.get("url", "").endswith("/dd-token"), sent)
check("the token file is under scratch HOME, never the live secrets dir", M.TOKEN_FILE.startswith(HOME))

# a missing token is a clean failure that leaves the last good token in place
open(M.TOKEN_FILE, "w").write("previous-good")
M.OPEN = lambda req, timeout=None: _Resp({"ok": False, "error": "sign-in required"})
rc = M.main()
check("no token returned is a failure that does not overwrite the last good token",
      rc == 1 and open(M.TOKEN_FILE).read() == "previous-good")

# with no secret configured it refuses to do anything (and reaches no network)
reached = {"n": 0}
M.OPEN = lambda req, timeout=None: reached.__setitem__("n", reached["n"] + 1) or _Resp({"ok": True, "token": "x"})
M.SECRET = ""
rc = M.main()
check("with no stage secret set it skips cleanly and never calls the Mac", rc == 0 and reached["n"] == 0)

print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
