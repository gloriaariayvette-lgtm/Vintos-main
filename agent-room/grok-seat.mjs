#!/usr/bin/env node
// Kept for the old command line. The seat itself lives in seat.mjs (--lens grok).
import { spawn } from 'node:child_process'; import { fileURLToPath } from 'node:url'; import path from 'node:path';
const here = path.dirname(fileURLToPath(import.meta.url));
spawn(process.execPath, [path.join(here, 'seat.mjs'), '--lens', 'grok', ...process.argv.slice(2)], { stdio: 'inherit' }).on('exit', c => process.exit(c ?? 1));
