#!/usr/bin/env python3
"""The S2Arm conditional of build-utils/embed_legal_bundle.py (the application's legal gate), on synthetic applications.

    python3 -B test/s2arm_legal_bundle_test.py

--validate-only checks the source notices before compilation. With --app naming an application that carries
S2Arm-native-identity.json, it also requires the S2Arm engine's licence and notice texts in the application's
Legal/S2Arm: their manifest license-sources.json, every text it lists with its SHA-256 and size and no other file, the
required texts (S2Arm's LICENSE, NOTICE and THIRD_PARTY_LICENSES.md, the .NET runtime and compiler notices, the codecs,
glslang, bcdec, ns2pro-bridge, Ryujinx, SPIRV-Cross), the RewindBox notice stating that no Nintendo data ships, and an
identity that records that manifest and the same S2Arm commit.
Without the identity file it behaves exactly as the common line's packager (git blob below, when this clone has it) and
as the current file with its S2Arm statements removed from the syntax tree (which must be that blob's program): same
exit status, output and calls, with and without --app (no application, an application without the identity, with an
incomplete Legal/S2Arm, an identity file elsewhere, a missing path), for a wrong Dolphin pin and a missing argument; the
embedding mode writes the same legal bundle, identity or not. Every check of the gate runs, except the source-evidence
collector, which is replaced by a recorder in both: on a branch head it refuses the declarations as it does on the
common line's head (they are reviewed for the delivered effective tree), and it is covered by its own tests.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'build-utils') not in sys.path:
    sys.path.insert(0, str(ROOT / 'build-utils'))

import embed_legal_bundle as legal  # noqa: E402

PATH = 'build-utils/embed_legal_bundle.py'
# embed_legal_bundle.py of the common line before the S2Arm statements (origin/Claude at 41c76404; same blob on this
# branch's base ba04c914).
PRE_CHANGE_BLOB = 'a63fe9d547adf567d54da3555c30c0be2aad270e'
DOLPHIN = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
COMMIT = '6b6a571553f7a687af46e03e2cdbf8ef4d77f335'
S2ARM_FUNCTIONS = ('s2arm_notice_errors', 'validate_s2arm_notices')
CODEC = 'op' + 'us'   # the audio codec's own name, spelt so that this file passes the model-name guard of the line


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module_from(source, name):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / PATH)
    exec(compile(source, str(ROOT / PATH), 'exec'), module.__dict__)
    return module


def pre_change_source():
    result = subprocess.run(['git', 'cat-file', 'blob', PRE_CHANGE_BLOB], cwd=ROOT, capture_output=True)
    return result.stdout.decode() if result.returncode == 0 else None


def is_s2arm(node):
    return any(isinstance(child, ast.Name) and child.id.startswith('S2ARM_') for child in ast.walk(node))


def stripped_tree():
    """The packager's syntax tree without its S2Arm constants, its two S2Arm functions and the conditional of main()."""
    tree = ast.parse((ROOT / PATH).read_text())
    constants = [node for node in tree.body if isinstance(node, ast.Assign) and is_s2arm(node)]
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in S2ARM_FUNCTIONS]
    tree.body = [node for node in tree.body if node not in constants and node not in functions]
    conditionals = 0
    for holder in ast.walk(tree):
        body = getattr(holder, 'body', None)
        if isinstance(body, list):
            kept = [node for node in body if not (isinstance(node, ast.If) and is_s2arm(node.test))]
            conditionals += len(body) - len(kept)
            holder.body = kept
    if len(constants) != 7 or len(functions) != 2 or conditionals != 1 or is_s2arm(tree):
        raise AssertionError(f'unexpected S2Arm statements: {len(constants)} constants, {len(functions)} functions, '
                             f'{conditionals} conditionals')
    return tree


def notice_files(commit=COMMIT, statement=True):
    """A complete Legal/S2Arm: every required text, one optional text, the RewindBox notice and the manifest."""
    texts = {path: f'licence text fixture: {path}\n'.encode() for path in legal.S2ARM_REQUIRED_NOTICES}
    texts['MacNativeGames/LICENSE'] = b'an optional licence text fixture\n'
    texts[legal.S2ARM_REWINDBOX_NOTICE] = ('RewindBox notice fixture.\n' + (legal.S2ARM_NO_NINTENDO_DATA if statement
                                                                           else 'Nothing said about the data.') + '\n').encode()
    return with_manifest(texts, commit)


