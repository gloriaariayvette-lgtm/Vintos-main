#!/usr/bin/env python3
"""One real avatar turn through GPT-4o that saves nowhere (Gloria, 2026-10-01: "Use the full normal avatar
route like I do ... Don't let it save anywhere").

Run only by avatar-sealed-turn.sh, which first seals his home: an overlay over the home directory sends every
write to a throwaway layer it deletes afterwards, and a fresh /tmp hides his daemons' sockets. Inside that,
this loads the house's own server.py, sets the chat to 4o, and posts her message to /api/avatar/chat exactly
as the app does: the full route, his full prompt and context, every system it runs. Nothing can leave the
machine but the call to OpenAI: every other connection and every subprocess is refused and listed.

    python3 avatar_sealed_turn.py SERVER_PY "message"      (inside the seal only)
"""
import json, os, socket, subprocess, sys, time

ALLOW_HOSTS = {"api.openai.com"}                 # 4o
ALLOW_ADDRS = {("100.79.177.103", 1234)}         # his local Gemma: the route's decline check reads it; saves nothing
blocked, allowed_ips = [], set()


def sealed():
    """True only when the home directory is an overlay and /tmp a fresh tmpfs, in this process's view."""
    home = os.path.realpath(os.path.expanduser("~"))
    kinds = {}
    for line in open("/proc/self/mounts"):
        parts = line.split()
        if len(parts) > 2:
            kinds[parts[1]] = parts[2]
    return kinds.get(home) == "overlay" and kinds.get("/tmp") == "tmpfs" and os.environ.get("VINTOS_SEALED") == "1"


def seal_the_wires():
    real_gai, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
    allow_hosts_by_addr = {h for h, _ in ALLOW_ADDRS}

    def gai(host, port, *a, **k):
        h = host.decode() if isinstance(host, bytes) else str(host)
        if h in ALLOW_HOSTS:
            res = real_gai(host, port, *a, **k)
            allowed_ips.update(r[4][0] for r in res)
            return res
        if h in allow_hosts_by_addr:
            return real_gai(host, port, *a, **k)
        blocked.append("%s:%s" % (h, port))
        raise socket.gaierror("sealed dry run: %s is not reachable" % h)

    def ok(self, addr):
        if self.family == getattr(socket, "AF_UNIX", None):
            blocked.append("socket %s" % (addr,))
            return False
        ip, port = addr[0], addr[1]
        if ip in allowed_ips or (ip, port) in ALLOW_ADDRS:
            return True
        blocked.append("%s:%s" % (ip, port))
        return False

    def connect(self, addr):
        if not ok(self, addr):
            raise ConnectionRefusedError("sealed dry run")
        return real_connect(self, addr)

    def connect_ex(self, addr):
        if not ok(self, addr):
            return 111
        return real_connect_ex(self, addr)

    socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = gai, connect, connect_ex

    class NoProcess(subprocess.Popen):
        def __init__(self, args, *a, **k):
            self._child_created = False          # so Popen's own cleanup has nothing to wait for
            blocked.append("process %s" % (" ".join(map(str, args))[:90] if isinstance(args, (list, tuple)) else str(args)[:90]))
            raise OSError("sealed dry run: no subprocess")
    subprocess.Popen = NoProcess
    os.system = lambda cmd: (blocked.append("process %s" % str(cmd)[:90]), 1)[1]


openai_calls = []


def watch_openai(real_urlopen):
    """urlopen that, for OpenAI's answers, notes what OpenAI itself reports: the model that served the call,
    the tokens it read and wrote, and how long it took. (Gloria: "Can't be right. Came back instantly.")"""
    import io

    def urlopen(req, *a, **k):
        url = str(getattr(req, "full_url", req))
        t0 = time.time()
        resp = real_urlopen(req, *a, **k)
        if "api.openai.com" not in url:
            return resp
        body = resp.read()
        try:
            d = json.loads(body)
            u = d.get("usage") or {}
            openai_calls.append({"model": d.get("model"), "in": u.get("prompt_tokens", u.get("input_tokens")),
                                 "out": u.get("completion_tokens", u.get("output_tokens")), "s": time.time() - t0})
        except ValueError:
            pass
        return io.BytesIO(body)
    return urlopen


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: avatar_sealed_turn.py SERVER_PY MESSAGE")
    if not sealed():
        sys.exit("refusing: his home is not sealed. Run scripts/avatar-sealed-turn.sh, which seals it first.")
    server_py, message = os.path.abspath(sys.argv[1]), sys.argv[2]
    seal_the_wires()
    import urllib.request
    urllib.request.urlopen = watch_openai(urllib.request.urlopen)
    here = os.path.dirname(server_py)
    for p in (os.path.expanduser("~/.vintos/workspace/scripts"), here):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(here)
    import importlib.util
    spec = importlib.util.spec_from_file_location("server", server_py)
    server = importlib.util.module_from_spec(spec)
    sys.modules["server"] = server
    spec.loader.exec_module(server)
    import model_router
    model_router.write_mode({"mode": "4o", "force_grok_turns": 0})     # inside the seal: thrown away after
    from fastapi.testclient import TestClient
    client = TestClient(server.app)                                     # no lifespan: startup jobs do not run
    t0 = time.time()
    r = client.post("/api/avatar/chat", json={"message": message}, headers={"X-Vintos-Secret": server.APP_SECRET})
    took = time.time() - t0
    try:
        d = r.json()
    except ValueError:
        d = {"reply": "", "error": r.text[:500]}
    print("\n" + "=" * 72)
    print("served by: %s   (%.1f s, HTTP %d)" % (d.get("model"), took, r.status_code))
    if d.get("error"):
        print("error:", d["error"])
    for c in openai_calls:
        print("OpenAI says: served by %s, read %s tokens (his prompt and context), wrote %s, in %.1f s"
              % (c["model"], c["in"], c["out"], c["s"]))
    print("\n" + (d.get("reply") or "(no reply)"))
    print("=" * 72)
    seen = sorted(set(blocked))
    print("\nrefused during the turn (%d): %s" % (len(seen), ", ".join(seen[:30]) + (" ..." if len(seen) > 30 else "")))


if __name__ == "__main__":
    main()
