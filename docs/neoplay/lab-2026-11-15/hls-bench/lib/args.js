'use strict';
// Minimal command-line parser shared by origin.js, run.js and matrix.js.
// spec: { name: { type: 'number'|'string'|'bool'|'json', default, help } }
// Accepts --name value, --name=value, --flag (bool), --no-flag.
function camel(name) { return name.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase()); }

function parseArgs(argv, spec, { allowUnknown = false } = {}) {
  const out = {}; const unknown = [];
  for (const [name, def] of Object.entries(spec)) out[camel(name)] = def.default;
  for (let i = 0; i < argv.length; i++) {
    let token = argv[i];
    if (!token.startsWith('--')) { unknown.push(token); continue; }
    let value = null; const eq = token.indexOf('=');
    if (eq > 0) { value = token.slice(eq + 1); token = token.slice(0, eq); }
    let name = token.slice(2); let negated = false;
    if (!(name in spec) && name.startsWith('no-') && name.slice(3) in spec) { name = name.slice(3); negated = true; }
    const def = spec[name];
    if (!def) {
      if (!allowUnknown) throw new Error(`unknown option --${name} (see README.md)`);
      unknown.push(argv[i]);
      if (value === null && i + 1 < argv.length && !argv[i + 1].startsWith('--')) unknown.push(argv[++i]);
      continue;
    }
    if (def.type === 'bool') {
      if (value === null) out[camel(name)] = !negated;
      else out[camel(name)] = !['0', 'false', 'no', 'off'].includes(value.toLowerCase());
      continue;
    }
    if (value === null) { if (i + 1 >= argv.length) throw new Error(`option --${name} needs a value`); value = argv[++i]; }
    if (def.type === 'number') {
      const n = Number(value); if (!Number.isFinite(n)) throw new Error(`option --${name}: "${value}" is not a number`);
      out[camel(name)] = n;
    } else if (def.type === 'json') {
      out[camel(name)] = readJson(value, name);
    } else out[camel(name)] = value;
  }
  return { options: out, unknown };
}

function readJson(value, name) {
  const fs = require('fs');
  try { return JSON.parse(value.startsWith('@') ? fs.readFileSync(value.slice(1), 'utf8') : value); }
  catch (error) { throw new Error(`option --${name}: invalid JSON (${error.message})`); }
}

function usage(spec) {
  return Object.entries(spec).map(([name, def]) => {
    const shown = def.default === undefined || def.default === null ? '' : ` [${typeof def.default === 'object' ? JSON.stringify(def.default) : def.default}]`;
    return `  --${name}${def.type === 'bool' ? '' : ' <' + def.type + '>'}${shown}\n      ${def.help || ''}`;
  }).join('\n');
}

// Re-serialises the options named in `spec` as an argv array (for child processes).
function toArgv(options, spec) {
  const argv = [];
  for (const [name, def] of Object.entries(spec)) {
    const value = options[camel(name)];
    if (value === undefined || value === null) continue;
    if (def.type === 'bool') { if (value !== def.default) argv.push(value ? `--${name}` : `--no-${name}`); continue; }
    if (value === def.default) continue;
    argv.push(`--${name}`, def.type === 'json' ? JSON.stringify(value) : String(value));
  }
  return argv;
}

module.exports = { parseArgs, usage, toArgv, camel };
