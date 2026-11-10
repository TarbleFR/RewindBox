#!/usr/bin/env python3
"""ZCULL part of the Core 621 test (imported by test/rpcs3_core621_test.py).

Build 620 logs (2 November 2026, PIDs 66891/66907/66957, Core 619):
- Assassin's Creed: the 619 on-demand lever served the menus, then tripped its
  wait budget in the first gameplay second (54 reads, 401.5 ms against 400 ms in
  one second); the boot then ran upstream: 2,100-2,900 GPU syncs and 3.4-4.3 s
  of the RSX thread blocked per 5 s window, 14-18 FPS.
- Black Ops II: the upstream switch at every boot (upstream_disables=1:0:0),
  then 200-390 GPU syncs, 1.1-1.9 s per 5 s multiplayer window, 20-35 FPS.

REWINDBOX_ZCULL_DEMAND_GUARD_621 changes the trip rule, REWINDBOX_ZCULL_DEMAND_BO2_621
adds Black Ops II and the per-game setting, REWINDBOX_ZCULL_FRAME_621 puts the
ZCULL waits of each slow frame in FRAMECAUSE_EVENT (cause_rule=v2). This module:
- runs test/rpcs3_core621/zcull_guard_test.cpp (the gate's rules) plain, TSan, ASan/UBSan;
- runs the Core 619 fault-protocol harness (the real ios_on_demand_fault,
  ios_retire_claimed, ios_release_stale_pages, ios_log_trip, the real sync() and
  on_access_violation entry blocks against a ZCULL/RSX mock) on the 621 sources,
  its one-second budget scenario replaced by the 621 ones: the Build 620 second
  (just above 400 ms) keeps the lever, three sustained seconds trip it once with
  one COREPROF ZCULLTRIP621 line;
- checks the ZCULLDEMAND619 line (printf-checked, -Wformat=2) with its 621 fields,
  the title levers, the setting, the policy, CONFIG_LAYERS and the frame wiring.
Host checks only; no iPhone, no FPS claim.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core621'


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c619 = _module('rpcs3_core619_test_for_621', ROOT / 'test/rpcs3_core619_test.py')


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def replace_once(text: str, old: str, new: str, what: str) -> str:
    require(text.count(old) == 1, f'619 harness anchor ({what}) found {text.count(old)} times')
    return text.replace(old, new)


BUDGET_621 = r'''	unsigned budget_faults = 0, transient_faults = 0, storm_faults = 0;
	int guard_trip_lines = 0;
	{ // REWINDBOX_ZCULL_DEMAND_GUARD_621, Build 620 (Assassin's Creed, first gameplay second): served
	  // reads of about 7 ms, just above 400 ms in one second, then quiet: the lever stays on.
		ZCULL_control z;
		rsx_server server(z, 7);
		const int lines_before = rsx_log.trip_lines.load();
		take(tally.wait_us);
		const auto start = get_system_time();
		u64 total = 0;
		while (total <= od::wait_budget_us + 2'000 && get_system_time() - start < 950'000)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
			total += take(tally.wait_us);
			transient_faults++;
		}
		CHECK(total > od::wait_budget_us && !z.m_ios_demand.tripped() && tally.tripped.load() == 0 && z.upstream_paths.load() == 0);
		std::this_thread::sleep_for(std::chrono::milliseconds(2'200));
		for (int i = 0; i < 3; i++)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
		}
		CHECK(!z.m_ios_demand.tripped() && z.upstream_paths.load() == 0 && rsx_log.trip_lines.load() == lines_before);
		take(tally.faults_report); take(tally.services); take(tally.waits); take(tally.wait_us);
		scenarios++;
	}
	{ // REWINDBOX_ZCULL_DEMAND_GUARD_621: one guest thread above 400 ms in 3 consecutive seconds (50 ms
	  // services, 45 ms of work between reads: about 10 reads and 500 ms per second, not a storm) trips at
	  // the first wait of the 4th second, wait_budget scope thread, with one COREPROF ZCULLTRIP621 line.
	  // The macOS runner sleeps longer than asked (Core 621 Apple run 41550627637: 21 reads, about 7 per
	  // second, windows 532/481/467 ms; run 41556537325: 15), so the read count only has to show at least
	  // two reads per second. Seconds are buckets of the clock: the first one is partial.
		ZCULL_control z;
		rsx_server server(z, 50);
		const int lines_before = rsx_log.trip_lines.load();
		tally.pickups = 0; tally.pickup_us = 0; tally.pickup_max_us = 0;
		const auto start = get_system_time();
		while (!z.m_ios_demand.tripped() && get_system_time() - start < 20'000'000)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
			budget_faults++;
			std::this_thread::sleep_for(std::chrono::milliseconds(45));
		}
		const auto elapsed = get_system_time() - start;
		const auto trip = z.m_ios_demand.trip_record();
		CHECK(z.m_ios_demand.tripped() && trip.reason == static_cast<u32>(od::trip_reason::wait_budget) && trip.scope == 1);
		CHECK(trip.windows_us[0] > od::wait_budget_us && trip.windows_us[1] > od::wait_budget_us && trip.windows_us[2] > od::wait_budget_us);
		// Core 665 Apple run 42067129517 (attempt 2, the Core 624 tree): on a loaded runner the trip came after
		// 8 s, with windows 587/494/511 ms, so the bound is 20 s; the trip reason, windows and read count
		// checks are unchanged.
		CHECK(elapsed >= 2'000'000 && elapsed < 20'000'000 && budget_faults >= 6); // the first bucket can be nearly whole
		CHECK(rsx_log.trip_lines.load() == lines_before + 1 && tally.tripped.load() == static_cast<u32>(od::trip_reason::wait_budget));
		CHECK(tally.pickups.load() >= 6 && tally.pickup_max_us.load() >= 40'000);
		guard_trip_lines += rsx_log.trip_lines.load() - lines_before;
		z.enqueue(address);
		CHECK(guest_access(z, address, thread_class::ppu) && z.upstream_paths.load() == 1);
		take(tally.faults_report); take(tally.services); take(tally.waits);
		scenarios++;
	}
	{ // REWINDBOX_ZCULL_DEMAND_GUARD_621: reads back to back, 5 ms each (a storm: the thread is blocked
	  // almost the whole second): wait_severe in one of the first seconds, before the 3-second rule could
	  // trip, one ZCULLTRIP621 line. The macOS runner stretches each read with its sleeps (Apple runs
	  // 41550627637, 41551302366 and 41552807852: 60 ms reads became about 70 ms, 30 ms about 57 ms, 15 ms
	  // up to about 70 ms under ASan), so the reads are short enough for 16 of them to fit in a second, and
	  // the bound is the 3-second rule (the trip reason), not one second of wall clock.
		ZCULL_control z;
		rsx_server server(z, 5);
		const int lines_before = rsx_log.trip_lines.load();
		const auto start = get_system_time();
		while (!z.m_ios_demand.tripped() && get_system_time() - start < 3'000'000)
		{
			z.enqueue(address);
			CHECK(guest_access(z, address, thread_class::ppu));
			storm_faults++;
		}
		const auto trip = z.m_ios_demand.trip_record();
		CHECK(trip.reason == static_cast<u32>(od::trip_reason::wait_severe) && trip.scope == 1 && trip.windows_us[2] > od::severe_wait_us);
		CHECK(storm_faults >= od::severe_min_waits && get_system_time() - start < 3'500'000);
		CHECK(rsx_log.trip_lines.load() == lines_before + 1);
		guard_trip_lines += rsx_log.trip_lines.load() - lines_before;
		take(tally.faults_report); take(tally.services); take(tally.waits);
		scenarios++;
	}
'''


# REWINDBOX_ZCULL_FAULT_CENSUS_624: the Core 624 fault path counts into ios/IOSZcullLabelPage.h;
# run() sets this when the tree under test carries that header.
WITH_LABEL_PAGE_HEADER = False


def fault_harness_621() -> str:
    text = c619.FAULT_HARNESS
    if WITH_LABEL_PAGE_HEADER:
        text = replace_once(text, '#include "ios/IOSZcullOnDemand.h"\n',
                            '#include "ios/IOSZcullOnDemand.h"\n#include "ios/IOSZcullLabelPage.h"\n', 'Core 624 header')
    text = replace_once(text, '#include <cstdio>\n', '#include <cstdio>\n#include <cstring>\n', 'includes')
    text = replace_once(
        text,
        '\tstd::atomic<int> warnings{0}, errors{0};\n',
        '\tstd::atomic<int> warnings{0}, errors{0}, notices{0}, trip_lines{0};\n'
        '\ttemplate <typename... Args> void notice(const char* format, Args... args) { notices++; '
        'if (std::strstr(format, "COREPROF ZCULLTRIP621")) trip_lines++; std::printf("[notice] "); '
        'std::printf(format, args...); std::printf("\\n"); }\n',
        'log mock')
    text = replace_once(text, '\tbool ios_page_locked(u32 address);\n',
                        '\tbool ios_page_locked(u32 address);\n\tvoid ios_log_trip() const;\n', 'mock members')
    # Harness timing (not product behaviour): a guest is released once the forced pass cleared its page,
    # which can be just before the RSX thread counts the service; let the two served checks see it.
    settle = '\t\tfor (int i = 0; i < 1000 && tally.services.load() == 0; i++) std::this_thread::sleep_for(std::chrono::milliseconds(1));\n'
    text = replace_once(text, '\t\tCHECK(take(tally.faults_report) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && !z.m_pages_accessed[1]);\n',
                        settle + '\t\tCHECK(take(tally.faults_report) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && !z.m_pages_accessed[1]);\n',
                        'first served check')
    text = replace_once(text, '\t\tCHECK(take(tally.faults_label) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && z.upstream_paths.load() == 0);\n',
                        settle + '\t\tCHECK(take(tally.faults_label) == 1 && take(tally.services) >= 1 && take(tally.waits) == 1 && z.upstream_paths.load() == 0);\n',
                        'label served check')
    # The previous (concurrent) scenario's RSX thread can count its last service after that scenario's
    # takes; its server is joined here, so drain the leftover before the RSX copy path counts one service.
    text = replace_once(text, '\t\tconst auto ticket = z.m_ios_demand.request();\n\t\tz.ios_retire_claimed(&rsx::g_thread);\n',
                        '\t\ttake(tally.services); // the previous scenario\'s RSX thread can count its last service late\n'
                        '\t\tconst auto ticket = z.m_ios_demand.request();\n\t\tz.ios_retire_claimed(&rsx::g_thread);\n',
                        'RSX copy path settle')
    start = text.index('\tunsigned budget_faults = 0;\n\t{ // guest waits above 400 ms in one second trip')
    end = text.index('\tunsigned concurrent = 0, concurrent_tripped = 0;')
    text = text[:start] + BUDGET_621 + text[end:]
    text = replace_once(
        text,
        '\t\t\tCHECK(tally.tripped.load() == static_cast<u32>(od::trip_reason::wait_budget));\n',
        '\t\t\tCHECK(tally.tripped.load() == static_cast<u32>(od::trip_reason::wait_budget) ||\n'
        '\t\t\t\ttally.tripped.load() == static_cast<u32>(od::trip_reason::wait_severe));\n',
        'concurrent trip reason')
    text = replace_once(
        text,
        '\treturn failures != 0;\n}\n',
        '\tstd::printf("{\\"failures\\": %d, \\"transient_faults\\": %u, \\"budget_faults\\": %u, \\"storm_faults\\": %u, \\"trip_lines\\": %d}\\n",\n'
        '\t\tfailures, transient_faults, budget_faults, storm_faults, guard_trip_lines);\n'
        '\treturn failures != 0;\n}\n',
        'summary line')
    return text


LEVERS_621 = r'''
#include "ios/IOSTitleLevers.h"
namespace levers = rpcs3::ios::title_levers;
// REWINDBOX_ZCULL_DEMAND_BO2_621: Assassin's Creed and Black Ops II, nothing else.
static_assert(levers::requires_zcull_on_demand("BLES00158") && levers::requires_zcull_on_demand("BLUS30089"));
static_assert(levers::requires_zcull_on_demand("BLES01717"));
static_assert(!levers::requires_zcull_on_demand("BCES00510") && !levers::requires_zcull_on_demand("BLUS30591") &&
	!levers::requires_zcull_on_demand(""));
int main() { return 0; }
'''


def run(source: Path, compiler: list[str], flag_sets: dict[str, list[str]], work: Path, sanitize: bool) -> dict:
    global WITH_LABEL_PAGE_HEADER
    WITH_LABEL_PAGE_HEADER = (source / 'rpcs3/ios/IOSZcullLabelPage.h').exists()
    rpcs3 = source / 'rpcs3'
    report: dict = {}

    # 1. The gate's rules.
    guard = {}
    for label, flags in flag_sets.items():
        if label != 'plain' and not sanitize:
            continue
        out = c619.compile_and_run(work, 'zcull_guard_' + label, {'main.cpp': (HERE / 'zcull_guard_test.cpp').read_text()},
                                   compiler, ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-pthread'] + flags, [rpcs3])
        result = json.loads(out.strip().splitlines()[-1])
        require(result['failures'] == 0 and result['scenarios'] == 16, f'zcull guard ({label}): ' + repr(result))
        guard[label] = result
    report['guard'] = guard

    # 2. The real fault protocol of the 621 sources, 621 budget scenarios.
    zcull = (source / c619.ZCULL).read_text()
    definitions = c619.extract_between(zcull, '\t\t// REWINDBOX_ZCULL_ON_DEMAND_619 (ios/IOSZcullOnDemand.h)\n', '#endif\n\n\t\t// Conditional rendering helpers')
    sync_entry = c619.extract_between(zcull, 'void ZCULL_control::sync(::rsx::thread* ptimer)\n\t\t{\n#ifdef RPCS3_IOS\n', '#endif\n\t\t\tif (m_pending_writes.empty())')
    pass_scope = c619.extract_between(zcull, '// REWINDBOX_ZCULL_ON_DEMAND_619: mark the pass (lever only), cleared on every exit.\n', '\n#endif\n\t\t\t// Quick reverse scan')
    fault_entry = c619.extract_between(zcull, '\t\t\t\t// Already faulted, no locks possible\n\t\t\t\treturn false;\n\t\t\t}\n\n#ifdef RPCS3_IOS\n',
                                       '#endif\n\n\t\t\tbool need_disable_optimizations = false;')
    require('void ZCULL_control::ios_log_trip() const' in definitions and 'COREPROF ZCULLTRIP621' in definitions,
            'ios_log_trip is among the on-demand definitions')
    require(definitions.count('ios_log_trip();') == 3, 'every trip site logs the trip (wait budget/severe, storm, pickup/hard)')
    require('&picked_at);' in definitions and 'tally.add_halves(pickup_sum, service_sum + (now - halves_at));' in definitions,
            'the served wait is split into pickup and service, over every request of the fault')
    fault_flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-pthread']
    faults = {}
    for label, flags in flag_sets.items():
        if label != 'plain' and not sanitize:
            continue
        out = c619.compile_and_run(work, 'zcull_fault_' + label,
                                   {'main.cpp': fault_harness_621(), 'definitions.inc': definitions, 'sync_entry.inc': sync_entry,
                                    'pass_scope.inc': pass_scope, 'fault_entry.inc': fault_entry},
                                   compiler, fault_flags + [f for f in flags if f.startswith('-fsanitize') or f == '-fno-sanitize-recover=all'], [rpcs3])
        lines = out.strip().splitlines()
        protocol, guard621 = json.loads(lines[-2]), json.loads(lines[-1])
        require(protocol['failures'] == 0 and protocol['scenarios'] == 18 and protocol['concurrent_accesses'] == 600,
                f'zcull fault protocol ({label}): ' + repr(protocol))
        require(guard621['failures'] == 0 and guard621['trip_lines'] == 2 and guard621['transient_faults'] >= 1 and guard621['budget_faults'] >= 6 and guard621['storm_faults'] >= 16,
                f'zcull 621 budget scenarios ({label}): ' + repr(guard621))
        trip_line = next((line for line in lines if 'COREPROF ZCULLTRIP621 reason=wait_budget' in line), '')
        require(re.search(r'COREPROF ZCULLTRIP621 reason=wait_budget scope=thread windows_ms=\d+\.\d:\d+\.\d:\d+\.\d at_us=\d+ '
                          r'rule=thread400ms_x3:all800ms_x3:severe900ms_16waits:storm1000:pickup2000ms:hard5000ms mode_after=upstream_for_boot', trip_line),
                'ZCULLTRIP621 line: ' + trip_line)
        faults[label] = {'protocol': protocol, 'guard621': guard621, 'trip_line': trip_line.replace('[notice] ', '')}
    report['fault_protocol'] = faults

    # 3. The profiler line (printf-checked) and its 621 fields.
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    block = c619.extract_between(perf, '        // REWINDBOX_ZCULL_ON_DEMAND_619: guest accesses to report pages', '        // REWINDBOX_SPU_OBJECT_PREFETCH_616')
    block = block[block.index('\n        {\n') + 1:]
    out = c619.compile_and_run(work, 'zcull_probe', {'main.cpp': c619.PROBE_HARNESS, 'probe.inc': block}, compiler,
                               ['-std=gnu++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wformat=2', '-pthread'], [rpcs3])
    line = out.strip().splitlines()[-1]
    require(line.startswith('COREPROF ZCULLDEMAND619 session=1 window=20 tuple=count:total_ms:max_ms enabled=1 tripped=2 faults=20:10:1 ') and
            line.endswith(' pickup=0:0.000:0.000 service=0:0.000:0.000 tripped_name=wait_budget '
                          'guard621=thread400ms_x3:all800ms_x3:severe900ms_16waits'),
            'ZCULLDEMAND619 line: ' + line)
    report['probe_line'] = line

    # 4. Title levers, setting, policy, CONFIG_LAYERS, frame wiring.
    c619.compile_and_run(work, 'zcull_levers', {'main.cpp': LEVERS_621}, compiler, ['-std=c++20', '-Wall', '-Wextra', '-Werror'], [rpcs3])
    text = lambda name: (source / name).read_text()
    config = text('rpcs3/Emu/system_config.h')
    policy = text('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp')
    settings = text('rpcs3/ios/RPCS3IOSSettings.cpp')
    boot = text('rpcs3/ios/RPCS3IOSBootDiagnostics.h')
    system = text('rpcs3/Emu/System.cpp')
    require('cfg::_enum<ios_experimental_mode> zcull_on_demand{ this, "ZCULL On-Demand Reads", ios_experimental_mode::automatic };' in config,
            'ZCULL On-Demand Reads setting (Automatic)')
    require('resolved.zcull_on_demand = resolve_mode(g_cfg.ios_experimental.zcull_on_demand,\n'
            '\t\trpcs3::ios::title_levers::requires_zcull_on_demand(title_id));' in policy, 'policy: Automatic is the title list')
    require('GAME_SETTING("experimental.zcull_on_demand", "Experimental", "ZCULL", "ZCULL on-demand reads"' in settings and
            'kind::RPCS3_IOS_SETTING_CHOICE, g_cfg.ios_experimental.zcull_on_demand' in settings, 'per-game setting entry')
    require('"experimental.zcull_on_demand", // REWINDBOX_ZCULL_DEMAND_BO2_621' in boot and
            'append_u32(line, "zcull_demand", rsx.zcull_demand ? 1u : 0u);' in boot, 'CONFIG_LAYERS part=rsx zcull_demand=')
    require('ios_rsx.zcull_demand = rpcs3::ios::get_experimental_policy().zcull_on_demand;' in system, 'CONFIG_LAYERS value is the resolved policy')
    frame = text('rpcs3/ios/IOSFrameTrace.h')
    query = text('rpcs3/Emu/RSX/VK/VKQueryPool.cpp')
    timing = text('rpcs3/ios/IOSGpuTiming.h')
    require('std::uint64_t zcull_ticks = 0, zcull_waits = 0;' in frame, 'frame waits carry the ZCULL wait')
    require('ios_frame_waits.zcull_ticks += ios_wait_ticks;' in query and 'ios_frame_waits.zcull_waits++;' in query and
            query.index('rpcs3::ios::rsx_sync::record_zcull_wait(ios_wait_ticks);') < query.index('ios_frame_waits.zcull_ticks += ios_wait_ticks;'),
            'the ZCULLWAIT616 probe point feeds the frame')
    require('{"zcull_sync", zcull_ms},' in timing and 'double submit_ms, double semaphore_ms, double zcull_ms, const frame_view& gpu' in timing,
            'cause_rule v2 candidate')
    require('zcull_wait_ms=%.3f zcull_waits=%llu' in perf and 'cause_rule=v2' in perf and 'cause_rule=v1' not in perf and
            'wait_ms(frame.waits.zcull_ticks), gpu_frame);' in perf, 'FRAMECAUSE_EVENT zcull fields and rule v2')
    report['levers'] = {'zcull_on_demand': ['BLES00158', 'BLUS30089', 'BLES01717'], 'setting': 'experimental.zcull_on_demand'}
    return report
