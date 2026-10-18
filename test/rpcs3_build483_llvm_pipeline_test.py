#!/usr/bin/env python3
"""Build 483: selectable LLVM pipelines of the RPCS3 recompilers. Host evidence in two parts.

1. Harness (when an LLVM 22 toolchain is available: --llvm-config, $LLVM_CONFIG, $HOST_LLVM_ROOT,
   Homebrew llvm@22 or PATH): compiles test/native/rpcs3_llvm_pipeline_harness.cpp and runs
     cc-hazard   InstCombine erases a direct call whose convention differs from its defined
                 callee (a non-terminator unreachable takes its place and the rest of the
                 pipeline leaves no call); the matched call survives. The Core therefore sets
                 the callee convention on both m_test_state calls before adding InstCombine
                 (upstream eda7621f / ARMSX3 ab53473f7).
     kernels     the five pipelines of the Core (PPU none/EarlyCSE/Extended, SPU Reference
                 481/Upstream InstCombine) on synthetic kernels shaped like translator output:
                 verification, IR and AArch64 (apple-m4) instruction counts, pass time and
                 bit-exact execution against the unoptimized module on the host.
   --require-llvm makes a missing toolchain an error (the Core build job).
2. Wiring: the materialized sources select the pipelines as reviewed: enums and settings,
   effective PPU level (Build 444 boolean = EarlyCSE), objects named per level (settings
   bits) and per SPU pipeline (object-cache key), InstCombine only on the Upstream SPU
   pipeline with convention-matched m_test_state calls, Extended PPU pipeline composition,
   JITPROF pipeline fields, settings catalog entries, PPU digest covering PPUThread.cpp,
   and the Build 436/481 guarantees unchanged.

Measured on the host only; nothing here is iPhone evidence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('source', type=Path, help='materialized RPCS3 Core source tree')
parser.add_argument('--llvm-config', type=Path, default=None)
parser.add_argument('--require-llvm', action='store_true')
parser.add_argument('--report', type=Path, default=None, help='where to copy the kernels JSON report')
parser.add_argument('--skip-native', action='store_true')
args = parser.parse_args()
core = args.source.resolve()


def read(relative: str) -> str:
    return (core / relative).read_text(encoding='utf-8')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def run(command, **kwargs):
    print('+', ' '.join(shlex.quote(str(part)) for part in command), flush=True)
    try:
        return subprocess.run([str(part) for part in command], check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, end='', flush=True)
        if error.stderr:
            print(error.stderr, end='', file=sys.stderr, flush=True)
        raise


def find_llvm_config():
    candidates = []
    if args.llvm_config:
        candidates.append(args.llvm_config)
    if os.environ.get('LLVM_CONFIG'):
        candidates.append(Path(os.environ['LLVM_CONFIG']))
    if os.environ.get('HOST_LLVM_ROOT'):
        candidates.append(Path(os.environ['HOST_LLVM_ROOT']) / 'bin/llvm-config')
    brew = shutil.which('brew')
    if brew:
        try:
            prefix = subprocess.run([brew, '--prefix', 'llvm@22'], check=True, capture_output=True, text=True, timeout=60).stdout.strip()
            candidates.append(Path(prefix) / 'bin/llvm-config')
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    on_path = shutil.which('llvm-config')
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def llvm_config(binary, *flags):
    return shlex.split(subprocess.run([str(binary), *flags], check=True, capture_output=True, text=True, timeout=60).stdout)


# ------------------------------------------------------------------ 1. harness
harness = 'skipped'
if not args.skip_native:
    binary = find_llvm_config()
    if binary is None:
        require(not args.require_llvm, 'no LLVM toolchain for the pipeline harness (set LLVM_CONFIG or HOST_LLVM_ROOT)')
        print('SKIP: no llvm-config on this host; the pipeline harness runs in the Core build job')
    else:
        version = subprocess.run([str(binary), '--version'], check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        require(version.startswith('22.'), f'the harness must run with the LLVM 22 release that builds the Core, found {version}')
        require('AArch64' in llvm_config(binary, '--targets-built'), 'LLVM toolchain lacks the AArch64 target')
        bindir = Path(llvm_config(binary, '--bindir')[0])
        libdir = Path(llvm_config(binary, '--libdir')[0])
        compiler = [str(bindir / 'clang++')] if (bindir / 'clang++').is_file() else shlex.split(os.environ.get('CXX', 'clang++'))
        env = dict(os.environ)
        env.pop('SDKROOT', None)
        with tempfile.TemporaryDirectory(prefix='rpcs3-build483-llvm-') as temporary:
            work = Path(temporary)
            exe = work / 'llvm-pipeline-harness'
            command = [*compiler, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-deprecated-declarations']
            command += [flag for flag in llvm_config(binary, '--cxxflags') if not flag.startswith(('-std=', '-O', '-g', '-W', '-fno-exceptions', '-fno-rtti'))]
            command += [str(ROOT / 'test/native/rpcs3_llvm_pipeline_harness.cpp'), '-o', str(exe)]
            command += llvm_config(binary, '--ldflags')
            command += llvm_config(binary, '--libs', 'core', 'irreader', 'passes', 'mcjit', 'native', 'aarch64', 'object', 'support', 'runtimedyld', 'executionengine', 'transformutils', 'scalaropts', 'instcombine', 'analysis')
            command += llvm_config(binary, '--system-libs')
            command += [f'-Wl,-rpath,{libdir}']
            run(command, env=env, timeout=600)
            hazard = run([exe, 'cc-hazard'], env=env, timeout=120, capture_output=True, text=True)
            print(hazard.stdout, end='')
            require('PASS: InstCombine erases a direct call with a mismatched convention (non-terminator unreachable)' in hazard.stdout, 'calling-convention hazard proof missing')
            report = work / 'llvm-pipeline-kernels.json'
            kernels = run([exe, 'kernels', report], env=env, timeout=300, capture_output=True, text=True)
            print(kernels.stdout, end='')
            require('PASS: 7 kernels x 5 pipelines verified' in kernels.stdout, 'kernel proof missing')
            data = json.loads(report.read_text(encoding='utf-8'))
            require(data['all_variants_bit_exact'] is True, 'a pipeline changed a kernel result')
            require(len(data['kernels']) == 7, 'kernel count')
            # The Upstream SPU pipeline must not generate more AArch64 instructions than Reference 481 on any SPU kernel,
            # and the PPU levels must be monotonic in IR size on the PPU kernels (a regression here would be visible on device).
            for entry in data['kernels']:
                by = {v['pipeline']: v for v in entry['variants']}
                if entry['family'] == 'spu':
                    require(by['spu_upstream']['aarch64_instructions'] <= by['spu_reference']['aarch64_instructions'],
                            f"{entry['name']}: Upstream InstCombine emits more AArch64 instructions than Reference 481")
                else:
                    require(by['ppu_early_cse']['ir_instructions'] <= by['none']['ir_instructions'] and
                            by['ppu_extended']['ir_instructions'] <= by['ppu_early_cse']['ir_instructions'],
                            f"{entry['name']}: PPU levels are not monotonic")
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(report, args.report)
        harness = f'executed with {version}'

# ------------------------------------------------------------------ 2. wiring
types_header = read('rpcs3/Emu/system_config_types.h')
types_source = read('rpcs3/Emu/system_config_types.cpp')
config = read('rpcs3/Emu/system_config.h')
ppu = read('rpcs3/Emu/Cell/PPUThread.cpp')
spu = read('rpcs3/Emu/Cell/SPULLVMRecompiler.cpp')
common = read('rpcs3/Emu/Cell/SPUCommonRecompiler.cpp')
settings = read('rpcs3/ios/RPCS3IOSSettings.cpp')
performance = read('rpcs3/ios/RPCS3IOSPerformance.cpp')
cmake = read('rpcs3/Emu/CMakeLists.txt')

# --- Enums, formatters and settings.
require('enum class ppu_llvm_pipeline_type\n{\n\tupstream,' in types_header and 'enum class spu_llvm_pipeline_type\n{\n\treference,' in types_header,
        'pipeline enums missing')
for name in ('"Upstream ARM64"', '"EarlyCSE"', '"Extended"', '"Reference 481"', '"Upstream InstCombine"'):
    require(name in types_source, f'formatter value {name} missing')
require('cfg::_enum<ppu_llvm_pipeline_type> ppu_llvm_pipeline{ this, "PPU LLVM Pipeline", ppu_llvm_pipeline_type::upstream };' in config,
        'PPU pipeline setting must default to Upstream ARM64')
require('cfg::_enum<spu_llvm_pipeline_type> spu_llvm_pipeline{ this, "SPU LLVM Pipeline", spu_llvm_pipeline_type::upstream };' in config,
        'SPU pipeline setting must default to Upstream InstCombine')
require('cfg::_bool ppu_llvm_ir_passes{ this, "PPU LLVM IR Passes", false };' in config, 'the Build 444 boolean must remain')
require('SETTING("emulator.ppu_llvm_pipeline", "Emulator", "Compilation", "PPU LLVM pipeline (ARM64)"' in settings and
        'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.core.ppu_llvm_pipeline, 0, 0, 0)' in settings, 'PPU pipeline catalog entry missing')
require('SETTING("emulator.spu_llvm_pipeline", "Emulator", "Compilation", "SPU LLVM pipeline"' in settings and
        'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.core.spu_llvm_pipeline, 0, 0, 0)' in settings, 'SPU pipeline catalog entry missing')

# --- PPU: effective level, objects named per level, Extended composition, both run sites.
require('static ppu_llvm_pipeline_type ppu_effective_pipeline()' in ppu and
        'if (selected == ppu_llvm_pipeline_type::upstream && g_cfg.core.ppu_llvm_ir_passes)' in ppu and
        'return ppu_llvm_pipeline_type::early_cse;' in ppu, 'effective pipeline helper must keep the Build 444 boolean as EarlyCSE')
require('\t\t\t\tarm64_ir_passes,\n\t\t\t\tarm64_ir_passes_extended,\n\n\t\t\t\t__bitset_enum_max' in ppu, 'Extended bit must be appended last')
require('case ppu_llvm_pipeline_type::extended:\n\t\t\t\tsettings += ppu_settings::arm64_ir_passes;\n\t\t\t\tsettings += ppu_settings::arm64_ir_passes_extended;' in ppu,
        'Extended objects must carry both bits')
require('case ppu_llvm_pipeline_type::early_cse:\n\t\t\t\tsettings += ppu_settings::arm64_ir_passes;\n\t\t\t\tbreak;' in ppu, 'EarlyCSE objects must carry the Build 444 bit only')
extended = ('\t\tfpm_extended.addPass(EarlyCSEPass(true));\n\t\tfpm_extended.addPass(SimplifyCFGPass());\n\t\tfpm_extended.addPass(InstCombinePass());\n'
            '\t\tfpm_extended.addPass(DSEPass());\n\t\tfpm_extended.addPass(createFunctionToLoopPassAdaptor(LICMPass(LICMOptions()), true));\n\t\tfpm_extended.addPass(ADCEPass());\n')
require(extended in ppu, 'Extended PPU pipeline composition changed')
require('FunctionPassManager& fpm_selected = ppu_pipeline == ppu_llvm_pipeline_type::extended ? fpm_extended : fpm;' in ppu, 'pipeline selection missing')
require(ppu.count('fpm_selected.run(*func, fam);') == 2 and ppu.count('#ifdef ARCH_X64 // TODO\n') == 2, 'both ARM64 run sites must use the selected pipeline; the x86-64 gates stay')
require('fpm.addPass(EarlyCSEPass());' in ppu, 'the x86-64 pipeline must stay EarlyCSE')
require('#include <llvm/Transforms/InstCombine/InstCombine.h>' in ppu, 'PPUThread.cpp must include InstCombine')

# --- SPU: InstCombine only on the Upstream pipeline, convention-matched m_test_state calls, key fold.
require('\t\tfpm.addPass(SimplifyCFGPass());\n\t\t// NEOSTATION_BUILD483_LLVM_PIPELINES_V1' in spu and
        'if (g_cfg.core.spu_llvm_pipeline == spu_llvm_pipeline_type::upstream)\n\t\t{\n\t\t\tfpm.addPass(InstCombinePass());\n\t\t}\n\t\tfpm.addPass(DSEPass());' in spu,
        'InstCombine must sit between SimplifyCFG and DSE on the Upstream SPU pipeline only')
require(spu.count('m_ir->CreateCall(m_test_state, {m_thread})->setCallingConv(m_test_state->getCallingConv());') == 2 and
        spu.count('m_ir->CreateCall(m_test_state, {m_thread});') == 0, 'both m_test_state calls must carry the callee convention')
require('#include <llvm/Transforms/InstCombine/InstCombine.h>' in spu, 'SPULLVMRecompiler.cpp must include InstCombine')
# Every other direct call to a function defined in the module already matches (chunks, functions, interpreter entries).
for site in ('call->setCallingConv(func->getCallingConv());', '_call->setCallingConv(fn->getCallingConv());',
             'entry_call->setCallingConv(entry_chunk->chunk->getCallingConv());', 'call0->setCallingConv(CallingConv::GHC);'):
    require(site in spu, f'convention site missing: {site}')
require('const u32 spu_pipeline = static_cast<u32>(g_cfg.core.spu_llvm_pipeline.get());\n\t\tfold(spu_pipeline);' in common,
        'the SPU pipeline must be folded into the object-cache key')
require(common.index('fold(object_cache::format_version);') < common.index('fold(spu_pipeline);') < common.index('sha1_finish(&ctx, key);'),
        'pipeline fold must be part of the key')

# --- Diagnostics and digest.
require('fmt::append(jit_line, " ppu_pipeline=%u ppu_ir_passes=%u spu_pipeline=%u",' in performance, 'JITPROF must name the pipelines')
require('#include "Emu/system_config.h"' in performance, 'performance reporter must read the settings')
require('        Cell/PPUThread.cpp\n' in cmake[cmake.index('NEOSTATION_PPU_CODEGEN_DIGEST'):cmake.index('NEOSTATION_SPU_CODEGEN_DIGEST')],
        'the PPU digest must cover the pipeline definition in PPUThread.cpp')

# --- Guarantees of earlier builds.
require('deferred_compile_enabled = false;' in read('rpcs3/Emu/Cell/SPUDeferredCompilePolicy.h'), 'deferred SPU compile must stay off')
require('inline constexpr bool arm64_objects_relocatable = true;' in read('rpcs3/Emu/Cell/SPUObjectCachePolicy.h'), 'object cache policy unchanged')
require('bool spu_llvm_module_is_relocatable(const llvm::Module& m, u64& offending)' in spu, 'relocatability guard unchanged')
require(re.search(r'getInt64\s*\(\s*reinterpret_cast<\s*u(?:64|ptr)\s*>', spu) is None, 'no baked host address may return')

print(f'PASS: Build 483 LLVM pipelines (harness {harness}; enums, settings, effective PPU level, per-level object names, '
      'SPU key fold, InstCombine with matched conventions, Extended composition, JITPROF fields and PPU digest wired)')
