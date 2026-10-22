/* All fetches, sockets and native interfaces are local stubs. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path');
const secret='isolated-test-house-credential-only-0000';
const calls=[],sockets=[];
const ctx={Headers,Request,URL,Date,Event,console,
 VINTOS_ENV:{VINTOS_SECRET:secret},location:{href:'capacitor://localhost'},
 localStorage:{getItem:()=>null,setItem:()=>{},removeItem:()=>{}},
 fetch:async(input,init={})=>{calls.push({input,init});return {ok:true,status:200,json:async()=>({ws:{telemetry:'telemetry-ticket',events:'events-ticket'},media_token:'media-ticket'})};},
 WebSocket:function(url,protocols){sockets.push({url,protocols});},dispatchEvent:()=>{}};
ctx.globalThis=ctx;
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../house_auth_client.js'),'utf8'),ctx);
(async()=>{
 await ctx.fetch('http://100.72.225.119:8500/api/history');
 assert.equal(calls[1].input,'https://aegis.tailaa3de5.ts.net:8443/api/history');
 assert.equal(calls[1].init.headers.get('X-Vintos-Secret'),secret);
 await ctx.fetch('https://external.invalid/data');assert.equal(calls[2].init.headers,undefined);
 for(const name of ['telemetry','events']){
  await ctx.VintosAuth.socket('wss://aegis.tailaa3de5.ts.net:8443/ws/'+name);
  const socket=sockets.at(-1);assert.equal(socket.url,'wss://aegis.tailaa3de5.ts.net:8443/ws/'+name);
  assert.equal(socket.protocols[1],'vintos-token.'+name+'-ticket');assert(!socket.url.includes(secret));
 }
 assert.equal(calls.filter(c=>String(c.input).endsWith('/api/auth/session')).length,1);
 assert(ctx.VintosAuth.mediaURL('/api/music/stream/a.mp3').includes('access_token=media-ticket'));
 assert.equal(ctx.VintosAuth.mediaURL('https://external.invalid/api/art/x'),'https://external.invalid/api/art/x');
 await assert.rejects(()=>ctx.VintosAuth.setSecret('short'));
 const handlers={},kv=new Map(),notifications=[];
 const runner={process:{env:{}},CapacitorKV:{get:k=>({value:kv.get(k)}),set:(k,v)=>kv.set(k,v)},
  CapacitorNotifications:{schedule:async x=>notifications.push(x)},Date,Math,
  fetch:async(url,init)=>{assert.equal(init.headers['X-Vintos-Secret'],secret);return {ok:true,json:async()=>({pending:false})};},
  addEventListener:(name,fn)=>handlers[name]=fn};
 vm.createContext(runner);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),runner);
 const event=(name,args)=>new Promise((resolve,reject)=>handlers[name](resolve,reject,args));
 await event('configureHouse',{VINTOS_SECRET:secret,VINTOS_API_BASE:'https://house.invalid'});
 await event('checkOutreach');assert.equal(notifications.length,0);
 console.log('PASS house client: HTTP identity, provider isolation, both WS audiences, media, native KV outreach; no sends');
})().catch(error=>{console.error(error);process.exit(1);});
