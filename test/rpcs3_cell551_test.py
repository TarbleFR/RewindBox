#!/usr/bin/env python3
"""Execute the production CELL551 headers and check the exact 547 -> 551 Core delta.

Usage: rpcs3_cell551_test.py <551 Core work tree> [--yaml-cpp DIR] [--report out.json]

1. REWINDBOX_LEGACY_CONFIG_INHERITANCE_V1: RPCS3IOSConfigInheritance.h runs with
   RPCS3's yaml-cpp fork (the tree's 3rdparty submodule, or --yaml-cpp) and
   yaml_load copied verbatim from rpcs3/util/yaml.cpp. The God of War III
   database document is rebuilt from the shipped Dart profile and offline
   GameDB exactly as Rpcs3ConfigAdapter.mergeScalarOverrides writes it. The
   full snapshot is the configuration CONFIG_LAYERS reported for every God of
   War III boot from build 412 to 547 (legacy_custom=1 database=0).
2. REWINDBOX_SPU_WAIT_PROFILE_V1 / REWINDBOX_RSX_SYNC_PROFILE_V1: the production
   headers under 120 concurrent threads (ASan+UBSan, then TSan).
3. Static: the 547 tree is rebuilt by reverse-applying the reviewed fixture;
   every added Core line is checked against the contract below, and the SPU
   alias keeps the 546 identity for this exact SPUThread.cpp snapshot.
Host checks only: no iPhone, MoltenVK or game was run.
"""
import argparse, hashlib, json, os, re, shlex, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell551.diff'
sha = lambda b: hashlib.sha256(b).hexdigest()
MODIFIED = ['rpcs3/Emu/CPU/JITCacheCompatibility.cmake', 'rpcs3/Emu/Cell/SPUThread.cpp',
            'rpcs3/Emu/RSX/RSXFIFO.cpp', 'rpcs3/Emu/RSX/RSXThread.cpp',
            'rpcs3/Emu/RSX/VK/VKCommandStream.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.cpp',
            'rpcs3/Emu/RSX/VK/VKGSRenderTypes.hpp', 'rpcs3/Emu/RSX/VK/VKPresent.cpp',
            'rpcs3/Emu/RSX/VK/VKTextureCache.cpp', 'rpcs3/Emu/RSX/VK/vkutils/commands.cpp',
            'rpcs3/Emu/RSX/VK/vkutils/device.cpp', 'rpcs3/Emu/RSX/VK/vkutils/device.h',
            'rpcs3/Emu/RSX/VK/vkutils/instance.cpp', 'rpcs3/Emu/RSX/VK/vkutils/sync.cpp',
            'rpcs3/Emu/System.cpp', 'rpcs3/Emu/system_config.h', 'rpcs3/ios/RPCS3IOSBootDiagnostics.h',
            'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h',
            'rpcs3/ios/RPCS3IOSPerformance.cpp', 'rpcs3/ios/RPCS3IOSPlatform.mm']
NEW = ['rpcs3/ios/IOSRsxSyncProfile.h', 'rpcs3/ios/IOSSpuWaitProfile.h', 'rpcs3/ios/RPCS3IOSConfigInheritance.h']
DART = ROOT / 'lib/services/rpcs3_game_profile_service.dart'
GAMEDB = ROOT / 'assets/data/rpcs3_ios_profiles.json'


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[a:b]


# --- Rpcs3ConfigAdapter (lib/services/rpcs3_config_adapter.dart), line for line.
def sanitise_for_ios(source):
    out = []
    for line in source.split('\n'):
        sep = line.find(':')
        if sep < 0:
            out.append(line)
            continue
        key = line[:sep].strip().replace('- ', '', 1)
        value = line[sep + 1:].strip()
        if key == 'Renderer' and value == 'OpenGL':
            continue
        if key == 'Frame limit' and value in ('Off', 'Infinite'):
            continue
        out.append(line)
    return '\n'.join(out).strip() + '\n'


def subtree_end(lines, start, parent_indent):
    for i in range(start, len(lines)):
        if not lines[i].strip():
            continue
        if len(lines[i]) - len(lines[i].lstrip()) <= parent_indent:
            return i
    return len(lines)


