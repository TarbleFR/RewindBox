#!/usr/bin/env python3
"""Materialize and embed only the verified source-built MeloNX runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'dist/melonx'
DEPS = ROOT / 'dist/melonx-native'
FRAMEWORKS = ROOT / 'packages/melonx_internal_bridge/ios/Frameworks'
NAMES = {'MeloNXMoltenVK','MeloNXSDL3','MeloNXAvUtil','MeloNXAvCodec','MeloNXJitSupport'}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def run(*args): return subprocess.check_output(list(map(str,args)),stderr=subprocess.STDOUT,text=True)

def materialize():
    identity = read(CORE/'ios-arm64/identity.json')
    pin = read(ROOT/'build-utils/melonx/source.json')
    assert identity['source'] == pin and identity['runtimeIdentifier'] == 'ios-arm64'
    assert identity['embeddedSessionDeviceVerified'] is False
    for name, digest in identity['adaptations'].items():
        assert sha(ROOT/name) == digest, 'Engine adaptation mismatch: '+name
    binary = CORE/'ios-arm64/Ryujinx.Library.dylib'
    assert sha(binary) == identity['sha256']
    assert 'platform IOS\n' in run('xcrun','vtool','-show-build',binary)
    dependencies = read(DEPS/'identity.json')
    assert dependencies['pins'] == read(ROOT/'build-utils/melonx/native-dependencies.json')
    device = [entry for entry in dependencies['binaries'] if entry['path'].startswith('ios/')]
    assert {Path(entry['path']).name for entry in device} == NAMES
    for entry in dependencies['binaries']:
        assert sha(DEPS/entry['path']) == entry['sha256'], entry['path']
    for entry in dependencies['sourceArchives']:
        assert sha(DEPS/entry['path']) == entry['sha256'], entry['path']
    FRAMEWORKS.mkdir(parents=True,exist_ok=True)
    for name in NAMES:
        shutil.copytree(DEPS/'ios'/f'{name}.framework',FRAMEWORKS/f'{name}.framework',dirs_exist_ok=True)
    directory=FRAMEWORKS/'MeloNXCore.framework';directory.mkdir(exist_ok=True)
    output=directory/'MeloNXCore';shutil.copy2(binary,output);output.chmod(0o755)
    run('install_name_tool','-id','@rpath/MeloNXCore.framework/MeloNXCore',output)
    plist={'CFBundleExecutable':'MeloNXCore','CFBundleName':'MeloNXCore',
           'CFBundleIdentifier':'com.neogamelab.neostation.melonx.core','CFBundlePackageType':'FMWK',
           'CFBundleVersion':os.environ.get('BUILD_NUMBER','506'),'CFBundleShortVersionString':'1.0',
           'MinimumOSVersion':'18.0','CFBundleSupportedPlatforms':['iPhoneOS'],'UIDeviceFamily':[1,2]}
    (directory/'Info.plist').write_bytes(plistlib.dumps(plist))
    # Every dependency is either an exact Apple SDK install name already audited
    # by the dependency lane or a private framework. No other emulator is used.
    for name in NAMES|{'MeloNXCore'}:
        executable=FRAMEWORKS/f'{name}.framework'/name
        assert 'platform IOS\n' in run('xcrun','vtool','-show-build',executable)
        for line in run('otool','-L',executable).splitlines()[1:]:
            dep=line.strip().split(' (',1)[0]
            assert dep.startswith(('/usr/lib/','/System/Library/Frameworks/','@rpath/')),dep
            if dep.startswith('@rpath/'):
                assert (FRAMEWORKS/dep.removeprefix('@rpath/')).is_file(),dep
    receipt={'sourceCoreIdentity':identity,'sourceDependenciesIdentity':dependencies,
             'packagedCoreSha256':sha(output),'frameworks':{name:sha(FRAMEWORKS/f'{name}.framework'/name) for name in sorted(NAMES|{'MeloNXCore'})},
             'gameplayTested':False,'physicalDeviceTested':False,'neoSwapLiveLoanConnected':False,
             'sources':{'engine':pin,'hostCommit':os.environ.get('GITHUB_SHA'),'repository':'https://github.com/TarbleFR/RewindBox'}}
    (CORE/'packaging-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Verified and materialized six private source-built MeloNX frameworks.')

def embed(app):
    receipt=read(CORE/'packaging-identity.json')
    for name,digest in receipt['frameworks'].items():
        source=FRAMEWORKS/f'{name}.framework'; assert sha(source/name)==digest
        target=app/'Frameworks'/source.name
        if target.exists():shutil.rmtree(target)
        shutil.copytree(source,target)
    (app/'MeloNX-native-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
    legal=app/'Legal/MeloNX';legal.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/'assets/legal/melonx',legal,dirs_exist_ok=True)
    shutil.copy2(CORE/'MeloNX-LICENSE.txt',legal/'Engine-LICENSE.txt')
    # Copy licenses verbatim from the same source archives used for compilation.
    notices={}
    for archive in sorted((DEPS/'sources').glob('*.tar.gz')):
        with tarfile.open(archive) as source:
            for member in source:
                basename=Path(member.name).name.upper()
                if not member.isfile() or not (basename.startswith(('LICENSE','COPYING','NOTICE')) or basename=='AUTHORS.TXT') or member.size>2*1024*1024:continue
                data=source.extractfile(member).read()
                name=archive.name.removesuffix('.tar.gz')+'/'+member.name
                target=legal/'NativeDependencies'/name
                # Never extract archive-controlled paths; create a bounded flat filename.
                target=legal/'NativeDependencies'/(hashlib.sha256(name.encode()).hexdigest()[:16]+'-'+Path(member.name).name)
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                notices[str(target.relative_to(legal))]={'sourceArchive':archive.name,'sourcePath':member.name,'sha256':hashlib.sha256(data).hexdigest()}
    assert notices,'Source-built native dependency licenses missing'
    (legal/'source-notices.json').write_text(json.dumps(notices,indent=2)+'\n')
    print('Embedded verified MeloNX frameworks, source identities and unmodified notices.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--embed',type=Path);args=parser.parse_args()
    embed(args.embed) if args.embed else materialize()
