#!/usr/bin/env python3
"""The sealed 4o avatar turn (2026-10-01): it refuses to run unsealed, and inside it nothing but OpenAI is reachable.

Every socket here is refused before the module is touched; the module's own wires are then tested against
addresses that are never dialled. Nothing reaches the network; nothing is written."""
import os, socket, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

real = (socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex, subprocess.Popen, os.system)
dialled = []
def never(self, addr): dialled.append(addr); raise OSError("this suite reaches nothing")
socket.socket.connect = never
socket.socket.connect_ex = lambda self, addr: (dialled.append(addr), 111)[1]
socket.getaddrinfo = lambda *a, **k: (dialled.append(a[0]), (_ for _ in ()).throw(OSError("no DNS here")))[1]
try:
    import avatar_sealed_turn as A
    os.environ.pop("VINTOS_SEALED", None)
    check("it will not run unless his home is sealed", A.sealed() is False)
    old = sys.argv
    sys.argv = ["avatar_sealed_turn.py", "/nowhere/server.py", "hi"]
    try:
        A.main(); refused = False
    except SystemExit as e:
        refused = "not sealed" in str(e)
    sys.argv = old
    check("and says so instead of running", refused)
    A.seal_the_wires()
    try:
        socket.getaddrinfo("ntfy.sh", 443); dns_ok = True
    except socket.gaierror:
        dns_ok = False
    check("inside, a notification host does not resolve", not dns_ok and "ntfy.sh:443" in A.blocked, A.blocked)
    s = socket.socket(socket.AF_INET)
    try:
        s.connect(("127.0.0.1", 8611)); local = True
    except ConnectionRefusedError:
        local = False
    s.close()
    check("a local service (his broker) is refused", not local and "127.0.0.1:8611" in A.blocked, A.blocked)
    if hasattr(socket, "AF_UNIX"):
        u = socket.socket(socket.AF_UNIX)
        try:
            u.connect("/tmp/emoclaw.sock"); unix = True
        except ConnectionRefusedError:
            unix = False
        u.close()
        check("a daemon socket is refused", not unix)
    try:
        subprocess.Popen(["true"]); spawned = True
    except OSError:
        spawned = False
    check("no subprocess starts (his writers are subprocesses)", not spawned and any(b.startswith("process") for b in A.blocked))
    check("only OpenAI and his local Gemma are allowed", A.ALLOW_HOSTS == {"api.openai.com"}
          and A.ALLOW_ADDRS == {("100.79.177.103", 1234)})
    sh = open(os.path.join(REPO, "scripts", "avatar-sealed-turn.sh")).read()
    check("the wrapper seals home with an overlay, hides /tmp, runs the house server as her, and deletes the layer",
          "mount -t overlay" in sh and "mount -t tmpfs tmpfs /tmp" in sh and "setpriv --reuid" in sh
          and "trap 'sudo rm -rf \"$LAYER\"' EXIT" in sh and "vintos-server" in sh)
    check("nothing was dialled", dialled == [], dialled)
finally:
    socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex, subprocess.Popen, os.system = real
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
