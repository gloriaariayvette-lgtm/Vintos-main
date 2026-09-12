#!/usr/bin/env python3
"""The bench as a page — the part that makes it manageable.

A ledger she has to remember a command to use is a ledger she will not use. This is
Buzz's layout in one stdlib file: a rail of agents, the work in the middle, one card
per task with the two buttons that matter. No node, no bundle, no build step — it can
be edited in place on Aegis and it survives a machine with nothing installed.

It reached her phone as a black rectangle the first time, and two separate faults
each did it on their own. Both have a check here:

  - `bench/ledgers/` was not tracked, so a fresh pull had no such directory, so
    systemd refused to start a unit whose `ReadWritePaths=` named it (226/NAMESPACE).
    Nothing was listening. A page cannot be debugged when the port is shut.
  - the page drew itself in JavaScript and shipped an empty `<main>` saying
    "loading…". Every pixel depended on a fetch. So the page is rendered on the
    server now, and the two buttons are real forms: the suite strips the script out
    entirely and asserts she can still read her tasks and still approve one.

What it must not become is a way to act as an agent. The page exposes her two verbs
and nothing else: approve and deny. Claiming, finishing and handing off belong to the
agents, and a button that could do them would let whoever opens the page work as one.

It is not his room, and it writes exactly one place: the bench's own ledgers."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
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


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def spawn(port, root, token_file=""):
    env = dict(os.environ, BENCH_ROOT=root, BENCH_PORT=str(port), PYTHONUNBUFFERED="1")
    env["BENCH_TOKEN_FILE"] = token_file or os.path.join(TMP, "no-such-token")
    p = subprocess.Popen([sys.executable, os.path.join(BENCH, "server.py")],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:%d" % port
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/health", timeout=5).read(); return p, base
        except Exception:
            time.sleep(0.1)
    return p, base


PORT = free_port()
proc, BASE = spawn(PORT, TMP)


def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def form(path, fields, follow=False):
    """A plain browser form post — no JavaScript anywhere near it."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    op = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with op.open(req, timeout=5) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def no_script(html):
    """The page as a browser that ran none of its JavaScript sees it."""
    return re.sub(r"(?is)<script.*?</script>", "", html)


