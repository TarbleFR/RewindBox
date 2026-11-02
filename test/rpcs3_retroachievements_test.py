#!/usr/bin/env python3
"""Contracts of the PS3 RetroAchievements integration (NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1).

Core side: build-utils/rpcs3/retroachievements-core.patch is a STAGED, additive
delta over the canonical Core postimage. It is not part of embedded-core.patch
yet: folding it (build-utils/rpcs3/fold_retroachievements_core_patch.py) changes
the Core identity that every IPA workflow checks, so it belongs to an
authorized Core build. Until then the host resolves the optional symbols with
dlsym and a Core without them reports "not available for this core".

    python3 test/rpcs3_retroachievements_test.py [--source <materialized Core tree>]

--source (optional) proves that the staged patch applies to, or is already
applied in, a tree produced by build-utils/materialize_rpcs3_core.py.
--sanitize (optional) compiles and runs the two C++ host tests under
AddressSanitizer and UndefinedBehaviorSanitizer, every report fatal.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGED = ROOT / 'build-utils/rpcs3/retroachievements-core.json'
CANONICAL = ROOT / 'build-utils/rpcs3/canonical-source.json'
BRIDGE = ROOT / 'packages/rpcs3_internal_bridge/ios'
CLASSES = BRIDGE / 'Classes'
PLUGIN = CLASSES / 'Rpcs3InternalBridgePlugin.mm'
CLIENT = CLASSES / 'Rpcs3Achievements.mm'
LIBRETRO_RCHEEVOS = ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/rcheevos'
RPCS3_RCHEEVOS = BRIDGE / 'ThirdParty/rcheevos'
SOURCE_TREE = None
SANITIZE = False


def sanitizer_flags() -> list:
    return ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'] if SANITIZE else []


def sanitizer_env() -> dict:
    import os
    return dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def lf_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def parse_patch(text: str) -> dict:
    """{path: {'new': bool, 'hunks': [[(sign, line), ...], ...]}} of a git diff."""
    files, current, hunk = {}, None, None
    for line in text.split('\n'):
        if line.startswith('diff --git '):
            path = line.split(' b/', 1)[1]
            current = files[path] = {'new': False, 'hunks': []}
            hunk = None
        elif current is None:
            continue
        elif line.startswith('new file mode'):
            current['new'] = True
        elif line.startswith('@@'):
            hunk = []
            current['hunks'].append(hunk)
        elif hunk is not None and line[:1] in ('+', '-', ' ') and not line.startswith(('+++ ', '--- ')):
            hunk.append((line[0], line[1:]))
    return files


def added(entry: dict) -> list:
    return [text for hunk in entry['hunks'] for sign, text in hunk if sign == '+']


def code_only(text: str) -> str:
    """Source without // comments (comments may name what the code avoids)."""
    return '\n'.join(line.split('//', 1)[0] for line in text.split('\n'))


def struct_fields(text: str, name: str) -> list:
    body = re.search(r'typedef struct ' + name + r'\s*\{(.*?)\}\s*' + name + ';', text, re.S)
    assert body, name
    fields = []
    for line in body.group(1).split('\n'):
        line = line.split('//', 1)[0].strip()
        if line:
            fields.append(re.sub(r'\s+', ' ', line.rstrip(';')))
    return fields


class StagedCorePatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(read(STAGED))
        cls.patch_path = ROOT / cls.manifest['patch']
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.files = parse_patch(cls.patch_bytes.decode('utf-8'))
        cls.canonical = json.loads(read(CANONICAL))

    def test_manifest_pins_the_patch_and_its_scope(self):
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), self.manifest['patch_sha256'])
        self.assertEqual(self.manifest['marker'], 'NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1')
        self.assertEqual(sorted(self.files), sorted(self.manifest['files_after_sha256']))
        self.assertEqual(sorted(p for p, e in self.files.items() if e['new']), self.manifest['new_files'])
        self.assertEqual(self.manifest['upstream_commit'], self.canonical['upstream_commit'])
        for flag in ('core_build_run', 'ios_build_run', 'iphone_validation_run', 'folded_into_canonical_delta'):
            self.assertIsInstance(self.manifest[flag], bool, flag)
        if not self.manifest['folded_into_canonical_delta']:
            for flag in ('core_build_run', 'ios_build_run', 'iphone_validation_run'):
                self.assertIs(self.manifest[flag], False, flag)

    def test_patch_matches_the_canonical_postimages(self):
        folded = self.manifest['folded_into_canonical_delta']
        if not folded:
            # A Core change elsewhere in the canonical delta keeps this patch
            # valid; a change to one of its five files means it must be rebased.
            for path, before in self.manifest['files_before_sha256'].items():
                self.assertEqual(self.canonical['files_sha256'].get(path), before,
                                 f'{path} changed in the canonical delta: rebase the staged RA patch')
            for path in self.manifest['new_files']:
                self.assertNotIn(path, self.canonical['files_sha256'])
        else:
            # Folded by fold_retroachievements_core_patch.py: the canonical
            # delta carries exactly these postimages.
            for path, after in self.manifest['files_after_sha256'].items():
                self.assertEqual(self.canonical['files_sha256'].get(path), after, path)
            self.assertTrue(self.canonical['retroachievements_core']['folded_into_canonical_delta'])

    def test_canonical_delta_and_core_identity_follow_the_fold_state(self):
        # Every IPA workflow requires these to equal the commit of the prebuilt
        # Core; the staged patch must not change them before a Core build.
        delta = (ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()
        self.assertEqual(hashlib.sha256(delta).hexdigest(), self.canonical['patch_sha256'])
        self.assertEqual(b'RETROACHIEVEMENTS' in delta, self.manifest['folded_into_canonical_delta'])
        # The host keeps the optional symbols out of the pinned Core ABI header.
        self.assertNotIn('rpcs3_ios_ra_', read(CLASSES / 'Rpcs3CoreABI.h'))

    def test_patch_is_purely_additive_and_keeps_abi_30(self):
        for path, entry in self.files.items():
            removed = [text for hunk in entry['hunks'] for sign, text in hunk if sign == '-']
            self.assertEqual(removed, [], path)
            for text in added(entry):
                self.assertNotRegex(code_only(text), r'RPCS3_IOS_ABI_VERSION|"abi":', path)
        self.assertEqual(self.manifest['abi_version'], 30)
        self.assertIs(self.manifest['abi_version_changed'], False)

    def test_exports_are_declared_defined_listed_and_optional_for_the_host(self):
        exports = [t.strip() for t in added(self.files['rpcs3/ios/RPCS3IOS.exports'])]
        names = [e[1:] for e in exports]
        self.assertEqual(names, self.manifest['exports_added'])
        declared = re.findall(r'RPCS3_IOS_EXPORT [^(]*?\b(rpcs3_ios_ra_\w+)\(',
                              '\n'.join(added(self.files['rpcs3/ios/RPCS3IOS.h'])))
        defined = re.findall(r'extern "C" [^(]*?\b(rpcs3_ios_ra_\w+)\(',
                             '\n'.join(added(self.files['rpcs3/ios/RPCS3IOS.cpp'])))
        self.assertEqual(sorted(declared), sorted(names))
        self.assertEqual(sorted(defined), sorted(names))
        host = read(PLUGIN) + read(CLIENT)
        self.assertNotRegex(host, r'LOAD\("rpcs3_ios_ra_')  # never a required symbol
        for name in names:
            self.assertIn(f'dlsym(handle, "{name}")', read(CLIENT))

    def test_vblank_hook_runs_after_the_guest_event_on_ios_only(self):
        hunks = self.files['rpcs3/Emu/RSX/RSXThread.cpp']['hunks']
        hook = next(h for h in hunks if any('vblank_hook().notify' in t for _, t in h))
        lines = [t for _, t in hook]
        notify = next(i for i, t in enumerate(lines) if 'vblank_hook().notify' in t)
        self.assertTrue(any('sys_rsx_context_attribute(0x55555555, 0xFED' in t for t in lines[:notify]))
        self.assertIn('#ifdef RPCS3_IOS', lines[notify - 3:notify])
        self.assertIn('#endif', lines[notify + 1:notify + 2])

    def test_boot_record_names_the_base_library_entry(self):
        cpp = '\n'.join(added(self.files['rpcs3/ios/RPCS3IOS.cpp']))
        self.assertIn('rpcs3::ios::achievements::last_boot().set(game->title_id, game->path);', cpp)
        self.assertEqual(cpp.count('last_boot().clear()'), 3)  # game, XMB and Big Picture boots
        block = code_only(cpp.split('// NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1: optional RetroAchievements hooks', 1)[1])
        for forbidden in ('set_error(', 'g_api_mutex', 'emit_log('):
            self.assertNotIn(forbidden, block)
        self.assertIn('vm::try_access(at, out, count, false)', cpp)

    def test_session_info_layout_matches_the_host_copy(self):
        core = '\n'.join(added(self.files['rpcs3/ios/RPCS3IOS.h']))
        host = read(CLASSES / 'Rpcs3AchievementsABI.h')
        self.assertEqual(struct_fields(core, 'rpcs3_ios_ra_session_info'),
                         struct_fields(host, 'rpcs3_ios_ra_session_info'))
        self.assertIn('#define RPCS3_IOS_RA_API_VERSION 1u', core)
        self.assertIn('#define RPCS3_IOS_RA_API_VERSION 1u', host)

    def test_core_hooks_compile_and_behave_on_the_host(self):
        compiler = shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('no C++ compiler')
        header = '\n'.join(added(self.files['rpcs3/ios/RPCS3IOSAchievements.h'])) + '\n'
        declarations = '\n'.join(added(self.files['rpcs3/ios/RPCS3IOS.h'])) + '\n'
        cpp_hunk = next(h for h in self.files['rpcs3/ios/RPCS3IOS.cpp']['hunks']
                        if any('rpcs3_ios_ra_get_session_info' in t for _, t in h))
        exports = '\n'.join(t for s, t in cpp_hunk if s == '+') + '\n'
        with tempfile.TemporaryDirectory(prefix='rpcs3-ra-core-') as tmp:
            work = Path(tmp)
            (work / 'RPCS3IOSAchievements.h').write_text(header)
            (work / 'ra_declarations.inc').write_text(declarations)
            (work / 'ra_exports.inc').write_text(exports)
            binary = work / 'core_test'
            subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                            *sanitizer_flags(), '-pthread', '-I', str(work),
                            str(ROOT / 'test/rpcs3_retroachievements_core_test.cpp'), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120 if SANITIZE else 60, env=sanitizer_env())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('runtime error', result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_optional_source_tree(self):
        if SOURCE_TREE is None:
            self.skipTest('--source not given')
        files = self.manifest['files_before_sha256']
        state = {p: lf_sha256((SOURCE_TREE / p).read_bytes()) for p in files}
        if state == files and not any((SOURCE_TREE / p).exists() for p in self.manifest['new_files']):
            command = ['git', '-C', str(SOURCE_TREE), 'apply', '--check', str(self.patch_path)]
        else:
            for path, after in self.manifest['files_after_sha256'].items():
                self.assertEqual(lf_sha256((SOURCE_TREE / path).read_bytes()), after, path)
            command = ['git', '-C', str(SOURCE_TREE), 'apply', '--check', '--reverse', str(self.patch_path)]
        subprocess.run(command, check=True)


class HostClient(unittest.TestCase):
    def test_rcheevos_copy_is_the_pinned_libretro_copy_without_its_adapter(self):
        theirs = {p.relative_to(LIBRETRO_RCHEEVOS): p for p in LIBRETRO_RCHEEVOS.rglob('*') if p.is_file()}
        ours = {p.relative_to(RPCS3_RCHEEVOS): p for p in RPCS3_RCHEEVOS.rglob('*') if p.is_file()}
        self.assertEqual(sorted(set(theirs) - set(ours)),
                         [Path('src/rc_libretro.c'), Path('src/rc_libretro.h')])
        self.assertFalse(set(ours) - set(theirs))
        for relative, path in ours.items():
            self.assertEqual(path.read_bytes(), theirs[relative].read_bytes(), relative)
        self.assertIn('v12.5.0', read(RPCS3_RCHEEVOS / 'SOURCE.txt'))
        self.assertIn('MIT', read(RPCS3_RCHEEVOS / 'LICENSE'))

    def test_podspec_builds_the_client_with_hashing_and_the_central_session(self):
        spec = read(BRIDGE / 'rpcs3_internal_bridge.podspec')
        for needle in ("'ThirdParty/rcheevos/src/**/*.{h,c}'", "RC_CLIENT_SUPPORTS_HASH=1",
                       "s.dependency 'retro_achievements_session'", "s.dependency 'achievement_translation'",
                       "s.ios.deployment_target = '18.0'", 'ThirdParty/rcheevos/include'):
            self.assertIn(needle, spec)
        public = re.search(r'public_header_files = \[(.*?)\]', spec, re.S).group(1)
        self.assertNotIn('rcheevos', public)
        self.assertNotIn('Achievements', public)

    def test_ps3_identification_and_memory_map(self):
        client = read(CLIENT)
        self.assertIn('RC_CONSOLE_PLAYSTATION_3', client)
        consoles = read(RPCS3_RCHEEVOS / 'src/rcheevos/consoleinfo.c')
        regions = re.search(r'_rc_memory_regions_playstation3\[\] = \{(.*?)\};', consoles, re.S).group(1)
        # Guest virtual addresses: real_address == start_address (identity read).
        for start, end, real in re.findall(r'\{ (0x[0-9A-F]+)U, (0x[0-9A-F]+)U, (0x[0-9A-F]+)U', regions):
            self.assertEqual(start, real)
        self.assertIn('rc_client_set_allow_background_memory_reads(client, 0)', client)

    def test_client_never_logs_account_data(self):
        client = read(CLIENT)
        self.assertNotIn('NSLog', client)
        calls = re.findall(r'note:@"[^"]+" detail:(.*?)\];\n', client, re.S)
        self.assertGreater(len(calls), 8)
        for call in calls:
            self.assertNotRegex(call, r'\b(username|token|url|URL|body|post_data|_hashPath|content_path)\b|request->', call)
        self.assertIn('The URL and body carry the account token: never logged.', client)

    def test_frames_never_block_the_vblank_thread(self):
        client = read(CLIENT)
        frame = client.split('- (void)processFrame {', 1)[1].split('\n}\n', 1)[0]
        vblank = frame.split('lock.unlock();', 1)[0]  # the rest runs later on the client queue
        self.assertIn('std::try_to_lock', vblank)
        self.assertNotIn('lock_guard', vblank)
        self.assertIn('dispatch_async(_queue', frame.split('lock.unlock();', 1)[1])
        self.assertNotIn('dispatch_sync', client)
        shutdown = client.split('- (void)shutdown {', 1)[1].split('\n}\n', 1)[0]
        self.assertLess(shutdown.index('set_frame_callback(NULL, NULL)'), shutdown.index('invalidateAndCancel'))
        self.assertLess(shutdown.index('set_frame_callback(NULL, NULL)'), shutdown.index('rc_client_destroy'))

    def test_bridge_owns_one_central_ticket_per_launch(self):
        plugin = read(PLUGIN)
        self.assertEqual(plugin.count('RBRATakeLaunchConfiguration(args, @"rpcs3")'), 1)
        self.assertIn('if (configuration) RBRAEndSession(configuration);', plugin)
        stop = plugin.split('- (void)stopAndDismiss:(FlutterResult)result {', 1)[1]
        self.assertLess(stop.index('[self.achievements suspendForRestart];'), stop.index('stop_emulation()'))
        self.assertLess(stop.index('[self.achievements resumeWithoutRestart];'), stop.index('return; // Keep Metal'))
        self.assertLess(stop.index('[self endAchievementSession];'), stop.index('NeoSwapStorage_EndSession();'))
        surface = plugin.split('RPCS3_DISPLAY_SURFACE_FAILED', 1)[0].rsplit('if (!controller || !controller.metalLayer.device)', 1)[1]
        self.assertIn('[self endAchievementSession];', surface)
        self.assertIn('if (bootStatus == 0)\n        [self startAchievementsForController:controller titleId:titleId savestateBoot:savestateId.length > 0];', plugin)

    def test_restarts_reset_rcheevos_and_hardcore_gates_hold(self):
        plugin = read(PLUGIN)
        command = plugin.split('- (void)performSessionCommand:', 1)[1].split('\n- (', 1)[0]
        self.assertIn('[achievements suspendForRestart];', command)
        self.assertIn('[achievements resumeAfterRestart:status == 0 savestateBoot:NO', command)
        state = plugin.split('- (void)performSessionStateAtSlot:', 1)[1].split('\n- (', 1)[0]
        self.assertLess(state.index('if (load && [self achievementHardcoreRestrictionsActive])'),
                        state.index('dispatch_async(_runtimeQueue'))
        self.assertIn('RBRALocalizedText(@"hardcoreBlocked"', state)
        self.assertIn('[achievements resumeAfterRestart:booted savestateBoot:savestateBoot', state)
        self.assertIn('if (enabled && [bridge achievementHardcoreRestrictionsActive]) { completion(NO); return; }', plugin)
        self.assertIn('restricted[@"hardcore"]=@YES', plugin)
        menu = read(CLASSES / 'Rpcs3SessionMenu.mm')
        self.assertIn('@"hardcore":@([raw[@"hardcore"] boolValue])', menu)

    def test_status_waits_for_the_running_game(self):
        client = read(CLIENT)
        frame = client.split('- (void)processFrame {', 1)[1].split('\n}\n', 1)[0]
        self.assertLess(frame.index('signalPresentationReady'), frame.index('if (_shutdown.load()'))
        self.assertIn('if (!_hookRegistered.load()) [self signalPresentationReady];', client)
        plugin = read(PLUGIN)
        self.assertIn('achievements.presentationReady = ^{', plugin)

    def test_policy_rules_compile_and_behave_on_the_host(self):
        compiler = shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('no C++ compiler')
        with tempfile.TemporaryDirectory(prefix='rpcs3-ra-policy-') as tmp:
            binary = Path(tmp) / 'policy_test'
            subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', *sanitizer_flags(), '-I', str(CLASSES),
                            str(ROOT / 'test/rpcs3_retroachievements_policy_test.cpp'), '-o', str(binary)],
                           check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120 if SANITIZE else 60, env=sanitizer_env())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('runtime error', result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_rcheevos_copy_compiles_without_the_libretro_adapter(self):
        compiler = shutil.which('gcc') or shutil.which('clang')
        if not compiler:
            self.skipTest('no C compiler')
        sources = sorted((RPCS3_RCHEEVOS / 'src').rglob('*.c'))
        self.assertFalse(any(p.name == 'rc_libretro.c' for p in sources))
        with tempfile.TemporaryDirectory(prefix='rpcs3-rcheevos-') as tmp:
            for source in sources:
                # gnu99, as Xcode compiles the pod (GNU dialect): strict c99 hides glibc's POSIX
                # strdup/strncasecmp on Linux runners while Darwin headers expose them either way.
                subprocess.run([compiler, '-std=gnu99', '-c', '-DRC_CLIENT_SUPPORTS_HASH=1',
                                '-I', str(RPCS3_RCHEEVOS / 'include'), '-I', str(RPCS3_RCHEEVOS / 'src'),
                                str(source), '-o', str(Path(tmp) / (source.stem + '.o'))], check=True)


class Wiring(unittest.TestCase):
    def test_central_hub_and_capability_accept_ps3_only_through_rpcs3(self):
        hub = read(ROOT / 'packages/retro_achievements_session/ios/Classes/RetroAchievementsSessionPlugin.m')
        self.assertIn('![@[@"melonx"] containsObject:engine]', hub)
        model = read(ROOT / 'lib/models/retro_achievements_session.dart')
        self.assertRegex(model, r"engine == 'rpcs3'\) \{[^}]*system == 'ps3'")

    def test_dart_launch_passes_one_ticket_and_releases_it_on_failure(self):
        service = read(ROOT / 'lib/services/rpcs3_internal_service.dart')
        launch = service.split('static Future<bool> launchTitle(', 1)[1].split('static Future<bool> stop()', 1)[0]
        self.assertIn("engine: 'rpcs3'", launch)
        self.assertIn("system: 'ps3'", launch)
        self.assertIn("raSessionId: raLaunch['raSessionId'] as String?", launch)
        self.assertEqual(launch.count('await raService.finishLaunch(raLaunch);'), 2)
        bridge = read(ROOT / 'packages/rpcs3_internal_bridge/lib/rpcs3_internal_bridge.dart')
        self.assertIn("'raSessionId': ?raSessionId,", bridge)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, default=None)
    parser.add_argument('--sanitize', action='store_true')
    args, rest = parser.parse_known_args()
    SOURCE_TREE = args.source.resolve() if args.source else None
    SANITIZE = args.sanitize
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
