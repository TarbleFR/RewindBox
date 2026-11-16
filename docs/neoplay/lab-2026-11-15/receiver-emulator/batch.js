'use strict';
// node src/batch.js <plan.json>   - runs the experiments of a plan one after the other and prints one line per run.
// plan: [{ "name": "shaka-base", "repeat": 3, "args": { "duration": 40, "flags": {...}, "playlist": {...}, "loadDelay": 100 } }, ...]
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { analyze, line } = require('./analyze.js');
const plan = JSON.parse(fs.readFileSync(path.resolve(process.argv[2]), 'utf8'));
for (const item of plan) {
  for (let i = 1; i <= (item.repeat || 1); i++) {
    const name = item.name + ((item.repeat || 1) > 1 ? '-' + i : '');
    const args = [path.join(__dirname, 'run.js'), '--name', name];
    const values = Object.assign({}, item.args);
    if (Array.isArray(values.loadDelay)) values.loadDelay = values.loadDelay[(i - 1) % values.loadDelay.length];
    for (const [key, value] of Object.entries(values)) args.push('--' + key, typeof value === 'object' ? JSON.stringify(value) : String(value));
    const done = spawnSync(process.execPath, args, { encoding: 'utf8', timeout: 300000 });
    const file = path.join(__dirname, '..', 'out', name + '.json');
    try { console.log(line(analyze(JSON.parse(fs.readFileSync(file, 'utf8'))))); } catch (e) { console.log(name + ': no result (' + (done.stdout || '') + (done.stderr || '') + ')'); }
  }
}
