#!/usr/bin/env python3
"""Compare the production texture address index and lifecycle with the linear baseline.

Production block/list/range iterators, matching, lookup and lifecycle bodies are
executed verbatim. GPU resource and guest-memory validation are host adapters;
their calls and order remain observable. No iPhone performance is inferred.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
CACHE='rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS='rpcs3/Emu/RSX/Common/texture_cache_utils.h'
CPP='rpcs3/Emu/RSX/Common/texture_cache.cpp'
RANGE='Utilities/address_range.h'
SOURCE=[CACHE,UTILS]
SUPPORT=[CPP,RANGE]
ADAPTER=ROOT/'test/native/rpcs3_texture_address_index.inc'
def sha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def braced(text, marker):
    start = text.index(marker)
    opening = text.index('{', start)
    depth, pos, state = 0, opening, None
    while pos < len(text):
        if state in ('"', "'"):
            if text[pos] == '\\':
                pos += 2
                continue
            if text[pos] == state:
                state = None
        elif state == '//':
            if text[pos] == '\n':
                state = None
        elif state == '/*':
            if text.startswith('*/', pos):
                state = None
                pos += 2
                continue
        elif text.startswith('//', pos):
            state = '//'
            pos += 2
            continue
        elif text.startswith('/*', pos):
            state = '/*'
            pos += 2
            continue
        elif text[pos] in ('"', "'"):
            state = text[pos]
        else:
            depth += (text[pos] == '{') - (text[pos] == '}')
            if not depth:
                return text[start:pos + 1]
        pos += 1
    raise ValueError(marker)


def harness(source,baseline):
    common=(source/CPP).read_text()
    code=ADAPTER.read_text()
    ranges='\n'.join(line for line in (source/RANGE).read_text().splitlines() if not line.startswith(('#include','#pragma')))
    code=code.replace('// @RANGES@',ranges)
    current=(source/UTILS).read_text();old=(baseline/UTILS).read_text()
    marker='class cached_texture_section :'
    assert current[current.index(marker):]==old[old.index(marker):]
    assert braced(current,'class ranged_storage\n')==braced(old,'class ranged_storage\n')
    body=''
    for sig in ['void buffered_section::reset(', 'void buffered_section::invalidate_range(', 'void buffered_section::discard(', 'const address_range32& buffered_section::get_bounds(']:
        body+=braced(common,sig)+'\n'
    code=code.replace('// @BUFFERED@',body)
    versions=''
    for label,tree in [('before',baseline),('after',source)]:
        util=(tree/UTILS).read_text();cache=(tree/CACHE).read_text()
        body='namespace '+label+' {\nusing namespace rsx;\n'
        body+='template <typename section_storage_type, usz array_size>\n'+braced(util,'class ranged_storage_block_list\n')+';\n'
        body+='template <typename _ranged_storage_type>\n'+braced(util,'class ranged_storage_block\n')+';\n'
        body+='template <typename traits>\n'+braced(util,'class ranged_storage\n')+';\n'
        section=code.split('// @SECTION_BEGIN@')[1].split('// @SECTION_END@')[0]
        methods=''
        for sig in ['void initialize(ranged_storage_block_type* block)', 'void reset(const address_range32& memory_range)', 'void notify_range_valid()', 'void invalidate_range()', 'void on_section_resources_created()', 'void on_section_resources_destroyed()', 'void set_dirty(bool new_dirty)', 'void update_unreleased()', 'bool is_unreleased() const', 'bool sync_protection()', 'bool matches(u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const', 'bool matches(u32 rsx_address, u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const']:
            part=braced(util,sig)
            # The first reset/invalidate declarations are in buffered_section;
            # select actual cached_texture_section bodies after its definition.
            if sig in ['void reset(const address_range32& memory_range)','void invalidate_range()']:
                part=braced(util[util.index('class cached_texture_section :'):],sig)
            name=sig.split('(')[0].split()[-1]
            part=part.replace(name+'(', 'Section::'+name+'(',1)
            methods+=part+'\n'
        lookup=braced(cache,'section_storage_type *find_texture_from_dimensions(')
        section=section.replace('// @LOOKUP@','template <bool check_unlocked=false>\n'+lookup)
        body+=section+methods+'}\n'
        # Visibility only, to measure index capacity without runtime telemetry.
        body=body.replace('private:', 'public:')
        versions+=body
    begin=code.index('// @SECTION_BEGIN@');end=code.index('// @SECTION_END@')+len('// @SECTION_END@')
    code=code[:begin]+versions+code[end:]
    assert '// @' not in code
    return code

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--baseline',required=True,type=Path)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    p.add_argument('--sanitizer',choices=['address,undefined'])
    p.add_argument('--benchmark',action='store_true');p.add_argument('--report',type=Path)
    a=p.parse_args();source=a.source.resolve();baseline=a.baseline.resolve()
    inputs={name:sha(source/name) for name in SOURCE+SUPPORT};old={name:sha(baseline/name) for name in SOURCE}
    code=harness(source,baseline);cxx=shlex.split(a.compiler)
    flags=['-std=c++20','-g','-Wall','-Wextra','-Werror','-pthread','-DRPCS3_IOS']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    flags+=['-O1','-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer'] if a.sanitizer else ['-O3']
    if a.sanitizer and platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    flags+=['-UNDEBUG']
    with tempfile.TemporaryDirectory(prefix='rpcs3-texture-address-') as tmp:
        cpp=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';cpp.write_text(code)
        subprocess.run(cxx+flags+[str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)]+(['benchmark'] if a.benchmark else []),text=True,capture_output=True,timeout=180,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:raise RuntimeError(f'exit{run.returncode}\n{run.stdout}\n{run.stderr}')
        results=json.loads(run.stdout)
    assert inputs=={name:sha(source/name) for name in SOURCE+SUPPORT}
    assert old=={name:sha(baseline/name) for name in SOURCE}
    report={'passed':True,'assertionsActive':True,'compiler':subprocess.check_output(cxx+['--version'],text=True).splitlines()[0],'compilerFlags':flags,'sanitizer':a.sanitizer,'sourceSHA256':inputs,'baselineSHA256':old,'harnessSHA256':hashlib.sha256(code.encode()).hexdigest(),'adapterSHA256':sha(ADAPTER),'host':platform.machine(),'results':results,'physicalDeviceTested':False,'gameplayMeasured':False,'scope':__doc__}
    if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
