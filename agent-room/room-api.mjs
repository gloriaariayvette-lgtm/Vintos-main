#!/usr/bin/env node
// The room API that agent-room-mcp (and any REST seat) posts to: POST /api/room {action,...}.
// Self-hosted over @agent-room/upstash-client — the library runs the whole turn machine
// (sequential/moderator, NotYourTurnError); this file only dispatches and shapes responses
// exactly as apps/mcp/src/roomApi.ts in the agent-room-mcp repo expects.
import http from 'node:http'; import path from 'node:path'; import { pathToFileURL } from 'node:url';
const SRC = process.env.AGENT_ROOM_SRC || path.resolve(process.env.HOME, 'agent-room');
const lib = await import(pathToFileURL(path.join(SRC,'packages/upstash-client/dist/index.js')).href);
const shared = await import(pathToFileURL(path.join(SRC,'packages/shared/dist/index.js')).href);
const PORT = +(process.env.PORT || 8787);
const client = lib.createClient({ url: process.env.UPSTASH_REDIS_REST_URL, token: process.env.UPSTASH_REDIS_REST_TOKEN });
const SYS = (text) => ({ id: Date.now()+Math.floor(Math.random()*1000), type: 'sys', name: 'System', initials: 'SY', color: '#888888', role: '', text, client: 'web', time: Date.now() });
async function sysNote(code, text){ try { await lib.appendSystemMessage(client, code, SYS(text)); } catch {} }
async function hostGate(code, hostKey){ await lib.verifyHostKey(client, code, hostKey); }   // throws HostNameTakenError if wrong/missing
const H = {
  async create(b){ const code = shared.generateCode(); const r = await lib.createRoom(client, { code, topic: b.topic, createdBy: b.createdBy }); const { hostKey, ...room } = r; return { room, hostKey }; },
  async get(b){ return { room: await lib.getRoom(client, b.code) }; },
  async join(b){ const r = await lib.joinRoom(client, b.code, b.participant, { hostKey: b.hostKey, priorIdentity: b.priorIdentity }); const { participant, ...room } = r; return { room, participant }; },
  async messages(b){ const [messages, total] = await Promise.all([lib.listMessages(client, b.code, +b.cursor||0), lib.getMessageTotalCount(client, b.code)]); return { messages, total }; },
  async send(b){ const room = await lib.getRoom(client, b.code); if (b.hostKey && b.message?.name === room.createdBy) await hostGate(b.code, b.hostKey);
    const result = await lib.appendMessage(client, b.code, b.message, b.kind || 'message');
    if (result?.leadSkipped) await sysNote(b.code, `${result.leadSkipped.name} was skipped (lead grace passed); the floor moved on.`); return { result }; },
  async systemMessage(b){ await hostGate(b.code, b.hostKey); await lib.appendSystemMessage(client, b.code, b.message); return { ok: true }; },
  async presence(b){ await lib.setListenUntil(client, b.code, b.name, +b.until); return { ok: true }; },
  async turnState(b){ return { turnState: await lib.getTurnState(client, b.code) }; },
  async sweep(b){ const room = await lib.getRoom(client, b.code); const s = await lib.sweepTimeouts(client, b.code, room);
    for (const k of (s.skipped||[])) await sysNote(b.code, `${k.name} did not answer in time and was skipped.`);
    if (s.fallback) await sysNote(b.code, `Reply mode fell back to open (${s.fallback.reason}: ${s.fallback.agentName}).`);
    return { room: await lib.getRoom(client, b.code) }; },
  async setReplyMode(b){ await hostGate(b.code, b.hostKey); return { room: await lib.setReplyMode(client, b.code, b.requesterName, b.mode, b.config) }; },
  async skipCurrent(b){ await hostGate(b.code, b.hostKey); const room = await lib.getRoom(client, b.code); const skipped = await lib.hostSkipCurrent(client, b.code, room);
    if (skipped) await sysNote(b.code, `${skipped.name} was skipped by the host.`); return { skipped }; },
  async directInvoke(b){ await hostGate(b.code, b.hostKey); return { added: await lib.directInvoke(client, b.code, b.target, b.source || 'host') }; },
  async end(b){ await hostGate(b.code, b.hostKey); return { room: await lib.endRoom(client, b.code) }; },
  async reactivate(b){ await hostGate(b.code, b.hostKey); return { room: await lib.reactivateRoom(client, b.code) }; },
  async removeParticipant(b){ await hostGate(b.code, b.hostKey); return { room: await lib.removeParticipant(client, b.code, b.requesterName, b.targetName, b.targetClient) }; },
  async createReport(b){ const room = await lib.getRoom(client, b.code); const messages = await lib.listMessages(client, b.code, 0); return { report: await lib.createRoomReport(client, room, messages) }; },
  async taskBoard(b){ return { board: await lib.getTaskBoard(client, b.code) }; },
};
const NOT_FOUND = new Set(['RoomNotFoundError']);
const server = http.createServer((req, res) => {
  res.setHeader('access-control-allow-origin', '*'); res.setHeader('access-control-allow-headers', 'content-type'); res.setHeader('content-type', 'application/json'); res.setHeader('cache-control', 'no-store');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  if (req.url === '/health') return res.end('{"ok":true}');
  if (req.method !== 'POST' || !req.url.startsWith('/api/room')) { res.statusCode = 404; return res.end('{"error":"RoomApiError","message":"not found"}'); }
  let body = ''; req.on('data', c => body += c); req.on('end', async () => {
    let b; try { b = JSON.parse(body || '{}'); } catch { res.statusCode = 400; return res.end('{"error":"RoomApiError","message":"bad json"}'); }
    const fn = H[b.action]; if (!fn) { res.statusCode = 400; return res.end(JSON.stringify({ error: 'RoomApiError', message: `action ${b.action} is not supported on this self-hosted room API` })); }
    try { res.end(JSON.stringify(await fn(b))); }
    catch (e) { res.statusCode = NOT_FOUND.has(e?.name) ? 404 : 400; res.end(JSON.stringify({ error: e?.name || 'RoomApiError', message: e?.message || String(e) })); }
  });
});
server.listen(PORT, '127.0.0.1', () => console.log(`[room-api] http://127.0.0.1:${PORT}/api/room  (lib: ${SRC})`));
