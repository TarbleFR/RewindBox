#!/usr/bin/env python3
"""Verify the actual packaged MeloNX engine, private closure and source notices."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/dolphin_internal_bridge/ci'))
from verify_ipa import macho

def validate(ipa):
 with zipfile.ZipFile(ipa) as z:
  assert z.testzip() is None
  roots={n.split('/')[1] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))>2 and n.split('/')[1].endswith('.app')}
  assert len(roots)==1;root='Payload/'+roots.pop()+'/'
  receipt=json.loads(z.read(root+'MeloNX-native-identity.json'))
  core=macho(z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore'))
  assert core['platform']==2
  required={'_'+name for name in receipt['sourceCoreIdentity']['exports']}
  assert required.issubset(set(core['definedSymbols'])),required-set(core['definedSymbols'])
  assert receipt['gameplayTested'] is False and receipt['neoSwapLiveLoanConnected'] is False
  framework_names=set(receipt['frameworks'])
  assert framework_names=={'MeloNXCore','MeloNXMoltenVK','MeloNXSDL3','MeloNXAvCodec','MeloNXAvUtil','MeloNXJitSupport'}
  for name in framework_names:
   binary=z.read(root+f'Frameworks/{name}.framework/{name}')
   image=macho(binary);assert image['platform']==2 and image['fileType']==6
   for dep in image['dependencies']:
    value=dep['path']
    if value.startswith('@rpath/'):
     assert root+'Frameworks/'+value.removeprefix('@rpath/') in z.namelist(),value
    else:assert value.startswith(('/usr/lib/','/System/Library/Frameworks/')),value
  bridge=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
  assert b'MeloNXInternalBridgePlugin' in bridge and b'neostation/melonx_internal' in bridge
  helper=plistlib.loads(z.read(root+'PlugIns/MeloNXJITHelper.appex/Info.plist'))
  host=plistlib.loads(z.read(root+'Info.plist'))
  assert helper['CFBundleVersion']==host['CFBundleVersion']
  assert helper['CFBundleIdentifier']==host['CFBundleIdentifier']+'.melonxjithelper'
  for component in receipt['sourceDependenciesIdentity']['sourceArchives']:assert len(component['sha256'])==64
  notices=json.loads(z.read(root+'Legal/MeloNX/source-notices.json'));assert notices
  for name,entry in notices.items():assert hashlib.sha256(z.read(root+'Legal/MeloNX/'+name)).hexdigest()==entry['sha256']
  assert not any('BreakpointJIT.framework/' in n for n in z.namelist())
  report={'result':'passed','build':host['CFBundleVersion'],'engineExportsVerified':len(required),'privateFrameworks':sorted(framework_names),
          'nativeSourceNoticesVerified':len(notices),'registeredFlutterBridge':True,'gameplayTested':False,'deviceInstallationTested':False}
  return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('ipa',type=Path);parser.add_argument('--report',type=Path);a=parser.parse_args()
 report=validate(a.ipa);print(json.dumps(report,indent=2))
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
