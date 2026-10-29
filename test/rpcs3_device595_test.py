#!/usr/bin/env python3
"""Targeted production-code checks for the post-595 allocation reductions.

GPU creation is a host boundary. The temporary-cache methods, array storage,
encoded key and array swap are extracted from the supplied Core sources.
This is neither an iOS build nor a measurement of game performance.
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
from rpcs3_texture_exact_index_test import stripped

ROOT = Path(__file__).resolve().parents[1]
CACHE = 'rpcs3/Emu/RSX/Common/texture_cache.h'
ARRAY = 'rpcs3/Emu/RSX/Common/simple_array.hpp'
RANGE = 'Utilities/address_range.h'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def make_temporary(source, baseline):
    current, old = (source / CACHE).read_text(), (baseline / CACHE).read_text()
    for path in [RANGE, 'rpcs3/Emu/RSX/Common/TextureUtils.h']:
        assert sha(source / path) == sha(baseline / path)
    key = braced(current, 'struct temporary_subresource_key\n') + ';'
    old_member = '\t\tstd::unordered_multimap<u32, std::pair<deferred_subresource, image_view_type>> m_temporary_subresource_cache;'
    begin = current.index('#ifdef RPCS3_IOS\n\t\t// The cache only consumes')
    end = current.index('#endif', begin) + len('#endif')
    assert current[:begin] + old_member + current[end:] == old
    code = (ROOT / 'test/native/rpcs3_temporary_key.inc').read_text()
    # Isolate the metadata change with the candidate array implementation shared
    # by both cache variants. The separate array case compares both full classes.
    code = code.replace('@RANGE@', stripped(source / RANGE)).replace(
        '@ARRAY@', '#define RPCS3_IOS\n' + stripped(source / ARRAY) + '\n#undef RPCS3_IOS')
    attrs = braced((source / 'rpcs3/Emu/RSX/Common/TextureUtils.h').read_text(), 'struct image_section_attributes_t\n')
    code = code.replace('@ATTRIBUTES@', attrs + ';')
    # Original descriptor fields and actual encoding; unused construction helpers
    # are not part of these cache operations.
    desc = current[current.index('struct deferred_subresource :'):]
    fields = desc[:desc.index('\n\t\t\tdeferred_subresource() = default;')]
    code = code.replace('@DESCRIPTOR@', fields + '\n' + braced(desc, 'u64 encoded_properties() const') + '\n};')
    versions = ''
    for name, text, compact in [('before', old, False), ('after', current, True)]:
        versions += 'namespace ' + name + ' { struct Cache : Boundary {\n'
        versions += key + '\n' if compact else ''
        versions += 'std::unordered_multimap<u32, std::pair<' + ('temporary_subresource_key' if compact else 'deferred_subresource') + ', image_view_type>> m_temporary_subresource_cache;\n'
        versions += braced(text, 'image_view_type create_temporary_subresource(') + '\n'
        versions += braced(text, 'void notify_surface_changed(') + '\n'
        frame = braced(text, 'virtual void on_frame_end()')
        a, b = frame.index('for (auto& entry : m_temporary_subresource_cache)'), frame.index('m_predictor.on_frame_end();')
        versions += 'void clear() {' + frame[a:b] + '}\n'
        versions += '~Cache(){clear();}\n};}\n'
    return code.replace('@VERSIONS@', versions), [CACHE, ARRAY, RANGE, 'rpcs3/Emu/RSX/Common/TextureUtils.h']


def make_array(source, baseline):
    current, old = (source / ARRAY).read_text(), (baseline / ARRAY).read_text()
    a=current.index('#ifdef RPCS3_IOS')
    b=current.index('#endif',a)+len('#endif\n\n')
    assert current[:a]+current[b:]==old
    code=(ROOT/'test/native/rpcs3_array_transfer.inc').read_text()
    versions=''
    for name,tree,ios in [('before',baseline,False),('after',source,True),('desktop',source,False)]:
        if ios:versions+='#define RPCS3_IOS\n'
        body=stripped(tree/ARRAY).replace('namespace rsx','namespace '+name).replace('rsx::',name+'::')
        versions+='namespace '+name+' { template<class T>using reverse_pointer=std::reverse_iterator<T*>;namespace aligned_allocator=adapters;}\n'+body+'\n'
        if ios:versions+='#undef RPCS3_IOS\n'
    return code.replace('@VERSIONS@',versions),[ARRAY]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--case', choices=['array', 'temporary'], required=True)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--sanitizer', choices=['address,undefined'])
    p.add_argument('--leak-check', choices=['enabled', 'disabled'], default='enabled')
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code, paths = globals()['make_' + args.case](source, baseline)
    assert '@' not in code
    inputs = {path: sha(source / path) for path in paths}
    baseline_inputs = {path: sha(baseline / path) for path in paths}
    cxx = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    if args.sanitizer:
        flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    else:
        flags += ['-O3']
    with tempfile.TemporaryDirectory(prefix='rpcs3-device595-') as tmp:
        cpp, exe = Path(tmp) / 'test.cpp', Path(tmp) / 'test'
        cpp.write_text(code)
        subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=180,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=' + str(int(args.leak_check == 'enabled')), UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
        results = json.loads(run.stdout)
    assert inputs == {path: sha(source / path) for path in paths}
    assert baseline_inputs == {path: sha(baseline / path) for path in paths}
    report = dict(passed=True, case=args.case, sourceSHA256=inputs, baselineSHA256=baseline_inputs,
                  harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),
                  compiler=subprocess.check_output(cxx + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, host=platform.machine(), results=results,
                  leakSanitizerEnabled=bool(args.sanitizer and args.leak_check == 'enabled'),
                  cacheVariantsUseCandidateArray=args.case == 'temporary',
                  physicalDeviceTested=False, gameplayMeasured=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
