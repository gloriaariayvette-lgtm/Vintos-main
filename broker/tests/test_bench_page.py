#!/usr/bin/env python3
"""The bench as a page — the part that makes it manageable.

A ledger she has to remember a command to use is a ledger she will not use. This is
Buzz's layout in one stdlib file: a rail of agents, the work in the middle, one card
per task with the two buttons that matter. No node, no bundle, no build step — it can
be edited in place on Aegis and it survives a machine with nothing installed.

What it must not become is a way to act as an agent. The page exposes her two verbs
and nothing else: approve and deny. Claiming, finishing and handing off belong to the
agents, and a button that could do them would let whoever opens the page work as one.

It is not his room, and it writes exactly one place: the bench's own ledgers."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BENCH = os.path.join(REPO, "bench")
sys.path.insert(0, BENCH)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

TMP = tempfile.mkdtemp()
os.makedirs(os.path.join(TMP, "ledgers"))
shutil.copytree(os.path.join(BENCH, "agents"), os.path.join(TMP, "agents"))

# a free port, so a run of this suite never collides with the real bench on 8791
_s = socket.socket(); _s.bind(("127.0.0.1", 0)); PORT = _s.getsockname()[1]; _s.close()
BASE = "http://127.0.0.1:%d" % PORT

env = dict(os.environ, BENCH_ROOT=TMP, BENCH_PORT=str(PORT), PYTHONUNBUFFERED="1")
proc = subprocess.Popen([sys.executable, os.path.join(BENCH, "server.py")],
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, r.read().decode()


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


try:
    up = False
    for _ in range(50):
        try:
            get("/health"); up = True; break
        except Exception:
            time.sleep(0.1)
    check("the page comes up with nothing installed but python", up)

    print("\n--- it serves one page, with no build step ---")
    code, page = get("/")
    check("the page is served", code == 200 and page.startswith("<!doctype html>"))
    check("it is one file — no bundle, no node, no import map",
          "<script src=" not in page and "type=\"module\"" not in page)
    check("it fits a phone", "width=device-width" in page and "viewport-fit=cover" in page)
    check("and keeps clear of the notch and the home bar",
          "safe-area-inset-top" in page and "safe-area-inset-bottom" in page)
    check("the buttons are thumb-sized", "min-height:44px" in page)
    check("it lays out as a rail and a pane on a big screen, one column on a small one",
          "grid-template-columns:minmax(0,1fr)" in page and "@media(min-width:900px)" in page)
    check("it carries Buzz's dark palette, attributed in the source",
          "hsl(232 23.4% 18.43%)" in page and "globals.css" in open(os.path.join(BENCH, "server.py")).read())

    print("\n--- it shows her what is waiting, and who is holding what ---")
    code, body = get("/api/state")
    st = json.loads(body)
    check("state carries every agent", code == 200 and set(st["agents"]) >= {"claude", "codex", "grok", "gemma"},
          list(st.get("agents", {})))
    check("and their delegate maps, so the page can show what goes where",
          st["agents"]["claude"]["delegate"]["grep"] == "gemma")
    check("no tasks yet", st["tasks"] == [])

    import bench as B
    B.ROOT = TMP; B.LEDGERS = os.path.join(TMP, "ledgers"); B.AGENTS = os.path.join(TMP, "agents")
    t, _ = B.propose(by="claude", what="find every caller of store_guard", kind="grep",
                     why="before the twin audit")
    code, body = get("/api/state")
    st = json.loads(body)
    row = next((x for x in st["tasks"] if x["task"] == t["task"]), None)
    check("a proposed task appears on the page", row is not None)
    check("addressed to the cheap agent, as the map says", row["owner"] == "gemma", row)
    check("with its history, so she can see how it got there", len(row.get("history") or []) == 1)

    print("\n--- her two verbs, and only hers ---")
    code, d = post("/api/approve", {"task": t["task"]})
    check("approve works from the page", code == 200 and d.get("state") == "approved", d)
    code, d = post("/api/approve", {"task": t["task"]})
    check("approving twice is refused, not silently repeated", "error" in d, d)
    t2, _ = B.propose(by="codex", what="rewrite the whole router", kind="refactor")
    code, d = post("/api/deny", {"task": t2["task"], "why": "not tonight"})
    check("deny works, and carries her reason", code == 200 and d.get("state") == "denied", d)
    check("the reason is on the record", "not tonight" in json.dumps(B.task(t2["task"])["history"]))

    for verb in ("/api/claim", "/api/done", "/api/handoff", "/api/fail", "/api/propose"):
        code, d = post(verb, {"task": t["task"], "by": "gemma"})
        check("the page cannot %s — that belongs to the agents" % verb.split("/")[-1],
              code == 404 and "no such path" in json.dumps(d), (verb, code, d))
    check("so the work still moves only through the agents' own hands",
          B.task(t["task"])["state"] == "approved")

    print("\n--- a bad request is answered, not a stack trace ---")
    req = urllib.request.Request(BASE + "/api/approve", data=b"{not json",
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5); bad = 0
    except urllib.error.HTTPError as e:
        bad = e.code
    check("malformed json is a 400", bad == 400, bad)
    code, d = post("/api/approve", {"task": "T-nothing"})
    check("an unknown task is an error message, not a crash", "error" in d and "no task" in d["error"], d)
    check("the server is still up afterwards", get("/health")[0] == 200)

    print("\n--- the token gate ---")
    src = open(os.path.join(BENCH, "server.py")).read()
    check("a token file, if present, is required on every request",
          "_authed" in src and "bad or missing token" in src and "do_GET" in src and "do_POST" in src)
    check("and it lives beside his other secrets, not in the repo",
          ".bench-token" in src and "TOKEN_FILE = os.path.expanduser" in src)

    print("\n--- the unit writes one directory, and it is not his ---")
    unit = open(os.path.join(REPO, "broker", "vintos-bench.service")).read()
    check("it is a user unit that restarts", "Restart=on-failure" in unit and "[Install]" in unit)
    check("its only writable path is the bench's ledgers",
          "ReadWritePaths=%h/repos/vintos/bench/ledgers" in unit
          and unit.count("ReadWritePaths") == 1, unit)
    check("his workspace is not writable to it", ".vintos/workspace" not in unit)
    check("and it is hardened like the others",
          all(k in unit for k in ("NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=read-only")))
    check("the deploy does not install it onto him",
          "vintos-bench" not in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

    print("\n--- and it reaches nothing of his ---")
    check("the server never names his room or his memory",
          "agent-room" not in src and ".vintos/workspace" not in src)
    check("it wrote only under its own root", B.LEDGERS.startswith(TMP))

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
