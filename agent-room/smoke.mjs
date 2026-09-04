#!/usr/bin/env node
const API = (process.env.AGENT_ROOM_BASE_URL || 'http://127.0.0.1:8787') + '/api/room';
async function post(p){ const r = await fetch(API,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(p)}); const b = await r.json(); if(!r.ok){ const e=new Error(b.message); e.name=b.error; throw e; } return b; }
const P = (name, ini) => ({ name, role:'lens', color:'#1F5F6B', initials: ini, client:'cc', joinedAt: Date.now(), lastSeenAt: Date.now() });
const M = (name, ini, text, client='cc') => ({ id: Date.now()+Math.floor(Math.random()*999), type:'msg', name, initials: ini, color:'#1F5F6B', role:'lens', text, client, time: Date.now() });
const ok = (c, m) => console.log((c?'PASS ':'FAIL ') + m) || (c ? 0 : process.exit(1));
const c = await post({ action:'create', topic:'smoke: three lenses', createdBy:'Gloria' }); const code = c.room.code, hostKey = c.hostKey; ok(!!code && !!hostKey, `create -> ${code} (hostKey ${hostKey.length} chars)`);
const host = await post({ action:'join', code, participant:{...P('Gloria','GL'), client:'web'}, hostKey }); ok(host.participant.name==='Gloria', 'host joins with hostKey');
const f = await post({ action:'join', code, participant: P('Fable','FA') }); const a = await post({ action:'join', code, participant: P('Astra','AS') }); const g = await post({ action:'join', code, participant: P('Grok','GR') });
ok([f,a,g].every(x=>x.participant && x.room.participants.length>=2), `three seats joined (${g.room.participants.map(p=>p.name).join(', ')})`);
let bad=null; try { await post({ action:'setReplyMode', code, requesterName:'Gloria', hostKey:'wrong', mode:'sequential' }); } catch(e){ bad=e.name; } ok(bad==='HostNameTakenError', 'set_mode with a wrong hostKey is refused');
const seq = await post({ action:'setReplyMode', code, requesterName:'Gloria', hostKey, mode:'sequential', config:{ leadAgentName:'Fable', leadAgentClient:'cc' } }).catch(async e => post({ action:'setReplyMode', code, requesterName:'Gloria', hostKey, mode:'sequential' }));
ok(seq.room.replyMode==='sequential', `mode -> ${seq.room.replyMode}`);
await post({ action:'send', code, message: M('Gloria','GL','Begin. Each of you: address the others\' finals.','web'), hostKey }); 
const ts = await post({ action:'turnState', code }); ok(!!ts.turnState && !!ts.turnState.currentName, `turn opened: current speaker = ${ts.turnState?.currentName} (${ts.turnState?.currentRole})`);
const cur = ts.turnState.currentName; const other = ['Fable','Astra','Grok'].find(n=>n!==cur);
let nyt=null; try { await post({ action:'send', code, message: M(other, other.slice(0,2).toUpperCase(), 'jumping in') }); } catch(e){ nyt=e.name; } ok(nyt==='NotYourTurnError', `${other} speaking out of turn -> ${nyt}`);
const sent = await post({ action:'send', code, message: M(cur, cur.slice(0,2).toUpperCase(), '[DECISION] the intent ledger belongs in the voice framing. Agreed.') }); ok(sent.result.appended===true, `${cur} speaks in turn (role ${sent.result.metadata.roleAtSend})`);
const ms = await post({ action:'messages', code, cursor: 0 }); ok(ms.messages.length>=2 && typeof ms.total==='number', `messages -> ${ms.messages.length} (total ${ms.total})`);
const sw = await post({ action:'sweep', code }); ok(sw.room.code===code, 'sweep returns the room');
const rep = await post({ action:'createReport', code }); ok(!!rep.report && Array.isArray(rep.report.decisions ?? rep.report.messages ?? []), `report created (${Object.keys(rep.report).slice(0,6).join(', ')})`);
const ended = await post({ action:'end', code, requesterName:'Gloria', hostKey }); ok(ended.room.status==='ended', 'host ends the room');
console.log('SMOKE OK', code);
