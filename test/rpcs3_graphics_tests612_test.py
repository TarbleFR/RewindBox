#!/usr/bin/env python3
"""REWINDBOX_GRAPHICS_TESTS_612: per-game accuracy tests for the Assassin's Creed torch
and Black Ops II viewmodel investigation. Host evidence only; nothing here runs a
game, Metal, MoltenVK or an iPhone, and nothing claims that a defect is fixed.

App contract (always):
  1. the bridge whitelist (RPCS3TestSettingValues) equals the in-game page levers
     (RPCS3AccuracyLevers), "@inherit" is the "Profile default" value, and the two
     commands (testSetting, testReset) are routed before the generic setting path;
  2. the test restart boots the title again after a successful stop even when a
     change is refused, and logs every change;
  3. the CONFIG_LAYERS part=rsx capture sits outside the RPCS3Log regions that the
     pipeline-cache milestones test and the boot-stability test compile;
  4. every text key of the page exists in the 12 locales.

Core contract (with --source <materialized Core 612>):
  5. Experimental "Position Invariance" (Automatic = the title list) resolved through
     resolve_mode; catalogue entries for the eight keys in the game context, with the
     option spellings the bridge sends;
  6. rpcs3_ios_set_game_setting handles "@inherit" before any value parsing, only for
     boolean/choice keys and only without a legacy full custom config;
  7. CONFIG_LAYERS part=rsx is emitted before the main CONFIG_LAYERS line, the main
     sparse-override call is unchanged, and the keys are read only when applied;
  8. executed: the real formatter header (native/rpcs3_graphics_tests612_rsx_line_test.cpp)
     and the real game_setting_override_keys / remove_game_setting_override bodies
     extracted from RPCS3IOSSettings.cpp, compiled against explicit storage stubs.

    python3 test/rpcs3_graphics_tests612_test.py [--source CORE] [--sanitize] [--report OUT.json]
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
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
BRIDGE = CLASSES / 'Rpcs3InternalBridgePlugin.mm'
MENU = CLASSES / 'Rpcs3SessionMenu.mm'
MENU_H = CLASSES / 'Rpcs3SessionMenu.h'
L10N = CLASSES / 'RPCS3InGameLocalization.mm'
NATIVE_RSX = ROOT / 'test/native/rpcs3_graphics_tests612_rsx_line_test.cpp'
LOCALES = ('en', 'fr', 'de', 'es', 'it', 'pt', 'id', 'ru', 'ja', 'ko', 'zh', 'zh_Hant')
KEYS = ('gpu.zcull_accuracy', 'debug.disable_occlusion', 'debug.emulate_depth_compare',
        'advanced.disable_msl_fast_math', 'debug.disable_vertex_cache', 'gpu.shader_precision',
        'experimental.position_invariance', 'experimental.moltenvk_async_submits')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def objc_strings(text: str) -> list[str]:
    return re.findall(r'@"((?:[^"\\]|\\.)*)"', text)


def block(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


# --- app contract ---------------------------------------------------------------
def bridge_whitelist(bridge: str) -> dict[str, list[str]]:
    body = block(bridge, 'static NSDictionary<NSString*, NSArray<NSString*>*>* RPCS3TestSettingValues(void) {',
                 '  return values;\n}')
    entries = re.findall(r'@"([a-z_.]+)": @\[([^\]]*)\]', body)
    return {key: objc_strings(values) for key, values in entries}


def menu_levers(menu: str) -> list[dict]:
    body = block(menu, 'static NSArray<NSDictionary*>* RPCS3AccuracyLevers(void) {', '  return levers;\n}')
    shared = {'onOff': ['false', 'true'], 'onOffLabels': ['disabled', 'enabled']}
    require('NSArray* onOff = @[@"false", @"true"];' in body and
            'NSArray* onOffLabels = @[@"disabled", @"enabled"];' in body, 'menu on/off lists changed')
    levers = []
    for item in re.findall(r'@\{(@"key".*?)\}', body, re.S):
        fields = dict(re.findall(r'@"(key|title|field)": @"([^"]+)"', item))
        for name in ('values', 'labels'):
            literal = re.search(r'@"' + name + r'": @\[([^\]]*)\]', item)
            alias = re.search(r'@"' + name + r'": (onOff\w*)', item)
            fields[name] = objc_strings(literal.group(1)) if literal else shared[alias.group(1)]
        levers.append(fields)
    return levers


def l10n_tables(text: str) -> dict[str, dict[str, str]]:
    body = block(text, 'NSDictionary<NSString*, NSDictionary<NSString*, NSString*>*>* Build612Translations() {',
                 '  return values;\n}')
    tables = {}
    for locale, entries in re.findall(r'\n      @"(\w+)": @\{\n(.*?)\n      \},', body, re.S):
        tables[locale] = dict(re.findall(r'@"(\w+)": @"((?:[^"\\]|\\.)*)",', entries))
    return tables


def app_contract() -> dict:
    bridge, menu, header, l10n = (p.read_text(encoding='utf-8') for p in (BRIDGE, MENU, MENU_H, L10N))
    allowed = bridge_whitelist(bridge)
    require(tuple(allowed) == KEYS, 'bridge whitelist keys differ: ' + repr(list(allowed)))
    levers = menu_levers(menu)
    require([lever['key'] for lever in levers] == list(KEYS), 'menu levers differ from the bridge whitelist')
    for lever in levers:
        require(lever['values'] == allowed[lever['key']], 'menu values differ for ' + lever['key'])
        require(len(lever['labels']) == len(lever['values']), 'menu labels differ for ' + lever['key'])
    fields = {lever['key']: lever.get('field') for lever in levers}
    require(fields == {'gpu.zcull_accuracy': None, 'debug.disable_occlusion': 'zcull_queries_off',
                       'debug.emulate_depth_compare': 'depth_compare', 'advanced.disable_msl_fast_math': 'msl_fast_math_off',
                       'debug.disable_vertex_cache': 'vertex_cache_off', 'gpu.shader_precision': None,
                       'experimental.position_invariance': 'invariance', 'experimental.moltenvk_async_submits': 'mvk_async'},
            'menu reads other CONFIG_LAYERS part=rsx fields')

    # Menu wiring: the page is appended (existing pages keep their values) and reached from Graphics row 3.
    enum = block(menu, 'typedef NS_ENUM(NSInteger, RPCS3MenuPage) {', '};')
    require(re.findall(r'\n  (RPCS3Menu\w+),', enum)[-1] == 'RPCS3MenuAccuracy', 'accuracy page is not the last page value')
    require('case RPCS3MenuGraphics: return 4;' in menu and
            'case RPCS3MenuAccuracy: return RPCS3AccuracyLevers().count + 1;' in menu, 'row counts')
    require('[self child:RPCS3MenuAccuracy title:[self text:@"accuracyMenu"]]' in menu, 'Graphics row 3 does not open the page')
    require('@{@"key": lever[@"key"], @"value": @"@inherit"}' in menu and
            'command:@"testSetting"' in menu and '[self performCommand:@"testReset" value:nil];' in menu,
            'page commands')
    require('child.readAccuracy = self.readAccuracy;' in menu and 'Rpcs3SessionReadAccuracy readAccuracy;' in header,
            'accuracy reader is not propagated')

    # Bridge routing and restart semantics.
    command = block(bridge, '- (void)performSessionCommand:(NSString*)command', '\n}\n')
    test_route = command.index('if ([command isEqual:@"testSetting"] || [command isEqual:@"testReset"]) {')
    require(test_route < command.index('NSString* setting = nil;'), 'test commands are not routed first')
    require('if (![setting isEqualToString:@"@inherit"] && ![allowed[key] containsObject:setting]) return nil;' in bridge,
            'bridge accepts values outside the whitelist')
    restart = block(bridge, '- (void)applyTestSettingChanges:', '\n}\n')
    stopped = restart.index('    if (stopped) {\n      for (NSArray<NSString*>* change in changes) {')
    reboot = restart.index('\n      }\n      status = [self bootTitleForCore:titleId.UTF8String savestate:NULL];\n    }\n')
    require(stopped < restart.index('break;') < reboot and restart.count('bootTitleForCore') == 1,
            'a refused change does not reboot the title unconditionally after the stop')
    require(restart.count('RPCS3Diagnostic(@"game_setting"') == 2 and 'test=1' in restart, 'test changes are not logged')
    require('menu.readAccuracy = ^{' in bridge and 'RPCS3RsxConfigSnapshot(accuracyTitle)' in bridge, 'menu reader')

    # The capture must stay outside the RPCS3Log regions compiled by other host tests.
    log = bridge.split('static void RPCS3Log(void* context, int32_t level, const char* message) {', 1)[1].split('\n}', 1)[0]
    capture = log.index('if (strstr(message, "CONFIG_LAYERS part=rsx") != nullptr) RPCS3RememberRsxConfig(message);')
    require(capture < log.index('// NEOSTATION_BUILD283_BOUNDED_CORE_LOG'), 'capture moved into the bounded-log region')
    for anchor in ('  } else if (RPCS3PipelineCacheBoundary(message)) {', '  const BOOL profiler =', '  NSString* text ='):
        require(capture < log.index(anchor), 'capture inside a compiled region: ' + anchor.strip())

    # 12 locales, the same keys everywhere, and every key the page reads.
    tables = l10n_tables(l10n)
    require(tuple(tables) == LOCALES, 'Build612Translations locales: ' + repr(list(tables)))
    keys = list(tables['en'])
    require(len(keys) == 23 and all(list(tables[locale]) == keys for locale in LOCALES), 'locale key sets differ')
    require(all(value.strip() for table in tables.values() for value in table.values()), 'empty translation')
    page = block(menu, '- (NSString*)accuracyDetail:(NSDictionary*)lever {', '\n}\n') + block(
        menu, '  if (self.page == RPCS3MenuAccuracy) {\n    NSArray<NSDictionary*>* levers', '\n  }\n')
    used = set(re.findall(r'\[self text:@"(\w+)"\]', page)) | {'accuracyMenu', 'accuracyMenuDetail', 'accuracyHelp',
                                                               'testProfileDefault'}
    used |= {lever['title'] for lever in levers} | {label for lever in levers for label in lever['labels']}
    used |= set(re.findall(r'@"(zcull\w+|precision\w+|testSource\w+)"', page))
    base = {'enabled', 'disabled'}
    require(all(f'@"{key}"' in l10n for key in base), 'enabled/disabled translations missing')
    missing = sorted(key for key in used - base if key not in tables['en'])
    require(not missing, 'untranslated page keys: ' + repr(missing))
    return {'whitelist': allowed, 'locales': list(tables), 'keys': len(keys),
            'bridge_sha256': sha(BRIDGE.read_bytes()), 'menu_sha256': sha(MENU.read_bytes()),
            'localization_sha256': sha(L10N.read_bytes())}


# --- Core contract ----------------------------------------------------------------
def catalogue(settings: str) -> dict[str, tuple[str, str, str]]:
    found = {}
    for macro, key, kind, entry in re.findall(
            r'\n\t(SETTING|GAME_SETTING|GLOBAL_SETTING)\("([a-z0-9_.]+)",.*?kind::(RPCS3_IOS_SETTING_\w+), ([\w.]+),', settings):
        found[key] = (macro, kind, entry)
    return found


def enum_spellings(types_cpp: str, enum: str) -> set[str]:
    return set(re.findall(r'case ' + enum + r'::\w+: return "([^"]+)";', types_cpp))


def core_contract(source: Path) -> dict:
    read = lambda relative: (source / relative).read_text(encoding='utf-8')
    config, policy, settings, settings_h = (read('rpcs3/Emu/system_config.h'), read('rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'),
                                            read('rpcs3/ios/RPCS3IOSSettings.cpp'), read('rpcs3/ios/RPCS3IOSSettings.h'))
    api, system, types_cpp, zcull = (read('rpcs3/ios/RPCS3IOS.cpp'), read('rpcs3/Emu/System.cpp'),
                                     read('rpcs3/Emu/system_config_types.cpp'), read('rpcs3/ios/RPCS3IOSZcullAccuracy.h'))
    require('cfg::_enum<ios_experimental_mode> position_invariance{ this, "Position Invariance", ios_experimental_mode::automatic };'
            in config, 'Position Invariance cfg entry')
    require('resolved.position_invariance = resolve_mode(g_cfg.ios_experimental.position_invariance,\n'
            '\t\trpcs3::ios::title_levers::requires_position_invariance(title_id));' in policy, 'invariance resolution')
    require(policy.count('resolved.position_invariance =') == 1, 'a second invariance assignment')

    entries = catalogue(settings)
    allowed = bridge_whitelist(BRIDGE.read_text(encoding='utf-8'))
    spellings = {
        'RPCS3_IOS_SETTING_BOOLEAN': {'false', 'true'},
    }
    for key in KEYS:
        require(key in entries, 'catalogue lacks ' + key)
        macro, kind, entry = entries[key]
        require(macro in ('SETTING', 'GAME_SETTING'), key + ' is not a game setting')
        values = set(allowed[key])
        if key == 'gpu.zcull_accuracy':
            accepted = set(re.findall(r'if \(value == "(\w+)"\)', zcull))
        elif key == 'gpu.shader_precision':
            accepted = enum_spellings(types_cpp, 'gpu_preset_level')
        elif key.startswith('experimental.'):
            require(entry == 'g_cfg.ios_experimental.' + key.split('.', 1)[1], key + ' entry')
            accepted = enum_spellings(types_cpp, 'ios_experimental_mode')
        else:
            require(kind == 'RPCS3_IOS_SETTING_BOOLEAN', key + ' is not boolean')
            accepted = spellings[kind]
        require(kind in ('RPCS3_IOS_SETTING_BOOLEAN', 'RPCS3_IOS_SETTING_CHOICE'), key + ' cannot take @inherit')
        require(values <= accepted, f'{key}: the Core does not accept {sorted(values - accepted)}')
    for key in ('experimental.position_invariance', 'experimental.moltenvk_async_submits'):
        require(entries[key][0] == 'GAME_SETTING' and entries[key][1] == 'RPCS3_IOS_SETTING_CHOICE', key + ' entry kind')

    # "@inherit" in the API, before any value parsing, never for text keys or full custom configs.
    setter = block(api, 'extern "C" rpcs3_ios_status rpcs3_ios_set_game_setting(', '\n}\n')
    inherit = setter.index('if (std::string_view{value} == "@inherit")')
    require(inherit < setter.index('if (std::string_view{key} == "gpu.resolution")') < setter.index('update_current_setting('),
            '@inherit is not handled first')
    branch = setter[inherit:setter.index('if (std::string_view{key} == "gpu.resolution")')]
    for needle in ('setting->kind != RPCS3_IOS_SETTING_BOOLEAN && setting->kind != RPCS3_IOS_SETTING_CHOICE',
                   'if (has_custom_config)', 'rpcs3::ios::remove_game_setting_override(title_id, key)',
                   'return RPCS3_IOS_SETTING_INVALID;', 'return RPCS3_IOS_OK;'):
        require(needle in branch, '@inherit branch lacks ' + needle)
    require('bool remove_game_setting_override(std::string_view title_id, std::string_view key) noexcept;' in settings_h and
            'std::string game_setting_override_keys(std::string_view title_id);' in settings_h, 'settings declarations')

    # Boot line order and the unchanged sparse-override call.
    require('if (!rpcs3::ios::apply_game_setting_overrides(m_title_id))' in system, 'sparse override call changed')
    require(re.search(r'if \(ios_sparse_overrides_applied\)\n\t+\{\n\t+ios_override_keys = '
                      r'rpcs3::ios::game_setting_override_keys\(m_title_id\);', system), 'keys read when not applied')
    rsx = system.index('format_config_rsx_line(ios_rsx)')
    require(rsx < system.index('format_config_layers_line(ios_layers)') and system.count('format_config_rsx_line(') == 1,
            'the rsx part is not emitted once, before the main line')
    require(system.index('rpcs3::ios::resolve_experimental_policy();') < rsx, 'rsx part before the policy resolution')
    return {'catalogue': {key: list(entries[key]) for key in KEYS},
            'files_sha256': {name: sha((source / name).read_bytes()) for name in (
                'rpcs3/Emu/system_config.h', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSSettings.cpp',
                'rpcs3/ios/RPCS3IOSSettings.h', 'rpcs3/ios/RPCS3IOS.cpp', 'rpcs3/Emu/System.cpp',
                'rpcs3/ios/RPCS3IOSBootDiagnostics.h')}}


# --- executed ---------------------------------------------------------------------
STUBS = r'''
#include <cstdio>
#include <map>
#include <string>
#include <string_view>
#include <utility>
#include <vector>
// Explicit storage stubs: the YAML file is a per-title vector; nothing else is emulated.
namespace fs {
enum class error { ok, noent, acces };
thread_local error g_tls_error = error::ok;
static std::map<std::string, bool> removable;
static int removals = 0;
inline bool remove_file(const std::string& path) {
	++removals;
	const auto found = removable.find(path);
	if (found == removable.end()) { g_tls_error = error::noent; return false; }
	if (!found->second) { g_tls_error = error::acces; return false; }
	removable.erase(found);
	return true;
}
}
static std::map<std::string, std::vector<std::pair<std::string, std::string>>> files;
static bool read_fails = false;
static int writes = 0;
static std::string game_setting_overrides_path(std::string_view title) { return "overrides/" + std::string{title} + ".yml"; }
static bool read_game_setting_overrides(std::string_view title, std::vector<std::pair<std::string, std::string>>& values) {
	values.clear();
	if (read_fails || title.empty()) return false;
	if (const auto found = files.find(std::string{title}); found != files.end()) values = found->second;
	return true;
}
static bool write_game_setting_overrides(std::string_view title, const std::vector<std::pair<std::string, std::string>>& values) {
	++writes;
	files[std::string{title}] = values;
	fs::removable[game_setting_overrides_path(title)] = true;
	return true;
}
'''

DRIVER = r'''
static int failures = 0;
static void check(bool condition, const char* what) { if (!condition) { std::fprintf(stderr, "FAIL: %s\n", what); ++failures; } }
static void put(const char* title, std::vector<std::pair<std::string, std::string>> values) {
	files[title] = std::move(values);
	fs::removable[game_setting_overrides_path(title)] = true;
}
int main() {
	check(game_setting_override_keys("BLES00158").empty(), "no file: no keys");
	put("BLES00158", {{"gpu.zcull_accuracy", "Approximate"}, {"debug.disable_occlusion", "true"}});
	check(game_setting_override_keys("BLES00158") == "gpu.zcull_accuracy,debug.disable_occlusion", "keys in file order");
	read_fails = true;
	check(game_setting_override_keys("BLES00158").empty(), "invalid file: no keys");
	check(!remove_game_setting_override("BLES00158", "gpu.zcull_accuracy"), "invalid file: removal fails");
	read_fails = false;

	writes = 0;
	check(remove_game_setting_override("BLES00158", "gpu.shader_precision") && writes == 0, "missing key: success, no write");
	check(remove_game_setting_override("BLES00158", "gpu.zcull_accuracy") && writes == 1, "one key removed and written");
	check(files["BLES00158"].size() == 1 && files["BLES00158"][0].first == "debug.disable_occlusion" &&
		files["BLES00158"][0].second == "true", "the other key and its value are kept");

	fs::removals = 0;
	check(remove_game_setting_override("BLES00158", "debug.disable_occlusion") && fs::removals == 1 && writes == 1,
		"last key: the file is removed, not rewritten empty");
	check(!fs::removable.count(game_setting_overrides_path("BLES00158")), "file gone");

	put("BLES01717", {{"debug.emulate_depth_compare", "true"}});
	fs::removable.erase(game_setting_overrides_path("BLES01717"));
	check(remove_game_setting_override("BLES01717", "debug.emulate_depth_compare"), "already absent file counts as removed");
	put("BLUS30089", {{"gpu.shader_precision", "Low"}});
	fs::removable[game_setting_overrides_path("BLUS30089")] = false;
	check(!remove_game_setting_override("BLUS30089", "gpu.shader_precision"), "a refused removal is reported");

	put("NPEB00001", {{"a", "1"}, {"b", "2"}, {"a", "3"}});
	check(remove_game_setting_override("NPEB00001", "a") && files["NPEB00001"].size() == 1 &&
		files["NPEB00001"][0].first == "b", "every copy of a duplicated key is removed");
	if (failures) return 1;
	std::printf("PASS: override key listing and single-key removal (extracted Core bodies)\n");
	return 0;
}
'''


def extract_function(text: str, signature: str) -> str:
    start = text.index(signature)
    end = text.index('\n}\n', start) + 3
    return text[start:end]


def sanitizer_flags(compiler: str, work: Path) -> list[str]:
    probe = work / 'probe.cpp'
    probe.write_text('int main(){return 0;}\n')
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    ok = subprocess.run([compiler, *flags, str(probe), '-o', str(work / 'probe')], capture_output=True).returncode == 0
    return flags if ok else []


def compile_run(compiler, sources, output, includes, flags):
    command = [compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, *includes, *map(str, sources), '-o', str(output)]
    built = subprocess.run(command, capture_output=True, text=True)
    require(built.returncode == 0, 'compile failed: ' + built.stdout + built.stderr)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    result = subprocess.run([str(output)], capture_output=True, text=True, timeout=120, env=env)
    require(result.returncode == 0 and 'runtime error' not in result.stderr, result.stdout + result.stderr)
    return result.stdout.strip().splitlines()[-1]


def executed(source: Path, compiler: str, sanitize: bool) -> dict:
    settings = (source / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text(encoding='utf-8')
    bodies = [extract_function(settings, 'std::string game_setting_override_keys(std::string_view title_id)\n{'),
              extract_function(settings, 'bool remove_game_setting_override(\n\tstd::string_view title_id,\n\tstd::string_view key) noexcept\n{')]
    with tempfile.TemporaryDirectory(prefix='graphics612-') as tmp:
        work = Path(tmp)
        flags = sanitizer_flags(compiler, work) if sanitize else []
        unit = work / 'overrides.cpp'
        unit.write_text(STUBS + '\n'.join(bodies) + DRIVER)
        overrides = compile_run(compiler, [unit], work / 'overrides', [], flags)
        includes = ['-I' + str(source), '-I' + str(source / 'rpcs3'), '-I' + str(source / 'rpcs3/ios')]
        rsx = compile_run(compiler, [NATIVE_RSX], work / 'rsx', includes, flags)
    return {'compiler': subprocess.run([compiler, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'sanitizers': bool(flags), 'override_logic': overrides, 'rsx_line': rsx,
            'extracted_bodies_sha256': sha('\n'.join(bodies).encode())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, help='materialized candidate Core (Core 612)')
    parser.add_argument('--sanitize', action='store_true', help='ASan/UBSan when the toolchain provides them')
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'scope': 'host only; no game, Metal, MoltenVK or iPhone', 'app': app_contract()}
    print('PASS: app contract (whitelist = page levers, @inherit, routing, reboot after refusal, capture region, 12 locales)')
    if args.source:
        source = args.source.resolve()
        report['core'] = core_contract(source)
        print('PASS: Core contract (Position Invariance cfg, catalogue spellings, @inherit branch, rsx line order)')
        require(args.cxx, 'a C++ compiler is required with --source')
        report['executed'] = executed(source, args.cxx, args.sanitize)
        print(report['executed']['override_logic'])
        print(report['executed']['rsx_line'])
    else:
        report['core'] = 'skipped: --source not given'
        print('SKIP: Core contract and executed checks (--source not given)')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
