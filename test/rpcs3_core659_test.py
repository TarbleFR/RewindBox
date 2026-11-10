#!/usr/bin/env python3
"""Host tests of RPCS3 Core 659 = Core 655 + build-utils/rpcs3/core659-from-655.patch.

Core 659 (iOS; IPA 657 logs, Core 655, PID 10471):
- REWINDBOX_EARLY_SUBMIT_BOUNDARY_659: Assassin's Creed and Black Ops II join the Automatic mode of early command
  buffer submission (561) in a boundary mode. A submission decided at the end of a draw, once the GPU has drained, is
  armed and taken where no render pass is open: at the start of a later draw, or after its textures are prepared. If
  no such point comes within max_deferred_draws (32) more draws, it is taken at the end of a draw, as in 561. Any
  other primary submission carries the armed draws. Dragon Ball Z and God of War III keep the end-of-draw submission.
  COREPROF OPT561 gains the boundary counters; the boot logs "Resolved title policy 659".
- REWINDBOX_ZCULL_READ_LEAD_659: for each guest access that finds its ZCULL report slot pending, the age of the slot's
  oldest pending report (COREPROF ZCULLLEAD659). Counters only.
- REWINDBOX_ZCULL_HINT_SITES_659: the ZCULL_control site of each zcull_sync hint that submitted (COREPROF ZCULLHINT659).
  Counters only.
This driver:
- authenticates the increment against its record and reverts it to the pinned Core 655 files;
- checks the source: the decision and its calls, the policy, the reporters, the five hint sites, the lead measurement;
- compiles the changed iOS headers (page slots, tally, hint sites, title list) into a test under ASan and UBSan;
- runs test/rpcs3_early_submit_boundary659_test.py (real early-submission code of both trees, ASan and UBSan);
- runs the Core 655 suite on the reverted tree (which runs the 652, 651, 645, 641, 638, 636, 634, 630 and 627 suites).
No rendering, gameplay, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / 'build-utils/rpcs3/core659-from-655.patch'
RECORD = ROOT / 'build-utils/rpcs3/core659-delta.json'
FILES = ('rpcs3/Emu/RSX/RSXZCULL.cpp', 'rpcs3/Emu/RSX/VK/VKDraw.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.cpp',
         'rpcs3/Emu/RSX/VK/VKGSRender.h', 'rpcs3/ios/IOSEarlySubmit.h', 'rpcs3/ios/IOSRsxSyncProfile.h',
         'rpcs3/ios/IOSTitleLevers.h', 'rpcs3/ios/IOSZcullOnDemand.h', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp',
         'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp', 'rpcs3/ios/RPCS3IOSSettings.cpp')
NEW: tuple = ()
MARKS = ('REWINDBOX_EARLY_SUBMIT_BOUNDARY_659', 'REWINDBOX_ZCULL_READ_LEAD_659', 'REWINDBOX_ZCULL_HINT_SITES_659')
# The only lines Core 659 removes or rewrites (whitespace-stripped): the 561 submission body moves into
# ios_take_early_submit, the policy expression and the OPT561 format gain terms, one setting text, the slot add.
REMOVED = {
    'const u32 draws = m_ios_draws_since_submit;',
    'flush_command_queue();',
    'm_ios_early_submits_this_frame++;',
    'early::submits.fetch_add(1, std::memory_order_relaxed);',
    'early::submitted_draws.fetch_add(draws, std::memory_order_relaxed);',
    'rpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(title_id) || is_god_of_war_iii_title(title_id));',
    '"gpu_busy_checks=%llu frame_capped_checks=%llu min_draws=%u max_per_frame=%u "',
    'early::min_draws, early::max_per_frame);',
    'page.ios_slots.add(static_cast<u32>(address)); // REWINDBOX_ZCULL_ASYNC_READS_630',
}

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core655']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core659-from-655.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape').replace('\r\n', '\n')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == len(FILES) and
            increment['new_files'] == list(NEW) and increment['insertions_only'] is False, 'core659 files')
    removed = [line[1:].strip() for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    # The early submission setting is rewritten (its text names the new titles), never removed: same key, same kind.
    setting = 'SETTING("experimental.early_submit", "Experimental", "FPS Experiments", "Early command buffer submission", '
    old_setting = [line for line in removed if line.startswith('SETTING(')]
    new_setting = [line for line in added if line.startswith('SETTING(')]
    require(len(old_setting) == len(new_setting) == 1 and old_setting[0].startswith(setting) and new_setting[0].startswith(setting) and
            old_setting[0].split('", kind::')[1] == new_setting[0].split('", kind::')[1] and
            "Assassin's Creed and Call of Duty: Black Ops II" in new_setting[0], 'only the early submission setting text changes')
    other = [line for line in removed if not line.startswith('SETTING(')]
    require(set(other) <= REMOVED and len(removed) == increment['removed_lines'],
            'Core 659 removes only the listed lines: ' + repr(sorted(set(other) - REMOVED)[:3]))
    for mark in MARKS:
        require(any(mark in line for line in added), mark + ' is not marked')
    code = [line for line in added if line and not line.startswith('//')]
    for needle in ('switch (early::at_draw_end(m_ios_early_armed_draws ? ++m_ios_early_armed_draws : 0))',
                   'if (early::arm_instead(early::at_pass_boundary.load(std::memory_order_relaxed), vk::is_renderpass_open(*m_current_command_buffer)))',
                   'if (!early::take_at_boundary(m_ios_early_armed_draws, vk::is_renderpass_open(*m_current_command_buffer), interruptible))',
                   'rpcs3::ios::early_submit::disarmed.fetch_add(1, std::memory_order_relaxed);',
                   'ios_early_submit_at_boundary(false);', 'ios_early_submit_at_boundary(true);',
                   'rpcs3::ios::title_levers::early_submit_at_pass_boundary(title_id));',
                   'resolved.early_submit_at_pass_boundary = resolved.early_submit && rpcs3::ios::title_levers::early_submit_at_pass_boundary(title_id);',
                   'rpcs3::ios::early_submit::at_pass_boundary.store(resolved.early_submit_at_pass_boundary, std::memory_order_relaxed);',
                   'return is_assassins_creed_title(title_id) || is_black_ops_ii_title(title_id);',
                   'page.ios_slots.add_at(static_cast<u32>(address), get_system_time()); // REWINDBOX_ZCULL_ASYNC_READS_630, REWINDBOX_ZCULL_READ_LEAD_659',
                   'if (const u64 lead = found->second.ios_slots.pending_age_us(pending_slot, get_system_time()))'):
        require(any(needle in line for line in code), 'missing from the increment: ' + needle)
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 659 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code), 'removed_lines': len(removed)}


def method(source: str, start: str) -> str:
    require(source.count(start) == 1, 'not exactly one ' + start.strip()[:80])
    first = source.index(start)
    depth = 0
    for index in range(source.index('{', first), len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return source[first:index + 1]
    raise SystemExit('FAIL: unbalanced ' + start)


def check_source(source: Path) -> dict:
    read = lambda name: (source / name).read_text('utf-8', 'surrogateescape').replace('\r\n', '\n')
    zcull, render, policy, performance = (read('rpcs3/Emu/RSX/RSXZCULL.cpp'), read('rpcs3/Emu/RSX/VK/VKGSRender.cpp'),
                                          read('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'), read('rpcs3/ios/RPCS3IOSPerformance.cpp'))
    # Every zcull_sync hint names its site just before it, by the function it is in.
    sites = {'void ZCULL_control::sync(::rsx::thread* ptimer)\n': ['hint_sync'],
             'void ZCULL_control::update(::rsx::thread* ptimer, u32 sync_address, bool hint)\n': ['hint_queue_depth', 'hint_critical_age'],
             'flags32_t ZCULL_control::read_barrier(::rsx::thread* ptimer, u32 memory_address, u32 memory_range, flags32_t flags)\n': ['hint_read_barrier'],
             'void ZCULL_control::ios_service_read(::rsx::thread* ptimer)\n': ['hint_service_read']}
    hint = 'ptimer->sync_hint(FIFO::interrupt_hint::zcull_sync'
    require(zcull.count(hint) == 5, 'five zcull_sync hints in RSXZCULL.cpp')
    for signature, expected in sites.items():
        body = method(zcull, signature)
        found = []
        for at in [m.start() for m in re.finditer(re.escape(hint), body)]:
            before = body[:at].rstrip('\t').splitlines()
            require(before[-1] == '#endif' and before[-3] == '#ifdef RPCS3_IOS' and 'rpcs3::ios::rsx_sync::zcull_hint_site = rpcs3::ios::rsx_sync::' in before[-2],
                    'a zcull_sync hint without its site in ' + signature.strip())
            found.append(re.search(r'rsx_sync::(hint_\w+);', before[-2]).group(1))
        require(found == expected, signature.strip() + ': sites ' + repr(found))
    sync_hint = method(render, 'void VKGSRender::sync_hint(rsx::FIFO::interrupt_hint hint, rsx::reports::sync_hint_payload_t payload)\n')
    require(sync_hint.count('zcull_hint_site_flushes[rpcs3::ios::rsx_sync::zcull_hint_site % rpcs3::ios::rsx_sync::hint_site_count]') == 1 and
            sync_hint.index('zcull_hint_site_flushes') > sync_hint.index('flush_command_queue();'), 'the per-site count follows the hint flush')
    # The lead is taken once per fault, under the pages mutex, when the slot is pending.
    fault = zcull[zcull.index('bool lead_taken = false;'):]
    lock = fault.index('std::scoped_lock lock(m_pages_mutex);')
    take = fault.index('tally.add_lead(lead);')
    require(lock < fault.index('pending_slot = found->second.ios_slots.first_pending(address, access.size);') < take and
            fault.index('if (!lead_taken)') < take and fault.index('lead_taken = true;') < take, 'the lead measurement placement')
    require(zcull.count('ios_slots.add(') == 0 and zcull.count('ios_slots.add_at(') == 1, 'the report enqueue records its time')
    # Policy: 561 Automatic adds the boundary titles; the boundary mode only with 561 on, for those titles.
    require(policy.count('rpcs3::ios::title_levers::early_submit_at_pass_boundary(title_id)') == 2 and
            policy.index('resolved.early_submit = resolve_mode(g_cfg.ios_experimental.early_submit,') <
            policy.index('rpcs3::ios::early_submit::enabled.store(resolved.early_submit, std::memory_order_relaxed);') <
            policy.index('resolved.early_submit_at_pass_boundary = resolved.early_submit &&') <
            policy.index('rpcs3::ios::early_submit::at_pass_boundary.store(resolved.early_submit_at_pass_boundary, std::memory_order_relaxed);'),
            'the 659 policy order')
    require(policy.count('"Resolved title policy 659: early_submit=%d early_submit_at_pass_boundary=%d max_deferred_draws=%u"') == 1, 'boot line 659')
    conversions = {}
    for name, end in (('COREPROF OPT561 session=%llu', '"scope=process_window_counters window_boundary_approximate=1",'),
                      ('COREPROF ZCULLLEAD659 session=%llu', '"scope=process_window window_boundary_approximate=1",'),
                      ('COREPROF ZCULLHINT659 session=%llu', 'window_boundary_approximate=1",')):
        start = performance.index(name)
        conversions[name.split()[1]] = performance[start:performance.index(end, start)].count('%')
    # OPT561: the nine 561 conversions and seven boundary ones; ZCULLLEAD659 and ZCULLHINT659: seven each (checked against their arguments).
    require(conversions == {'OPT561': 16, 'ZCULLLEAD659': 7, 'ZCULLHINT659': 7}, 'reporter conversions ' + json.dumps(conversions))
    return {'hint_sites': 5, 'reporter_conversions': conversions}


HEADERS_TEST = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>
#include "ios/IOSEarlySubmit.h"
#include "ios/IOSRsxSyncProfile.h"
#include "ios/IOSTitleLevers.h"
#include "ios/IOSZcullOnDemand.h"
#define CHECK(x) do { if (!(x)) { std::printf("check failed: %s\n", #x); std::exit(1); } } while (0)
namespace tl = rpcs3::ios::title_levers;
static_assert(tl::early_submit_at_pass_boundary("BLES00158") && tl::early_submit_at_pass_boundary("BLUS30089") &&
	tl::early_submit_at_pass_boundary("BLES01717") && !tl::early_submit_at_pass_boundary("BLES01658") &&
	!tl::early_submit_at_pass_boundary("BCES00510") && !tl::early_submit_at_pass_boundary(""));
int main()
{
	namespace od = rpcs3::ios::zcull_on_demand;
	auto* slots = new od::page_slots{};
	const std::uint32_t page = 0x30100000u, a = page + 0x40, b = page + 0x50;
	CHECK(slots->pending_age_us(a, 1000) == 0);
	slots->add_at(a, 1000);
	slots->add_at(a, 1500);              // a second pending report keeps the oldest time
	CHECK(slots->pending(a, 4) && slots->pending_age_us(a, 4000) == 3000);
	slots->remove(a);
	CHECK(slots->pending(a, 4) && slots->pending_age_us(a, 4000) == 3000);
	slots->remove(a);
	CHECK(!slots->pending(a, 4) && slots->pending_age_us(a, 4000) == 0);
	slots->add_at(a, 9000);              // pending again: a new oldest time
	CHECK(slots->pending_age_us(a, 9500) == 500);
	CHECK(slots->pending_age_us(a, 8000) == 0);   // a clock behind the enqueue gives no age
	slots->add(b);                        // the 630 add() records no time: no age, same pending counts
	CHECK(slots->pending(b, 4) && slots->pending_age_us(b, 99999) == 0);
	CHECK(slots->first_pending(page + 0x40, 0x20) == a);
	delete slots;
	auto& t = od::counters();
	t.add_lead(1000); t.add_lead(20000); t.add_lead(od::tally::lead_reference_us);
	CHECK(t.leads.load() == 3 && t.lead_us.load() == 1000 + 20000 + od::tally::lead_reference_us &&
		t.lead_max_us.load() == 20000 && t.leads_over_wait.load() == 2);
	namespace sync = rpcs3::ios::rsx_sync;
	CHECK(sync::zcull_hint_site == sync::hint_sync);
	for (unsigned id = 0; id < sync::hint_site_count; id++) { sync::zcull_hint_site = id; sync::zcull_hint_site_flushes[sync::zcull_hint_site % sync::hint_site_count].fetch_add(id + 1); }
	for (unsigned id = 0; id < sync::hint_site_count; id++) CHECK(sync::zcull_hint_site_flushes[id].load() == id + 1);
	namespace early = rpcs3::ios::early_submit;
	CHECK(!early::at_pass_boundary.load() && early::max_deferred_draws == 32 && early::min_draws == 32 && early::max_per_frame == 6);
	std::printf("{\"result\":\"passed\"}\n");
	return 0;
}
'''


def headers_test(source: Path, work: Path, cxx: str, sanitize: bool) -> dict:
    cpp = work / 'headers659.cpp'
    cpp.write_text(HEADERS_TEST)
    binary = work / 'headers659'
    flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'] if sanitize else []
    built = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', *flags,
                            '-I', str(source / 'rpcs3'), str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, 'the Core 659 header test does not compile:\n' + built.stderr[-4000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    require(run.returncode == 0, 'the Core 659 header test fails:\n' + run.stdout[-2000:] + run.stderr[-2000:])
    return dict(json.loads(run.stdout), sanitizers=['address', 'undefined'] if sanitize else [])


def core655_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core655']
    tree = work / 'core655'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 655 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 655 SHA-256')
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='core659-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        print('source')
        report['source'] = check_source(source)
        print('headers')
        report['headers'] = headers_test(source, work, args.cxx, sanitize)
        tree655 = core655_tree(source, work)
        require(MARKS[0] not in (tree655 / 'rpcs3/ios/IOSEarlySubmit.h').read_text('utf-8', 'surrogateescape'),
                'the Core 655 tree already has the change')
        print('early submission at pass boundaries: real code, control 655 and candidate 659')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_early_submit_boundary659_test.py'), '--candidate', str(source),
                                 '--control', str(tree655), '--cxx', args.cxx, '--report', str(work / 'early.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        require(result.returncode == 0, 'early submission boundary test fails:\n' + result.stdout[-3000:])
        report['earlySubmitBoundary'] = json.loads((work / 'early.json').read_text())
        print('core 655 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core655_test.py'), '--source', str(tree655), '--cxx', args.cxx,
                   '--report', str(work / 'core655.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 655' in result.stdout, 'the Core 655 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core655'] = json.loads((work / 'core655.json').read_text())
    print('PASS: Core 659 increment reverts to Core 655; early submissions of the boundary titles wait for a point without an open '
          'pass (end-of-draw mode equals Core 655); ZCULL lead and hint-site counters; the Core 655 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
