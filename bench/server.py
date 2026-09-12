#!/usr/bin/env python3
"""server.py — the bench, as a page. Her agents, manageable from her phone.

The ledger is useless if approving a task means remembering a command. This is a custom layout, not the Buzz application. It uses — a rail of agents down one side, the work in the middle, one card
per task with the two buttons that matter — in a single file with no build step, no
node, no bundle. It is stdlib only, so it survives on Aegis without anything to keep
installed and can be edited in place.

    python3 server.py                 serve on 0.0.0.0:8791 (the tailnet)
    BENCH_PORT=... python3 server.py

THE PAGE IS RENDERED HERE, IN PYTHON, NOT IN HER BROWSER.

The first version drew itself with JavaScript and shipped an empty <main> that said
"loading…". It reached her phone as a black rectangle. Two things were wrong at once
— the unit was not running at all, and even had it been, every pixel depended on a
fetch succeeding. Only one of those was fixed by fixing the unit.

So: the server renders the whole page, every time, from state it already has. Approve
and Deny are real <form method=post> — they work with JavaScript switched off, in a
private tab, on a page that failed to finish loading its script. The script is an
enhancement and nothing more: it swaps the same server-rendered fragment in place so
the page does not jump. If it never runs, she loses smoothness and loses nothing else.

Every request except health requires ~/.vintos/.bench-token, supplied through
a Bearer header or ?t=<token>. A missing or empty token keeps the page closed. A refusal is an HTML page that says so, not a JSON blob she has to read.

It is NOT the agent room, and it does not read his memory. It reads and writes the
bench's own ledgers, through bench.py, and nothing else.
"""
import json
import hmac
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench as B

PORT = int(os.environ.get("BENCH_PORT", "8791"))
# Overridable only so the suite can prove the gate without a token file on the host
# that serves her. On Aegis it is the default and nothing sets the variable.
TOKEN_FILE = os.environ.get("BENCH_TOKEN_FILE") or os.path.expanduser("~/.vintos/.bench-token")

OPEN_STATES = ("proposed", "approved", "claimed")

