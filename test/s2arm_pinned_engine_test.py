#!/usr/bin/env python3
"""Offline contract of the S2Arm instance of the pinned-engine component kind (no network, no build; runs on Linux).

    python3 -B test/s2arm_pinned_engine_test.py

Synthetic producers (frameworks, preparation xcframework, system data tree, licence texts) and a mocked API:
the pin is built and verified by build-utils/s2arm/engine_pin.py, the recipe downloads and embeds it through its own
generic functions (standard_delivery.engine_download / engine_evidence / engine_embed / engine_ipa), and
build-utils/s2arm/check_app.py checks the application. Accepted, refused and absent (a manifest without the
component behaves as the common line).
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
for _part in ('.github/diagnostics', 'build-utils', 'build-utils/s2arm', 'packages/dolphin_internal_bridge/ci', 'test'):
    sys.path.insert(0, str(ROOT / _part))

import standard_delivery as sd  # noqa: E402
import engine_pin as pin_tool  # noqa: E402
import check_app as app_check  # noqa: E402
import single_ipa_distribution_test as fixtures  # noqa: E402

BRANCH = 'work/s2arm-switch2-prototype-20261110'
HEADS = {'engine': '1' * 40, 'prepare': '2' * 40, 'sysdata': '3' * 40}
RUNS = {'engine': 101, 'prepare': 102, 'sysdata': 103}
ARTIFACT_IDS = {'engine': 201, 'prepare': 202, 'sysdata': 203}
NAMES = {'engine': 's2arm-engine-framework-{}', 'prepare': 'S2ArmPrepare-{}', 'sysdata': 's2arm-sysdata-macOS-{}'}
S2ARM_COMMIT = '6b6a571553f7a687af46e03e2cdbf8ef4d77f335'
CHAIN = b'0be3f28548fd'
LIBRARY = b'!<arch>\nS2ArmPrepare.o/ 0 0 0 644 16 `\nrelocatable obj\n'
NOTICE = (ROOT / 'build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt').read_bytes()
IMAGE = 'Frameworks/S2ArmEngine.framework/S2ArmEngine'
IDENTITY_FILE = 'S2Arm-native-identity.json'
REGISTRANT = ('#import "GeneratedPluginRegistrant.h"\n@implementation GeneratedPluginRegistrant\n'
              '+ (void)registerWithRegistry:(NSObject<FlutterPluginRegistry>*)registry {\n'
              '  [S2ArmEngineBridgePlugin registerWithRegistrar:[registry registrarForPlugin:@"S2ArmEngineBridgePlugin"]];\n}\n@end\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def framework_files(name):
    files = {f'{name}.framework/{name}': dylib(
        f'@rpath/{name}.framework/{name}', ('/usr/lib/libSystem.B.dylib',) +
        (('@rpath/NS2Pro.framework/NS2Pro',) if name == 'S2ArmEngine' else ())),
        f'{name}.framework/Info.plist': plistlib.dumps({'CFBundleExecutable': name, 'CFBundlePackageType': 'FMWK'}),
        f'{name}.framework/{name.lower()}.metallib': b'MTLB fixture data'}
    if name == 'S2ArmEngine':
        files[f'{name}.framework/S2ArmDirectChain.txt'] = CHAIN + b'\n'
    return files


def licence_texts():
    import embed_legal_bundle as gate
    texts = {path: f'licence text fixture: {path}\n'.encode() for path in gate.S2ARM_REQUIRED_NOTICES}
    texts[gate.S2ARM_REWINDBOX_NOTICE] = NOTICE
    manifest = dict(schema=1, engine='S2Arm', s2arm=dict(repository='https://github.com/jhaizhou-ops/S2Arm', commit=S2ARM_COMMIT),
                    collector='collect_licenses.py', components=[
                        dict(component=path.split('/')[0], license='fixture', files=[dict(
                            path=path, sha256=sha(data), bytes=len(data),
                            source=dict(kind='rewindbox' if path == gate.S2ARM_REWINDBOX_NOTICE else 's2arm', path=path))])
                        for path, data in texts.items()])
    return dict(texts, **{gate.S2ARM_NOTICE_MANIFEST: (json.dumps(manifest, indent=1) + '\n').encode()})


def engine_artifact(drop=(), identity=None, zips=None):
    zips = zips or {f'{name}.framework.zip': zipped(framework_files(name)) for name in pin_tool.FRAMEWORKS}
    texts = licence_texts()
    ident = dict(run=RUNS['engine'], attempt=1, head_sha=HEADS['engine'], s2arm_commit=S2ARM_COMMIT, patches=[], xcode='fixture',
                 files={name: sha(data) for name, data in zips.items()},
                 licenses={'manifest': 'licenses/license-sources.json', 'sha256': sha(texts['license-sources.json']),
                           'files': len(texts)})
    ident.update(identity or {})
    members = dict(zips, **{'s2arm-engine-identity.json': json.dumps(ident).encode()},
                   **{'licenses/' + name: data for name, data in texts.items()})
    return zipped({name: data for name, data in members.items() if name not in drop})


def prepare_artifact(archive=None):
    archive = archive or zipped(xcframework())
    ident = dict(component='S2ArmPrepare.xcframework', source=HEADS['prepare'], s2arm=S2ARM_COMMIT, dependencies={},
                 sha256={'S2ArmPrepare.xcframework.zip': sha(archive), 'libS2ArmPrepare.a': sha(LIBRARY)}, xcode='fixture')
    members = {'S2ArmPrepare.xcframework.zip': archive,
               'sha256.txt': f'{sha(archive)}  S2ArmPrepare.xcframework.zip\n{sha(LIBRARY)}  libS2ArmPrepare.a\n'.encode(),
               'undefined.txt': b'\n_free\n_malloc\n', 'S2ArmPrepare-identity.json': json.dumps(ident).encode()}
    return zipped(members)


def sysdata_artifact(tree=None, sums=None, extra=None):
    tree = sysdata_tree() if tree is None else tree
    members = dict(tree, SHA256SUMS=sums_of(tree) if sums is None else sums)
    members.update(extra or {})
    return zipped(members)


def meta_for(archives):
    return {name: dict(run=RUNS[name], attempt=1, artifact=ARTIFACT_IDS[name], name=NAMES[name].format(HEADS[name]),
                       bytes=len(raw), sha256=sha(raw), headSha=HEADS[name], expiresAt='2026-12-12T00:00:00Z')
            for name, raw in archives.items()}


def component(**overrides):
    value = {
        'mode': 'pinned-engine', 'pin': 'build-utils/s2arm/engine-pin.json', 'verifier': 'build-utils/s2arm/engine_pin.py',
        'identityFile': IDENTITY_FILE, 'frameworks': ['Frameworks/S2ArmEngine.framework', 'Frameworks/NS2Pro.framework'],
        'image': IMAGE, 'sideImages': [], 'extensions': ['S2ArmJITHelper.appex'], 'legalFolders': ['Legal/S2Arm'],
        'checks': ['build-utils/s2arm/check_app.py'],
        'producers': {'engine': {'workflow': '.github/workflows/s2arm-engine.yml', 'branch': BRANCH},
                      'prepare': {'workflow': '.github/workflows/s2arm-core.yml', 'branch': BRANCH, 'subdir': 'prepare'},
                      'sysdata': {'workflow': '.github/workflows/s2arm-prepare.yml', 'branch': BRANCH, 'subdir': 'sysdata'}},
        'podLibraries': ['s2arm_engine_bridge'],
        'appResources': [{'path': 'S2ArmSystemData/SHA256SUMS', 'binary': 'sysdata/SHA256SUMS'}],
    }
    value.update(overrides)
    return value


def dylib(install_name, dependencies=(), signed=False, filetype=6, rpaths=()):
    """A minimal arm64 iOS image: LC_BUILD_VERSION (iOS 18.0), LC_ID_DYLIB, LC_LOAD_DYLIB, LC_RPATH, optionally
    an empty code-signature superblob (what signing adds; the payload fingerprint ignores it)."""
    def text(kind, value):
        raw = value.encode() + b'\0'
        size = (24 + len(raw) + 7) // 8 * 8
        return struct.pack('<6I', kind, size, 24, 0, 0, 0) + raw + bytes(size - 24 - len(raw))
    commands = [struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 0)]
    if install_name:
        commands.append(text(0xD, install_name))
    commands += [text(0xC, item) for item in dependencies]
    commands += [text(0x8000001C, item) for item in rpaths]
    size = sum(map(len, commands)) + (16 if signed else 0)
    body = b'image payload'
    signature = struct.pack('>III', 0xFADE0CC0, 12, 0)
    if signed:
        commands.append(struct.pack('<4I', 0x1D, 16, 32 + size + len(body), len(signature)))
    header = struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, filetype, len(commands), size, 0, 0)
    return header + b''.join(commands) + body + (signature if signed else b'')


def zipped(files, symlink=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, data in files.items():
            archive.writestr(path, data)
        if symlink:
            entry = zipfile.ZipInfo(symlink)
            entry.external_attr = (0o120777 << 16)
            archive.writestr(entry, b'target')
    return buffer.getvalue()


def xcframework(library=LIBRARY, entry=None, extra=None, info=None):
    """S2ArmPrepare.xcframework as xcodebuild -create-xcframework makes it from one iOS arm64 static library."""
    library_entry = dict(BinaryPath=pin_tool.PREPARE_LIBRARY, HeadersPath='Headers', LibraryIdentifier='ios-arm64',
                         LibraryPath=pin_tool.PREPARE_LIBRARY, SupportedArchitectures=['arm64'], SupportedPlatform='ios')
    library_entry.update(entry or {})
    plist = dict(AvailableLibraries=[library_entry], CFBundlePackageType='XFWK', XCFrameworkFormatVersion='1.0')
    plist.update(info or {})
    root = pin_tool.PREPARE_XCFRAMEWORK + '/'
    files = {root + 'Info.plist': plistlib.dumps(plist), root + 'ios-arm64/' + pin_tool.PREPARE_LIBRARY: library,
             root + 'ios-arm64/Headers/s2arm_prepare.h': b'/* fixture */\n',
             root + 'ios-arm64/Headers/s2arm_pack.h': b'/* fixture */\n'}
    files.update(extra or {})
    return files


def sysdata_tree():
    """The system data tree build_sysdata_bundle.sh makes (open fonts, tz data, synthesised data), without SHA256SUMS."""
    return {
        'systemdata/fonts/nintendo_udsg-r_std_003.bfttf': b'open replacement font fixture',
        'systemdata/fonts/nintendo_ext_003.bfttf': b'pad icon font fixture',
        'systemdata/010000000000080E/zoneinfo/UTC': b'TZif2 fixture',
        'systemdata/010000000000080E/binaryList.txt': b'UTC\n',
        'systemdata/0100000000000802/data.bin': b'empty but well-formed fixture',
        'systemdata/0100000000000802.synth': '合成：pack/sysdata_synth.py 0100000000000802\n'.encode(),
        'licenses/fonts/OFL-NotoSans.txt': b'SIL Open Font License 1.1 fixture',
        'licenses/fonts/OFL-NotoSansCJK.txt': b'SIL Open Font License 1.1 fixture',
        'licenses/fonts/MANIFEST.tsv': b'font\tsource\n',
        'licenses/fonts/LICENSES.md': b'# fonts\n',
        'licenses/tzdata/LICENSE': b'Unless specified below, all files in the tz code and data are in the public domain.\n',
        'SOURCES.tsv': ('part\tsource\ns2arm\t' + S2ARM_COMMIT + '\nfonts\tfixture\n'
                        'tzdata\tservices/systemdata/make_tzdata.sh, IANA 2026f\nsynthesised\t0100000000000802\n').encode(),
    }


def sums_of(files):
    return ''.join(f'{sha(data)}  {path}\n' for path, data in files.items()).encode()


def uleb(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def export_trie(names):
    """A dyld export trie: the root's edges are the whole names, each leading to a terminal node (flags 0)."""
    names = sorted(names)
    leaf = uleb(3) + b'\x00' + uleb(0x1000) + b'\x00'   # terminal of 3 bytes: flags, address; no child
    size = 0
    while True:
        root = b'\x00' + bytes([len(names)]) + b''.join(
            name.encode() + b'\0' + uleb(size + index * len(leaf)) for index, name in enumerate(names))
        if len(root) == size:
            return root + leaf * len(names)
        size = len(root)


