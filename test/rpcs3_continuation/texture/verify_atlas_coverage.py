#!/usr/bin/env python3
"""Compare production atlas clear control flow and bounded coverage against texel painting."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--name', default='atlas')
p.add_argument('--report-dir', type=Path)
p.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
p.add_argument('--generate-only', action='store_true')
p.add_argument('--sanitize', action='store_true')
args=p.parse_args()
rel='rpcs3/Emu/RSX/VK/VKTextureCache.cpp'
candidate=(args.source/rel).read_text()
baseline=(args.baseline/rel).read_text()
def block(text, marker):
    start=text.index(marker); pos=text.index('{',start); end=pos+1; depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
helper=block(candidate,'bool texture_cache::copy_transfer_regions_fully_cover_2d_image(')
new=block(candidate,'vk::image_view* texture_cache::generate_atlas_from_images(')
old=block(baseline,'vk::image_view* texture_cache::generate_atlas_from_images(').replace('texture_cache::generate_atlas_from_images','baseline_cache::generate_atlas_from_images',1)
program=(HERE/'atlas_adapter.cpp').read_text().replace('// INSERT_COVERAGE',helper).replace('// INSERT_CANDIDATE',new).replace('// INSERT_BASELINE',old)
out=(args.report_dir or HERE/'results'/args.name).resolve();out.mkdir(parents=True,exist_ok=True)
cpp=out/'atlas.cpp';cpp.write_text(program);binary=out/'atlas'
command=[args.compiler,'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(cpp),'-o',str(binary)]
if args.sanitize:command[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
if args.generate_only:
    report=dict(case='atlas_coverage',executed=False,command=command,program_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),source_sha256=hashlib.sha256((args.source/rel).read_bytes()).hexdigest(),baseline_sha256=hashlib.sha256((args.baseline/rel).read_bytes()).hexdigest())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));raise SystemExit(0)
r=subprocess.run(command,capture_output=True,text=True)
(out/'compile.txt').write_text(r.stdout+r.stderr)
if r.returncode:raise SystemExit(r.stdout+r.stderr)
r=subprocess.run([str(binary)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'),timeout=45)
(out/'output.txt').write_text(r.stdout+r.stderr)
if r.returncode:raise SystemExit(r.stdout+r.stderr)
report=json.loads(r.stdout)
report.update(command=command,program_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),source_sha256=hashlib.sha256((args.source/rel).read_bytes()).hexdigest(),baseline_sha256=hashlib.sha256((args.baseline/rel).read_bytes()).hexdigest(),sanitizers=args.sanitize,limitations=['Recorded Vulkan APIs and independent texel painter, not GPU execution.','No driver timing, Metal execution or iPhone FPS claim.'])
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
