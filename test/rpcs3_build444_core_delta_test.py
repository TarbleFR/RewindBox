#!/usr/bin/env python3
"""Execute the Build 444 JIT phase profile on the host and verify the Core wiring.

The native test runs the phase registry with the real header from the
materialized source. The wiring checks prove that the production call sites use
it (PPU translate/verify/codegen/cache/link/finalize/symbols, SPU build/passes/
codegen, JITPROF reporter), that the PPU object cache name carries the codegen
identity, that the ARM64 IR passes stay opt-in and hashed, and that the relay
client uses the optional direct admission without any blocking gameplay path.
No assertion here is iPhone evidence.
"""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--sanitize', action='store_true')
args = parser.parse_args()
core = args.source.resolve()


def read(relative: str) -> str:
    return (core / relative).read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


compiler = shlex.split(os.environ.get('CXX', 'clang++'))
if sdk := os.environ.get('HOST_MACOS_SDK'):
    compiler += ['-isysroot', sdk]
env = dict(os.environ)
env.pop('SDKROOT', None)
with tempfile.TemporaryDirectory(prefix='rpcs3-build444-') as temporary:
    exe = Path(temporary) / 'jit-phase-profile'
    command = [*compiler, '-std=c++20', '-O1', '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
               '-I', str(core), str(ROOT / 'test/native/rpcs3_build444_core_delta_test.cpp'), '-o', str(exe)]
    if args.sanitize:
        command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run(command, check=True, env=env, timeout=120)
    subprocess.run([str(exe)], check=True, timeout=30)

profile = read('Utilities/JITPhaseProfile.h')
jit_header = read('Utilities/JIT.h')
jit = read('Utilities/JITLLVM.cpp')
ppu = read('rpcs3/Emu/Cell/PPUThread.cpp')
spu = read('rpcs3/Emu/Cell/SPULLVMRecompiler.cpp')
performance = read('rpcs3/ios/RPCS3IOSPerformance.cpp')
config = read('rpcs3/Emu/system_config.h')
settings = read('rpcs3/ios/RPCS3IOSSettings.cpp')
cmake = read('rpcs3/Emu/CMakeLists.txt')
client = read('rpcs3/ios/NeoSwapRelayClient.h')
relay_abi = read('rpcs3/ios/NeoSwapRelay.h')
exports = read('rpcs3/ios/RPCS3IOS.exports').splitlines()
core_api = read('rpcs3/ios/RPCS3IOS.cpp')

# --- Phase registry: constant-initialized, no constructor during dlopen.
require('inline constinit registry g_counters{};' in profile, 'phase registry must be constant-initialized')
require('inline thread_local std::uint64_t t_nested_ticks = 0;' in profile, 'nested-scope accounting missing')
require(all(name in profile for name in ('ppu_translate', 'ppu_opt', 'ppu_verify', 'ppu_codegen', 'ppu_cache_write',
                                         'ppu_cache_read', 'ppu_object_load', 'ppu_finalize', 'ppu_symbols',
                                         'spu_build', 'spu_passes', 'spu_codegen')), 'phase list changed')

# --- JITLLVM.cpp: cache read/write, codegen (miss) and object load are measured in place.
require('#include "JITPhaseProfile.h"' in jit, 'JITLLVM.cpp does not include the phase profile')
require('jit_phase::scope phase_timer(jit_phase::ppu_cache_write, utils::get_tsc, obj.getBufferSize());' in jit,
        'object cache write is not measured')
require('jit_phase::scope phase_timer(jit_phase::ppu_cache_read, utils::get_tsc);' in jit and
        'phase_timer.bytes = out.size();' in jit, 'object cache read is not measured with its decompressed size')
require(jit.count('const jit_phase::scope phase_timer(jit_phase::ppu_codegen, utils::get_tsc);\n\t\tm_engine->generateCodeForModule(ptr);') == 2,
        'both cached add() paths must time code generation')
require('jit_phase::scope phase_timer(jit_phase::ppu_object_load, utils::get_tsc);' in jit and
        'phase_timer.bytes = cache->getBufferSize();' in jit, 'object load is not measured')

# --- PPU cache identity: LLVM release + configure-time digest + target features.
require('static std::string codegen_identity();' in jit_header and
        'static const std::vector<std::string>& target_attributes();' in jit_header, 'JIT.h identity API missing')
require('#include <llvm/Config/llvm-config.h>' in jit and 'std::string seed = LLVM_VERSION_STRING;' in jit,
        'identity must include the LLVM release')
require('#ifdef NEOSTATION_PPU_CODEGEN_ID\n\t\tseed += NEOSTATION_PPU_CODEGEN_ID;' in jit,
        'identity must include the configure-time source digest')
