#!/usr/bin/env python3
"""Exercise recovery file preservation and refusal paths without a native build."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', ROOT/'build-utils/rpcs3/collect_rpcs3_mvk_unverified_core.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class Capture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rpcs3-unverified-capture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.dist = self.root/'dist'
        self.dist.mkdir()
        self.core = self.dist/'libRPCS3Core.dylib'
        self.core.write_bytes(b'actual failed-metadata binary fixture')
        (self.dist/'RPCS3_IOS_ABI.txt').write_text('30\n')
        self.native = self.root/'native'
        (self.native/'rpcs3').mkdir(parents=True)
        (self.native/'rpcs3/git-version.h').write_text('#define RPCS3_GIT_VERSION "generated"\n')
        self.build = self.root/'build'
        (self.build/'sub').mkdir(parents=True)
        (self.build/'sub/core.rsp').write_text('object.o -framework Metal')
        self.proof = self.root/'proof.json'
        self.proof.write_text(json.dumps({'compiled_source_root':str(self.native),'build_root':str(self.build)}))
        self.out = self.root/'diagnostics'

    def collect(self):
        return recovery.collect(self.dist,self.proof,self.out,'a'*40,'123')

    def test_full_preservation_and_exact_build_inputs(self):
        original = recovery.fingerprint(self.core)
        result = self.collect()
        self.assertEqual(result['status'],'captured_unverified_core')
        self.assertEqual(result['validation_status'],'unverified')
        self.assertTrue(result['full_dist_copied'])
        self.assertFalse(result['verified_core_claimed'])
        self.assertEqual(recovery.fingerprint(self.out/'unverified-core/libRPCS3Core.dylib'),original)
        self.assertEqual(result['captured_build_inputs']['git-version.h'],dict(recovery.fingerprint(self.native/'rpcs3/git-version.h'),source_path=str(self.native/'rpcs3/git-version.h')))
        self.assertEqual(result['captured_response_files'],1)
        self.assertEqual((self.out/'captured-build-inputs/link-response/sub/core.rsp').read_bytes(),(self.build/'sub/core.rsp').read_bytes())
        self.assertEqual(recovery.fingerprint(self.core),original)

    def test_existing_gate_identity_skips_duplicate_binary(self):
        item=dict(recovery.fingerprint(self.core),type='rpcs3-ios-mvk-deferred-cache-candidate',host_commit='a'*40,abi_version=30,architectures=['arm64'],actual_ios_syntax_compile_link_passed=True)
        (self.dist/'identity.json').write_text(json.dumps(item))
        result=self.collect()
        self.assertEqual(result['status'],'gate_identity_present_recovery_not_needed')
        self.assertFalse((self.out/'unverified-core').exists())
        self.assertFalse(result['verified_core_claimed'])

    def test_job_failure_preserves_binary_even_with_gate_identity(self):
        item=dict(recovery.fingerprint(self.core),type='rpcs3-ios-mvk-deferred-cache-candidate',host_commit='a'*40,abi_version=30,architectures=['arm64'],actual_ios_syntax_compile_link_passed=True)
        (self.dist/'identity.json').write_text(json.dumps(item))
        result=recovery.collect(self.dist,self.proof,self.out,'a'*40,'123',job_status='failure')
        self.assertEqual(result['status'],'unverified_capture_due_to_job_failure')
        self.assertTrue(result['gate_identity_present'])
        self.assertEqual(result['validation_status'],'unverified')
        self.assertFalse(result['verified_core_claimed'])
        self.assertTrue((self.out/'unverified-core/libRPCS3Core.dylib').is_file())
        self.assertTrue((self.out/'unverified-core/identity.json').is_file())
        self.assertEqual(result['captured_response_files'],1)

    def test_stale_identity_does_not_suppress_recovery(self):
        (self.dist/'identity.json').write_text(json.dumps({'sha256':'wrong','type':'rpcs3-ios-mvk-deferred-cache-candidate'}))
        result=self.collect()
        self.assertEqual(result['status'],'captured_unverified_core')
        self.assertTrue((self.out/'unverified-core/identity.json').is_file())

    def test_missing_proof_preserves_binary_without_invented_roots(self):
        self.proof.unlink()
        result=self.collect()
        self.assertTrue((self.out/'unverified-core/libRPCS3Core.dylib').is_file())
        self.assertEqual(result['captured_build_inputs'],{})
        self.assertTrue(any(item['input']=='compiled_source_root' for item in result['warnings']))

    def test_symlinks_cannot_capture_outside_data(self):
        secret=self.root/'outside-secret'
        secret.write_text('must not be copied')
        (self.dist/'unexpected').symlink_to(secret)
        (self.build/'sub/outside.rsp').symlink_to(secret)
        (self.build/'elsewhere').symlink_to(self.root,target_is_directory=True)
        (self.native/'rpcs3/git-version.h').unlink()
        (self.native/'rpcs3/git-version.h').symlink_to(secret)
        result=self.collect()
        self.assertFalse(result['full_dist_copied'])
        self.assertFalse((self.out/'unverified-core/unexpected').exists())
        self.assertFalse((self.out/'captured-build-inputs/git-version.h').exists())
        self.assertFalse((self.out/'captured-build-inputs/link-response/sub/outside.rsp').exists())
        self.assertEqual(result['captured_response_files'],1)
        self.assertEqual(secret.read_text(),'must not be copied')

    def test_rsp_bounds_leave_binary_available(self):
        old=recovery.MAX_RSP_BYTES
        recovery.MAX_RSP_BYTES=1
        self.addCleanup(setattr,recovery,'MAX_RSP_BYTES',old)
        result=self.collect()
        self.assertEqual(result['captured_response_files'],0)
        self.assertTrue((self.out/'unverified-core/libRPCS3Core.dylib').is_file())
        self.assertTrue(any(item['reason']=='response_capture_bound_exceeded' for item in result['warnings']))

    def test_existing_recovery_files_are_not_overwritten(self):
        self.out.mkdir()
        (self.out/'unverified-core').mkdir()
        protected=self.out/'unverified-core/keep'
        protected.write_text('preserve')
        with self.assertRaises(ValueError):self.collect()
        self.assertEqual(protected.read_text(),'preserve')

    def test_no_core_is_reported_without_fabrication(self):
        self.core.unlink()
        result=self.collect()
        self.assertEqual(result['status'],'no_core_available')
        self.assertFalse((self.out/'unverified-core').exists())


if __name__=='__main__':
    unittest.main()