# Buzz's dark palette, taken from web/src/shared/styles/globals.css (Apache-2.0).
STYLE = """<style>
:root{
  --bg:hsl(232 23.4% 18.43%); --fg:hsl(227 68.25% 87.65%);
  --card:hsl(232 23.4% 21%); --muted:hsl(230 18.8% 26.08%);
  --muted-fg:hsl(228 39.22% 80%); --primary:hsl(267 82.69% 79.61%);
  --primary-fg:hsl(232 23.4% 18.43%); --destructive:hsl(351 73.91% 72.94%);
  --border:hsl(231 15.61% 33.92%); --radius:0.625rem;
  --ok:hsl(115 54% 76%); --warn:hsl(41 86% 83%);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.5 ui-sans-serif,-apple-system,"SF Pro Text",Inter,system-ui,sans-serif;
  padding-bottom:env(safe-area-inset-bottom)}
a{color:inherit;text-decoration:none}
header{position:sticky;top:0;z-index:5;background:var(--bg);
  border-bottom:1px solid var(--border);padding:14px 16px;
  padding-top:calc(14px + env(safe-area-inset-top));display:flex;align-items:center;gap:12px}
header h1{margin:0;font-size:16px;font-weight:600;letter-spacing:.02em}
header .count{margin-left:auto;font-size:13px;color:var(--muted-fg)}
.wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:0}
@media(min-width:900px){.wrap{grid-template-columns:260px minmax(0,1fr)}}
nav{border-bottom:1px solid var(--border);padding:10px 12px;display:flex;gap:8px;overflow-x:auto;
  -webkit-overflow-scrolling:touch}
@media(min-width:900px){nav{flex-direction:column;border-bottom:0;border-right:1px solid var(--border);
  min-height:calc(100vh - 56px);overflow:visible}}
nav a{flex:0 0 auto;background:transparent;color:var(--muted-fg);border:1px solid transparent;
  border-radius:var(--radius);padding:9px 12px;font-size:14px;min-height:44px;
  display:flex;flex-direction:column;justify-content:center;white-space:nowrap}
nav a.on{background:var(--muted);color:var(--fg);border-color:var(--border)}
nav a .sub{display:block;font-size:11px;color:var(--muted-fg);margin-top:2px}
main{padding:16px;min-width:0}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:14px;margin:0 0 12px}
.card .top{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.id{font:12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted-fg)}
.kind{font-size:12px;background:var(--muted);border-radius:999px;padding:3px 9px;color:var(--fg)}
.who{font-size:12px;color:var(--primary)}
.what{margin:9px 0 0;font-size:15px}
.why{margin:6px 0 0;font-size:13px;color:var(--muted-fg)}
.row{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;align-items:stretch}
.row form{flex:1 1 140px;display:flex;gap:8px;margin:0}
button.act{flex:1 1 140px;min-height:44px;border-radius:var(--radius);border:1px solid var(--border);
  font:inherit;font-weight:600;cursor:pointer}
button.yes{background:var(--primary);color:var(--primary-fg);border-color:transparent}
button.no{background:transparent;color:var(--destructive);border-color:var(--destructive)}
input.why{flex:2 1 160px;min-height:44px;border-radius:var(--radius);border:1px solid var(--border);
  background:var(--bg);color:var(--fg);font:inherit;padding:0 12px;margin:0}
.state{font-size:12px;padding:3px 9px;border-radius:999px;border:1px solid var(--border);color:var(--muted-fg)}
.state.approved{color:var(--warn);border-color:var(--warn)}
.state.claimed{color:var(--primary);border-color:var(--primary)}
.state.done{color:var(--ok);border-color:var(--ok)}
.state.failed,.state.denied{color:var(--destructive);border-color:var(--destructive)}
.empty{color:var(--muted-fg);padding:28px 4px;text-align:center}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted-fg);
  margin:22px 0 10px;font-weight:600}
h2:first-child{margin-top:0}
.deleg{font-size:12px;color:var(--muted-fg);margin-top:8px;line-height:1.7}
.deleg code{background:var(--muted);border-radius:4px;padding:1px 5px;
  font:11px ui-monospace,Menlo,monospace}
.hist{margin-top:10px;border-top:1px solid var(--border);padding-top:9px;
  font:12px/1.7 ui-monospace,Menlo,monospace;color:var(--muted-fg)}
.err{background:var(--destructive);color:var(--primary-fg);padding:10px 14px;border-radius:var(--radius);
  margin:0 0 12px;font-size:14px}
</style>"""

HEAD = ('<!doctype html>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        '<meta name="color-scheme" content="dark">\n'
        '<title>bench</title>\n' + STYLE + '\n')

# The whole of the client side. It renders nothing — it asks the server for the same
# fragment the server already rendered and puts it where it was. Switch it off and the
# page still works; the forms below are real forms.
SCRIPT = """<script>
(function(){
  var wrap = document.getElementById('wrap');
  if(!wrap) return;
  function swap(html){
    var d = document.createElement('div');
    d.innerHTML = html;
    var w = d.querySelector('#wrap'), c = d.querySelector('#count');
    if(w) wrap.innerHTML = w.innerHTML;
    if(c) document.getElementById('count').textContent = c.textContent;
  }
  function refresh(){
    fetch(location.pathname + location.search, {headers:{'X-Fragment':'1'}})
      .then(function(r){ return r.text(); }).then(swap).catch(function(){});
  }
  document.addEventListener('submit', function(e){
    var f = e.target;
    if(!f.matches('form.bench')) return;
    e.preventDefault();
    fetch(f.action, {method:'POST', body:new URLSearchParams(new FormData(f)),
                     headers:{'X-Fragment':'1'}})
      .then(function(r){ return r.text(); }).then(swap).catch(function(){ f.submit(); });
  });
  setInterval(refresh, 5000);
})();
</script>"""