require('for (const auto& attribute : target_attributes())' in jit, 'identity must include the target features')
require('return fmt::base57(output, 12);' in jit, 'identity digest must be a short base57 string')
require('const std::vector<std::string> attributes = target_attributes();' in jit and
        '.setMAttrs(attributes)' in jit, 'engine must advertise the same features the identity hashes')
attributes_body = jit[jit.index('const std::vector<std::string>& jit_compiler::target_attributes()'):jit.index('std::string jit_compiler::codegen_identity()')]
require(all(attributes_body.count(f'if (utils::{feature}())') == 1 for feature in ('has_sha3', 'has_dotprod', 'has_i8mm', 'has_sve', 'has_sve2')),
        'feature detection must live once in target_attributes(), shared by the engine and the identity')
constructor_body = jit[jit.index('jit_compiler::jit_compiler(const std::unordered_map<std::string, u64>& _link'):jit.index('jit_compiler& jit_compiler::operator=(thread_state s) noexcept')]
require('attributes.push_back(' not in constructor_body, 'the constructor must not build a second feature list')
require('fmt::append(obj_name, "v9-neostation-%s-%s-%s-%s.obj", fmt::base57(output, 16), fmt::base57(settings), '
        'jit_compiler::cpu(g_cfg.core.llvm_cpu.to_string()), jit_compiler::codegen_identity());' in ppu,
        'PPU object name must carry module hash, settings, CPU and the codegen identity')
require('v8-neostation-embedded1' not in ppu, 'old object name generation still emitted')
require('target_compile_definitions(rpcs3_emu PRIVATE NEOSTATION_PPU_CODEGEN_ID="${NEOSTATION_PPU_CODEGEN_ID}")' in cmake,
        'CMake must define the configure-time digest for the Core')
for digested in ('Cell/PPUTranslator.cpp', 'Cell/PPUTranslator.h', 'Cell/PPUThread.h', 'CPU/CPUTranslator.cpp',
                 '../../Utilities/JITLLVM.cpp', '../../Utilities/JITPhaseProfile.h',
                 '../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp'):
    require(f'        {digested}' in cmake, f'digest must cover {digested}')
    if not digested.startswith('../../3rdparty'):
        require((core / 'rpcs3/Emu' / digested).is_file(), f'digested source missing: {digested}')

# --- ARM64 IR passes: opt-in, hashed into the settings bits, measured.
require('cfg::_bool ppu_llvm_ir_passes{ this, "PPU LLVM IR Passes", false };' in config,
        'the ARM64 IR pass option must exist and default to off')
require('SETTING("emulator.ppu_llvm_ir_passes", "Emulator", "Compilation", "PPU LLVM IR passes (ARM64)"' in settings,
        'the option must be exposed next to the compile-thread limit')
require('kind::RPCS3_IOS_SETTING_BOOLEAN, g_cfg.core.ppu_llvm_ir_passes, 0, 1, 1)' in settings, 'option kind/range')
require('\t\t\t\tarm64_ir_passes,\n\n\t\t\t\t__bitset_enum_max' in ppu, 'settings bit must be appended last')
require('if (g_cfg.core.ppu_llvm_ir_passes)\n\t\t\t\tsettings += ppu_settings::arm64_ir_passes;' in ppu,
        'objects built with/without the passes must not share a name')
require('const bool run_ir_passes = g_cfg.core.ppu_llvm_ir_passes;' in ppu, 'pass gate must read the option once')
require(ppu.count('#elif defined(RPCS3_IOS)\n\t\t\t\t\tif (run_ir_passes)\n') == 1 and
        ppu.count('#elif defined(RPCS3_IOS)\n\t\t\t\tif (run_ir_passes)\n') == 1,
        'both x86-64 pass sites must gate the ARM64 passes on the option')
require(ppu.count('#ifdef ARCH_X64 // TODO\n') == 2, 'upstream x86-64 pass gates must remain')
require(ppu.count('jit_phase::g_counters.add(jit_phase::ppu_opt, utils::get_tsc() - opt_started') == 2,
        'ARM64 passes must be measured at both sites')
require('ppu_llvm_ir_passes' not in read('rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'), 'the option is PPU-only')

# --- PPU phases at the production call sites.
require('#include "Utilities/JITPhaseProfile.h"' in ppu, 'PPUThread.cpp does not include the phase profile')
require('jit_phase::g_counters.add(jit_phase::ppu_translate, utils::get_tsc() - translate_started, mod_func.size);' in ppu,
        'translation is not measured')
require('jit_phase::g_counters.add(jit_phase::ppu_verify, utils::get_tsc() - verify_started, guest_code_size);' in ppu,
        'verification is not measured')
require('const jit_phase::scope phase_timer(jit_phase::ppu_finalize, utils::get_tsc);\n\t\t\t\tjit->fin();' in ppu,
        'finalization is not measured')
