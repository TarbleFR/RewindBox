#!/usr/bin/env python3
"""Test private fragment-cache key normalization against production GLSL consumers.

The complete key/cache/hint bodies are extracted, not reimplemented. Host adapters
provide SIMD lanes, mutexes, shader lane annotations and the GPU compilation
boundary. Generated GLSL fragments are deterministic fixtures, not game dumps.
No glslang/SPIRV-Cross/Metal tool is required by the Apple gate.
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

ROOT = Path(__file__).resolve().parents[1]
CACHE = 'rpcs3/Emu/RSX/Program/ProgramStateCache.h'
COMPARE = 'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp'
THREAD = 'rpcs3/Emu/RSX/RSXThread.cpp'
DISK = 'rpcs3/Emu/RSX/rsx_cache.h'
SOURCE = [CACHE, COMPARE]
BASELINE = SOURCE + [THREAD, DISK]
SUPPORT = [
    'rpcs3/Emu/RSX/Program/RSXVertexProgram.h',
    'rpcs3/Emu/RSX/Program/RSXFragmentProgram.h',
    'rpcs3/Emu/RSX/Program/program_util.h',
    'rpcs3/util/fnv_hash.hpp', 'rpcs3/util/bit_set.hpp',
    'rpcs3/Emu/RSX/Program/Assembler/FPOpcodes.h',
    'rpcs3/Emu/RSX/Program/Assembler/FPOpcodes.cpp',
    'rpcs3/Emu/RSX/Program/ShaderParam.h',
    'rpcs3/Emu/RSX/Program/FragmentProgramDecompiler.cpp',
    'rpcs3/Emu/RSX/Program/FragmentProgramDecompiler.h',
    'rpcs3/Emu/RSX/Program/GLSLCommon.cpp',
    'rpcs3/Emu/RSX/VK/VKFragmentProgram.cpp',
    'rpcs3/Emu/RSX/Core/RSXDriverState.h', THREAD, DISK,
]
ADAPTER = ROOT / 'test/native/rpcs3_bo2_fragment_key.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


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


def harness(source, baseline):
    """Pure assembly of the executed C++ from authenticated source trees."""
    read = lambda p: (source / p).read_text()
    cache, comp = read(CACHE), read(COMPARE)
    before_cache, before_comp = (baseline / CACHE).read_text(), (baseline / COMPARE).read_text()
    # No persisted identity, caller ordering or common ucode-analysis changes.
    # The device594 follow-up changes prefetch invalidation, covered by its
    # own native test. The caller, its ordering and every other body stay exact.
    thread_text, old_thread = read(THREAD), (baseline / THREAD).read_text()
    prefetch = 'void thread::prefetch_fragment_program()'
    assert thread_text.replace(braced(thread_text, prefetch), '@PREFETCH@', 1) == old_thread.replace(braced(old_thread, prefetch), '@PREFETCH@', 1)
    assert sha(source / DISK) == sha(baseline / DISK)
    analysis = 'fragment_program_utils::fragment_program_metadata fragment_program_utils::analyse_fragment_program('
    assert braced(comp, analysis) == braced(before_comp, analysis)
    current = braced(read(THREAD), 'void thread::analyse_current_rsx_pipeline(')
    assert current.index('m_program_cache_hint.invalidate(') < current.index('prefetch_fragment_program(')
    code = ADAPTER.read_text()
    body = '\n'.join(line for line in read(SUPPORT[4]).splitlines()
                     if not line.startswith(('#include', '#pragma')))
    body += '\nnamespace rsx {\n'
    for name in ['fragment_program_texture_config', 'fragment_program_texture_state', 'vertex_program_texture_state']:
        body += braced(read(SUPPORT[2]), 'struct ' + name + '\n') + ';\n'
    body += braced(read(SUPPORT[12]), 'enum pipeline_state : u32') + ';\n}\n'
    body += '\nnamespace rsx::assembler {\n' + braced(read(SUPPORT[5]), 'enum FP_opcode\n') + ';\n}\nusing namespace rsx::assembler;\n'
    for marker in ['enum register_type\n', 'enum register_precision\n', 'union OPDEST\n', 'union SRC0\n', 'union SRC1\n', 'union SRC2\n', 'union SRC_Common\n']:
        body += braced(read(SUPPORT[1]), marker) + ';\n'
    for path, name in [(SUPPORT[0], 'RSXVertexProgram'), (SUPPORT[1], 'RSXFragmentProgram')]:
        body += braced(read(path), 'struct ' + name + '\n') + ';\n'
    body += '\n'.join(line for line in read(SUPPORT[3]).splitlines()
                      if not line.startswith(('#include', '#pragma')))
    body += '\nnamespace rsx::assembler::FP {\n'
    for marker in ['bool is_instruction_valid(', 'u8 get_operand_count(']:
        body += braced(read(SUPPORT[6]), marker) + '\n'
    body += '}\n'
    for marker in ['enum ParamFlag\n', 'struct ParamItem\n', 'struct ParamType\n', 'struct ParamArray\n']:
        body += braced(read(SUPPORT[7]), marker) + ';\n'
    code = code.replace('// @PRODUCTION_TYPES@', body)
    body = 'namespace program_hash_util {\n'
    for name in ['vertex_program_utils', 'fragment_program_utils', 'vertex_program_storage_hash',
                 'fragment_program_storage_hash', 'vertex_program_compare', 'fragment_program_compare']:
        body += braced(cache, 'struct ' + name + '\n') + ';\n'
    body += '}\nusing namespace program_hash_util;\n'
    for signature in [
        'usz vertex_program_utils::get_vertex_program_ucode_hash(',
        'usz vertex_program_storage_hash::operator()(', 'bool vertex_program_compare::operator()(',
        'bool vertex_program_compare::compare_properties(',
        'bool fragment_program_utils::is_any_src_constant(',
        'static u16 fragment_instruction_input_mask(',
        'u16 fragment_program_utils::get_fragment_program_input_mask(',
        'std::optional<RSXFragmentProgram> fragment_program_utils::normalize_fragment_program_key(',
        analysis, 'usz fragment_program_utils::get_fragment_program_ucode_hash(',
        'usz fragment_program_storage_hash::operator()(', 'bool fragment_program_compare::operator()(',
        'bool fragment_program_compare::compare_properties(']:
        body += braced(comp, signature) + '\n'
    # A separate exact baseline analysis body enables meaningful common-path timings.
    body += 'namespace baseline_analysis {\nstruct fragment_program_utils {\n'
    body += braced(before_cache, 'struct fragment_program_metadata\n') + ';\n'
    body += 'static fragment_program_metadata analyse_fragment_program(const void*);\nstatic bool is_any_src_constant(v128);\n};\n'
    body += braced(before_comp, 'bool fragment_program_utils::is_any_src_constant(') + '\n' + braced(before_comp, analysis) + '\n}\n'
    code = code.replace('// @PRODUCTION_HASHES@', body)
    body = 'namespace rsx {\n' + braced(cache, 'struct program_cache_hint_t\n') + ';\n'
    for name in ['invalidate', 'invalidate_vertex_program', 'invalidate_fragment_program', 'cache_vertex_program', 'cache_fragment_program']:
        body += braced(comp, 'void program_cache_hint_t::' + name + '(') + '\n'
    code = code.replace('// @PRODUCTION_HINTS@', body + '}\n')
    body = braced(read(SUPPORT[8]), 'static const std::string reg_table[] =') + ';\n'
    for marker in ['std::string FragmentProgramDecompiler::AddReg(', 'std::string FragmentProgramDecompiler::AddConst(',
                   'std::string FragmentProgramDecompiler::ClampValue(', 'template<typename T> std::string FragmentProgramDecompiler::GetSRC(']:
        body += braced(read(SUPPORT[8]), marker) + '\n'
    code = code.replace('// @PRODUCTION_DECOMPILER@', body)
    body = braced(read(SUPPORT[10]), 'void insert_fragment_shader_inputs_block(')
    body = body.replace('FN(x.location < y.location)', '[](const auto& x,const auto& y){return x.location<y.location;}')
    code = code.replace('// @PRODUCTION_INPUT_BLOCK@', body)
    code = code.replace('// @PRODUCTION_MAIN_START@', braced(read(SUPPORT[11]), 'void VKFragmentDecompilerThread::insertMainStart('))
    body = ''
    for label, original in [('before', before_cache), ('after', cache)]:
        body += '\ntemplate<typename backend_traits>\n' + braced(original, 'class program_state_cache\n').replace('program_state_cache', label + '_cache') + ';\n'
    code = code.replace('// @PRODUCTION_CACHES@', body)
    assert '// @' not in code
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined', 'thread'])
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--emit-glsl', type=Path, help='Optional deterministic fragments for the separate host translator proof.')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    source_hash = {p: sha(source / p) for p in SOURCE + SUPPORT}
    baseline_hash = {p: sha(baseline / p) for p in BASELINE}
    code = harness(source, baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
             '-DRPCS3_IOS', '-DARCH_ARM64']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    flags += ['-UNDEBUG']
    with tempfile.TemporaryDirectory(prefix='rpcs3-bo2-fragment-') as tmp:
        cpp, exe = Path(tmp) / 'test.cpp', Path(tmp) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        command = [str(exe)]
        if args.benchmark:
            command += ['--benchmark']
        if args.emit_glsl:
            command += ['--glsl', str(args.emit_glsl.resolve())]
        run = subprocess.run(command, text=True, capture_output=True, timeout=180,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0',
                                      UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            raise RuntimeError(f'{command} exited {run.returncode}\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}')
        result = json.loads(run.stdout)
    assert source_hash == {p: sha(source / p) for p in SOURCE + SUPPORT}
    assert baseline_hash == {p: sha(baseline / p) for p in BASELINE}
    report = {'passed': True, 'host': platform.machine(),
              'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
              'compilerFlags': flags, 'sanitizer': args.sanitizer, 'assertionsActive': True,
              'sourceSHA256': source_hash, 'baselineSHA256': baseline_hash,
              'harnessSHA256': hashlib.sha256(code.encode()).hexdigest(),
              'adapterSHA256': sha(ADAPTER), 'results': result,
              'physicalDeviceTested': False, 'MetalCompiled': False, 'gameplayMeasured': False,
              'scope': 'Complete production cache/hash/hint/parser; production GetSRC/input-block/main-start consumers. Host mutex/SIMD, lane-annotation, shader-compile and allocation adapters. Generated GLSL fragments are synthetic, not BO2 dumps.'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
