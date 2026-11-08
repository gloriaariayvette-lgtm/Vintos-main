#!/usr/bin/env node
// The room's human window. It listens on loopback only and refuses any other address: the phone reaches it through
// `tailscale serve` (HTTPS, tailnet only), never through a listener on every interface (Gloria, 2026-11-08).
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const T = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml', '.png':'image/png', '.json':'application/json', '.woff2':'font/woff2', '.ico':'image/x-icon' };
const LOOPBACK = new Set(['127.0.0.1', '::1', 'localhost']);

// The address to listen on: loopback by default; anything else is refused (throws), so a stray BIND fails closed.
export function resolveBind(env = process.env) {
  const bind = String(env.BIND || '127.0.0.1').trim();
  if (!LOOPBACK.has(bind)) throw new Error(`refusing BIND=${bind}: the window listens on loopback only; reach it through tailscale serve`);
  return bind;
}

// What a request is: the room API (POST to exactly /api/room), a refused API call, or a static file.
export function route(method, url) {
  const p = String(url || '').split('?')[0];
  if (p === '/api/room') return method === 'POST' ? 'api' : 'api-method';
  if (p.startsWith('/api/')) return 'api-unknown';
  return 'static';
}

export function makeServer({ dir, api }) {
  return http.createServer((req, res) => {
    const kind = route(req.method, req.url);
    if (kind === 'api-method') { res.writeHead(405, { allow: 'POST', 'content-type': 'application/json' }); return res.end('{"error":"MethodNotAllowed"}'); }
    if (kind === 'api-unknown') { res.writeHead(404, { 'content-type': 'application/json' }); return res.end('{"error":"NotFound"}'); }
    if (kind === 'api') { let b=''; req.on('data',c=>b+=c); req.on('end', async()=>{ try{ const r=await fetch(api+'/api/room',{method:'POST',headers:{'content-type':'application/json'},body:b}); res.writeHead(r.status,{'content-type':'application/json','cache-control':'no-store'}); res.end(await r.text()); }catch(e){ res.writeHead(502,{'content-type':'application/json'}); res.end(JSON.stringify({error:'RoomApiError',message:'room api unreachable: '+e.message})); } }); return; }
    let p = path.normalize(decodeURIComponent(req.url.split('?')[0])); let f = path.join(dir, p);
    if (!f.startsWith(dir) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(dir, 'index.html');   // SPA fallback
    res.setHeader('content-type', T[path.extname(f)] || 'application/octet-stream'); fs.createReadStream(f).pipe(res);
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let bind;
  try { bind = resolveBind(); } catch (e) { console.error('[web] ' + e.message); process.exit(2); }
  const API = process.env.ROOM_API || 'http://127.0.0.1:8787';   // /api/room is forwarded here so the page is same-origin
  const DIR = process.env.WEB_DIST, PORT = +(process.env.PORT || 8788);
  makeServer({ dir: DIR, api: API }).listen(PORT, bind, () => console.log(`[web] http://${bind}:${PORT}  (${DIR})`));
}
