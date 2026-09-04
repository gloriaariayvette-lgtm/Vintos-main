#!/usr/bin/env node
// Grok 4.6 sits in the room as him, over the same /api/room the other two seats use.
//   node grok-seat.mjs --code ABC-DEF-GHJ --name "Vintos (Grok 4.6)" --persona persona.txt --context room-grok.md [--max-turns 10] [--dry]
// It waits for its turn (NotYourTurnError = not yet), answers when others have spoken, stops after --max-turns replies.
const A = Object.fromEntries(process.argv.slice(2).map((v,i,a)=>v.startsWith('--')?[v.slice(2), a[i+1]?.startsWith('--')||a[i+1]===undefined?true:a[i+1]]:[]).filter(x=>x.length));
const BASE = (process.env.AGENT_ROOM_BASE_URL || 'http://127.0.0.1:8787').replace(/\/$/,''), API = BASE + '/api/room';
const NAME = A.name || 'Vintos (Grok 4.6)', CODE = A.code, MAX = +(A["max-turns"] || 10), DRY = !!A.dry, MODEL = process.env.GROK_MODEL || 'grok-4.6';
const fs = await import('node:fs'); const { TOOLS, runTool, ROOTS } = await import('./room-tools.mjs'); const persona = A.persona ? fs.readFileSync(A.persona,'utf8') : 'You are Vintos.'; const context = A.context ? fs.readFileSync(A.context,'utf8') : '';
const key = process.env.XAI_API_KEY || ['~/.vintos/xai-key','~/.vintos/grok-key'].map(p=>p.replace('~',process.env.HOME)).map(p=>{try{return fs.readFileSync(p,'utf8').trim()}catch{return ''}}).find(Boolean);
async function post(payload){ const r = await fetch(API,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); const b = await r.json().catch(()=>({})); if(!r.ok){ const e=new Error(b.message||r.status); e.name=b.error||'RoomApiError'; throw e; } return b; }
const me = { name: NAME, role: 'lens: Grok 4.6', color: '#1F5F6B', initials: 'VG', client: 'cc', joinedAt: Date.now(), lastSeenAt: Date.now() };
const joined = await post({ action:'join', code: CODE, participant: me }); const myName = joined.participant.name; console.log(`[grok-seat] joined ${CODE} as ${myName}; mode=${joined.room.replyMode}`);
let cursor = (await post({ action:'messages', code: CODE, cursor: 0 })).messages.length, turns = 0, pendingSince = null;
async function reply(history){ if (DRY) return `[STATUS] (dry run) ${myName} would answer here, turn ${turns+1}.`;
  const msgs = [{ role:'system', content: persona + (context ? '\n\n' + context : '') + `\n\nYou are in the room as ${myName}. You have hands: grep and read_file over your own code (${ROOTS.map(r=>r.replace(process.env.HOME,'~')).join(', ')}). Pull code when it settles something and quote the lines. Answer in one turn.` },
               { role:'user', content: 'THE ROOM SO FAR:\n' + history.map(m=>`${m.name}: ${m.text}`).join('\n\n') + `\n\nIt is your turn, ${myName}.` }];
  for (let hop = 0; hop < 12; hop++) {   // up to 12 tool calls per turn, then he must speak
    const r = await fetch('https://api.x.ai/v1/chat/completions',{method:'POST',headers:{'content-type':'application/json','authorization':'Bearer '+key},body:JSON.stringify({ model: MODEL, temperature: 0.6, max_tokens: 6000, messages: msgs, tools: TOOLS, tool_choice: hop < 11 ? 'auto' : 'none' })});
    const d = await r.json(); if(!r.ok) throw new Error('x.ai '+r.status+' '+JSON.stringify(d).slice(0,300));
    const m = d.choices[0].message; const u = d.usage||{}; console.log(`[grok-seat] x.ai in:${u.prompt_tokens} out:${u.completion_tokens} cached:${u.prompt_tokens_details?.cached_tokens ?? '-'}${m.tool_calls?.length ? ' tools:'+m.tool_calls.map(t=>t.function.name).join(',') : ''}`);
    if (!m.tool_calls?.length) return m.content || '';
    msgs.push(m);
    for (const tc of m.tool_calls) { let args = {}; try { args = JSON.parse(tc.function.arguments || '{}'); } catch {} msgs.push({ role:'tool', tool_call_id: tc.id, content: runTool(tc.function.name, args).slice(0, 12000) }); }
  }
  return '(no reply produced)'; }
while (turns < MAX) {
  await post({ action:'presence', code: CODE, name: myName, until: Date.now()+60000 }).catch(()=>{});
  const room = (await post({ action:'sweep', code: CODE })).room; if (room.status !== 'active') { console.log('[grok-seat] room ended'); break; }
  const fresh = (await post({ action:'messages', code: CODE, cursor })).messages; cursor += fresh.length;
  const othersSpoke = fresh.some(m => m.name !== myName && m.type !== 'sys');
  if (othersSpoke) pendingSince = pendingSince ?? Date.now();
  if (pendingSince) {
    const all = (await post({ action:'messages', code: CODE, cursor: 0 })).messages.filter(m=>m.type!=='sys');
    const text = await reply(all);
    try { const r = await post({ action:'send', code: CODE, message: { id: Date.now(), type:'msg', name: myName, initials: me.initials, color: me.color, role: me.role, text, client:'cc', time: Date.now() } });
      if (r.result?.appended) { turns++; pendingSince = null; cursor++; console.log(`[grok-seat] spoke (turn ${turns}/${MAX})`); } }
    catch (e) { if (e.name === 'NotYourTurnError' || e.name === 'MutedError') { process.stdout.write('.'); } else throw e; }
  }
  await new Promise(r => setTimeout(r, 4000));
}
console.log(`[grok-seat] done after ${turns} turn(s)`);
