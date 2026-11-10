#!/usr/bin/env python3
"""Bind the actual signed host to the tested Hogwarts activation source."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='MeloNX-hogwarts603-policy.json'
PATHS=['lib/widgets/melonx_hogwarts_graphics_options.dart',
       'lib/widgets/melonx_internal_playlist_actions.dart','lib/l10n/melonx_library_locale.dart',
       'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
       'packages/melonx_internal_bridge/ios/Classes/MeloNXHogwartsGraphics.swift',
       'lib/services/melonx_unreal_profiles.dart', 'lib/widgets/melonx_unreal_profile_dialog.dart',
       'packages/melonx_jit_helper/ios/Resources/melonx-universal.js']

def expected():
    checks=json.loads((ROOT/'build/delivery/hogwarts603-policy-checks.json').read_text())
    flutter=json.loads((ROOT/'build/delivery/hogwarts603-flutter-checks.json').read_text())
    assert checks['result']=='passed' and checks['swiftExecuted'] is True and checks['swiftChecks']>=3340
    assert flutter['result']=='passed' and flutter['tests']==23
    return dict(build=603,titleId='0100F7E00C70E000',hostSource=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                defaultOptions=dict(occlusionQuerySync=True,relaxQueryFlushing=True),explicitOptOutRespected=True,batchingRequiresSync=True,
                nativePreflightIdentityRequired=True,coreContentIdentityCheckedAgain=True,shaderChoicesPreserved=True,
                sourceSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in PATHS},swiftChecks=checks['swiftChecks'],flutterTests=23,checksReexecuted=False,helperProof=json.loads((ROOT/'build/delivery/melonx-jit-helper-init.json').read_text()),
                deviceGameplayTested=False,literalLoadFixIncluded=True,hogwartsCrashCauseProven=False,gpuStartupDelayFixed=False,coreRebuiltInSeparateProducer=True,unrealProfilesDefault="off",unrealCVarsVerified=False,progressiveJitMiB=[1024,960,896,832,768,704,640,576,512],blackTextureFixOnDeviceProven=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    receipt=expected()
    if a.embed:
        info=plistlib.loads((a.embed/'Info.plist').read_bytes());assert str(info['CFBundleVersion'])=='603'
        (a.embed/IDENTITY).write_text(json.dumps(receipt,indent=2)+'\n');return
    assert a.ipa and a.report
    with zipfile.ZipFile(a.ipa)as z:
        root='Payload/NeoStation.app/'
        assert z.testzip()is None and json.loads(z.read(root+IDENTITY))==receipt
        info=plistlib.loads(z.read(root+'Info.plist'));assert str(info['CFBundleVersion'])=='603'
        assert z.read(root+'PlugIns/MeloNXJITHelper.appex/melonx-universal.js') == (ROOT/'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(), 'Packaged sized-JIT helper differs from tested source'
        host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in [b'Hogwarts GPU policy:',b'occlusionQuerySync',b'relaxQueryFlushing',b'original core SHA256 prefix',b'inspectUnreal']:
            assert marker in host,'Compiled host marker missing: '+repr(marker)
    report=dict(result='passed',build=603,ipaSHA256=hashlib.sha256(a.ipa.read_bytes()).hexdigest(),policy=receipt,compiledHostMarkers=True,physicalDeviceTested=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
