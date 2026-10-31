#!/usr/bin/env python3
"""Offline rejection tests for exact producer/source/transport boundaries."""
import copy
import ast
import importlib
import io
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get('REWINDBOX_CONTRACT_REFERENCE_ROOT', ROOT))
sys.path[:0] = [str(ROOT / '.github/diagnostics'), str(REFERENCE / '.github/diagnostics')]
tree = importlib.import_module('rewind606_baseline')
engine = importlib.import_module('rewind606_engine')
sys.path[:0] = [str(REFERENCE / 'build-utils'), str(REFERENCE / 'packages/dolphin_internal_bridge/ci')]


def sealing_functions():
    # Load only the pure sealing boundary functions: the unrelated retained
    # RPCS3 downloader must not run or need producer artifacts in offline tests.
    wanted = {'arm64_payload', 'payload_record', 'app_payloads', 'zip_payloads', 'seal', 'save'}
    parsed = ast.parse((ROOT / '.github/diagnostics/rewind606_delivery.py').read_text())
    selected = [node for node in parsed.body if (isinstance(node, ast.FunctionDef) and node.name in wanted) or
                (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'MACHO_MAGICS' for target in node.targets))]
    namespace = dict(require=tree.require, struct=struct, json=json, zipfile=zipfile, sha=tree.sha, Path=Path,
        engine=engine)
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<sealing-functions>', 'exec'), namespace)
    return namespace


def thin_fixture():
    commands = 152 + 24
    offset = 32 + commands
    header = struct.pack('<8I', 0xfeedfacf, 0x0100000C, 0, 6, 2, commands, 0, 0)
    segment = struct.pack('<II16sQQQQiiII', 0x19, 152, b'__TEXT', 0x100000000, 4096, 0, offset + 4, 7, 5, 1, 0)
    section = struct.pack('<16s16sQQIIIIIIII', b'__text', b'__TEXT', 0x100000000 + offset, 4, offset, 2, 0, 0, 0, 0, 0, 0)
    build = struct.pack('<6I', 0x32, 24, 2, 18 << 16, 18 << 16, 0)
    return header + segment + section + build + b'abcd'


def fat_fixture(thin, wide=False):
    offset = 4096
    if wide:
        header = struct.pack('>II', 0xcafebabf, 1) + struct.pack('>IIQQII', 0x0100000C, 0, offset, len(thin), 12, 0)
    else:
        header = struct.pack('>II', 0xcafebabe, 1) + struct.pack('>IIIII', 0x0100000C, 0, offset, len(thin), 12)
    return header + b'\0' * (offset - len(header)) + thin


