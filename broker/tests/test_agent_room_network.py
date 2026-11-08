#!/usr/bin/env python3
"""The agent room's window listens on loopback only and reaches the tailnet through `tailscale serve`, failing closed
(Gloria, 2026-11-08). Node runs the window's own functions and a real server on loopback with a stub room API;
tailscale is a stub on PATH. Nothing here touches Tailscale, a firewall or the network beyond 127.0.0.1."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
KIT = os.path.join(REPO, "agent-room")
NODE = shutil.which("node")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

def node(js):
    p = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, cwd=KIT)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

STATIC = "file://" + os.path.join(KIT, "static.mjs")

if not NODE:
    print("SKIP no node on this machine"); sys.exit(0)

# --- listener configuration ---
rc, out, err = node("import {resolveBind} from '%s'; console.log(JSON.stringify([resolveBind({}), resolveBind({BIND:'127.0.0.1'}), resolveBind({BIND:'::1'})]))" % STATIC)
check("default bind is loopback; loopback forms accepted", rc == 0 and json.loads(out) == ["127.0.0.1", "127.0.0.1", "::1"], (out, err))
for bad in ("0.0.0.0", "::", "100.64.0.20", "192.168.1.5", ""):
    rc, out, err = node("import {resolveBind} from '%s'; try { resolveBind({BIND:%s}); console.log('accepted') } catch(e) { console.log('refused') }" % (STATIC, json.dumps(bad)))
    expect = "accepted" if bad == "" else "refused"   # empty means unset: loopback
    check("BIND=%r is %s" % (bad, expect), out == expect, (out, err))

env = dict(os.environ, BIND="0.0.0.0", WEB_DIST=tempfile.mkdtemp(), PORT="0")
p = subprocess.run([NODE, os.path.join(KIT, "static.mjs")], env=env, capture_output=True, text=True, timeout=30)
check("started with BIND=0.0.0.0 the window exits instead of listening", p.returncode == 2 and "refusing BIND" in p.stderr, (p.returncode, p.stderr))

unit = open(os.path.join(KIT, "setup-aegis.sh")).read()
web = unit[unit.index("unit agent-room-web"):]
web = web[:web.index('static.mjs"')]
check("the web unit sets BIND=127.0.0.1", "Environment=BIND=127.0.0.1" in web, web)
check("setup never turns Funnel on", "tailscale funnel" not in unit and "funnel" not in open(os.path.join(KIT, "tailnet-window.sh")).read().replace("never Funnel", "").replace("never turns Funnel on", "").lower())

# --- routing and forwarding (a real server on loopback, a stub room API) ---
js = r"""
import http from 'node:http'; import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
import {makeServer, route} from '%s';
const seen = [];
const api = http.createServer((q,s)=>{ let b=''; q.on('data',c=>b+=c); q.on('end',()=>{ seen.push({m:q.method,u:q.url,b}); s.writeHead(200,{'content-type':'application/json'}); s.end('{"ok":true}'); }); });
await new Promise(r=>api.listen(0,'127.0.0.1',r));
const dir = fs.mkdtempSync(path.join(os.tmpdir(),'win-')); fs.writeFileSync(path.join(dir,'index.html'),'<p>window</p>');
const web = makeServer({dir, api:'http://127.0.0.1:'+api.address().port});
await new Promise(r=>web.listen(0,'127.0.0.1',r));
const base = 'http://127.0.0.1:'+web.address().port;
const out = {routes:[route('POST','/api/room'),route('GET','/api/room'),route('POST','/api/roomX'),route('POST','/api/other'),route('GET','/x')]};
let r = await fetch(base+'/api/room',{method:'POST',headers:{'content-type':'application/json'},body:'{"action":"getRoom","code":"A","hostKey":"k"}'});
out.post = [r.status, await r.text()];
r = await fetch(base+'/api/room'); out.get = r.status;
r = await fetch(base+'/api/roomX',{method:'POST',body:'{}'}); out.prefix = r.status;
r = await fetch(base+'/api/other',{method:'POST',body:'{}'}); out.other = r.status;
r = await fetch(base+'/?code=A'); out.page = [r.status, await r.text()];
out.seen = seen; out.addr = web.address().address;
console.log(JSON.stringify(out)); web.close(); api.close();
""" % STATIC
rc, out, err = node(js)
try:
    o = json.loads(out.splitlines()[-1])
except Exception:
    o = {}
check("routes: only POST /api/room goes to the API", o.get("routes") == ["api", "api-method", "api-unknown", "api-unknown", "static"], (out, err))
check("POST /api/room is forwarded with its body unchanged (host keys ride in the body)",
      o.get("post", [0])[0] == 200 and o.get("seen") == [{"m": "POST", "u": "/api/room", "b": '{"action":"getRoom","code":"A","hostKey":"k"}'}], o)
check("GET /api/room is refused, not forwarded", o.get("get") == 405)
check("/api/roomX and other /api paths are 404, not forwarded", o.get("prefix") == 404 and o.get("other") == 404 and len(o.get("seen", [])) == 1, o)
check("the page is still served", o.get("page") == [200, "<p>window</p>"], o.get("page"))

# --- tailscale prerequisites (stub tailscale on PATH) ---
def window(stub):
    d = tempfile.mkdtemp()
    if stub is not None:
        with open(os.path.join(d, "tailscale"), "w") as f: f.write("#!/bin/bash\n" + stub)
        os.chmod(os.path.join(d, "tailscale"), 0o755)
    path = d + ":" + ":".join(x for x in os.environ.get("PATH", "").split(":") if x and not os.path.exists(os.path.join(x, "tailscale")))
    p = subprocess.run(["bash", "-c", '. "%s"; tailnet_window 8788 8789' % os.path.join(KIT, "tailnet-window.sh")],
                       env=dict(os.environ, PATH=path), capture_output=True, text=True, timeout=30)
    url = [l[len("WINDOW_URL="):] for l in p.stdout.splitlines() if l.startswith("WINDOW_URL=")]
    return p.returncode, url[-1] if url else None, p.stdout, d

rc, url, out, _ = window(None)
check("no Tailscale: the window stays local, setup does not fail", rc == 0 and url == "http://127.0.0.1:8788", out)
rc, url, out, _ = window('case "$1" in ip) exit 0;; *) exit 1;; esac\n')
check("Tailscale not up: the window stays local", rc == 0 and url == "http://127.0.0.1:8788" and "not up" in out, out)
rc, url, out, _ = window('case "$1" in ip) echo 100.64.0.9;; serve) exit 1;; status) echo \'{"Self":{"DNSName":"box.example.ts.net."}}\';; esac\n')
check("serve refused: local, and the exact command is printed", url == "http://127.0.0.1:8788"
      and "tailscale serve --bg --https=8789 http://127.0.0.1:8788" in out, out)
rc, url, out, d = window('echo "$@" >> "$(dirname "$0")/calls"\ncase "$1" in ip) echo 100.64.0.9;; serve) exit 0;; status) echo \'{"Self":{"DNSName":"box.example.ts.net."}}\';; esac\n')
calls = open(os.path.join(d, "calls")).read()
check("serve works: the tailnet https address", url == "https://box.example.ts.net:8789", out)
check("serve is the only change: https 8789 to loopback 8788, no funnel", "serve --bg --https=8789 http://127.0.0.1:8788" in calls
      and "funnel" not in calls, calls)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