def runner_image(defined=None, undefined=(), exports=None, entitlements=None, dependencies=(), rpaths=()):
    """A synthetic arm64 iOS Runner: build version, dylibs and rpaths, a symbol table (external definitions and
    imports), a dyld export trie (LC_DYLD_EXPORTS_TRIE) and a code signature with the given entitlements."""
    defined = ['_main', *app_check.RUNNER_DEFINES] if defined is None else list(defined)
    exports = ['__mh_execute_header', '_main', app_check.ENGINE_LOADED] if exports is None else list(exports)

    def text(kind, value):
        raw = value.encode() + b'\0'
        size = (24 + len(raw) + 7) // 8 * 8
        return struct.pack('<6I', kind, size, 24, 0, 0, 0) + raw + bytes(size - 24 - len(raw))
    commands = [struct.pack('<6I', 0x32, 24, 2, 18 << 16, 0, 0)]
    commands += [text(0xC, item) for item in dependencies] + [text(0x8000001C, item) for item in rpaths]
    strings, entries = bytearray(b'\0'), bytearray()
    for name, kind in [(name, 0x0F) for name in defined] + [(name, 0x01) for name in undefined]:
        entries += struct.pack('<IBBHQ', len(strings), kind, 1 if kind == 0x0F else 0, 0, 0x1000 if kind == 0x0F else 0)
        strings += name.encode() + b'\0'
    trie = export_trie(exports)
    signature = fixtures.macho({} if entitlements is None else entitlements)[48:]
    size = sum(map(len, commands)) + 24 + 16 + 16
    symbols = 32 + size
    trie_offset = symbols + len(entries) + len(strings)
    commands += [struct.pack('<6I', 2, 24, symbols, len(defined) + len(undefined), symbols + len(entries), len(strings)),
                 struct.pack('<4I', 0x80000033, 16, trie_offset, len(trie)),
                 struct.pack('<4I', 0x1D, 16, trie_offset + len(trie), len(signature))]
    header = struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, 2, len(commands), size, 0, 0)
    return header + b''.join(commands) + bytes(entries) + bytes(strings) + trie + signature


