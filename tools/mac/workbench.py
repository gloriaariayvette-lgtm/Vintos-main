#!/usr/bin/env python3
"""Workbench: talk with a local model (Gemma, or whichever LM Studio model she picks) on her Mac.

Gloria, 24 October: "a way to talk to Gemma (or whatever local model I select) with only the memory of whatever we
discuss in the thread, but it has to be able to access links and grep his code ... able to write code and not execute
it but store it in a set file that won't be disrupted by our deploys, just lives on the Mac."

  - Memory: the thread, and nothing else. No journal, no wants, none of his memory. Each thread is its own file.
  - Tools the model may ask for, one per line at the start of a line; the Workbench runs them and answers:
        FETCH <url>                    a web page or file, as text
        GREP <regex> [in <glob>]       his code, read-only (the checkout named in the config)
        READ <path> [<first>-<last>]   a file of his code, or one it saved
        LIST [<dir>]                   a folder of his code
        SAVE <filename>                then a ``` fenced block: the code is written to the Workbench's code folder
  - Code is never run. SAVE writes a plain file (never executable) into ~/Vintos-Workbench/code; an existing name is
    never overwritten, the new one gets the time added. Nothing here is in a deploy: it lives only on the Mac.
  - Local models only, no paid calls. It talks to an OpenAI-compatible server (LM Studio: http://localhost:1234/v1).

Run:  python3 ~/Vintos-Workbench/workbench.py      then open http://127.0.0.1:8765
From her phone (24 October): `tailscale serve --bg 8765` on the Mac, then open https://<the Mac's name>.ts.net on the
phone. Only her tailnet reaches it; a request that came through Tailscale must carry her Tailscale login, and nothing
listens beyond 127.0.0.1 on the Mac itself.
Python's standard library only; nothing to install.
"""
import fnmatch, html, html.parser, json, os, re, sys, threading, time, urllib.error, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.environ.get("WORKBENCH_HOME", os.path.expanduser("~/Vintos-Workbench"))
CODE = os.path.join(HOME, "code")        # its one working folder: files it writes and the sandbox may run
CODE_HISTORY = os.path.join(CODE, ".history")
RUNS = os.path.join(HOME, "runs")        # a throwaway working dir per run; nothing it does escapes here or CODE
THREADS = os.path.join(HOME, "threads")
CONFIG = os.path.join(HOME, "config.json")
SUCCESSES = os.path.join(HOME, "successes.md")   # local-only log of what worked; never committed, pushed, or deployed
PORT = int(os.environ.get("WORKBENCH_PORT", "8765"))
DEFAULTS = {"base_url": "http://localhost:1234/v1", "model": "", "repo": os.path.expanduser("~/Documents/Vintos-main-faultloop"),
            "also_read": os.path.expanduser("~/Documents/Codex"), "context_chars": 80000, "max_tokens": 2048, "temperature": 0.4, "tool_rounds": 8, "offline_runs": False}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".mypy_cache"}
LOCK = threading.Lock()

SYSTEM = """You are a careful coding companion working with Gloria on her Mac. You remember only this conversation.

You can look things up yourself. To use a tool, write the tool line on its own line, plain text, no backticks, no
bullet, nothing else on the line, and then END your message; the results come back to you in the next message:
FETCH <url>                         read a web page or file from the internet
GREP <regex> [in <glob or folder>]  search code (read-only), e.g. GREP def tend in scripts/*.py
READ <path> [<first>-<last>]        read a file: a path GREP or LIST gave, or code/<name> for one you saved
LIST [<folder>]                     list a folder
GIT [in <folder>] <command> <args>  read-only git: log, show, diff, branch, status, ls-tree, grep, blame
SAVE <filename>                     save code: the next ``` fenced block is written to code/<filename> (the prior
                                    version is kept); keep working one file and SAVE it again to update it
RUN <filename>                      run code/<filename> and get its output and errors back. It may use the network, so
                                    code that must find or reach a machine on Gloria's network (like her Acer laptop)
                                    can do so. It may read the Mac but may only WRITE inside your code folder and a
                                    throwaway run folder. Save a fix with SAVE, then RUN again, until it works.
HOSTS                               list every device on Gloria's network with its IP, MAC and open services. USE THIS
                                    to find a machine's address — never ping-sweep, Windows PCs ignore ping. HOSTS <ip>
                                    inspects one device and says which ports are open, refused, or firewalled (dropped).
BT                                  investigate Bluetooth: this Mac's radio, paired/connected devices, nearby advertisers.
Write the real value where the usage shows <...> or [...]: LIST scripts, not LIST [scripts] or LIST <folder>.
Paths are relative to his checkout, or absolute inside a folder she made readable (named below). Look before you answer:
do not describe a plan to look, look. Never pretend a tool ran. Everything you build stays in your code folder.
Do ONE tool per message and wait for its result before the next: to test code, SAVE it in one message, and after it is
saved, RUN it in the next message. Say plainly when you do not know something, and quote paths and line numbers only
from what the tools returned."""

DISTILL = """Gloria just marked this thread a success. Write ONLY the recipe for what worked: the final solution and
everything it needed — the exact commands, file names, settings, addresses, versions, and any gotcha that would trip up
someone repeating it. Leave out the dead ends, the back-and-forth, and anything that did not end up mattering. Write it
as finished steps someone could follow cold, in plain markdown. No preamble, no sign-off, no questions — the recipe
only."""


def load_config():
    try:
        return {**DEFAULTS, **json.load(open(CONFIG))}
    except Exception:
        return dict(DEFAULTS)


def save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ tools (read-only)

class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"): self.skip += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "pre"): self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.out.append(data)


def fetch(url, limit=20000):
    if not re.match(r"https?://", url):
        return "refused: only http and https addresses"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Vintos Workbench; read-only)"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            kind = r.headers.get("Content-Type", "")
            raw = r.read(3_000_000)
    except urllib.error.HTTPError as e:
        return "HTTP %d from %s" % (e.code, url)
    except Exception as e:
        return "could not fetch %s: %s" % (url, str(e)[:200])
    text = raw.decode("utf-8", "replace")
    if "html" in kind or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        p = _Text(); p.feed(text); text = html.unescape("".join(p.out))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:limit] + ("\n...[cut at %d of %d characters]" % (limit, len(text)) if len(text) > limit else "")


def _inside(root, rel):
    path = os.path.realpath(os.path.join(root, rel))
    return path if path == os.path.realpath(root) or path.startswith(os.path.realpath(root) + os.sep) else None


def _unwrap(text):
    """The argument itself, without the brackets, quotes or backticks a model copies from a usage line
    (25 October: Gemma wrote LIST [/Users/kevin/...] and every path read as missing)."""
    text = str(text or "").strip()
    while len(text) >= 2 and text[0] + text[-1] in ("[]", "<>", "()", "``", "''", '""', "{}"):
        text = text[1:-1].strip()
    return text


def roots(cfg):
    """Where it may read: his checkout, the folders she adds in Settings (e.g. Codex's worktrees), its own code folder."""
    extra = [os.path.expanduser(r.strip()) for r in str(cfg.get("also_read") or "").split(",") if r.strip()]
    return [r for r in [cfg["repo"]] + extra + [CODE] if os.path.isdir(r)]


def where(cfg, path):
    """(root, absolute path) for a path it named: absolute inside a readable folder, code/<name>, or relative to his
    checkout; (None, None) for anything else."""
    path = _unwrap(path).rstrip("…").rstrip(",;:") or "."
    if path not in (".", "..") and path.endswith("."): path = path.rstrip(".")
    if path.startswith("~"): path = os.path.expanduser(path)
    if path.startswith("code/"): return CODE, _inside(CODE, path[5:])
    if os.path.isabs(path):
        for r in roots(cfg):
            hit = _inside(r, os.path.relpath(path, r)) if os.path.realpath(path).startswith(os.path.realpath(r)) else None
            if hit: return r, hit
        return None, None
    return cfg["repo"], _inside(cfg["repo"], path)


