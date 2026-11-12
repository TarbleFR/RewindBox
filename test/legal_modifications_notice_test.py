#!/usr/bin/env python3
"""The shipped modifications notice names the engine revisions the repository pins.

assets/legal/RewindBox-MODIFICATIONS.md is required in every IPA's Legal
directory (build-utils/embed_legal_bundle.py REQUIRED_LEGAL_FILES). It states
which engines RewindBox modified, from which upstream revision and where the
changes are (GPL-2.0 2(a), GPL-3.0 5(a), Apache-2.0 4(b), MPL-2.0 3). A pin that
moves without the notice fails here.
"""
from pathlib import Path
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = ROOT / 'assets/legal/RewindBox-MODIFICATIONS.md'
sys.path.insert(0, str(ROOT / 'build-utils'))
sys.dont_write_bytecode = True


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def latest_delivery() -> dict:
    manifests = sorted((ROOT / 'build-utils/delivery').glob('[0-9]*.json'), key=lambda path: int(path.stem))
    return json.loads(manifests[-1].read_text())


class ModificationsNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = NOTICE.read_text()

    def test_it_ships_in_every_legal_bundle(self):
        import embed_legal_bundle
        self.assertIn('RewindBox-MODIFICATIONS.md', embed_legal_bundle.REQUIRED_LEGAL_FILES)

    def test_every_pinned_engine_revision_is_named(self):
        pins = {
            'RPCS3': load('build-utils/rpcs3/canonical-source.json')['upstream_commit'],
            'ARMSX2': load('build-utils/armsx2/source.json')['revision'],
            'MeloNX': load('build-utils/melonx/source.json')['revision'],
            'XeniOS': load('build-utils/xenia/source.json')['revision'],
            'StikJIT': load('build-utils/stikjit/source.json')['revision'],
            'S2Arm': load('build-utils/s2arm/engine-pin.json')['identity']['sourceIdentity']['s2arm_commit'],
            'Nestopia': load('native/nestopia/source.json')['revision'],
            'PPSSPP': load('native/ppsspp/source.json')['revision'],
            'Dolphin': latest_delivery()['components']['dolphin']['upstreamRevision'],
        }
        for engine, revision in pins.items():
            self.assertRegex(revision, r'^[0-9a-f]{40}$', engine)
            row = next((line for line in self.text.splitlines() if line.startswith(f'| {engine}')), '')
            self.assertIn(f'`{revision}`', row, f'{engine}: the notice does not name the pinned revision {revision}')

    def test_every_named_change_location_exists(self):
        for path in re.findall(r'`((?:build-utils|packages|native)/[^`*]+)`', self.text):
            self.assertTrue((ROOT / path.rstrip('/')).exists(), path)
        for pattern in re.findall(r'`((?:build-utils|packages|native)/[^`]*\*[^`]*)`', self.text):
            self.assertTrue(list(ROOT.glob(pattern)), pattern)


if __name__ == '__main__':
    unittest.main()
