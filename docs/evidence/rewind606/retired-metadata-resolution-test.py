"""Focused private predicate checks on the actual authenticated metadata only."""
import copy
import json
from pathlib import Path
import unittest
import zipfile

import verify_downloaded_ipa606 as verify

BASE=Path('/workspace/scratch/17fcc7f76cc4')


class ExactRetiredMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(BASE/'private606/download/RewindBox-606.ipa') as archive:
            cls.raw=archive.read(verify.ROOT+verify.IDENTITY)
        cls.identity=json.loads(cls.raw)
        with zipfile.ZipFile(BASE/'delivery606/host.zip') as archive:
            raw=archive.read('result.json')
        pin=json.loads((BASE/'RewindBox/build-utils/rewind606-delivery.json').read_bytes())['host']
        assert verify.sha(raw)==pin['resultSha256']
        cls.host=json.loads(raw)
        cls.scan=json.loads((BASE/'private606/download/retired-component-scan.json').read_bytes())['dusklight']

    def reject(self,scan=None,identity=None,host=None):
        with self.assertRaises(ValueError):
            verify.retired_metadata_resolution(scan or self.scan,
                json.dumps(identity).encode() if identity is not None else self.raw,
                host or self.host)

    def test_actual_three_audit_mentions_resolved_without_rewriting_failed_scan(self):
        before=copy.deepcopy(self.scan)
        result=verify.retired_metadata_resolution(self.scan,self.raw,self.host)
        self.assertFalse(result['canonicalGuardPassed'])
        self.assertFalse(result['runtimeOrAssetExceptionGranted'])
        self.assertEqual(result['occurrenceCount'],3)
        self.assertEqual(before,self.scan)
        self.assertFalse(self.scan['passed'])

    def test_runtime_file_finding_still_fails(self):
        scan=copy.deepcopy(self.scan);scan['findings']['Frameworks/rogue.framework/rogue']=['1 occurrence']
        self.reject(scan=scan)

    def test_ports_asset_finding_still_fails(self):
        scan=copy.deepcopy(self.scan);scan['findings']['Frameworks/App.framework/flutter_assets/assets/systems/ports.json']=['removed component']
        self.reject(scan=scan)

    def test_any_additional_identity_occurrence_fails(self):
        identity=copy.deepcopy(self.identity);identity['extra']='dusklight'
        self.reject(identity=identity)

    def test_same_count_at_another_json_path_fails(self):
        identity=copy.deepcopy(self.identity);host=copy.deepcopy(self.host)
        phrase=host['flutter']['names'][18];host['flutter']['names'][18]='neutral test name'
        identity['hostChecks']['originalHostResult']=host;identity['extra']=phrase
        self.reject(identity=identity,host=host)

    def test_unauthenticated_embedded_host_fails(self):
        identity=copy.deepcopy(self.identity);identity['hostChecks']['originalHostResult']['execution']['run']+=1
        self.reject(identity=identity)

    def test_altered_guard_input_hash_fails_even_if_supplied_host_matches(self):
        identity=copy.deepcopy(self.identity);host=copy.deepcopy(self.host)
        host['inputs']['test/no_dusklight_ipa_test.py']='0'*64
        identity['hostChecks']['originalHostResult']=host
        self.reject(identity=identity,host=host)

    def test_altered_test_name_fails_even_if_supplied_host_matches(self):
        identity=copy.deepcopy(self.identity);host=copy.deepcopy(self.host)
        host['flutter']['names'][18]='different Dusklight mention'
        identity['hostChecks']['originalHostResult']=host
        self.reject(identity=identity,host=host)


if __name__=='__main__':unittest.main()
