#!/usr/bin/env python3
"""Offline crypto, input-identity, clean-miss and unchanged-recipe checks."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cache', ROOT / 'build-utils/ipa_build_cache.py')
cache = importlib.util.module_from_spec(spec); spec.loader.exec_module(cache)
KEY = b'a dedicated test-only secret key!!'
ENV = dict(GITHUB_REPOSITORY=cache.REPO, GITHUB_REF=cache.REF, GITHUB_EVENT_NAME='push',
           GITHUB_WORKFLOW_REF=cache.WORKFLOW, GITHUB_SHA='1' * 40, GITHUB_RUN_ID='123',
           GITHUB_RUN_ATTEMPT='1', REWINDBOX_BUILD_CACHE_KEY=KEY.decode(), BUILD_NUMBER='733')


class HostCache(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(ENV, GITHUB_OUTPUT=str(self.root / 'outputs'))
        self.write('lib/main.dart', b'unchanged source')
        self.write('pubspec.yaml', b'name: app\nversion: 1.2.3+733\n')
        self.write('pubspec.lock', b'locked')
        self.write('.dart-defines.json', b'{"SCREENSCRAPER_DEV_PASSWORD":"never use as cache key"}')
        self.write('.dart_tool/package_config.json', b'{"packages":[{"rootUri":"../"}],"generated":"2026-11-13T00:00:00Z","generatorVersion":"3.12"}')
        self.write('.flutter-plugins-dependencies', b'{"plugins":{},"date_created":"2026-11-13 00:00:00.123456"}')
        self.write('ios/Runner.xcodeproj/project.pbxproj', b'current generated project\nCURRENT_PROJECT_VERSION = 733;\n')
        self.write('ios/Flutter/Generated.xcconfig', b'FLUTTER_BUILD_NUMBER=733\nFLAGS=unchanged\n')
        self.write('ios/Runner/Info.plist', plistlib.dumps(dict(CFBundleVersion='733', CFBundleShortVersionString='1.2.3')))
        for package in ('rpcs3_internal_bridge', 'melonx_internal_bridge'):
            self.write(f'packages/{package}/ios/{package}.podspec', b's.preserve_paths = "Frameworks"\ns.source_files = "Classes/*"')
        for name in cache.POSTLINK: self.write(name, b'first core')
        self.write(cache.CORE_INFO, plistlib.dumps(dict(CFBundleVersion='733', CFBundleIdentifier='core')))
        self.write('packages/melonx_internal_bridge/ios/Classes/ABI.h', b'ABI1')
        self.write('build/delivery/environment.json', cache.canonical(dict(xcode='Xcode 26.3', sdk='26.3',
                   flutter=dict(frameworkRevision='rev', engineRevision='engine'), cocoaPods='1.16', ruby='3.4', macOS='26.1')))
        self.write('.github/workflows/standard-delivery.yml', (ROOT / '.github/workflows/standard-delivery.yml').read_bytes())
        self.write(cache.DD + '/Build/Intermediates.noindex/bridge.o', b'compiled unchanged host')
        self.write(cache.DD + '/Build/Products/Runner.app/Runner', b'pre-embed host')
        (self.root / cache.CACHE).mkdir()
        self.addCleanup(patch.stopall)
        # Capture toolchain calls, but let real OpenSSL encrypt/decrypt fixtures.
        patch.object(cache.subprocess, 'check_output', return_value=b'actual test toolchain').start()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
        return path

    def state(self): return cache.inputs(self.root, self.env)
    def identity(self): return cache.key_for(self.state(), KEY)

    def test_roundtrip_authenticated_preembed_and_fresh_version_timestamps(self):
        source = self.root / 'lib/main.dart'
        os.utime(source, ns=(1_000_000_000, 1_000_000_000))
        state = self.state(); cache.pack(self.root, state, KEY, self.env)
        blob = self.root / cache.CACHE / 'state.enc'
        self.assertNotIn(b'compiled unchanged host', blob.read_bytes())
        # Current Core and build metadata change after the pre-embed snapshot.
        for name in cache.POSTLINK: self.write(name, b'new core for current delivery')
        self.env['BUILD_NUMBER'] = '734'
        self.write('ios/Runner.xcodeproj/project.pbxproj', b'current generated project\nCURRENT_PROJECT_VERSION = 734;\n')
        info = self.write('ios/Runner/Info.plist', plistlib.dumps(dict(CFBundleVersion='734', CFBundleShortVersionString='1.2.3')))
        self.write(cache.CORE_INFO, plistlib.dumps(dict(CFBundleVersion='734', CFBundleIdentifier='core')))
        self.write('ios/Flutter/Generated.xcconfig', b'FLUTTER_BUILD_NUMBER=734\nFLAGS=unchanged\n')
        self.write('pubspec.yaml', b'name: app\nversion: 1.2.3+734\n')
        current_mtime = info.stat().st_mtime_ns
        current = self.state(); self.assertEqual(state['identity'], current['identity'])
        os.utime(source, ns=(9_000_000_000, 9_000_000_000))
        shutil.rmtree(self.root / cache.DD)
        cache.unpack(self.root, current, KEY)
        self.assertEqual(source.stat().st_mtime_ns, 1_000_000_000)
        self.assertEqual(info.stat().st_mtime_ns, current_mtime)
        self.assertEqual(plistlib.loads(info.read_bytes())['CFBundleVersion'], '734')
        self.assertEqual((self.root / cache.DD / 'Build/Products/Runner.app/Runner').read_bytes(), b'pre-embed host')
        for name in cache.POSTLINK: self.assertEqual((self.root / name).read_bytes(), b'new core for current delivery')

    def test_source_generated_abi_linked_dependency_toolchain_options_invalidate(self):
        original = self.identity()
        for name in ('lib/main.dart', 'ios/Runner.xcodeproj/project.pbxproj',
                     'packages/melonx_internal_bridge/ios/Classes/ABI.h',
                     'packages/melonx_internal_bridge/ios/Frameworks/NewHeader.h',
                     'packages/stikjit_bridge/ios/Frameworks/StikJIT', '.dart-defines.json', 'pubspec.lock'):
            path = self.root / name; previous = path.read_bytes() if path.exists() else None
            self.write(name, b'changed input'); self.assertNotEqual(self.identity(), original, name)
            if previous is None: path.unlink()
            else: path.write_bytes(previous)
        environment = self.root / 'build/delivery/environment.json'
        previous = environment.read_bytes(); value = json.loads(previous)
        value['flutter']['engineRevision'] = 'different'; environment.write_bytes(cache.canonical(value))
        self.assertNotEqual(self.identity(), original); environment.write_bytes(previous)
        self.env['OTHER_LDFLAGS'] = '-changed'; self.assertNotEqual(self.identity(), original)

    def test_only_delivery_and_generation_timestamps_normalize(self):
        identity = self.identity()
        self.write('.flutter-plugins-dependencies', b'{"plugins":{},"date_created":"2026-11-14 00:00:00.123456"}')
        self.write('.dart_tool/package_config.json', b'{"packages":[{"rootUri":"../"}],"generated":"2026-11-14T00:00:00Z","generatorVersion":"3.12"}')
        self.assertEqual(self.identity(), identity)
        self.write('pubspec.yaml', b'name: app\nversion: 1.2.4+733\n'); self.assertNotEqual(self.identity(), identity)
        dependency = 'ios/Pods/Dependency.framework/Info.plist'
        self.write(dependency, plistlib.dumps(dict(CFBundleVersion='733'))); identity = self.identity()
        self.write(dependency, plistlib.dumps(dict(CFBundleVersion='734'))); self.assertNotEqual(self.identity(), identity)
        data = plistlib.dumps(dict(CFBundleVersion='unknown'))
        self.assertEqual(plistlib.loads(cache.normalized('ios/Runner/Info.plist', data, '733'))['CFBundleVersion'], 'unknown')

    def test_core_linkage_unknown_disables_cache_identity(self):
        self.write('ios/Runner.xcodeproj/project.pbxproj', b'link MeloNXCore.framework')
        with self.assertRaises(ValueError): self.state()

    def test_ciphertext_header_tag_wrongkey_and_inputs_rejected_atomically(self):
        state = self.state(); cache.pack(self.root, state, KEY, self.env)
        path = self.root / cache.CACHE / 'state.enc'; original = path.read_bytes()
        for position in (0, len(cache.MAGIC) + 5, len(original) // 2, len(original) - 1):
            changed = bytearray(original); changed[position] ^= 1; path.write_bytes(changed)
            with self.assertRaises(Exception): cache.unpack(self.root, state, KEY)
            self.assertEqual((self.root / cache.DD / 'Build/Intermediates.noindex/bridge.o').read_bytes(), b'compiled unchanged host')
        path.write_bytes(original)
        with self.assertRaises(ValueError): cache.unpack(self.root, state, b'another dedicated cache secret key')
        changed = copy.deepcopy(state); changed['identity']['inputs']['lib/main.dart'] = '0' * 64
        with self.assertRaises(ValueError): cache.unpack(self.root, changed, KEY)

    def test_missing_key_untrusted_missing_corrupt_all_clean_miss(self):
        for field, value in [('REWINDBOX_BUILD_CACHE_KEY', ''), ('GITHUB_EVENT_NAME', 'pull_request'),
                             ('GITHUB_REF', 'refs/heads/main'), ('GITHUB_WORKFLOW_REF', 'other'),
                             ('GITHUB_REPOSITORY', 'attacker/repo')]:
            env = dict(self.env); env[field] = value
            cache.main('prepare', self.root, env)
            self.assertEqual(json.loads((self.root / 'build/delivery/host-cache.json').read_bytes())['prepare']['status'], 'disabled')
        cache.main('prepare', self.root, self.env)
        for blob in (None, b'corrupt cache'):
            if blob is not None: self.write(cache.CACHE + '/state.enc', blob)
            self.write(cache.DD + '/stale.app', b'must not survive')
            cache.main('restore', self.root, self.env)
            self.assertFalse((self.root / cache.DD).exists())
            self.assertEqual(json.loads((self.root / 'build/delivery/host-cache.json').read_bytes())['restore']['status'], 'miss')

    def test_snapshot_symlink_escape_and_oversize_rejected(self):
        (self.root / cache.DD / 'escape').symlink_to(self.root / '.dart-defines.json')
        with self.assertRaises(ValueError): cache.pack(self.root, self.state(), KEY, self.env)
        (self.root / cache.DD / 'escape').unlink()
        with patch.object(cache, 'MAX_BYTES', 1):
            with self.assertRaises(ValueError): cache.pack(self.root, self.state(), KEY, self.env)

    def test_archive_traversal_symlink_hardlink_special_and_limit(self):
        state = self.state()
        real_crypt = cache.crypt
        for kind in ('traversal', 'symlink', 'hardlink', 'special', 'duplicate'):
            def malicious(source, destination, key, iv, decrypt=False):
                if decrypt: return real_crypt(source, destination, key, iv, True)
                # Retain the valid manifest, root and payload; only the added
                # malicious member differs from a successful round trip.
                with tarfile.open(source, 'r:gz') as original:
                    members = [(member, original.extractfile(member).read() if member.isfile() else None)
                               for member in original.getmembers()]
                with tarfile.open(source, 'w:gz') as archive:
                    for member, data in members:
                        archive.addfile(member, io.BytesIO(data) if data is not None else None)
                    name = '../escape' if kind == 'traversal' else 'DerivedData/entry'
                    member = tarfile.TarInfo(name)
                    if kind in ('symlink', 'hardlink'):
                        member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE; member.linkname = '../escape'
                    if kind == 'special': member.type = tarfile.FIFOTYPE
                    if kind == 'duplicate': member.name = 'DerivedData/Build/Intermediates.noindex/bridge.o'
                    archive.addfile(member)
                real_crypt(source, destination, key, iv)
            with patch.object(cache, 'crypt', malicious): cache.pack(self.root, state, KEY, self.env)
            reason = {'traversal': 'archive path', 'duplicate': 'archive duplicate'}.get(kind, 'archive type')
            with self.assertRaisesRegex(ValueError, '^' + reason + '$'):
                cache.unpack(self.root, state, KEY)
            self.assertEqual((self.root / cache.DD / 'Build/Intermediates.noindex/bridge.o').read_bytes(),
                             b'compiled unchanged host')


class Recipe(unittest.TestCase):
    def test_unchanged_recipe_and_safe_cache_order(self):
        workflow = (ROOT / '.github/workflows/standard-delivery.yml').read_text()
        names = ['Verify optional host cache and unchanged recipe guards', 'Determine exact optional host cache identity', 'Restore encrypted host intermediates by exact identity',
                 'Authenticate optional cache or use a clean build', 'Snapshot encrypted host state before any runtime embedding',
                 'Save only the encrypted pre-embed host state after final validation']
        reduced = workflow
        for name in names:
            pattern = r'^    - name: ' + re.escape(name) + r'\n.*?(?=^    - |\Z)'
            reduced, count = re.subn(pattern, '', reduced, flags=re.M | re.S)
            self.assertEqual(count, 1, name)
        # Exact pre-change workflow: every compile, proof, embed, sign, validate,
        # encrypt and upload step is unchanged. Update only after reviewed edits.
        self.assertEqual(hashlib.sha256(reduced.encode()).hexdigest(), '4a77e2d5ab5bb17b0ce70ed2c763f90cff7911aef5452b8a7e48256032ade80f')
        self.assertLess(workflow.index(names[3]), workflow.index('    - name: Compile Release device binary'))
        self.assertLess(workflow.index('neostation-fast-xcodebuild.log"\n', workflow.index('    - name: Compile Release device binary')),
                        workflow.index(names[4]))
        self.assertLess(workflow.index(names[4]), workflow.index('    - name: Embed NeoPlay source identity'))
        self.assertLess(workflow.index('version-validation.json'), workflow.index(names[5]))
        self.assertNotIn('restore-keys:', workflow)
        self.assertEqual(workflow.count('REWINDBOX_BUILD_CACHE_KEY:'), 3)
        self.assertEqual(workflow.count('path: .ci-host-cache/state.enc'), 2)
        compile_step = workflow.split('    - name: Compile Release device binary', 1)[1].split('    - name:', 1)[0]
        self.assertNotIn('if:', compile_step)
        self.assertNotIn('continue-on-error:', compile_step)
        self.assertNotIn('REWINDBOX_BUILD_CACHE_KEY', compile_step)
        for token in ('xcodebuild -workspace', 'set -euo pipefail', ' build \\'):
            self.assertIn(token, compile_step)


if __name__ == '__main__': unittest.main()