def helper_image(signed=True):
    """The helper executable as the build links it: StikJIT of the host through @executable_path/../../Frameworks."""
    image = fixtures.packaging_image({}, dependencies=(app_check.STIKJIT, '/System/Library/Frameworks/Foundation.framework/Foundation'),
                                     rpaths=('@executable_path/Frameworks', '@executable_path/../../Frameworks'))
    return image   # packaging_image always carries a (synthetic) code signature


class Fixture(unittest.TestCase):
    """Synthetic producers, their pin, a temporary root and a mocked API."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.script = (ROOT / app_check.HELPER_SCRIPT).read_bytes()
        (self.root / app_check.HELPER_SCRIPT).parent.mkdir(parents=True)
        (self.root / app_check.HELPER_SCRIPT).write_bytes(self.script)
        (self.root / app_check.BRIDGE_REGISTRANT).parent.mkdir(parents=True)
        (self.root / app_check.BRIDGE_REGISTRANT).write_text(REGISTRANT)
        self.build({'engine': engine_artifact(), 'prepare': prepare_artifact(), 'sysdata': sysdata_artifact()})

    def build(self, archives):
        self.archives = archives
        self.pin = pin_tool.build_pin(meta_for(archives), archives)
        self.write_pin(self.pin)

    def write_pin(self, pin):
        path = self.root / 'build-utils/s2arm/engine-pin.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pin, indent=2) + '\n')
        self.manifest = {'components': {'s2arm': component(pinSha256=sha(path.read_bytes()))}}

    def api(self, branch=BRANCH, artifacts=None):
        def get(endpoint):
            for name, run in RUNS.items():
                if endpoint == f'actions/runs/{run}':
                    return {'id': run, 'path': component()['producers'][name]['workflow'], 'head_branch': branch,
                            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1, 'head_sha': HEADS[name]}
                if endpoint == f'actions/runs/{run}/artifacts':
                    raw = self.archives[name]
                    default = [{'id': ARTIFACT_IDS[name], 'name': NAMES[name].format(HEADS[name]), 'expired': False,
                                'digest': 'sha256:' + sha(raw), 'size_in_bytes': len(raw)}]
                    return {'artifacts': default if artifacts is None else artifacts(name, default)}
            raise AssertionError(endpoint)
        return get

    def verify(self, spec, archive, root):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = pin_tool.verify(archive, Path(root) / spec['pin'])
        if code:
            raise ValueError('The engine verifier refused the artifact: ' + output.getvalue())
        return output.getvalue().strip().splitlines()[-1]

    def download(self, **options):
        by_id = {ARTIFACT_IDS[name]: raw for name, raw in self.archives.items()}
        arguments = dict(root=self.root, get=self.api(), download=lambda artifact, path: path.write_bytes(by_id[artifact]),
                         verify=self.verify, repo=AllAncestors())
        arguments.update(options)
        return sd.engine_download('s2arm', arguments.pop('manifest', self.manifest), **arguments)

    def application(self, helper_signed=False, runner=None):
        """The built application with the engine embedded the way the workflow does it (ditto of the downloaded trees)."""
        dist = self.root / 'dist/s2arm'
        app = self.root / 'Runner.app'
        if app.exists():
            shutil.rmtree(app)
        helper = app / 'PlugIns' / app_check.HELPER
        helper.mkdir(parents=True)
        (app / 'Frameworks').mkdir()
        import validate_single_ipa_distribution as distribution
        contract = distribution.S2ARM_EXTENSIONS[app_check.HELPER]
        host = {'CFBundleIdentifier': 'com.neogamelab.neostation', 'CFBundleVersion': '803',
                'CFBundleShortVersionString': '0.0.8', 'CFBundleExecutable': 'Runner'}
        (app / 'Info.plist').write_bytes(plistlib.dumps(host))
        (app / 'Runner').write_bytes(runner_image() if runner is None else runner)
        (helper / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleExecutable': app_check.HELPER_EXECUTABLE, 'CFBundlePackageType': 'XPC!',
            'CFBundleIdentifier': host['CFBundleIdentifier'] + contract['bundleSuffix'], 'CFBundleVersion': '803',
            'CFBundleShortVersionString': '0.0.8', contract['marker']: '1',
            'NSExtension': {'NSExtensionPointIdentifier': 'com.apple.share-services',
                            'NSExtensionPrincipalClass': contract['principalClass']}}))
        (helper / app_check.HELPER_EXECUTABLE).write_bytes(helper_image())
        (helper / 's2arm-universal.js').write_bytes(self.script)
        for framework in ('S2ArmEngine.framework', 'NS2Pro.framework'):
            shutil.copytree(dist / framework, app / 'Frameworks' / framework)
        shutil.copytree(dist / 'sysdata', app / 'S2ArmSystemData')
        shutil.copytree(dist / 'licenses', app / 'Legal/S2Arm')
        return app


class AllAncestors:
    def is_ancestor(self, *_):
        return True


class Accepted(Fixture):
    def test_the_pin_is_well_formed_for_the_component(self):
        self.assertEqual(sd.engine_pin_errors(self.manifest['components']['s2arm'], self.pin), [])
        self.assertEqual(sd.engine_spec_errors('s2arm', self.manifest['components']['s2arm'],
                                               {'images': {'added': [IMAGE]}}), [])
        self.assertEqual(self.pin['zips'], {name: sha(raw) for name, raw in self.archives.items()})
        self.assertEqual(set(self.pin['producers']), {'engine', 'prepare', 'sysdata'})

    def test_the_real_verifier_accepts_each_artifact_and_names_it(self):
        for name, raw in self.archives.items():
            path = self.root / (name + '.zip')
            path.write_bytes(raw)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(pin_tool.main(['verify', str(path), '--pin', str(self.root / 'build-utils/s2arm/engine-pin.json')]), 0)
            self.assertIn(f'OK ({name}', output.getvalue())

    def test_download_embed_check_and_the_signed_ipa(self):
        result = self.download()
        self.assertEqual(sorted(result['producers']), ['engine', 'prepare', 'sysdata'])
        dist = self.root / 'dist/s2arm'
        self.assertTrue((dist / 'S2ArmEngine.framework/S2ArmEngine').is_file(), 'the framework zips are unpacked')
        self.assertFalse((dist / 'S2ArmEngine.framework.zip').exists())
        self.assertTrue((dist / 'prepare/S2ArmPrepare.xcframework.zip').is_file())
        self.assertTrue((dist / 'sysdata/SHA256SUMS').is_file())
        self.assertTrue((dist / 'licenses/license-sources.json').is_file())
        evidence = sd.engine_evidence('s2arm', self.manifest, root=self.root)
        self.assertEqual(evidence['packagedFingerprint'], self.pin['packagedFingerprint'])
        app = self.application()
        record = sd.engine_embed('s2arm', self.manifest, app, root=self.root, run_checks=False)
        identity = json.loads((app / IDENTITY_FILE).read_bytes())
        self.assertEqual(identity['component'], 's2arm')
        self.assertEqual(identity['sourceIdentity']['s2arm_commit'], S2ARM_COMMIT, 'read by the legal gate')
        self.assertEqual(identity['licenses'], self.pin['identity']['licenses'])
        self.assertEqual(sorted(identity['producers']), ['engine', 'prepare', 'sysdata'])
        self.assertEqual(record['identity'], identity)
        self.assertIn('S2Arm app OK', app_check.check_app(app, self.root))
        import embed_legal_bundle as gate
        self.assertEqual(gate.validate_s2arm_notices(app)['s2arm']['commit'], S2ARM_COMMIT)
        # the signed IPA: the image carries the pinned fingerprint, the identity says what was embedded
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for path in sorted(app.rglob('*')):
                if path.is_file():
                    archive.writestr('Payload/NeoStation.app/' + path.relative_to(app).as_posix(), path.read_bytes())
        with zipfile.ZipFile(buffer) as archive:
            result = sd.engine_ipa(archive, 'Payload/NeoStation.app/', 's2arm', self.manifest, evidence, root=self.root)
        self.assertEqual(result['packagedFingerprint'], self.pin['packagedFingerprint'])

    def test_the_inventory_names_the_engine_image_and_its_pinned_fingerprint(self):
        with mock.patch.object(sd, 'engine_pin', lambda spec, root=None: self.pin):   # the recipe reads the repository's pin
            self.assertEqual(sd.engine_inventory(self.manifest, {IMAGE: self.pin['packagedFingerprint']}), 1)
            with self.assertRaises(ValueError):
                sd.engine_inventory(self.manifest, {IMAGE: '0' * 64})

    def test_the_exports_list_is_exact(self):
        spec = dict(self.manifest['components']['s2arm'], appResources=None, exportsList={
            'Runner': ['__mh_execute_header', '_main', app_check.ENGINE_LOADED]})
        app = self.root / 'Runner.app'
        app.mkdir()
        (app / 'Runner').write_bytes(runner_image())
        sd.engine_extras(spec, self.pin, lambda relative: (app / relative).read_bytes())
        for wrong in (['_main'], ['__mh_execute_header', '_main', app_check.ENGINE_LOADED, '_extra']):
            with self.assertRaisesRegex(ValueError, 'exported symbols'):
                sd.engine_extras(dict(spec, exportsList={'Runner': wrong}), self.pin,
                                 lambda relative: (app / relative).read_bytes())

    def test_the_pod_libraries_are_in_the_podfile_lock(self):
        lock = 'PODS:\n  - Flutter (1.0.0)\n  - s2arm_engine_bridge (0.0.1):\n    - Flutter\n'
        sd.engine_pods(self.manifest['components']['s2arm'], lock)
        with self.assertRaisesRegex(ValueError, 'lacks the engine pod libraries'):
            sd.engine_pods(self.manifest['components']['s2arm'], 'PODS:\n  - Flutter (1.0.0)\n')


class Refused(Fixture):
    def test_a_wrong_artifact_digest(self):
        changed = dict(self.archives, sysdata=sysdata_artifact(extra={'systemdata/fonts/other.bfttf': b'x'},
                                                              sums=None, tree=dict(sysdata_tree(), **{'systemdata/fonts/other.bfttf': b'x'})))
        with self.assertRaisesRegex(ValueError, 'differs from the pinned size or sha256'):
            self.download(download=lambda artifact, path: path.write_bytes(
                changed['sysdata'] if artifact == ARTIFACT_IDS['sysdata'] else self.archives[
                    next(n for n, i in ARTIFACT_IDS.items() if i == artifact)]))
        with self.assertRaisesRegex(ValueError, 'not exactly one unexpired artifact'):
            self.download(get=self.api(artifacts=lambda name, default: [dict(default[0], digest='sha256:' + '0' * 64)]
                                       if name == 'engine' else default))

    def test_a_framework_archive_that_is_not_the_pinned_one(self):
        other = engine_artifact(zips={f'{name}.framework.zip': zipped(dict(
            framework_files(name), **{f'{name}.framework/{name.lower()}.metallib': b'changed'}))
            for name in pin_tool.FRAMEWORKS})
        path = self.root / 'other.zip'
        path.write_bytes(other)
        self.pin['producers']['engine'].update(bytes=len(other), sha256=sha(other))
        self.pin['zips']['engine'] = sha(other)
        self.write_pin(self.pin)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(pin_tool.verify(path, self.root / 'build-utils/s2arm/engine-pin.json'), 1)
        self.assertIn('members differ from the pin', output.getvalue())

    def test_a_missing_framework(self):
        with self.assertRaisesRegex(SystemExit, 'must hold exactly'):
            pin_tool.build_pin(meta_for({'engine': engine_artifact(drop=('NS2Pro.framework.zip',))}),
                               {'engine': engine_artifact(drop=('NS2Pro.framework.zip',))})
        self.download()
        app = self.application()
        shutil.rmtree(app / 'Frameworks/NS2Pro.framework')
        with self.assertRaisesRegex(ValueError, 'NS2Pro.framework is not the verified engine artifact|embedded'):
            sd.engine_embed('s2arm', self.manifest, app, root=self.root, run_checks=False)

    def test_an_identity_without_the_engine(self):
        self.download()
        app = self.application()
        sd.engine_embed('s2arm', self.manifest, app, root=self.root, run_checks=False)
        shutil.rmtree(app / 'Frameworks/S2ArmEngine.framework')
        with self.assertRaises((SystemExit, FileNotFoundError, KeyError, ValueError)):
            app_check.check_app(app, self.root)
        other = self.root / 'Other.app'
        other.mkdir()
        (other / IDENTITY_FILE).write_text('{}')
        with self.assertRaises((SystemExit, KeyError)):
            app_check.check_app(other, self.root)

    def test_a_sysdata_file_that_is_not_in_the_listing(self):
        tree = sysdata_tree()
        with self.assertRaisesRegex(SystemExit, 'not listed'):
            pin_tool.build_pin(meta_for({'sysdata': sysdata_artifact(tree=tree, extra={'systemdata/extra.bin': b'x'})}),
                               {'sysdata': sysdata_artifact(tree=tree, extra={'systemdata/extra.bin': b'x'})})
        self.download()
        app = self.application()
        sd.engine_embed('s2arm', self.manifest, app, root=self.root, run_checks=False)
        (app / 'S2ArmSystemData/systemdata/extra.bin').write_bytes(b'x')
        with self.assertRaisesRegex(SystemExit, 'not listed'):
            app_check.check_app(app, self.root)

    def test_the_application_resource_must_be_the_pinned_listing(self):
        self.download()
        app = self.application()
        (app / 'S2ArmSystemData/SHA256SUMS').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'app resource'):
            sd.engine_embed('s2arm', self.manifest, app, root=self.root, run_checks=False)

    def test_the_producer_must_be_a_run_of_the_named_branch(self):
        with self.assertRaisesRegex(ValueError, 'not the successful pinned run'):
            self.download(get=self.api(branch='Claude'))

    def test_a_draft_pin_is_refused(self):
        draft = json.loads((ROOT / 'build-utils/s2arm/engine-pin.json').read_text())
        self.assertEqual(draft['status'], 'draft')
        self.assertTrue(sd.engine_pin_errors(component(), draft))

    def test_a_pin_resource_that_names_no_binary(self):
        spec = component(appResources=[{'path': 'S2ArmSystemData/SHA256SUMS', 'binary': 'sysdata/missing'}])
        self.assertTrue([e for e in sd.engine_pin_errors(spec, self.pin) if 'appResources' in e])

    def test_the_closed_lists_hold_only_reviewed_entries(self):
        self.assertIn('build-utils/s2arm/engine_pin.py', sd.PINNED_ENGINE_VERIFIERS)
        self.assertIn('build-utils/s2arm/check_app.py', sd.PINNED_ENGINE_CHECKS)
        for path in sd.PINNED_ENGINE_VERIFIERS + sd.PINNED_ENGINE_CHECKS:
            self.assertTrue((ROOT / path).is_file(), path)
        for name, value in (('verifier', 'build-utils/s2arm/other.py'),):
            self.assertTrue([e for e in sd.engine_spec_errors('s2arm', component(**{name: value}), {'images': {'added': [IMAGE]}})
                             if name in e])


class Absent(unittest.TestCase):
    """A manifest without the component (726) behaves as before: nothing of the instance runs."""

    def test_726_has_no_engine_and_the_receipts_are_empty(self):
        manifest = json.loads((ROOT / 'build-utils/delivery/726.json').read_text())
        self.assertEqual(sd.engine_components(manifest), {})
        self.assertEqual(sd.engine_receipts(manifest), {})
        self.assertEqual(sd.engine_inventory(manifest, {}), 0)
        self.assertNotIn('s2arm', manifest['components'])
        self.assertEqual([e for e in sd.manifest_errors(manifest) if 's2arm' in e], [])

    def test_the_s2arm_steps_need_the_component_and_there_is_one_of_each(self):
        text = (ROOT / '.github/workflows/standard-delivery.yml').read_text()
        guard = "steps.engines.outputs.s2arm == 'true'"
        names = [line.split('name: ', 1)[1] for line in text.splitlines() if line.strip().startswith('- name: ')]
        for name in ('Download and authenticate the pinned S2Arm engine, preparation library and system data',
                     'Verify the pinned S2Arm engine, preparation library and system data',
                     'Install the pinned S2Arm preparation library where the engine bridge podspec vendors it',
                     'Add the S2Arm JIT helper extension to the generated host',
                     'Embed the pinned S2Arm engine, system data and notices, then check the app'):
            self.assertEqual(names.count(name), 1, name)
        self.assertEqual(text.count(guard), 5)
        order = names.index
        self.assertLess(order('Install the pinned S2Arm preparation library where the engine bridge podspec vendors it'),
                        order('Configure release host'))
        self.assertLess(order('Configure release host'), order('Add the S2Arm JIT helper extension to the generated host'))
        self.assertLess(order('Add the S2Arm JIT helper extension to the generated host'),
                        order('Compile Release device binary with measured AOT and Xcode phases'))
        self.assertLess(order('Embed legal, license and source notices'),
                        order('Embed the pinned S2Arm engine, system data and notices, then check the app'))


if __name__ == '__main__':
    unittest.main()