def set_scalar(source, path, value):
    trimmed = source.rstrip()
    lines = [] if not trimmed else trimmed.split('\n')
    start, end = 0, len(lines)
    for depth in range(len(path)):
        indent = depth * 2
        prefix = ' ' * indent + path[depth] + ':'
        found = -1
        for i in range(start, end):
            if lines[i].startswith(prefix):
                rest = lines[i][len(prefix):]
                if rest and not rest.startswith(' '):
                    continue
                found = i
                break
        leaf = depth == len(path) - 1
        if found >= 0:
            if leaf:
                lines[found] = f'{prefix} {value}'
                return '\n'.join(lines) + '\n'
            start = found + 1
            end = subtree_end(lines, start, indent)
            continue
        inserted = [(' ' * (r * 2) + path[r] + ':' + (f' {value}' if r == len(path) - 1 else ''))
                    for r in range(depth, len(path))]
        lines[end:end] = inserted
        return '\n'.join(lines) + '\n'
    return '\n'.join(lines) + '\n'


def gow3_database():
    dart = DART.read_text()
    paths = {k: re.findall(r"'([^']*)'", body) for k, body in
             re.findall(r"'([a-z0-9_.]+)' => const <String>\[(.*?)\]", dart, re.S)}
    body = braced(dart, 'static const Map<String, String> _godOfWarIII =')
    overrides = re.findall(r"^\s*'([a-z0-9_.]+)': '([^']*)',", body, re.M)
    assert overrides and all(k in paths for k, _ in overrides), overrides
    config = sanitise_for_ios(json.loads(GAMEDB.read_text())['games']['BCES00510']['config'])
    for key, value in overrides:
        config = set_scalar(config, paths[key], value)
    return config, dict(overrides)


# RPCS3 defaults (rpcs3/Emu/system_config.h) as cfg::node::to_string writes
# them, with the values CONFIG_LAYERS reported for God of War III.
GLOBAL = '''Core:
  PPU Decoder: Recompiler (LLVM)
  PPU Threads: 2
  LLVM Precompilation: true
  SPU Decoder: Recompiler (LLVM)
  Preferred SPU Threads: 0
  Max SPURS Threads: 6
  SPU Block Size: Safe
  Accurate SPU Reservations: true
  PPU Profiler: false
  SPU XFloat Accuracy: Approximate
  Libraries Control:
    []
Video:
  Renderer: Vulkan
  Frame limit: Auto
  Shader Mode: Legacy Recompiler (single-threaded)
  Shader Precision: High
  Write Color Buffers: false
  Write Depth Buffer: false
  Multithreaded RSX: false
  Resolution Scale: 100
  Vulkan:
    Adapter: Apple A18 Pro GPU
    Asynchronous Texture Streaming: false
Audio:
  Renderer: Cubeb
iOS Experimental:
  FPS Optimization Batch: Automatic
  RSX FIFO Read Cache: 1 KiB
  GETLLAR Mobile Backoff: Automatic
  God of War III MLAA Bypass: Automatic
  MoltenVK Asynchronous Submits: Automatic
  SPU Spin Timing: Reference
'''


def cxx_string(name, text):
    return f'static const std::string {name} = R"rbx({text})rbx";\n'


def leaves(text):
    """Leaf count of the adapter's YAML subset (maps of scalars or lists)."""
    lines = [l for l in text.split('\n') if l.strip()]
    count = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith('- '):
            continue
        indent = len(line) - len(line.lstrip())
        value = line.split(':', 1)[1].strip() if ':' in line else ''
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        deeper = nxt and len(nxt) - len(nxt.lstrip()) > indent
        if value or (deeper and nxt.lstrip().startswith('- ')):
            count += 1
    return count


def baseline(source: Path, work: Path) -> Path:
    tree = work / 'before'
    for path in MODIFIED + NEW:
        dest = tree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if (source / path).exists():
            dest.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=tree, check=True)
    return tree


def hunks(path):
    text = FIXTURE.read_text()
    block = text[text.index(f'diff --git a/{path} b/{path}'):]
    nxt = block.find('\ndiff --git', 1)
    block = block if nxt < 0 else block[:nxt]
    added = [l[1:] for l in block.splitlines() if l.startswith('+') and not l.startswith('+++')]
    removed = [l[1:] for l in block.splitlines() if l.startswith('-') and not l.startswith('---')]
    return added, removed


