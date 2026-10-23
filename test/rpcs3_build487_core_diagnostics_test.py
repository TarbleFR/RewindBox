#!/usr/bin/env python3
"""Build 487 Core diagnostics and levers (NEOSTATION_BUILD487_DIAGNOSTICS_V1): host evidence.

Usage: python3 test/rpcs3_build487_core_diagnostics_test.py <materialized Core tree>

1. Executed helpers (C++20, CXX or clang++/g++, with ASan/UBSan when the
   toolchain provides them): the profiler maths and metrics layout
   (RPCS3IOSProfilerHelpers.h with the real RPCS3IOS.h), the four boot line
   formatters and the restart hand-off (RPCS3IOSBootDiagnostics.h with the real
   Utilities/JITPhaseProfile.h), the spin thresholds and directory retention
   (RPCS3IOSLeverHelpers.h), and the boot-time retention sequence against the
   unchanged SPU object-cache policy (SPUObjectCachePolicy.h).
2. Unchanged code generation: the translator/backend sources are byte-identical
   to the Build 483 postimages, and the lines that compose the SPU object-cache
   key and the PPU object name are identical to Build 483.
3. Wiring: each audit item (D1-D10, L2, L3, L5, L9) is present at its site with
   the exact line prefixes the host admits, the four settings keep the Build 483
   behaviour by default, the new translation unit is built and syntax-gated,
   the deferred SPU compilation of Build 435 stays off.

Executed on the host only; nothing here is iPhone evidence.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2:
    raise SystemExit('usage: rpcs3_build487_core_diagnostics_test.py <materialized Core tree>')
core = Path(sys.argv[1]).resolve()
MARK = 'NEOSTATION_BUILD487_DIAGNOSTICS_V1'


def read(relative: str) -> str:
    return (core / relative).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def lf_sha256(relative: str) -> str:
    return hashlib.sha256((core / relative).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


# --- 1. executed helpers --------------------------------------------------------
compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
require(compiler is not None, 'a C++ compiler is required')
NATIVE = [
    ('test/native/rpcs3_build487_profiler_helpers_test.cpp', 'profiler helpers and metrics layout'),
    ('test/native/rpcs3_build487_boot_diagnostics_test.cpp', 'boot lines and restart hand-off'),
    ('test/native/rpcs3_build487_lever_helpers_test.cpp', 'spin thresholds and directory retention'),
    ('test/native/rpcs3_build487_retention_sequence_test.cpp', 'retention sequence against the SPU object-cache policy'),
]
includes = ['-I' + str(core), '-I' + str(core / 'rpcs3'), '-I' + str(core / 'rpcs3/ios')]
# The Core job passes Xcode's clang++, which needs the macOS SDK explicitly (as the
# other Core tests do with HOST_MACOS_SDK); /usr/bin/clang++ and Linux need nothing.
SYSROOT = []
if sdk := os.environ.get('HOST_MACOS_SDK'):
    SYSROOT = ['-isysroot', sdk]
elif sys.platform == 'darwin' and shutil.which('xcrun'):
    SYSROOT = ['-isysroot', subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()]


def sanitizer_flags():
    with tempfile.TemporaryDirectory(prefix='rpcs3-487-probe-') as tmp:
        probe = Path(tmp) / 'p.cpp'
        probe.write_text('int main(){return 0;}\n')
        flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        result = subprocess.run([compiler, '-std=c++20', *SYSROOT, *flags, str(probe), '-o', str(Path(tmp) / 'p')],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return flags if result.returncode == 0 else []


SANITIZE = sanitizer_flags()
with tempfile.TemporaryDirectory(prefix='rpcs3-487-native-') as tmp:
    for source, label in NATIVE:
        binary = Path(tmp) / Path(source).stem
        subprocess.run([compiler, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', *SYSROOT, *SANITIZE, *includes,
                        str(ROOT / source), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary)], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else '')
        print(f'PASS executed: {label}' + (' (ASan/UBSan)' if SANITIZE else ' (no sanitizer runtime on this host)'))

# --- 2. unchanged code generation ----------------------------------------------
BUILD483_CODEGEN = {
    'Utilities/JIT.h': '77f2e0aa81b74e2307a5e8dcc7a6f275d67ed9b38c6013d9c2b7fcde1e7a7e31',
    'Utilities/JITLLVM.cpp': '4537588e1da2a4ee51f3218ae30ecd9342ba2c3e0d062cbfa1cc1dec458d1dae',
    'rpcs3/Emu/CPU/Backends/AArch64/SPUInterpreterGateway.h': '225a20768e91a4c3fa1c361327c58cd3aad01bcadc94f98a5d10c51ae0e38fd3',
    'rpcs3/Emu/CPU/Backends/AArch64/SPUReservationHash.h': '682f3bed5668268dc8173b1c583706f26bbe5d2adc8225395ca32629a04a18f3',
    'rpcs3/Emu/CPU/CPUTranslator.h': '6a75ba938064bb21f1a6c87f9b737192588c8dd64360c58ce8df37bbb2bc51ce',
    'rpcs3/Emu/Cell/PPUAnalyser.cpp': 'd1e305c525914ab4c7b15b898c60614c33a8738d2126fc0e25eea18279391d31',
    'rpcs3/Emu/Cell/PPUTranslator.cpp': 'ca045fcf45d11eba12fb4f0b309bb12dfc7b6e48c29201a26f6188258bd6b730',
    'rpcs3/Emu/Cell/PPUTranslator.h': '78c7b817d792de7c3b08abf40502724245736385bd414666a0b2d958e2fdd3c3',
    'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp': '0fbd4c477a3e83f8254c0ae4efc77cf17348dba3f2159c4d6686aff9e4317b17',
    'rpcs3/Emu/Cell/SPURecompiler.h': '0cc7ed8ea11b3b6f8bd15b933c6d9291bf21cbe7cf10a610f479e24d6f891f07',
}
for relative, digest in BUILD483_CODEGEN.items():
    if relative == 'Utilities/JIT.h':
        text = read(relative)
        api = '\tstatic void release_cached_object_buffers();\n'
        prototype = '\tbool try_add_minimal_object(jit_cached_object object, const std::string& entry,\n\t\tconst std::unordered_map<std::string, u64>& bindings, std::string& error);\n\n'
        if api in text or prototype in text:
            require(text.count(api) == text.count(prototype) == 1, 'Unexpected JIT audit API declaration')
            text = text.replace(api, '').replace(prototype, '')
        require(hashlib.sha256(text.encode()).hexdigest() == digest,
                'JIT.h changed beyond the exact memory-audit API additions')
    elif relative == 'Utilities/JITLLVM.cpp' and (ROOT / 'test/fixtures/rpcs3_memory_audit/JITLLVM.diff').is_file():
        # Reverse the exact reviewed cache/ownership/prototype delta, then keep
        # the original full-file code-generation hash. An extra changed byte
        # either makes reverse application fail or breaks the historical hash.
        with tempfile.TemporaryDirectory(prefix='jitllvm-reference-') as temporary:
            target = Path(temporary) / relative
            target.parent.mkdir(parents=True)
            target.write_text(read(relative))
            delta = ROOT / 'test/fixtures/rpcs3_memory_audit/JITLLVM.diff'
            subprocess.run(['git', 'apply', '--reverse', '--check', str(delta)], cwd=temporary, check=True)
            subprocess.run(['git', 'apply', '--reverse', str(delta)], cwd=temporary, check=True)
            require(hashlib.sha256(target.read_bytes()).hexdigest() == digest,
                    'JITLLVM.cpp changed beyond the reviewed audit delta')
    elif relative == 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp':
        # Build 499 intentionally fixes one SHUFB mask and compile diagnostics.
        # Undo exactly those edits, then retain the full historical SHA check.
        # The new Core preflight executes both revisions against scalar results.
        from rpcs3_build499_spu_audit_test import reference_translator
        require(hashlib.sha256(reference_translator(read(relative)).encode()).hexdigest() == digest,
                'SPULLVMRecompiler.cpp changed beyond the independently tested Build 499 delta')
    else:
        require(lf_sha256(relative) == digest, f'{relative} differs from Build 483: code generation must not change')
KEY_LINES = re.compile(r'fold\(|fold_string\(|settings \+=|arm64_ir_passes|obj_name')
for relative, digest in (('rpcs3/Emu/Cell/SPUCommonRecompiler.cpp', '98523ee8a93967b143c652cc634c5ab428b0549014c83e893104dc33b7818f2b'),
                         ('rpcs3/Emu/Cell/PPUThread.cpp', '1cba19d9c6ff59aa07543c410b0b4deda194d01c64396c4e44bdddcade6f184c')):
    lines = ''.join(line.lstrip() + '\n' for line in read(relative).splitlines() if KEY_LINES.search(line))
    require(hashlib.sha256(lines.encode()).hexdigest() == digest,
            f'{relative}: object-cache key/name lines differ from Build 483')
print('PASS: historical codegen hashes retained after exact Build 499 delta reversal; SPU key / PPU object name lines equal Build 483')

# --- 3. wiring -------------------------------------------------------------------
files = {
    'rpcs3/ios/RPCS3IOS.h': ['RPCS3_IOS_PERFORMANCE_GUEST_FRAMES_VALID = 1u << 4', 'RPCS3_IOS_PERFORMANCE_BOOT_PROGRESS_VALID = 1u << 7',
                             'uint64_t guest_frames_presented;', 'uint32_t boot_progress_total;'],
    'rpcs3/ios/RPCS3IOSPerformance.cpp': ['other_ms=', 'window_ms=', 'top=%s', 'rsx_fifo_busy=', 'rsx_thread_cpu=',
                                          'compile_threads=', '_max_hold_us=', 'neostation_freeze_dump(',
                                          'RPCS3_IOS_PERFORMANCE_GUEST_FRAMES_VALID'],
    'rpcs3/ios/RPCS3IOS.cpp': ['RPCS3_IOS_PERFORMANCE_STATE_VALID', 'RPCS3_IOS_PERFORMANCE_BOOT_PROGRESS_VALID',
                               'std::try_to_lock', 'restart_reason::savestate_create', 'apply_spu_spin_timing_policy()'],
    'rpcs3/ios/RPCS3IOSFreezeDump.cpp': ['"FREEZE_DUMP begin ', '"FREEZE_DUMP end ', '"FREEZE_DUMP ppu ', '"FREEZE_DUMP spu '],
    'rpcs3/ios/RPCS3IOSFreezeDump.h': ['void neostation_freeze_dump(const char* reason, double seconds_without_frames, double busiest_group_cores);'],
    'rpcs3/Emu/Cell/lv2/sys_mutex.cpp': ['MUTEX_DESTROY_BUSY mutex_id=0x%x owner_id=0x%x owner_name=%s caller_id=0x%x caller_name=%s'],
    'rpcs3/ios/RPCS3IOSBootDiagnostics.h': ['"CONFIG_LAYERS', '"NEOSTATION_RESTART reason=', '"JITPROF_BOOT', '"SAVESTATE_BOOT'],
    'rpcs3/Emu/System.cpp': ['format_config_layers_line(', 'consume_restart_line(', 'Found custom config. Ignoring database config',
                             'Applying database config'],
    'rpcs3/Emu/Cell/PPUThread.cpp': ['format_jitprof_boot_line(', 'format_savestate_analysis_line(', 'format_savestate_link_line('],
    'rpcs3/Emu/RSX/Overlays/HomeMenu/overlay_home_menu_savestate.cpp': ['restart_reason::savestate'],
    'rpcs3/Emu/RSX/Overlays/HomeMenu/overlay_home_menu_main_menu.cpp': ['restart_reason::home_menu'],
    'rpcs3/Emu/Cell/lv2/sys_game.cpp': ['restart_reason::sys_game'],
    'Utilities/JITPhaseProfile.h': ['totals()', 'window_delta('],
    'rpcs3/Emu/system_config.h': ['cfg::_enum<ios_spu_spin_timing> spu_spin_timing{ this, "SPU Spin Timing", ios_spu_spin_timing::reference };',
                                  'cfg::uint<1, 4> spu_object_cache_retained_keys{ this, "SPU Object Cache Retained Keys", 2 };',
                                  'cfg::_enum<ios_spu_warmup_scope> spu_warmup_scope{ this, "SPU Warmup Scope", ios_spu_warmup_scope::god_of_war_iii };',
                                  'fifo_idle_mode{ this, "RSX FIFO Idle Wait", ios_fifo_idle_mode::yield };'],
    'rpcs3/Emu/system_config_types.h': ['bounded_sleep', 'enum class ios_spu_spin_timing', 'enum class ios_spu_warmup_scope'],
    'rpcs3/Emu/system_config_types.cpp': ['case ios_fifo_idle_mode::bounded_sleep: return "Bounded sleep";',
                                          'case ios_spu_spin_timing::calibrated: return "Calibrated";',
                                          'case ios_spu_warmup_scope::all_titles_with_metadata: return "All titles with metadata";'],
    'rpcs3/ios/RPCS3IOSSettings.cpp': ['"experimental.spu_spin_timing"', '"experimental.spu_object_cache_retained_keys"',
                                       '"experimental.spu_warmup_scope"'],
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp': ['spin_timing=', 'fifo_idle=', 'spuobj_keys=', 'warmup_scope=', 'getllar_ticks='],
    'rpcs3/Emu/Cell/SPUThread.cpp': ['getllar_forced_sleep_ticks', 'getllar_spin_window_ticks', 'getllar_refail_ticks'],
    'rpcs3/Emu/RSX/RSXFIFO.cpp': ['fifo_idle_bounded_sleep_microseconds', 'm_fifo_idle_bounded_sleep'],
    'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp': ['plan_directory_retention(', 'levers::build_marker_name', 'spu_warmup_all_titles'],
    'rpcs3/ios/RPCS3IOSLeverHelpers.h': ['getllar_forced_sleep_ticks = 400\'000;', 'build_marker_name = "neostation-build.id"'],
    'rpcs3/CMakeLists.txt': ['ios/RPCS3IOSFreezeDump.cpp'],
}
for relative, needles in files.items():
    text = read(relative)
    require(MARK in text or relative in ('rpcs3/CMakeLists.txt',) or relative.endswith('system_config_types.cpp'),
            f'{relative} lacks {MARK}')
    for needle in needles:
        require(needle in text, f'{relative}: missing {needle!r}')
gate = (ROOT / 'build-utils/rpcs3_core_syntax_gate.py').read_text()
for unit in ('RPCS3IOSFreezeDump.cpp', 'System.cpp', 'sys_game.cpp', 'sys_mutex.cpp', 'RSXThread.cpp',
             'overlay_home_menu_savestate.cpp', 'overlay_home_menu_main_menu.cpp', 'RPCS3IOSExperimentalPolicy.cpp',
             'RPCS3IOSSettings.cpp', 'system_config_types.cpp'):
    require(f"'{unit}'" in gate, f'syntax gate does not compile {unit} before the Core build')
require('inline constexpr bool deferred_compile_enabled = false;' in read('rpcs3/Emu/Cell/SPUDeferredCompilePolicy.h'),
        'deferred SPU compilation (Build 435) must stay off')
print('PASS: Build 487 Core diagnostics and levers (helpers executed, historical codegen controls retained, audited API/admission additions isolated, wiring and defaults)')
