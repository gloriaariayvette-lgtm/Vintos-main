#!/usr/bin/env node
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
const API = process.env.ROOM_API || 'http://127.0.0.1:8787';   // /api/room is forwarded here so the page is same-origin
const DIR = process.env.WEB_DIST, PORT = +(process.env.PORT || 8788), BIND = process.env.BIND || '0.0.0.0';
const T = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml', '.png':'image/png', '.json':'application/json', '.woff2':'font/woff2', '.ico':'image/x-icon' };
http.createServer((req,res)=>{
  if (req.url.startsWith('/api/room')) { let b=''; req.on('data',c=>b+=c); req.on('end', async()=>{ try{ const r=await fetch(API+'/api/room',{method:'POST',headers:{'content-type':'application/json'},body:b}); res.writeHead(r.status,{'content-type':'application/json','cache-control':'no-store'}); res.end(await r.text()); }catch(e){ res.writeHead(502,{'content-type':'application/json'}); res.end(JSON.stringify({error:'RoomApiError',message:'room api unreachable: '+e.message})); } }); return; }
  let p = path.normalize(decodeURIComponent(req.url.split('?')[0])); let f = path.join(DIR, p);
  if (!f.startsWith(DIR) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(DIR, 'index.html');   // SPA fallback
  res.setHeader('content-type', T[path.extname(f)] || 'application/octet-stream'); fs.createReadStream(f).pipe(res);
}).listen(PORT, BIND, () => console.log(`[web] http://${BIND}:${PORT}  (${DIR})`));
