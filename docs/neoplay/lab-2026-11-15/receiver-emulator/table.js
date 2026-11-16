'use strict';
// node src/table.js [out-dir] [name-filter-regex]  - one row per configuration: runs out/<config>-<i>.json are pooled.
// Per run the steady delay is the median over the samples where the picture moves; the table gives the
// median and the range of those per-run medians, the pooled p95, and the stalls.
const fs = require('fs');
const path = require('path');
const { analyze, stats } = require('./analyze.js');
const dir = path.resolve(process.argv[2] || path.join(__dirname, '..', 'out'));
const filter = process.argv[3] ? new RegExp(process.argv[3]) : null;
const groups = new Map();
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort()) {
  const name = file.replace(/\.json$/, ''), config = name.replace(/-\d+$/, '');
  if (filter && !filter.test(name)) continue;
  let a; try { a = analyze(JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'))); } catch (e) { continue; }
  if (!a.player) continue;
  if (!groups.has(config)) groups.set(config, []);
  groups.get(config).push(a);
}
const s1 = (ms) => ms === null || ms === undefined ? 'n/a' : (ms / 1000).toFixed(2);
const rows = [];
for (const [config, runs] of groups) {
  const started = runs.filter((r) => r.loadToFirstMotionMs !== null);
  const startStats = stats(started.map((r) => r.loadToFirstMotionMs));
  const med = stats(started.filter((r) => r.delayMovingMs).map((r) => r.delayMovingMs.median));
  const p95 = stats(started.filter((r) => r.delayMovingMs).map((r) => r.delayMovingMs.p95));
  const window = started.reduce((a, r) => a + r.windowSeconds, 0);
  const freezes = started.reduce((a, r) => a + r.freezes.count, 0), frozen = started.reduce((a, r) => a + r.freezes.totalMs, 0);
  rows.push({
    config, player: runs[0].player, runs: runs.length, neverMoved: runs.length - started.length,
    startupDelaySec: startStats ? `${s1(startStats.median)} (${s1(startStats.min)}..${s1(startStats.max)})` : 'n/a',
    steadyDelayMedianSec: med ? `${s1(med.median)} (${s1(med.min)}..${s1(med.max)})` : 'n/a',
    steadyDelayP95Sec: p95 ? s1(p95.max) : 'n/a',
    stalls: started.length ? `${freezes} in ${window.toFixed(0)} s watched (${(frozen / 1000).toFixed(1)} s frozen)` : 'picture never moved',
  });
}
if (process.argv.includes('--json')) console.log(JSON.stringify(rows, null, 1));
else {
  console.log(['config', 'player', 'runs', 'never moved', 'start s: median (min..max)', 'steady delay s: median of runs (min..max)', 'worst p95 s', 'stalls after start'].join(' | '));
  for (const r of rows) console.log([r.config, r.player, r.runs, r.neverMoved, r.startupDelaySec, r.steadyDelayMedianSec, r.steadyDelayP95Sec, r.stalls].join(' | '));
}
