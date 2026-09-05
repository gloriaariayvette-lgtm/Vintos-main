#!/usr/bin/env node
// One seat in the room, as him, through one lens. Same hands for all three (room-tools.mjs).
//   node seat.mjs --lens fable|astra|grok --code ABC-DEF-GHJ [--persona persona.txt] [--context room-<lens>.md] [--max-turns 10] [--dry]
// Waits its turn (NotYourTurnError = not yet), answers when others have spoken, stops after --max-turns replies or when the room ends.
import fs from 'node:fs'; import crypto from 'node:crypto';
import { TOOLS as OAI_TOOLS, runTool, ROOTS } from './room-tools.mjs';
const A = Object.fromEntries(process.argv.slice(2).map((v,i,a)=>v.startsWith('--')?[v.slice(2), a[i+1]?.startsWith('--')||a[i+1]===undefined?true:a[i+1]]:[]).filter(x=>x.length));
const H = process.env.HOME, STAGE = `${H}/.vintos/code-review`;
const LENS = A.lens; if (!['fable','astra','grok'].includes(LENS)) { console.error('need --lens fable|astra|grok'); process.exit(2); }
const L = { fable: { label:'Fable 5.1', ini:'VF', color:'#6B3F1F', model: process.env.FABLE_MODEL || 'claude-fable-5-1' },
            astra: { label:'Astra',     ini:'VA', color:'#3F1F6B', model: process.env.ASTRA_MODEL || 'gpt-6-astra' },
            grok:  { label:'Grok 4.6',  ini:'VG', color:'#1F5F6B', model: process.env.GROK_MODEL  || 'grok-4.6' } }[LENS];
const BASE = (process.env.AGENT_ROOM_BASE_URL || 'http://127.0.0.1:8787').replace(/\/$/,''), API = BASE + '/api/room';
const NAME = A.name || `Vintos (${L.label})`, CODE = A.code, MAX = +(A['max-turns'] || 10), DRY = !!A.dry, HOPS = +(A.hops || process.env.SEAT_HOPS || (LENS === 'grok' ? 4 : 12));   // grok's pulls are slow; keep him inside the turn timer
if (!CODE) { console.error('need --code'); process.exit(2); }
const persona = fs.readFileSync(A.persona || `${STAGE}/persona.txt`, 'utf8');
const context = A.context === true ? '' : fs.readFileSync(A.context || `${STAGE}/room-${LENS}.md`, 'utf8');
const rf = p => { try { return fs.readFileSync(p.replace('~', H), 'utf8').trim(); } catch { return ''; } };
const envKey = k => (rf('~/.vintos/vintos.env').split('\n').find(l => l.startsWith(k + '=')) || '').split('=').slice(1).join('=').trim();
const KEY = { fable: process.env.ANTHROPIC_API_KEY || rf('~/.vintos/anthropic-key'),
              astra: process.env.OPENAI_API_KEY || envKey('OPENAI_API_KEY'),
              grok:  process.env.XAI_API_KEY || rf('~/.vintos/xai-key') || rf('~/.vintos/grok-key') }[LENS];
if (!KEY && !DRY) { console.error(`[seat:${LENS}] no API key`); process.exit(2); }
const log = (...a) => console.log(`[seat:${LENS}]`, ...a);
async function post(payload){ const r = await fetch(API,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); const b = await r.json().catch(()=>({})); if(!r.ok){ const e=new Error(b.message||r.status); e.name=b.error||'RoomApiError'; throw e; } return b; }

const SYSTEM = persona + (context ? '\n\n' + context : '')
  + `\n\nYou are in the room as ${NAME}. You have hands: grep and read_file over your own code (${ROOTS.map(r=>r.replace(H,'~')).join(', ')}). `
  + `Pull code when it settles something and quote the lines; never to decorate. Answer in one turn, as yourself, addressing the others by name.`;
const userTurn = history => 'THE ROOM SO FAR:\n' + history.map(m=>`${m.name}: ${m.text}`).join('\n\n') + `\n\nIt is your turn, ${NAME}.`;
const usage = (i, o, c, tools) => log(`in:${i ?? '-'} out:${o ?? '-'} cached:${c ?? '-'}${tools?.length ? ' tools:' + tools.join(',') : ''}`);