def guarded(text, needle):
    """True when `needle` sits inside an #ifdef RPCS3_IOS (or __APPLE__) block, not its #else."""
    at = text.index(needle)
    depth, ios = 0, []
    for m in re.finditer(r'^\s*#\s*(ifdef|ifndef|if|else|elif|endif)\b(.*)$', text[:at], re.M):
        kind, rest = m.group(1), m.group(2).strip()
        if kind in ('ifdef', 'ifndef', 'if'):
            ios.append(kind == 'ifdef' and rest in ('RPCS3_IOS', '__APPLE__'))
        elif kind in ('else', 'elif') and ios:
            ios[-1] = False
        elif kind == 'endif' and ios:
            ios.pop()
    return any(ios)


def static_checks(source: Path, before: Path) -> dict:
    added_all = [l[1:] for l in FIXTURE.read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]
    assert not [l for l in added_all if re.search(r'\b(try|catch|throw)\b', l)]
    for line in added_all:
        assert not re.search(r'\bbusy_wait\(|thread_ctrl::wait|sleep_for|this_thread::yield', line), line
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    if record := manifest.get('cell551'):
        for path, digest in record['before_sha256'].items():
            assert sha((before / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
        for path, digest in record['after_sha256'].items():
            assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    # Codegen: SPUThread.cpp is the only changed file of either digest list.
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    listed = set()
    for block in re.findall(r'foreach\(NEOSTATION_(?:PPU|SPU)_CODEGEN_SOURCE IN ITEMS(.*?)\)', cmake, re.S):
        listed |= {('rpcs3/Emu/' + p).replace('rpcs3/Emu/../../', '').replace('rpcs3/Emu/../', 'rpcs3/') for p in block.split()}
    assert listed & set(MODIFIED + NEW) == {'rpcs3/Emu/Cell/SPUThread.cpp'}, listed & set(MODIFIED + NEW)
    alias = r'source STREQUAL "Cell/SPUThread\.cpp" AND\s+actual STREQUAL "([0-9a-f]{64})"\)\s+set\(\$\{output\} "([0-9a-f]{64})"'
    now = re.search(alias, (source / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text())
    then = re.search(alias, (before / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text())
    assert now.group(1) == sha((source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_bytes())
    assert then.group(1) == sha((before / 'rpcs3/Emu/Cell/SPUThread.cpp').read_bytes())
    assert now.group(2) == then.group(2), 'SPUThread.cpp must keep the 546 identity'
    sys.path.insert(0, str(ROOT / 'test'))
    import rpcs3_cell538_test
    identities = rpcs3_cell538_test.cache_identities(source)
    assert identities == {'PPU': 'a987639e9f838d1c', 'SPU': 'd070cb361bdef607'}, identities
    # Every added line of these files is iOS-only.
    for path in MODIFIED:
        text = (source / path).read_text()
        added, removed = hunks(path)
        if path.endswith('.cmake') or path in ('rpcs3/ios/RPCS3IOSBootDiagnostics.h', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h',
                                               'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSPerformance.cpp',
                                               'rpcs3/Emu/RSX/VK/vkutils/device.h', 'rpcs3/ios/RPCS3IOSPlatform.mm'):
            continue
        # System.cpp reads each full config once so the same text is applied
        # and kept for the comparison; identical behaviour on every platform.
        shared = {'const std::string cfg_text = cfg_file.to_string();', 'if (g_cfg.from_string(cfg_text))'}
        for line in added:
            s = line.strip()
            if not s or s.startswith('#') or s.startswith('//') or s in ('{', '}', 'else'):
                continue
            if path == 'rpcs3/Emu/System.cpp' and s in shared:
                continue
            assert guarded(text, line), (path, line)
        if path == 'rpcs3/Emu/System.cpp':
            assert removed == ['					if (g_cfg.from_string(cfg_file.to_string()))',
                               '						if (g_cfg.from_string(cfg_file.to_string()))',
                               '			// A legacy full custom config remains authoritative and suppresses GameDB.'], removed
        elif path != 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake':
            assert not removed, (path, removed)
    system = (source / 'rpcs3/Emu/System.cpp').read_text()
    # Global snapshot before any title file; upstream non-iOS behaviour kept.
    assert system.index('const std::string ios_global_config = g_cfg.to_string();') < \
        system.index('if (m_config_mode == cfg_mode::database_config || m_config_mode == cfg_mode::custom)')
    assert system.count('ios_full_config = cfg_text;') == 2
    assert 'inherit_database(*m_db_config, ios_full_config, ios_global_config)' in system
    assert 'sys_log.notice("Found custom config. Ignoring database config");\n\t\t\t\t\t\t\t\tm_add_database_config = false;' in system
    assert not guarded(system, 'sys_log.notice("Found custom config. Ignoring database config")')
    vk = (source / 'rpcs3/Emu/RSX/VK/vkutils/instance.cpp').read_text()
    assert '"MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS", VK_LAYER_SETTING_TYPE_BOOL32_EXT, 1, &setting_false' in vk
    device = (source / 'rpcs3/Emu/RSX/VK/vkutils/device.cpp').read_text()
    assert 'get_experimental_policy().moltenvk_async_submits && pgpu->optional_features_support.global_priority' in device
    config = (source / 'rpcs3/Emu/system_config.h').read_text()
    assert 'moltenvk_async_submits{ this, "MoltenVK Asynchronous Submits", ios_experimental_mode::automatic };' in config
    assert 'resolved.moltenvk_async_submits = resolve_mode(g_cfg.ios_experimental.moltenvk_async_submits, false);' in \
        (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
    platform = (source / 'rpcs3/ios/RPCS3IOSPlatform.mm').read_text()
    hook = braced(platform, 'extern "C" __attribute__((visibility("hidden"))) dispatch_queue_t rbx_mvk_compile_qos_queue(')
    assert 'qos_class_self() == QOS_CLASS_USER_INTERACTIVE' in hook
    assert 'dispatch_get_global_queue(QOS_CLASS_USER_INTERACTIVE, 0)' in hook and 'dispatch_get_global_queue(identifier, flags)' in hook
    assert len('_rbx_mvk_compile_qos_queue') == len('_dispatch_get_global_queue')
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    assert '"COREPROF RSXSYNC551 ' in perf and '"COREPROF SPUWAIT551 ' in perf and '"COREPROF RSXFRAME551 ' in perf
    rsx = (source / 'rpcs3/Emu/RSX/RSXThread.cpp').read_text()
    flip = rsx[rsx.index('REWINDBOX_RSX_FRAME_PROFILE_V1 (ios/IOSRsxSyncProfile.h)'):rsx.index('m_profiler.enabled = m_profiler.enabled || ios_sample_frame;')]
    assert flip.index('window.frames.fetch_add(1, relaxed);') < flip.index('m_frame_stats = {};')
    assert (source / 'rpcs3/Emu/RSX/RSXFIFO.cpp').read_text().count('rsx_frames.fifo_idle_entries.fetch_add(1') == 3
    boot = (source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h').read_text()
    for token in ('inherited', 'kept', 'accurate_res', 'mt_rsx', 'spu_spin', 'mlaa_bypass'):
        assert f'"{token}"' in boot, token
    return dict(noExceptionsAdded=True, noWaitAdded=True, codegenFilesChanged=['rpcs3/Emu/Cell/SPUThread.cpp'],
                identities=identities, iosOnlyLines=True)


def yaml_sources(yaml_dir: Path):
    sources = sorted((yaml_dir / 'src').rglob('*.cpp'))
    assert sources and (yaml_dir / 'include/yaml-cpp/yaml.h').exists(), yaml_dir
    return sources


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--yaml-cpp', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    yaml_dir = (a.yaml_cpp or source / '3rdparty/yaml-cpp/yaml-cpp').resolve()
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    database, overrides = gow3_database()
    assert 'gpu.shader_mode' not in overrides and 'Shader Mode:' not in database
    snapshot = GLOBAL  # identical to the global config for every key, as observed
    with tempfile.TemporaryDirectory(prefix='cell551-') as td:
        work = Path(td)
        before = baseline(source, work)
        checks = static_checks(source, before)
        yaml_cpp = (source / 'rpcs3/util/yaml.cpp').read_text()
        load = braced(yaml_cpp, 'std::pair<YAML::Node, std::string> yaml_load(const std::string& from)')
        code = ('#include <cstdint>\nusing u64 = std::uint64_t;\n#define RPCS3_IOS 1\n'
                f'#include "{source / "rpcs3/ios/RPCS3IOSConfigInheritance.h"}"\n'
                f'#include "{source / "rpcs3/ios/IOSSpuWaitProfile.h"}"\n'
                f'#include "{source / "rpcs3/ios/IOSRsxSyncProfile.h"}"\n'
                + load + '\n' + cxx_string('kGow3Database', database) + cxx_string('kLegacySnapshot', snapshot)
                + cxx_string('kGlobal', GLOBAL) + f'static constexpr unsigned kGow3DatabaseLeaves = {leaves(database)};\n'
                + (ROOT / 'test/native/rpcs3_cell551.inc').read_text())
        cpp = work / 'cell551.cpp'
        cpp.write_text(code)
        includes = ['-I', str(source / 'rpcs3'), '-I', str(source / 'rpcs3/ios'), '-isystem', str(yaml_dir / 'include')]
        results = {}
        for mode, flags in (('sanitized', ['-O1', '-fsanitize=address,undefined']), ('thread', ['-O1', '-fsanitize=thread'])):
            exe = work / ('cell551-' + mode)
            # RPCS3's yaml-cpp fork is third-party code: built with the same
            # sanitizers but without -Werror; the harness itself is -Werror.
            objects = []
            for index, unit in enumerate(yaml_sources(yaml_dir)):
                obj = work / f'yaml-{mode}-{index}.o'
                subprocess.run(cxx + ['-std=c++20', '-w', '-g', '-pthread', '-fno-omit-frame-pointer', *flags,
                                      '-isystem', str(yaml_dir / 'include'), '-c', str(unit), '-o', str(obj)], check=True)
                objects.append(str(obj))
            subprocess.run(cxx + ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                  '-Wno-unused-function', '-pthread', '-fno-omit-frame-pointer', *flags, *includes, str(cpp),
                                  *objects, '-o', str(exe)], check=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                       TSAN_OPTIONS='halt_on_error=1')
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=900, env=env)
            if run.returncode:
                print(run.stdout, run.stderr)
                run.check_returncode()
            results[mode] = json.loads(run.stdout)
        # CONFIG_LAYERS: the production formatter with the 551 tokens.
        boot = work / 'boot487'
        subprocess.run(cxx + ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-I', str(source), '-I', str(source / 'rpcs3'),
                              '-I', str(source / 'rpcs3/ios'), str(ROOT / 'test/native/rpcs3_build487_boot_diagnostics_test.cpp'),
                              '-o', str(boot)], check=True)
        boot_run = subprocess.run([str(boot)], capture_output=True, text=True, timeout=120)
        assert boot_run.returncode == 0 and 'PASS' in boot_run.stdout, (boot_run.stdout, boot_run.stderr)
        results['configLayers'] = boot_run.stdout.strip().splitlines()[-1]
        harness = sha(code.encode())
    assert all(r['failures'] == 0 for k, r in results.items() if k != 'configLayers')
    inputs = ['test/rpcs3_cell551_test.py', 'test/native/rpcs3_cell551.inc', 'test/fixtures/rpcs3_cell551.diff',
              'test/native/rpcs3_build487_boot_diagnostics_test.cpp',
              'lib/services/rpcs3_game_profile_service.dart', 'assets/data/rpcs3_ios_profiles.json']
    report = dict(result='passed', passed=True, static=checks, scenarios=results, harnessSHA256=harness,
                  gow3DatabaseSHA256=sha(database.encode()), gow3DatabaseLeaves=leaves(database),
                  sanitizers='ASan+UBSan, then TSan', yamlCpp=str(yaml_dir), cpuCount=os.cpu_count(),
                  sourceSHA256={p: sha((source / p).read_bytes().replace(b'\r\n', b'\n')) for p in MODIFIED + NEW},
                  inputs={p: sha((ROOT / p).read_bytes()) for p in inputs}, physicalDeviceTested=False,
                  scope='configuration layering, counters and wait attribution on the host; not MoltenVK, Metal or the iPhone')
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 CELL551: legacy configs inherit the database, SPU/RSX profiles exact under concurrency, delta iOS-only.')


if __name__ == '__main__':
    main()
