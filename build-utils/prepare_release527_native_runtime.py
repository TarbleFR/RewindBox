#!/usr/bin/env python3
"""Reuse native bootstrap assets from the last published RewindBox IPA (527).

The complete baseline ZIP and selected signed Cores are authenticated before
extraction. RPCS3 and ARMSX2 are then replaced by their independently pinned
artifacts; all host plugins, Dart code and StikJIT are built from source.
"""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import shutil
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DOLPHIN_SHA='eec54ff2a16f4878e070ce2ae96c7e5dfc25e5e8246448ffe8b14bb0a42392b4'
RPCS3_SHA='bc2e292488c1df849eed32dbed9e662c6f200e6743f4b8a501b08c82c088db04'
ARMSX2_SHA='cdbcef7f13b693374b4eaebdc6d2ffd3e5271cd6924961b77204fc89fe6ffb9e'
BASELINE_IPA_SHA='884a44dea6e627fc9cd774d296dc2abf1ef683ca01572651d5c0e3425bd9756e'
BASELINE_RELEASE='0.0.9'
BASELINE_BUILD='527'


def sha(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def demand(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--build-number', required=True)
    args=parser.parse_args()

    donor=args.artifact.resolve()
    with tempfile.TemporaryDirectory(prefix='neostation-fast-native-') as temp:
        work=Path(temp)
        ipa=donor
        demand(ipa.is_file(), 'Baseline IPA missing')
        demand(sha(ipa)==BASELINE_IPA_SHA, 'Published Build 527 IPA hash mismatch')

        with zipfile.ZipFile(ipa) as archive:
            demand(archive.testzip() is None, 'Donor IPA ZIP is corrupt')
            names=archive.namelist()
            demand(not any('kartpad' in n.lower() or 'dusklight' in n.lower() for n in names),
                   'Retired component in baseline IPA')
            demand(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names),
                   'Unsafe baseline member path')
            apps=sorted({
                name.split('/')[1]
                for name in names
                if name.startswith('Payload/')
                and len(name.split('/'))>2
                and name.split('/')[1].endswith('.app')
            })
            demand(len(apps)==1, f'Expected one donor application, found {apps}')
            archive.extractall(work/'ipa')

        app=work/'ipa'/'Payload'/apps[0]
        app_info=plistlib.loads((app/'Info.plist').read_bytes())
        demand(app_info['CFBundleVersion']==BASELINE_BUILD, 'Wrong baseline build')
        dolphin=app/'Frameworks/DolphinCore.framework'
        rpcs3=app/'Frameworks/libRPCS3Core.dylib'
        armsx2=app/'Frameworks/ARMSX2Core.framework'
        dolphin_bridge=app/'Frameworks/dolphin_internal_bridge.framework'

        for required in (
            dolphin/'DolphinCore', rpcs3,
            armsx2/'ARMSX2Core', app/'cacert.pem',
        ):
            demand(required.is_file(), f'Missing donor runtime: {required}')
        # The donor subset never carries the removed Dusklight Core.
        for retired in (app/'Frameworks/DusklightCore.framework',
                        app/'Dusklight-native-identity.json', app/'Dusklight-Licenses'):
            demand(not retired.exists(), f'Removed Dusklight runtime in the donor: {retired}')

        demand(sha(dolphin/'DolphinCore')==DOLPHIN_SHA, 'DolphinCore donor hash mismatch')
        demand(sha(rpcs3)==RPCS3_SHA, 'RPCS3Core donor hash mismatch')
        demand(sha(armsx2/'ARMSX2Core')==ARMSX2_SHA, 'ARMSX2Core donor hash mismatch')
        dolphin_dst=ROOT/'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'
        copytree(dolphin, dolphin_dst)
        # zipfile extraction does not reliably restore POSIX executable bits.
        # Restore the verified donor Mach-O mode before Xcode/IPA packaging.
        (dolphin_dst/'DolphinCore').chmod(0o755)
        info_path=dolphin_dst/'Info.plist'
        if info_path.is_file():
            info=plistlib.loads(info_path.read_bytes())
            info['CFBundleVersion']=str(args.build_number)
            info_path.write_bytes(
                plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False)
            )

        core_dst=ROOT/'packages/rpcs3_internal_bridge/ios/Frameworks/libRPCS3Core.dylib'
        core_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rpcs3, core_dst)
        core_dst.chmod(0o755)

        armsx2_root=ROOT/'dist/armsx2'
        if armsx2_root.exists():
            shutil.rmtree(armsx2_root)
        copytree(armsx2, armsx2_root/'ARMSX2Core.framework')
        (armsx2_root/'ARMSX2Core.framework/ARMSX2Core').chmod(0o755)
        (armsx2_root/'identity.json').write_text(json.dumps({
            'sourceRelease':BASELINE_RELEASE,
            'baselineBuild':BASELINE_BUILD,
            'baselineIpaSha256':BASELINE_IPA_SHA,
            'architectures':['arm64'],
            'sha256':ARMSX2_SHA,
        }, indent=2)+'\n')

        # A Dusklight tree left by an older build step is never packaged.
        retired_dusklight=ROOT/'dist/dusklight'
        if retired_dusklight.exists():
            shutil.rmtree(retired_dusklight)

        sys_src=app/'Sys'
        sys_dst=ROOT/'ios/Runner/Sys'
        demand(sys_src.is_dir(), 'Donor Dolphin Sys resources missing')
        copytree(sys_src, sys_dst)
        shutil.copy2(app/'cacert.pem', ROOT/'ios/Runner/cacert.pem')

        touch_dst=ROOT/'packages/dolphin_internal_bridge/ios/TouchResources'
        if touch_dst.exists():
            shutil.rmtree(touch_dst)
        touch_dst.mkdir(parents=True)
        demand(dolphin_bridge.is_dir(), 'Donor Dolphin bridge framework missing')
        copied=0
        for child in dolphin_bridge.iterdir():
            if child.suffix=='.png' or child.name.endswith('.nib'):
                target=touch_dst/child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copy2(child, target)
                copied+=1
        demand(copied>0, 'No Dolphin touchscreen resources found in donor framework')

        identity=ROOT/'build/fast-native/identity.json'
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text(json.dumps({
            'donorIpa':ipa.name,
            'baselineBuild':BASELINE_BUILD,
            'baselineRelease':BASELINE_RELEASE,
            'baselineIpaSha256':BASELINE_IPA_SHA,
            'dolphinCoreSha256':sha(dolphin/'DolphinCore'),
            'armsx2CoreSha256':sha(armsx2/'ARMSX2Core'),
            'rpcs3CoreSha256':sha(rpcs3),
            'touchResourcesCopied':copied,
        }, indent=2)+'\n')
        print(identity.read_text())


if __name__=='__main__':
    main()
