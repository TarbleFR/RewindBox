// Assembles the static site of the RewindBox Cast receiver: node site.mjs <output directory>
// The page lives under cast/ (the Receiver Application URL ends in /cast/); the
// NeoPlay protocol, SPS and audio modules are the Windows receiver's own files.
import { mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const shared = join(here, '..', 'neoplay-receiver');
const output = process.argv[2];
if (!output) { console.error('usage: node site.mjs <output directory>'); process.exit(2); }
const own = ['index.html', 'receiver.mjs', 'frames-engine.mjs', 'mp4-engine.mjs', 'stream-packets.mjs'];
const borrowed = ['protocol.mjs', 'h264-sps.mjs', 'audio-ring.mjs', 'audio-worklet.mjs'];
rmSync(output, { recursive: true, force: true });
mkdirSync(join(output, 'cast'), { recursive: true });
for (const name of own) copyFileSync(join(here, name), join(output, 'cast', name));
for (const name of borrowed) copyFileSync(join(shared, name), join(output, 'cast', name));
writeFileSync(join(output, '.nojekyll'), '');
writeFileSync(join(output, 'index.html'), '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><title>RewindBox</title><p>RewindBox — Google Cast receiver: <a href="cast/">cast/</a></p>\n');
console.log(`site: ${own.length + borrowed.length} files in ${join(output, 'cast')}`);