class FullSigningInventory(unittest.TestCase):
    def setUp(self):
        self.functions = sealing_functions()
        self.thin = thin_fixture()

    def test_thin_and_single_fat_fingerprints_cover_same_compiled_sections(self):
        record = self.functions['payload_record']
        expected = record(self.thin)['fingerprint']
        for wide in (False, True):
            with self.subTest(wide=wide):
                self.assertEqual(self.functions['arm64_payload'](fat_fixture(self.thin, wide))[0], self.thin)
                self.assertEqual(record(fat_fixture(self.thin, wide))['fingerprint'], expected)

    def test_reject_truncated_architecture_table_and_multiarch(self):
        valid = fat_fixture(self.thin)
        for raw in (valid[:7], valid[:27], valid[:4] + struct.pack('>I', 2) + valid[8:]):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                self.functions['arm64_payload'](raw)

    def test_endian_swapped_fat_is_detected_and_rejected_in_stage_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / 'app'; app.mkdir()
            ipa = Path(directory) / 'candidate.ipa'
            for magic in (b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
                raw = magic + fat_fixture(self.thin)[4:]
                (app / 'image').write_bytes(raw)
                with zipfile.ZipFile(ipa, 'w') as archive:
                    archive.writestr('Payload/NeoStation.app/image', raw)
                with self.subTest(magic=magic), self.assertRaises(ValueError):
                    self.functions['app_payloads'](app)
                with self.subTest(zipMagic=magic), self.assertRaises(ValueError):
                    self.functions['zip_payloads'](ipa)

    def test_reject_non_arm64_and_disagreeing_inner_architecture(self):
        for offset in (8, 4096 + 4):
            data = bytearray(fat_fixture(self.thin))
            struct.pack_into('>I' if offset == 8 else '<I', data, offset, 0x01000007)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.functions['arm64_payload'](bytes(data))

    def test_reject_invalid_slice_alignment_bounds_and_trailing_data(self):
        wrong_offset = bytearray(fat_fixture(self.thin)); struct.pack_into('>I', wrong_offset, 16, 27)
        wrong_alignment = bytearray(fat_fixture(self.thin)); struct.pack_into('>I', wrong_alignment, 24, 32)
        for data in (bytes(wrong_offset), bytes(wrong_alignment), fat_fixture(self.thin)[:-1], fat_fixture(self.thin) + b'x'):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                self.functions['arm64_payload'](data)

    def test_reject_truncated_and_inconsistent_load_commands(self):
        for offset, value in ((16, 65537), (20, 1000000), (36, 7), (16, 1)):
            data = bytearray(self.thin); struct.pack_into('<I', data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                self.functions['arm64_payload'](bytes(data))

    def exercise_seal(self, alter_fat=False):
        import delivery_benchmark
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'build/ios/dolphin-unsigned/Payload/NeoStation.app'
            out = root / 'build/delivery'; out.mkdir(parents=True)
            ipa = root / 'dist/NeoStation.ipa'; ipa.parent.mkdir(parents=True)
            for index in range(89):
                name = 'Image' + str(index)
                path = app / 'Frameworks' / (name + '.framework') / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(fat_fixture(self.thin) if index < 3 else self.thin)
            self.functions.update(ROOT=root, OUT=out)
            def old_seal():
                # Model the inherited hole: only86 thin images are recorded.
                original = self.functions['app_payloads'](app)
                legacy = {name: record['fingerprint'] for name, record in original.items() if record['container'] == 'thin-arm64'}
                if alter_fat:
                    path = app / 'Frameworks/Image0.framework/Image0'
                    path.write_bytes(path.read_bytes()[:-4] + b'evil')
                with zipfile.ZipFile(ipa, 'w') as archive:
                    for path in app.rglob('*'):
                        if path.is_file(): archive.writestr('Payload/NeoStation.app/' + path.relative_to(app).as_posix(), path.read_bytes())
                (out / 'signed-payload-identity.json').write_text(json.dumps(dict(images=legacy, ipaSha256=tree.sha(ipa.read_bytes()),
                    ipaBytes=ipa.stat().st_size, allCompiledCodeAndDataSectionsUnchangedBySigning=True, abiMetadataUnchangedBySigning=True)))
                (out / 'signature.json').write_text(json.dumps(dict(signatures=[
                    dict(bundle=Path(name).parent.as_posix(), signatureVerified=True) for name in original])))
            with patch.object(delivery_benchmark, 'seal', side_effect=old_seal):
                return self.functions['seal']()

    def test_seal_replaces_thin_only_receipt_with_all_89_images(self):
        receipt = self.exercise_seal()
        self.assertEqual(receipt['imageCount'], 89)
        self.assertEqual(receipt['singleArm64FatImages'], 3)
        self.assertTrue(receipt['completeNativeInventoryCheckedInFinalZIP'])

    def test_seal_rejects_fat_payload_change_hidden_by_old_receipt(self):
        with self.assertRaises(ValueError): self.exercise_seal(alter_fat=True)


class ProducerOrigin(unittest.TestCase):
    def setUp(self):
        self.pin = dict(source='a' * 40, run=9, job=13, attempt=2,
            workflow='.github/workflows/melonx-core.yml', artifact=41,
            name='MeloNX-engine-' + 'a' * 40, bytes=19, sha256='b' * 64)
        self.run = dict(id=9, head_sha='a' * 40, head_branch='Claude', path=self.pin['workflow'],
            status='completed', conclusion='success', run_attempt=2)
        self.job = dict(id=13, run_id=9, head_sha='a' * 40, conclusion='success', run_attempt=2,
            steps=[dict(name=n, conclusion='success') for n in engine.CORE_STEPS])
        self.artifact = dict(id=41, name=self.pin['name'], size_in_bytes=19, digest='sha256:' + 'b' * 64,
            expired=False, workflow_run=dict(id=9, head_sha='a' * 40))

    def validate(self):
        return engine.validate_origin(self.pin, self.run, self.job, self.artifact, 'core')

    def test_exact_retry_is_bound_without_assuming_attempt_one(self):
        self.assertEqual(self.validate()['attempt'], 2)

    def test_different_source_success_is_not_a_substitute(self):
        self.run['head_sha'] = 'c' * 40
        with self.assertRaises(ValueError): self.validate()

    def test_original_failure_cannot_be_relabelled_success(self):
        self.run['conclusion'] = 'failure'
        with self.assertRaises(ValueError): self.validate()

    def test_missing_runtime_step_rejects_compilation_only(self):
        self.job['steps'].pop()
        with self.assertRaises(ValueError): self.validate()

    def test_artifact_from_another_run_rejected(self):
        self.artifact['workflow_run']['id'] = 8
        with self.assertRaises(ValueError): self.validate()

    def test_artifact_digest_and_size_are_both_bound(self):
        for key, value in (('digest', 'sha256:' + 'f' * 64), ('size_in_bytes', 20), ('expired', True)):
            with self.subTest(key=key):
                original = self.artifact[key]; self.artifact[key] = value
                with self.assertRaises(ValueError): self.validate()
                self.artifact[key] = original

    def test_other_workflow_cannot_supply_current_core(self):
        self.pin['workflow'] = self.run['path'] = '.github/workflows/old-core.yml'
        with self.assertRaises(ValueError): self.validate()


class PreparedSourceBindings(unittest.TestCase):
    def setUp(self):
        self.path = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
        self.untouched = 'src/Ryujinx.Common/Unmodified.Dependency.cs'
        self.gate = dict(requiredPostimages=[self.path], assertions={'assertions.count': 4},
            compiledBindings=[dict(reportPath=['compiledSourceInputs', 'EmbeddedPerformanceDiagnostics.cs'], productionPath=self.path),
                              dict(reportPath=['compiledSourceInputs', 'Unmodified.Dependency.cs'], productionPath=self.untouched)])
        self.frozen = dict(baselinePreparedMembers={self.path: 'old'}, baselineUnadaptedMembers={},
            preparedMembers={self.path: 'new'}, untouchedFixtureMembers={self.untouched: 'same'})
        self.report = dict(result='passed', physicalDeviceTested=False, inputs={'fixture.py': 'input'},
            assertions={'count': 4}, preimages={self.path: 'old'}, postimages={self.path: 'new'},
            upstreamInputs={self.untouched: 'same'},
            compiledSourceInputs={'EmbeddedPerformanceDiagnostics.cs': 'new', 'Unmodified.Dependency.cs': 'same'})

    def validate(self):
        with patch.object(engine, 'inputs_match') as inputs:
            engine.verify_gate(self.report, self.gate, self.frozen, 'producer')
            inputs.assert_called_once_with({'fixture.py': 'input'}, 'producer')

    def test_list_report_path_keeps_dots_in_filename(self):
        self.validate()

    def test_unchanged_upstream_dependency_is_authenticated(self):
        self.assertNotIn(self.untouched, self.frozen['preparedMembers'])
        self.validate()

    def test_fixture_using_preliminary_postimage_rejected(self):
        self.report['postimages'][self.path] = 'preliminary'
        with self.assertRaises(ValueError): self.validate()

    def test_valid_report_hash_cannot_hide_wrong_compiled_binding(self):
        self.report['compiledSourceInputs']['EmbeddedPerformanceDiagnostics.cs'] = 'old'
        with self.assertRaises(ValueError): self.validate()

    def test_unauthenticated_upstream_dependency_rejected(self):
        self.frozen['untouchedFixtureMembers'].clear()
        with self.assertRaises(ValueError): self.validate()

    def test_absent_required_postimage_rejected(self):
        self.report['postimages'].clear()
        with self.assertRaises(ValueError): self.validate()

    def test_failed_assertion_rejected(self):
        self.report['assertions']['count'] = 3
        with self.assertRaises(ValueError): self.validate()


class ArchiveBoundaries(unittest.TestCase):
    def archive(self, names):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(buffer, 'w') as archive:
                for name in names: archive.writestr(name, b'proof')
        return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))

    def test_safe_archive(self):
        with self.archive(['a/result.json', 'src/File.cs']) as archive:
            self.assertEqual(len(engine.safe_members(archive)), 2)

    def test_duplicate_and_path_escape_rejected(self):
        for names in (['a', 'a'], ['../outside'], ['/absolute'], ['a\\..\\outside'], ['C:/outside']):
            with self.subTest(names=names), self.archive(names) as archive:
                with self.assertRaises(ValueError): engine.safe_members(archive)

    def test_symlink_rejected(self):
        name = zipfile.ZipInfo('link'); name.external_attr = 0o120777 << 16
        with self.archive([name]) as archive:
            with self.assertRaises(ValueError): engine.safe_members(archive)


