#!/usr/bin/env python3
"""server.py — the bench, as a page. Her agents, manageable from her phone.

The ledger is useless if approving a task means remembering a command. This is the
layout Buzz uses — a rail of agents down one side, the work in the middle, one card
per task with the two buttons that matter — in a single file with no build step, no
node, no bundle. It is stdlib only, so it survives on Aegis without anything to keep
installed and can be edited in place.

    python3 server.py                 serve on 0.0.0.0:8791 (the tailnet)
    BENCH_PORT=... python3 server.py

If ~/.vintos/.bench-token exists, every request must carry it as ?t=<token>. If it
does not exist, the page is open on the tailnet, which is the same posture as his
other rooms.

It is NOT the agent room, and it does not read his memory. It reads and writes the
bench's own ledgers, through bench.py, and nothing else.
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench as B

PORT = int(os.environ.get("BENCH_PORT", "8791"))
TOKEN_FILE = os.path.expanduser("~/.vintos/.bench-token")

# Buzz's dark palette, taken from web/src/shared/styles/globals.css (Apache-2.0).
PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>bench</title>
<style>
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
header{position:sticky;top:0;z-index:5;background:var(--bg);
  border-bottom:1px solid var(--border);padding:14px 16px calc(14px + env(safe-area-inset-top)) 16px;
  padding-top:calc(14px + env(safe-area-inset-top));display:flex;align-items:center;gap:12px}
header h1{margin:0;font-size:16px;font-weight:600;letter-spacing:.02em}
header .count{margin-left:auto;font-size:13px;color:var(--muted-fg)}
.wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:0}
@media(min-width:900px){.wrap{grid-template-columns:260px minmax(0,1fr)}}
nav{border-bottom:1px solid var(--border);padding:10px 12px;display:flex;gap:8px;overflow-x:auto;
  -webkit-overflow-scrolling:touch}
@media(min-width:900px){nav{flex-direction:column;border-bottom:0;border-right:1px solid var(--border);
  min-height:calc(100vh - 56px);overflow:visible}}
nav button{flex:0 0 auto;background:transparent;color:var(--muted-fg);border:1px solid transparent;
  border-radius:var(--radius);padding:9px 12px;font:inherit;font-size:14px;text-align:left;cursor:pointer}
nav button.on{background:var(--muted);color:var(--fg);border-color:var(--border)}
nav button .sub{display:block;font-size:11px;color:var(--muted-fg);margin-top:2px}
main{padding:16px;min-width:0}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:14px;margin:0 0 12px}
.card .top{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.id{font:12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted-fg)}
.kind{font-size:12px;background:var(--muted);border-radius:999px;padding:3px 9px;color:var(--fg)}
.who{font-size:12px;color:var(--primary)}
.what{margin:9px 0 0;font-size:15px}
.why{margin:6px 0 0;font-size:13px;color:var(--muted-fg)}
.row{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
button.act{flex:1 1 140px;min-height:44px;border-radius:var(--radius);border:1px solid var(--border);
  font:inherit;font-weight:600;cursor:pointer}
button.yes{background:var(--primary);color:var(--primary-fg);border-color:transparent}
button.no{background:transparent;color:var(--destructive);border-color:var(--destructive)}
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
</style>
<header><h1>bench</h1><span class="count" id="count"></span></header>
<div class="wrap"><nav id="nav"></nav><main id="main"><div class="empty">loading…</div></main></div>
<script>
const T = new URLSearchParams(location.search).get('t');
const q = p => T ? p + (p.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(T) : p;
let S = {agents:{}, tasks:[]}, view = 'pending', err = '';

const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function load(){
  try{ const r = await fetch(q('/api/state')); if(!r.ok) throw new Error('HTTP '+r.status);
       S = await r.json(); err=''; }
  catch(e){ err = String(e.message||e); }
  draw();
}
async function act(path, body){
  try{
    const r = await fetch(q(path), {method:'POST', headers:{'Content-Type':'application/json'},
                                    body: JSON.stringify(body)});
    const d = await r.json();
    if(d.error) err = d.error; else err='';
  }catch(e){ err = String(e.message||e); }
  load();
}
function drawNav(){
  const pend = S.tasks.filter(t=>t.state==='proposed').length;
  const items = [['pending','waiting on you', pend ? pend+' to approve' : 'nothing waiting'],
                 ['all','every task', S.tasks.length+' total']];
  for(const [name,cfg] of Object.entries(S.agents)){
    const open = S.tasks.filter(t=>t.owner===name && ['proposed','approved','claimed'].includes(t.state)).length;
    items.push(['a:'+name, name, open ? open+' open' : 'idle']);
  }
  document.getElementById('nav').innerHTML = items.map(([k,l,s]) =>
    `<button class="${view===k?'on':''}" onclick="view='${k}';draw()">${esc(l)}<span class="sub">${esc(s)}</span></button>`).join('');
  document.getElementById('count').textContent = pend ? pend+' waiting on you' : 'all clear';
}
function taskCard(t, withButtons){
  const hist = (t.history||[]).map(h=>`${h.at.slice(11,16)} ${h.event}${h.by?' · '+h.by:''}${h.result?' — '+esc(h.result).slice(0,120):''}${h.why?' — '+esc(h.why).slice(0,120):''}`).join('<br>');
  return `<div class="card">
    <div class="top"><span class="id">${esc(t.task)}</span>
      <span class="kind">${esc(t.kind||'—')}</span>
      <span class="who">${esc(t.by)} → ${esc(t.owner)}</span>
      <span class="state ${esc(t.state)}" style="margin-left:auto">${esc(t.state)}</span></div>
    <p class="what">${esc(t.what)}</p>
    ${t.why?`<p class="why">${esc(t.why)}</p>`:''}
    ${withButtons&&t.state==='proposed'?`<div class="row">
      <button class="act yes" onclick="act('/api/approve',{task:'${t.task}'})">Approve</button>
      <button class="act no" onclick="deny('${t.task}')">Deny</button></div>`:''}
    ${hist?`<div class="hist">${hist}</div>`:''}
  </div>`;
}
function deny(id){
  const why = prompt('Why not?') ; if(why===null) return;
  act('/api/deny',{task:id, why:why});
}
function draw(){
  drawNav();
  const m = document.getElementById('main');
  let h = err ? `<div class="err">${esc(err)}</div>` : '';
  if(view==='pending'){
    const rows = S.tasks.filter(t=>t.state==='proposed');
    h += rows.length ? '<h2>waiting on you</h2>' + rows.map(t=>taskCard(t,true)).join('')
                     : '<div class="empty">Nothing waiting on you.</div>';
  } else if(view==='all'){
    const open = S.tasks.filter(t=>['proposed','approved','claimed'].includes(t.state));
    const shut = S.tasks.filter(t=>!['proposed','approved','claimed'].includes(t.state)).reverse();
    h += open.length?'<h2>open</h2>'+open.map(t=>taskCard(t,true)).join(''):'';
    h += shut.length?'<h2>closed</h2>'+shut.slice(0,40).map(t=>taskCard(t,false)).join(''):'';
    if(!open.length&&!shut.length) h += '<div class="empty">No tasks yet.</div>';
  } else {
    const name = view.slice(2), cfg = S.agents[name]||{};
    const d = cfg.delegate||{}, keys = Object.keys(d);
    h += `<div class="card"><div class="top"><strong>${esc(name)}</strong></div>
      <p class="why">${esc(cfg.what||'')}</p>
      ${keys.length?`<div class="deleg">hands down: ${keys.map(k=>`<code>${esc(k)}</code> → ${esc(d[k])}`).join(' · ')}</div>`:''}
      ${(cfg.keeps||[]).length?`<div class="deleg">keeps: ${cfg.keeps.map(k=>`<code>${esc(k)}</code>`).join(' ')}</div>`:''}
      <div class="deleg">starts unasked: ${(cfg.auto_approve||[]).length?cfg.auto_approve.map(k=>`<code>${esc(k)}</code>`).join(' '):'nothing — everything waits on you'}</div>
    </div>`;
    const rows = S.tasks.filter(t=>t.owner===name||t.by===name).reverse();
    h += rows.length?'<h2>its ledger</h2>'+rows.slice(0,60).map(t=>taskCard(t,true)).join('')
                    :'<div class="empty">Nothing in this ledger yet.</div>';
  }
  m.innerHTML = h;
}
load(); setInterval(load, 5000);
</script>
"""


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except Exception:
        return ""


def _state():
    tasks = [t for t in B._all() if t]
    tasks.sort(key=lambda t: t.get("proposed_at") or "")
    return {"agents": B.agents(), "tasks": tasks}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _authed(self):
        want = _token()
        if not want:
            return True
        got = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("t", [""])[0]
        return got == want

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._authed():
            return self._send(403, json.dumps({"error": "bad or missing token"}))
        if path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if path == "/api/state":
            return self._send(200, json.dumps(_state()))
        if path == "/health":
            return self._send(200, json.dumps({"ok": True}))
        self._send(404, json.dumps({"error": "no such path"}))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._authed():
            return self._send(403, json.dumps({"error": "bad or missing token"}))
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
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
            return self._send(404, json.dumps({"error": "no such path"}))
        if t is None:
            return self._send(200, json.dumps({"error": why}))
        self._send(200, json.dumps({"ok": True, "task": t["task"], "state": t["state"]}))


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    tok = _token()
    print("bench on http://0.0.0.0:%d%s" % (PORT, "  (token required)" if tok else "  (open on the tailnet)"),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
