#!/usr/bin/env node
// Proves the contract: the real npm MCP server (the seat Claude Code / Codex will run) talks to our room API.
import { spawn } from 'node:child_process';
const [cmd, ...cargs] = process.argv[2].split(' '); const CODE = process.argv[3]; const NAME = process.argv[4] || 'Fable';
const p = spawn(cmd, cargs, { env: { ...process.env }, stdio: ['pipe','pipe','inherit'] });
let buf=''; const waiters = new Map(); p.stdout.on('data', c => { buf += c; let i; while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0,i); buf = buf.slice(i+1); if(!line.trim()) continue; try { const m = JSON.parse(line); if (m.id !== undefined && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); } } catch {} } });
let id=0; const call = (method, params) => new Promise(res => { const m = { jsonrpc:'2.0', id: ++id, method, params }; waiters.set(m.id, res); p.stdin.write(JSON.stringify(m)+'\n'); });
const text = r => (r.result?.content||[]).map(c=>c.text||'').join('\n');
await call('initialize', { protocolVersion:'2024-11-05', capabilities:{}, clientInfo:{ name:'probe', version:'0' } }); p.stdin.write(JSON.stringify({ jsonrpc:'2.0', method:'notifications/initialized' })+'\n');
const tools = await call('tools/list', {}); console.log('tools:', tools.result.tools.map(t=>t.name).join(' '));
const j = await call('tools/call', { name:'room_join', arguments:{ code: CODE, name: NAME, role:'lens', listenAfterJoin:false } }); console.log('room_join ->', text(j).slice(0,300).replace(/\n/g,' | '));
const s = await call('tools/call', { name:'room_send', arguments:{ code: CODE, name: NAME, text:'[STATUS] MCP seat is in the room.' } }); console.log('room_send ->', text(s).slice(0,200).replace(/\n/g,' | '));
const l = await call('tools/call', { name:'room_listen', arguments:{ code: CODE, since: 0, timeoutMs: 0, name: NAME } }); console.log('room_listen ->', text(l).slice(0,300).replace(/\n/g,' | '));
p.kill(); process.exit(text(j).toLowerCase().includes('error') && !text(j).toLowerCase().includes('joined') ? 1 : 0);
