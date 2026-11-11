#!/usr/bin/env python3
"""Host test of RPCS3 Core 931, the thermal chantier (maintainer, 11 Nov 2026: « Principal amélioration à faire serait au
niveau thermique » ; « fais un vrai chantier d'innovation sur la gestion thermique »).

Source checks on the Core tree (--source) and a harness built from the Core's own headers:
- REWINDBOX_HOT_COUNTERS_931: per-thread shards for the writer-lock phase, park and PPU park counters; sums, maxima and
  clearing equal the previous single atomics under 24 concurrent writers and a concurrent reporter;
- REWINDBOX_WRITER_RECORD_AFTER_RELEASE_931: vm::writer_lock's constructor keeps its phases in a thread-local slot that
  record_writer_lock (called by the destructor after the release) publishes, once, on the same thread;
- REWINDBOX_THERMAL_POLICY_931: the decision table (Automatic from the serious state, Enabled, Disabled, a comparison
  step), the comparison schedule (the eight combinations with the levers of 917 and 918), and the three monitor waits
  in the real sources, with the PPU thread showing cpu_flag::wait BEFORE it sleeps (otherwise the writer that holds the
  bit and the PPU thread would wait for each other);
- REWINDBOX_ENERGY_931: the line's arithmetic (nanojoules to millijoules, Mach ticks to milliseconds, per frame),
  unavailable and first-window states, counters that went back;
- REWINDBOX_BACKGROUND_PAUSE_931: pause only a running emulation, resume only a pause made here, after the GPU gate has
  reopened, from a serial queue (never the main thread).
Controls, always run: a report that reads one shard only, and three source mutations (wait flag after the sleep,
phases recorded inside the lock, resume before the gate) must each be caught.
Not an iPhone: energy, heat and frame rate are read from the device journals (COREPROF ENERGY931 and THERMAL931)."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/rpcs3_thermal931/harness.cpp'


def read(source: Path, rel: str) -> str:
    return (source / rel).read_text(encoding='utf-8', errors='replace')


def source_errors(texts: dict[str, str]) -> list[str]:
    errors: list[str] = []
    vm = texts['rpcs3/Emu/Memory/vm.cpp']
    perf = texts['rpcs3/ios/RPCS3IOSPerformance.cpp']
    fifo = texts['rpcs3/Emu/RSX/RSXFIFO.cpp']
    plat = texts['rpcs3/ios/RPCS3IOSPlatform.mm']
    spu = texts['rpcs3/Emu/Cell/SPUThread.cpp']

    # Writer park spin: the event branch waits on the PPU thread's state line, with the clock read every step.
    if 'const bool ios_event_wait = ios_park_spin && rpcs3::ios::thermal::event_waits();' not in vm:
        errors.append('writer park: event decision missing')
    if 'ios_event_wait ? 1 : rpcs3::ios::writer_park::clock_interval' not in vm:
        errors.append('writer park: budget clock not read every step in event mode')
    if not re.search(r'const void\* ios_word = &ptr->state\.raw\(\);\s*rpcs3::ios::event_wait::once32\(ios_word, rpcs3::ios::event_wait::load32\(ios_word\)\);', vm):
        errors.append('writer park: monitor wait on the PPU state word missing')

    # PPU passive spin: cpu_flag::wait set before the sleep, same 6.7 us bound, the timed waits after it.
    passive = re.search(r'if \(ios_event_wait\)\s*\{\s*const u64 ios_now = utils::get_tsc\(\);(.*?)\n\t\t\t\t\t\}\n\t\t\t\t\telse\n', vm, re.S)
    if not passive:
        errors.append('ppu passive: event branch not found')
    else:
        body = passive.group(1)
        flag = body.find('cpu.state += cpu_flag::wait;')
        sleep = body.find('rpcs3::ios::event_wait::once64(')
        if flag < 0 or sleep < 0 or flag > sleep:
            errors.append('ppu passive: cpu_flag::wait is not set before the monitor wait')
        if 'i = 99;' not in body or 'ios_spin_until = ios_now + ios_spin_ticks;' not in body:
            errors.append('ppu passive: time bound or hand-over to the timed waits missing')
    if 'static const u64 ios_spin_ticks = utils::get_tsc_freq() * 67 * 100 / 1\'000\'000\'000;' not in vm:
        errors.append('ppu passive: bound is not 100 x 67 ns')

    # Phases recorded after the release.
    if 'rpcs3::ios::writer_lock_record::defer(' not in vm:
        errors.append('writer lock: phases not deferred')
    if re.search(r'rpcs3::ios::writer_lock_phases::record\(|rpcs3::ios::writer_park::record_park\(', vm):
        errors.append('writer lock: phases still recorded inside the lock')
    record = re.search(r'void record_writer_lock\(u32 source, u64 acquire_ticks, u64 hold_ticks\) noexcept\n\{(.*?)\n\}', perf, re.S)
    if not record or 'rpcs3::ios::writer_lock_record::flush();' not in record.group(1):
        errors.append('record_writer_lock does not publish the deferred phases')
    dtor = re.search(r'writer_lock::~writer_lock\(\) noexcept\n\t\{(.*?)\n\t\}', spu, re.S)
    if not dtor or dtor.group(1).find('range_lock->release(0);') < 0 or dtor.group(1).find('record_writer_lock(') < dtor.group(1).find('range_lock->release(0);'):
        errors.append('the destructor no longer calls record_writer_lock after the release')

    # RSX FIFO idle: monitor wait on PUT, then the yield as before.
    if not re.search(r'const void\* ios_word = &m_ctrl->put\.raw\(\);\s*rpcs3::ios::event_wait::once32\(ios_word, rpcs3::ios::event_wait::load32\(ios_word\)\);\s*rpcs3::ios::thermal::count\(rpcs3::ios::thermal::rsx_idle\);\s*\}\s*#endif\s*std::this_thread::yield\(\);', fifo):
        errors.append('rsx fifo: monitor wait on PUT before the kept yield missing')

    # Background pause and thermal state in the lifecycle observers.
    active = re.search(r'UIApplicationDidBecomeActiveNotification object:nil queue:nil\s*usingBlock:\^\(NSNotification\*\) \{(.*?)\}\];', plat, re.S)
    if not active or active.group(1).find('gate::instance().app_became_active();') < 0 or \
            active.group(1).find('rpcs3::ios::background_pause::app_became_active();') < active.group(1).find('gate::instance().app_became_active();'):
        errors.append('background pause: resume is not after the gate reopens')
    if 'UIApplicationDidEnterBackgroundNotification object:nil queue:nil\n\t\t\t\tusingBlock:^(NSNotification*) { rpcs3::ios::background_pause::app_entered_background(); }' not in plat:
        errors.append('background pause: no pause on entering the background')
    if 'dispatch_queue_create("rpcs3.background-pause", DISPATCH_QUEUE_SERIAL)' not in plat or 'rpcs3_ios_pause_emulation() == RPCS3_IOS_OK' not in plat \
            or 'rpcs3_ios_resume_emulation() == RPCS3_IOS_OK' not in plat:
        errors.append('background pause: not on its serial queue through the exports')
    if 'NSProcessInfoThermalStateDidChangeNotification' not in plat or 'rpcs3::ios::thermal::set_state(static_cast<int>(NSProcessInfo.processInfo.thermalState));' not in plat:
        errors.append('thermal state observer missing')

    # Setting, policy line, report lines.
    if 'cfg::_enum<ios_experimental_mode> event_waits_when_hot{ this, "Event Waits When Hot", ios_experimental_mode::automatic };' not in texts['rpcs3/Emu/system_config.h']:
        errors.append('setting missing or not Automatic by default')
    if 'SETTING("experimental.event_waits_when_hot"' not in texts['rpcs3/ios/RPCS3IOSSettings.cpp']:
        errors.append('settings registry entry missing')
    if 'Resolved title policy 931: event_waits_when_hot=%s' not in texts['rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp']:
        errors.append('policy line 931 missing')
    for marker in ('energy931::format_line(profile_session, profile_window, comparable, m_energy, energy, guest_window_flips)',
                   'COREPROF THERMAL931 session=%llu window=%llu thermal_state=%s',
                   'rpcs3::ios::thermal::compare_forced.store(next_step ? (cmp::event_waits_at(next_step) ? 1 : 0) : -1'):
        if marker not in perf:
            errors.append('report: ' + marker[:60] + ' missing')
    return errors


FILES = ('rpcs3/Emu/Memory/vm.cpp', 'rpcs3/ios/RPCS3IOSPerformance.cpp', 'rpcs3/Emu/RSX/RSXFIFO.cpp', 'rpcs3/ios/RPCS3IOSPlatform.mm',
         'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/system_config.h', 'rpcs3/ios/RPCS3IOSSettings.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')


def mutations(texts: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    vm = texts['rpcs3/Emu/Memory/vm.cpp']
    flag_first = '''							if (cpu_flag::wait - cpu.state)
							{
								cpu.state += cpu_flag::wait;
							}

							const void* ios_word = &get_range_lock_bits(true).raw();
							rpcs3::ios::event_wait::once64(ios_word, rpcs3::ios::event_wait::load64(ios_word));'''
    flag_after = '''							const void* ios_word = &get_range_lock_bits(true).raw();
							rpcs3::ios::event_wait::once64(ios_word, rpcs3::ios::event_wait::load64(ios_word));
							if (cpu_flag::wait - cpu.state)
							{
								cpu.state += cpu_flag::wait;
							}'''
    inside = vm.replace('rpcs3::ios::writer_lock_record::defer(phase_bits_end - acquire_begin, phase_ranges_end - phase_bits_end,\n\t\t\t\t\tphase_park_end - phase_ranges_end, phase_flagged, slow_threshold, utils::get_tsc_freq(), ios_park.spent);',
                        'rpcs3::ios::writer_lock_phases::record(phase_bits_end - acquire_begin, phase_ranges_end - phase_bits_end,\n\t\t\t\t\tphase_park_end - phase_ranges_end, phase_flagged, slow_threshold);', 1)
    plat = texts['rpcs3/ios/RPCS3IOSPlatform.mm']
    early = plat.replace('''					gate::instance().app_became_active();
					rpcs3::ios::background_pause::app_became_active(); // REWINDBOX_BACKGROUND_PAUSE_931''',
                         '''					rpcs3::ios::background_pause::app_became_active(); // REWINDBOX_BACKGROUND_PAUSE_931
					gate::instance().app_became_active();''', 1)
    out = []
    for name, rel, changed in (('wait flag after the sleep', 'rpcs3/Emu/Memory/vm.cpp', vm.replace(flag_first, flag_after, 1)),
                               ('phases recorded inside the lock', 'rpcs3/Emu/Memory/vm.cpp', inside),
                               ('resume before the gate', 'rpcs3/ios/RPCS3IOSPlatform.mm', early)):
        if changed == texts[rel]:
            raise SystemExit('control could not be built: ' + name)
        out.append((name, {**texts, rel: changed}))
    return out


def analyzer_errors(work: Path) -> list[str]:
    """REWINDBOX_ENERGY_931 in tools/rpcs3/capture_analyzer.py: per thermal state, event waits off against on; never a hot
    window against a cool one."""
    lines = []
    clock = 1794384000.0
    def line(message: str) -> None:
        nonlocal clock
        clock += 0.001
        lines.append(json.dumps({'build': '931', 'message': 'TID: 1: ' + message, 'timestamp': clock, 'stage': 'core_log', 'pid': 4242}))
    lines.append(json.dumps({'build': '931', 'message': 'Resolved title policy 931: event_waits_when_hot=automatic', 'timestamp': clock, 'stage': 'core_log', 'pid': 4242,
                             'title': 'BLES01717'}))
    windows = [(1, 'fair', 'off', 40.0, 50.0), (2, 'serious', 'off', 30.0, 80.0), (3, 'serious', 'off', 31.0, 78.0),
               (4, 'serious', 'on', 31.0, 70.0), (5, 'serious', 'on', 32.0, 69.0)]
    for window, state, waits, fps, mj in windows:
        clock += 5.0
        line(f'COREPROF FRAMEPROF527 session=2 window={window} wall_guest_fps={fps} p95_ms=40.0')
        line(f'COREPROF SCHED918 session=2 window={window} task_events=available context_switches=400000 mach_traps=200000 unix_syscalls=350000 busy_wait_scale=42')
        line(f'COREPROF ENERGY931 session=2 window={window} energy=available frames={int(fps * 5)} cpu_energy_mj={mj * fps * 5:.1f} p_energy_mj=1.0 '
             f'mj_per_frame={mj:.3f} cpu_ms=100.0 p_cpu_ms=50.0 p_share=0.500 timer_wakeups_2ms=1000 timer_wakeups_5ms=10 gpu_utilisation_delta=5 pset_switches=1')
        line(f'COREPROF THERMAL931 session=2 window={window} thermal_state={state} state_changes=1 event_waits={waits} mode=automatic compared=no')
    journal = work / 'RPCS3-performance.log'
    journal.write_text('\n'.join(lines) + '\n')
    run = subprocess.run([sys.executable, str(ROOT / 'tools/rpcs3/capture_analyzer.py'), str(journal)], capture_output=True, text=True)
    out = run.stdout
    errors = []
    if run.returncode != 0:
        errors.append('analyzer failed: ' + run.stderr[-500:])
    if 'energy per frame (medians per window; ENERGY931, THERMAL931):' not in out:
        errors.append('analyzer: no energy section')
    if not re.search(r'thermal_state=serious: windows 4 \(2,3,4,5\)', out):
        errors.append('analyzer: serious windows not grouped')
    if not re.search(r'event_waits=off: windows 2 \(2,3\) fps 30\.50 mj_per_frame 79\.000', out) or \
            not re.search(r'event_waits=on: windows 2 \(4,5\) fps 31\.50 mj_per_frame 69\.500', out):
        errors.append('analyzer: off/on comparison inside the serious state wrong:\n' + out[-1500:])
    if re.search(r'thermal_state=fair: .*\n\s+event_waits=', out):
        errors.append('analyzer: a state with one side only was compared')
    return errors


def build_and_run(cxx: str, include: Path, work: Path, extra: list[str], sanitize: bool) -> tuple[int, str]:
    binary = work / ('harness' + ('_m' if extra else ''))
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-pthread']
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([cxx, *flags, *extra, '-I', str(include), str(HARNESS), '-o', str(binary)], check=True)
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=600)
    return run.returncode, run.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    texts = {rel: read(source, rel) for rel in FILES}
    errors = source_errors(texts)
    for name, mutated in mutations(texts):
        if not source_errors(mutated):
            errors.append('control not caught: ' + name)
    work = Path(tempfile.mkdtemp(prefix='thermal931-'))
    try:
        code, out = build_and_run(args.cxx, source / 'rpcs3/ios', work, [], not args.no_sanitizers)
        result = json.loads(out.strip().splitlines()[-1])
        waits = json.loads(out.strip().splitlines()[-2])
        if code or result['failures']:
            errors.append('harness: ' + out[-2000:])
        errors.extend(analyzer_errors(work))
        mcode, mout = build_and_run(args.cxx, source / 'rpcs3/ios', work, ['-DMUTANT_TAKE_FIRST_SHARD'], False)
        if mcode == 0:
            errors.append('control not caught: a report reading one shard only')
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report = {'result': 'failed' if errors else 'passed', 'checks': result.get('checks'), 'eventWait': waits, 'errors': errors,
              'controls': ['one shard read', 'wait flag after the sleep', 'phases recorded inside the lock', 'resume before the gate'],
              'physicalDeviceTested': False}
    if args.report:
        args.report.write_text(json.dumps(report, indent=1) + '\n')
    if errors:
        print('\n'.join(errors))
        return 1
    print('PASS: Core 931 thermal chantier (%s); the four controls are caught' % json.dumps({'checks': result['checks'], 'failures': 0, 'event_wait': waits}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