def esc(s):
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except Exception:
        return ""


def _state():
    tasks = [t for t in B._all() if t]
    tasks.sort(key=lambda t: t.get("proposed_at") or "")
    return {"agents": B.agents(), "tasks": tasks}


def _link(view, tok):
    q = {"view": view}
    if tok:
        q["t"] = tok
    return "/?" + urllib.parse.urlencode(q)


# --- the page, rendered here ------------------------------------------------------

def _history(t):
    out = []
    for h in (t.get("history") or []):
        at = str(h.get("at") or "")[11:16]
        line = "%s %s" % (esc(at), esc(h.get("event")))
        if h.get("by"):
            line += " &middot; " + esc(h["by"])
        for k in ("result", "why"):
            if h.get(k):
                line += " — " + esc(str(h[k])[:120])
        out.append(line)
    return "<br>".join(out)


def _card(t, tok, view, buttons=True):
    acts = ""
    if buttons and t.get("state") == "proposed":
        hidden = ('<input type="hidden" name="task" value="%s">'
                  '<input type="hidden" name="view" value="%s">'
                  % (esc(t.get("task")), esc(view)))
        if tok:
            hidden += '<input type="hidden" name="t" value="%s">' % esc(tok)
        acts = ('<div class="row">'
                '<form class="bench" method="post" action="/api/approve">%s'
                '<button class="act yes" type="submit">Approve</button></form>'
                '<form class="bench" method="post" action="/api/deny">%s'
                '<input class="why" type="text" name="why" placeholder="why not?">'
                '<button class="act no" type="submit">Deny</button></form>'
                '</div>' % (hidden, hidden))
    hist = _history(t)
    return ('<div class="card">'
            '<div class="top"><span class="id">%s</span>'
            '<span class="kind">%s</span>'
            '<span class="who">%s &rarr; %s</span>'
            '<span class="state %s" style="margin-left:auto">%s</span></div>'
            '<p class="what">%s</p>%s%s%s</div>'
            % (esc(t.get("task")), esc(t.get("kind") or "—"), esc(t.get("by")),
               esc(t.get("owner")), esc(t.get("state")), esc(t.get("state")),
               esc(t.get("what")),
               ('<p class="why">%s</p>' % esc(t["why"])) if t.get("why") else "",
               acts,
               ('<div class="hist">%s</div>' % hist) if hist else ""))


def _nav(st, view, tok):
    pend = [t for t in st["tasks"] if t.get("state") == "proposed"]
    items = [("pending", "waiting on you",
              ("%d to approve" % len(pend)) if pend else "nothing waiting"),
             ("all", "every task", "%d total" % len(st["tasks"]))]
    for name in st["agents"]:
        open_n = len([t for t in st["tasks"]
                      if t.get("owner") == name and t.get("state") in OPEN_STATES])
        items.append(("a:" + name, name, ("%d open" % open_n) if open_n else "idle"))
    out = []
    for key, label, sub in items:
        out.append('<a class="%s" href="%s">%s<span class="sub">%s</span></a>'
                   % ("on" if view == key else "", esc(_link(key, tok)), esc(label), esc(sub)))
    return "<nav>" + "".join(out) + "</nav>"


