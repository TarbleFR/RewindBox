#!/usr/bin/env python3
"""Build 481: persistent ARM64 SPU object cache. Host evidence in three parts.

1. Policy: compiles and runs test/native/rpcs3_build481_spu_object_cache_test.cpp
   against the real rpcs3/Emu/Cell/SPUObjectCachePolicy.h of the materialized
   Core (host-address floor, bounded oldest-first eviction, variant names).
2. Mechanism: when an LLVM 22 toolchain is available (--llvm-config, $LLVM_CONFIG,
   Homebrew llvm@22 or PATH), compiles test/native/rpcs3_spu_object_relocation_test.cpp
   and runs it in SEPARATE PROCESSES: `save` generates and writes an object built
   with the Core's SPU triple, `load` links that object in a new process whose
   symbols live at different addresses and forbids code generation, `corrupt`
   proves that truncated or foreign files are rejected by the same validation the
   Core performs and replaced by a normal compilation. --require-llvm makes a
   missing toolchain an error (the Core build job); otherwise this part is
   reported as skipped (the Linux checks job).
3. Wiring: the materialized sources use the mechanism as reviewed: no baked host
   address remains in the SPU translator, the timebase symbol is mapped, the
   relocatability guard refuses persistence of any module that bakes one, the
   key folds the codegen identity, objects are validated before MCJIT, the
   cache is bounded and evicted oldest-first, JITPROF/SPUPROF carry the new
   counters, and deferred SPU compilation stays off.

No assertion here is iPhone evidence.
"""
import argparse
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
parser.add_argument('--sanitize', action='store_true')
parser.add_argument('--llvm-config', type=Path, default=None)
parser.add_argument('--require-llvm', action='store_true', help='fail when no LLVM toolchain is available for the mechanism proof')
parser.add_argument('--skip-native', action='store_true', help='source wiring checks only (no compiler on this host)')
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
        # Captured output is the only trace of a failed proof process: show it.
        if error.stdout:
            print(error.stdout, end='', flush=True)
        if error.stderr:
            print(error.stderr, end='', file=sys.stderr, flush=True)
        raise


compiler = shlex.split(os.environ.get('CXX', 'clang++'))
sdk = os.environ.get('HOST_MACOS_SDK')
env = dict(os.environ)
env.pop('SDKROOT', None)

# ------------------------------------------------------------------ 1. policy
if not args.skip_native:
    with tempfile.TemporaryDirectory(prefix='rpcs3-build481-policy-') as temporary:
        exe = Path(temporary) / 'spu-object-cache-policy'
        command = [*compiler]
        if sdk:
            command += ['-isysroot', sdk]
        command += ['-std=c++20', '-O1', '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-I', str(core),
                    str(ROOT / 'test/native/rpcs3_build481_spu_object_cache_test.cpp'), '-o', str(exe)]
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        run(command, env=env, timeout=180)
        run([exe], timeout=60)


# --------------------------------------------------------------- 2. mechanism
def find_llvm_config() -> Path | None:
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


def llvm_config(binary: Path, *flags: str) -> list[str]:
    return shlex.split(subprocess.run([str(binary), *flags], check=True, capture_output=True, text=True, timeout=60).stdout)


