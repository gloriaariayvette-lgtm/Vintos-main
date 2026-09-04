#!/usr/bin/env node
// Upstash-REST-compatible proxy over a plain local Redis. Zero dependencies (RESP over net).
// Exactly what @agent-room/upstash-client and the web client speak:
//   POST /          body: ["GET","k"]            -> {"result": ...}
//   POST /pipeline  body: [["GET","k"],["LLEN","l"]] -> [{"result":...},{"result":...}]
//   Authorization: Bearer <UPSTASH_TOKEN>
import http from 'node:http'; import net from 'node:net';
const PORT = +(process.env.PORT || 8079), TOKEN = process.env.UPSTASH_TOKEN || 'change-me';
const [RHOST, RPORT] = (process.env.REDIS_ADDR || '127.0.0.1:6379').split(':');
function encode(args){ let s=`*${args.length}\r\n`; for(const a of args){ const b=Buffer.from(String(a)); s+=`$${b.length}\r\n${b}\r\n`; } return s; }
class Resp { constructor(){ this.buf=Buffer.alloc(0); }
  push(c){ this.buf=Buffer.concat([this.buf,c]); }
  parse(){ const r=this._one(0); if(!r) return null; this.buf=this.buf.subarray(r.end); return r; }
  _line(i){ const j=this.buf.indexOf('\r\n',i); return j<0?null:{s:this.buf.subarray(i,j).toString(),end:j+2}; }
  _one(i){ if(i>=this.buf.length) return null; const t=String.fromCharCode(this.buf[i]); const l=this._line(i+1); if(!l) return null;
    if(t==='+') return {value:l.s,end:l.end}; if(t==='-') return {error:l.s,end:l.end}; if(t===':') return {value:Number(l.s),end:l.end};
    if(t==='$'){ const n=+l.s; if(n<0) return {value:null,end:l.end}; if(this.buf.length<l.end+n+2) return null; return {value:this.buf.subarray(l.end,l.end+n).toString(),end:l.end+n+2}; }
    if(t==='*'){ const n=+l.s; if(n<0) return {value:null,end:l.end}; const out=[]; let p=l.end; for(let k=0;k<n;k++){ const e=this._one(p); if(!e) return null; out.push(e.error!==undefined?{error:e.error}:e.value); p=e.end; } return {value:out,end:p}; }
    throw new Error('bad RESP '+t); } }
let sock=null, parser=new Resp(), queue=[], chain=Promise.resolve();
function connect(){ return new Promise((res,rej)=>{ sock=net.connect(+RPORT,RHOST,()=>res()); sock.on('error',e=>{ rej(e); for(const q of queue.splice(0)) q.rej(e); sock=null; });
  sock.on('close',()=>{ sock=null; }); sock.on('data',c=>{ parser.push(c); let r; while((r=parser.parse())){ const q=queue.shift(); if(q) q.res(r); } }); }); }
function cmd(args){ return new Promise(async(res,rej)=>{ if(!sock){ try{ await connect(); }catch(e){ return rej(e);} } queue.push({res,rej}); sock.write(encode(args)); }); }
function run(args){ chain=chain.then(()=>cmd(args)); return chain; }
const server=http.createServer((req,res)=>{
  res.setHeader('access-control-allow-origin','*'); res.setHeader('access-control-allow-headers','authorization,content-type,cache-control,pragma');
  if(req.method==='OPTIONS'){ res.writeHead(204); return res.end(); }
  const auth=req.headers['authorization']||''; if(auth!==`Bearer ${TOKEN}`){ res.writeHead(401,{'content-type':'application/json'}); return res.end('{"error":"Unauthorized"}'); }
  if(req.method!=='POST'){ res.writeHead(405); return res.end(); }
  let body=''; req.on('data',c=>body+=c); req.on('end',async()=>{
    res.setHeader('content-type','application/json'); res.setHeader('cache-control','no-store');
    try{ const j=JSON.parse(body||'null');
      if(req.url.startsWith('/pipeline')){ const out=[]; for(const c of j){ const r=await run(c); out.push(r.error!==undefined?{error:r.error}:{result:r.value}); } return res.end(JSON.stringify(out)); }
      const r=await run(j); if(r.error!==undefined){ res.statusCode=400; return res.end(JSON.stringify({error:r.error})); } return res.end(JSON.stringify({result:r.value}));
    }catch(e){ res.statusCode=500; res.end(JSON.stringify({error:String(e.message||e)})); } });
});
const BIND=process.env.BIND||'127.0.0.1';
server.listen(PORT,BIND,()=>console.log(`[upstash-proxy] ${BIND}:${PORT} -> redis ${RHOST}:${RPORT}`));