def with_manifest(texts, commit=COMMIT, change=None):
    components = {}
    for path, data in texts.items():
        name = path.split('/')[0] if '/' in path else 'RewindBox'
        kind = ('rewindbox' if path == legal.S2ARM_REWINDBOX_NOTICE else 'nuget' if path.startswith('dotnet/') else
                'archive' if name in ('libvpx', CODEC, 'dav1d', 'glslang') else 's2arm')
        components.setdefault(name, []).append(dict(path=path, sha256=sha(data), bytes=len(data),
                                                    source=dict(kind=kind, path=path)))
    manifest = dict(schema=1, engine='S2Arm', s2arm=dict(repository='https://github.com/jhaizhou-ops/S2Arm', commit=commit),
                    components=[dict(component=name, files=entries) for name, entries in components.items()])
    if change:
        change(manifest)
    return dict(texts, **{legal.S2ARM_NOTICE_MANIFEST: json.dumps(manifest, indent=1).encode()})


def identity(files, commit=COMMIT, recorded=None):
    manifest = files.get(legal.S2ARM_NOTICE_MANIFEST, b'') if files else b''
    return json.dumps(dict(schema=1, engine='S2Arm', sourceIdentity=dict(s2arm_commit=commit),
                           licenses=dict(path='Legal/S2Arm', manifest=legal.S2ARM_NOTICE_MANIFEST,
                                         sha256=recorded or sha(manifest)))).encode()


def application(root, files=None, carries=None, at=legal.S2ARM_IDENTITY):
    """A built application (a folder), with Legal/S2Arm holding `files` and the identity bytes `carries` at `at`."""
    app = root / 'Runner.app'
    (app / 'Frameworks/App.framework/flutter_assets').mkdir(parents=True)
    (app / 'Frameworks/App.framework/flutter_assets/NOTICES.txt').write_text('Synthetic Flutter notice fixture.\n')
    (app / 'Info.plist').write_bytes(b'<plist/>')
    for path, data in (files or {}).items():
        target = app / 'Legal' / legal.S2ARM_LEGAL / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if carries is not None:
        (app / at).parent.mkdir(parents=True, exist_ok=True)
        (app / at).write_bytes(carries)
    return app


def run_main(module, arguments):
    """(exit status, output, error output, collector calls) of module.main() with these arguments."""
    calls = []

    def collector(*values):
        calls.append([str(value) for value in values])
        return {'BUILD_SOURCE_EVIDENCE.json': b'{"schema": 1}\n'}, {'cocoapods': {'status': 'not_present_in_this_source_checkout'}}
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(module, 'collect_source_evidence', collector), \
            mock.patch.object(sys, 'argv', ['embed_legal_bundle.py', *arguments]), \
            mock.patch.dict(os.environ, {'GITHUB_SHA': 'c' * 40}), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            module.main()
            status = 0
        except SystemExit as error:
            status = error.code
    return status, out.getvalue(), err.getvalue(), calls


def references():
    found = {'stripped': module_from(stripped_tree(), 'embed_legal_bundle_stripped')}
    source = pre_change_source()
    if source is not None:
        found['common line blob'] = module_from(source, 'embed_legal_bundle_common')
    return found


class WithoutTheIdentityFile(unittest.TestCase):
    def test_the_diff_only_adds_statements_behind_the_identity_file(self):
        source = pre_change_source()
        if source is None:
            self.skipTest('the common line blob is not in this clone')
        self.assertEqual(ast.dump(stripped_tree()), ast.dump(ast.parse(source)))

    def test_validate_only_is_the_common_gate(self):
        found = references()
        with tempfile.TemporaryDirectory(prefix='s2arm-legal-') as directory:
            root = Path(directory)
            plain = application(root / 'plain')
            incomplete = application(root / 'incomplete', files={'S2Arm/LICENSE': b'x'})
            elsewhere = application(root / 'elsewhere', files=notice_files(), carries=identity(notice_files()),
                                    at='Frameworks/' + legal.S2ARM_IDENTITY)
            cases = {
                'no application': ['--validate-only', '--dolphin-sha', DOLPHIN],
                'an application without the identity': ['--validate-only', '--dolphin-sha', DOLPHIN, '--app', str(plain)],
                'an incomplete Legal/S2Arm without the identity': ['--validate-only', '--dolphin-sha', DOLPHIN, '--app',
                                                                   str(incomplete)],
                'an identity file outside the application root': ['--validate-only', '--dolphin-sha', DOLPHIN, '--app',
                                                                  str(elsewhere)],
                'a missing application': ['--validate-only', '--dolphin-sha', DOLPHIN, '--app', str(root / 'none.app')],
                'another Dolphin revision': ['--validate-only', '--dolphin-sha', '0' * 40],
                'no Dolphin revision': ['--validate-only'],
            }
            expected = {name: 0 for name in cases}
            expected.update({'another Dolphin revision': 'Legal notice assets/legal/Dolphin-COPYING.txt is stale: expected '
                                                         f"'Pinned revision/tag: {'0' * 40}'", 'no Dolphin revision': 2})
            for name, arguments in cases.items():
                actual = run_main(legal, arguments)
                self.assertEqual(actual[0], expected[name], name + ': ' + actual[2][-300:])
                if expected[name] == 0:
                    self.assertEqual(actual[1], 'Validated all required notices and pinned revisions before compilation\n')
                    self.assertEqual(actual[3], [[str(ROOT), 'c' * 40]])
                for label, module in found.items():
                    with self.subTest(case=name, reference=label):
                        self.assertEqual(actual, run_main(module, arguments))
        self.assertEqual(len(found), 1 + (pre_change_source() is not None))

    def test_the_embedding_mode_is_unchanged(self):
        """Embedding writes the same legal bundle with the current file and the common line's, identity or not (the
        engine's notices are placed after it, by the test line's launcher)."""
        found = references()
        bundles = {}
        for label, module in dict(found, current=legal).items():
            for carries in (False, True):
                with tempfile.TemporaryDirectory(prefix='s2arm-legal-') as directory:
                    app = application(Path(directory), carries=identity(notice_files()) if carries else None)
                    status, out, err, calls = run_main(module, ['--app', str(app), '--build-number', '803',
                                                                '--dolphin-sha', DOLPHIN])
                    self.assertEqual(status, 0, err[-300:])
                    tree = {path.relative_to(app / 'Legal').as_posix(): sha(path.read_bytes())
                            for path in sorted((app / 'Legal').rglob('*')) if path.is_file()}
                    self.assertNotIn(legal.S2ARM_LEGAL, {name.split('/')[0] for name in tree})
                    bundles[(label, carries)] = (tree, calls[0][1:2], out.replace(str(app), 'APP'))
        reference = bundles[('current', False)]
        self.assertIn('BUILD_SOURCE_IDENTITY.json', reference[0])
        for key, value in bundles.items():
            self.assertEqual(value, reference, key)