try:
    check("the page comes up with nothing installed but python", get("/health")[0] == 200)

    print("\n--- it serves one page, with no build step ---")
    code, page = get("/")
    check("the page is served", code == 200 and page.startswith("<!doctype html>"), code)
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
    check("and tells the browser it is a dark page, so the chrome matches",
          'name="color-scheme" content="dark"' in page)

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
    check("a proposed task appears in the state", row is not None)
    check("addressed to the cheap agent, as the map says", row["owner"] == "gemma", row)
    check("with its history, so she can see how it got there", len(row.get("history") or []) == 1)

    print("\n--- THE BLACK RECTANGLE: the page renders on the server, not in her browser ---")
    code, page = get("/")
    bare = no_script(page)
    check("the task is in the HTML the server sent — not fetched afterwards",
          "find every caller of store_guard" in bare, bare[-400:])
    check("its id, kind and owner too", t["task"] in bare and ">grep<" in bare and "gemma" in bare)
    check("the reason she was given is on it", "before the twin audit" in bare)
    check("the agent rail is in the HTML too, not built by a script",
          "<nav" in bare and "waiting on you" in bare and ">claude<" in bare and ">codex<" in bare)
    check("nothing on the page says loading — there is nothing to wait for",
          "loading" not in page.lower())
    check("and the empty <main> that started all this is gone",
          "<main" in bare and bare.index("<main") < bare.index("find every caller"))
    check("the script is an enhancement: it renders nothing, it only swaps what the server sent",
          "innerHTML = w.innerHTML" in page and "X-Fragment" in page)

    print("\n--- her two verbs work with JavaScript switched off ---")
    check("Approve is a real form, posting to a real path",
          '<form class="bench" method="post" action="/api/approve">' in bare)
    check("Deny is too, and carries a field for the reason",
          '<form class="bench" method="post" action="/api/deny">' in bare
          and 'name="why"' in bare)
    code, _, hdrs = form("/api/approve", {"task": t["task"], "view": "pending"})
    check("a plain form post approves", code == 303, code)
    check("and sends her back to the page she was on, not to a JSON blob",
          "/?view=pending" in (hdrs.get("Location") or ""), hdrs.get("Location"))
    check("the task is approved on the record", B.task(t["task"])["state"] == "approved")

    t2, _ = B.propose(by="codex", what="rewrite the whole router", kind="refactor")
    code, _, hdrs = form("/api/deny", {"task": t2["task"], "why": "not tonight", "view": "all"})
    check("a plain form post denies", code == 303 and B.task(t2["task"])["state"] == "denied", code)
    check("and her reason is on the record", "not tonight" in json.dumps(B.task(t2["task"])["history"]))
    check("it returns her to the view she was in", "view=all" in (hdrs.get("Location") or ""))

    t3, _ = B.propose(by="grok", what="port the fix to the twin", kind="port")
    code, frag, _ = form("/api/approve", {"task": t3["task"], "view": "pending"})
    check("with the script running it answers with the same fragment, not a redirect",
          code == 303, code)
    code, frag, _ = form("/api/deny", {"task": "T-nothing", "why": "x", "view": "pending"})
    check("and a form post naming no task is a page, not a stack trace",
          code == 303 or "<!doctype html>" in frag, code)

    print("\n--- the fragment the script asks for is the same thing, rendered once ---")
    code, frag = get("/?view=all", {"X-Fragment": "1"})
    check("a fragment request gets the pane only, no doctype",
          code == 200 and not frag.startswith("<!doctype") and 'id="wrap"' in frag, frag[:120])
    check("and it carries the same cards", "rewrite the whole router" in frag)

    print("\n--- the JSON api still answers, for anything that is not a browser ---")
    t4, _ = B.propose(by="claude", what="one more", kind="grep")
    code, d = post("/api/approve", {"task": t4["task"]})
    check("approve works as json too", code == 200 and d.get("state") == "approved", d)
    code, d = post("/api/approve", {"task": t4["task"]})
    check("approving twice is refused, not silently repeated", "error" in d, d)

    for verb in ("/api/claim", "/api/done", "/api/handoff", "/api/fail", "/api/propose"):
        code, d = post(verb, {"task": t4["task"], "by": "gemma"})
        check("the page cannot %s — that belongs to the agents" % verb.split("/")[-1],
              code == 404 and "no such path" in json.dumps(d), (verb, code, d))
    for verb in ("/api/claim", "/api/done"):
        code, b, _ = form(verb, {"task": t4["task"], "by": "gemma"})
        check("nor by posting a form at %s" % verb.split("/")[-1], code == 404, (verb, code))
    check("so the work still moves only through the agents' own hands",
          B.task(t4["task"])["state"] == "approved")

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
    code, page404 = get("/nowhere")
    check("an unknown path is a page with a way back, not a blank",
          code == 404 and "<!doctype html>" in page404 and 'href="/"' in page404, code)
    check("the server is still up afterwards", get("/health")[0] == 200)

    print("\n--- /diag, so the next blank page takes thirty seconds ---")
    code, diag = get("/diag")
    check("diag answers in plain text", code == 200 and "ledgers dir" in diag, diag[:200])
    check("it says whether the directory the unit needs is there",
          "exists=True" in diag and "writable=True" in diag, diag)
    check("and it never prints the token", "token" in diag and TMP in diag)

    print("\n--- the token gate ---")
    t5, _ = B.propose(by="claude", what="something still waiting on her", kind="review")
    tokf = os.path.join(TMP, "tok")
    open(tokf, "w").write("s3cret\n")
    p2, base2 = spawn(free_port(), TMP, token_file=tokf)
    _real_base = BASE
    try:
        BASE = base2
        check("health is never gated — it is how she checks it is up", get("/health")[0] == 200)
        code, refused = get("/")
        check("the page without a token is refused", code == 403, code)
        check("and refused as a page that says what to do, not a JSON blob she has to read",
              "<!doctype html>" in refused and ".bench-token" in refused, refused[:160])
        code, okpage = get("/?t=s3cret")
        check("with the token it is her bench", code == 200 and "<nav" in okpage, code)
        check("and the token is carried on every link on it, so she is not thrown out",
              "t=s3cret" in okpage)
        check("and on the forms, so approving does not lose it",
              'name="t" value="s3cret"' in okpage)
        code, d = post("/api/approve", {"task": "x"})
        check("the api is gated too", code == 403, (code, d))
    finally:
        BASE = _real_base
        p2.terminate()
        try:
            p2.wait(timeout=5)
        except Exception:
            p2.kill()

    src = open(os.path.join(BENCH, "server.py")).read()
    check("the gate is on both verbs",
          "_authed" in src and "bad or missing token" in src and "do_GET" in src and "do_POST" in src)
    check("and the token lives beside his other secrets, not in the repo",
          ".bench-token" in src and "os.path.expanduser" in src)

    print("\n--- the unit starts, which is the other half of the black rectangle ---")
    unit = open(os.path.join(REPO, "broker", "vintos-bench.service")).read()
    check("it is a user unit that restarts", "Restart=on-failure" in unit and "[Install]" in unit)
    directives = [l for l in unit.splitlines() if l.startswith("ReadWritePaths")]
    check("its only writable path is the bench's ledgers",
          len(directives) == 1 and directives[0].endswith("%h/repos/vintos/bench/ledgers"), directives)
    check("his workspace is not writable to it", ".vintos/workspace" not in unit)
    check("and it is hardened like the others",
          all(k in unit for k in ("NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=read-only")))
    check("the checkout is read-only inside it, so python is told not to write bytecode",
          "PYTHONDONTWRITEBYTECODE=1" in unit)
    check("the deploy does not install it onto him",
          "vintos-bench" not in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

    # The fault itself: systemd refuses to start a unit whose ReadWritePaths= names a
    # path that does not exist, and ProtectHome=read-only means the service cannot
    # create it. An untracked bench/ledgers/ was a dead port and a blank phone.
    rw = directives[0].split("=", 1)[1].strip()
    check("the writable path is marked optional, so a missing directory cannot refuse the unit",
          rw.startswith("-"), rw)
    check("and the directory is tracked, so a fresh pull has it",
          os.path.isfile(os.path.join(BENCH, "ledgers", ".gitkeep")))
    tracked = subprocess.run(["git", "ls-files", "bench/ledgers"], cwd=REPO,
                             capture_output=True, text=True).stdout
    check("tracked in git, not merely present on this machine", ".gitkeep" in tracked, tracked)
    check("the .gitkeep says why it is there, so nobody tidies it away",
          "226" in open(os.path.join(BENCH, "ledgers", ".gitkeep")).read())

    print("\n--- and there is a doctor, so the next one is not a night ---")
    doc = os.path.join(BENCH, "doctor.sh")
    check("doctor.sh exists", os.path.isfile(doc))
    dsrc = open(doc).read()
    check("it checks the directory, the unit, the port and the health in that order",
          all(w in dsrc for w in ("bench/ledgers is MISSING", "is not installed",
                                  "nothing is listening", "/health")))
    # "active" one second after a restart means nothing: Type=simple marks a unit
    # active the instant the process is spawned. The doctor said "ok and active"
    # over a service that was already dead, and printed no reason at all.
    check("it does not believe 'active' one second after a restart",
          "still active two seconds later" in dsrc and "NRestarts" in dsrc)
    check("a dead port prints the journal without being asked",
          "journalctl --user -u" in dsrc and "-n 40" in dsrc)
    check("and how it exited, with 226/NAMESPACE named so the sandbox is recognisable",
          "ExecMainStatus" in dsrc and "226" in dsrc and "NAMESPACE" in dsrc)
    check("and it runs the same code outside the sandbox, so the verdict is not a guess",
          "outside the sandbox" in dsrc and "VERDICT" in dsrc and "8799" in dsrc)
    check("the URL it prints is lowercase — the host answers to Aegis, the link should not shout",
          'tr "A-Z" "a-z"' in dsrc)
    check("and it prints the whole URL, because Safari searches for a bare hostname",
          "http://${HOSTN}:${PORT}/" in dsrc and "turns a" in dsrc)
    out = subprocess.run(["bash", "-n", doc], capture_output=True, text=True)
    check("and it parses", out.returncode == 0, out.stderr[:300])

    print("\n--- and it reaches nothing of his ---")
    check("the server never names his room or his memory",
          "agent-room" not in src and ".vintos/workspace" not in src)
    # A service that dies without saying why is a black page with nothing behind it.
    check("the server says what it is about to do before it does it, and flushes",
          "print(_diag(), flush=True)" in src and src.index("print(_diag()") < src.index("ThreadingHTTPServer(("))
    check("a bind failure is a sentence, not a bare traceback",
          "could not bind" in src and "already on that port" in src)
    check("and anything else it dies of reaches the journal",
          "traceback.print_exc()" in src)
    check("it wrote only under its own root", B.LEDGERS.startswith(TMP))

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
