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
Python's standard library only; nothing to install.
"""
import fnmatch, html, html.parser, json, os, re, sys, threading, time, urllib.error, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.environ.get("WORKBENCH_HOME", os.path.expanduser("~/Vintos-Workbench"))
CODE = os.path.join(HOME, "code")
THREADS = os.path.join(HOME, "threads")
CONFIG = os.path.join(HOME, "config.json")
PORT = int(os.environ.get("WORKBENCH_PORT", "8765"))
DEFAULTS = {"base_url": "http://localhost:1234/v1", "model": "", "repo": os.path.expanduser("~/Documents/Vintos-main-faultloop"),
            "context_chars": 80000, "max_tokens": 2048, "temperature": 0.4, "tool_rounds": 6}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".mypy_cache"}
LOCK = threading.Lock()

SYSTEM = """You are a careful coding companion working with Gloria on her Mac. You remember only this conversation.

You can look things up. To use a tool, put it on its own line at the very start of a line, and nothing else on that line:
FETCH <url>                       read a web page or file from the internet
GREP <regex> [in <glob>]          search Vintos's code (read-only), e.g. GREP def tend in scripts/*.py
READ <path> [<first>-<last>]      read a file of his code by its path from GREP, or a file you saved (code/<name>)
LIST [<dir>]                      list a folder of his code
SAVE <filename>                   save code: the next ``` fenced block is written to her Workbench code folder
After a FETCH, GREP, READ or LIST line, stop and wait: the results come back in the next message. Use as few as you need.
You never run code and nothing you write is run; SAVE only stores it for her. Say plainly when you do not know something,
and quote file paths and line numbers from what the tools returned, never from memory."""


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


def grep(repo, pattern, glob=None, limit=60):
    if not os.path.isdir(repo):
        return "his code is not at %s; set the checkout in Settings" % repo
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return "bad regex: %s" % e
    hits = []
    for top, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(top, name); rel = os.path.relpath(path, repo)
            if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(name, glob): continue
            try:
                if os.path.getsize(path) > 1_000_000: continue
                with open(path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append("%s:%d: %s" % (rel, n, line.rstrip()[:240]))
                            if len(hits) >= limit:
                                return "\n".join(hits) + "\n...[first %d matches]" % limit
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(hits) or "no matches"


def read(repo, rel, span=None, limit=400):
    root, rel = (CODE, rel[5:]) if rel.startswith("code/") else (repo, rel)
    path = _inside(root, rel)
    if not path or not os.path.isfile(path):
        return "no such file: %s" % rel
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


def listing(repo, rel=""):
    path = _inside(repo, rel or ".")
    if not path or not os.path.isdir(path):
        return "no such folder: %s" % rel
    names = sorted(n + ("/" if os.path.isdir(os.path.join(path, n)) else "") for n in os.listdir(path) if n not in SKIP_DIRS)
    return "\n".join(names[:300]) or "(empty)"


def save_code(name, code):
    """A plain file in the code folder. Never executable, never overwritten."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name.strip()))[:120].lstrip(".") or "untitled.txt"
    os.makedirs(CODE, exist_ok=True)
    path = os.path.join(CODE, name)
    if os.path.exists(path):
        stem, ext = os.path.splitext(name)
        path = os.path.join(CODE, "%s-%s%s" % (stem, time.strftime("%Y%m%d-%H%M%S"), ext))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code if code.endswith("\n") else code + "\n")
    return path


TOOL = re.compile(r"^\s*(FETCH|GREP|READ|LIST)\b[ \t]*(.*?)\s*$", re.M)
SAVE = re.compile(r"^\s*SAVE[ \t]+(\S+)[^\n]*\n(?:.*?\n)??\s*```[^\n]*\n(.*?)\n\s*```", re.M | re.S)


def run_tools(reply, cfg):
    """The results of every lookup line in a reply, or '' when it asked for none."""
    out = []
    for verb, arg in TOOL.findall(reply)[:6]:
        if verb == "FETCH":
            result = fetch(arg.split()[0] if arg else "")
        elif verb == "GREP":
            m = re.match(r"(.*?)\s+in\s+(\S+)$", arg)
            result = grep(cfg["repo"], *(m.groups() if m else (arg, None)))
        elif verb == "READ":
            parts = arg.split()
            result = read(cfg["repo"], parts[0] if parts else "", parts[1] if len(parts) > 1 else None)
        else:
            result = listing(cfg["repo"], arg)
        out.append("=== %s %s ===\n%s" % (verb, arg, result))
    return "\n\n".join(out)


def do_saves(reply):
    return [save_code(name, code) for name, code in SAVE.findall(reply)]


# ------------------------------------------------------------------------------------------------ the model

def models(cfg):
    try:
        with urllib.request.urlopen(cfg["base_url"].rstrip("/") + "/models", timeout=8) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except Exception as e:
        return {"error": str(e)[:200]}


def complete(cfg, messages):
    body = {"model": cfg["model"], "messages": messages, "max_tokens": int(cfg["max_tokens"]),
            "temperature": float(cfg["temperature"]), "stream": False}
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"].get("content") or ""


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
    shown, saved = [], []
    for _ in range(int(cfg["tool_rounds"]) + 1):
        msgs = fitted([{"role": "system", "content": SYSTEM}] +
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
</style></head><body>
<aside><button onclick="newThread()">+ New thread</button><div id="threads"></div>
<p class="mut">Code it saves: ~/Vintos-Workbench/code</p><details><summary class="mut">Settings</summary>
<p><label class="mut">Model server<br><input id="base" style="width:100%"></label></p>
<p><label class="mut">His code (checkout on this Mac)<br><input id="repo" style="width:100%"></label></p>
<button onclick="saveCfg()">Save settings</button></details></aside>
<main><div id="bar"><select id="model"></select><span id="st" class="mut"></span></div><div id="log"></div>
<form onsubmit="send(event)"><textarea id="txt" placeholder="Ask, paste a link, or ask it to grep his code. Cmd+Enter sends."></textarea><button>Send</button></form></main>
<script>
let tid=localStorage.getItem('wb-thread')||'';const $=id=>document.getElementById(id);
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function cfg(){const c=await j('/api/config');$('base').value=c.base_url;$('repo').value=c.repo;
 const ms=await j('/api/models');const s=$('model');s.innerHTML='';
 if(ms.error){$('st').textContent='No model server: '+ms.error;return}
 ms.forEach(m=>{const o=document.createElement('option');o.value=o.textContent=m;if(m==c.model)o.selected=true;s.appendChild(o)});
 $('st').textContent='Local only. It remembers this thread and nothing else.'}
$('model').onchange=()=>j('/api/config',{method:'POST',body:JSON.stringify({model:$('model').value})});
async function saveCfg(){await j('/api/config',{method:'POST',body:JSON.stringify({base_url:$('base').value,repo:$('repo').value})});cfg()}
async function threads(){const ts=await j('/api/threads');$('threads').innerHTML='';
 ts.forEach(t=>{const b=document.createElement('button');b.className='t'+(t.id==tid?' on':'');b.textContent=t.title||'Untitled';b.onclick=()=>open_(t.id);$('threads').appendChild(b)})}
function newThread(){tid=crypto.randomUUID();localStorage.setItem('wb-thread',tid);$('log').innerHTML='';threads()}
async function open_(id){tid=id;localStorage.setItem('wb-thread',id);const th=await j('/api/thread?id='+id);draw(th);threads()}
function draw(th){const l=$('log');l.innerHTML='';(th.messages||[]).forEach(m=>{const d=document.createElement('div');
 d.className='m'+(m.tool?' tool':'');d.innerHTML='<div class="who"></div><div class="b"></div>';
 d.querySelector('.who').textContent=(m.tool?'Workbench':m.role=='user'?'You':(m.model||'Model'))+' · '+(m.at||'');
 d.querySelector('.b').textContent=m.content;l.appendChild(d)});l.scrollTop=l.scrollHeight}
async function send(e){e&&e.preventDefault();const t=$('txt').value.trim();if(!t)return;if(!tid)newThread();
 $('txt').value='';$('st').textContent='Thinking…';const r=await j('/api/send',{method:'POST',body:JSON.stringify({thread:tid,text:t})});
 draw(r.thread);threads();$('st').textContent=r.saved&&r.saved.length?'Saved: '+r.saved.join(', '):''}
$('txt').onkeydown=e=>{if(e.key=='Enter'&&(e.metaKey||e.ctrlKey))send()};
cfg();if(tid)open_(tid);else threads();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
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
        if self.headers.get("Origin") not in (None, "http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT):
            return self._send(403, {"error": "local page only"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/config":
            cfg = load_config()
            cfg.update({k: v for k, v in body.items() if k in ("base_url", "model", "repo")})
            save_json(CONFIG, cfg)
            return self._send(200, cfg)
        if self.path == "/api/send":
            cfg = load_config()
            if not cfg.get("model"):
                ms = models(cfg)
                if isinstance(ms, list) and ms: cfg["model"] = ms[0]
            return self._send(200, turn(str(body.get("thread") or uuid.uuid4()), str(body.get("text") or ""), cfg))
        self._send(404, {"error": "not found"})


def main():
    for d in (HOME, CODE, THREADS):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(CONFIG):
        save_json(CONFIG, DEFAULTS)
    print("Workbench on http://127.0.0.1:%d  (code saved in %s)" % (PORT, CODE), flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
