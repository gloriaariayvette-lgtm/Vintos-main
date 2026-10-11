const fs=require('fs'),vm=require('vm'),assert=require('assert');
async function check(file){
 const page=fs.readFileSync(file,'utf8');
 const nodes=new Map(),events=new Map();let requests=[];
 class El{
  constructor(id=''){this.id=id;this.parentNode=null;this.children=[];this.dataset={};this.value='';if(id)nodes.set(id,this);}
  appendChild(el){if(el.parentNode)el.parentNode.children=el.parentNode.children.filter(x=>x!==el);this.children.push(el);el.parentNode=this;return el;}
  insertAdjacentElement(_,el){this.parentNode.appendChild(el);}
  set innerHTML(html){for(const child of this.children){nodes.delete(child.id);for(const c of child.children)nodes.delete(c.id);}this.children=[];this.html=html;for(const m of html.matchAll(/id="([^"]+)"/g))this.appendChild(new El(m[1]));}
  get innerHTML(){return this.html||'';}
  closest(){return this;}
 }
 const root=new El('root');for(const id of ['wb-incoming','wb-caps','wb-incoming-count','wb-routed-count','wb-discussion','wb-steps-panel'])root.appendChild(new El(id));
 const doc={getElementById:id=>nodes.get(id)||null,addEventListener:(name,fn)=>{if(!events.has(name))events.set(name,[]);events.get(name).push(fn);}};
 const wants=[{id:'first',want:'Inspect sourced protein',capability:'multistep',steps:[{capability:'web_search',note:'First source'}]},{id:'second',want:'Write report',capability:'multistep',steps:[{capability:'creative_write',note:'Second source'}]}];
 const context=vm.createContext({document:doc,Date,console,setTimeout:()=>{},alert:()=>{},API:'http://test.invalid',CONFIG:{secret:'test-only'},VintosUI:{request:async(url,opts)=>{requests.push({url,opts});assert(url.startsWith('http://test.invalid'));return {json:async()=>({success:true,wants,steps:[{capability:'web_search'}]})};}},_esc:s=>String(s),_jsArg:s=>String(s)});
 const start=page.indexOf('const WB_CAPS ='),end=page.indexOf('async function loadFulfilledWants',start);
 assert(end>start);vm.runInContext(page.slice(start,end),context);
 await vm.runInContext('_wbLoad()',context);
 assert(events.has('click'),'semantic click handler missing');
 const tap=(action,wid,extra={})=>{const target=new El();target.dataset={wbaction:action,wid,...extra};for(const fn of events.get('click'))fn({target});};
 vm.runInContext("_wbDisc='first';_wbRender()",context);
 tap('steps','second');
 assert.strictEqual(vm.runInContext('_wbDisc',context),null,'discussion still hides steps');
 let panel=doc.getElementById('wb-steps-panel');assert(panel.innerHTML.includes('Second source'));assert.strictEqual(panel.parentNode.id,'wbc-second','steps must appear in tapped card');
 vm.runInContext('_wbRender()',context);assert.strictEqual(doc.getElementById('wb-steps-panel'),panel);assert.strictEqual(panel.parentNode.id,'wbc-second');
 tap('steps','first');assert.strictEqual(panel.parentNode.id,'wbc-first');assert(panel.innerHTML.includes('First source'));
 tap('addstep','first');tap('pickstepcap','first',{cap:'web_search'});assert(panel.innerHTML.includes('data-wbaction="confirmstep"'));
 tap('closesteps');assert.strictEqual(panel.innerHTML,'');assert.strictEqual(vm.runInContext('_wbStepWid',context),null);
 assert(requests.every(x=>!x.opts.method),'inspection must not write to an account');
 console.log('PASS',file,'click opens selected card despite discussion, survives refresh, switches cards, add-step selection and close; requests isolated');
}
(async()=>{for(const file of process.argv.slice(2))await check(file);})().catch(e=>{console.error(e);process.exit(1);});
