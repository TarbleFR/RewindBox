#!/usr/bin/env python3
"""Verify the actual IPA contains every reviewed cheat index, code and licence byte."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'packages/libretro_internal_bridge/ios/Resources/Cheats'
def validate(path):
 expected=json.loads((DATA/'manifest.json').read_bytes())
 with zipfile.ZipFile(path) as archive:
  matches=[n for n in archive.namelist() if n.startswith('Payload/') and n.endswith('/NeoStationCheats.bundle/manifest.json')]
  if len(matches)!=1:raise ValueError('Missing or ambiguous cheat bootstrap resource bundle')
  prefix=matches[0].removesuffix('manifest.json')
  manifest=json.loads(archive.read(matches[0]))
  if manifest!=expected:raise ValueError('Packaged cheat manifest differs from reviewed sources')
  size=0
  for name,digest in expected['outputs'].items():
   data=archive.read(prefix+name);size+=len(data)
   if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Packaged cheat data changed: '+name)
 return {'result':'passed','bundle':prefix,'resources':len(expected['outputs']),'bytes':size,
  'sourceRevisions':{'libretro':expected['libretroRevision'],'openemu-community':expected['openemuRevision']},
  'ipaSHA256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'physicalDeviceValidated':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('ipa',type=Path);p.add_argument('--report',type=Path);args=p.parse_args();report=validate(args.ipa)
 if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
