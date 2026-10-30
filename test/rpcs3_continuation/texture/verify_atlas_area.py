#!/usr/bin/env python3
"""Verify production atlas coverage arithmetic with a wide independent oracle."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--name', default='atlas-area')
p.add_argument('--report-dir', type=Path)
p.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
p.add_argument('--generate-only', action='store_true')
p.add_argument('--sanitize', action='store_true')
args = p.parse_args()
rel = 'rpcs3/Emu/RSX/Common/texture_cache.h'

def block(text, marker):
    start = text.index(marker); end = text.index('{', start) + 1; depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return text[start:end]

candidate = block((args.source / rel).read_text(), 'bool atlas_covers_target_area(')
baseline = block((args.baseline / rel).read_text(), 'bool atlas_covers_target_area(')
program = (HERE / 'atlas_area_adapter.cpp').read_text().replace('// INSERT_CANDIDATE', candidate).replace('// INSERT_BASELINE', baseline)
out = (args.report_dir or HERE / 'results' / args.name).resolve(); out.mkdir(parents=True, exist_ok=True)
cpp = out / 'atlas_area.cpp'; cpp.write_text(program); binary = out / 'atlas_area'
command = [args.compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)]
if args.sanitize:
    command[1:1] = ['-DVERIFY_CANDIDATE_ONLY', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer']
if args.generate_only:
    report = dict(case='atlas_area', executed=False, command=command, source_sha256=hashlib.sha256((args.source / rel).read_bytes()).hexdigest(), baseline_sha256=hashlib.sha256((args.baseline / rel).read_bytes()).hexdigest(), program_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest())
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report)); raise SystemExit(0)
r = subprocess.run(command, text=True, capture_output=True)
(out / 'compile.txt').write_text(r.stdout + r.stderr)
if r.returncode: raise SystemExit(r.stdout + r.stderr)
env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
r = subprocess.run([str(binary)], text=True, capture_output=True, env=env, timeout=45)
(out / 'output.txt').write_text(r.stdout + r.stderr)
if r.returncode: raise SystemExit(r.stdout + r.stderr)
report = json.loads(r.stdout)
if args.sanitize:
    probe = subprocess.run([str(binary), '--baseline-overflow-probe'], text=True, capture_output=True, env=env, timeout=10)
    (out / 'baseline-overflow.txt').write_text(probe.stdout + probe.stderr)
    if probe.returncode == 0 or 'signed integer overflow' not in probe.stderr:
        raise SystemExit('Baseline UBSan probe did not detect expected signed overflow: ' + probe.stderr)
    report['baseline_signed_overflow_detected'] = True
report.update(command=command, source_sha256=hashlib.sha256((args.source / rel).read_bytes()).hexdigest(),
              baseline_sha256=hashlib.sha256((args.baseline / rel).read_bytes()).hexdigest(),
              program_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(), sanitizers=args.sanitize,
              limitations=['Extracted area decision and width/height box arithmetic; no GPU execution.',
                           'Large-field bounds stress is distinct from the generated 256 MiB volume set.',
                           'No device performance or game-specific visual result.'])
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
