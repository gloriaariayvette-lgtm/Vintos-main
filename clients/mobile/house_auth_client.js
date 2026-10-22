/* Runtime enrollment, authenticated reads and short-lived WebSocket/media tickets. */
(function (root) {
  'use strict';
  const BASE = 'https://aegis.tailaa3de5.ts.net:8443';
  const aliases = new Set(['aegis.tailaa3de5.ts.net', '100.72.225.119', '127.0.0.1', 'localhost']);
  const rawFetch = root.fetch.bind(root);
  const NativeWebSocket = root.WebSocket;
  let enrolled = '', session = null, pending = null, enrollment = null;
  function environment() {
    return root.VINTOS_ENV || (typeof process !== 'undefined' && process.env) || {};
  }
  function stored() {
    try { return root.localStorage.getItem('VINTOS_SECRET') || ''; } catch (_) { return ''; }
  }
  function secret() { return String(enrolled || environment().VINTOS_SECRET || stored()).trim(); }
  function configured(value) { return typeof value === 'string' && value.length >= 32 && value === value.trim(); }
  function api() { return String(environment().VINTOS_API_BASE || BASE).replace(/\/$/, ''); }
  function houseURL(value) {
    if(typeof value==='string' && value.startsWith('/') && !value.startsWith('//'))return true;
    const url = new URL(typeof value === 'string' ? value : (value.href || value.url), root.location && root.location.href || api());
    const target = new URL(api());
    return url.origin === target.origin || (aliases.has(url.hostname) && (url.port === '8500' || url.port === '8443'));
  }
  function canonical(value) {
    const url = new URL(typeof value === 'string' ? value : (value.href || value.url), root.location && root.location.href || api());
    if (!houseURL(url.href)) return url.href;
    return api() + url.pathname + url.search + url.hash;
  }
  async function provisionRunner() {
    const runner = root.Capacitor && root.Capacitor.Plugins && root.Capacitor.Plugins.BackgroundRunner;
    if (runner && runner.dispatchEvent) {
      await runner.dispatchEvent({label:'dev.vintos.outreach-check', event:'configureHouse',
        details:{VINTOS_SECRET:secret(), VINTOS_API_BASE:api()}});
    }
  }
  async function setSecret(value) {
    if (!configured(value)) throw new Error('Use the newly provisioned house credential.');
    // Validate before replacing a working enrollment or changing the background runner.
    const response = await rawFetch(api()+'/api/auth/session', {
      method:'POST', headers:{'X-Vintos-Secret':value}, credentials:'include', cache:'no-store'});
    if (!response.ok) throw new Error('The house did not accept this credential.');
    const body = await response.json();
    enrolled=value; session=Object.assign(body,{until:Date.now()+45000});
    try { root.localStorage.setItem('VINTOS_SECRET',value); root.localStorage.removeItem('vintosSecret'); } catch (_) {}
    provisionRunner().catch(()=>{root.dispatchEvent(new Event('vintos-runner-enrollment-failed'));});
    signExistingMedia();
  }
  async function ensure(force=false) {
    if (!force && configured(secret())) return;
    if (enrollment) return enrollment;
    enrollment = new Promise((resolve) => {
      const show = () => {
        const box = root.document.createElement('div');
        box.id='house-enrollment'; box.setAttribute('role','dialog');
        box.style.cssText='position:fixed;inset:0;background:#1c1e22;color:white;z-index:200000;display:grid;place-items:center;padding:24px';
        const form=root.document.createElement('form');
        const title=root.document.createElement('h2'); title.textContent='Connect to Vintos';
        const input=root.document.createElement('input'); input.type='password'; input.autocomplete='current-password'; input.placeholder='House credential'; input.required=true;
        const button=root.document.createElement('button');button.type='submit';button.textContent='Connect';
        const status=root.document.createElement('p');status.setAttribute('role','status');
        form.append(title,input,button,status);box.append(form);root.document.body.append(box);
        form.onsubmit=async(event)=>{event.preventDefault();button.disabled=true;
          try {await setSecret(input.value);input.value='';box.remove();enrollment=null;resolve();}
          catch (_) {status.textContent='Connection failed. Check the house credential and try again.';button.disabled=false;}
        };
      };
      if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',show,{once:true});else show();
    });
    return enrollment;
  }
  async function getSession() {
    await ensure();
    if (session && Date.now()<session.until) return session;
    if (!pending) pending=(async()=>{
      const response=await rawFetch(api()+'/api/auth/session',{method:'POST',
        headers:{'X-Vintos-Secret':secret()},credentials:'include',cache:'no-store'});
      if(response.status===401){session=null;await ensure(true);return session;}
      if(!response.ok)throw new Error('House enrollment requires renewal.');
      session=Object.assign(await response.json(),{until:Date.now()+45000});
      return session;
    })().finally(()=>{pending=null;});
    return pending;
  }
  async function request(input,init={}) {
    if (!houseURL(input)) return rawFetch(input,init);
    await getSession();
    const headers=new Headers((typeof Request!=='undefined' && input instanceof Request) ? input.headers : {});
    new Headers(init.headers||{}).forEach((value,key)=>headers.set(key,value));
    headers.set('X-Vintos-Secret',secret());
    const url=canonical(input);
    const target=(typeof Request!=='undefined' && input instanceof Request) ? new Request(url,input) : url;
    const response=await rawFetch(target,Object.assign({},init,{headers,credentials:'include'}));
    if(response.status===401){session=null;ensure(true).catch(()=>{});}
    return response;
  }
  async function socket(url) {
    const target=new URL(canonical(url));
    if(!houseURL(target.href)||!['/ws/telemetry','/ws/events'].includes(target.pathname))throw new Error('Unsupported house stream');
    const tickets=await getSession();
    target.protocol=target.protocol==='https:'?'wss:':target.protocol==='http:'?'ws:':target.protocol;
    const name=target.pathname.split('/').pop();
    return new NativeWebSocket(target.href,['vintos-v1','vintos-token.'+tickets.ws[name]]);
  }
  function mediaURL(value) {
    if(!session||!value||!houseURL(value))return value;
    const url=new URL(canonical(value));
    if(!/^(?:\/avatar\/stage\/(?:clip|speech|still)\/|\/api\/(?:file\/|music\/stream\/|art\/|video\/(?:file|still)\/|voice\/stream\/|avatar\/imprint))/.test(url.pathname))return value;
    if(!url.searchParams.has('access_token'))url.searchParams.set('access_token',session.media_token);
    return url.href;
  }
  function signExistingMedia() {
    if(!root.document||!session)return;
    root.document.querySelectorAll('[src],[poster],a[href]').forEach(node=>{
      ['src','poster','href'].forEach(attr=>{
        const value=node.getAttribute(attr);if(!value)return;
        try {const signed=mediaURL(value);if(signed!==value)node.setAttribute(attr,signed);}catch(_){}
      });
    });
  }
  root.fetch=request;
  root.VintosAuth={secret,api,request,socket,mediaURL,setSecret,getSession,ensure};
  if(root.document){
    const start=()=>{
      if(root.MutationObserver)new root.MutationObserver(signExistingMedia).observe(root.document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['src','poster','href']});
      getSession().then(()=>{signExistingMedia();return provisionRunner();}).catch(()=>{});
    };
    if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  }
})(typeof window==='undefined'?globalThis:window);