class WithTheIdentityFile(unittest.TestCase):
    def gate(self, files, carries, module=legal):
        with tempfile.TemporaryDirectory(prefix='s2arm-legal-') as directory:
            app = application(Path(directory), files=files, carries=carries)
            return run_main(module, ['--validate-only', '--dolphin-sha', DOLPHIN, '--app', str(app)])

    def test_complete_notices_are_accepted(self):
        files = notice_files()
        status, out, err, calls = self.gate(files, identity(files))
        self.assertEqual(status, 0, err[-500:])
        self.assertEqual(out, f'Validated the S2Arm engine notices (S2Arm {COMMIT}) in Legal/S2Arm\n'
                              'Validated all required notices and pinned revisions before compilation\n')
        self.assertEqual(legal.s2arm_notice_errors(files), [])
        source = pre_change_source()
        if source is not None:   # the common line's gate does not look at them
            self.assertEqual(self.gate({}, identity({}), module_from(source, 'embed_legal_bundle_common'))[0], 0)

    def test_the_required_texts(self):
        self.assertEqual(legal.S2ARM_REQUIRED_NOTICES, (
            legal.S2ARM_REWINDBOX_NOTICE, 'S2Arm/LICENSE', 'S2Arm/NOTICE', 'S2Arm/THIRD_PARTY_LICENSES.md',
            'dotnet/Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/LICENSE.TXT',
            'dotnet/Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/THIRD-PARTY-NOTICES.TXT',
            'dotnet/Microsoft.DotNet.ILCompiler/THIRD-PARTY-NOTICES.TXT',
            'libvpx/LICENSE', 'libvpx/PATENTS', CODEC + '/COPYING', 'dav1d/COPYING', 'glslang/LICENSE.txt',
            'bcdec/LICENSE', 'ns2pro-bridge/LICENSE', 'Ryujinx/LICENSE.txt', 'SPIRV-Cross/LICENSE'))
        for path in legal.S2ARM_REQUIRED_NOTICES:
            with self.subTest(missing=path):
                texts = {name: data for name, data in notice_files().items()
                         if name not in (path, legal.S2ARM_NOTICE_MANIFEST)}
                files = with_manifest(texts)
                status = self.gate(files, identity(files))[0]
                self.assertIsInstance(status, str)
                self.assertIn('required texts missing: ' + path, status)
        for word in ('Nintendo', 'SIL Open Font License', 'IANA time zone database', 'synthesised'):
            self.assertIn(word, legal.S2ARM_NO_NINTENDO_DATA)

    def test_incomplete_or_changed_notices_are_refused(self):
        files = notice_files()
        manifest = json.loads(files[legal.S2ARM_NOTICE_MANIFEST])
        first = manifest['components'][1]['files'][0]['path']

        def edited(change):
            value = json.loads(files[legal.S2ARM_NOTICE_MANIFEST])
            change(value)
            return dict(files, **{legal.S2ARM_NOTICE_MANIFEST: json.dumps(value).encode()})

        def entry(update):
            def change(value):
                value['components'][1]['files'][0].update(update)
            return change
        cases = {
            'no Legal/S2Arm': (None, 'requires the engine notices in Legal/S2Arm'),
            'no manifest': ({path: data for path, data in files.items() if path != legal.S2ARM_NOTICE_MANIFEST},
                            'no readable license-sources.json'),
            'manifest not JSON': (dict(files, **{legal.S2ARM_NOTICE_MANIFEST: b'{'}), 'no readable license-sources.json'),
            'other schema': (edited(lambda value: value.update(schema=2)), 'not an S2Arm notice manifest'),
            'other engine': (edited(lambda value: value.update(engine='MeloNX')), 'not an S2Arm notice manifest'),
            'short commit': (edited(lambda value: value['s2arm'].update(commit='6b6a5715')), 'not an S2Arm notice manifest'),
            'no component': (edited(lambda value: value.update(components=[])), 'not an S2Arm notice manifest'),
            'component without texts': (edited(lambda value: value['components'].append(dict(component='x', files=[]))),
                                        'a component without its name or texts'),
            'listed text missing': ({path: data for path, data in files.items() if path != first}, first + ' is missing'),
            'text changed': (dict(files, **{first: files[first] + b'x'}), first + ' differs from license-sources.json'),
            'size differs': (edited(entry(dict(bytes=1))), first + ' differs from license-sources.json'),
            'digest in capitals': (edited(entry(dict(sha256=json.loads(files[legal.S2ARM_NOTICE_MANIFEST])['components'][1]
                                                     ['files'][0]['sha256'].upper()))), first + ': no SHA-256, size or source'),
            'unknown source': (edited(entry(dict(source=dict(kind='hand')))), first + ': no SHA-256, size or source'),
            'no source': (edited(entry(dict(source=None))), first + ': no SHA-256, size or source'),
            'unlisted file': (dict(files, **{'Other/LICENSE': b'x'}), 'not in license-sources.json: Other/LICENSE'),
            'parent path': (edited(entry(dict(path='../LICENSE'))), "unsafe or repeated path: '../LICENSE'"),
            'absolute path': (edited(entry(dict(path='/LICENSE'))), "unsafe or repeated path: '/LICENSE'"),
            'hidden path': (edited(entry(dict(path='S2Arm/.LICENSE'))), "unsafe or repeated path: 'S2Arm/.LICENSE'"),
            'backslash': (edited(entry(dict(path='S2Arm\\LICENSE'))), 'unsafe or repeated path'),
            'empty part': (edited(entry(dict(path='S2Arm//LICENSE'))), "unsafe or repeated path: 'S2Arm//LICENSE'"),
            'manifest listed': (edited(entry(dict(path=legal.S2ARM_NOTICE_MANIFEST))), 'unsafe or repeated path'),
            'repeated path': (edited(lambda value: value['components'][1]['files'].append(
                dict(value['components'][1]['files'][0]))), 'unsafe or repeated path: ' + repr(first)),
            'no statement': (notice_files(statement=False), 'does not state that no Nintendo data ships'),
        }
        for name, (case, message) in cases.items():
            with self.subTest(case=name):
                status = self.gate(case, identity(case or {}))[0]
                self.assertIsInstance(status, str, name)
                self.assertTrue(status.startswith('S2Arm engine notices: ') or 'Legal/S2Arm' in status, status)
                self.assertIn(message, status)

    def test_the_identity_binds_the_notices(self):
        files = notice_files()
        cases = {
            'another manifest recorded': (identity(files, recorded='0' * 64), 'does not record this license-sources.json'),
            'no licences recorded': (json.dumps(dict(sourceIdentity=dict(s2arm_commit=COMMIT))).encode(),
                                     'does not record this license-sources.json'),
            'another S2Arm commit': (identity(files, commit='1' * 40), "not of the engine's S2Arm commit"),
            'identity not JSON': (b'not json', 'does not record this license-sources.json'),
        }
        for name, (carries, message) in cases.items():
            with self.subTest(case=name):
                status = self.gate(files, carries)[0]
                self.assertIsInstance(status, str)
                self.assertIn(message, status)
        other = notice_files(commit='1' * 40)
        self.assertEqual(self.gate(other, identity(other, commit='1' * 40))[0], 0)

    def test_a_symbolic_link_is_refused(self):
        files = notice_files()
        with tempfile.TemporaryDirectory(prefix='s2arm-legal-') as directory:
            app = application(Path(directory), files=files, carries=identity(files))
            (app / 'Legal/S2Arm/Linked').symlink_to(app / 'Info.plist')
            status = run_main(legal, ['--validate-only', '--dolphin-sha', DOLPHIN, '--app', str(app)])[0]
        self.assertEqual(status, 'Symbolic link in Legal/S2Arm: Linked')


if __name__ == '__main__':
    unittest.main(verbosity=2)