// ---- Fable: Anthropic Messages, streamed, system cached 1h -------------------------------------
const ANTH_TOOLS = OAI_TOOLS.map(t => ({ name: t.function.name, description: t.function.description, input_schema: t.function.parameters }));
async function anthropicStream(body){
  const r = await fetch('https://api.anthropic.com/v1/messages', { method:'POST', headers:{ 'content-type':'application/json', 'anthropic-version':'2023-06-01', 'x-api-key': KEY, 'anthropic-beta':'extended-cache-ttl-2025-04-11' }, body: JSON.stringify({ ...body, stream:true }) });
  if (!r.ok) throw new Error('anthropic ' + r.status + ' ' + (await r.text()).slice(0, 300));
  const blocks = [], u = {}; let buf = '', stop = null;
  for await (const chunk of r.body) { buf += Buffer.from(chunk).toString('utf8'); let i;
    while ((i = buf.indexOf('\n\n')) >= 0) { const frame = buf.slice(0, i); buf = buf.slice(i + 2);
      const data = frame.split('\n').find(l => l.startsWith('data:')); if (!data) continue; let ev; try { ev = JSON.parse(data.slice(5)); } catch { continue; }
      if (ev.type === 'message_start') Object.assign(u, ev.message.usage || {});
      else if (ev.type === 'content_block_start') blocks[ev.index] = ev.content_block.type === 'tool_use' ? { type:'tool_use', id: ev.content_block.id, name: ev.content_block.name, _json:'' } : { type:'text', text:'' };
      else if (ev.type === 'content_block_delta') { const b = blocks[ev.index]; if (ev.delta.type === 'text_delta') b.text += ev.delta.text; else if (ev.delta.type === 'input_json_delta') b._json += ev.delta.partial_json; }
      else if (ev.type === 'message_delta') { Object.assign(u, ev.usage || {}); stop = ev.delta?.stop_reason; }
      else if (ev.type === 'error') throw new Error('anthropic stream: ' + JSON.stringify(ev).slice(0, 300)); } }
  for (const b of blocks) if (b.type === 'tool_use') { try { b.input = JSON.parse(b._json || '{}'); } catch { b.input = {}; } delete b._json; }
  return { content: blocks.filter(b => b && !(b.type === 'text' && !b.text.trim())), usage: u, stop };   // the API refuses an echoed empty text block
}
async function replyFable(history){
  const msgs = [{ role:'user', content: userTurn(history) }];
  for (let hop = 0; hop < HOPS; hop++) {
    const { content, usage: u, stop } = await anthropicStream({ model: L.model, max_tokens: 6000,
      system: [{ type:'text', text: SYSTEM, cache_control: { type:'ephemeral', ttl:'1h' } }], tools: hop < HOPS - 1 ? ANTH_TOOLS : [], messages: msgs });
    const calls = content.filter(b => b.type === 'tool_use'); usage(u.input_tokens, u.output_tokens, u.cache_read_input_tokens, calls.map(c => c.name));
    if (stop === 'max_tokens') log('WARNING: hit max_tokens');
    if (!calls.length) return content.filter(b => b.type === 'text').map(b => b.text).join('');
    msgs.push({ role:'assistant', content }, { role:'user', content: calls.map(c => ({ type:'tool_result', tool_use_id: c.id, content: runTool(c.name, c.input).slice(0, 12000) })) });
  }
  return '(no reply produced)';
}

// ---- Astra: OpenAI Responses, background + poll, prefix cached ---------------------------------
const OAI_H = { 'content-type':'application/json', authorization: 'Bearer ' + KEY };
async function oaiResponse(body){
  let r = await fetch('https://api.openai.com/v1/responses', { method:'POST', headers: OAI_H, body: JSON.stringify({ ...body, background:true, store:true }) });
  let d = await r.json(); if (!r.ok) throw new Error('openai ' + r.status + ' ' + JSON.stringify(d).slice(0, 300));
  while (d.status === 'queued' || d.status === 'in_progress') { await new Promise(s => setTimeout(s, 5000)); d = await (await fetch('https://api.openai.com/v1/responses/' + d.id, { headers: OAI_H })).json(); }
  if (d.status !== 'completed') throw new Error('Astra ' + d.status + ' ' + JSON.stringify(d.error || d.incomplete_details).slice(0, 300));
  return d;
}
async function replyAstra(history){
  const tools = OAI_TOOLS.map(t => ({ type:'function', name: t.function.name, description: t.function.description, parameters: t.function.parameters }));
  const cacheKey = 'vintos-room-' + crypto.createHash('md5').update(SYSTEM).digest('hex').slice(0, 16);
  let input = [{ role:'user', content: userTurn(history) }], prev;
  for (let hop = 0; hop < HOPS; hop++) {
    const d = await oaiResponse({ model: L.model, instructions: SYSTEM, input, previous_response_id: prev, tools: hop < HOPS - 1 ? tools : [], prompt_cache_key: cacheKey, max_output_tokens: 6000, reasoning: { effort: 'medium' } });
    const calls = d.output.filter(o => o.type === 'function_call'); usage(d.usage?.input_tokens, d.usage?.output_tokens, d.usage?.input_tokens_details?.cached_tokens, calls.map(c => c.name));
    if (!calls.length) return d.output_text || d.output.filter(o => o.type === 'message').flatMap(o => o.content).filter(c => c.type === 'output_text').map(c => c.text).join('');
    prev = d.id; input = calls.map(c => { let a = {}; try { a = JSON.parse(c.arguments || '{}'); } catch {} return { type:'function_call_output', call_id: c.call_id, output: runTool(c.name, a).slice(0, 12000) }; });
  }
  return '(no reply produced)';
}