def _main(st, view, tok, err):
    h = ('<div class="err">%s</div>' % esc(err)) if err else ""
    tasks = st["tasks"]
    if view == "all":
        open_t = [t for t in tasks if t.get("state") in OPEN_STATES]
        shut = [t for t in tasks if t.get("state") not in OPEN_STATES][::-1]
        if open_t:
            h += "<h2>open</h2>" + "".join(_card(t, tok, view) for t in open_t)
        if shut:
            h += "<h2>closed</h2>" + "".join(_card(t, tok, view, False) for t in shut[:40])
        if not open_t and not shut:
            h += '<div class="empty">No tasks yet.</div>'
    elif view.startswith("a:"):
        name = view[2:]
        cfg = st["agents"].get(name) or {}
        d = cfg.get("delegate") or {}
        keeps = cfg.get("keeps") or []
        auto = cfg.get("auto_approve") or []
        h += ('<div class="card"><div class="top"><strong>%s</strong></div>'
              '<p class="why">%s</p>' % (esc(name), esc(cfg.get("what") or "")))
        if d:
            h += ('<div class="deleg">hands down: %s</div>'
                  % " &middot; ".join("<code>%s</code> &rarr; %s" % (esc(k), esc(v))
                                      for k, v in d.items()))
        if keeps:
            h += ('<div class="deleg">keeps: %s</div>'
                  % " ".join("<code>%s</code>" % esc(k) for k in keeps))
        h += ('<div class="deleg">starts unasked: %s</div></div>'
              % (" ".join("<code>%s</code>" % esc(k) for k in auto) if auto
                 else "nothing — everything waits on you"))
        rows = [t for t in tasks if t.get("owner") == name or t.get("by") == name][::-1]
        h += ("<h2>its ledger</h2>" + "".join(_card(t, tok, view) for t in rows[:60])) if rows \
            else '<div class="empty">Nothing in this ledger yet.</div>'
    else:
        rows = [t for t in tasks if t.get("state") == "proposed"]
        h += ("<h2>waiting on you</h2>" + "".join(_card(t, tok, view) for t in rows)) if rows \
            else '<div class="empty">Nothing waiting on you.</div>'
    return "<main>" + h + "</main>"


def fragment(st, view, tok, err=""):
    """The half that changes. Rendered identically for a full load and for a poll, so
    there is exactly one renderer and the page cannot disagree with itself."""
    pend = len([t for t in st["tasks"] if t.get("state") == "proposed"])
    count = ("%d waiting on you" % pend) if pend else "all clear"
    return ('<span class="count" id="count">%s</span>'
            '<div class="wrap" id="wrap">%s%s</div>'
            % (esc(count), _nav(st, view, tok), _main(st, view, tok, err)))


def render(view="pending", tok="", err=""):
    try:
        st = _state()
    except Exception as e:                      # a broken ledger is a message, not a blank page
        st = {"agents": {}, "tasks": []}
        err = err or ("the ledgers could not be read: %s" % e)
    frag = fragment(st, view, tok, err)
    head, _, body = frag.partition("<div class=\"wrap\"")
    return (HEAD + "<header><h1>bench</h1>" + head + "</header>\n"
            + "<div class=\"wrap\"" + body + "\n" + SCRIPT + "\n")


REFUSED = (HEAD + '<header><h1>bench</h1></header><main>'
           '<div class="err">bad or missing token</div>'
           '<p class="why">This bench is behind a token. Open it with '
           '<code>?t=&lt;token&gt;</code> — the token is the one line in '
           '<code>~/.vintos/.bench-token</code> on Aegis.</p></main>\n')

NOTFOUND = (HEAD + '<header><h1>bench</h1></header><main>'
            '<div class="empty">no such path</div>'
            '<p class="why" style="text-align:center"><a href="/">back to the bench</a></p>'
            '</main>\n')


