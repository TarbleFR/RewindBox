#!/usr/bin/env python3
"""Execute the production shader-cache searches with the real key/compare/hash bodies.

GPU compilation, mutex and SIMD lanes are host adapters. This verifies lookup,
ownership and publication; synthetic lookup timings are not iPhone FPS results.
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

import rpcs3_runtime_log_followup as log_followup

ROOT = Path(__file__).resolve().parents[1]
CACHE = 'rpcs3/Emu/RSX/Program/ProgramStateCache.h'
COMPARE = 'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp'
SUPPORT = [COMPARE, 'rpcs3/Emu/RSX/Program/RSXVertexProgram.h',
           'rpcs3/Emu/RSX/Program/RSXFragmentProgram.h',
           'rpcs3/Emu/RSX/Program/program_util.h', 'rpcs3/util/fnv_hash.hpp',
           'rpcs3/util/bit_set.hpp']


def braced(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for position in range(opening, len(text)):
        depth += (text[position] == '{') - (text[position] == '}')
        if depth == 0:
            return text[start:position + 1]
    raise ValueError(signature)


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def make_cpp(source, before):
    native = (ROOT / 'test/native/rpcs3_recent_shader.inc').read_text()
    preamble, suffix = native.split('// PRODUCTION_TYPES')
    adapters, tests = suffix.split('// PRODUCTION_CACHES')
    code = preamble
    code += '\n'.join(line for line in (source / SUPPORT[5]).read_text().splitlines()
                      if not line.startswith(('#include', '#pragma')))
    utility = (source / SUPPORT[3]).read_text()
    code += '\nnamespace rsx {\n'
    for name in ['fragment_program_texture_config', 'fragment_program_texture_state', 'vertex_program_texture_state']:
        code += braced(utility, 'struct ' + name + '\n') + ';\n'
    code += '}\n'
    for path, name in [(SUPPORT[1], 'RSXVertexProgram'), (SUPPORT[2], 'RSXFragmentProgram')]:
        code += braced((source / path).read_text(), 'struct ' + name + '\n') + ';\n'
    code += '\n'.join(line for line in (source / SUPPORT[4]).read_text().splitlines()
                      if not line.startswith(('#include', '#pragma')))
    code += adapters.split('// PRODUCTION_HASHES')[0]
    comparator = (source / COMPARE).read_text()
    for signature in [
        'usz vertex_program_utils::get_vertex_program_ucode_hash(',
        'usz vertex_program_storage_hash::operator()(',
        'bool vertex_program_compare::operator()(',
        'bool vertex_program_compare::compare_properties(',
        'bool fragment_program_utils::is_any_src_constant(',
        'usz fragment_program_utils::get_fragment_program_ucode_hash(',
        'usz fragment_program_storage_hash::operator()(',
        'bool fragment_program_compare::operator()(',
        'bool fragment_program_compare::compare_properties(']:
        code += '\n' + braced(comparator, signature) + '\n'
    code += adapters.split('// PRODUCTION_HASHES')[1]
    for label, tree in [('before', before), ('after', source)]:
        original = (tree / CACHE).read_text()
        body = braced(original, 'class program_state_cache\n')
        body = body.replace('program_state_cache', label + '_cache')
        body = body.replace('program_hash_util::vertex_program_storage_hash', 'CountedVertexHash')
        body = body.replace('program_hash_util::fragment_program_storage_hash', 'CountedFragmentHash')
        code += '\ntemplate<typename backend_traits>\n' + body + ';\n'
    code += tests
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--before', '--baseline', dest='before', type=Path,
                        help='Optional Core592 tree; otherwise reconstruct it from the authenticated follow-up fixture.')
    parser.add_argument('--benchmark', action='store_true')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--sanitize', action='store_true')
    modes.add_argument('--thread-sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    authenticated = log_followup.authenticate(source, manifest) if log_followup.KEY in manifest else None
    if not args.before and authenticated is None:
        parser.error('--before is required until the canonical runtime follow-up fixture is present')
    with tempfile.TemporaryDirectory(prefix='rpcs3-shader-cache-') as tmp:
        before = args.before.resolve() if args.before else log_followup.reconstruct(
            source, Path(tmp) / 'before', authenticated)
        before_hash = sha(before / CACHE)
        after_hash = sha(source / CACHE)
        if authenticated:
            assert before_hash == authenticated[1]['before_sha256'][CACHE]
            assert after_hash == authenticated[1]['after_sha256'][CACHE]
        support_hashes = {p: sha(source / p) for p in SUPPORT}
        code = make_cpp(source, before)
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            cxx += ['-isysroot', sdk]
        flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
                 '-UNDEBUG', '-DRPCS3_IOS', '-DARCH_ARM64']
        if args.sanitize:
            flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        elif args.thread_sanitize:
            flags += ['-O1', '-fsanitize=thread', '-fno-omit-frame-pointer']
        else:
            flags += ['-O3']
        flags += ['-UNDEBUG']
        cpp, exe = Path(tmp) / 'cache.cpp', Path(tmp) / 'cache'
        cpp.write_text(code)
        subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)] + (['benchmark'] if args.benchmark else []),
                             check=True, text=True, capture_output=True, timeout=120,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0',
                                      UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1'))
        assert sha(before / CACHE) == before_hash and sha(source / CACHE) == after_hash
        assert {p: sha(source / p) for p in SUPPORT} == support_hashes
        report = {'passed': True, 'host': platform.machine(),
                  'compiler': subprocess.check_output(cxx + ['--version'], text=True).splitlines()[0],
                  'compilerFlags': flags,
                  'sanitized': args.sanitize, 'threadSanitized': args.thread_sanitize,
                  'harnessSHA256': sha(cpp), 'sourceBeforeSHA256': before_hash,
                  'sourceAfterSHA256': after_hash, 'supportSHA256': support_hashes,
                  'results': json.loads(run.stdout), 'physicalDeviceTested': False,
                  'MetalCompiled': False, 'gameplayMeasured': False,
                  'scope': 'Production full cache classes, key ownership, hash and comparison. GPU compilation, mutex and SIMD-lane host adapters.'}
        if authenticated:
            report['followupFixtureSHA256'] = authenticated[1]['fixture_sha256']
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
