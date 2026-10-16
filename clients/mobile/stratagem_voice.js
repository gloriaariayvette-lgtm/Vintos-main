/* One response admission per provider input event. No vault objectives are sent
   to the browser; audio is held until the server checks stop/revocation/expiry. */
(function(root){
  'use strict';
  async function post(request, base, secret, action, body){
    const response=await request(base+'/api/voice/stratagem/'+action,{
      method:'POST',headers:{'Content-Type':'application/json','X-Vintos-Secret':secret},body:JSON.stringify(body)});
    if(!response.ok)throw new Error('Voice authorization unavailable');
    const value=await response.json();if(value.error)throw new Error(value.error);return value;
  }
  root.VintosStratagemVoice={
    admit:(request,base,secret,transcript,eventId)=>post(request,base,secret,'admit',{transcript,event_id:eventId}),
    eligible:(request,base,secret,eventId)=>post(request,base,secret,'eligible',{event_id:eventId}),
    complete:(request,base,secret,reply,eventId)=>post(request,base,secret,'complete',{reply,event_id:eventId})
  };
  if(typeof module!=='undefined')module.exports=root.VintosStratagemVoice;
})(typeof window!=='undefined'?window:globalThis);
