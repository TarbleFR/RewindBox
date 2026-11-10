#!/usr/bin/env python3
"""Run source-extracted texture regressions; no Vulkan driver or iPhone is modeled."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--baseline', type=Path, help='Optional immutable baseline for provenance')
parser.add_argument('--name', default='candidate')
parser.add_argument('--report-dir', type=Path)
parser.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
parser.add_argument('--generate-only', action='store_true')
parser.add_argument('--only', choices=['pressure', 'depth'])
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--expect-baseline', action='store_true')
args = parser.parse_args()
out = args.report_dir or HERE / 'results' / args.name
out = out.resolve()
out.mkdir(parents=True, exist_ok=True)

def block(text, marker):
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 1
    end = pos + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

vulkan = args.source / 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp'
common = args.source / 'rpcs3/Emu/RSX/Common/texture_cache.h'
text = vulkan.read_text()
pressure = block(text, 'bool texture_cache::handle_memory_pressure(')
pressure_program = (HERE / 'pressure_adapter.cpp').read_text().replace('// INSERT_PRODUCTION_PRESSURE', pressure)
text = common.read_text()
start = text.index('image_section_attributes_t attributes{};', text.index('sampled_image_descriptor upload_texture('))
end = text.index('const auto lookup_range = ', start)
prefix = text[start:end]
depth_program = (HERE / 'depth_adapter.cpp').read_text().replace('// INSERT_PRODUCTION_PREFIX', prefix)

reports = []
for name, program in [('pressure', pressure_program), ('depth', depth_program)]:
    if args.only and args.only != name:
        continue
    cpp = out / (name + '.cpp')
    binary = out / name
    cpp.write_text(program)
    command = [args.compiler, '-std=c++20', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror', '-DRPCS3_IOS', str(cpp), '-o', str(binary)]
    if args.expect_baseline:
        command.insert(1, '-DEXPECT_BASELINE')
    if args.sanitize:
        command[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    if args.generate_only:
        reports.append({'case': name, 'program_sha256': hashlib.sha256(cpp.read_bytes()).hexdigest(), 'command': command, 'executed': False})
        continue
    result = subprocess.run(command, capture_output=True, text=True)
    (out / (name + '-compile.txt')).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
    result = subprocess.run([str(binary)], capture_output=True, text=True, env=env, timeout=45)
    (out / (name + '-output.txt')).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    record = json.loads(result.stdout)
    record.update(program_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(), command=command)
    reports.append(record)

report = {
    'name': args.name,
    'source_hashes': {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [vulkan, common]},
    'baseline_expected': args.expect_baseline,
    'generate_only': args.generate_only,
    'sanitizers': 'ASan/UBSan; LSan disabled' if args.sanitize else 'none',
    'reports': reports,
    'limits': ['GPU allocation/destruction APIs are recording substitutes.', 'Memory bytes are allocation lifetimes, not device RSS.', 'Texture prefix is extracted, not a complete Core compilation.', 'No iPhone or FPS measurement.']
}
if args.baseline:
    report['baseline_hashes'] = {str(p.relative_to(args.source)): hashlib.sha256((args.baseline / p.relative_to(args.source)).read_bytes()).hexdigest() for p in [vulkan, common]}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
