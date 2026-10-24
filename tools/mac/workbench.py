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
PORT = int(os.environ.get("WORKBENCH_PORT", "8765"))
DEFAULTS = {"base_url": "http://localhost:1234/v1", "model": "", "repo": os.path.expanduser("~/Documents/Vintos-main-faultloop"),
            "also_read": os.path.expanduser("~/Documents/Codex"), "context_chars": 80000, "max_tokens": 2048, "temperature": 0.4, "tool_rounds": 8, "allow_network_runs": False}
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
RUN <filename>                      run code/<filename> and get its output and errors back. It runs contained: it may
                                    read the Mac but may only write inside your code folder and a throwaway run folder,
                                    and it has NO network. Write a fix with SAVE, then RUN again, until it works.
Write the real value where the usage shows <...> or [...]: LIST scripts, not LIST [scripts] or LIST <folder>.
Paths are relative to his checkout, or absolute inside a folder she made readable (named below). Look before you answer:
do not describe a plan to look, look. Never pretend a tool ran. Everything you build stays in your code folder. Say
plainly when you do not know something, and quote paths and line numbers only from what the tools returned."""


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


GIT_READ = {"log", "show", "diff", "branch", "status", "ls-tree", "grep", "rev-parse", "describe", "shortlog", "blame"}
GIT_NEVER = re.compile(r"^(?:--output|-o$|--exec|-c$|--ext-diff|--upload-pack|--receive-pack|--config|-C$|--git-dir|--work-tree)")


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
    if not words or words[0] not in GIT_READ:
        return "only read-only git here: %s" % ", ".join(sorted(GIT_READ))
    if any(GIT_NEVER.match(w) for w in words[1:]):
        return "that git option is not allowed here"
    cmd = ["git", "-C", folder, "--no-pager", "-c", "core.pager=cat", words[0]]
    if words[0] in ("log", "show", "diff"): cmd += ["--no-ext-diff", "--no-textconv"]
    if words[0] == "branch" and not any(w.startswith("-") for w in words[1:]): words = words + ["-a"]
    try:
        r = subprocess.run(cmd + words[1:], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return "git did not run: %s" % str(e)[:200]
    out = (r.stdout or r.stderr or "(nothing)").strip()
    return out[:20000] + ("\n...[cut]" if len(out) > 20000 else "")


def save_code(name, code):
    """Write code/<name>, its one working file, keeping the previous version in code/.history so an edit loop never
    loses a good draft. A plain file, inside the code folder only."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name.strip()))[:120].lstrip(".") or "untitled.txt"
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
    """Run code/<file> and return its output and errors, so the model can fix it and run it again. Contained: it may
    read the Mac but writes only inside the code folder and a throwaway run folder, and has no network unless Gloria
    turned 'allow network in runs' on in Settings AND the line says --net (for code that must reach another machine)."""
    import shlex, subprocess, tempfile
    want_net = False
    words = shlex.split(_unwrap(arg)) if arg else []
    words = [w for w in words if (want_net := want_net or w in ("--net", "--network")) is not None and w not in ("--net", "--network")]
    name = os.path.basename(words[0]) if words else ""
    path = _inside(CODE, name)
    if not name or not path or not os.path.isfile(path):
        return "no such saved file: code/%s — SAVE it first, then RUN it" % (name or "?")
    interp = INTERP.get(os.path.splitext(path)[1].lower())
    if not interp:
        return "I only run .py, .sh, .js, .ts, .rb or .pl files here"
    net_on = want_net and cfg.get("allow_network_runs")
    os.makedirs(RUNS, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="run-", dir=RUNS)
    cmd = [interp, path]
    sandboxed = False
    if os.path.exists("/usr/bin/sandbox-exec"):
        profile = SANDBOX % {"code": os.path.realpath(CODE), "scratch": os.path.realpath(scratch),
                             "tmp": os.path.realpath(tempfile.gettempdir()),
                             "net": "" if net_on else "(deny network*)"}
        cmd = ["/usr/bin/sandbox-exec", "-p", profile] + cmd
        sandboxed = True
    try:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER")}
        done = subprocess.run(cmd, cwd=scratch, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env)
        out = ((done.stdout or "") + (("\n--- errors ---\n" + done.stderr) if done.stderr.strip() else "")).strip()
        head = "ran code/%s%s%s, exit %d%s" % (name, " (with network)" if net_on else "",
               "" if sandboxed else " — NOT sandboxed on this Mac (sandbox-exec missing)", done.returncode,
               "" if done.returncode == 0 else "  ← it failed; read the errors and SAVE a fix")
        if want_net and not cfg.get("allow_network_runs"):
            head += "\n(note: it asked for the network; runs have none until you turn on 'allow network in runs' in Settings)"
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
TOOL = re.compile(r"^[ \t>*\-`]*(?:\d+[.)][ \t]*)?[*`]*(FETCH|GREP|READ|LIST|GIT|RUN)\b[*`]*[ \t:]*(.*?)[*`]*[ \t]*$", re.M)
SAVE = re.compile(r"^\s*SAVE[ \t]+(\S+)[^\n]*\n(?:.*?\n)??\s*```[^\n]*\n(.*?)\n\s*```", re.M | re.S)


