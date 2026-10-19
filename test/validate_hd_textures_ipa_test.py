"""The Build 486 IPA gate accepts the real packaged catalogue only and names every refusal."""
from pathlib import Path
import json,plistlib,subprocess,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build-utils'))
import validate_hd_textures_ipa as gate  # noqa: E402

INDEX=(ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
LABELS=(ROOT/'packages/neo_texture_catalog/ios/Resources/labels.json').read_bytes()
FRAMEWORK=b' '.join(gate.FRAMEWORK_MARKERS)


def build_ipa(path,build=486,index=INDEX,labels=LABELS,drop=(None,b''),extra=None,expected=None):
    # drop=(binary, marker): that marker is left out of that one binary.
    def binary(name,content):return content.replace(drop[1],b'') if drop[0]==name else content
    root='Payload/NeoStation.app/'
    bundle=root+'Frameworks/neo_texture_catalog.framework/NeoTextureCatalog.bundle/'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr(root+'Info.plist',plistlib.dumps({'CFBundleVersion':str(build)}))
        z.writestr(root+'Frameworks/neo_texture_catalog.framework/neo_texture_catalog',binary('neo_texture_catalog',FRAMEWORK))
        z.writestr(bundle+'Info.plist',plistlib.dumps({'CFBundleIdentifier':'org.cocoapods.NeoTextureCatalog'}))
        z.writestr(bundle+'manifest.json.gz',index)
        z.writestr(bundle+'labels.json',labels)
        for name,markers in gate.BRIDGE_MARKERS.items():
            z.writestr(root+f'Frameworks/{name}.framework/{name}',binary(name,b' '.join(markers)))
        z.writestr(root+'Frameworks/App.framework/App',binary('App',b'...neostation/texture_catalog...'))
        if extra:z.writestr(bundle+extra,b'\x89PNG')


def refused(message,**kwargs):
    with tempfile.TemporaryDirectory() as folder:
        ipa=Path(folder)/'candidate.ipa';build_ipa(ipa,**kwargs)
        try:gate.validate(ipa,kwargs.get('expected',486))
        except ValueError as error:
            assert message in str(error),(message,str(error));return
        raise AssertionError('accepted: '+message)


with tempfile.TemporaryDirectory() as folder:
    ipa=Path(folder)/'candidate.ipa';build_ipa(ipa)
    report=Path(folder)/'report.json'
    subprocess.run([sys.executable,str(ROOT/'build-utils/validate_hd_textures_ipa.py'),str(ipa),'--build-number','486',
                    '--report',str(report)],check=True,capture_output=True)
    result=json.loads(report.read_text())
    assert result['result']=='passed' and result['packs']>0 and result['packsBundled'] is False
    assert result['physicalDeviceValidated'] is False and set(result['frameworksSHA256'])=={'neo_texture_catalog',*gate.BRIDGE_MARKERS}
    assert sum(result['packsPerSystem'].values())>=result['packs']
refused('Wrong IPA build',build=487)
refused('starts with Build 486',build=485,expected=485)
tampered=bytearray(INDEX);tampered[-1]^=1
refused('differs from the hosted and tested index',index=bytes(tampered))
refused('labels differ',labels=LABELS.replace(b'"en"',b'"EN"',1))
refused('Unexpected files',extra='pack/tex1_256x256_0123456789abcdef_14.png')
refused('neo_texture_catalog is missing textureViewControllerWithOptions:',drop=('neo_texture_catalog',b'textureViewControllerWithOptions:'))
refused('armsx2_internal_bridge is missing initWithExpandedFolder',drop=('armsx2_internal_bridge',b'initWithExpandedFolder:sourceName:dataPath:game:'))
refused('libretro_internal_bridge is missing libretro-menu-hd-textures',drop=('libretro_internal_bridge',b'libretro-menu-hd-textures'))
refused('dolphin_internal_bridge is missing NeoTextureHDPage',drop=('dolphin_internal_bridge',b'NeoTextureHDPage'))
refused('Flutter channel is missing',drop=('App',b'neostation/texture_catalog'))
print('PASS HD texture IPA gate: real index/labels/framework/channel/bridges accepted; wrong build, earlier build, tampered '
      'index, changed labels, a bundled texture file and each missing entry point refused (10 refusals)')
