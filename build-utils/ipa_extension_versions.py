"""Align versions for the exact extension set declared by the packaged runtime."""
import json,plistlib
from validate_single_ipa_distribution import EXPECTED_EXTENSIONS

def validate_extension_versions(archive,root,build):
    host=plistlib.loads(archive.read(root+'Info.plist'))
    assert str(host['CFBundleVersion'])==str(build)
    expected=set(EXPECTED_EXTENSIONS)
    identity=root+'MeloNX-native-identity.json'
    if identity in archive.namelist():
        expected.add('MeloNXJITHelper.appex')
        if 'ramDonorSource' in json.loads(archive.read(identity)):
            expected.add('MeloNXRamDonor.appex')
    extensions=[n for n in archive.namelist() if n.startswith(root+'PlugIns/') and n.endswith('.appex/Info.plist')]
    assert set(extensions)=={root+'PlugIns/'+name+'/Info.plist' for name in expected}
    assert len(extensions)==len(expected)
    for path in extensions:
        info=plistlib.loads(archive.read(path))
        assert info['CFBundleVersion']==host['CFBundleVersion'],path
        assert info['CFBundleShortVersionString']==host['CFBundleShortVersionString'],path
    return len(extensions)
