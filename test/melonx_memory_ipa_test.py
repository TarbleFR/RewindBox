"""Exercise all three packagers with the new donor and malformed variants."""
import copy,json,plistlib,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'test'))
from single_ipa_distribution_test import APP,complete_dolphin_packaging_members,packaging_image,validator,dolphin_validator,rpcs3_validator
m=complete_dolphin_packaging_members();m[APP+'MeloNX-native-identity.json']=b'{"ramDonorSource":{}}'
host=plistlib.loads(m[APP+'Info.plist'])
for name,suffix,principal,marker,point in [
 ('MeloNXJITHelper','.melonxjithelper','MeloNXJITRequestHandler','NeoStationMeloNXJITHelper','com.apple.share-services'),
 ('MeloNXRamDonor','.melonxramdonor','MLXRamDonorHandler','RewindBoxMeloNXRamDonor','com.apple.ar.viewer')]:
 info=dict(CFBundleExecutable=name,CFBundleIdentifier=host['CFBundleIdentifier']+suffix,CFBundlePackageType='XPC!',
  CFBundleVersion=host['CFBundleVersion'],CFBundleShortVersionString=host['CFBundleShortVersionString'],
  NSExtension={'NSExtensionPointIdentifier':point,'NSExtensionPrincipalClass':principal},**{marker:'1'})
 if name=='MeloNXRamDonor':
  info.update(MinimumOSVersion='18.0',XPCService={'ServiceType':'Application','_MultipleInstances':True,'_ProcessType':'App'})
  info['NSExtension'].update(NSExtensionAttributes={'NSExtensionActivationRule':'FALSEPREDICATE'},NSExtensionContextClass='NSExtensionContext',NSExtensionContextHostClass='NSExtensionContext')
 prefix=APP+'PlugIns/'+name+'.appex/';m[prefix+'Info.plist']=plistlib.dumps(info);m[prefix+name]=packaging_image({})
for component in ('MeloNXCore','MeloNXMoltenVK','MeloNXSDL3','MeloNXAvCodec','MeloNXAvUtil','MeloNXJitSupport'):
 m[APP+f'Frameworks/{component}.framework/{component}']=packaging_image({},filetype=6)
def run(m,accepted):
 for check in [validator.validate,dolphin_validator.validate,None]:
  with tempfile.TemporaryDirectory() as d:
   w=Path(d);ipa=w/'test.ipa'
   with zipfile.ZipFile(ipa,'w') as z:
    for k,v in m.items():
     item=zipfile.ZipInfo(k);item.external_attr=(0o100755 if v[:4]==bytes.fromhex('cffaedfe') else 0o100644)<<16
     z.writestr(item,v)
   try:
    if check:check(ipa)
    else:
     with zipfile.ZipFile(ipa) as z:z.extractall(w)
     rpcs3_validator.validate_helper_bundles(w/APP,host)
   except (ValueError,RuntimeError,AssertionError) as e:
    if accepted:raise
   else:assert accepted,'Malformed MeloNX donor accepted'
run(m,True);cases=3
prefix=APP+'PlugIns/MeloNXRamDonor.appex/'
for change in ['missing','version','principal','point','service','context','entitlements','identity']:
 bad=copy.deepcopy(m);info=plistlib.loads(bad[prefix+'Info.plist'])
 if change=='missing':bad.pop(prefix+'MeloNXRamDonor')
 elif change=='version':info['CFBundleVersion']='999'
 elif change=='principal':info['NSExtension']['NSExtensionPrincipalClass']='Wrong'
 elif change=='point':info['NSExtension']['NSExtensionPointIdentifier']='com.apple.share-services'
 elif change=='service':info['XPCService']['_MultipleInstances']=False
 elif change=='context':info['NSExtension']['NSExtensionContextClass']='Wrong'
 elif change=='entitlements':bad[prefix+'MeloNXRamDonor']=packaging_image({'get-task-allow':True})
 elif change=='identity':bad[APP+'MeloNX-native-identity.json']=b'{}'
 bad[prefix+'Info.plist']=plistlib.dumps(info);run(bad,False);cases += 3
print('PASS',cases,'MeloNX donor packaging cases across distribution, Dolphin packaging and RPCS3 validators; synthetic Mach-O only.')
sys.path.insert(0,str(ROOT/'build-utils'))
from ipa_extension_versions import validate_extension_versions
for variant in ['current','legacy','missing','extra','version','undeclared']:
 members=copy.deepcopy(m);accepted=variant in {'current','legacy'}
 if variant=='legacy':
  members={k:v for k,v in members.items() if not k.startswith(prefix)}
  members[APP+'MeloNX-native-identity.json']=b'{}'
 elif variant=='missing':members.pop(prefix+'Info.plist')
 elif variant=='extra':members[APP+'PlugIns/Unknown.appex/Info.plist']=members[prefix+'Info.plist']
 elif variant=='version':
  info=plistlib.loads(members[prefix+'Info.plist']);info['CFBundleVersion']='999';members[prefix+'Info.plist']=plistlib.dumps(info)
 elif variant=='undeclared':members[APP+'MeloNX-native-identity.json']=b'{}'
 with tempfile.TemporaryDirectory() as d:
  path=Path(d)/'test.ipa'
  with zipfile.ZipFile(path,'w') as z:
   for k,v in members.items():z.writestr(k,v)
  try:
   with zipfile.ZipFile(path) as z:count=validate_extension_versions(z,APP,host['CFBundleVersion'])
  except AssertionError:
   assert not accepted,variant
  else:assert accepted and count==(6 if variant=='legacy' else 7),variant
print('PASS 6 exact extension-set/version cases shared by all three UI validators.')