def _diag():
    """What is actually true on this host, in plain text, with no secret in it. When
    the page does not come up, this is the first thing to read."""
    lines = ["bench diagnostics",
             "python        %s" % sys.version.split()[0],
             "port          %d" % PORT,
             "bench root    %s" % B.ROOT,
             "ledgers dir   %s  exists=%s writable=%s"
             % (B.LEDGERS, os.path.isdir(B.LEDGERS), os.access(B.LEDGERS, os.W_OK)),
             "agents dir    %s  exists=%s" % (B.AGENTS, os.path.isdir(B.AGENTS)),
             "token         %s" % ("required (?t=...)" if _token() else "missing — access refused")]
    try:
        st = _state()
        lines.append("agents        %s" % ", ".join(sorted(st["agents"])) or "(none)")
        lines.append("tasks         %d, %d waiting on her"
                     % (len(st["tasks"]), len([t for t in st["tasks"] if t.get("state") == "proposed"])))
    except Exception as e:
        lines.append("state         UNREADABLE: %s" % e)
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _q(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _authed(self):
        want = _token()
        if not want:
            return False
        supplied = self.headers.get("Authorization", "")
        supplied = supplied[7:] if supplied.startswith("Bearer ") else self._q().get("t", [""])[0]
        return hmac.compare_digest(supplied, want)

    def _send(self, code, body, ctype="application/json", extra=()):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _wants_fragment(self):
        return self.headers.get("X-Fragment") == "1"

    def _view(self, src):
        v = (src.get("view") or ["pending"])[0]
        return v if (v in ("pending", "all") or v.startswith("a:")) else "pending"

    def _html(self, view, tok, err="", code=200):
        if self._wants_fragment():
            try:
                st = _state()
            except Exception as e:
                st, err = {"agents": {}, "tasks": []}, err or str(e)
            return self._send(code, fragment(st, view, tok, err), "text/html; charset=utf-8")
        self._send(code, render(view, tok, err), "text/html; charset=utf-8")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":                    # never gated: it is how she checks it is up
            return self._send(200, json.dumps({"ok": True}))
        if not self._authed():
            if path.startswith("/api/"):
                return self._send(403, json.dumps({"error": "bad or missing token"}))
            return self._send(403, REFUSED, "text/html; charset=utf-8")
        q = self._q()
        tok = q.get("t", [""])[0]
        if path in ("/", "/index.html"):
            return self._html(self._view(q), tok)
        if path == "/api/state":
            return self._send(200, json.dumps(_state()))
        if path == "/diag":
            return self._send(200, _diag(), "text/plain; charset=utf-8")
        self._send(404, NOTFOUND, "text/html; charset=utf-8")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._authed():
            return self._send(403, json.dumps({"error": "bad or missing token"}))
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        form = ctype != "application/json"
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            body = ({k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                    if form else json.loads(raw or b"{}"))
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        tid = str(body.get("task") or "")
        # Only her two verbs are exposed. The page cannot claim, finish or hand off —
        # those belong to the agents, and a button that could do them would be a way
        # for whoever opens this page to act as one.
        if path == "/api/approve":
            t, why = B.approve(tid)
        elif path == "/api/deny":
            t, why = B.deny(tid, str(body.get("why") or ""))
        else:
            if form:
                return self._send(404, NOTFOUND, "text/html; charset=utf-8")
            return self._send(404, json.dumps({"error": "no such path"}))
        if not form:
            if t is None:
                return self._send(200, json.dumps({"error": why}))
            return self._send(200, json.dumps({"ok": True, "task": t["task"], "state": t["state"]}))
        # A form post answers with the page she is already looking at. With the script
        # running that is a fragment swapped in place; without it, a plain redirect —
        # so the two buttons work on a phone with JavaScript off.
        view = self._view({k: [v] for k, v in body.items()})
        tok = str(body.get("t") or "")
        if self._wants_fragment():
            return self._html(view, tok, "" if t is not None else (why or ""))
        return self._send(303, b"", "text/html; charset=utf-8",
                          extra=[("Location", _link(view, tok))])


def main():
    # Everything here is printed before anything is served, and flushed, because when
    # this fails the journal is the only account of why. A service that dies silently
    # is a black page with nothing behind it — which is exactly what happened once.
    print(_diag(), flush=True)
    try:
        srv = ThreadingHTTPServer((os.environ.get("BENCH_HOST", "0.0.0.0"), PORT), Handler)
    except OSError as e:
        print("bench: could not bind 0.0.0.0:%d — %s" % (PORT, e), flush=True)
        if getattr(e, "errno", None) == 98:
            print("bench: something is already on that port. `ss -ltnp | grep %d`" % PORT,
                  flush=True)
        raise
    tok = _token()
    print("bench on http://0.0.0.0:%d%s" % (PORT, "  (token required)" if tok else "  (token missing; access refused)"),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except BaseException:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise
