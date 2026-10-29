#!/usr/bin/env python3
"""Compare the exact production uncompressed lookup before/after address selection.

Storage/list/index/range iteration, matching, pitch and lifecycle methods are
production bodies. GPU resources and guest-memory hashing are host boundaries.
One real storage is restored between versions so unordered unowned entries have
identical traversal order. No iPhone/Metal timing or gameplay is inferred.
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
from rpcs3_texture_address_index_test import braced
from rpcs3_cell559_test import without_ios_blocks

ROOT=Path(__file__).resolve().parents[1]
CACHE='rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS='rpcs3/Emu/RSX/Common/texture_cache_utils.h'
CPP='rpcs3/Emu/RSX/Common/texture_cache.cpp'
RANGE='Utilities/address_range.h'
PITCH='rpcs3/Emu/RSX/Utils/rsx_utils.h'
ARRAY='rpcs3/Emu/RSX/Common/simple_array.hpp'
SOURCE=[CACHE]
SUPPORT=[UTILS,CPP,RANGE,PITCH,ARRAY]
ADAPTER=ROOT/'test/native/rpcs3_texture_exact_index.inc'

def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def stripped(path):
    return '\n'.join(line for line in path.read_text().splitlines() if not line.startswith(('#include','#pragma')))

def lookup_body(tree):
    text=(tree/CACHE).read_text()
    start=text.index('\t\t\tconst u32 lookup_mask =',text.index('// Check shader_read storage. In a given scene, reads from local memory'))
    end=text.index('\n\t\t\tif (!options.prefer_surface_cache)',start)
    return text[start:end]

def harness(source,baseline):
    for path in SUPPORT:
        assert sha(source/path)==sha(baseline/path),path
    assert without_ios_blocks((source/CACHE).read_text())==without_ios_blocks((baseline/CACHE).read_text())
    code=ADAPTER.read_text()
    code=code.replace('// @RANGES@',stripped(source/RANGE))
    code=code.replace('// @ARRAY@',stripped(source/ARRAY))
    code=code.replace('// @PITCH@','template <bool __is_surface=true, typename SurfaceType>\n'+braced((source/PITCH).read_text(),'inline bool pitch_compatible(const SurfaceType* surface, u32 pitch_required, u16 height_required)'))
    common=(source/CPP).read_text()
    buffered='\n'.join(braced(common,sig) for sig in ['void buffered_section::reset(', 'void buffered_section::invalidate_range(', 'void buffered_section::discard(', 'const address_range32& buffered_section::get_bounds('])
    code=code.replace('// @BUFFERED@',buffered)
    util=(source/UTILS).read_text()
    storage='using namespace rsx;\n'
    for template,signature in [('template <typename section_storage_type, usz array_size>','class ranged_storage_block_list\n'),('template <typename _ranged_storage_type>','class ranged_storage_block\n'),('template <typename traits>','class ranged_storage\n')]:
        storage+=template+'\n'+braced(util,signature)+';\n'
    code=code.replace('// @STORAGE@',storage)
    methods=''
    for sig in ['void initialize(ranged_storage_block_type* block)', 'void reset(const address_range32& memory_range)', 'void notify_range_valid()', 'void invalidate_range()', 'void on_section_resources_created()', 'void on_section_resources_destroyed()', 'void set_dirty(bool new_dirty)', 'void update_unreleased()', 'bool is_unreleased() const', 'bool sync_protection()', 'bool matches(u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const', 'bool matches(u32 rsx_address, u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const']:
        text=util[util.index('class cached_texture_section :'):] if sig in ['void reset(const address_range32& memory_range)','void invalidate_range()'] else util
        part=braced(text,sig);name=sig.split('(')[0].split()[-1]
        methods+=part.replace(name+'(','Section::'+name+'(',1)+'\n'
    code=code.replace('// @METHODS@',methods)
    lookups=''
    for debug in [False,True]:
        if debug:lookups+='#define TEXTURE_CACHE_DEBUG\n'
        for label,tree in [('before',baseline),('after',source)]:
            lookups+='[[gnu::noinline]] Result query_'+label+('_debug' if debug else '')+'(const Attributes& attr,const address_range32& memory_range,const Options& options) {\n'
            lookups+='const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;\n'
            lookups+=lookup_body(tree)
            lookups+='\nResult result;result.merge_count=overlapping_locals.size();if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;\n}\n'
        if debug:lookups+='#undef TEXTURE_CACHE_DEBUG\n'
    code=code.replace('// @LOOKUPS@',lookups)
    code=code.replace('// @SECTION_BEGIN@','').replace('// @SECTION_END@','')
    assert '// @' not in code
    return code

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--compiler',default=os.environ.get('CXX','c++'))
    parser.add_argument('--sanitizer',choices=['address,undefined'])
    parser.add_argument('--benchmark',action='store_true');parser.add_argument('--report',type=Path)
    args=parser.parse_args();source=args.source.resolve();baseline=args.baseline.resolve()
    inputs={path:sha(source/path) for path in SOURCE+SUPPORT};old={path:sha(baseline/path) for path in SOURCE+SUPPORT}
    code=harness(source,baseline);cxx=shlex.split(args.compiler)
    flags=['-std=c++20','-g','-Wall','-Wextra','-Werror','-pthread','-DRPCS3_IOS']
    if sdk:=os.environ.get('HOST_MACOS_SDK'):flags+=['-isysroot',sdk]
    flags+=['-O1','-fsanitize='+args.sanitizer,'-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system()=='Linux':flags+=['-fno-pie','-no-pie']
    flags+=['-UNDEBUG']
    with tempfile.TemporaryDirectory(prefix='rpcs3-texture-exact-') as temp:
        cpp=Path(temp)/'test.cpp';exe=Path(temp)/'test';cpp.write_text(code)
        subprocess.run(cxx+flags+[str(cpp),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)]+(['benchmark'] if args.benchmark else []),text=True,capture_output=True,timeout=180,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:raise RuntimeError(f'exit{run.returncode}\n{run.stdout}\n{run.stderr}')
        results=json.loads(run.stdout)
    assert inputs=={path:sha(source/path) for path in SOURCE+SUPPORT}
    assert old=={path:sha(baseline/path) for path in SOURCE+SUPPORT}
    report={'passed':True,'assertionsActive':True,'compiler':subprocess.check_output(cxx+['--version'],text=True).splitlines()[0],'compilerFlags':flags,'sanitizer':args.sanitizer,'sourceSHA256':inputs,'baselineSHA256':old,'harnessSHA256':hashlib.sha256(code.encode()).hexdigest(),'adapterSHA256':sha(ADAPTER),'host':platform.machine(),'results':results,'physicalDeviceTested':False,'gameplayMeasured':False,'scope':__doc__}
    if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