mechanism = 'skipped'
if not args.skip_native:
    binary = find_llvm_config()
    if binary is None:
        require(not args.require_llvm, 'no LLVM toolchain for the two-process relocation proof (set LLVM_CONFIG or HOST_LLVM_ROOT)')
        print('SKIP: no llvm-config on this host; the two-process relocation proof runs in the Core build job')
    else:
        version = subprocess.run([str(binary), '--version'], check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        require(version.startswith('22.'), f'the mechanism proof must run with the LLVM 22 release that builds the Core, found {version}')
        targets = llvm_config(binary, '--targets-built')
        require('AArch64' in targets, 'LLVM toolchain lacks the AArch64 target')
        bindir = Path(llvm_config(binary, '--bindir')[0])
        libdir = Path(llvm_config(binary, '--libdir')[0])
        mechanism_compiler = [str(bindir / 'clang++')] if (bindir / 'clang++').is_file() else [*compiler]
        with tempfile.TemporaryDirectory(prefix='rpcs3-build481-reloc-') as temporary:
            work = Path(temporary)
            exe = work / 'spu-object-relocation'
            cache_dir = work / 'spuobj-v6-test'
            cache_dir.mkdir()
            command = [*mechanism_compiler]
            if sdk and mechanism_compiler == compiler:
                command += ['-isysroot', sdk]
            command += ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-deprecated-declarations']
            command += [flag for flag in llvm_config(binary, '--cxxflags') if not flag.startswith(('-std=', '-O', '-g', '-W', '-fno-exceptions', '-fno-rtti'))]
            command += [str(ROOT / 'test/native/rpcs3_spu_object_relocation_test.cpp'), '-o', str(exe)]
            command += llvm_config(binary, '--ldflags')
            command += llvm_config(binary, '--libs', 'core', 'mcjit', 'native', 'aarch64', 'object', 'support', 'runtimedyld', 'executionengine', 'irreader')
            command += llvm_config(binary, '--system-libs')
            command += [f'-Wl,-rpath,{libdir}']
            run(command, env=env, timeout=300)
            save = run([exe, 'save', cache_dir], env=env, timeout=120, capture_output=True, text=True)
            print(save.stdout, end='')
            objects = sorted(path.name for path in cache_dir.iterdir() if path.suffix == '.obj')
            require(objects == ['__spu-0x00abc-reloctest.obj'], f'save must write exactly the module object, found {objects}')
            load = run([exe, 'load', cache_dir], env=env, timeout=120, capture_output=True, text=True)
            print(load.stdout, end='')
            require('PASS: relocated external data' in load.stdout, 'load process did not report the relocation proof')
            corrupt = run([exe, 'corrupt', cache_dir], env=env, timeout=120, capture_output=True, text=True)
            print(corrupt.stdout, end='')
            require('PASS: truncated and foreign objects are rejected' in corrupt.stdout, 'corrupt process did not report the validation proof')
            # The replaced object links again in a fourth process.
            reload = run([exe, 'load', cache_dir], env=env, timeout=120, capture_output=True, text=True)
            print(reload.stdout, end='')
            require('PASS: relocated external data' in reload.stdout, 'reload after replacement failed')
        mechanism = f'executed with {version}'

# ------------------------------------------------------------------ 3. wiring
policy = read('rpcs3/Emu/Cell/SPUObjectCachePolicy.h')
spu = read('rpcs3/Emu/Cell/SPULLVMRecompiler.cpp')
common = read('rpcs3/Emu/Cell/SPUCommonRecompiler.cpp')
jit = read('Utilities/JITLLVM.cpp')
jit_header = read('Utilities/JIT.h')
profile = read('Utilities/JITPhaseProfile.h')
performance = read('rpcs3/ios/RPCS3IOSPerformance.cpp')
performance_header = read('rpcs3/ios/RPCS3IOSPerformance.h')
experimental = read('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
settings = read('rpcs3/ios/RPCS3IOSSettings.cpp')
cmake = read('rpcs3/Emu/CMakeLists.txt')
translator = read('rpcs3/Emu/CPU/CPUTranslator.h')

# --- No baked host address in the SPU translator (the ARMSX3 457a932c7 defect class).
baked = re.compile(r'getInt64\s*\(\s*reinterpret_cast<\s*u(?:64|ptr)\s*>|CreateIntToPtr\s*\(\s*m_ir->getInt64\s*\(')
require(not baked.search(spu), 'SPULLVMRecompiler.cpp still turns a host address into an IR constant')
require(not baked.search(translator), 'CPUTranslator.h turns a host address into an IR constant')
for header in ('rpcs3/Emu/Cell/SPUARM64Lowering.h', 'rpcs3/Emu/Cell/SPUARM64CompareLowering.h',
               'rpcs3/Emu/CPU/Backends/AArch64/AArch64JIT.cpp', 'rpcs3/Emu/CPU/Backends/AArch64/SPUInterpreterGateway.h',
               'rpcs3/Emu/CPU/Backends/AArch64/SPUReservationHash.h'):
    require(not baked.search(read(header)), f'{header} turns a host address into an IR constant')
# Every reinterpret_cast<u64> left in the translator is a symbol mapping, never an IR constant.
for line_number, line in enumerate(spu.splitlines(), 1):
    if 'reinterpret_cast<u64>' in line and 'm_ir->' in line:
        raise SystemExit(f'FAIL: SPULLVMRecompiler.cpp:{line_number} feeds a host address into the IR builder: {line.strip()}')
require('m_engine->updateGlobalMapping("spu_timebase_offs", reinterpret_cast<u64>(&g_timebase_offs));' in spu,
        'the timebase offset must be mapped as a symbol once per engine')
require('m_module->getOrInsertGlobal("spu_timebase_offs", get_type<u64>())' in spu and '&g_timebase_offs)), get_type<u64*>()' not in spu,
        'SPU_RdDec must read the timebase offset through the external symbol')
require(spu.index('m_engine->updateGlobalMapping("spu_timebase_offs"') < spu.index('m_module->getOrInsertGlobal("spu_timebase_offs"'),
        'the mapping must be registered in init(), before any module references the symbol')

# --- Relocatability guard: persistence refused for any module that bakes a host address.
require('bool spu_llvm_module_is_relocatable(const llvm::Module& m, u64& offending)' in spu, 'relocatability guard missing')
require('rpcs3::spu::object_cache::is_host_address_constant(imm->getZExtValue())' in spu, 'guard must use the policy floor')
require('if (spu_cached_object || spu_llvm_module_is_relocatable(*_module, offending))' in spu, 'guard must gate the cached add')
require('added = m_jit.try_add_cached(std::move(_module), spu_obj_cache, std::move(spu_cached_object), spu_cache_outcome, llvm_error);' in spu,
        'cached add missing')
require('rpcs3::ios::record_spu_object_cache_event(rpcs3::ios::spu_object_cache_event::nonreloc);' in spu and
        'compiled without persistence' in spu, 'a non-relocatable module must be counted and compiled without persistence')
require('llvm::isa<llvm::GlobalValue>(value)' in spu, 'symbols must be accepted by the guard')
require('inline constexpr std::uint64_t host_address_floor = 1ull << 32;' in policy, 'host address floor changed')

# --- Hit path: object read and validated before the IR exists; passes and verification skipped on a hit.
require('spu_cached_object = jit_compiler::load_cached_object(spu_obj_cache + m_hash + ".obj", m_hash);' in spu,
        'the cached object must be loaded under the module name and require the entry symbol')
require('const bool use_spu_obj_cache = !spu_obj_cache.empty() && !g_cfg.core.spu_debug;' in spu, 'spu_debug must never reuse objects')
require('if (!spu_cached_object)\n#endif\n\t\t{\n\t\t\tfor (auto& f : *m_module)' in spu, 'a hit must skip the pass pipeline')
require('const bool verify_ir = !spu_cached_object;' in spu and 'if (verify_ir && verifyModule(*_module, &verification_out))' in spu,
        'a hit must skip IR verification')
require('m_hash += rpcs3::spu::object_cache::variant_suffix(m_use_tbl2, m_use_fma);' in spu, 'retry variants must not share an object name')
require(spu.index('m_hash += rpcs3::spu::object_cache::variant_suffix') < spu.index('jit_compiler::load_cached_object(spu_obj_cache + m_hash'),
        'the variant suffix must be part of the name before the lookup')
require('jit_phase::g_counters.add(jit_phase::spu_object_load, utils::get_tsc() - codegen_started, spu_cache_outcome.object_bytes);' in spu,
        'a hit must be measured as spu_object_load')
require('jit_phase::g_counters.add(jit_phase::spu_codegen, utils::get_tsc() - codegen_started, m_size);' in spu, 'a miss must keep spu_codegen')
require('if (!fn)\n\t\t{' in spu and 'fs::remove_file(spu_obj_cache + m_hash + ".obj.gz");' in spu, 'null entry point guard missing')
require('// Built once per process; the interpreter module is not persisted' in spu, 'interpreter module must stay process-local')

# --- JIT engine: validation before MCJIT, preloaded objects, SPU phases, identity.
require('static bool validate(const llvm::MemoryBuffer& buffer, std::string_view required_symbol)' in jit, 'object validation missing')
require('llvm::object::ObjectFile::createObjectFile(buffer.getMemBufferRef())' in jit and
        'return !(*flags & llvm::object::SymbolRef::SF_Undefined);' in jit, 'validation must parse the object and require a defined symbol')
require('jit_log.error("LLVM: Removed unloadable cached module: %s", path);' in jit, 'an unloadable cached module must be removed on the generic path')
require('jit_cached_object jit_compiler::load_cached_object(const std::string& path, const std::string& required_symbol)' in jit and
        'result.removed_invalid = true;' in jit, 'load_cached_object must report removed files')
require('bool jit_compiler::try_add_cached(std::unique_ptr<llvm::Module> _module, const std::string& path_dir, jit_cached_object preloaded, jit_cache_outcome& outcome, std::string& error)' in jit,
        'cached add missing')
require('ObjectCache cache{path_dir, this, true, std::move(preloaded.buffer), &outcome};' in jit, 'cached add must hand the preloaded object to the cache')
require('return std::move(m_preloaded);' in jit and 'm_outcome->loaded = true;' in jit, 'a preloaded object must replace the file read and report the hit')
require('m_outcome->written = true;' in jit and 'if (!module_file.commit())' in jit, 'a written object must be committed atomically and reported')
require('const jit_phase::scope phase_timer(m_spu ? jit_phase::spu_cache_write : jit_phase::ppu_cache_write, utils::get_tsc, obj.getBufferSize());' in jit,
        'SPU writes must be measured under their own phase')
require('ObjectCache::load(path, jit_phase::spu_cache_read)' in jit, 'SPU reads must be measured under their own phase')
require('std::string jit_compiler::spu_codegen_identity()' in jit and 'seed += NEOSTATION_SPU_CODEGEN_ID;' in jit and
        '|spu-objects-v1' in jit, 'SPU codegen identity missing')
require('static std::string spu_codegen_identity();' in jit_header and 'struct jit_cached_object' in jit_header and
        'struct jit_cache_outcome' in jit_header, 'JIT.h API missing')
for phase in ('spu_cache_read', 'spu_object_load', 'spu_cache_write'):
    require(f'\t\t{phase},' in profile and f'"{phase}"' in profile, f'phase {phase} missing')
require(profile.count('"ppu_translate", "ppu_opt", "ppu_verify", "ppu_codegen", "ppu_cache_write", "ppu_cache_read",\n\t\t"ppu_object_load", "ppu_finalize", "ppu_symbols", "spu_build", "spu_passes", "spu_codegen",\n\t\t"spu_cache_read", "spu_object_load", "spu_cache_write",') == 1,
        'phase names must keep the Build 444 order and append the Build 481 phases')

# --- Key, bounds and eviction at boot (single-threaded, before compile workers exist).
require('if (g_cfg.core.spu_cache && rpcs3::ios::get_experimental_policy().persistent_spu_object_cache)' in common,
        'the object cache must follow the SPU cache setting and the resolved policy')
require('fold(object_cache::format_version);' in common and 'fold_string(jit_compiler::spu_codegen_identity());' in common and
        'fold_string(jit_compiler::cpu(g_cfg.core.llvm_cpu.to_string()));' in common and 'fold(tsc_freq);' in common and 'fold(hw);' in common,
        'the key must fold format, settings, device features, CPU and codegen identity')
require('m_obj_cache_path = m_cache_path + fmt::format("spuobj-v%u-%s/", object_cache::format_version, fmt::base57(key, 16));' in common,
        'directory name must carry the format version and the key')
require('entry.name.starts_with("spuobj-") && m_cache_path + entry.name + "/" != m_obj_cache_path' in common,
        'directories of other keys must be removed')
require('const object_cache::eviction_plan plan = object_cache::plan_eviction(std::move(entries));' in common and
        'fs::remove_file(m_obj_cache_path + name);' in common, 'oldest-first eviction must apply the policy plan')
require('fs::remove_all(m_obj_cache_path, false)' not in common and 'rebuilding it' not in common,
        'a bound crossing must never drop the whole valid cache')
require('inline constexpr std::size_t max_files = 40\'000;' in policy and 'inline constexpr std::uint64_t max_bytes = 512ull << 20;' in policy,
        'bounds changed')
require(common.index('for (const std::string& name : stale_directories)') < common.index('if (!fs::create_path(m_obj_cache_path))') <
        common.index('object_cache::plan_eviction'), 'boot order: stale directories, create, evict')

# --- Policy resolution and the Core settings catalog (English, like its other entries).
require('resolved.persistent_spu_object_cache = arm64_default && rpcs3::spu::object_cache::arm64_objects_relocatable &&\n\t\tresolve_mode(g_cfg.ios_experimental.persistent_spu_object_cache, true);' in experimental,
        'Automatic must enable the cache on ARM64 only while the translator is relocatable')
require('inline constexpr bool arm64_objects_relocatable = true;' in policy, 'relocatable switch must be on')
require('"Keeps the compiled ARM64 SPU code of each title between sessions.' in settings and
        'process-specific addresses' not in settings, 'settings description must describe the new behaviour')

# --- Diagnostics: SPUPROF obj_* fields and the event recorder.
require('enum class spu_object_cache_event : u32' in performance_header and
        'void record_spu_object_cache_event(spu_object_cache_event event, u64 amount = 1) noexcept;' in performance_header,
        'event recorder API missing')
for name in ('hit', 'miss', 'written', 'write_failed', 'invalid', 'nonreloc', 'evicted', 'stale_directory', 'count'):
    require(f'\t{name},' in performance_header, f'event {name} missing')
require('"obj_hits=%llu obj_hit_kib=%.3f obj_misses=%llu obj_written=%llu obj_written_kib=%.3f obj_write_failures=%llu "\n\t\t\t"obj_invalid=%llu obj_nonreloc=%llu obj_evicted=%llu obj_stale_dirs=%llu",' in performance,
        'SPUPROF must report the object cache fields')
require(performance.index('obj_events[index] = m_spu_object_events[index].exchange(0, std::memory_order_relaxed);') <
        performance.index('"SPUPROF session=%llu'), 'object cache counters must be exchanged with zero per window')
require('for (auto& counter : m_spu_object_events)\n\t\t\tcounter = 0;' in performance, 'reset must clear the object cache counters')
require('void record_spu_object_cache_event(spu_object_cache_event event, u64 amount) noexcept\n{\n\tg_performance_registry.record_spu_object_cache_event(event, amount);\n}' in performance,
        'event recorder wrapper missing')

# --- CMake: configure-time digest of the SPU codegen sources.
require('target_compile_definitions(rpcs3_emu PRIVATE NEOSTATION_SPU_CODEGEN_ID="${NEOSTATION_SPU_CODEGEN_ID}")' in cmake,
        'CMake must define the SPU codegen digest')
for digested in ('Cell/SPULLVMRecompiler.cpp', 'Cell/SPUCommonRecompiler.cpp', 'Cell/SPURecompiler.h', 'Cell/SPUThread.h',
                 'Cell/SPUAnalyser.h', 'Cell/SPUObjectCachePolicy.h', 'Cell/SPUARM64Lowering.h', 'Cell/SPUARM64CompareLowering.h',
                 'CPU/CPUTranslator.cpp', 'CPU/CPUTranslator.h', 'CPU/Backends/AArch64/AArch64JIT.cpp', 'CPU/Backends/AArch64/AArch64JIT.h',
                 'CPU/Backends/AArch64/SPUChecksum.h', 'CPU/Backends/AArch64/SPUInterrupts.h', 'CPU/Backends/AArch64/SPUInterpreterGateway.h',
                 'CPU/Backends/AArch64/SPUReservationHash.h', 'CPU/Backends/AArch64/SPUReservationScan.h',
                 '../../Utilities/JIT.h', '../../Utilities/JITLLVM.cpp',
                 '../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp'):
    block = cmake[cmake.index('NEOSTATION_SPU_CODEGEN_DIGEST'):]
    require(f'        {digested}\n' in block or f'        {digested})\n' in block, f'SPU digest must cover {digested}')
    if not digested.startswith('../../3rdparty'):
        require((core / 'rpcs3/Emu' / digested).is_file(), f'digested source missing: {digested}')

# --- Unchanged guarantees of earlier builds.
require('deferred_compile_enabled = false;' in read('rpcs3/Emu/Cell/SPUDeferredCompilePolicy.h'), 'the Build 436 deferred compile switch must stay off')
require('fpm.addPass(EarlyCSEPass(true));' in spu, 'SPU pipeline must be unchanged')
require('vm::range_lock<128>(range_lock, addr, 128);' in read('rpcs3/Emu/Cell/SPUThread.cpp'), 'PUTLLC 16-byte path must remain')

print(f'PASS: Build 481 SPU object cache (policy executed; relocation proof {mechanism}; translator free of baked host addresses; '
      'guard, validation, key, bounds, eviction, counters and digest wired; deferred SPU compile still off)')