def _refused(cfg, path):
    return "not readable here: %s (readable: %s)" % (path, ", ".join(roots(cfg)) or "nothing yet: set his checkout in Settings")


def grep(cfg, pattern, scope=None, limit=60):
    base, glob = cfg["repo"], scope
    if scope and (os.path.isabs(scope) or scope.startswith(("~", "code/"))):
        root, base = where(cfg, scope)
        if not base: return _refused(cfg, scope)
        glob = None
        if os.path.isfile(base): base, glob = os.path.dirname(base), os.path.basename(base)
    if not os.path.isdir(base):
        return "his code is not at %s; set the checkout in Settings" % base
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return "bad regex: %s" % e
    hits = []
    for top, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(top, name); rel = os.path.relpath(path, base)
            if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(name, glob): continue
            try:
                if os.path.getsize(path) > 1_000_000: continue
                with open(path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append("%s:%d: %s" % (path if base != cfg["repo"] else rel, n, line.rstrip()[:240]))
                            if len(hits) >= limit:
                                return "\n".join(hits) + "\n...[first %d matches]" % limit
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(hits) or "no matches"


def read(cfg, rel, span=None, limit=400):
    root, path = where(cfg, rel)
    if not path: return _refused(cfg, rel)
    if not os.path.isfile(path):
        return "no such file: %s (it can look in: %s)" % (rel, ", ".join(roots(cfg)))
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except (UnicodeDecodeError, OSError) as e:
        return "cannot read %s: %s" % (rel, e)
    first, last = 1, min(len(lines), limit)
    if span:
        m = re.match(r"(\d+)\s*-\s*(\d+)", span)
        if m: first, last = int(m.group(1)), min(int(m.group(2)), int(m.group(1)) + limit - 1, len(lines))
    return "\n".join("%d\t%s" % (n, lines[n - 1]) for n in range(max(1, first), last + 1)) + (
        "\n...[%d lines in all]" % len(lines) if last < len(lines) else "")


def listing(cfg, rel=""):
    root, path = where(cfg, rel or ".")
    if not path: return _refused(cfg, rel)
    if not os.path.isdir(path):
        return "no such folder: %s (it can look in: %s)" % (rel, ", ".join(roots(cfg)))
    names = sorted(n + ("/" if os.path.isdir(os.path.join(path, n)) else "") for n in os.listdir(path) if n not in SKIP_DIRS)
    return "\n".join(names[:300]) or "(empty)"


GITHUB = re.compile(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)(?:/(blob|tree|commit)/([^\s#?]+))?/?(?:[#?]\S*)?$", re.I)


_TOKEN = {}


def _gh_token():
    """Her GitHub login as the Mac's git already keeps it (the keychain), for reading private repositories through
    GitHub's API. Used only as a request header to api.github.com; never shown, saved or sent anywhere else."""
    if "t" not in _TOKEN:
        import subprocess
        try:
            r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                               text=True, timeout=10, env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never"))
            _TOKEN["t"] = next((l[9:] for l in r.stdout.splitlines() if l.startswith("password=")), "")
        except Exception:
            _TOKEN["t"] = ""
    return _TOKEN["t"]


def _api(path):
    req = urllib.request.Request("https://api.github.com" + path, headers={"Accept": "application/vnd.github+json",
                                 "User-Agent": "Vintos-Workbench", "X-GitHub-Api-Version": "2022-11-28",
                                 **({"Authorization": "Bearer " + _gh_token()} if _gh_token() else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _his(cfg, owner, name):
    import subprocess
    repo = cfg["repo"]
    if not os.path.isdir(os.path.join(repo, ".git")): return False
    remote = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, text=True).stdout
    return ("%s/%s" % (owner, name)).lower() in remote.lower()


def fetch_link(cfg, url):
    """A link she gave. A GitHub repository, folder, file or commit is read through GitHub itself (its API, with the
    Mac's GitHub login for private ones): nothing is downloaded to keep, and every folder it shows comes with the links
    that go further. His own repository is read from his checkout on this Mac. Anything else is fetched from the web."""
    m = GITHUB.match(url or "")
    if not m:
        return fetch(url)
    owner, name = m.group(1), m.group(2).removesuffix(".git")
    if _his(cfg, owner, name):
        return _his_link(cfg, m)
    base, web = "/repos/%s/%s" % (owner, name), "https://github.com/%s/%s" % (owner, name)
    try:
        info = _api(base)
        branches = []
        for page in (1, 2, 3):
            got = _api("%s/branches?per_page=100&page=%d" % (base, page))
            branches += [b["name"] for b in got]
            if len(got) < 100: break
    except urllib.error.HTTPError as e:
        return ("GitHub answered %d for %s/%s%s" % (e.code, owner, name, " (private, and this Mac's git has no GitHub "
                "login that can read it)" if e.code == 404 and not _gh_token() else ""))
    except Exception as e:
        return "could not reach GitHub for %s/%s: %s" % (owner, name, str(e)[:200])
    kind = (m.group(3) or "tree").lower()
    if kind == "commit":
        c = _api("%s/commits/%s" % (base, m.group(4).split("/")[0]))
        return "%s commit %s by %s: %s\n%s" % (web, c["sha"][:10], c["commit"]["author"]["name"], c["commit"]["message"][:500],
               "\n".join("%s %s (+%d -%d)" % (f["status"], f["filename"], f["additions"], f["deletions"]) for f in c.get("files", [])[:100]))
    branch, path = info.get("default_branch", "main"), ""
    if m.group(4):
        parts = m.group(4).split("/")
        for i in range(len(parts), 0, -1):          # branch names may hold slashes: the longest one that exists
            if "/".join(parts[:i]) in branches:
                branch, path = "/".join(parts[:i]), "/".join(parts[i:]); break
        else:
            return "no branch of %s/%s matches %s (branches: %s)" % (owner, name, m.group(4), ", ".join(branches[:30]))
    from urllib.parse import quote
    try:
        got = _api("%s/contents/%s?ref=%s" % (base, quote(path), quote(branch, safe="")))
    except urllib.error.HTTPError as e:
        return "GitHub answered %d for %s in %s/%s, branch %s" % (e.code, path or "the top level", owner, name, branch)
    head = "%s/%s, branch %s%s" % (owner, name, branch, (", " + path) if path else "")
    if isinstance(got, list):
        rows = ["%s%s  %s/%s/%s/%s" % (e["name"], "/" if e["type"] == "dir" else "", web, "tree" if e["type"] == "dir" else "blob",
                                        branch, e["path"]) for e in got[:300]]
        top = ("Branches: %s\n\n" % ", ".join(branches[:40])) if not path else ""
        return "%s:\n%s%s\n\nTo go further, FETCH any link above." % (head, top, "\n".join(rows))
    import base64
    text = base64.b64decode(got.get("content") or "").decode("utf-8", "replace") if got.get("encoding") == "base64" else ""
    if not text and got.get("download_url"):
        text = fetch(got["download_url"])
    return "%s:\n%s" % (head, text[:20000] + ("\n...[cut]" if len(text) > 20000 else ""))


def _his_link(cfg, m):
    """His own repository, from his checkout on this Mac (it is already here; nothing new is downloaded but the branch)."""
    import subprocess
    repo = cfg["repo"]
    run = lambda *a, **k: subprocess.run(["git", "-C", repo] + list(a), capture_output=True, text=True,
                                         timeout=k.get("timeout", 60), env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    known = sorted(l.split("refs/heads/", 1)[1] for l in run("ls-remote", "--heads", "origin").stdout.splitlines() if "refs/heads/" in l)
    go = lambda b: ("\n\nTo go further in branch {b}: GIT ls-tree --name-only origin/{b} <folder>/ lists a folder, "
                    "GIT show origin/{b}:<path> reads a file, GIT log --oneline -10 origin/{b} shows its commits.").format(b=b)
    if not m.group(3):
        return "His repository. Branches: %s\n\nTop level:\n%s%s" % (", ".join(known) or "none read", listing(cfg, "."), go("<branch>"))
    kind, rest = m.group(3).lower(), m.group(4)
    if kind == "commit":
        return git(cfg, "show --stat %s" % rest.split("/")[0])
    parts = rest.split("/")
    for i in range(len(parts), 0, -1):
        branch, path = "/".join(parts[:i]), "/".join(parts[i:])
        if branch not in known or run("fetch", "-q", "origin", branch).returncode: continue
        if kind == "tree":
            listed = git(cfg, "ls-tree --name-only origin/%s %s" % (branch, (path.rstrip("/") + "/") if path else "")).strip()
            return "his repository, branch %s, %s:\n%s%s" % (branch, path or "top level", listed or "(empty)", go(branch))
        r = run("--no-pager", "show", "origin/%s:%s" % (branch, path), timeout=30)
        out = (r.stdout or r.stderr).strip()
        return "his repository, branch %s, %s:\n%s%s" % (branch, path, out[:20000] + ("\n...[cut]" if len(out) > 20000 else ""), go(branch))
    return "no branch of his repository matches %s" % rest


URL = re.compile(r"https?://[^\s<>\"')\]]+")


COMMON_PORTS = [22, 80, 135, 139, 443, 445, 515, 548, 631, 1883, 3000, 3389, 5000, 5357, 5900, 7860, 8000, 8080, 8443, 9100, 62078]
PORT_NAME = {22: "ssh", 80: "http", 135: "rpc", 139: "netbios", 443: "https", 445: "smb", 515: "printer", 548: "afp",
             631: "ipp", 1883: "mqtt", 3389: "rdp", 5000: "http", 5357: "wsd", 5900: "vnc", 7860: "http", 8000: "http",
             8080: "http", 8443: "https", 9100: "printer", 62078: "iphone"}


def _local_ipv4():
    import socket as _s
    try:
        u = _s.socket(_s.AF_INET, _s.SOCK_DGRAM); u.connect(("8.8.8.8", 80))
        ip = u.getsockname()[0]; u.close(); return ip
    except Exception:
        return ""


def _poke(ip, port, timeout=0.7):
    return _poke_status(ip, port, timeout) == "open"


def _poke_status(ip, port, timeout=0.7):
    """open (a service answered), closed (the host refused — nothing there), or filtered (no reply — a firewall is
    dropping it, and a service could be hidden behind it)."""
    import socket as _s, errno
    c = _s.socket(_s.AF_INET, _s.SOCK_STREAM); c.settimeout(timeout)
    try:
        rc = c.connect_ex((ip, port))
        if rc == 0: return "open"
        return "closed" if rc in (errno.ECONNREFUSED, errno.ECONNRESET) else "filtered"
    except (_s.timeout, OSError):
        return "filtered"
    finally:
        c.close()


def _arp_table():
    import subprocess
    out = {}
    try:
        text = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return out
    for line in text.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)", line)
        if m and "incomplete" not in line:
            mac = m.group(2).lower()
            if mac.count(":") == 5:
                out[m.group(1)] = mac
    return out


def _gateway():
    import subprocess
    try:
        for line in subprocess.run(["netstat", "-rn"], capture_output=True, text=True, timeout=8).stdout.splitlines():
            if line.split()[:1] == ["default"]:
                return line.split()[1]
    except Exception:
        pass
    return ""


def _rdns(ip):
    import socket as _s
    old = _s.getdefaulttimeout(); _s.setdefaulttimeout(0.6)
    try:
        return _s.gethostbyaddr(ip)[0]
    except Exception:
        return ""
    finally:
        _s.setdefaulttimeout(old)


def _bt_le_scan(seconds=6):
    """A short Bluetooth-LE scan via CoreBluetooth, when this Mac's Python has pyobjc. Returns a list of nearby
    devices (name, identifier, RSSI) or a reason it could not scan. Never raises."""
    try:
        import objc  # noqa
        from CoreBluetooth import CBCentralManager
        from Foundation import NSObject, NSRunLoop, NSDate
    except Exception:
        return "live scan needs pyobjc (not on this Mac's Python); showing paired/known devices only"
    found = {}
    class D(NSObject):
        def centralManagerDidUpdateState_(self, c):
            if c.state() == 5: c.scanForPeripheralsWithServices_options_(None, None)
        def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(self, c, per, adv, rssi):
            key = str(per.identifier().UUIDString())
            nm = (adv.get("kCBAdvDataLocalName") or per.name() or "")
            found[key] = {"name": str(nm), "id": key, "rssi": int(rssi)}
    try:
        d = D.alloc().init()
        mgr = CBCentralManager.alloc().initWithDelegate_queue_(d, None)  # noqa
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
        try: mgr.stopScan()
        except Exception: pass
    except Exception as e:
        return "live scan could not run (%s); showing paired/known devices only" % str(e)[:120]
    return sorted(found.values(), key=lambda x: -x["rssi"])


def discover_bluetooth(cfg, arg=""):
    """Investigate Bluetooth from this Mac: the Mac's own radio, every paired or connected device (the Acer shows here
    if it has ever paired or is connected), each with its address, whether it is connected, and its signal; plus a
    short live scan for nearby advertising devices when this Mac's Python can do it. Read-only."""
    import subprocess
    out = ["== Bluetooth on this Mac =="]
    try:
        text = subprocess.run(["system_profiler", "SPBluetoothDataType"], capture_output=True, text=True, timeout=25).stdout.strip()
    except Exception as e:
        text = ""
        out.append("could not read system Bluetooth: %s" % str(e)[:120])
    if text:
        # keep it readable: the controller block and each device with its address/connection/RSSI
        keep, device = [], False
        for line in text.splitlines():
            low = line.strip().lower()
            if any(k in low for k in ("address:", "connected:", "rssi", "services:", "minor type", "vendor", "firmware",
                                      "state:", "discoverable", "device type", "paired")) or line.endswith(":"):
                keep.append(line.rstrip())
        out.append("\n".join(keep[:200]) or text[:4000])
    live = _bt_le_scan()
    out.append("\n== Nearby devices advertising right now ==")
    if isinstance(live, str):
        out.append(live)
    elif live:
        out += ["  %-32s  RSSI %4d  %s" % ((d["name"] or "(no name)")[:32], d["rssi"], d["id"]) for d in live[:40]]
    else:
        out.append("no devices were advertising in the scan window")
    out.append("\nTo reach the Acer over Bluetooth it must be paired (or in pairing mode). A never-paired, non-"
               "advertising device will not appear until it is made discoverable on the Acer, or paired once in the "
               "Mac's Bluetooth settings. Classic-Bluetooth devices that are paired already show above with their address.")
    return "\n".join(out)


def _probe_one(ip, ports, me, gw):
    """Look closely at one device: which ports are open, which are refused, which are firewalled (dropped). A machine
    whose ports are mostly 'filtered' is alive but behind a firewall that is swallowing the probes — a service may be
    there and simply blocked, which is different from 'nothing is listening'."""
    import concurrent.futures
    status = {}
    def one(port): status[port] = _poke_status(ip, port, 0.8)
    with concurrent.futures.ThreadPoolExecutor(max_workers=120) as pool:
        list(pool.map(one, ports))
    openp = sorted(p for p, st in status.items() if st == "open")
    filt = sorted(p for p, st in status.items() if st == "filtered")
    closed = sorted(p for p, st in status.items() if st == "closed")
    mac = _arp_table().get(ip, "")
    name = _rdns(ip)
    lines = ["%s%s%s%s" % (ip, ("  " + mac) if mac else "", ("  " + name) if name else "",
                           "  ← this Mac" if ip == me else "  ← router" if ip == gw else "")]
    lines.append("  alive: %s" % ("yes (MAC %s)" % mac if mac else "no ARP entry — may be off or on another subnet"))
    lines.append("  OPEN   : %s" % (", ".join("%d/%s" % (p, PORT_NAME.get(p, "?")) for p in openp) or "none"))
    lines.append("  closed : %s" % (("%d ports actively refused (the host says nothing is there)" % len(closed)) if closed else "none"))
    lines.append("  firewalled: %s" % (("%d ports dropped with no reply — a firewall is swallowing probes; a service "
                 "could be hidden behind it" % len(filt)) if filt else "none"))
    if filt and not openp:
        lines.append("  → it answers at the network layer but its firewall is dropping connections. Nothing here can "
                     "reach a service until that machine allows it, or it opens an outbound/paired channel instead.")
    elif openp:
        lines.append("  → connect to an OPEN port above.")
    else:
        lines.append("  → every port actively refused: it is up but genuinely running no TCP service.")
    return "\n".join(lines)


def discover_hosts(cfg, arg=""):
    """Every device alive on her network, by IP and MAC, with the services each one answers on. Finds a Windows laptop
    (the Acer) that ignores ping, because it pokes a TCP port (which makes the host answer ARP at the network layer,
    firewall or not) and then reads the Mac's ARP table. Her own tool, not model-written code: bounded and read-only.

    HOSTS                      list the network
    HOSTS <ip>                 look only at that one device, across more ports
    HOSTS ports=8080,5000      sweep with these ports (e.g. the one your Acer service listens on)"""
    import concurrent.futures, socket as _s
    arg = _unwrap(arg).strip()
    me = _local_ipv4()
    if not me or me.count(".") != 3:
        return "could not read this Mac's network address"
    sub = me.rsplit(".", 1)[0]
    ports = COMMON_PORTS
    m = re.search(r"ports?\s*=\s*([\d, ]+)", arg)
    if m:
        ports = [int(x) for x in re.findall(r"\d+", m.group(1))][:40] or COMMON_PORTS
    one = re.match(r"(\d+\.\d+\.\d+\.\d+)$", arg)
    if one:
        ports = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else \
                sorted(set(COMMON_PORTS + [21, 23, 25, 111, 1433, 2049, 3306, 5432, 5555, 8888, 9000]))
        return _probe_one(one.group(1), ports, me, _gateway())
    targets = ["%s.%d" % (sub, i) for i in range(1, 255)]
    found = {}
    def scan(ip):
        opens = []
        for port in ports:
            if _poke(ip, port, 0.7 if one else 0.3):
                opens.append(port)
        if opens:
            found[ip] = opens
    with concurrent.futures.ThreadPoolExecutor(max_workers=200) as pool:
        list(pool.map(scan, targets))
    arp = _arp_table()
    gw = _gateway()
    rows, ips = [], sorted(set(list(found) + list(arp)) if not one else [one.group(1)],
                           key=lambda x: int(x.rsplit(".", 1)[-1]))
    for ip in ips:
        mac = arp.get(ip, "")
        opens = found.get(ip, [])
        if not mac and not opens and not one:
            continue
        name = _rdns(ip)
        tag = " ← this Mac" if ip == me else " ← router" if ip == gw else ""
        svc = ", ".join("%d/%s" % (p, PORT_NAME.get(p, "?")) for p in opens) or ("no common port open" if mac else "quiet")
        rows.append("%-15s  %-17s  %-22s  %s%s" % (ip, mac or "(no MAC yet)", (name or "")[:22], svc, tag))
    head = ("Devices on %s.0/24 (this Mac is %s).\n"
            "IP               MAC                Name                    Services open\n"
            "%s\n" % (sub, me, "-" * 78))
    note = ("\n\nFind your Acer by its MAC: on the Acer run  ipconfig /all  and match the Physical Address. A Windows PC "
            "often shows no name here and may answer on no common port; its MAC still appears once it is awake and has "
            "been on the network. If your Acer service uses a particular port, run  HOSTS ports=<that port>  to spot it.")
    return head + ("\n".join(rows) or "no other devices answered — is Wi-Fi the same network as the Acer?") + (note if not one else "")


# inherently read-only subcommands: their positional arguments are refs or paths, never a mutating action
GIT_READONLY = {"log", "show", "diff", "status", "ls-tree", "grep", "rev-parse", "describe", "shortlog", "blame"}
GIT_SUBS = GIT_READONLY | {"branch"}
# options that could write a file or run an external program, rejected on every subcommand
GIT_ESCAPE = re.compile(r"^(?:-o|--output(=.*)?|--exec(=.*)?|--upload-pack(=.*)?|--receive-pack(=.*)?|--ext-diff|--textconv)$")
# `branch` is list-only here: only these (read/list) flags, and never a branch name, so it cannot create, rename,
# delete, move, copy, force, or change upstream (Chat, 24 October: -D, -m and a bare name slipped through before)
GIT_BRANCH_LIST = re.compile(r"^(?:-a|--all|-r|--remotes|-v|-vv|--verbose|-l|--list|--show-current|-q|--quiet|"
                             r"--color(=.*)?|--no-color|--column(=.*)?|--no-column|--sort=.*|--points-at(=.*)?|"
                             r"--contains(=.*)?|--no-contains(=.*)?|--merged(=.*)?|--no-merged(=.*)?|--format=.*)$")


def git(cfg, arg):
    """Read-only git in a readable folder: GIT [in <folder>] <log|show|diff|branch|...> <args>. Never writes."""
    import shlex, subprocess, tempfile
    try:
        words = shlex.split(arg)
    except ValueError as e:
        return "could not read the git line: %s" % e
    folder = cfg["repo"]
    if len(words) >= 2 and words[0] == "in":
        root, folder = where(cfg, words[1]); words = words[2:]
        if not folder: return _refused(cfg, arg.split()[1])
    if not words or words[0] not in GIT_SUBS:
        return "only read-only git here: %s, and branch (list-only)" % ", ".join(sorted(GIT_READONLY))
    sub, args = words[0], words[1:]
    if any(GIT_ESCAPE.match(w) for w in args):
        return "that git option is not allowed here (it could write a file or run a program)"
    if sub == "branch":
        for w in args:
            if not w.startswith("-"):
                return "GIT branch only lists branches here; it will not create, rename or delete one"
            if not GIT_BRANCH_LIST.match(w):
                return "GIT branch is list-only here; '%s' could change a branch and is refused" % w
        if not args:
            args = ["-a"]
    cmd = ["git", "-C", folder, "--no-pager", "-c", "core.pager=cat", sub]
    if sub in ("log", "show", "diff"): cmd += ["--no-ext-diff", "--no-textconv"]
    words = [sub] + args
    try:
        r = subprocess.run(cmd + words[1:], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return "git did not run: %s" % str(e)[:200]
    out = (r.stdout or r.stderr or "(nothing)").strip()
    return out[:20000] + ("\n...[cut]" if len(out) > 20000 else "")


def _clean_name(name):
    """A tidy filename from whatever the model wrote: strip quotes/backticks/brackets, drop any other stray character
    (so `udp_probe.py` or udp_probe.py<junk> never becomes udp_probe.py_), collapse spaces, keep the real extension."""
    name = os.path.basename(_unwrap(str(name or "")).strip())
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)   # drop junk entirely, never turn it into an underscore
    name = name.strip("_.-")                       # trim edge punctuation, but a trailing .py is kept (ends in a letter)
    return name[:120] or "untitled.txt"


def save_code(name, code):
    """Write code/<name>, its one working file, keeping the previous version in code/.history so an edit loop never
    loses a good draft. A plain file, inside the code folder only."""
    name = _clean_name(name)
    os.makedirs(CODE, exist_ok=True)
    path = os.path.join(CODE, name)
    if os.path.exists(path):   # keep the version it is replacing, so an edit loop never loses a good draft
        os.makedirs(CODE_HISTORY, exist_ok=True)
        stem, ext = os.path.splitext(name)
        try:
            with open(path, "rb") as a, open(os.path.join(CODE_HISTORY, "%s.%s%s" % (stem, time.strftime("%Y%m%d-%H%M%S"), ext)), "wb") as b:
                b.write(a.read())
        except OSError:
            pass
    tmp = os.path.join(CODE, ".%s.%d.tmp" % (name, os.getpid()))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code if code.endswith("\n") else code + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return path


INTERP = {".py": "python3", ".sh": "bash", ".js": "node", ".ts": "node", ".rb": "ruby", ".pl": "perl", "": "python3"}
RUN_TIMEOUT_S = 30
RUN_OUTPUT_CAP = 16000

SANDBOX = """(version 1)
(allow default)
(deny file-write*)
(allow file-write* (subpath "%(code)s") (subpath "%(scratch)s") (subpath "%(tmp)s") (subpath "/private/var/folders"))
(allow file-write-data (literal "/dev/null") (regex #"^/dev/(stdout|stderr|tty|dtracehelper)"))
%(net)s"""


def run_code(cfg, arg):
    """Run code/<file> and return its output and errors, so the model can fix it and run it again. It may use the
    network (so its code can find and reach machines on Gloria's network, like her Acer laptop) and read the Mac, but
    it may only WRITE inside the code folder and a throwaway run folder: everything it builds stays contained there.
    Turn 'run code offline' on in Settings to take the network away."""
    import shlex, subprocess, tempfile
    words = [w for w in (shlex.split(_unwrap(arg)) if arg else []) if w not in ("--net", "--network", "--offline")]
    name = _clean_name(words[0]) if words else ""
    path = _inside(CODE, name)
    if not name or not path or not os.path.isfile(path):
        return "no such saved file: code/%s — SAVE it first, then RUN it" % (name or "?")
    interp = INTERP.get(os.path.splitext(path)[1].lower())
    if not interp:
        return "I only run .py, .sh, .js, .ts, .rb or .pl files here"
    offline = bool(cfg.get("offline_runs"))
    os.makedirs(RUNS, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="run-", dir=RUNS)
    cmd = [interp, path]
    sandboxed = False
    if os.path.exists("/usr/bin/sandbox-exec"):
        profile = SANDBOX % {"code": os.path.realpath(CODE), "scratch": os.path.realpath(scratch),
                             "tmp": os.path.realpath(tempfile.gettempdir()),
                             "net": "(deny network*)" if offline else ""}
        cmd = ["/usr/bin/sandbox-exec", "-p", profile] + cmd
        sandboxed = True
    try:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER")}
        done = subprocess.run(cmd, cwd=scratch, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env)
        out = ((done.stdout or "") + (("\n--- errors ---\n" + done.stderr) if done.stderr.strip() else "")).strip()
        head = "ran code/%s%s%s, exit %d%s" % (name, " (offline)" if offline else "",
               "" if sandboxed else " — NOT sandboxed on this Mac (sandbox-exec missing)", done.returncode,
               "" if done.returncode == 0 else "  ← it failed; read the errors and SAVE a fix")
        return "%s\n%s" % (head, out[:RUN_OUTPUT_CAP] + ("\n...[output cut]" if len(out) > RUN_OUTPUT_CAP else "") or "(no output)")
    except subprocess.TimeoutExpired:
        return "code/%s ran longer than %d seconds and was stopped (a loop, or it is waiting on something)." % (name, RUN_TIMEOUT_S)
    except FileNotFoundError:
        return "cannot run code/%s: %s is not installed on this Mac" % (name, interp)
    except Exception as e:
        return "could not run code/%s: %s" % (name, str(e)[:200])
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


# a tool line, however the model dressed it: `LIST x`, - GREP y, 1. READ z, **GIT log** (25 October: Gemma wrote
# "`LIST /Users/kevin/...`" in backticks and nothing ran)
TOOL = re.compile(r"^[ \t>*\-`]*(?:\d+[.)][ \t]*)?[*`]*(FETCH|GREP|READ|LIST|GIT|RUN|HOSTS|SCAN|BT|BLUETOOTH)\b[*`]*[ \t:]*(.*?)[*`]*[ \t]*$", re.M)
SAVE = re.compile(r"^\s*SAVE[ \t]+(\S+)[^\n]*\n(?:.*?\n)??\s*```[^\n]*\n(.*?)\n\s*```", re.M | re.S)


VERBS = {"fetch": "FETCH", "grep": "GREP", "read": "READ", "list": "LIST", "git": "GIT", "save": "SAVE", "run": "RUN",
         "hosts": "HOSTS", "scan": "HOSTS", "bt": "BT", "bluetooth": "BT"}
NATIVE = re.compile(r"(?:<\|?tool_call\|?>|<tool_call>)?\s*call:\s*([A-Za-z_]+)\s*(\{.*?\}(?=\s*(?:<\|?/?tool_call\|?>|<tool_call\|>|END|$))|[^\n]*)", re.S)


def native_lines(reply):
    """A model's own tool-call syntax turned into the Workbench's lines (25 October: Gemma wrote
    "<|tool_call>call:LIST [/Users/kevin/...]END", its native form, and nothing ran). Handles call:NAME args and
    call:name{key:value,...}, with Gemma's <|"|> quotes."""
    text = reply.replace('<|"|>', '"')
    lines = []
    for name, args in NATIVE.findall(text):
        verb = VERBS.get(name.lower())
        if not verb: continue
        args = re.sub(r"(?:<\|?/?tool_call\|?>|<tool_call\|>|\bEND)\s*$", "", args.strip()).strip()
        if args.startswith("{"):
            body = args[1:-1] if args.endswith("}") else args[1:]
            try:
                values = list(json.loads("{" + body + "}").values())
            except ValueError:
                values = [v.strip().strip('"') for v in re.findall(r'\w+\s*:\s*("[^"]*"|[^,]+)', body)]
            if verb == "SAVE" and len(values) >= 2:
                lines.append("SAVE %s\n```\n%s\n```" % (values[0], values[1])); continue
            args = " ".join(str(v) for v in values)
        lines.append("%s %s" % (verb, args))
    return "\n".join(lines)


def run_tools(reply, cfg):
    """The results of every lookup line in a reply, or '' when it asked for none."""
    out = []
    reply = reply + "\n" + native_lines(reply)
    for verb, arg in list(dict.fromkeys(TOOL.findall(reply)))[:6]:
        arg = _unwrap(arg)
        if verb == "FETCH":
            result = fetch_link(cfg, _unwrap(arg.split()[0]) if arg else "")
        elif verb == "GREP":
            m = re.match(r"(.*?)\s+in\s+(\S+)$", arg)
            pattern, scope = (m.groups() if m else (arg, None))
            result = grep(cfg, _unwrap(pattern), _unwrap(scope) if scope else None)
        elif verb == "READ":
            parts = arg.split()
            result = read(cfg, _unwrap(parts[0]) if parts else "", _unwrap(parts[1]) if len(parts) > 1 else None)
        elif verb == "GIT":
            result = git(cfg, arg)
        elif verb == "RUN":
            result = run_code(cfg, arg)
        elif verb == "HOSTS":
            result = discover_hosts(cfg, arg)
        elif verb == "BT":
            result = discover_bluetooth(cfg, arg)
        else:
            result = listing(cfg, arg)
        out.append("=== %s %s ===\n%s" % (verb, arg, result))
    return "\n\n".join(out)


def do_saves(reply):
    reply = reply + "\n" + native_lines(reply)
    return [save_code(name, code) for name, code in dict.fromkeys(SAVE.findall(reply))]


# ------------------------------------------------------------------------------------------------ the model

def models(cfg):
    try:
        with urllib.request.urlopen(cfg["base_url"].rstrip("/") + "/models", timeout=8) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except Exception as e:
        return {"error": str(e)[:200]}


def loaded_models(cfg):
    """The models LM Studio has in memory now (its own /api/v0/models says which); [] when it cannot say."""
    base = re.sub(r"/v1/?$", "", cfg["base_url"].rstrip("/"))
    try:
        with urllib.request.urlopen(base + "/api/v0/models", timeout=8) as r:
            return [m["id"] for m in json.load(r).get("data", []) if m.get("state") == "loaded"]
    except Exception:
        return []


def _fn(name, about, **params):
    return {"type": "function", "function": {"name": name, "description": about, "parameters": {
        "type": "object", "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
        "required": list(params)[:1]}}}


TOOLS = [_fn("fetch", "Read a web page, or a GitHub repository, folder, file or commit link", url="the link"),
         _fn("grep", "Search code (read-only) for a regular expression", pattern="the regex",
             scope="optional: a glob like scripts/*.py, or a readable folder"),
         _fn("read", "Read a file", path="its path", lines="optional: first-last, e.g. 40-120"),
         _fn("list", "List a folder", folder="its path; . for his checkout's top"),
         _fn("git", "Read-only git", command="e.g. log --oneline -10, or in <folder> show <rev>:<path>"),
         _fn("save", "Save code to your working folder (prior version kept)", filename="the file name", code="the whole file"),
         _fn("run", "Run a file you saved and get its output/errors; it may use the network but writes only in your folder", filename="code/<name>"),
         _fn("hosts", "List devices on Gloria's network; HOSTS <ip> shows a device's open/closed/firewalled ports", target="optional: an IP to inspect, or ports=8080,5000"),
         _fn("bt", "Investigate Bluetooth: the Mac's radio, paired/connected devices (incl. the Acer if paired), and nearby advertisers", note="no argument needed")]


def _as_lines(message):
    """The answer's text, with any native tool calls written as Workbench lines so they run the same way."""
    out = [message.get("content") or ""]
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        verb = VERBS.get(str(fn.get("name", "")).lower())
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        if not verb: continue
        if verb == "SAVE":
            out.append("SAVE %s\n```\n%s\n```" % (args.get("filename", "untitled.txt"), args.get("code", "")))
        elif verb == "GREP":
            out.append("GREP %s%s" % (args.get("pattern", ""), (" in " + args["scope"]) if args.get("scope") else ""))
        else:
            out.append("%s %s" % (verb, " ".join(str(v) for v in args.values())))
    return "\n".join(x for x in out if x)


def complete(cfg, messages):
    """The model's answer. Its tools are offered natively (LM Studio passes them to Gemma in Gemma's own format and
    returns tool_calls); a server that refuses tools is asked again without them, and the text lines still work."""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = {"model": cfg["model"], "messages": messages, "max_tokens": int(cfg["max_tokens"]),
            "temperature": float(cfg["temperature"]), "stream": False, "tools": TOOLS}
    for attempt in (0, 1):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                return _as_lines(json.load(r)["choices"][0]["message"])
        except urllib.error.HTTPError as e:
            if attempt or e.code not in (400, 422): raise
            body.pop("tools", None)


def fitted(messages, limit):
    """System prompt and the newest turns that fit; the oldest go first. The thread file keeps everything."""
    system, rest = messages[0], messages[1:]
    kept, size = [], len(system["content"])
    for m in reversed(rest):
        size += len(m["content"])
        if size > limit and kept: break
        kept.insert(0, m)
    return [system] + kept


def thread_path(tid):
    return os.path.join(THREADS, re.sub(r"[^A-Za-z0-9-]", "", tid) + ".json")


def load_thread(tid):
    try:
        return json.load(open(thread_path(tid)))
    except Exception:
        return {"id": tid, "title": "", "created": time.strftime("%Y-%m-%d %H:%M"), "messages": []}


def direct_tool(text):
    """When Gloria types a tool command herself (HOSTS, LIST x, RUN foo.py, ...), the Workbench runs it directly and
    shows the result — no model in the way, so it works even when Gemma is fumbling or the model server is down."""
    line = str(text or "").strip()
    if "\n" in line:
        return None
    parts = line.split(None, 1)
    first = parts[0].upper() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    # her own command only when it is the verb alone or with a single argument (an IP, a path, a flag, ports=...),
    # never a sentence like "run the tests" or "read the handoff"
    if first in ("FETCH", "GREP", "READ", "LIST", "GIT", "RUN", "HOSTS", "SCAN", "BT", "BLUETOOTH") and (not rest or " " not in rest):
        return {"SCAN": "HOSTS", "BLUETOOTH": "BT"}.get(first, first) + ((" " + rest) if rest else "")
    return None


def write_success(headline, recipe, th):
    """Append one clean entry to the local successes log, newest on top. Written atomically; never leaves the Mac."""
    entry = "## %s — %s\n\n%s\n\n_thread: %s (%s)_\n\n---\n" % (
        time.strftime("%Y-%m-%d %H:%M"), headline, recipe.strip(), th.get("title") or "?", th.get("id") or "?")
    header = ("# Successes — local only\n\nWhat worked on this Mac, kept apart from the messy threads. This file is "
              "never committed, pushed, or deployed; it lives only here. Newest entry on top.\n\n---\n")
    with LOCK:
        try:
            old = open(SUCCESSES, encoding="utf-8").read()
        except OSError:
            old = ""
        if "---\n" in old:
            i = old.index("---\n") + len("---\n")
            new = old[:i] + "\n" + entry + old[i:]
        else:
            new = header + "\n" + entry
        tmp = SUCCESSES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, SUCCESSES)
    return SUCCESSES


def parse_successes():
    """Read successes.md and return a list of entries, newest first. Each entry is {headline, recipe, thread, at}."""
    try:
        text = open(SUCCESSES, encoding="utf-8").read()
    except OSError:
        return []
    entries = []
    for block in re.split(r"\n---\n", text):
        m = re.match(r"\s*##\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*[—–-]\s*(.*)", block)
        if not m:
            continue
        at, headline = m.group(1), m.group(2).strip()
        body = block[m.end():].strip()
        th_m = re.search(r"_thread:\s*(.+?)\s*\(([^)]+)\)_\s*$", body)
        thread_title, thread_id = (th_m.group(1), th_m.group(2)) if th_m else ("", "")
        recipe = body[:th_m.start()].strip() if th_m else body
        entries.append({"at": at, "headline": headline, "recipe": recipe, "thread_title": thread_title, "thread_id": thread_id})
    return entries


def mark_success(th, headline, cfg, model_call=complete):
    """Gloria typed !success: the model distils what worked in this thread into a clean recipe, and the Workbench saves
    it to the local successes log. Gemma writes the prose; the Workbench does the saving, so the save never depends on
    Gemma getting a tool call right."""
    if not any(m.get("role") == "assistant" and not m.get("tool") for m in th["messages"]):
        return "Nothing to save yet — !success keeps what worked in this thread, but this thread has no results in it."
    convo = [{"role": "system", "content": DISTILL}] + \
            [{"role": m["role"], "content": m["content"]} for m in th["messages"]
             if not str(m.get("content", "")).strip().lower().startswith("!success")]
    convo.append({"role": "user", "content": "Write the success recipe now." +
                  ((" Gloria's note on what succeeded: " + headline) if headline else "")})
    try:
        recipe = str(model_call(cfg, fitted(convo, int(cfg["context_chars"]))) or "").strip()
    except Exception:
        recipe = ""
    note = ""
    if not recipe:   # the model fumbled or the server is down: keep the last real answer verbatim so the win is not lost
        recipe = next((str(m["content"]).strip() for m in reversed(th["messages"])
                       if m.get("role") == "assistant" and not m.get("tool")), "")
        note = "  (the model could not distil it; saved the last answer as-is — edit the file if it is off)"
    head = (headline or th.get("title") or "Untitled").strip().splitlines()[0][:80] if (headline or th.get("title")) else "Untitled"
    where = write_success(head, recipe, th)
    return "SAVED a success — \"%s\" -> %s%s\n\n%s" % (
        head, where, note, recipe[:1500] + ("\n..." if len(recipe) > 1500 else ""))


def turn(tid, text, cfg, model_call=complete):
    """Her message in, the model's answer out, with as many lookup rounds as it asks for (up to tool_rounds)."""
    with LOCK:
        th = load_thread(tid)
    th["messages"].append({"role": "user", "content": text, "at": time.strftime("%H:%M")})
    if not th.get("title"): th["title"] = text.strip().splitlines()[0][:60] if text.strip() else "Untitled"
    if text.strip().lower().startswith("!success"):   # she marks the win; the model writes the recipe, we save it local
        headline = text.strip()[len("!success"):].strip()
        th["messages"].append({"role": "user", "tool": True, "at": time.strftime("%H:%M"),
                               "content": mark_success(th, headline, cfg, model_call)})
        th["working"] = False
        with LOCK:
            save_json(thread_path(tid), th)
        return {"thread": th, "saved": []}
    cmd = direct_tool(text)
    if cmd:
        th["messages"].append({"role": "user", "tool": True, "at": time.strftime("%H:%M"),
                               "content": run_tools(cmd, cfg) or "(the command produced nothing)"})
        th["working"] = False
        with LOCK:
            save_json(thread_path(tid), th)
        return {"thread": th, "saved": do_saves(cmd)}
    links = list(dict.fromkeys(u.rstrip(".,;:") for u in URL.findall(text)))[:3]
    if links:   # the links she gave are read for it before it answers (25 October: it never asked to FETCH them)
        th["messages"].append({"role": "user", "tool": True, "at": time.strftime("%H:%M"),
                               "content": "LINKS GLORIA GAVE (read by the Workbench):\n\n" +
                                          "\n\n".join("=== %s ===\n%s" % (u, fetch_link(cfg, u)) for u in links)})
    def flush(working=True):
        th["working"] = working
        with LOCK:
            save_json(thread_path(tid), th)
    flush()                                   # her message (and any links) show at once, before the model is asked
    shown, saved = [], []
    for _ in range(int(cfg["tool_rounds"]) + 1):
        system = SYSTEM + "\n\nReadable folders: %s. His checkout (relative paths start here): %s." % (
            ", ".join(roots(cfg)) or "none yet", cfg["repo"])
        msgs = fitted([{"role": "system", "content": system}] +
                      [{"role": m["role"], "content": m["content"]} for m in th["messages"]], int(cfg["context_chars"]))
        try:
            reply = model_call(cfg, msgs)
        except Exception as e:
            reply = "(the model did not answer: %s)" % str(e)[:300]
        th["messages"].append({"role": "assistant", "content": reply, "at": time.strftime("%H:%M"), "model": cfg["model"]})
        shown.append(reply); saved += do_saves(reply)
        results = run_tools(reply, cfg)
        if results:
            th["messages"].append({"role": "user", "content": "TOOL RESULTS (from the Workbench, not from Gloria):\n" + results,
                                   "at": time.strftime("%H:%M"), "tool": True})
            shown.append("[looked up]\n" + results[:4000] + ("\n..." if len(results) > 4000 else ""))
        flush(bool(results))                  # each round is saved, so the page shows it the moment it lands
        if not results: break
    if saved:
        th["messages"].append({"role": "user", "content": "SAVED (by the Workbench): " + ", ".join(saved), "tool": True,
                               "at": time.strftime("%H:%M")})
    flush(False)
    return {"thread": th, "saved": saved}


# ------------------------------------------------------------------------------------------------ the page

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workbench</title><style>
:root{--bg:#fbfaf7;--fg:#1d1b18;--mut:#6d675f;--line:#e4dfd6;--card:#fff;--acc:#3d5a80;--tool:#f1eee8}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8e1;--mut:#9a948b;--line:#2c2a26;--card:#1f1d1a;--acc:#9cb8dc;--tool:#25231f}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg);display:flex;height:100vh}
aside{width:250px;border-right:1px solid var(--line);padding:12px;overflow:auto;flex-shrink:0}main{flex:1;display:flex;flex-direction:column;min-width:0}
button,select,input,textarea{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
button{cursor:pointer}.t{display:block;width:100%;text-align:left;margin:4px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t.on{border-color:var(--acc)}#log{flex:1;overflow:auto;padding:16px 20px}.m{max-width:900px;margin:0 0 14px}.who{font-size:12px;color:var(--mut)}
.b{white-space:pre-wrap;word-wrap:break-word;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tool .b{background:var(--tool);font:12px/1.4 ui-monospace,Menlo,monospace;max-height:260px;overflow:auto}
form{display:flex;gap:8px;padding:12px 20px;border-top:1px solid var(--line)}textarea{flex:1;min-height:60px;resize:vertical}
#bar{display:flex;gap:8px;align-items:center;padding:8px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}.mut{color:var(--mut);font-size:13px}
#menu{display:none}
.modal{display:none;position:fixed;inset:0;z-index:10;background:rgba(0,0,0,.5);align-items:center;justify-content:center}
.modal.open{display:flex}.modal-box{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:20px;max-width:600px;width:90%;max-height:80vh;overflow:auto}
.modal-box h3{margin:0 0 12px}.suc{display:block;width:100%;text-align:left;margin:6px 0;padding:10px 12px;cursor:pointer}
.suc:hover{border-color:var(--acc)}.suc .sh{font-weight:600}.suc .sd{font-size:13px;color:var(--mut);margin-top:4px;white-space:pre-wrap;max-height:80px;overflow:hidden}
@media (max-width:700px){body{display:block;height:100dvh}main{height:100dvh}aside{display:none;position:fixed;inset:0;z-index:5;width:auto;background:var(--bg)}
 aside.open{display:block}#menu{display:inline-block}#log{padding:12px}form{padding:8px 12px;padding-bottom:max(8px,env(safe-area-inset-bottom))}
 #bar{padding:8px 12px}textarea{font-size:16px;min-height:48px}.m{max-width:100%}select{max-width:60vw}}
</style></head><body>
<aside id="side"><button onclick="newThread()">+ New thread</button> <button onclick="fromSuccess()">From success</button> <button id="close" onclick="side(false)">Close</button><div id="threads"></div>
<p class="mut">Code it saves: ~/Vintos-Workbench/code</p><p class="mut">Type <b>!success</b> to keep what worked in this thread → ~/Vintos-Workbench/successes.md (local only)</p><details><summary class="mut">Settings</summary>
<p><label class="mut">Model server<br><input id="base" style="width:100%"></label></p>
<p><label class="mut">His code (checkout on this Mac)<br><input id="repo" style="width:100%"></label></p>
<p><label class="mut">Also readable (folders, comma-separated)<br><input id="also" style="width:100%"></label></p>
<p><label class="mut"><input type="checkbox" id="offline"> Run code offline (take the network away). Default: runs may use the network to reach machines on your network; files stay contained either way.</label></p>
<button onclick="saveCfg()">Save settings</button></details></aside>
<main><div id="bar"><button id="menu" onclick="side(true)">☰</button><select id="model"></select><span id="st" class="mut"></span></div><div id="log"></div>
<form onsubmit="send(event)"><textarea id="txt" placeholder="Ask, paste a link, or ask it to grep his code. Cmd+Enter sends."></textarea><button>Send</button></form></main>
<div id="sucModal" class="modal" onclick="if(event.target===this)this.classList.remove('open')"><div class="modal-box"><h3>Start from a success</h3><div id="sucList"></div><button onclick="$('sucModal').classList.remove('open')">Cancel</button></div></div>
<script>
let tid=localStorage.getItem('wb-thread')||'';const $=id=>document.getElementById(id);
function side(on){$('side').classList.toggle('open',on)}
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function cfg(){const c=await j('/api/config');$('base').value=c.base_url;$('repo').value=c.repo;$('also').value=c.also_read||'';$('offline').checked=!!c.offline_runs;
 const ms=await j('/api/models');const s=$('model');s.innerHTML='';
 if(ms.error){$('st').textContent='No model server: '+ms.error;return}
 ms.forEach(m=>{const o=document.createElement('option');o.value=o.textContent=m;if(m==c.model)o.selected=true;s.appendChild(o)});
 $('st').textContent='Local only. It remembers this thread and nothing else.'}
$('model').onchange=()=>j('/api/config',{method:'POST',body:JSON.stringify({model:$('model').value})});
async function saveCfg(){await j('/api/config',{method:'POST',body:JSON.stringify({base_url:$('base').value,repo:$('repo').value,also_read:$('also').value,offline_runs:$('offline').checked})});cfg()}
async function threads(){const ts=await j('/api/threads');$('threads').innerHTML='';
 ts.forEach(t=>{const row=document.createElement('div');row.style.cssText='display:flex;gap:4px;align-items:center';
  const b=document.createElement('button');b.className='t'+(t.id==tid?' on':'');b.textContent=t.title||'Untitled';b.style.flex='1';b.onclick=()=>{side(false);open_(t.id)};
  const x=document.createElement('button');x.textContent='\u00d7';x.title='Delete this thread';x.style.cssText='padding:4px 8px';
  x.onclick=async()=>{if(!confirm('Delete this thread and everything in it? This cannot be undone.'))return;
   await j('/api/delete',{method:'POST',body:JSON.stringify({thread:t.id})});if(t.id==tid){newThread()}else{threads()}};
  row.appendChild(b);row.appendChild(x);$('threads').appendChild(row)});
 const all=document.createElement('button');all.textContent='Delete all threads';all.style.cssText='margin-top:10px;width:100%';
 all.onclick=async()=>{if(!confirm('Delete ALL threads and their history? This cannot be undone.'))return;
  await j('/api/delete',{method:'POST',body:JSON.stringify({thread:'*'})});newThread()};
 if(ts.length)$('threads').appendChild(all)}
function newThread(){side(false);tid=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random().toString(16).slice(2));localStorage.setItem('wb-thread',tid);$('log').innerHTML='';drawn=0;threads();watch()}
async function open_(id){tid=id;localStorage.setItem('wb-thread',id);const th=await j('/api/thread?id='+id);draw(th);threads();watch()}
function draw(th){const l=$('log');const bottom=l.scrollHeight-l.scrollTop-l.clientHeight<80;l.innerHTML='';
 (th.messages||[]).forEach(m=>{const d=document.createElement('div');
 d.className='m'+(m.tool?' tool':'');d.innerHTML='<div class="who"></div><div class="b"></div>';
 d.querySelector('.who').textContent=(m.tool?'Workbench':m.role=='user'?'You':(m.model||'Model'))+' · '+(m.at||'');
 d.querySelector('.b').textContent=m.content;l.appendChild(d)});
 if(th.working){const d=document.createElement('div');d.className='m';d.innerHTML='<div class="who"></div><div class="b"></div>';
  d.querySelector('.who').textContent='Workbench';d.querySelector('.b').textContent='…working';l.appendChild(d)}
 drawn=(th.messages||[]).length+(th.working?1:0);if(bottom)l.scrollTop=l.scrollHeight}
let drawn=0,poll=null;
function watch(){clearInterval(poll);poll=setInterval(async()=>{if(!tid)return;const th=await j('/api/thread?id='+tid);
 const n=(th.messages||[]).length+(th.working?1:0);if(n!=drawn){draw(th);if(!th.working){$('st').textContent='';threads()}}
 },2000)}
async function send(e){e&&e.preventDefault();const t=$('txt').value.trim();if(!t)return;if(!tid)newThread();
 $('txt').value='';$('st').textContent='Working… (it updates as it goes; safe to leave or send more)';watch();
 try{const r=await j('/api/send',{method:'POST',body:JSON.stringify({thread:tid,text:t})});
  if(r.error){$('txt').value=t;$('st').textContent=r.error;return}
  draw(r.thread);threads();$('st').textContent=r.saved&&r.saved.length?'Saved: '+r.saved.join(', '):''}
 catch(err){$('st').textContent='still working on the Mac; it keeps going and the thread updates when it lands'}}
$('txt').onkeydown=e=>{if(e.key=='Enter'&&(e.metaKey||e.ctrlKey))send()};
async function fromSuccess(){const ss=await j('/api/successes');const el=$('sucList');el.innerHTML='';
 if(!ss.length){el.innerHTML='<p class="mut">No successes saved yet. Type <b>!success</b> in a thread to save one.</p>';$('sucModal').classList.add('open');return}
 ss.forEach((s,i)=>{const b=document.createElement('button');b.className='suc';
  b.innerHTML='<div class="sh">'+esc(s.headline)+'</div><div class="sd">'+esc(s.at+(s.thread_title?' — '+s.thread_title:''))+'\n'+esc(s.recipe.slice(0,200)+(s.recipe.length>200?'…':''))+'</div>';
  b.onclick=()=>{$('sucModal').classList.remove('open');side(false);newThread();
   $('txt').value='Starting from this working recipe:\n\n'+s.recipe;send()};el.appendChild(b)});
 $('sucModal').classList.add('open')}
function esc(s){const d=document.createElement('span');d.textContent=s;return d.innerHTML}
cfg();if(tid)open_(tid);else threads();
</script></body></html>"""


def allowed(headers, port=PORT):
    """On the Mac itself (no proxy in between), or through Tailscale with her login on it. Tailscale serve adds
    Tailscale-User-Login for a person's device and never for a tagged machine, so an agent on the tailnet is refused."""
    proxied = any(headers.get(h) for h in ("X-Forwarded-For", "Tailscale-User-Login", "Tailscale-User-Name"))
    if not proxied:
        return (headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")
    return bool(headers.get("Tailscale-User-Login"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        try:
            self.send_response(code); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError, ConnectionError):
            # the phone or browser closed the connection while a slow turn was still running; the turn already saved
            # its work as it went, so the thread is intact and this answer is simply not delivered. Not an error.
            self.close_connection = True

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionError):
            self.close_connection = True

    def log_message(self, *a):
        pass

    def do_GET(self):
        if not allowed(self.headers):
            return self._send(403, {"error": "her Mac or her Tailscale only"})
        cfg = load_config()
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/config":
            return self._send(200, cfg)
        if self.path == "/api/models":
            return self._send(200, models(cfg))
        if self.path == "/api/threads":
            rows = []
            for name in os.listdir(THREADS) if os.path.isdir(THREADS) else []:
                try:
                    th = json.load(open(os.path.join(THREADS, name)))
                    rows.append({"id": th["id"], "title": th.get("title", ""), "at": os.path.getmtime(os.path.join(THREADS, name))})
                except Exception:
                    pass
            return self._send(200, sorted(rows, key=lambda r: -r["at"])[:100])
        if self.path == "/api/successes":
            return self._send(200, parse_successes())
        if self.path.startswith("/api/thread?id="):
            return self._send(200, load_thread(self.path.split("=", 1)[1]))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not allowed(self.headers) or (origin and origin.split("://", 1)[-1] != (self.headers.get("Host") or "")
                                         and origin not in ("http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT)):
            return self._send(403, {"error": "her Mac or her Tailscale only"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/config":
            cfg = load_config()
            cfg.update({k: v for k, v in body.items() if k in ("base_url", "model", "repo", "also_read", "offline_runs")})
            save_json(CONFIG, cfg)
            return self._send(200, cfg)
        if self.path == "/api/delete":
            which = str(body.get("thread") or "")
            removed = 0
            targets = ([thread_path(which)] if which != "*" else
                       [os.path.join(THREADS, n) for n in (os.listdir(THREADS) if os.path.isdir(THREADS) else [])])
            for fp in targets:
                try:
                    if os.path.realpath(os.path.dirname(fp)) == os.path.realpath(THREADS) and os.path.isfile(fp):
                        os.remove(fp); removed += 1
                except OSError:
                    pass
            return self._send(200, {"deleted": removed})
        if self.path == "/api/send":
            cfg = load_config()
            if not cfg.get("model"):
                # never one that is only downloaded: LM Studio would load it, and the Mac may have no room (24 October)
                loaded = loaded_models(cfg)
                if not loaded:
                    return self._send(200, {"thread": load_thread(str(body.get("thread") or "")), "saved": [],
                                            "error": "choose a model that is already loaded in LM Studio"})
                cfg["model"] = loaded[0]
            return self._send(200, turn(str(body.get("thread") or uuid.uuid4()), str(body.get("text") or ""), cfg))
        self._send(404, {"error": "not found"})


def main():
    for d in (HOME, CODE, THREADS, RUNS):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(CONFIG):
        save_json(CONFIG, DEFAULTS)
    print("Workbench on http://127.0.0.1:%d  (code saved in %s)" % (PORT, CODE), flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
