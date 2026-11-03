#!/usr/bin/env python3
"""Build 621: the RPCS3 Core 621 changes and the host integration, on the host.

Core 621 is the delivered Core 619 plus build-utils/rpcs3/core621-from-619.patch:

1. REWINDBOX_GPU_TIMING_621 (ios/IOSGpuTiming.h, VKGSRender.cpp/.h,
   VKGSRenderTypes.hpp, VKPresent.cpp, VKCommandStream.cpp, vkutils/device.*,
   RSXThread.cpp, RPCS3IOSPerformance.cpp, the GPU Timing Probe setting): a
   Vulkan timestamp pair around every RSX primary command buffer (MoltenVK
   1.4.2 samples it on the GPU at Metal stage boundaries), read without waiting
   once the chunk's fence signalled, calibrated against the host clock with
   VK_EXT_calibrated_timestamps, attributed to the session and to the RSX
   frame, overlaps counted once (COREPROF GPUTIME621, FRAMECAUSE_EVENT fields).
2. REWINDBOX_FREEZE_EPISODE_621 (RPCS3IOSFreezeEpisode.h, the 500 ms sampler,
   RPCS3IOSFreezeDump.cpp): freezes as episodes whose clock stops while
   paused, loading or suspended; a quiet freeze; one dump per episode with a
   waits summary; FREEZE_EPISODE begin/update/end.
3. REWINDBOX_ISO_IMAGE_LIFETIME_621 (Loader/ISO.cpp/.h): the mounted image is
   opened once and shared by every file (pread), so renaming it during a
   session cannot fail a later open (the Minecraft report).
4. REWINDBOX_PIPELINE_QUEUE_621 (IOSPipelineQueue.h, VKDraw.cpp): the graphics
   pipeline queue per window and the draws skipped for a program not ready.

Host (packages/rpcs3_internal_bridge/ios/Classes): REWINDBOX_CORE_LOG_BOUNDED_621
(Rpcs3CoreLogAdmission.h, asynchronous core_log) and REWINDBOX_INCIDENT_REPORT_621
(Rpcs3IncidentReport.h: incidents, session record, last-fatal file, streamed
report export; the Objective-C++ glue is compiled by the application build).

This test:
- reverts core621-from-619.patch on a copy of the touched files of --source and
  requires the delivered Core 619 files (--baseline619) byte for byte, every
  touched file naming a 621 marker;
- runs the GPU timing bookkeeping (union, attribution, pending, session,
  calibration, 512-slot ring soak, concurrent reader) plain, under TSan and
  under ASan/UBSan, and reports its host cost per submission;
- replays the freeze-episode scenarios (normal pause, freeze then repeated
  pauses, quiet freeze, guest-fault freeze and stop, iOS suspension, loading,
  recovery then a later freeze);
- compiles the real Loader/ISO.cpp of both trees against a POSIX fs stub with
  generated PS3 images: Core 619 reproduces the failure (a file first opened
  after renaming the mounted image throws "Null object." on its first read),
  Core 621 reads it, survives a replacement, 8 concurrent readers (TSan), an
  unmount with a file open, releases the descriptor and mounts another disc;
- runs the host logging test: slow disk (2 ms per line), bursts, a fatal line
  written right before abort(), the session record, incidents, and the peak
  memory of the streamed export of a large journal against a whole-file read;
- checks the host integration text (no dispatch_sync of core_log lines, the 13
  new strings in the 12 locales, the GPU timing lever and its whitelist entry).

    python3 test/rpcs3_core621_test.py --source <Core 621 tree> --baseline619 <Core 619 tree>
        [--cxx g++] [--big-log-mib 256] [--no-sanitizers] [--report out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core621'
DELTA = ROOT / 'build-utils/rpcs3/core621-from-619.patch'
RECORD = ROOT / 'build-utils/rpcs3/core621-delta.json'
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
MARKERS = ('REWINDBOX_GPU_TIMING_621', 'REWINDBOX_FREEZE_EPISODE_621', 'REWINDBOX_ISO_IMAGE_LIFETIME_621',
           'REWINDBOX_PIPELINE_QUEUE_621',
           # Build 620 logs: ZCULL waits explained per frame, the on-demand guard, Black Ops II joins the lever.
           'REWINDBOX_ZCULL_FRAME_621', 'REWINDBOX_ZCULL_DEMAND_GUARD_621', 'REWINDBOX_ZCULL_DEMAND_BO2_621',
           # Single re-read of the Build 620 logs: texture cache and feedback barriers per window, deeper freeze dump.
           'REWINDBOX_TEXCACHE_PROFILE_621', 'REWINDBOX_FREEZE_DEEP_621')
LOCALES = ('en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko')
KEYS_621 = ('reportProblem', 'reportProblemDetail', 'reportFailed', 'gameStoppedTitle',
            'gameStoppedMessage', 'closeAndReport', 'closeGame', 'previousEndedTitle', 'previousEndedMessage',
            'shareReport', 'later', 'testGpuTiming', 'testZcullOnDemand')


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def run(command, cwd=None, timeout=1800, env=None):
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, timeout=timeout, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result, time.monotonic() - started


def patch_files(text: str) -> list[str]:
    return sorted(set(re.findall(r'^diff --git a/(\S+) b/', text, re.M)))


def check_increment(source: Path, baseline: Path | None, work: Path) -> tuple[dict, Path]:
    """Reverts the delta on a copy of the touched files; returns the report and the Core 619 copy."""
    increment = json.loads(RECORD.read_text())['increment_from_core619'] if RECORD.exists() else {}
    pinned = increment.get('files_before_sha256', {})
    raw = DELTA.read_bytes()
    text = raw.decode('utf-8', 'surrogateescape')
    files = patch_files(text)
    require(files, 'core621-from-619.patch names no file')
    copy = work / 'revert'
    new_files = []
    for name in files:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        body = (source / name).read_text('utf-8', 'surrogateescape')
        require(any(marker in body for marker in MARKERS), f'{name} names no Core 621 marker')
        if (baseline is not None and not (baseline / name).exists()) or (baseline is None and name in increment.get('new_files', ())):
            new_files.append(name)
    subprocess.run(['git', 'init', '-q'], cwd=copy, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=copy,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core621-from-619.patch does not revert: ' + result.stdout[-2000:])
    for name in files:
        reverted = copy / name
        if name in new_files:
            require(not reverted.exists() or reverted.stat().st_size == 0, f'{name} survives the revert')
            continue
        digest = hashlib.sha256(reverted.read_bytes()).hexdigest()
        if baseline is not None:
            require(reverted.read_bytes() == (baseline / name).read_bytes(), f'{name} reverted is not the Core 619 file')
        if pinned:
            require(pinned.get(name) == digest, f'{name} reverted does not match its pinned Core 619 SHA-256')
        require(baseline is not None or pinned, 'neither --baseline619 nor core621-delta.json to authenticate the revert')
    return ({'files': len(files), 'new_files': new_files, 'patch_sha256': hashlib.sha256(raw).hexdigest(),
             'authenticated_by': ('tree ' if baseline is not None else '') + ('pinned_sha256' if pinned else '')}, copy)


def notice_arguments(text: str, marker: str) -> tuple[int, int]:
    """Counts the printf conversions of the notice whose format names `marker`, and its arguments."""
    start = text.index(marker)
    call = text.rindex('ios_core_profiler.notice(', 0, start) + len('ios_core_profiler.notice(')
    depth, index = 1, call
    while depth:
        depth += {'(': 1, ')': -1}.get(text[index], 0)
        index += 1
    body = text[call:index - 1]
    literal = ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', body[:body.rindex('"') + 1]))
    conversions = len(re.findall(r'%(?!%)[-+ #0-9.]*(?:ll|l|z)?[duxXfsp]', literal))
    rest, depth, args = body[body.rindex('"') + 1:], 0, 0
    for char in rest:
        if char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
        elif char == ',' and depth == 0:
            args += 1
    return conversions, args


def build(cxx: str, sources: list[Path], output: Path, includes: list[Path], flags: list[str]) -> None:
    command = [cxx, '-std=c++20', *flags, *[f'-I{path}' for path in includes], *map(str, sources), '-o', str(output), '-pthread']
    result, _ = run(command, timeout=1200)
    require(result.returncode == 0, f'compile {output.name} failed:\n' + result.stdout[-4000:])


def execute(command, label: str, env=None) -> str:
    result, seconds = run(command, env=env)
    require(result.returncode == 0, f'{label} failed:\n' + result.stdout[-6000:])
    print(f'  {label}: ok ({seconds:.1f} s)')
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='materialized Core 621 tree')
    parser.add_argument('--baseline619', type=Path, help='materialized Core 619 tree (default: the reverted copy, '
                        'authenticated by the SHA-256 pinned in core621-delta.json increment_from_core619)')
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++') or 'c++')
    parser.add_argument('--big-log-mib', type=int, default=256)
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    baseline = args.baseline619.resolve() if args.baseline619 else None
    report: dict = {'cxx': args.cxx}
    plain = ['-O2', '-Wall', '-Wextra', '-Werror']
    asan = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=undefined']
    tsan = ['-O1', '-g', '-fsanitize=thread'] + (['-Wno-tsan'] if 'clang' not in Path(args.cxx).name and 'g++' in Path(args.cxx).name else [])
    sanitize = not args.no_sanitizers
    with tempfile.TemporaryDirectory(prefix='core621-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'], reverted = check_increment(source, baseline, work)

        print('gpu timing')
        core_include = source / 'rpcs3'
        gt = work / 'gpu_timing'
        build(args.cxx, [HERE / 'gpu_timing_test.cpp'], gt, [core_include], plain)
        output = execute([str(gt)], 'gpu timing (plain)')
        bench = re.search(r'BENCH_JSON (\{.*\})', output)
        report['gpu_timing'] = {'bench': json.loads(bench.group(1)) if bench else None,
                                'soak': re.search(r'ring soak: (.*)', output).group(1)}
        if sanitize:
            build(args.cxx, [HERE / 'gpu_timing_test.cpp'], work / 'gpu_timing_tsan', [core_include], tsan)
            execute([str(work / 'gpu_timing_tsan'), '--quick'], 'gpu timing (TSan)', env=dict(os.environ, TSAN_OPTIONS='halt_on_error=1'))
            build(args.cxx, [HERE / 'gpu_timing_test.cpp'], work / 'gpu_timing_asan', [core_include], asan)
            execute([str(work / 'gpu_timing_asan'), '--quick'], 'gpu timing (ASan/UBSan)')

        print('zcull on demand (Build 620 logs)')
        sys.path.insert(0, str(ROOT / 'test'))
        import rpcs3_core621_zcull as zcull621
        report['zcull_on_demand'] = zcull621.run(
            source, [args.cxx], {'plain': [], 'tsan': [f for f in tsan if f not in ('-O1', '-g')],
                                 'asan': ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']},
            work, sanitize)
        print('  zcull on demand: guard, real fault protocol' + (' (plain, TSan, ASan/UBSan)' if sanitize else ' (plain)') +
              ', ZCULLDEMAND619/ZCULLTRIP621 lines, levers, setting, frame wiring: ok')

        print('texture cache profile (Build 620 logs)')
        tc = work / 'texcache_profile'
        build(args.cxx, [HERE / 'texcache_profile_test.cpp'], tc, [core_include], plain)
        execute([str(tc)], 'texture cache profile (plain)')
        if sanitize:
            build(args.cxx, [HERE / 'texcache_profile_test.cpp'], work / 'texcache_tsan', [core_include], tsan)
            execute([str(work / 'texcache_tsan')], 'texture cache profile (TSan)', env=dict(os.environ, TSAN_OPTIONS='halt_on_error=1'))
        performance = (core_include / 'ios/RPCS3IOSPerformance.cpp').read_text()
        conversions, arguments = notice_arguments(performance, 'COREPROF TEXCACHE621 ')
        require(conversions == arguments == 20, f'TEXCACHE621 line has {conversions} conversions for {arguments} arguments')
        present = (core_include / 'Emu/RSX/VK/VKPresent.cpp').read_text()
        require(present.index('rpcs3::ios::texture_cache_profile::on_frame_end({') < present.index('m_texture_cache.on_frame_end();'),
                'the texture cache statistics are not taken before on_frame_end resets them')
        targets = (core_include / 'Emu/RSX/VK/VKRenderTargets.cpp').read_text()
        for counter in ('feedback_skipped', 'feedback_barriers', 'post_skipped', 'post_barriers'):
            require(f'texture_cache_profile::counters.{counter});' in targets, f'{counter} is not counted')
        cache = (core_include / 'Emu/RSX/VK/VKTextureCache.cpp').read_text()
        require('texture_cache_profile::on_temporary_subresource(cached != nullptr);' in cache, 'temporary copies are not counted')
        settings = (core_include / 'ios/RPCS3IOSSettings.cpp').read_text()
        require('Black Ops II runs with Accurate SPU Reservations off, so there it changes nothing.' in settings,
                'the no-op PUTLLC setting still promises an effect on Black Ops II')
        freeze = (core_include / 'ios/RPCS3IOSFreezeDump.cpp').read_text()
        for line in ('FREEZE_DUMP line addr=0x%x rtime=0x%llx data=%s', 'FREEZE_DUMP sema id=0x%x name=%s val=%d max=%d waiters=%d ids=%s',
                     'spurs_addr=0x%x', 'lr=0x%llx'):
            require(line in freeze, f'freeze dump lacks {line!r}')
        report['texcache_profile'] = {'conversions': conversions}

        print('freeze episodes')
        fe = work / 'freeze_episode'
        build(args.cxx, [HERE / 'freeze_episode_test.cpp'], fe, [core_include], plain)
        execute([str(fe)], 'freeze episodes (plain)')
        if sanitize:
            build(args.cxx, [HERE / 'freeze_episode_test.cpp'], work / 'freeze_episode_asan', [core_include], asan)
            execute([str(work / 'freeze_episode_asan')], 'freeze episodes (ASan/UBSan)')

        print('iso lifetime')
        iso_results = {}
        core619_iso = baseline if baseline is not None else reverted
        variants = [('core619', core619_iso, 'defect', ['-O1', '-g']), ('core621', source, 'fixed', ['-O1', '-g'])]
        if sanitize:
            variants += [('core621-tsan', source, 'fixed', tsan), ('core621-asan', source, 'fixed', asan)]
        for label, tree, expect, flags in variants:
            loader = work / f'iso-{label}' / 'Loader'
            loader.mkdir(parents=True)
            for name in ('ISO.h', 'ISO.cpp'):
                shutil.copyfile(tree / 'rpcs3/Loader' / name, loader / name)
            images = work / f'iso-{label}-work'
            images.mkdir()
            execute([sys.executable, '-I', str(HERE / 'make_iso.py'), str(images)], f'iso images ({label})')
            binary = work / f'iso-{label}.bin'
            build(args.cxx, [loader / 'ISO.cpp', HERE / 'iso_lifetime_test.cpp'], binary,
                  [HERE / 'iso_stub', loader.parent, loader], flags + ['-w'])
            output = execute([str(binary), expect, str(images / 'disc-a.iso'), str(images / 'disc-b.iso'), str(images)],
                             f'iso lifetime {label} expects {expect}',
                             env=dict(os.environ, TSAN_OPTIONS='halt_on_error=1'))
            iso_results[label] = re.search(r'rename_then_new_file=(.*)', output).group(1)
        require(iso_results['core619'] == 'Null object.', 'Core 619 did not reproduce the renamed-image failure')
        require(iso_results['core621'] == 'ok', 'Core 621 does not read a file first opened after the rename')
        report['iso_lifetime'] = iso_results

        print('host logging')
        hl = work / 'host_logging'
        build(args.cxx, [HERE / 'host_logging_test.cpp'], hl, [CLASSES], plain)
        logs = work / 'host-logs'
        logs.mkdir()
        output = execute([str(hl), str(logs), str(args.big_log_mib)], 'host logging (plain)')
        export = re.search(r'EXPORT_JSON (\{.*\})', output)
        report['host_logging'] = {
            'export': json.loads(export.group(1)) if export else None,
            'slow_disk': re.search(r'slow disk \(2 ms/line\): (.*)', output).group(1),
            'repeated_burst': re.search(r'repeated burst: (.*)', output).group(1),
        }
        if sanitize:
            build(args.cxx, [HERE / 'host_logging_test.cpp'], work / 'host_logging_asan', [CLASSES], asan)
            asan_logs = work / 'host-logs-asan'
            asan_logs.mkdir()
            execute([str(work / 'host_logging_asan'), str(asan_logs), '16'], 'host logging (ASan/UBSan, 16 MiB journal)')

        print('host integration text')
        diagnostics = (CLASSES / 'Rpcs3Diagnostics.mm').read_text()
        plugin = (CLASSES / 'Rpcs3InternalBridgePlugin.mm').read_text()
        menu = (CLASSES / 'Rpcs3SessionMenu.mm').read_text()
        localization = (CLASSES / 'RPCS3InGameLocalization.mm').read_text()
        require('dispatch_sync(_diagnosticQueue, write)' not in diagnostics, 'core_log lines are still written synchronously')
        require('RPCS3CoreLogAdmissionShared().written(reserved)' in diagnostics, 'written core_log bytes are not released')
        require('RPCS3CoreLogAdmissionShared().admit(' in plugin, 'RPCS3Log does not use the admission')
        require('RPCS3RecordFatalLine(message, decision.game_stopped)' in plugin, 'fatal lines are not written at once')
        # The Build 283 budget (and its Build 546 LOG_BUDGET report) stays the code the MoltenVK
        # dependency run's milestones test compiled; fatal and FREEZE_EPISODE lines leave before
        # it, the other admitted lines reach the admission after it (no second budget there).
        log = plugin[plugin.index('static void RPCS3Log(void* context, int32_t level, const char* message) {'):]
        log = log[:log.index('\n}\n')]
        require(log.index('if (level == 1 || strstr(message, "FREEZE_EPISODE ") != nullptr) {') <
                log.index('  const BOOL profiler =') < log.index('if (budgetCount >= 128) {') <
                log.index('if (dropped) RPCS3ReportDroppedLines(dropped);') < log.index('  NSString* text =') <
                log.index('RPCS3AdmitCoreLog(level, message, profiler, text);'), 'RPCS3Log order changed')
        require('limits.per_second = 0;' in diagnostics, 'the shared admission budgets ordinary lines a second time')
        require('@"experimental.gpu_timing": @[@"Enabled", @"Disabled"]' in plugin, 'GPU timing lever not whitelisted')
        require('@"experimental.zcull_on_demand": @[@"Enabled", @"Disabled"]' in plugin, 'ZCULL on-demand lever not whitelisted')
        require('@"key": @"experimental.zcull_on_demand", @"title": @"testZcullOnDemand", @"field": @"zcull_demand"' in menu,
                'ZCULL on-demand lever missing from the accuracy page')
        require('@"key": @"experimental.gpu_timing"' in menu, 'GPU timing lever missing from the accuracy page')
        require('@"reportProblem"' in menu, '"Report a problem" row missing')
        block = localization[localization.index('Build621Translations() {'):]
        block = block[:block.index('return values;')]
        for locale in LOCALES:
            match = re.search(r'@"%s": @\{(.*?)\n      \},' % re.escape(locale), block, re.S)
            require(match, f'Build621Translations has no {locale} table')
            for key in KEYS_621:
                require(re.search(r'@"%s": @"[^"]+",' % key, match.group(1)), f'{locale} lacks {key}')
        require('build621[locale][key] ?: build621[@"en"][key]' in localization, '621 strings are not looked up first')
        report['localization'] = {'locales': len(LOCALES), 'keys': len(KEYS_621)}

    print('PASS: Core 621 increment reverts to Core 619; GPU timing bookkeeping (TSan/ASan), freeze episodes, '
          'ISO lifetime (619 fails, 621 reads), bounded core_log, incidents and streamed export; host text checks')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
