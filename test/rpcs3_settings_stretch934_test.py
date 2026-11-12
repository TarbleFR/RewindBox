#!/usr/bin/env python3
"""Core 934 checks: the settings API follows the Core 922 boot rule, and the Metal present honours Stretch To Display Area.

REWINDBOX_SETTINGS_API_RULE_934 (rpcs3/ios/RPCS3IOSSettings.cpp, load_effective_settings): since Core 922 the boot no longer
applies a legacy full custom_configs file (System.cpp, CONFIG_DB922), but the settings API still read it, showed its values
and saved every per-game change into it. God of War III has such a file, so Stretch to fill screen (and any other per-game
choice) was saved where the boot never looks. The API now loads global < RPCS3 database < the sparse user overrides, as the
boot does, and set_game_setting saves a sparse override.

REWINDBOX_METAL_STRETCH_934 (rpcs3/Emu/RSX/Metal/MTLPresent.h, MTLGSRender.cpp): the native Metal 4 present always fitted the
image with its aspect ratio; place() fills the drawable when Stretch To Display Area is on, as VKPresent.cpp does.

Usage: rpcs3_settings_stretch934_test.py --source TREE [--cxx g++]
Each check has a control that reverts the fix on a copy and must be caught.
"""
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HARNESS = r'''
#include "Emu/RSX/Metal/MTLPresent.h"
#include <cstdio>
using namespace mtl::present_pass;
int main()
{
	int failures = 0;
	auto check = [&](bool ok, const char* what) { if (!ok) { std::printf("FAIL: %s\n", what); ++failures; } };
	// A 1280x720 frame on a 2556x1179 iPhone drawable.
	const auto off = place(1280, 720, 2556, 1179, false);
	const auto fitted = fit(1280, 720, 2556, 1179);
	check(off.left == fitted.left && off.right == fitted.right && off.bottom == fitted.bottom && off.top == fitted.top,
		"stretch off is exactly fit()");
	check(off.left > -1.f && off.right < 1.f && off.bottom == -1.f && off.top == 1.f, "stretch off keeps the aspect ratio (pillarbox)");
	const auto on = place(1280, 720, 2556, 1179, true);
	check(on.left == -1.f && on.right == 1.f && on.bottom == -1.f && on.top == 1.f, "stretch on fills the drawable");
	const auto tall = place(720, 1280, 1179, 2556, true);
	check(tall.left == -1.f && tall.right == 1.f && tall.bottom == -1.f && tall.top == 1.f, "stretch on fills a portrait drawable");
	const auto no_source = place(0, 720, 2556, 1179, true);
	check(no_source.left == 0.f && no_source.right == 0.f && no_source.bottom == 0.f && no_source.top == 0.f, "an empty source draws nothing");
	const auto no_target = place(1280, 720, 0, 0, true);
	check(no_target.left == 0.f && no_target.right == 0.f, "an empty target draws nothing");
	std::printf(failures ? "present: FAIL\n" : "present: PASS\n");
	return failures ? 1 : 0;
}
'''


def function_body(text, signature):
    start = text.index(signature)
    depth, i = 0, text.index('{', start)
    for j in range(i, len(text)):
        if text[j] == '{':
            depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise AssertionError('unterminated ' + signature)


def check_present(tree, cxx, work):
    harness = work / 'present934.cpp'
    harness.write_text(HARNESS)
    binary = work / 'present934'
    build = subprocess.run([cxx, '-std=c++20', '-I', str(tree / 'rpcs3'), '-I', str(tree), '-o', str(binary), str(harness)],
                           capture_output=True, text=True)
    if build.returncode:
        return False, 'compile failed: ' + build.stderr[-600:]
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    return run.returncode == 0, run.stdout.strip()


def check_present_wiring(tree):
    source = (tree / 'rpcs3/Emu/RSX/Metal/MTLGSRender.cpp').read_text()
    uses = source.count('mtl::present_pass::place(display_width, display_height, m_drawable_width, m_drawable_height, '
                        'g_cfg.video.stretch_to_display_area)')
    fits = len(re.findall(r'present_pass::fit\(', source))
    ok = uses == 2 and fits == 0
    return ok, f'place() with the setting at {uses} of 2 sites, fit() left at {fits}'


