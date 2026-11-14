#!/usr/bin/env python3
"""Host test of REWINDBOX_LEVER_COMPARISON_ON_REQUEST_920 on the real code.

Cores 917 to 919: with Writer Lock Park Spin or Busy Wait Reference Duration on Automatic (the default), the 5 s
performance report switched the lever off and on again between its windows during the first minutes of every boot
(REWINDBOX_PARK_SPIN_COMPARE_917, extended by REWINDBOX_BUSY_WAIT_REFERENCE_918): three passes of 16 windows by pairs,
so a player played parts of those minutes with a lever off. Core 920: the passes run only when the new setting Lever
Comparison Between Report Windows is Enabled; Automatic and Disabled never alternate.

The harness is built twice, from the tree under test and from the Core 919 tree (the Core 920 increment reversed):
the real comparison header (ios/IOSWriterParkSpin917.h), the real report-thread block that applies it
(ios/RPCS3IOSPerformance.cpp, from the REWINDBOX_PARK_SPIN_COMPARE_917 comment to the next diagnostics block) and the
real policy statements that allow it (ios/RPCS3IOSExperimentalPolicy.cpp: policy.busy_wait_compare and
resolved.writer_park_compare), around a model of a boot: 140 report windows of a running game showing frames, each in
a storm of heavy PUTLLC, on a 1 GHz counter (reference scale 42). It checks:
- the defect before the correction: the control, with every setting at its default, switches the park spin and the
  busy wait scale between windows and logs COREPROF PARKCMP917 steps;
- the correction: with Lever Comparison on Automatic or Disabled, for every combination of the two lever settings
  (Automatic, Enabled, Disabled), the tree under test never switches a lever, logs no step, and runs both levers as
  their settings resolve (Automatic: on); a new boot after a boot that compared does not compare;
- the comparison asked for: with Lever Comparison Enabled, only a lever whose own setting is Automatic switches, the
  switches stay inside the three passes (none after the last window of the last pass), each is logged, and both
  levers end on.
Source checks: the setting (default Automatic), its catalogue entry, the policy line "Resolved title policy 920", the
busy wait description without the comparison sentence. Host model of the report thread; no FPS claim.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INCREMENT = ROOT / 'build-utils/rpcs3/core920-from-919.patch'
# Later increments over the same files, newest first: reversed before this one when they apply in reverse.
# Newest first: Core 925 inserts next to the Core 921 policy lines, so 921 only reverses once 925 has; Core 931 inserts next
# to the Core 920 setting lines (Event Waits When Hot), so 920 only reverses once 931 has.
LATER = (ROOT / 'build-utils/rpcs3/core938-from-937.patch', ROOT / 'build-utils/rpcs3/core937-from-936.patch', ROOT / 'build-utils/rpcs3/core936-from-935.patch', ROOT / 'build-utils/rpcs3/core935-from-934.patch', ROOT / 'build-utils/rpcs3/core934-from-933.patch', ROOT / 'build-utils/rpcs3/core933-from-932.patch', ROOT / 'build-utils/rpcs3/core932-from-931.patch', ROOT / 'build-utils/rpcs3/core931-from-930.patch', ROOT / 'build-utils/rpcs3/core925-from-924.patch', ROOT / 'build-utils/rpcs3/core921-from-920.patch')
HEADER = 'rpcs3/ios/IOSWriterParkSpin917.h'
REPORT = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
MARK = 'REWINDBOX_LEVER_COMPARISON_ON_REQUEST_920'
BLOCK_START = '// REWINDBOX_PARK_SPIN_COMPARE_917 and REWINDBOX_BUSY_WAIT_REFERENCE_918 (ios/IOSWriterParkSpin917.h): this'
BLOCK_END = '// NEOSTATION_BUILD487_DIAGNOSTICS_V1'
MODES = ('automatic', 'enabled', 'disabled')

HARNESS = r'''
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ARCH_ARM64 1
namespace utils { inline std::atomic<u64> arm_timer_scale{1}; }
#include "ios/IOSWriterParkSpin917.h"

enum class ios_experimental_mode { automatic, enabled, disabled };
struct setting { ios_experimental_mode value = ios_experimental_mode::automatic; ios_experimental_mode get() const { return value; } };
struct { struct { setting writer_park_spin, busy_wait_reference, lever_comparison; } ios_experimental; } g_cfg;
static bool resolve_mode(const setting& s, bool automatic_value)
{
	return s.value == ios_experimental_mode::automatic ? automatic_value : s.value == ios_experimental_mode::enabled;
}
enum class system_state { running, paused };
static unsigned g_steps_logged = 0;
struct logger { template <typename... A> void notice(const char* format, A...) { if (std::strstr(format, "PARKCMP917")) g_steps_logged++; } } ios_core_profiler;

struct policy_t { u64 busy_wait_reference_scale = 42; bool busy_wait_compare = false; };
struct resolved_t { bool writer_park_compare = false; };

static ios_experimental_mode mode_of(const char* text)
{
	return !std::strcmp(text, "enabled") ? ios_experimental_mode::enabled : !std::strcmp(text, "disabled") ? ios_experimental_mode::disabled : ios_experimental_mode::automatic;
}

int main(int argc, char** argv)
{
	// argv: spin busy comparison [spin busy comparison ...]: one boot each, in order.
	rpcs3::ios::writer_park::compare::tracker m_park_compare;
	std::printf("[");
	for (int boot = 0; 1 + boot * 3 + 2 < argc; boot++)
	{
		g_cfg.ios_experimental.writer_park_spin.value = mode_of(argv[1 + boot * 3]);
		g_cfg.ios_experimental.busy_wait_reference.value = mode_of(argv[2 + boot * 3]);
		g_cfg.ios_experimental.lever_comparison.value = mode_of(argv[3 + boot * 3]);
		// ---- the boot policy (RPCS3IOSExperimentalPolicy.cpp) ----
		const bool calibrated = false;
		policy_t policy;
		resolved_t resolved;
		@@BUSY_POLICY@@
		@@SPIN_POLICY@@
		const bool busy_wait_reference = !calibrated && resolve_mode(g_cfg.ios_experimental.busy_wait_reference, true);
		utils::arm_timer_scale.store(busy_wait_reference ? policy.busy_wait_reference_scale : 1);
		rpcs3::ios::writer_park::compare::busy_wait_scale_on.store(policy.busy_wait_reference_scale);
		rpcs3::ios::writer_park::compare::busy_wait_allowed.store(policy.busy_wait_compare);
		rpcs3::ios::writer_park::spin_enabled.store(resolve_mode(g_cfg.ios_experimental.writer_park_spin, true));
		rpcs3::ios::writer_park::compare::allowed.store(resolved.writer_park_compare);
		const bool spin_resolved = rpcs3::ios::writer_park::spin_enabled.load();
		const u64 scale_resolved = utils::arm_timer_scale.load();
		g_steps_logged = 0;
		unsigned spin_switches = 0, scale_switches = 0, last_switch_window = 0, spin_off_windows = 0, scale_off_windows = 0;
		const unsigned long long profile_session = 1000 + boot;
		for (unsigned long long profile_window = 1; profile_window <= 140; profile_window++)
		{
			const system_state state = system_state::running;
			const unsigned long long guest_window_flips = 120, ios_putllc_heavy_window = 1'000'000;
			if (!rpcs3::ios::writer_park::spin_enabled.load()) spin_off_windows++;
			if (utils::arm_timer_scale.load() != scale_resolved) scale_off_windows++;
			const bool spin_before = rpcs3::ios::writer_park::spin_enabled.load();
			const u64 scale_before = utils::arm_timer_scale.load();
			// ---- the report-thread block (RPCS3IOSPerformance.cpp) ----
			@@REPORT_BLOCK@@
			if (rpcs3::ios::writer_park::spin_enabled.load() != spin_before) { spin_switches++; last_switch_window = static_cast<unsigned>(profile_window); }
			if (utils::arm_timer_scale.load() != scale_before) { scale_switches++; last_switch_window = static_cast<unsigned>(profile_window); }
		}
		std::printf("%s{\"spin_compare\":%d,\"busy_compare\":%d,\"spin_resolved\":%d,\"scale_resolved\":%llu,\"spin_switches\":%u,\"scale_switches\":%u,"
			"\"spin_off_windows\":%u,\"scale_off_windows\":%u,\"last_switch_window\":%u,\"steps_logged\":%u,\"spin_end\":%d,\"scale_end\":%llu}",
			boot ? "," : "", resolved.writer_park_compare ? 1 : 0, policy.busy_wait_compare ? 1 : 0, spin_resolved ? 1 : 0,
			static_cast<unsigned long long>(scale_resolved), spin_switches, scale_switches, spin_off_windows, scale_off_windows,
			last_switch_window, g_steps_logged, rpcs3::ios::writer_park::spin_enabled.load() ? 1 : 0,
			static_cast<unsigned long long>(utils::arm_timer_scale.load()));
	}
	std::printf("]\n");
	return 0;
}
'''


def require(condition, message):
    if not condition:
        print('FAIL: ' + message)
        raise SystemExit(1)


def text(tree: Path, name: str) -> str:
    return (tree / name).read_text(encoding='utf-8', errors='surrogateescape')


def statement(source: str, start: str) -> str:
    index = source.index(start)
    return source[index:source.index(';', index) + 1]


def build(tree: Path, work: Path, name: str, cxx: str, sanitize: bool) -> Path:
    report = text(tree, REPORT)
    begin = report.index(BLOCK_START)
    block = report[begin:report.index(BLOCK_END, begin)]
    block = block[:block.rindex('}') + 1]
    policy = text(tree, POLICY)
    source = (HARNESS.replace('@@REPORT_BLOCK@@', block)
              .replace('@@BUSY_POLICY@@', statement(policy, 'policy.busy_wait_compare = '))
              .replace('@@SPIN_POLICY@@', statement(policy, 'resolved.writer_park_compare = ')))
    cpp = work / (name + '.cpp')
    cpp.write_text(source)
    binary = work / name
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wno-unused-variable', '-Wno-unused-but-set-variable', '-I', str(tree / 'rpcs3')]
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    built = subprocess.run([cxx, *flags, str(cpp), '-o', str(binary)], capture_output=True, text=True)
    require(built.returncode == 0, name + ' does not compile:\n' + built.stderr[-6000:])
    return binary


def boots(binary: Path, configurations) -> list:
    argv = [str(binary)]
    for spin, busy, comparison in configurations:
        argv += [spin, busy, comparison]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    require(result.returncode == 0, binary.name + ' failed:\n' + result.stdout[-2000:] + result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def control_tree(source: Path, work: Path) -> Path:
    require(INCREMENT.is_file(), 'the Core 920 increment ' + str(INCREMENT.relative_to(ROOT)))
    tree = work / 'tree919'
    shutil.copytree(source / 'rpcs3', tree / 'rpcs3', symlinks=True)
    # Core 932's increment also holds Utilities files (the patch engine, the JIT arena): without them it cannot be reversed,
    # and Core 931, then Core 920, would not reverse after it.
    for extra in ('Utilities', 'util'):
        if (source / extra).is_dir():
            shutil.copytree(source / extra, tree / extra, symlinks=True)
    for later in LATER:
        if later.is_file() and subprocess.run(['git', 'apply', '-R', '--check', '--whitespace=nowarn', str(later)], cwd=tree,
                                              capture_output=True).returncode == 0:
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(later)], cwd=tree, check=True, capture_output=True)
    reverse = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(INCREMENT)], cwd=tree, capture_output=True, text=True)
    require(reverse.returncode == 0, 'the Core 920 increment does not reverse on the tree under test:\n' + reverse.stderr[-3000:])
    return tree


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--control', type=Path)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()

    # --- the sources ---
    config, settings, policy = text(source, CONFIG), text(source, SETTINGS), text(source, POLICY)
    require('cfg::_enum<ios_experimental_mode> lever_comparison{ this, "Lever Comparison Between Report Windows", ios_experimental_mode::automatic };'
            in config, 'the setting, Automatic by default')
    require(settings.count('SETTING("experimental.lever_comparison", "Experimental", "FPS Experiments", "Lever comparison between report windows"') == 1
            and 'Automatic and Disabled never alternate' in settings and 'g_cfg.ios_experimental.lever_comparison, 0, 0, 0),' in settings,
            'the catalogue entry')
    busy_entry = settings[settings.index('SETTING("experimental.busy_wait_reference"'):]
    busy_entry = busy_entry[:busy_entry.index('\n')]
    require('compares both' not in busy_entry, 'the busy wait description still announces a comparison')
    require('"Resolved title policy 920: lever_comparison=%s park_spin_alternates=%d busy_wait_alternates=%d"' in policy, 'the 920 policy line')
    require(MARK in policy and MARK in text(source, HEADER), 'the 920 marker')

    temporary = tempfile.TemporaryDirectory(prefix='lever-comparison-920-')
    work = Path(temporary.name)
    try:
        control = args.control.resolve() if args.control else control_tree(source, work)
        require(MARK not in text(control, POLICY), 'the control tree is the one before Core 920')
        sanitize = not args.no_sanitizers
        before = build(control, work, 'control919', args.cxx, sanitize)
        after = build(source, work, 'candidate920', args.cxx, sanitize)

        # --- the defect before the correction: every setting at its default ---
        default = boots(before, [('automatic', 'automatic', 'automatic')])[0]
        print('control919 defaults: ' + json.dumps(default))
        require(default['spin_compare'] == 1 and default['busy_compare'] == 1, 'the control does not allow the comparison by default')
        require(default['spin_switches'] >= 6 and default['scale_switches'] >= 6 and default['steps_logged'] > 0,
                'the control does not reproduce the switches of the levers: ' + json.dumps(default))
        require(default['spin_off_windows'] > 0 and default['scale_off_windows'] > 0, 'the control never ran a window with a lever off')

        # --- the correction: no comparison unless asked for, whatever the lever settings ---
        configurations = [(spin, busy, comparison) for comparison in ('automatic', 'disabled') for spin in MODES for busy in MODES]
        results = boots(after, configurations)
        for (spin, busy, comparison), result in zip(configurations, results):
            label = f'candidate920 spin={spin} busy={busy} comparison={comparison}'
            require(result['spin_compare'] == 0 and result['busy_compare'] == 0, label + ': a comparison is allowed')
            require(result['spin_switches'] == 0 and result['scale_switches'] == 0 and result['steps_logged'] == 0,
                    label + ': a lever switched: ' + json.dumps(result))
            require(result['spin_end'] == result['spin_resolved'] and result['scale_end'] == result['scale_resolved'], label + ': a lever moved')
            require(result['spin_resolved'] == (spin != 'disabled') and result['scale_resolved'] == (1 if busy == 'disabled' else 42),
                    label + ': the levers do not run as their settings resolve: ' + json.dumps(result))
        print(f'candidate920: {len(configurations)} boots without a requested comparison, 0 switches, 0 steps logged; Automatic = both on')

        # --- a boot that compared, then ordinary boots ---
        sequence = boots(after, [('automatic', 'automatic', 'enabled'), ('automatic', 'automatic', 'automatic'),
                                 ('automatic', 'automatic', 'enabled'), ('automatic', 'automatic', 'disabled')])
        asked, plain, asked_again, plain_again = sequence
        print('candidate920 comparison asked for: ' + json.dumps(asked))
        last_pass_window = 6 + 3 * (16 + 22)
        for label, result in (('first', asked), ('third', asked_again)):
            require(result['spin_compare'] == 1 and result['busy_compare'] == 1, label + ' boot: the comparison asked for is not allowed')
            require(result['spin_switches'] >= 6 and result['scale_switches'] >= 6 and result['steps_logged'] > 0,
                    label + ' boot: the comparison asked for does not run: ' + json.dumps(result))
            require(0 < result['last_switch_window'] <= last_pass_window and result['spin_end'] == 1 and result['scale_end'] == 42,
                    label + ' boot: switches outside the passes or a lever left off: ' + json.dumps(result))
        for label, result in (('second', plain), ('fourth', plain_again)):
            require(result['spin_switches'] == 0 and result['scale_switches'] == 0 and result['steps_logged'] == 0,
                    label + ' boot after a comparison: a lever switched: ' + json.dumps(result))
        only = boots(after, [('enabled', 'automatic', 'enabled'), ('automatic', 'disabled', 'enabled'), ('disabled', 'enabled', 'enabled')])
        require(only[0]['spin_switches'] == 0 and only[0]['scale_switches'] > 0, 'comparison asked for: an Enabled park spin switched')
        require(only[1]['spin_switches'] > 0 and only[1]['scale_switches'] == 0, 'comparison asked for: a Disabled busy wait switched')
        require(only[2]['spin_switches'] == 0 and only[2]['scale_switches'] == 0 and only[2]['steps_logged'] == 0,
                'comparison asked for with both levers set explicitly: a lever switched')
        print('PASS: lever comparison on request (920): the control (Core 919 code, default settings) switches the park spin '
              f'{default["spin_switches"]} times and the busy wait scale {default["scale_switches"]} times in the first '
              f'{last_pass_window} windows ({default["spin_off_windows"]} and {default["scale_off_windows"]} windows with a lever off); the tree under '
              f'test switches nothing in {len(configurations)} boots without a requested comparison and in the boots after one; a comparison '
              'asked for switches only Automatic levers, inside its three passes, logged, and leaves both on')
    finally:
        temporary.cleanup()


if __name__ == '__main__':
    main()
