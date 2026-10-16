/* Run the actual bundled voice function with fake media, sockets and HTTP.
   Audio must never start before server completion authorization. */
'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(path.join(root,'clients/mobile/index.html'),'utf8');
const source=html.slice(html.indexOf('function startVoiceCallWithToken('),html.indexOf('    function endVintosCall()'));
const helper=fs.readFileSync(path.join(root,'clients/mobile/stratagem_voice.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function scenario(final,duplicate=false){
  const sent=[],played=[],posted=[],shown={textContent:''};let socket,release;
  class Socket{constructor(){socket=this;this.readyState=1;}send(s){sent.push(JSON.parse(s));}close(){}}
  class AudioContext{
    constructor(){this.currentTime=0;this.destination={};}resume(){}close(){}
    createMediaStreamSource(){return {connect(){}};}
    createScriptProcessor(){return {connect(){},disconnect(){}};}
    createBuffer(_c,n){return {duration:n/24000,getChannelData(){return new Float32Array(n);}};}
    createBufferSource(){return {connect(){},start(){played.push(this);},stop(){}};}
  }
  const request=async(url,options)=>{
    if(url.endsWith('/admit'))return {ok:true,json:async()=>duplicate?{duplicate:true}:{instructions:'sealed capsule'}};
    if(url.endsWith('/complete'))return new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>final});});
    if(url.endsWith('/api/avatar/speak'))return {ok:true,json:async()=>({})};
    throw new Error('unexpected HTTP '+url);
  };
  const ctx={console,voiceGeneration:0,API:'',CONFIG:{secret:'test-secret'},VintosUI:{request},
    navigator:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[],getTracks:()=>[]})}},
    WebSocket:Socket,AudioContext,document:{getElementById:()=>shown},
    atob:s=>Buffer.from(s,'base64').toString('binary'),btoa:s=>Buffer.from(s,'binary').toString('base64'),
    setInterval:()=>1,clearInterval(){},_vcRefreshFraming(){},_vcPostVoiceTurn:(g,v,m)=>posted.push({g,v,m}),alert(){},setTimeout};
  ctx.window=ctx;vm.createContext(ctx);vm.runInContext(helper+'\n'+source,ctx);
  ctx.startVoiceCallWithToken('fake','identity','grok');await tick();socket.onopen();
  assert.strictEqual(sent[0].session.turn_detection,null,'provider must not auto-generate');
  socket.onmessage({data:JSON.stringify({type:'conversation.item.input_audio_transcription.completed',item_id:'input-1',transcript:'hello'})});
  await tick();
  if(duplicate){assert(!sent.some(e=>e.type==='response.create'));return;}
  assert(sent.some(e=>e.type==='response.create'&&e.response.instructions.includes('sealed capsule')));
  socket.onmessage({data:JSON.stringify({type:'response.created',response:{id:'response-1'}})});
  socket.onmessage({data:JSON.stringify({type:'response.output_audio.delta',response_id:'response-1',delta:'AAAAAA=='})});
  socket.onmessage({data:JSON.stringify({type:'response.output_audio_transcript.delta',response_id:'response-1',delta:'private draft'})});
  assert.strictEqual(played.length,0);assert.strictEqual(shown.textContent,'');
  socket.onmessage({data:JSON.stringify({type:'response.done',response:{id:'response-1'}})});
  await tick();assert.strictEqual(played.length,0,'hold audio until server rechecks authorization');
  release();await tick();await tick();
  assert.strictEqual(played.length,final.allowed&&!final.changed?1:0);
  if(final.allowed){assert.strictEqual(shown.textContent,final.reply);}
  if(!final.allowed){assert(posted.every(p=>p.v===''),'stopped output must not enter client history');}
}
(async()=>{
  await scenario({allowed:true,reply:'Public words.',changed:false});
  await scenario({allowed:false,reply:''});
  await scenario({allowed:true,reply:'Clean words.',changed:true});
  await scenario({},true);
  console.log('4/4 realtime client playback/admission scenarios passed');
})().catch(error=>{console.error(error);process.exit(1);});
