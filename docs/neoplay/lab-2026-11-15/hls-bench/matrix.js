#!/usr/bin/env node
'use strict';
// Runs a plan (a list of run.js invocations), a few at a time, and writes summary.json + summary.md.
//   node matrix.js --plan plans/first.json --out-dir results/first [--concurrency 2] [--only substring] [--summarize]
// Plan: { "defaults": { run.js options }, "runs": [ { "label": "seg0.5", "args": { "seg": 0.5 }, "repeat": 3, "phases": [0.1, 0.5, 0.9] } ] }
// Options use the run.js names without the leading dashes; "phases" gives --join-phase for each repetition.

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { parseArgs } = require('./lib/args');
const { summary, analyze } = require('./analyze');

const { options: O } = parseArgs(process.argv.slice(2), {
  'plan': { type: 'string', default: '' },
  'out-dir': { type: 'string', default: '' },
  'concurrency': { type: 'number', default: 1 },
  'only': { type: 'string', default: '' },
  'summarize': { type: 'bool', default: false },      // only rebuild the summary from the result files present
  'raw': { type: 'bool', default: false },
  'reanalyze': { type: 'bool', default: false },     // with --summarize: recompute every result from its .raw.json
  'retries': { type: 'number', default: 2 },         // repetitions of a run whose verdict says the lab was overloaded
});
if (!O.plan || !O.outDir) { console.error('usage: node matrix.js --plan plan.json --out-dir dir [--concurrency 1] [--retries 2] [--only text] [--summarize] [--raw]'); process.exit(2); }
const plan = JSON.parse(fs.readFileSync(O.plan, 'utf8'));
const outDir = path.resolve(O.outDir); fs.mkdirSync(outDir, { recursive: true });

const jobs = [];
for (const run of plan.runs) {
  if (O.only && !run.label.includes(O.only)) continue;
  const repeat = run.repeat || (run.phases ? run.phases.length : plan.repeat || 1);
  for (let i = 0; i < repeat; i++) {
    const args = Object.assign({}, plan.defaults || {}, run.args || {});
    if (run.phases) args['join-phase'] = run.phases[i % run.phases.length];
    const label = repeat > 1 ? `${run.label}-r${i + 1}` : run.label;
    const argv = ['--label', label, '--out', path.join(outDir, label + '.json'), '--quiet'];
    if (O.raw) argv.push('--raw');
    for (const [key, value] of Object.entries(args)) {
      if (value === true) argv.push('--' + key); else if (value === false) argv.push('--no-' + key);
      else argv.push('--' + key, typeof value === 'object' ? JSON.stringify(value) : String(value));
    }
    jobs.push({ group: run.label, label, argv, file: path.join(outDir, label + '.json'), note: run.note || '' });
  }
}

const children = new Set();
let aborted = false;
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => { aborted = true; for (const child of children) child.kill('SIGTERM'); setTimeout(() => process.exit(130), 2500); });

function runJob(job) {
  return new Promise((resolve) => {
    const started = Date.now();
    const child = spawn(process.execPath, [path.join(__dirname, 'run.js'), ...job.argv], { stdio: ['ignore', 'ignore', 'pipe'] });
    children.add(child); child.on('exit', () => children.delete(child));
    let stderr = ''; child.stderr.on('data', (c) => { stderr = (stderr + c).slice(-1500); });
    child.on('exit', (code) => { job.exit = code; job.stderr = stderr.trim(); console.error(`${code === 0 ? 'ok  ' : 'FAIL'} ${job.label} (${Math.round((Date.now() - started) / 1000)} s)${code === 0 ? '' : ' ' + stderr.trim().split('\n').pop()}`); resolve(); });
  });
}

const med = (values) => { const v = values.filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b); return v.length ? v[v.length >> 1] : null; };
const span = (values) => { const v = values.filter((x) => typeof x === 'number' && Number.isFinite(x)); return v.length ? `${Math.round(Math.min(...v))}..${Math.round(Math.max(...v))}` : '-'; };
const show = (v, digits = 0) => (v === null || v === undefined ? '-' : typeof v === 'number' ? v.toFixed(digits) : String(v));