class PendingAndBaseline(unittest.TestCase):
    def test_pending_configuration_cannot_start_production(self):
        config = json.loads((ROOT / tree.CONFIG).read_bytes())
        config['status'] = 'pending'; config['reviewedSource'] = None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'build-utils').mkdir()
            (root / tree.CONFIG).write_text(json.dumps(config))
            with patch.object(tree, 'ROOT', root):
                with self.assertRaises(ValueError): tree.pins()

    def test_604_cannot_replace_the_actual605_baseline(self):
        config = json.loads((ROOT / tree.CONFIG).read_bytes())
        config['baseline']['build'] = 604
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'build-utils').mkdir()
            (root / tree.CONFIG).write_text(json.dumps(config))
            with patch.object(tree, 'ROOT', root):
                with self.assertRaises(ValueError): tree.pins(ready=False)


class RecoveredProducerBinding(unittest.TestCase):
    def setUp(self):
        self.original = dict(source='a' * 40, run=10, job=11, attempt=1, artifact=12)
        self.config = dict(originalProducer=self.original, originalFailedStep='finalizer', originalFailure='Invalid final managed metrics',
            contractPath='contract.json', contractSha256='old-contract', currentContractSha256='updated-contract',
            verifierChanges={'build-utils/melonx/verify_performance_core.py': {'before': 'old', 'after': 'fixed'}},
            compileProofSha256={'runtime-smoke/actual-runtime.json': 'smoke'}, binaries={'ios-arm64': 'binary'}, identities={'ios-arm64': 'identity'})
        self.validation = dict(source='b' * 40, run=20, attempt=1, resultPath='finalization-validation/result.json')
        self.pin = dict(source='a' * 40, validation=self.validation)
        self.inputs = {'contract.json': 'updated-contract', 'test/melonx_performance_finalization_test.py': 'test'}
        original_member = b'immutable compiled proof'
        self.proof = dict(members={'core-validation/compiled.json': tree.sha(original_member)},
            smoke={'homebrewGuestSvcSessions': [1, 2]}, reusedEvidenceSha256={'reuse.json': 'reuse'})
        self.files = {'core-validation/compiled.json': original_member}
        for name in ('run', 'job', 'artifact'):
            self.files['finalization-validation/original-' + name + '.json'] = json.dumps({'kind': name, 'conclusion': 'failure'}).encode()
        self.files['finalization-validation/original-members.json'] = json.dumps(self.proof['members']).encode()
        regression = dict(result='passed', checks=26, originalFailureReproduced=True, originalFailure=self.config['originalFailure'],
            actualRuntimeSha256='smoke', correctedVerifierSha256='fixed', testSha256='test', engineExecuted=False,
            nativeCodeCompiled=False, historicalGatesReexecuted=False, physicalDeviceTested=False)
        self.files['finalization-validation/regression.json'] = json.dumps(regression).encode()
        self.result = dict(result='passed', schemaVersion=1, engineSource='a' * 40, originalRunConclusion='failure',
            **{key: self.config[key] for key in ('originalProducer', 'originalFailedStep', 'originalFailure', 'contractSha256',
                'currentContractSha256', 'verifierChanges', 'compileProofSha256', 'binaries', 'identities')},
            validation=dict(source='b' * 40, run=20, attempt=1, url='https://github.com/TarbleFR/RewindBox/actions/runs/20'),
            originalMembersSha256=tree.sha(self.files['finalization-validation/original-members.json']), originalMemberCount=1,
            inputs=self.inputs, homebrewSimulatorSessions=2, releasedBackingSessions=2, performanceDiagnosticsFinalSessions=2,
            guestSvcSessions=[1, 2], freshAppleGatesInOriginalProducer=4, reusedAppleGatesInOriginalProducer=32,
            historicalAppleReceipts=40, reusedEvidenceSha256=self.proof['reusedEvidenceSha256'], engineRecompiled=False,
            priorGatesReexecuted=False, smokeReexecuted=False, physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False,
            regressionSha256=tree.sha(self.files['finalization-validation/regression.json']))
        self.helper = SimpleNamespace(VALIDATION_INPUTS=('test/melonx_performance_finalization_test.py',),
            authenticate_origin=lambda config, run, job, artifact: tree.require(run['conclusion'] == job['conclusion'] == 'failure', 'wrong original origin'))

    def validate(self):
        raw = json.dumps(self.result).encode()
        self.files[self.validation['resultPath']] = raw; self.validation['resultSha256'] = tree.sha(raw)
        with patch.object(engine, 'inputs_match') as inputs:
            value = engine.validate_recovered_members(self.pin, self.files.__getitem__, set(self.files), self.proof,
                self.config, {'reusedAppleGates': 32}, self.helper)
            inputs.assert_called_once_with(self.inputs, 'b' * 40)
            return value

    def test_separate_success_preserves_original_failure(self):
        value = self.validate()
        self.assertEqual(value['originalRunConclusion'], 'failure')
        self.assertFalse(value['engineRecompiled'])

    def test_altered_original_compiled_member_rejected(self):
        self.files['core-validation/compiled.json'] = b'changed compiled proof'
        with self.assertRaises(ValueError): self.validate()

    def test_added_original_final_result_rejected(self):
        self.files['core-validation/result.json'] = b'{"result":"passed"}'
        self.proof['members']['core-validation/result.json'] = tree.sha(self.files['core-validation/result.json'])
        with self.assertRaises(ValueError): self.validate()

    def test_packaging_receipt_inside_producer_archive_is_still_rejected(self):
        self.files['packaging-identity.json'] = b'{}'
        with self.assertRaises(ValueError): self.validate()

    def test_original_failure_cannot_be_relabelled_after_rehashing_result(self):
        self.result['originalRunConclusion'] = 'success'
        with self.assertRaises(ValueError): self.validate()

    def test_recovery_cannot_claim_new_native_execution(self):
        for key in ('engineRecompiled', 'priorGatesReexecuted', 'smokeReexecuted', 'physicalDeviceTested'):
            with self.subTest(key=key):
                self.result[key] = True
                with self.assertRaises(ValueError): self.validate()
                self.result[key] = False

    def test_extra_verifier_change_in_result_rejected(self):
        self.result['verifierChanges'] = {**self.config['verifierChanges'], 'native/changed.cs': {'before': 'x', 'after': 'y'}}
        with self.assertRaises(ValueError): self.validate()

    def test_recovery_requires_its_own_successful_workflow_and_artifact(self):
        pin = dict(source='b' * 40, run=20, job=21, attempt=1, artifact=22, bytes=3, sha256='c' * 64,
            workflow='.github/workflows/melonx-performance-finalize.yml', name='MeloNX-ae78b4be-finalization-20')
        run = dict(id=20, head_sha=pin['source'], head_branch='Claude', path=pin['workflow'], status='completed', conclusion='success', run_attempt=1)
        job = dict(id=21, run_id=20, head_sha=pin['source'], conclusion='success', run_attempt=1,
            steps=[dict(name=name, conclusion='success') for name in engine.RECOVERY_STEPS])
        artifact = dict(id=22, name=pin['name'], size_in_bytes=3, digest='sha256:' + pin['sha256'], expired=False,
            workflow_run=dict(id=20, head_sha=pin['source']))
        self.assertEqual(engine.validate_origin(pin, run, job, artifact, 'core-validation')['run'], 20)
        run['conclusion'] = 'failure'
        with self.assertRaises(ValueError): engine.validate_origin(pin, run, job, artifact, 'core-validation')


