import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).with_name('scan.py')
spec = importlib.util.spec_from_file_location('ipa_upload_scan', SCRIPT)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


class UploadBoundaryTest(unittest.TestCase):
    def check_bytes(self, value, name='archive.zip', budget=None):
        scan.scan_stream(io.BytesIO(value), name, budget)

    def test_plain_ipa_rejected_even_with_innocent_contents(self):
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(b'fixture', 'RewindBox.ipa')

    def test_uppercase_and_compressed_ipa_names_rejected(self):
        for name in ['PRIVATE.IPA', 'candidate.ipa.zip', 'candidate.ipa.tar.gz']:
            with self.subTest(name=name), self.assertRaises(scan.UnsafeArtifact):
                self.check_bytes(b'fixture', name)

    def test_ipa_in_github_artifact_rejected(self):
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'notes.txt': b'proof', 'NeoStation.ipa': b'app'}))

    def test_renamed_installable_zip_rejected(self):
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'Payload/Runner.app/Info.plist': b'plist'}), 'data.bin')

    def test_prefixed_and_renamed_zip_rejected_at_both_levels(self):
        data = b'harmless transport prefix\n' + zipped({'Payload/Runner.app/Runner': b'app'})
        for value in (data, zipped({'innocent.bin': data})):
            with self.subTest(nested=value is not data), self.assertRaises(scan.UnsafeArtifact):
                self.check_bytes(value, 'evidence.bin')

    def test_renamed_v7_tar_rejected_at_both_levels(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            info = tarfile.TarInfo('Payload/Runner.app/Runner')
            info.size = 3
            archive.addfile(info, io.BytesIO(b'app'))
        data = bytearray(raw.getvalue())
        data[257:265] = b'\0' * 8
        data[148:156] = b' ' * 8
        data[148:156] = ('%06o\0 ' % sum(data[:512])).encode()
        for value in (bytes(data), zipped({'innocent.bin': bytes(data)})):
            with self.subTest(nested=value[:2] == b'PK'), self.assertRaises(scan.UnsafeArtifact):
                self.check_bytes(value, 'evidence.bin')

    def test_nested_original_zip_republication_rejected(self):
        package = zipped({'Payload/Runner.app/Runner': b'app'})
        original = zipped({'innocent.bin': package})
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'republication.json': b'{}', 'original.zip': original}))

    def test_nested_gzip_tar_rejected(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            info = tarfile.TarInfo('evidence/candidate.ipa')
            info.size = 3
            archive.addfile(info, io.BytesIO(b'app'))
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'evidence.tar.gz': gzip.compress(buffer.getvalue())}))

    def test_archived_device_application_rejected(self):
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'Build.xcarchive/Products/Applications/Runner.app/Runner': b'app'}))

    def test_core_and_xctest_components_remain_public(self):
        self.check_bytes(zipped({'MeloNXCore.framework/MeloNXCore': b'\xcf\xfa\xed\xfe'+b'core',
                                 'DolphinTests.xcresult/Data/data.0': b'test',
                                 'original.zip': zipped({'libRPCS3Core.dylib': b'core'})}))

    def test_encrypted_envelope_and_cms_are_not_plaintext_ipas(self):
        self.check_bytes(zipped({'artifact.tar.enc': b'Salted__'+b'ciphertext',
                                 'password.rsa': b'encrypted session key',
                                 'format.json': b'{}'}))
        self.check_bytes(zipped({'NeoStation.ipa.p7m': b'\x30\x82'+b'CMS envelope',
                                 'NeoStation.ipa.sha256': b'digest'}))

    def test_renamed_plaintext_is_not_accepted_as_encryption(self):
        with self.assertRaises(scan.UnsafeArtifact):
            self.check_bytes(zipped({'artifact.tar.enc': zipped({'Payload/Runner.app/Runner': b'app'})}))

    def test_truncated_archive_fails_closed(self):
        with self.assertRaises(scan.InspectionError):
            self.check_bytes(b'PK\x03\x04broken')

    def test_uninspectable_archive_fails_closed(self):
        with self.assertRaises(scan.InspectionError):
            self.check_bytes(b'7z\xbc\xaf\x27\x1c'+b'compressed', 'evidence.bin')

    def test_member_budget_fails_closed(self):
        with self.assertRaises(scan.InspectionError):
            self.check_bytes(zipped({'a.txt': b'one', 'b.txt': b'two'}),
                             budget=scan.Budget(max_members=1))

    def test_compressed_byte_budget_fails_closed(self):
        with self.assertRaises(scan.InspectionError):
            self.check_bytes(gzip.compress(b'a'*2048), 'log.gz', scan.Budget(max_bytes=1024))

    def test_nested_depth_fails_closed(self):
        data = b'plain'
        for _ in range(11):
            data = zipped({'nested.zip' if data.startswith(b'PK') else 'note.txt': data})
        with self.assertRaises(scan.InspectionError):
            self.check_bytes(data)

    def test_cli_blocks_upload_directory_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'NeoStation.ipa'
            path.write_bytes(b'app')
            result = subprocess.run([sys.executable, str(SCRIPT)],
                env={**os.environ, 'IPA_ARTIFACT_PATHS': folder}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Plaintext IPA', result.stderr)
            self.assertEqual(path.read_bytes(), b'app')

    def test_directory_symlink_does_not_hide_ipa(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'source').mkdir()
            (root/'source'/'candidate.ipa').write_bytes(b'app')
            (root/'upload').mkdir()
            try:
                (root/'upload'/'alias').symlink_to(root/'source', target_is_directory=True)
            except OSError:
                self.skipTest('Symlinks unavailable')
            with self.assertRaises(scan.UnsafeArtifact):
                scan.scan_paths(str(root/'upload'))

    def test_symlink_cycle_terminates_after_unique_target_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            try:
                (Path(folder)/'cycle').symlink_to(folder, target_is_directory=True)
            except OSError:
                self.skipTest('Symlinks unavailable')
            (Path(folder)/'receipt.json').write_text('{}')
            self.assertEqual(scan.scan_paths(folder)['filesInspected'], 1)

    def test_directory_alias_preserves_legitimate_framework_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'real').mkdir()
            (root/'real'/'binary').write_bytes(b'framework')
            try:
                (root/'alias').symlink_to(root/'real', target_is_directory=True)
            except OSError:
                self.skipTest('Symlinks unavailable')
            self.assertEqual(scan.scan_paths(folder)['filesInspected'], 1)

    def test_hidden_ipa_and_exclusion_cannot_bypass_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'.private.ipa').write_bytes(b'app')
            with self.assertRaises(scan.UnsafeArtifact):
                scan.scan_paths(folder+'\n!'+folder+'/.private.ipa')

    def test_missing_glob_preserves_uploader_missing_file_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(scan.scan_paths(folder+'/missing/*.txt')['filesInspected'], 0)

    def test_plain_reports_pass_through_real_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'receipt.json').write_text('{}')
            result = subprocess.run([sys.executable, str(SCRIPT), folder], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['filesInspected'], 1)


if __name__ == '__main__':
    unittest.main()
