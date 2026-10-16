#!/usr/bin/env python3
"""Offline integrity/redistribution and complete index checks; no emulation claim."""
import hashlib,json,re,unittest,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'packages/libretro_internal_bridge/ios/Resources/Cheats'
class Bootstrap(unittest.TestCase):
 def test_all_resources_match_manifest(self):
  manifest=json.loads((DATA/'manifest.json').read_text())
  self.assertEqual(set(manifest['outputs']),{p.name for p in DATA.iterdir() if p.name!='manifest.json'})
  for name,digest in manifest['outputs'].items():
   with self.subTest(name=name):self.assertEqual(hashlib.sha256((DATA/name).read_bytes()).hexdigest(),digest)
 def test_complete_bounded_indices_and_unique_paths(self):
  games=identities=0
  for path in DATA.glob('libretro-*.json'):
   catalog=json.loads(path.read_text());self.assertLessEqual(len(catalog['games']),20000)
   self.assertEqual(len({r['path'] for r in catalog['games']}),len(catalog['games']))
   for row in catalog['games']:
    self.assertEqual(row['console'],catalog['console']);self.assertRegex(row['sha'],'^[a-f0-9]{40}$')
    self.assertEqual(row['revision'],catalog['revision']);self.assertTrue(row['path'].endswith('.cht'))
   for row in catalog['identities']:
    self.assertTrue(row['title']);self.assertTrue(row.get('md5') or row.get('sha1'))
    if 'md5' in row:self.assertRegex(row['md5'],'^[a-f0-9]{32}$')
    if 'sha1' in row:self.assertRegex(row['sha1'],'^[a-f0-9]{40}$')
   games+=len(catalog['games']);identities+=len(catalog['identities'])
  self.assertEqual(games,22746);self.assertEqual(identities,40398)
  print('Bundled official entries:',games,'content identities:',identities)
 def test_initial_offline_codes_and_licences(self):
  xml=ET.parse(DATA/'openemu.xml');self.assertEqual(len(xml.findall('.//game')),10)
  self.assertEqual((DATA/'openemu.xml').read_bytes(),(ROOT/'test/fixtures/libretro_cheats/openemu-original.xml').read_bytes())
  for source in ('openemu','libretro'):
   self.assertEqual((DATA/(source+'-LICENSE')).read_bytes(),(ROOT/'test/fixtures/libretro_cheats'/(source+'-LICENSE')).read_bytes())
 def test_twelve_complete_locales(self):
  text=(ROOT/'lib/l10n/libretro_locale.dart').read_text()
  for key in ('cheatFind','cheatNoSources','cheatNoVariant','cheatNone','cheatRetry','cheatDisableAll','cheatCoreUnsupported','cheatEffectsHelp','cheatResultsLimited'):
   self.assertEqual(text.count('"'+key+'":'),12,key)
  self.assertIn("'zh_Hant':",text)
if __name__=='__main__':unittest.main()
