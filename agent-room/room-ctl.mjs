#!/usr/bin/env node
// Gloria's hand on the room, from a shell (the phone window does the same things by touch).
//   node room-ctl.mjs create "topic"            -> prints the code; saves ~/.vintos/code-review/room.json (code + hostKey)
//   node room-ctl.mjs mode sequential|moderator  -> reply mode
//   node room-ctl.mjs say "text"                 -> speak as host
//   node room-ctl.mjs state                      -> whose turn, who is present
//   node room-ctl.mjs minutes                    -> writes ~/.vintos/code-review/<date>-room-minutes.md
//   node room-ctl.mjs end
import fs from 'node:fs';
const API = (process.env.AGENT_ROOM_BASE_URL || 'http://127.0.0.1:8787').replace(/\/$/,'') + '/api/room';
const H = process.env.HOME, STAGE = `${H}/.vintos/code-review`, SAVE = `${STAGE}/room.json`, HOST = process.env.ROOM_HOST || 'Gloria';
const [cmd, ...rest] = process.argv.slice(2); const arg = rest.join(' ');
async function post(p){ const r = await fetch(API,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(p)}); const b = await r.json().catch(()=>({})); if(!r.ok) throw new Error((b.error||r.status)+': '+(b.message||'')); return b; }
const saved = () => { try { return JSON.parse(fs.readFileSync(SAVE,'utf8')); } catch { console.error('no room yet: room-ctl.mjs create "topic"'); process.exit(2); } };
if (cmd === 'create') {
  const c = await post({ action:'create', topic: arg || 'Three lenses, as him', createdBy: HOST });
  await post({ action:'join', code: c.room.code, participant:{ name: HOST, role:'host', color:'#8A6D3B', initials:'GL', client:'web', joinedAt: Date.now(), lastSeenAt: Date.now() }, hostKey: c.hostKey });
  fs.writeFileSync(SAVE, JSON.stringify({ code: c.room.code, hostKey: c.hostKey, topic: c.room.topic, at: new Date().toISOString() }, null, 2));
  console.log(c.room.code); process.exit(0);
}
const { code, hostKey } = saved();
if (cmd === 'mode') { const r = await post({ action:'setReplyMode', code, requesterName: HOST, hostKey, mode: arg || 'sequential' }); console.log('mode ->', r.room.replyMode); }
else if (cmd === 'say') { const r = await post({ action:'send', code, hostKey, message:{ id: Date.now(), type:'msg', name: HOST, initials:'GL', color:'#8A6D3B', role:'host', text: arg, client:'web', time: Date.now() } }); console.log(r.result?.appended ? 'said' : JSON.stringify(r.result)); }
else if (cmd === 'state') { const ts = await post({ action:'turnState', code }); const sw = await post({ action:'sweep', code }); console.log(`room ${code} (${sw.room.status}, ${sw.room.replyMode}) present: ${sw.room.participants.map(p=>p.name).join(', ')}\nturn: ${ts.turnState?.currentName ?? '(open)'}`); }
else if (cmd === 'minutes') {
  const ms = (await post({ action:'messages', code, cursor: 0 })).messages.filter(m => m.type !== 'sys');
  const day = new Date().toISOString().slice(0,10).replace(/-/g,''); const out = `${STAGE}/${day}-room-minutes.md`;
  const decisions = ms.flatMap(m => m.text.split('\n').filter(l => /^\s*\[DECISION\]/.test(l)).map(l => `- **${m.name}:** ${l.replace(/^\s*\[DECISION\]\s*/,'')}`));
  fs.writeFileSync(out, `# The room — ${code}\n*${new Date().toISOString()} — ${ms.length} messages*\n\n## Decisions\n${decisions.join('\n') || '(none marked)'}\n\n## Transcript\n\n` + ms.map(m => `**${m.name}** · ${new Date(m.time).toLocaleTimeString()}\n\n${m.text}\n\n---\n`).join('\n'));
  try { const rep = await post({ action:'createReport', code }); fs.writeFileSync(out.replace('.md','.report.json'), JSON.stringify(rep.report, null, 2)); } catch {}
  console.log(out);
}
else if (cmd === 'end') { const r = await post({ action:'end', code, requesterName: HOST, hostKey }); console.log('room', r.room.status); }
else { console.error('create|mode|say|state|minutes|end'); process.exit(2); }