def check_settings(tree):
    settings = (tree / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text()
    body = function_body(settings, 'settings_load_error load_effective_settings(std::string_view title_id, bool& has_custom_config) noexcept')
    problems = []
    code = re.sub(r'//[^\n]*', '', body)
    if 'get_custom_config_path' in code or 'custom_config' in code.replace('has_custom_config', ''):
        problems.append('load_effective_settings still reads the legacy custom config')
    if 'REWINDBOX_SETTINGS_API_RULE_934' not in body:
        problems.append('marker missing')
    if code.count('has_custom_config = true'):
        problems.append('has_custom_config can still become true')
    system = (tree / 'rpcs3/Emu/System.cpp').read_text()
    if 'legacy_custom_ignored=1' not in system:
        problems.append('the Core 922 boot rule this follows is gone (System.cpp CONFIG_DB922)')
    api = (tree / 'rpcs3/ios/RPCS3IOS.cpp').read_text()
    if not re.search(r'has_custom_config\s*\?\s*rpcs3::ios::save_game_settings\(title_id\)\s*:\s*rpcs3::ios::save_game_setting_override\(title_id, key, value\)', api):
        problems.append('set_game_setting no longer chooses the sparse override when there is no custom config')
    return not problems, '; '.join(problems) or 'API = global < database < sparse overrides; set_game_setting saves an override'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    tree = args.source.resolve()
    failures = 0
    with tempfile.TemporaryDirectory(prefix='core934-') as tmp:
        work = Path(tmp)
        for name, (ok, detail) in (('present', check_present(tree, args.cxx, work)),
                                   ('present wiring', check_present_wiring(tree)),
                                   ('settings rule', check_settings(tree))):
            print(('PASS' if ok else 'FAIL') + f': {name}: {detail}')
            failures += not ok

        # Controls: each fix reverted on a copy must be caught.
        copy = work / 'control'
        for rel in ('rpcs3/Emu/RSX/Metal/MTLPresent.h', 'rpcs3/Emu/RSX/Metal/MTLGSRender.cpp', 'rpcs3/ios/RPCS3IOSSettings.cpp',
                    'rpcs3/ios/RPCS3IOS.cpp', 'rpcs3/Emu/System.cpp', 'rpcs3/util/types.hpp'):
            (copy / rel).parent.mkdir(parents=True, exist_ok=True)
            if (tree / rel).exists():
                shutil.copy2(tree / rel, copy / rel)
        for extra in (tree / 'rpcs3/util').glob('*.hpp'):
            shutil.copy2(extra, copy / 'rpcs3/util' / extra.name)

        def control(name, rel, old, new, check):
            path = copy / rel
            original = path.read_text()
            if old not in original:
                print(f'FAIL: control not applicable (the fix is absent): {name}')
                return False
            path.write_text(original.replace(old, new))
            try:
                ok, detail = check()
            finally:
                path.write_text(original)
            caught = not ok
            print(('PASS' if caught else 'FAIL') + f': control caught: {name}')
            return caught

        caught = [
            control('stretch ignored by place()', 'rpcs3/Emu/RSX/Metal/MTLPresent.h', 'if (!stretch ||', 'if (true ||',
                    lambda: check_present(copy, args.cxx, work)),
            control('present back to fit()', 'rpcs3/Emu/RSX/Metal/MTLGSRender.cpp',
                    'mtl::present_pass::place(display_width, display_height, m_drawable_width, m_drawable_height, '
                    'g_cfg.video.stretch_to_display_area)',
                    'mtl::present_pass::fit(display_width, display_height, m_drawable_width, m_drawable_height)',
                    lambda: check_present_wiring(copy)),
            control('legacy custom config read again', 'rpcs3/ios/RPCS3IOSSettings.cpp',
                    '\treturn settings_load_error::none;\n}\n\nbool save_game_settings',
                    '\tconst std::string custom_path = rpcs3::utils::get_custom_config_path(std::string{title_id});\n'
                    '\tif (fs::file custom_config{custom_path}) { has_custom_config = true; g_cfg.from_string(custom_config.to_string()); }\n'
                    '\treturn settings_load_error::none;\n}\n\nbool save_game_settings',
                    lambda: check_settings(copy)),
            control('boot rule 922 removed', 'rpcs3/Emu/System.cpp', 'legacy_custom_ignored=1', 'legacy_custom_applied=1',
                    lambda: check_settings(copy)),
        ]
        failures += caught.count(False)
    print('PASS: Core 934 settings rule and Metal stretch' if not failures else f'FAIL: {failures} problem(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