function summarize() {
  const rows = [];
  for (const job of jobs) {
    if (!fs.existsSync(job.file)) { rows.push({ group: job.group, label: job.label, missing: true, note: job.note }); continue; }
    let result = JSON.parse(fs.readFileSync(job.file, 'utf8'));
    const rawFile = job.file.replace(/\.json$/, '.raw.json');
    if (O.reanalyze && fs.existsSync(rawFile)) {       // recompute the result from the raw samples with the current analyze.js
      const again = analyze(JSON.parse(fs.readFileSync(rawFile, 'utf8'))); again.browser = result.browser; result = again;
      fs.writeFileSync(job.file, JSON.stringify(result));
    }
    const row = summary(result); row.group = job.group; row.note = job.note; rows.push(row);
  }
  fs.writeFileSync(path.join(outDir, 'summary.json'), JSON.stringify(rows, null, 1));
  const lines = ['| run | join phase | first-frame delay ms | steady delay ms: median (p05..p95, max) | drift ms/min | buffered ahead s: median (min) | Shaka buffering: n / ms | freezes >100 ms: n / ms | smooth seconds share (first smooth s) | presented fps | skipped | seeks | outage: before -> after ms | ok |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|'];
  for (const r of rows) {
    if (r.missing) { lines.push(`| ${r.label} | (no result) |||||||||||`); continue; }
    lines.push(`| ${r.label} | ${show(r.joinPhase, 2)} | ${show(r.delayFirstMs)} | ${show(r.delayMedianMs)} (${show(r.delayP05Ms)}..${show(r.delayP95Ms)}, ${show(r.delayMaxMs)}) | ${show(r.driftMsPerMin, 1)} | ${show(r.bufferedAheadS, 2)} (${show(r.bufferedAheadMinS, 2)}) | ${r.bufferingCount} / ${show(r.bufferingMs)} | ${r.freezeCount} / ${show(r.freezeMs)} | ${show(r.smoothShare, 2)} (${show(r.firstSmoothSecond)}) | ${show(r.presentedFps, 1)} | ${r.skippedFrames} | ${r.seeks} | ${r.delayBeforeMs === null ? '-' : show(r.delayBeforeMs) + ' -> ' + show(r.delayAfterMs)} | ${r.ok ? 'yes' : 'NO: ' + r.problems} |`);
  }
  const groups = [...new Set(rows.map((r) => r.group))];
  lines.push('', '| configuration | runs | steady delay ms: median of runs (range of run medians) | p95 (worst run) | first-frame delay (range) | Shaka buffering events / ms (sum) | freezes n / ms (sum) | smooth share (range) | after outage: delay change ms (range) | seeks (sum) | note |', '|---|---|---|---|---|---|---|---|---|---|---|');
  for (const group of groups) {
    const g = rows.filter((r) => r.group === group && !r.missing);
    if (!g.length) continue;
    const sum = (key) => g.reduce((total, r) => total + (r[key] || 0), 0);
    lines.push(`| ${group} | ${g.length} | ${show(med(g.map((r) => r.delayMedianMs)))} (${span(g.map((r) => r.delayMedianMs))}) | ${show(Math.max(...g.map((r) => r.delayP95Ms ?? NaN)))} | ${span(g.map((r) => r.delayFirstMs))} | ${sum('bufferingCount')} / ${show(sum('bufferingMs'))} | ${sum('freezeCount')} / ${show(sum('freezeMs'))} | ${Math.min(...g.map((r) => r.smoothShare)).toFixed(2)}..${Math.max(...g.map((r) => r.smoothShare)).toFixed(2)} | ${span(g.map((r) => r.outageDeltaMs))} | ${sum('seeks')} | ${g[0].note || ''} |`);
  }
  fs.writeFileSync(path.join(outDir, 'summary.md'), lines.join('\n') + '\n');
  return lines.join('\n');
}

(async () => {
  if (!O.summarize) {
    const queue = jobs.slice();
    const worker = async () => {
      for (;;) {
        const job = queue.shift(); if (!job || aborted) return;
        // a run flagged "lab overloaded" (or failed) is repeated: other jobs on the machine must not pass for stutter
        for (let attempt = 0; attempt <= O.retries && !aborted; attempt++) {
          await runJob(job);
          if (job.exit === 0) break;
          let reason = 'failed';
          try { reason = JSON.parse(fs.readFileSync(job.file, 'utf8')).verdict.problems.join('; '); } catch (_) { /* no file */ }
          if (!/overloaded|FAILED|failed|no frame/.test(reason) || attempt === O.retries) break;
          console.error(`     retry ${job.label}: ${reason}`);
          try { fs.renameSync(job.file, job.file.replace(/\.json$/, `.attempt${attempt + 1}.json`)); } catch (_) { /* nothing to keep */ }
        }
      }
    };
    await Promise.all(Array.from({ length: Math.max(1, O.concurrency) }, worker));
  }
  console.log(summarize());
})();
