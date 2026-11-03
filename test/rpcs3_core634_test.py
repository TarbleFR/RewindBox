#!/usr/bin/env python3
"""Host tests of RPCS3 Core 634 = Core 630 + build-utils/rpcs3/core634-from-630.patch.

From the Build 629 iPhone logs (3 November 2026, PID 3616): boots, memory and SPU hitches.

REWINDBOX_SPIRV_DISK_CACHE_634: the SPIR-V of each GLSL text, on disk, per title. glslang took
5.5 s of CPU and most of a 1.6 s warmup at each boot of Black Ops II multiplayer.
REWINDBOX_FAST_JIT_LOAD_634: cached PPU objects are checked and linked on several threads, one
MCJIT engine per thread, without a debug copy of each object; 3.2 to 4.4 s were spent on one thread.
REWINDBOX_JIT_OBJECT_RELEASE_634: MCJIT no longer keeps every object file: 130 to 300 MB.
REWINDBOX_CRYPTO_A64_634: the AES and SHA instructions of the CPU in rpcs3/Crypto.
REWINDBOX_SPU_PREFETCH_AC_634: Assassin's Creed joins the SPU object prefetch.

This test:
- reverts core634-from-630.patch on a copy of the touched files, authenticated by the Core 630
  SHA-256 pinned in core634-delta.json (increment_from_core630), then runs the whole Core 630
  suite (test/rpcs3_core630_test.py) on the reverted Core 630 tree;
- runs the real rpcs3/Crypto sources: FIPS vectors and random data, instructions against C
  (test/rpcs3_core634/crypto_a64_test.cpp). Apple ARM64 runs the real instructions; other hosts
  run the same rounds on test/rpcs3_core634/neon_shim/arm_neon.h;
- runs the real SPIR-V store on a real file, under TSan and ASan/UBSan: torn tail, damaged entry,
  other revision, size bound, six workers and a flush (test/rpcs3_core634/spirv_cache_test.cpp);
- runs the real object window, held bytes and link workers, extracted from JITLLVM.cpp and
  PPUThread.cpp around mock LLVM types (test/rpcs3_core634/jit_load_test.cpp);
- checks rule 1 (the one boot line) and the wiring in 12 locales.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core634'
DELTA = ROOT / 'build-utils/rpcs3/core634-from-630.patch'
RECORD = ROOT / 'build-utils/rpcs3/core634-delta.json'
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
LOCALES = ('en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko')
SETTINGS = (('fast_jit_load', 'Fast JIT Load', 'testFastJitLoad', 8),
            ('jit_object_release', 'JIT Object Release', 'testJitObjectRelease', 9),
            ('spirv_disk_cache', 'SPIR-V Disk Cache', 'testSpirvDiskCache', 10),
            ('hardware_crypto', 'Hardware Crypto', 'testHardwareCrypto', 11))

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core621_test as core621  # noqa: E402  (shared helpers: require, run, execute)

require = core621.require
APPLE_ARM64 = sys.platform == 'darwin' and platform.machine() == 'arm64'


def build(cxx: str, sources: list, output: Path, includes: list, flags: list) -> None:
    command = [cxx, '-std=gnu++20', *flags, *[f'-I{path}' for path in includes], *map(str, sources), '-o', str(output), '-pthread', '-lz']
    result, _ = core621.run(command, timeout=1200)
    require(result.returncode == 0, f'compile {output.name} failed:\n' + result.stdout[-4000:])


def sanitizer_sets(cxx: str, sanitize: bool) -> dict:
    sets = {'plain': []}
    if sanitize:
        sets['tsan'] = ['-fsanitize=thread'] + ([] if 'clang' in Path(cxx).name else ['-Wno-tsan'])
        sets['asan'] = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    return sets


def patch_files(text: str) -> list[str]:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def check_increment(source: Path, work: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core630']
    pinned = increment['files_before_sha256']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core634-from-630.patch differs from its record')
    files = patch_files(raw.decode('utf-8', 'surrogateescape'))
    require(files and increment['files'] == len(files), 'core634-from-630.patch files')
    copy = work / 'revert634'
    for name in files:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'init', '-q'], cwd=copy, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=copy,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core634-from-630.patch does not revert: ' + result.stdout[-2000:])
    for name in files:
        reverted = copy / name
        if name in increment['new_files']:
            require(not reverted.exists() or reverted.stat().st_size == 0, f'{name} survives the revert')
            continue
        require(pinned.get(name) == hashlib.sha256(reverted.read_bytes()).hexdigest(),
                f'{name} reverted does not match its pinned Core 630 SHA-256')
    return {'files': len(files), 'new_files': increment['new_files'], 'patch_sha256': increment['patch_sha256'],
            'authenticated_by': 'pinned_sha256'}


def core630_tree(source: Path, work: Path) -> Path:
    tree = work / 'core630'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 630 tree cannot be rebuilt: ' + result.stdout[-2000:])
    require(not (tree / 'rpcs3/ios/IOSSpirvCache.h').exists(), 'the Core 634 header survives in the Core 630 tree')
    return tree


def run_crypto(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    folder = work / 'crypto'
    folder.mkdir()
    files = [HERE / 'crypto_a64_test.cpp'] + [source / 'rpcs3/Crypto' / name for name in ('aes.cpp', 'aesni.cpp', 'sha1.cpp', 'sha256.cpp')]
    includes = [source / 'rpcs3', source]
    if APPLE_ARM64:
        common = ['-O2', '-g', '-DRPCS3_IOS=1', '-march=armv8.4-a']
    else:
        common = ['-O1', '-g', '-DRPCS3_TEST_CRYPTO_A64=1', '-maes', '-msse2']
        includes.insert(0, HERE / 'neon_shim')
    report = {'real_instructions': APPLE_ARM64}
    sets = sanitizer_sets(cxx, sanitize)
    sets.pop('tsan', None) # one thread
    for label, extra in sets.items():
        output = folder / label
        build(cxx, files, output, includes, common + extra)
        out = core621.execute([str(output)], f'crypto ({label})')
        result = json.loads(out.strip().splitlines()[-1])
        require(result['failures'] == 0 and result['crypto_compared'] >= 100, 'crypto: ' + repr(result))
        require(result['instructions'] == 3, 'crypto: the instruction paths did not run: ' + repr(result))
        report[label] = result
    return report


def run_spirv(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    folder = work / 'spirv'
    folder.mkdir()
    report = {}
    for label, extra in sanitizer_sets(cxx, sanitize).items():
        output = folder / label
        flags = ['-O1', '-g'] + extra + (['-DRPCS3_IOS=1'] if APPLE_ARM64 else [])
        build(cxx, [HERE / 'spirv_cache_test.cpp', source / 'rpcs3/Crypto/sha256.cpp'], output, [source / 'rpcs3', source], flags)
        out = core621.execute([str(output), str(folder)], f'SPIR-V store ({label})')
        report[label] = json.loads(out.strip().splitlines()[-1])
        require(report[label]['failures'] == 0, 'SPIR-V store: ' + repr(report[label]))
    return report


def extract(text: str, begin: str, end: str) -> str:
    start = text.index(begin)
    return text[start:text.index(end, start)]


def run_jit_load(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    folder = work / 'jit'
    folder.mkdir()
    read = lambda name: (source / name).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    jit, ppu = read('Utilities/JITLLVM.cpp'), read('rpcs3/Emu/Cell/PPUThread.cpp')
    (folder / 'jit_window.inc').write_text(extract(jit, 'struct object_file_identity\n', 'object_file_identity object_identity(') +
                                           extract(jit, 'struct validated_object_window\n', 'validated_object_window& validated_objects()'),
                                           'utf-8', 'surrogateescape')
    (folder / 'jit_held.inc').write_text(extract(jit, 'struct held_object_bytes\n', 'held_object_bytes& held_objects()'), 'utf-8', 'surrogateescape')
    (folder / 'ppu_link_jobs.inc').write_text(extract(ppu, 'template <typename Job>\nvoid ios_run_link_jobs(', '\n}\n}\n') + '\n}\n', 'utf-8', 'surrogateescape')
    report = {}
    for label, extra in sanitizer_sets(cxx, sanitize).items():
        output = folder / label
        build(cxx, [HERE / 'jit_load_test.cpp'], output, [source / 'rpcs3', folder], ['-O1', '-g'] + extra)
        out = core621.execute([str(output)], f'JIT load ({label})')
        report[label] = json.loads(out.strip().splitlines()[-1])
        require(report[label]['failures'] == 0, 'JIT load: ' + repr(report[label]))
    return report


def check_rule_one() -> dict:
    """Rule 1 of the task: no new counter, no new COREPROF tag, no new log line but one per boot."""
    added = [line[1:] for line in DELTA.read_text('utf-8', 'surrogateescape').splitlines()
             if line.startswith('+') and not line.startswith('+++')]
    code = [line for line in added if not line.lstrip().startswith('//') and not line.lstrip().startswith('#')]
    # The parallel link says what the serial one says, for the same modules.
    same = ('NeoStation PPU link begin: %s', 'LLVM: Failed to load module %s', 'LLVM: Loaded module #%u %s', 'ObjectCache: Successfully added %s')
    logs = [line for line in code if re.search(r'\.(notice|warning|error|success|fatal|trace)\(', line) and not any(text in line for text in same)]
    require(len(logs) == 1 and 'Resolved title policy 634:' in logs[0], 'log calls added by Core 634: ' + repr(logs))
    require(not any('COREPROF ' in line for line in code), 'a COREPROF format added by Core 634')
    counters = [line for line in code if 'fetch_add(' in line and 'objects_loaded.fetch_add' not in line]
    require(not counters, 'a new counter in Core 634: ' + repr(counters))
    members = [line for line in code if re.search(r'std::atomic<', line) and not re.search(r'inline std::atomic<(bool|std::size_t)> (enabled|fast_load|release_bytes|window_limit)\{', line)]
    require(not members, 'a new atomic in Core 634: ' + repr(members))
    return {'added_lines': len(added), 'log_calls': len(logs)}


def check_wiring(source: Path) -> dict:
    text = lambda name: (source / name).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    config, settings = text('rpcs3/Emu/system_config.h'), text('rpcs3/ios/RPCS3IOSSettings.cpp')
    policy, policy_h = text('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'), text('rpcs3/ios/RPCS3IOSExperimentalPolicy.h')
    menu = (CLASSES / 'Rpcs3SessionMenu.mm').read_text()
    plugin = (CLASSES / 'Rpcs3InternalBridgePlugin.mm').read_text()
    l10n = (CLASSES / 'RPCS3InGameLocalization.mm').read_text()
    system = text('rpcs3/Emu/System.cpp')
    table = l10n[l10n.index('Build634Translations() {'):l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build630Translations() {')]
    locales = re.findall(r'^      @"(\w+)": @\{$', table, re.M)
    require(sorted(locales) == sorted(LOCALES), 'locales of the test page rows: ' + repr(locales))
    previous = 'zcull_async_reads'
    for setting, name, label, bit in SETTINGS:
        require(f'cfg::_enum<ios_experimental_mode> {setting}{{ this, "{name}", ios_experimental_mode::automatic }};' in config, 'setting ' + setting)
        require(settings.count(f'GAME_SETTING("experimental.{setting}", "Experimental"') == 1 and
                f'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.{setting}, 0, 0, 0)' in settings, 'catalogue ' + setting)
        require(f'bool {setting} = false;' in policy_h, 'policy field ' + setting)
        require(f'resolved.{setting} = resolve_mode(g_cfg.ios_experimental.{setting}, true);' in policy, 'Automatic is every title: ' + setting)
        require(f'ios_add_lever(ios_levers.{previous}, ios_lever_settings.{previous});\n'
                f'\t\t\t\t\tios_add_lever(ios_levers.{setting}, ios_lever_settings.{setting});\n' in system, 'digit of the state field: ' + setting)
        previous = setting
        require(f'@{{@"key": @"experimental.{setting}", @"title": @"{label}", @"field": @"levers627", @"bit": @{bit},\n' in menu, 'test page row ' + setting)
        require(f'@"experimental.{setting}": @[@"Enabled", @"Disabled"]' in plugin, 'test page whitelist ' + setting)
        values = dict(zip(locales, re.findall(rf'@"{label}": @"([^"]+)"', table)))
        require(len(values) == len(LOCALES), 'test page row in every locale: ' + setting)
        same = [locale for locale in values if locale != 'en' and values[locale] == values['en']]
        require(not same, 'locales that keep English text: ' + repr(same))
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build634[locale][key]') < lookup.index('build630[locale][key]'), 'the 634 table is read')
    require(policy.count('Resolved title policy 634:') == 1, 'the one boot line')
    require('rpcs3::ios::jit_load::fast_load.store(resolved.fast_jit_load' in policy and 'rpcs3::ios::jit_load::release_bytes.store(resolved.jit_object_release' in policy and
            'rpcs3::ios::crypto_a64::enabled.store(resolved.hardware_crypto' in policy, 'the flags reach their code')

    levers = text('rpcs3/ios/IOSTitleLevers.h')
    require('return is_black_ops_ii_title(title_id) || is_assassins_creed_title(title_id);\n}\n\n// REWINDBOX_ZCULL_ON_DEMAND_619' in levers, 'the prefetch titles')

    jit = text('Utilities/JITLLVM.cpp')
    require(jit.count('m_engine->addObjectFile(std::move(*object_file));') == 1 and jit.count('held_objects().hold(this, std::move(cache));') == 1, 'the PPU bytes stay with the compiler')
    require('held_objects().hold(m_compiler, std::move(m_preloaded));' in jit and 'llvm::MemoryBuffer::getMemBuffer(m_preloaded->getMemBufferRef(), false)' in jit, 'the SPU bytes stay with the compiler')
    fin = extract(jit, 'void jit_compiler::fin()', 'bool jit_compiler::try_fin(')
    try_fin = extract(jit, 'bool jit_compiler::try_fin(', 'u64 jit_compiler::get(')
    require('held_objects().release(this);' in fin and fin.index('m_engine->finalizeObject();') < fin.index('held_objects().release(this);') and
            'if (success) held_objects().release(this);' in try_fin, 'released after finalizeObject, on success')
    require('held_objects().release(this);' in extract(jit, 'jit_compiler::~jit_compiler() noexcept', 'void jit_compiler::add('), 'released with the compiler')
    announcer = extract(jit, 'void notifyObjectLoaded(u64,', 'info.getObjectForDebug(obj);')
    require('jit_load::fast_load' in announcer and '!jit_profile::spu_writer().enabled()' in announcer, 'the debug copy is skipped only when nothing reads it')

    ppu = text('rpcs3/Emu/Cell/PPUThread.cpp')
    link = extract(ppu, 'if (rpcs3::ios::jit_load::fast_load.load(std::memory_order_relaxed) && jits.size() > 1)\n\t\t{\n\t\t\tatomic_t<u32> ios_failed', 'for (const auto& [obj_name, is_compiled] : link_workload)')
    require('const usz first = engine * c_modules_per_jit;' in link and 'jits[engine]->add(cache_path + obj_name)' in link, 'each engine gets the objects of its index, in order')
    check = extract(ppu, 'atomic_t<u32> ios_missing = 0;', 'if (g_progr_ftotal_bits && file_size)')
    require('record_ppu_cache_lookup' in check and 'note_cache_lookup' in check and 'return ios_missing != 0;' in check, 'the deferred checks answer the same question')
    arena = extract(text('Utilities/JITIOS.cpp'), 'void* allocate(bool executable, usz size, usz alignment) noexcept', 'void release_allocation(')
    require(arena.index('update_live_bytes(executable, allocation.size);') < arena.index('lock.unlock();') < arena.index('std::memset(storage, 0, allocation.size);'), 'the zero fill leaves the arena lock')

    cache = text('rpcs3/Emu/RSX/rsx_cache.h')
    require(cache.count('spirv_cache::instance().open(') == 1 and 'get_experimental_policy().spirv_disk_cache' in cache and cache.count('spirv_cache::instance().flush();') == 2 and
            cache.count('spirv_cache::instance().close();') == 1, 'the SPIR-V store lifecycle')
    pipeline = extract(text('rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp'), 'VkShaderModule shader::compile()', '#else')
    require(pipeline.index('disk_cache.find(disk_key, binary)') < pipeline.index('spirv::compile_glsl_to_spv(binary, m_source, type, ::glsl::glsl_rules_vulkan)') < pipeline.index('disk_cache.add(disk_key, binary);'),
            'a hit skips glslang, a compilation is kept')
    spirv = text('rpcs3/Emu/RSX/Program/SPIRVCommon.cpp')
    require('EShTargetVulkan_1_2' in spirv and 'EShTargetSpv_1_5' in spirv and 'options.disableOptimizer = true;' in spirv and 'options.optimizeSize = true;' in spirv,
            'the compiler environment the cache key names: a change here must change environment_revision')
    for name, marker in (('rpcs3/Crypto/aes.cpp', 'crypto_a64::ecb('), ('rpcs3/Crypto/aes.cpp', 'crypto_a64::ctr_blocks('), ('rpcs3/Crypto/sha1.cpp', 'crypto_a64::sha1_blocks('),
                         ('rpcs3/Crypto/sha256.cpp', 'crypto_a64::sha256_blocks(')):
        require(marker in text(name), name + ' uses the instructions')
    return {'settings': [item[0] for item in SETTINGS], 'locales': sorted(LOCALES)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    report: dict = {'cxx': args.cxx}
    sanitize = not args.no_sanitizers
    with tempfile.TemporaryDirectory(prefix='core634-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source, work)
        print('rule 1: observation added by the increment')
        report['rule_one'] = check_rule_one()
        print('wiring')
        report['wiring'] = check_wiring(source)
        print('crypto')
        report['crypto'] = run_crypto(source, args.cxx, work, sanitize)
        print('SPIR-V store')
        report['spirv'] = run_spirv(source, args.cxx, work, sanitize)
        print('JIT load')
        report['jit'] = run_jit_load(source, args.cxx, work, sanitize)
        print('core 630 suite on the reverted tree')
        tree = core630_tree(source, work)
        command = [sys.executable, str(ROOT / 'test/rpcs3_core630_test.py'), '--source', str(tree), '--cxx', args.cxx,
                   '--report', str(work / 'core630.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 630' in result.stdout, 'the Core 630 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core630'] = json.loads((work / 'core630.json').read_text())
    print('PASS: Core 634 increment reverts to Core 630; the Core 630 suite on that tree; rule 1; wiring in 12 locales; '
          'crypto against C, the SPIR-V store, the JIT load code')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