VERBS = {"fetch": "FETCH", "grep": "GREP", "read": "READ", "list": "LIST", "git": "GIT", "save": "SAVE", "run": "RUN"}
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
         _fn("run", "Run a file you saved and get its output and errors (contained, no network)", filename="code/<name>")]


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
            with urllib.request.urlopen(req, timeout=600) as r:
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


def turn(tid, text, cfg, model_call=complete):
    """Her message in, the model's answer out, with as many lookup rounds as it asks for (up to tool_rounds)."""
    with LOCK:
        th = load_thread(tid)
    th["messages"].append({"role": "user", "content": text, "at": time.strftime("%H:%M")})
    if not th.get("title"): th["title"] = text.strip().splitlines()[0][:60] if text.strip() else "Untitled"
    links = list(dict.fromkeys(u.rstrip(".,;:") for u in URL.findall(text)))[:3]
    if links:   # the links she gave are read for it before it answers (25 October: it never asked to FETCH them)
        th["messages"].append({"role": "user", "tool": True, "at": time.strftime("%H:%M"),
                               "content": "LINKS GLORIA GAVE (read by the Workbench):\n\n" +
                                          "\n\n".join("=== %s ===\n%s" % (u, fetch_link(cfg, u)) for u in links)})
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
        shown.append(reply)
        saved += do_saves(reply)
        results = run_tools(reply, cfg)
        if not results: break
        th["messages"].append({"role": "user", "content": "TOOL RESULTS (from the Workbench, not from Gloria):\n" + results,
                               "at": time.strftime("%H:%M"), "tool": True})
        shown.append("[looked up]\n" + results[:4000] + ("\n..." if len(results) > 4000 else ""))
    if saved:
        th["messages"].append({"role": "user", "content": "SAVED (by the Workbench): " + ", ".join(saved), "tool": True,
                               "at": time.strftime("%H:%M")})
    with LOCK:
        save_json(thread_path(tid), th)
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
@media (max-width:700px){body{display:block;height:100dvh}main{height:100dvh}aside{display:none;position:fixed;inset:0;z-index:5;width:auto;background:var(--bg)}
 aside.open{display:block}#menu{display:inline-block}#log{padding:12px}form{padding:8px 12px;padding-bottom:max(8px,env(safe-area-inset-bottom))}
 #bar{padding:8px 12px}textarea{font-size:16px;min-height:48px}.m{max-width:100%}select{max-width:60vw}}
</style></head><body>
<aside id="side"><button onclick="newThread()">+ New thread</button> <button id="close" onclick="side(false)">Close</button><div id="threads"></div>
<p class="mut">Code it saves: ~/Vintos-Workbench/code</p><details><summary class="mut">Settings</summary>
<p><label class="mut">Model server<br><input id="base" style="width:100%"></label></p>
<p><label class="mut">His code (checkout on this Mac)<br><input id="repo" style="width:100%"></label></p>
<p><label class="mut">Also readable (folders, comma-separated)<br><input id="also" style="width:100%"></label></p>
<p><label class="mut"><input type="checkbox" id="netrun"> Let code it runs use the network (e.g. reach another machine). Off keeps runs fully contained.</label></p>
<button onclick="saveCfg()">Save settings</button></details></aside>
<main><div id="bar"><button id="menu" onclick="side(true)">☰</button><select id="model"></select><span id="st" class="mut"></span></div><div id="log"></div>
<form onsubmit="send(event)"><textarea id="txt" placeholder="Ask, paste a link, or ask it to grep his code. Cmd+Enter sends."></textarea><button>Send</button></form></main>
<script>
let tid=localStorage.getItem('wb-thread')||'';const $=id=>document.getElementById(id);
function side(on){$('side').classList.toggle('open',on)}
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function cfg(){const c=await j('/api/config');$('base').value=c.base_url;$('repo').value=c.repo;$('also').value=c.also_read||'';$('netrun').checked=!!c.allow_network_runs;
 const ms=await j('/api/models');const s=$('model');s.innerHTML='';
 if(ms.error){$('st').textContent='No model server: '+ms.error;return}
 ms.forEach(m=>{const o=document.createElement('option');o.value=o.textContent=m;if(m==c.model)o.selected=true;s.appendChild(o)});
 $('st').textContent='Local only. It remembers this thread and nothing else.'}
$('model').onchange=()=>j('/api/config',{method:'POST',body:JSON.stringify({model:$('model').value})});
async function saveCfg(){await j('/api/config',{method:'POST',body:JSON.stringify({base_url:$('base').value,repo:$('repo').value,also_read:$('also').value,allow_network_runs:$('netrun').checked})});cfg()}
async function threads(){const ts=await j('/api/threads');$('threads').innerHTML='';
 ts.forEach(t=>{const b=document.createElement('button');b.className='t'+(t.id==tid?' on':'');b.textContent=t.title||'Untitled';b.onclick=()=>{side(false);open_(t.id)};$('threads').appendChild(b)})}
function newThread(){side(false);tid=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random().toString(16).slice(2));localStorage.setItem('wb-thread',tid);$('log').innerHTML='';threads()}
async function open_(id){tid=id;localStorage.setItem('wb-thread',id);const th=await j('/api/thread?id='+id);draw(th);threads()}
function draw(th){const l=$('log');l.innerHTML='';(th.messages||[]).forEach(m=>{const d=document.createElement('div');
 d.className='m'+(m.tool?' tool':'');d.innerHTML='<div class="who"></div><div class="b"></div>';
 d.querySelector('.who').textContent=(m.tool?'Workbench':m.role=='user'?'You':(m.model||'Model'))+' · '+(m.at||'');
 d.querySelector('.b').textContent=m.content;l.appendChild(d)});l.scrollTop=l.scrollHeight}
async function send(e){e&&e.preventDefault();const t=$('txt').value.trim();if(!t)return;if(!tid)newThread();
 $('txt').value='';$('st').textContent='Thinking… (if the phone sleeps, reopen: the answer is kept)';const r=await j('/api/send',{method:'POST',body:JSON.stringify({thread:tid,text:t})});
 if(r.error){$('txt').value=t;$('st').textContent=r.error;return}
 draw(r.thread);threads();$('st').textContent=r.saved&&r.saved.length?'Saved: '+r.saved.join(', '):''}
$('txt').onkeydown=e=>{if(e.key=='Enter'&&(e.metaKey||e.ctrlKey))send()};
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
        self.send_response(code); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

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
            cfg.update({k: v for k, v in body.items() if k in ("base_url", "model", "repo", "also_read", "allow_network_runs")})
            save_json(CONFIG, cfg)
            return self._send(200, cfg)
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
