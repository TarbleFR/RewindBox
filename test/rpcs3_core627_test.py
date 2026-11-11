#!/usr/bin/env python3
"""Host tests of RPCS3 Core 627 = Core 624 + build-utils/rpcs3/core627-from-624.patch.

From the Build 624 iPhone logs (3 November 2026, PID 1893) and the God of War III run of Build
622 (PID 1598):

1. REWINDBOX_ZCULL_WAIT_GUARD_627, REWINDBOX_ZCULL_COND_NO_WAIT_627, REWINDBOX_ZCULL_CONSERVATIVE_627:
   guest waits no longer send the ZCULL on-demand lever to the upstream mode, conditional renders
   never wait for a query still on the GPU, and an optional mode where reports read "visible"
   until the GPU result replaces them.
2. REWINDBOX_SPU_NOOP_SPIN_WAIT_627: an SPU polling with no-op PUTLLC waits for a bounded time.
3. REWINDBOX_SPU_QOS_627: SPU threads one QoS class below PPU and RSX;
   REWINDBOX_MVK_ASYNC_RETRY_627: the second try of asynchronous MoltenVK submits.
4. REWINDBOX_FIFO_NOP_FAST_627: a FIFO NOP is not an idle period.
5. REWINDBOX_LIGHT_MEASUREMENT_627: a per-game journal with only the synthesis line.

This test:
- reverts core627-from-624.patch on a copy of the touched files, authenticated by the Core 624
  SHA-256 pinned in core627-delta.json (increment_from_core624), then runs the whole Core 624
  suite (test/rpcs3_core624_test.py) on the reverted Core 624 tree;
- runs the real ZCULL fault protocol of the Core 627 RSXZCULL.cpp, the 621 rules with the
  guard on and the 627 scenarios with it off, plain, TSan and ASan/UBSan;
- runs the real polling block of do_putllc() against mocks of the reservation table
  (test/rpcs3_core627/spin_wait_test.cpp), plain, TSan and ASan/UBSan;
- checks the wiring, the settings, the title defaults, the test page in 12 locales, and rule 1
  of the task: the increment adds no COREPROF tag, no counter and one log call, one line per boot.
No gameplay claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core627'
DELTA = ROOT / 'build-utils/rpcs3/core627-from-624.patch'
RECORD = ROOT / 'build-utils/rpcs3/core627-delta.json'
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
MARKERS = ('627',)
LOCALES = ('en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko')
SETTINGS = {
    'zcull_wait_guard': ('ZCULL On-Demand Wait Guard', 'testZcullWaitGuard'),
    'zcull_cond_no_wait': ('ZCULL Conditional Draw Without Wait', 'testZcullCondNoWait'),
    'zcull_conservative_reports': ('ZCULL Conservative Reports', 'testZcullConservative'),
    'spu_noop_spin_wait': ('SPU No-op Spin Wait', 'testSpuNoopSpinWait'),
    'spu_qos_below_rsx': ('SPU QoS Below RSX And PPU', 'testSpuQos'),
    'fifo_nop_fast_path': ('RSX FIFO NOP Fast Path', 'testFifoNopFast'),
    'light_measurement': ('Light Measurement Profile', 'testLightMeasurement'),
}

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core621_test as core621  # noqa: E402  (shared helpers: require, build, execute)
import rpcs3_core621_zcull as zcull621  # noqa: E402

require = core621.require
c619 = zcull621.c619

GUARD_627 = r'''
	unsigned guard627 = 0, guard627_reads = 0;
	rpcs3::ios::g_policy.zcull_wait_guard = false;
	{ // REWINDBOX_ZCULL_WAIT_GUARD_627, the Build 624 trip (TaskThread1, 548/564/610 ms in three seconds):
	  // the same reads, above the 400 ms budget for more than three seconds, keep the lever.
		ZCULL_control z;
		rsx_server server(z, 50);
		tally.tripped = 0;
		const auto start = get_system_time();
		while (get_system_time() - start < 3'600'000)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
			guard627_reads++;
			std::this_thread::sleep_for(std::chrono::milliseconds(45));
		}
		CHECK(guard627_reads >= 6 && !z.m_ios_demand.tripped() && tally.tripped.load() == 0 && z.upstream_paths.load() == 0 && !z.m_pages_accessed[1]);
		take(tally.faults_report); take(tally.services); take(tally.waits);
		guard627++;
	}
	{ // Reads back to back for three seconds (the 621 severe rule): the lever stays. The macOS runner
	  // stretches each 5 ms read to about 70 ms under ASan (test/rpcs3_core621_zcull.py): three seconds
	  // keep the read floor well within reach.
		ZCULL_control z;
		rsx_server server(z, 5);
		const auto start = get_system_time();
		unsigned reads = 0;
		while (get_system_time() - start < 3'000'000)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
			reads++;
		}
		CHECK(reads >= od::severe_min_waits && !z.m_ios_demand.tripped() && z.upstream_paths.load() == 0);
		take(tally.faults_report); take(tally.services); take(tally.waits);
		guard627++;
	}
	{ // A request nobody picks up still trips at the pickup deadline: the protection stays.
		ZCULL_control z;
		z.enqueue(address);
		const auto start = get_system_time();
		CHECK(guest_access(z, address, thread_class::ppu));
		CHECK(get_system_time() - start >= od::pickup_deadline_us && z.m_ios_demand.tripped());
		CHECK(z.m_ios_demand.trip_record().reason == static_cast<u32>(od::trip_reason::pickup) && z.upstream_paths.load() == 1);
		take(tally.faults_report); take(tally.timeouts);
		guard627++;
	}
	{ // A storm of services still trips.
		ZCULL_control z;
		const u64 now = get_system_time();
		bool tripped = false;
		for (u32 i = 0; i <= od::storm_services && !tripped; i++) tripped = z.m_ios_demand.serve(z.m_ios_demand.request(), now);
		CHECK(tripped && z.m_ios_demand.trip_record().reason == static_cast<u32>(od::trip_reason::storm));
		guard627++;
	}
	rpcs3::ios::g_policy.zcull_wait_guard = true;
	tally.tripped = 0;
	std::printf("{\"guard627\": %u, \"guard627_reads\": %u}\n", guard627, guard627_reads);

'''


def patch_files(text: str) -> list[str]:
    return sorted(set(re.findall(r'^diff --git a/(\S+) b/', text, re.M)))


def check_increment(source: Path, work: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core624']
    pinned = increment['files_before_sha256']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core627-from-624.patch differs from its record')
    files = patch_files(raw.decode('utf-8', 'surrogateescape'))
    require(files and increment['files'] == len(files), 'core627-from-624.patch files')
    copy = work / 'revert627'
    for name in files:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'init', '-q'], cwd=copy, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=copy,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core627-from-624.patch does not revert: ' + result.stdout[-2000:])
    for name in files:
        reverted = copy / name
        if name in increment['new_files']:
            require(not reverted.exists() or reverted.stat().st_size == 0, f'{name} survives the revert')
            continue
        require(pinned.get(name) == hashlib.sha256(reverted.read_bytes()).hexdigest(),
                f'{name} reverted does not match its pinned Core 624 SHA-256')
    return {'files': len(files), 'new_files': increment['new_files'], 'patch_sha256': increment['patch_sha256'],
            'authenticated_by': 'pinned_sha256'}


def core624_tree(source: Path, work: Path) -> Path:
    tree = work / 'core624'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 624 tree cannot be rebuilt: ' + result.stdout[-2000:])
    require(not (tree / 'rpcs3/ios/IOSSpuNoopSpin.h').exists(), 'the Core 627 header survives in the Core 624 tree')
    return tree


def fault_harness_627() -> str:
    zcull621.WITH_LABEL_PAGE_HEADER = True
    text = zcull621.fault_harness_621()
    text = zcull621.replace_once(text, 'struct policy_mock { bool zcull_on_demand = true; };',
                                 'struct policy_mock { bool zcull_on_demand = true; bool zcull_wait_guard = true; };', 'policy mock')
    return zcull621.replace_once(text, '\tstd::printf("{\\"failures\\": %d, \\"scenarios\\": %u, \\"pickup_timeout_ms\\"',
                                 GUARD_627 + '\tstd::printf("{\\"failures\\": %d, \\"scenarios\\": %u, \\"pickup_timeout_ms\\"', 'summary')


def run_fault_protocol(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    zcull = (source / c619.ZCULL).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    definitions = c619.extract_between(zcull, '\t\t// REWINDBOX_ZCULL_ON_DEMAND_619 (ios/IOSZcullOnDemand.h)\n', '#endif\n\n\t\t// Conditional rendering helpers')
    sync_entry = c619.extract_between(zcull, 'void ZCULL_control::sync(::rsx::thread* ptimer)\n\t\t{\n#ifdef RPCS3_IOS\n', '#endif\n\t\t\tif (m_pending_writes.empty())')
    pass_scope = c619.extract_between(zcull, '// REWINDBOX_ZCULL_ON_DEMAND_619: mark the pass (lever only), cleared on every exit.\n', '\n#endif\n\t\t\t// Quick reverse scan')
    fault_entry = c619.extract_between(zcull, '\t\t\t\t// Already faulted, no locks possible\n\t\t\t\treturn false;\n\t\t\t}\n\n#ifdef RPCS3_IOS\n',
                                       '#endif\n\n\t\t\tbool need_disable_optimizations = false;')
    require('rpcs3::ios::get_experimental_policy().zcull_wait_guard && m_ios_demand.record_wait(now - started, now)' in definitions,
            'the wait rules run only with the guard on')
    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-pthread']
    tsan = ['-fsanitize=thread'] + (['-Wno-tsan'] if 'clang' not in Path(cxx).name else [])
    sets = {'plain': []}
    if sanitize:
        sets.update({'tsan': tsan, 'asan': ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']})
    report = {}
    for label, extra in sets.items():
        out = c619.compile_and_run(work, 'zcull627_' + label,
                                   {'main.cpp': fault_harness_627(), 'definitions.inc': definitions, 'sync_entry.inc': sync_entry,
                                    'pass_scope.inc': pass_scope, 'fault_entry.inc': fault_entry},
                                   [cxx], flags + extra, [source / 'rpcs3'])
        lines = out.strip().splitlines()
        guard, protocol, guard621 = json.loads(lines[-3]), json.loads(lines[-2]), json.loads(lines[-1])
        require(guard['guard627'] == 4 and guard['guard627_reads'] >= 6, f'627 guard scenarios ({label}): ' + repr(guard))
        require(protocol['failures'] == 0 and protocol['scenarios'] == 18, f'zcull fault protocol ({label}): ' + repr(protocol))
        require(guard621['failures'] == 0 and guard621['trip_lines'] == 2, f'621 rules with the guard on ({label}): ' + repr(guard621))
        report[label] = {'guard627': guard, 'protocol': protocol, 'guard621': guard621}
    return report


def spin_block(source: Path) -> str:
    text = (source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_text('utf-8', 'surrogateescape')
    body = c619.extract_between(text, '// the reservation notifier of this line, while the line is as this thread read it.\n',
                                '#endif\n\t\t\traddr = 0;\n\t\t\treturn true;')
    require('if (rpcs3::ios::get_experimental_policy().spu_noop_spin_wait)' in body, 'the polling block')
    return body


def run_spin(source: Path, cxx: str, work: Path, sanitize: bool) -> dict:
    folder = work / 'spin'
    folder.mkdir()
    (folder / 'spin_block.inc').write_text(spin_block(source), 'utf-8', 'surrogateescape')
    binary = folder / 'spin'
    include = [source / 'rpcs3', folder]
    plain = ['-O2', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers']
    core621.build(cxx, [HERE / 'spin_wait_test.cpp'], binary, include, plain)
    output = core621.execute([str(binary)], 'polling block (plain)')
    report = json.loads(output.strip().splitlines()[-1])
    require(report['failures'] == 0 and report['scenarios'] == 13, 'polling block: ' + repr(report))
    if sanitize:
        core621.build(cxx, [HERE / 'spin_wait_test.cpp'], folder / 'spin_tsan', include, ['-O1', '-g', '-fsanitize=thread'])
        core621.execute([str(folder / 'spin_tsan')], 'polling block (TSan)')
        core621.build(cxx, [HERE / 'spin_wait_test.cpp'], folder / 'spin_asan', include,
                      ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=undefined'])
        core621.execute([str(folder / 'spin_asan')], 'polling block (ASan/UBSan)')
    return report


def check_rule_one() -> dict:
    """Rule 1 of the task: no new counter, no new COREPROF tag, no new log line but one per boot."""
    added = [line[1:] for line in DELTA.read_text('utf-8', 'surrogateescape').splitlines()
             if line.startswith('+') and not line.startswith('+++')]
    code = [line for line in added if not line.lstrip().startswith('//') and not line.lstrip().startswith('#')]
    logs = [line for line in code if re.search(r'\.(notice|warning|error|success|fatal)\(', line)]
    require(len(logs) == 1 and 'Resolved title policy 627:' in logs[0], 'log calls added by Core 627: ' + repr(logs))
    require(not any('COREPROF ' in line for line in code), 'a COREPROF format added by Core 627')
    counters = [line for line in code if re.search(r'std::atomic<|atomic_t<u\d+>\s+\w+\{|fetch_add\(', line)]
    require(not counters, 'a counter added by Core 627: ' + repr(counters))
    return {'added_lines': len(added), 'log_calls': len(logs)}


def check_wiring(source: Path) -> dict:
    text = lambda name: (source / name).read_bytes().replace(b'\r\n', b'\n').decode('utf-8', 'surrogateescape')
    config, settings = text('rpcs3/Emu/system_config.h'), text('rpcs3/ios/RPCS3IOSSettings.cpp')
    policy, policy_h = text('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'), text('rpcs3/ios/RPCS3IOSExperimentalPolicy.h')
    boot = text('rpcs3/ios/RPCS3IOSBootDiagnostics.h')
    menu = (CLASSES / 'Rpcs3SessionMenu.mm').read_text()
    plugin = (CLASSES / 'Rpcs3InternalBridgePlugin.mm').read_text()
    l10n = (CLASSES / 'RPCS3InGameLocalization.mm').read_text()
    system = text('rpcs3/Emu/System.cpp')
    require('append_text(line, "levers627", rsx.levers627, 8);' in boot and 'ios_rsx.levers627 = ios_levers627;' in system, 'CONFIG_LAYERS levers627=')
    require(re.search(r'\s+'.join(rf'ios_add_lever\(ios_levers\.{key}, ios_lever_settings\.{key}\);' for key in SETTINGS), system),
            'levers627= digits in the order of the settings')
    require("'0' + (lever ? 1 : 0) + (setting.get() != ios_experimental_mode::automatic ? 2 : 0)" in system, 'levers627= digit: on, plus an explicit value')
    require('label = (digit & 1) ? @"enabled" : @"disabled";' in menu and 'explicitValue = (digit & 2) != 0;' in menu and
            '(explicitValue || [overrides containsObject:key]) ? @"testSourceTest"' in menu, 'the test page reads both bits of the digit')
    for bit, (key, (name, label)) in enumerate(SETTINGS.items()):
        require(f'cfg::_enum<ios_experimental_mode> {key}{{ this, "{name}", ios_experimental_mode::automatic }};' in config, 'setting ' + key)
        require(settings.count(f'GAME_SETTING("experimental.{key}", "Experimental"') == 1 and
                f'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.{key}, 0, 0, 0)' in settings, 'catalogue ' + key)
        require(f'bool {key} = ' in policy_h, 'policy field ' + key)
        require(f'@{{@"key": @"experimental.{key}", @"title": @"{label}", @"field": @"levers627", @"bit": @{bit},\n' in menu, 'test page ' + key)
        require(f'@"experimental.{key}": @[@"Enabled", @"Disabled"]' in plugin, 'test page whitelist ' + key)
    table = l10n[l10n.index('Build627Translations() {'):l10n.index('NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build621Translations() {')]
    locales = re.findall(r'^      @"(\w+)": @\{$', table, re.M)
    require(sorted(locales) == sorted(LOCALES), 'locales of the test page rows: ' + repr(locales))
    chunks = re.split(r'^      @"\w+": @\{$', table, flags=re.M)[1:]
    english = {}
    for locale, chunk in zip(locales, chunks):
        values = dict(re.findall(r'@"(test\w+)": @"([^"]+)"', chunk))
        require(set(values) == {label for _, label in SETTINGS.values()}, 'test page rows in ' + locale)
        if locale == 'en':
            english = values
    for locale, chunk in zip(locales, chunks):
        if locale == 'en':
            continue
        values = dict(re.findall(r'@"(test\w+)": @"([^"]+)"', chunk))
        same = [key for key in values if values[key] == english[key]]
        require(not same, f'{locale} keeps English text: {same}')
    lookup = l10n[l10n.index('NSString* RPCS3LocalizedString('):]
    require(lookup.index('build627[locale][key]') < lookup.index('build621[locale][key]'), 'the 627 table is read')

    # Defaults per title.
    for needle in ('resolved.zcull_wait_guard = resolve_mode(g_cfg.ios_experimental.zcull_wait_guard,\n\t\t!rpcs3::ios::title_levers::requires_zcull_on_demand(title_id));',
                   'resolved.zcull_cond_no_wait = resolve_mode(g_cfg.ios_experimental.zcull_cond_no_wait,\n\t\trpcs3::ios::title_levers::requires_zcull_on_demand(title_id));',
                   'resolved.zcull_conservative_reports = resolve_mode(g_cfg.ios_experimental.zcull_conservative_reports, false) &&\n\t\t!g_cfg.core.rsx_accurate_res_access;',
                   'rpcs3::ios::title_levers::wants_spu_noop_spin_wait(title_id) || is_god_of_war_iii_title(title_id));',
                   'resolved.light_measurement = resolve_mode(g_cfg.ios_experimental.light_measurement, false);',
                   'resolved.gpu_timing = !resolved.light_measurement && resolve_mode(g_cfg.ios_experimental.gpu_timing, true);'):
        require(needle in policy, 'policy: ' + needle[:60])
    require(policy.count('Resolved title policy 627:') == 1, 'the one boot line')

    # ZCULL.
    zcull = text('rpcs3/Emu/RSX/RSXZCULL.cpp')
    read_report = zcull[zcull.index('void ZCULL_control::read_report('):zcull.index('void ZCULL_control::allocate_new_query(')]
    require(read_report.index('on_report_enqueued(sink);') < read_report.index('write(sink, ptimer->timestamp(), type, 1u);') <
            read_report.index('ptimer->async_tasks_pending++;'), 'conservative report written once queued')
    enqueued = zcull[zcull.index('void ZCULL_control::on_report_enqueued('):zcull.index('void ZCULL_control::on_report_completed(')]
    require(enqueued.index('zcull_conservative_reports') < enqueued.index('m_locked_pages'), 'a conservative report locks no page')
    barrier = zcull[zcull.index('flags32_t ZCULL_control::read_barrier(::rsx::thread* ptimer, u32 memory_address, u32 memory_range'):]
    require(barrier.index('if (!rpcs3::ios::get_experimental_policy().zcull_conservative_reports)') < barrier.index('disable_optimizations(ptimer, location1);') <
            barrier.index('update(ptimer, sync_address);'), 'an RSX copy does not leave the conservative mode, and still waits for its reports')
    copies = zcull[zcull.index('u32 ZCULL_control::copy_reports_to('):zcull.index('void ZCULL_control::on_report_enqueued(')]
    require(copies.index('writer.sink_alias.push_back(vm::cast(address));') < copies.index('zcull_conservative_reports') < copies.index('return 0;') <
            copies.index('return bytes_to_write;'), 'a conservative block transfer runs now and its aliases keep the GPU result')
    thread = text('rpcs3/Emu/RSX/RSXThread.cpp')
    require('rpcs3::ios::get_experimental_policy().zcull_cond_no_wait && rsx::method_registers.depth_test_enabled() &&\n'
            '\t\t\t\t\t\trsx::method_registers.depth_func() != rsx::comparison_function::always);' in thread,
            'conditional render setting, only for a draw the depth test can hide')

    # SPU.
    spu = text('rpcs3/Emu/Cell/SPUThread.cpp')
    putllc_at = spu.index('bool spu_thread::do_putllc(const spu_mfc_cmd& args)')
    putllc = spu[putllc_at:spu.index('void do_cell_atomic_128_store(', putllc_at)]
    require(putllc.index('if (raddr != addr)') < putllc.index('const bool unchanged =') < putllc.index('t_ios_noop_spin.on_noop(') <
            putllc.index('raddr = 0;') < putllc.index('t_ios_noop_spin.on_progress();') < putllc.index('auto& res = vm::reservation_acquire(addr);'),
            'the wait is in the no-op path, reached with raddr == addr, before raddr is cleared and before any lock')
    require(spu.count('t_ios_noop_spin') == putllc.count('t_ios_noop_spin') + 1, 'the tracker is only used by do_putllc')
    require('static thread_local rpcs3::ios::spu_noop_spin::tracker t_ios_noop_spin;' in spu, 'the tracker is not a member')

    # QoS, canary, FIFO, light profile.
    thread_cpp = text('Utilities/Thread.cpp')
    require('level.utility ? QOS_CLASS_UTILITY : level.user_initiated ? QOS_CLASS_USER_INITIATED : QOS_CLASS_USER_INTERACTIVE' in thread_cpp, 'QoS class')
    cpu = text('rpcs3/Emu/CPU/CPUThread.cpp')
    require('get_class() == thread_class::spu && rpcs3::ios::get_experimental_policy().spu_qos_below_rsx' in cpu, 'SPU QoS at thread start')
    # REWINDBOX_MVK_ASYNC_RETRY_926: a later Core names a new record (its second try); the rule is unchanged.
    canary = text('rpcs3/ios/IOSMoltenVKAsyncCanary.h')
    require('file_name = "rewindbox-mvk-async-627.txt"' in canary or 'file_name = "rewindbox-mvk-async-926.txt"' in canary, 'canary record of this Core')
    fifo = text('rpcs3/Emu/RSX/RSXFIFO.cpp')
    nop = fifo[fifo.index('case FIFO::FIFO_NOP:'):fifo.index('case FIFO::FIFO_EMPTY:')]
    require('performance_counters.state == FIFO::state::running && !rpcs3::ios::get_experimental_policy().fifo_nop_fast_path' in nop and
            'fifo_ctrl->sync_get_force();' in nop, 'the NOP path keeps publishing GET')
    performance = text('rpcs3/ios/RPCS3IOSPerformance.cpp')
    window = performance[performance.index('void report_profile_window()'):]
    require(window.index('if (ios_light && ios_channel_level > logs::level::warning)') <
            window.index('ios_core_profiler.enabled.release(logs::level::warning);') <
            window.index('ios_core_profiler.enabled.release(ios_channel_level); // REWINDBOX_LIGHT_MEASUREMENT_627') <
            window.index('"COREPROF frames=%llu avg_fps=%.3f'), 'only the synthesis line is emitted in a light run')
    require(window.count('ios_core_profiler.enabled.release(') == 2 and performance.count('ios_core_profiler.enabled.release(') == 2,
            'the channel is lowered in a light run only, for this report only, and gets the boot level back')
    require('!rpcs3::ios::get_experimental_policy().light_measurement);' in performance and
            'if (result.dump && !rpcs3::ios::get_experimental_policy().light_measurement &&' in performance, 'signal trace and dumps')
    require('!rpcs3::ios::get_experimental_policy().light_measurement; // REWINDBOX_LIGHT_MEASUREMENT_627' in thread, 'frame stages')
    return {'settings': sorted(SETTINGS), 'locales': sorted(LOCALES)}


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
    with tempfile.TemporaryDirectory(prefix='core627-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source, work)
        print('rule 1: observation added by the increment')
        report['rule_one'] = check_rule_one()
        print('wiring')
        report['wiring'] = check_wiring(source)
        print('polling block')
        report['polling'] = run_spin(source, args.cxx, work, sanitize)
        print('zcull fault protocol on the Core 627 tree')
        report['zcull'] = run_fault_protocol(source, args.cxx, work, sanitize)
        print('core 624 suite on the reverted tree')
        tree = core624_tree(source, work)
        command = [sys.executable, str(ROOT / 'test/rpcs3_core624_test.py'), '--source', str(tree), '--cxx', args.cxx,
                   '--report', str(work / 'core624.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5400)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 624' in result.stdout, 'the Core 624 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core624'] = json.loads((work / 'core624.json').read_text())
    print('PASS: Core 627 increment reverts to Core 624; the Core 624 suite on that tree; rule 1; wiring in 12 locales; '
          'the real polling block and the real ZCULL fault protocol')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
