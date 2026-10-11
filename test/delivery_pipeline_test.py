"""Meaningful input-reuse and final-code identity guards for the new lane."""
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import unittest
import struct
import tempfile
import os

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reuse',ROOT/'build-utils/verify_delivery_reuse.py')
reuse=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/('build-utils/'+name+'.py'))
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

class DeliveryPipeline(unittest.TestCase):
    def test_reuse_rejects_modified_unrelated_runtime(self):
        for path in ('native/armsx2_internal_helper/Info.plist',
                     'native/neoswap-donation/Broker.cpp'):
            with self.subTest(path=path):
                file=ROOT/path
                old=file.read_bytes()
                try:
                    file.write_bytes(old+b'\n')
                    with self.assertRaisesRegex(ValueError,'Unreviewed validation input changed: '+path):
                        reuse.verify_tree()
                finally:
                    file.write_bytes(old)

    def test_current_library_and_native_reference_remain_exact(self):
        subprocess.run(['python3','test/retroarch_baseline_scope_test.py'],cwd=ROOT,check=True)
        changed,unchanged=reuse.verify_tree()
        self.assertGreater(len(unchanged),500)
        self.assertIn('lib/services/retroarch_library_service.dart',changed)
        # RPCS3's host allocators use best fit and publish active donated
        # backing. Their sources and the settings catalogue are tested anew;
        # IPC, extensions, storage and other engines keep their identities.
        native_changed={p for p in changed if p.startswith('native/')}
        self.assertEqual(native_changed,{
            'native/import-memory-candidate.json',
            'native/neoswap-donation/Pool.cpp',
            'native/neoswap-relay/Backend.cpp',
            'native/neoswap-relay/Backend.h',
            'native/neoswap/localizations.json',
        })
        self.assertTrue(native_changed<=reuse.NEOSWAP_434_DELTA|reuse.NEOSWAP_435_DELTA|reuse.NEOSWAP_MELONX_DELTA|reuse.NEOSWAP_DONATED_DELTA)

    def test_changed_neoswap_sources_have_fresh_native_checks(self):
        workflow=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
        native=workflow.split('  native:\n',1)[1].split('  cold:\n',1)[0]
        checks=native.split('name: Validate changed RPCS3 NeoSwap allocators and iPhone control plane',1)[1]
        checks=checks.split('    - name: Preserve exact NeoSwap native validation',1)[0]
        for path in reuse.NEOSWAP_MELONX_DELTA:
            if not path.endswith('NeoSwapDonationScheduler.h'):
                self.assertIn(path,checks)
        self.assertIn('test/neoswap_preparation_test.cpp',checks)
        self.assertIn('test/neoswap_relay_loans_test.cpp',checks)
        self.assertIn('test/neoswap_usage_policy_test.cpp',checks)
        self.assertIn('python3 test/rpcs3_neoswap_localizations_test.py',checks)
        self.assertIn('packages/neo_swap/ios/Classes/NeoSwapRelayService.mm',checks)
        self.assertIn("graph=Path('packages/rpcs3_internal_bridge/ios/Classes')",checks)
        self.assertIn("p.suffix in ('.h','.m','.mm')",checks)
        self.assertIn('packages/neo_swap/ios/neo_swap.podspec',checks)
        self.assertIn('-fsanitize=address,undefined',checks)
        self.assertIn('-DNEOSWAP_DONATION=1 -DNEOSWAP_RELAY=1 -DNEOSWAP_SHADER_STORAGE=1',checks)
        self.assertIn('-fsyntax-only',checks)
        self.assertIn('-arch arm64',checks)
        self.assertIn('hashlib.sha256',checks)

    def test_changed_neoswap_dart_inputs_invalidate_and_run_their_checks(self):
        workflow=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
        checks=workflow.split('  checks:\n',1)[1].split('  native:\n',1)[0]
        keys=re.findall(r'hashFiles\((.*?)\)',checks,re.S)
        self.assertEqual(len(keys),3) # Restore, record and verify the same key.
        self.assertEqual(keys,[keys[0]]*3)
        for path in ('native/neoswap/localizations.json','.github/workflows/retroarch-delivery.yml'):
            self.assertIn("'"+path+"'",keys[0])
        fresh=checks.split('name: Validate changed library, callback, launch and restart behavior',1)[1]
        fresh=fresh.split('    - name: Verify reused Dart evidence',1)[0]
        self.assertIn("steps.dart-evidence.outputs.cache-hit != 'true'",fresh)
        self.assertIn('flutter test test/neo_swap_locale_test.dart test/neo_swap_channel_test.dart test/neo_swap_dialog_test.dart',fresh)
        self.assertIn('python3 test/neoswap_donor_contract_test.py',checks)

    def test_donation_delta_is_explicit_and_excludes_other_runtimes(self):
        self.assertEqual(reuse.NEOSWAP_DONATED_DELTA,{
            'build-utils/validate_neoswap_donation_metrics.py',
            'lib/l10n/neoswap_locale.dart',
            'lib/screens/settings_screen/neoswap_dialog.dart',
            'native/neoswap-relay/Backend.cpp',
            'native/neoswap-relay/Backend.h',
            'native/neoswap/localizations.json',
            'packages/neo_swap/ios/Classes/NeoSwap.cpp',
            'packages/neo_swap/ios/Classes/NeoSwapDonationMetrics.h',
            'packages/neo_swap/ios/Classes/NeoSwapHost.h',
            'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
            'packages/neo_swap/ios/Classes/NeoSwapRelayService.mm',
            'packages/neo_swap/ios/neo_swap.podspec',
            'packages/rpcs3_internal_bridge/ios/Classes/NeoSwapUsagePolicy.h',
            'packages/rpcs3_internal_bridge/ios/Classes/RPCS3InGameLocalization.mm',
            'packages/rpcs3_internal_bridge/ios/Classes/RPCS3PerformanceOverlay.h',
            'packages/rpcs3_internal_bridge/ios/Classes/RPCS3PerformanceOverlay.mm',
            'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
            'test/neo_swap_dialog_test.dart',
            'test/neoswap_donor_contract_test.py',
            'test/neoswap_usage_policy_test.cpp',
            'test/neoswap_relay_loans_test.cpp',
            'test/relay_backend_test.cpp',
            'test/rpcs3_neoswap_localizations_test.py',
        })

    def test_release_device_and_signature_guards_are_active(self):
        workflow=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
        self.assertIn("generic/platform=iOS",workflow)
        self.assertIn('-configuration Release -sdk iphoneos',workflow)
        self.assertNotIn('flutter clean',workflow)
        self.assertIn('verify_delivery_reuse.py',workflow)
        self.assertIn('sign_delivery.py',(ROOT/'build-utils/delivery_benchmark.py').read_text().replace('from sign_delivery import sign','sign_delivery.py'))
        self.assertIn('codesign', (ROOT/'build-utils/sign_delivery.py').read_text())
        self.assertIn('allCompiledCodeAndDataSectionsUnchangedBySigning',(ROOT/'build-utils/delivery_benchmark.py').read_text())

    def test_final_payload_check_rejects_changed_device_code(self):
        benchmark=module('delivery_benchmark')
        header=struct.pack('<8I',0xfeedfacf,0x0100000c,0,2,2,176,0,0)
        segment=struct.pack('<II16sQQQQIIII',0x19,152,b'__TEXT',0x100000000,4096,0,212,7,5,1,0)
        section=struct.pack('<16s16sQQIIIIIIII',b'__text',b'__TEXT',0x1000000d0,4,208,2,0,0,0x80000400,0,0,0)
        version=struct.pack('<6I',0x32,24,2,0x00110400,0x001a0200,0)
        original=header+segment+section+version+b'ABCD'
        self.assertNotEqual(benchmark.payload_fingerprint(original),benchmark.payload_fingerprint(original[:-1]+b'E'))

    def test_source_metadata_restoration_requires_identical_bytes(self):
        benchmark=module('delivery_benchmark')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'native').mkdir()
            source=folder/'native/fixture.cpp';source.write_text('verified source')
            subprocess.run(['git','init','-q',str(folder)],check=True)
            subprocess.run(['git','-C',str(folder),'add','native'],check=True)
            benchmark.ROOT=folder
            before=source.stat().st_mtime_ns;benchmark.source_times()
            os.utime(source,ns=(before+1000000000,before+1000000000))
            benchmark.source_times(True)
            self.assertEqual(source.stat().st_mtime_ns,before)
            source.write_text('changed source')
            with self.assertRaisesRegex(ValueError,'source identity changed'):benchmark.source_times(True)

    def test_artifact_encryption_round_trip(self):
        cipher=module('delivery_cipher')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'build-utils').mkdir();source=folder/'source';source.mkdir()
            (source/'NeoStation.ipa').write_bytes(b'private delivery fixture')
            private=folder/'key.pem';public=folder/'build-utils/delivery-422-recipient.pem'
            subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',str(private)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['openssl','pkey','-in',str(private),'-pubout','-out',str(public)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cipher.ROOT=folder
            cipher.artifact(source,folder/'encrypted')
            password=folder/'password';archive=folder/'archive.tar'
            subprocess.run(['openssl','pkeyutl','-decrypt','-inkey',str(private),'-in',str(folder/'encrypted/password.rsa'),'-out',str(password),'-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256'],check=True)
            cipher.aes(folder/'encrypted/artifact.tar.enc',archive,password,decrypt=True)
            import tarfile
            with tarfile.open(archive) as tar:
                self.assertEqual(tar.extractfile('./NeoStation.ipa').read(),b'private delivery fixture')

    def test_compilation_cache_rejects_tampering(self):
        from unittest.mock import patch
        cipher=module('delivery_cipher')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);fixture=folder/'fixture';fixture.mkdir()
            (fixture/'code').write_bytes(b'compiled fixture')
            cipher.ROOT=folder;cipher.CACHE_PATHS=['fixture']
            with patch.dict(os.environ,{'SCREENSCRAPER_DEV_PASSWORD':'test-only-secret','GITHUB_SHA':'a'*40,'BUILD_NUMBER':'422'}):
                cipher.cache()
                (fixture/'code').unlink()
                cipher.cache(True)
                self.assertEqual((fixture/'code').read_bytes(),b'compiled fixture')
                blob=folder/'.ci-cache/device-state.enc'
                raw=bytearray(blob.read_bytes());raw[-1]^=1;blob.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'authentication failed'):cipher.cache(True)

if __name__=='__main__': unittest.main(verbosity=2)