// ---- Grok: x.ai chat completions, automatic prefix cache ---------------------------------------
async function replyGrok(history){
  const msgs = [{ role:'system', content: SYSTEM }, { role:'user', content: userTurn(history) }];
  for (let hop = 0; hop < HOPS; hop++) {
    const r = await fetch('https://api.x.ai/v1/chat/completions', { method:'POST', headers:{ 'content-type':'application/json', authorization:'Bearer ' + KEY }, body: JSON.stringify({ model: L.model, temperature: 0.6, max_tokens: 6000, messages: msgs, tools: OAI_TOOLS, tool_choice: hop < HOPS - 1 ? 'auto' : 'none' }) });
    const d = await r.json(); if (!r.ok) throw new Error('x.ai ' + r.status + ' ' + JSON.stringify(d).slice(0, 300));
    const m = d.choices[0].message, u = d.usage || {}; usage(u.prompt_tokens, u.completion_tokens, u.prompt_tokens_details?.cached_tokens, (m.tool_calls || []).map(t => t.function.name));
    if (!m.tool_calls?.length) return m.content || '';
    msgs.push(m); for (const tc of m.tool_calls) { let a = {}; try { a = JSON.parse(tc.function.arguments || '{}'); } catch {} msgs.push({ role:'tool', tool_call_id: tc.id, content: runTool(tc.function.name, a).slice(0, 12000) }); }
  }
  return '(no reply produced)';
}
const reply = DRY ? async () => `[STATUS] (dry run) ${NAME} would answer here.` : { fable: replyFable, astra: replyAstra, grok: replyGrok }[LENS];

// ---- the seat loop ----------------------------------------------------------------------------
const me = { name: NAME, role: `lens: ${L.label}`, color: L.color, initials: L.ini, client: 'cc', joinedAt: Date.now(), lastSeenAt: Date.now() };
const joined = await post({ action:'join', code: CODE, participant: me, priorIdentity: { name: NAME, client: 'cc' } })
  .catch(() => post({ action:'join', code: CODE, participant: me }));   // a restarted seat takes its old chair back
const myName = joined.participant.name; log(`joined ${CODE} as ${myName}; mode=${joined.room.replyMode}; model=${L.model}`);
let cursor = 0, turns = 0, pending = false, draft = null;   // anything already said (the host's opening) counts
while (turns < MAX) {
  await post({ action:'presence', code: CODE, name: myName, until: Date.now() + 60000 }).catch(()=>{});
  const room = (await post({ action:'sweep', code: CODE })).room; if (room.status !== 'active') { log('room ended'); break; }
  const fresh = (await post({ action:'messages', code: CODE, cursor })).messages; cursor += fresh.length;
  if (fresh.some(m => m.name !== myName && m.type !== 'sys')) { pending = true; draft = null; }   // new words: any unsent draft is stale
  if (pending) {
    const ts = await post({ action:'turnState', code: CODE }).catch(() => ({}));
    if (!ts.turnState?.currentName || ts.turnState.currentName === myName) {
      const all = (await post({ action:'messages', code: CODE, cursor: 0 })).messages.filter(m => m.type !== 'sys');
      if (!draft) { try { draft = await reply(all); } catch (e) { log('reply failed:', e.message.slice(0, 300)); await new Promise(r => setTimeout(r, 15000)); continue; } }
      try { const r = await post({ action:'send', code: CODE, message: { id: Date.now(), type:'msg', name: myName, initials: me.initials, color: me.color, role: me.role, text: draft, client:'cc', time: Date.now() } });
        if (r.result?.appended) { turns++; pending = false; draft = null; cursor++; log(`spoke (turn ${turns}/${MAX})`); } }
      catch (e) { if (e.name === 'NotYourTurnError' || e.name === 'MutedError') process.stdout.write('.'); else throw e; }
    } else process.stdout.write('.');
  }
  await new Promise(r => setTimeout(r, 4000));
}
log(`done after ${turns} turn(s)`);