class ExtractedCoreStaging(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'core'
        self.root.mkdir()
        self.members = {'ios-arm64/identity.json': b'original identity',
                        'finalization-validation/result.json': b'original validation'}
        for name, raw in self.members.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def validate(self):
        return engine.validate_extracted_members(self.root, self.members.__getitem__, set(self.members))

    def test_exact_extraction_and_two_local_packaging_receipts_are_accepted(self):
        self.assertEqual(self.validate(), {})
        for name in engine.LOCAL_PACKAGING_RECEIPTS:
            (self.root / name).write_bytes(b'{"fixture":"local packaging output"}')
        expected = {name: tree.sha((self.root / name).read_bytes()) for name in engine.LOCAL_PACKAGING_RECEIPTS}
        self.assertEqual(self.validate(), expected)

    def test_unknown_file_is_rejected(self):
        (self.root / 'unknown.json').write_bytes(b'{}')
        with self.assertRaises(ValueError): self.validate()

    def test_changed_original_is_rejected(self):
        (self.root / 'ios-arm64/identity.json').write_bytes(b'changed identity')
        with self.assertRaises(ValueError): self.validate()

    def test_missing_original_is_rejected(self):
        (self.root / 'ios-arm64/identity.json').unlink()
        with self.assertRaises(ValueError): self.validate()

    def test_symlink_including_allowed_packaging_name_is_rejected(self):
        (self.root / 'packaging-identity.json').symlink_to(self.root / 'ios-arm64/identity.json')
        with self.assertRaises(ValueError): self.validate()

    def test_symlink_directory_is_rejected(self):
        (self.root / 'linked').symlink_to(self.root / 'ios-arm64', target_is_directory=True)
        with self.assertRaises(ValueError): self.validate()

    def test_unknown_empty_directory_is_rejected(self):
        (self.root / 'unknown').mkdir()
        with self.assertRaises(ValueError): self.validate()


class RecoveredHostBinding(unittest.TestCase):
    def test_recovery_workflow_requires_explicit_old_command_provenance(self):
        with self.assertRaises(ValueError):
            engine.verify_host_recovery({}, {}, {'workflow': '.github/workflows/hogwarts606-host-recovery.yml'})

    def test_fresh_workflow_cannot_silently_carry_a_recovery_annotation(self):
        with self.assertRaises(ValueError):
            engine.verify_host_recovery({'recovery': {}}, {}, {'workflow': '.github/workflows/hogwarts606-host.yml'})

    def test_copied_original_output_must_remain_byte_identical(self):
        original_files = {'preflight.json': b'{"inputs":{}}', 'routing-native.json': b'foundation',
                          'flutter.execution.json': b'command', 'flutter.stdout': b'original output', 'flutter.stderr': b''}
        origin = b'{"origin":"failed original"}'
        expected = {'original': {'metadataSHA256': tree.sha(origin)}}
        outputs = {**original_files, 'original-host.zip': b'archive', 'reused-origin.json': origin}
        helper = SimpleNamespace(VERIFIER='helper.py', WORKFLOW='workflow.yml', REUSED=('flutter',),
            authenticate_origin=lambda value: None, original_files=lambda raw: original_files,
            verify_commit_inputs=lambda original: None, recovery_record=lambda *args: expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'helper.py').write_text('helper'); (root / 'workflow.yml').write_text('workflow')
            with patch.dict(sys.modules, {'hogwarts606_presentation_recovery': helper}), patch.object(engine, 'ROOT', root), patch.object(engine, 'inputs_match'):
                before = {'recovery': expected}
                pin = {'workflow': '.github/workflows/hogwarts606-host-recovery.yml', 'source': 'validated'}
                self.assertEqual(engine.verify_host_recovery(before, outputs, pin), expected)
                outputs['flutter.stdout'] = b'edited original output'
                with self.assertRaises(ValueError): engine.verify_host_recovery(before, outputs, pin)


if __name__ == '__main__':
    unittest.main()
