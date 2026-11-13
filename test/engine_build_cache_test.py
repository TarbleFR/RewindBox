#!/usr/bin/env python3
"""Offline boundaries of optional engine build/download caches."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE_ACTION = '0057852bfaa89a56745cba8c7296529d2fc39830'
spec = importlib.util.spec_from_file_location('prefetch', ROOT / 'build-utils/s2arm/engine/prefetch_sources.py')
prefetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prefetch)
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import retained_components


class EngineCacheTest(unittest.TestCase):
    def workflow(self, name):
        return yaml.safe_load((ROOT / f'.github/workflows/{name}.yml').read_text())

    def test_melonx_request_matrix_and_envelope_boundaries(self):
        workflow = self.workflow('melonx-core')
        expression = workflow['jobs']['core']['if']
        markers = re.findall(r"contains\(github.event.head_commit.message, '([^']+)'\)", expression)
        self.assertEqual(markers, ['[melonx-dma-core]', '[melonx-arrays-core]', '[melonx-reads-core]',
                                  '[melonx-liveness-core]', '[hogwarts606-checks]', '[melonx-launch-only]'])
        # Evaluate the actual restricted Actions expression across the request matrix.
        for event, message, expected in [('workflow_dispatch', '', True), ('push', 'ordinary change', False),
                                        ('push', '[standard-delivery] IPA 733', False)] + [
                                            ('push', marker, True) for marker in markers]:
            actual = expression.removeprefix('${{').removesuffix('}}').strip()
            actual = actual.replace('github.event_name', repr(event)).replace('github.event.head_commit.message', repr(message))
            self.assertEqual(eval(actual.replace('||', 'or'), {'contains': lambda value, marker: marker in value}), expected)
        self.assertFalse(workflow['concurrency']['cancel-in-progress'])
        recovery = json.loads((ROOT / 'build-utils/melonx/core-baseline.json').read_text())['recovery']
        native = json.loads((ROOT / 'build-utils/delivery/666.json').read_text())['components']['melonx-dependencies']
        expected = {
            '.native-sources/melonx-core743-recovery.zip.republished.zip': recovery['743']['republished']['sha256'],
            '.native-sources/melonx-b181cbe1-arrays.zip.republished.zip': recovery['614']['republished']['sha256'],
            'build/components-retained/retained-melonx-dependencies.zip.republished.zip': native['republished']['sha256']}
        actual_native = retained_components.retained_archive('melonx-dependencies').relative_to(ROOT)
        self.assertIn(str(actual_native) + '.republished.zip', expected)
        for action in ('restore', 'save'):
            steps = [step for step in workflow['jobs']['core']['steps'] if step.get('uses', '').startswith('actions/cache/' + action)]
            self.assertEqual(len(steps), 3)
            for step in steps:
                self.assertEqual(step['uses'], f'actions/cache/{action}@{CACHE_ACTION}')
                self.assertEqual(step['with']['key'], 'melonx-envelope-v1-' + expected[step['with']['path']])
                self.assertNotIn('restore-keys', step['with'])

    def test_s2arm_missing_valid_corrupt_and_bad_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / 'sources'
            payloads = {}
            for codec, extension, _ in prefetch.CODECS:
                data = codec.encode()
                payloads[codec] = data
                recipe = root / 'services' / codec / 'build.sh'
                recipe.parent.mkdir(parents=True)
                recipe.write_text(f'VER=1.2; SHA={hashlib.sha256(data).hexdigest()}\n')
            requests = []
            def download(url, path):
                requests.append(url)
                path.write_bytes(payloads['opus' if 'opus' in url else 'dav1d'])
            prefetch.prefetch(root, cache, download)
            self.assertEqual(len(requests), 2)
            requests.clear()
            prefetch.prefetch(root, cache, download)
            self.assertEqual(requests, [])
            target = next(cache.glob('*/opus-*'))
            target.write_bytes(b'bad!')
            prefetch.prefetch(root, cache, download)
            self.assertEqual(len(requests), 1)
            target.unlink()
            with self.assertRaises(ValueError):
                prefetch.prefetch(root, cache, lambda url, path: path.write_bytes(b'untrusted'))
            self.assertFalse(target.exists())
            target.symlink_to(root / 'outside')
            prefetch.prefetch(root, cache, download)
            self.assertFalse(target.is_symlink())
            self.assertFalse((root / 'outside').exists())
            (root / 'services/opus/build.sh').write_text('VER=../../escape; SHA=' + '0'*64)
            with self.assertRaises(ValueError):
                prefetch.prefetch(root, cache, download)
        workflow = self.workflow('s2arm-engine')
        self.assertEqual(workflow['jobs']['engine']['strategy']['matrix']['os'], ['macos-26', 'macos-15'])
        for step in workflow['jobs']['engine']['steps']:
            if step.get('uses', '').startswith('actions/cache/'):
                self.assertEqual(step['with']['path'], '${{ runner.temp }}/s2arm-build-cache/sources')



if __name__ == '__main__':
    unittest.main()
