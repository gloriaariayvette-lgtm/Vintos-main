// Code hands for a REST seat: grep and read_file, fenced to the room roots. Used by grok-seat.mjs.
import fs from 'node:fs'; import path from 'node:path'; import { execFileSync } from 'node:child_process';
const H = process.env.HOME;
export const ROOTS = (process.env.ROOM_ROOTS ? process.env.ROOM_ROOTS.split(':') : [
  `${H}/Vintos`, `${H}/.vintos/workspace/scripts`, `${H}/.vintos/deploy/vintos-main`, `${H}/.vintos/deploy/velaris-main`, `${H}/.vintos/code-review`,
]).map(p => path.resolve(p)).filter(p => fs.existsSync(p));
function inside(p){ const r = path.resolve(String(p).replace(/^~(?=\/|$)/, H)); return ROOTS.some(root => r === root || r.startsWith(root + path.sep)) ? r : null; }
export const TOOLS = [
  { type:'function', function:{ name:'grep', description:'Search his code. Regex over the room roots (his organs and the repos). Returns file:line: text, max 60 hits.',
      parameters:{ type:'object', properties:{ pattern:{type:'string'}, path:{type:'string', description:'optional file or directory to limit to'} }, required:['pattern'] } } },
  { type:'function', function:{ name:'read_file', description:'Read a slice of a file (1-based lines). Max 400 lines per call.',
      parameters:{ type:'object', properties:{ path:{type:'string'}, start:{type:'integer'}, end:{type:'integer'} }, required:['path'] } } },
];
export function runTool(name, args){
  try {
    if (name === 'grep') {
      const where = args.path ? [inside(args.path)].filter(Boolean) : ROOTS; if (!where.length) return 'outside the room roots';
      try { return execFileSync('grep', ['-rnE', '--include=*.py', '--include=*.sh', '--include=*.md', '--include=*.json', '--include=*.txt', '-m', '20', args.pattern, ...where], { encoding:'utf8', maxBuffer: 4e6 }).split('\n').slice(0, 60).map(l => l.replace(H, '~')).join('\n') || '(no matches)'; }
      catch (e) { return e.status === 1 ? '(no matches)' : 'grep error: ' + (e.stderr || e.message).slice(0, 200); }
    }
    if (name === 'read_file') {
      const f = inside(args.path.replace(/^~/, H)); if (!f || !fs.existsSync(f)) return 'no such file inside the room roots';
      const lines = fs.readFileSync(f, 'utf8').split('\n'); const a = Math.max(1, args.start || 1), b = Math.min(lines.length, args.end || a + 199, a + 399);
      return lines.slice(a - 1, b).map((l, i) => `${a + i}: ${l}`).join('\n') + (b < lines.length ? `\n... (${lines.length} lines total)` : '');
    }
    return 'unknown tool';
  } catch (e) { return 'tool error: ' + e.message; }
}
