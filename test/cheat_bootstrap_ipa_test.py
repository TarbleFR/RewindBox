#!/usr/bin/env python3
import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bootstrap_ipa',ROOT/'build-utils/validate_cheat_bootstrap_ipa.py');validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
class PackagedBootstrap(unittest.TestCase):
 def test_verified_data_is_required_inside_the_ipa(self):
  with tempfile.TemporaryDirectory() as work:
   valid=Path(work)/'test.ipa';missing=Path(work)/'missing.ipa';bad=Path(work)/'bad.ipa';prefix='Payload/Runner.app/NeoStationCheats.bundle/'
   with zipfile.ZipFile(valid,'w',zipfile.ZIP_DEFLATED) as z:
    for p in validator.DATA.iterdir():z.write(p,prefix+p.name)
   report=validator.validate(valid);self.assertEqual(report['result'],'passed');self.assertGreater(report['resources'],30)
   with zipfile.ZipFile(missing,'w') as z:z.writestr('Payload/Runner.app/placeholder','')
   with self.assertRaisesRegex(ValueError,'Missing'):validator.validate(missing)
   with zipfile.ZipFile(valid) as old,zipfile.ZipFile(bad,'w',zipfile.ZIP_DEFLATED) as z:
    for name in old.namelist():z.writestr(name,b'corrupted' if name.endswith('/openemu.xml') else old.read(name))
   with self.assertRaisesRegex(ValueError,'Packaged cheat data changed'):validator.validate(bad)
if __name__=='__main__':unittest.main()
