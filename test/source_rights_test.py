"""Verify the real withdrawal and overlay metadata against their reviewed input."""
import base64
import gzip
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='8308865b873879f74768aff10a9d336d074cb8f7'
# The Pokemon France withdrawal as published, before the 28 October 2026
# withdrawal (test/source_rights_fps478_test.py) replaced 14 more packs.
RESULT='cb59a78472a9ce5c5fc6925db7119649e76b3220'
REMOVED={'533635c085f971e8a5e3e0f854348c69','60d89cf805c614b7c3b08e4b53ee5b48'}
def original(path,commit=BASE):return subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)
def digest(data):return hashlib.sha256(data).hexdigest()
class RightsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.old=json.loads(gzip.decompress(original('packages/neo_cheat_catalog/ios/Resources/manifest.json.gz')))
  cls.new=json.loads(gzip.decompress(original('packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',RESULT)))
  cls.current=json.loads(gzip.decompress((ROOT/'native/cheats/catalogue/manifest.json.gz').read_bytes()))
  cls.receipt=json.loads((ROOT/'docs/evidence/source-rights-withdrawal.json').read_text())
 def test_publication_counts_and_withheld_credit(self):
  self.assertEqual(self.new['totals']['sources'],50);self.assertEqual(self.new['totals']['programs'],2395541)
  self.assertEqual(self.new['excluded_sources'][-1]['id'],'pokemonfrance')
  for m in (self.new,self.current):
   self.assertNotIn('pokemonfrance',{s['id'] for s in m['sources']})
   self.assertTrue(next(s for s in m['excluded_sources'] if s['id']=='pokemonfrance')['url'])
  # The app bundles the origin publication (v2) built from the hosted index.
  self.assertEqual((ROOT/'native/cheats/catalogue/v2/manifest.json.gz').read_bytes(),(ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes())
 def test_every_unrelated_chunk_is_unchanged(self):
  before={g['id']:g for g in self.old['games']};after={g['id']:g for g in self.new['games']}
  self.assertEqual(before.keys()-after.keys(),REMOVED)
  for gid,game in after.items():self.assertEqual({k:v for k,v in game.items() if k!='pack_id'},{k:v for k,v in before[gid].items() if k!='pack_id'})
 def test_replacement_packs_preserve_all_other_bytes(self):
  oldpacks={p['path']:p for p in self.old['packs']};newpacks={p['path']:p for p in self.new['packs']}
  self.assertEqual(len(set(oldpacks)&set(newpacks)),872)
  for change in self.receipt['replacedPacks']:
   before=json.loads(gzip.decompress(original('native/cheats/catalogue/'+change['old'])))
   data=original('native/cheats/catalogue/'+change['new'],RESULT);meta=newpacks[change['new']]
   self.assertEqual(digest(data),meta['sha256']);self.assertEqual(len(data),meta['size'])
   after=json.loads(gzip.decompress(data));self.assertEqual(after['files'],[f for f in before['files'] if f['game_id'] not in REMOVED])
   for f in after['files']:
    for c in json.loads(base64.b64decode(f['data']))['cheats']:
     self.assertFalse(any(p.get('source_id')=='pokemonfrance' or p.get('import_source_id')=='pokemonfrance' for p in c.get('provenance',[])))
 def test_future_input_exclusion_and_updated_hashes(self):
  data=(ROOT/'tools/cheats/unified-curated.json').read_bytes();curated=json.loads(data)
  self.assertFalse(any(g.get('source_id')=='pokemonfrance' for g in curated['games']))
  lock=json.loads((ROOT/'tools/cheats/unified-sources.json').read_text())
  for s in lock['sources']:
   if s['id']=='pokemonfrance':self.assertFalse(s['publication']['enabled'])
   if s.get('local_path')=='unified-curated.json':self.assertEqual(s['sha256'],digest(data))
 def test_overlay_layouts_and_image_lists_unchanged(self):
  before=json.loads(original('assets/data/libretro_skin_overlays.json'));after=json.loads((ROOT/'assets/data/libretro_skin_overlays.json').read_text())
  self.assertEqual(len(before['entries']),len(after['entries']))
  for a,b in zip(before['entries'],after['entries']):
   for k,v in a.items():self.assertEqual(b[k],v,(a['path'],k))
 def test_original_overlay_creators_and_notices(self):
  m=json.loads((ROOT/'assets/data/libretro_skin_overlays.json').read_text());entries={e['path']:e for e in m['entries']}
  self.assertEqual(entries['gamepads/rgpad/rgpad_modern.cfg']['author'],'DJM')
  self.assertEqual(entries['gamepads/quadpad/quadpad.cfg']['author'],'DJM')
  self.assertEqual(entries['misc/gb-portrait/gb.cfg']['author'],'ZilogZ92')
  self.assertIn('Piixel',entries['gamepads/Piixel-Gamepads/Retropad/Piixel Retropad.cfg']['author'])
  for e in m['entries']:
   self.assertTrue(e['notice_files'],e['path'])
   if e['source']=='libretro-overlays':self.assertIn('COPYING',e['notice_files'])
if __name__=='__main__':unittest.main()