require('const jit_phase::scope phase_timer(jit_phase::ppu_symbols, utils::get_tsc);' in ppu, 'symbol lookups are not measured')
require('jit_phase::g_counters.note_headroom(rpcs3::ios::available_process_memory_headroom());' in ppu,
        'headroom after a module compile is not sampled')
require('Emu.Pause();\n\t\t\t\t\treturn;' in ppu, 'translation failure path must remain')

# --- SPU phases: build, passes and codegen inside the compile function.
require('#include "Utilities/JITPhaseProfile.h"' in spu, 'SPULLVMRecompiler.cpp does not include the phase profile')
require('jit_phase::g_counters.add(jit_phase::spu_build, passes_started - compile_started, m_size);' in spu,
        'SPU IR construction is not measured')
require('jit_phase::g_counters.add(jit_phase::spu_passes, codegen_started - passes_started, m_size);' in spu,
        'SPU passes are not measured')
require('jit_phase::g_counters.add(jit_phase::spu_codegen, utils::get_tsc() - codegen_started, m_size);' in spu,
        'SPU code generation is not measured')
require(spu.index('spu_build') < spu.index('spu_passes') < spu.index('spu_codegen') < spu.index('// Register function pointer'),
        'SPU phase order must follow the compile function')
require('fpm.addPass(EarlyCSEPass(true));' in spu, 'SPU pipeline must be unchanged')
require('deferred_compile_enabled = false;' in read('rpcs3/Emu/Cell/SPUDeferredCompilePolicy.h'),
        'the Build 436 deferred compile switch must stay off')

# --- JITPROF reporter.
require('#include "Utilities/JITPhaseProfile.h"' in performance, 'reporter does not include the phase profile')
require('const auto jit = jit_phase::g_counters.exchange();' in performance and
        'std::string jit_line = fmt::format("JITPROF session=%llu", profile_session);' in performance,
        'JITPROF line missing')
require('fmt::append(jit_line, " %s=%llu:%.3f:%.3f:%llu", jit_phase::names[phase], jit.events[phase],' in performance,
        'JITPROF fields must be name=events:total_ms:max_ms:bytes')
require('headroom_samples=%llu headroom_min_mib=%.3f' in performance, 'JITPROF headroom fields missing')
require(performance.index('JITPROF') > performance.index('RANGELOCKPROF') and
        performance.index('JITPROF') < performance.index('COREPROF_RESILIENCE'),
        'JITPROF must be reported in the same window as the other profiles')

# --- Direct relay admission in the Core client: optional table, no blocking gameplay path.
require(relay_abi == (ROOT / 'packages/neo_swap/ios/Classes/NeoSwapRelay.h').read_text(), 'relay ABI header copies differ')
require('enum { NEOSWAP_DIRECT_RELAY_ABI = 1 };' in relay_abi and 'enum { NEOSWAP_RELAY_CLIENT_STATS_EXT_ABI = 1 };' in relay_abi,
        'direct admission and extension ABIs missing')
require('enum { NEOSWAP_PREPARED_RELAY_ABI = 1 };' in relay_abi and 'enum { NEOSWAP_RELAY_CLIENT_STATS_ABI = 1 };' in relay_abi,
        'Build 441 ABIs must be untouched')
require('inline constinit std::atomic<const NeoSwapDirectRelayAPI*> direct_api{nullptr};' in client, 'direct table slot missing')
require('if (!admit || !ready || (result != NEOSWAP_RELAY_QUOTA && result != NEOSWAP_RELAY_INVALID))' in client,
        'only an empty stock or an oversize request may try direct admission')
require('result = admit->try_create(NEOSWAP_RPCS3, bytes, &token);' in client, 'direct creation call missing')
gameplay_block = client[client.index('if (gameplay) {'):client.index('} else {\n                    if (!api->enabled(NEOSWAP_RPCS3))')]
require('api->create(' not in gameplay_block and 'api->enabled(' not in gameplay_block,
        'the gameplay path must never call the blocking create or sample the host')
require('ext_counters.fallback_live_objects.fetch_sub(1, std::memory_order_relaxed);' in client,
        'live exclusion must end with the object')
require('inline constexpr std::uint64_t prepared_stock_maximum_bytes = 16ULL * 1024 * 1024;' in client, 'oversize threshold')
for name in ('_rpcs3_ios_set_neoswap_direct_relay_api', '_rpcs3_ios_get_neoswap_relay_client_stats_ext'):
    require(name in exports, f'missing link export {name}')
    require(f'extern "C" RPCS3_IOS_EXPORT int32_t {name[1:]}(' in core_api, f'missing production export {name}')
print('PASS: Build 444 Core delta (JIT phase profile executed; cache identity, opt-in ARM64 IR passes, '
      'JITPROF reporter and direct relay admission wired; deferred SPU compile still off)')
