#!/usr/bin/env python3
"""Offline checks for the independent archive diagnostic; no creator downloads."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import hosts
import research


class ArchiveDiagnosticTests(unittest.TestCase):
    def test_missing_decoder_and_interruption_are_inconclusive(self):
        for result in [
            {'exit_code': 2, 'output': 'ERROR: Unsupported Method\nData Error'},
            {'exit_code': 2, 'output': 'CRC Failed : encrypted (wrong password?)'},
            {'exit_code': 2, 'output': 'Data Error', 'timed_out': True},
            {'exit_code': 8, 'output': 'not enough memory'},
            {'exit_code': 0, 'output': 'No files to process'},
        ]:
            self.assertIsNone(research.archive_test_verdict(result)['crc_valid'])
        self.assertTrue(research.archive_test_verdict({'exit_code': 0, 'output': 'Everything is Ok'})['crc_valid'])
        self.assertFalse(research.archive_test_verdict({'exit_code': 2, 'output': 'ERROR: CRC Failed : member.png'})['crc_valid'])

    def test_tool_output_is_drained_and_bounded(self):
        result = research.bounded_command([sys.executable, '-c', "print('start'+('X'*200000)+'finish')"], limit=1024)
        self.assertEqual(result['exit_code'], 0)
        self.assertTrue(result['output_truncated'])
        self.assertGreater(result['output_bytes'], 200000)
        self.assertLess(len(result['output']), 1100)
        self.assertTrue(result['output'].startswith('start'))
        self.assertIn('finish', result['output'])
        result = research.bounded_command([sys.executable, '-c',
            "import sys; print('X'*20000+'Unsupported Method'+'Y'*20000+'CRC Failed'); sys.exit(2)"], limit=1024)
        self.assertNotIn('Unsupported Method', result['output'])
        self.assertIsNone(research.archive_test_verdict(result)['crc_valid'])

    def test_exact_pins_and_duplicate_ids(self):
        targets = ROOT / 'tools/textures/research/direct400-rar-crc-review.json'
        self.assertEqual(len(research.pinned_archive_targets(targets, 4 << 30)), 3)
        with self.assertRaises(ValueError):
            research.pinned_archive_targets(targets, 3 << 30)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'targets.json'
            target = json.loads(targets.read_text())['archives'][0]
            path.write_text(json.dumps([target, target]))
            with self.assertRaises(ValueError):
                research.pinned_archive_targets(path, 4 << 30)

    def test_download_once_exact_sha_before_read_only_test_and_cleanup(self):
        body = b'Rar!\x1a\x07\x01\x00synthetic protocol fixture'
        target = {'id': 'fixture', 'url': 'https://drive.google.com/file/d/synthetic/view',
                  'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()}

        def fetch(url, path, limit):
            self.assertEqual(limit, len(body))
            Path(path).write_bytes(body)
            return {'size': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'final': 'https://signed.invalid/secret'}

        with tempfile.TemporaryDirectory() as temporary, patch.object(hosts, 'fetch', side_effect=fetch) as download, \
                patch.object(research, 'pace'), patch.object(research, 'bounded_command', return_value={'exit_code': 0, 'output': 'Everything is Ok'}) as command:
            result = research.probe_archive(target, temporary, {'selected': '/fixture/7z'})
            self.assertTrue(result['sha256_pin_matched'])
            self.assertTrue(result['crc_valid'])
            download.assert_called_once()
            self.assertEqual(command.call_args.args[0][1:6], ['t', '-bd', '-bb0', '-y', '--'])
            self.assertNotIn('secret', json.dumps(result))
            self.assertEqual(list(Path(temporary).iterdir()), [])
            target['sha256'] = '0' * 64
            command.reset_mock()
            result = research.probe_archive(target, temporary, {'selected': '/fixture/7z'})
            self.assertEqual(result['status'], 'changed')
            command.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_refusal_has_no_fallback_and_missing_tool_has_no_download(self):
        target = {'id': 'fixture', 'url': 'https://drive.google.com/file/d/synthetic/view', 'size': 1, 'sha256': '0' * 64}
        with tempfile.TemporaryDirectory() as temporary, patch.object(hosts, 'fetch', side_effect=hosts.HostError('quota', 'HTTP 429')) as download, \
                patch.object(research, 'pace'), patch.object(research, 'bounded_command') as command:
            result = research.probe_archive(target, temporary, {'selected': '/fixture/7z'})
            self.assertEqual(result['status'], 'quota')
            self.assertIsNone(result['crc_valid'])
            download.assert_called_once()
            command.assert_not_called()
            download.reset_mock()
            result = research.probe_archive(target, temporary, {'selected': None, 'reason': 'no RAR decoder'})
            self.assertEqual(result['status'], 'archive_test_inconclusive')
            download.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
