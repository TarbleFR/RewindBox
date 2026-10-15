#!/usr/bin/env python3
"""Reproduce Build 463 resource rejection; test an existing install on the candidate.

Runs the exact original DualShocked archive, the old renderer and the current
session/menu/renderer on Simulator. No commercial ROM or physical-device claim.
"""
import argparse
import json
import plistlib
import shutil
import tempfile
from pathlib import Path
import libretro_simulator_probe as probe
import libretro_skin_press_probe as skins


def legacy_validation(sources, fixture, work, evidence):
    app = work / 'legacy' / 'Probe.app'
    app.mkdir(parents=True)
    shutil.copytree(fixture, app / 'original-dualshocked')
    (app / 'expect.json').write_text(json.dumps({'valid':False}))
    classes = sources / 'Classes'
    names = ('LibretroGeometry.m','LibretroInputMap.m','LibretroSkin.m',
             'LibretroSkinLayout.m','LibretroSkinButtonCrop.m','LibretroSkinPressure.m','LibretroSkinRenderer.m')
    command = ['xcrun','--sdk','iphonesimulator','clang','-target',probe.TARGET,
               '-isysroot',probe.sdk_path(),'-fobjc-arc','-O1','-Wno-deprecated-declarations',
               '-I',str(classes),'-I',str(sources/'ThirdParty/include/libretro'),
               *(str(classes / name) for name in names),
               str(probe.ROOT / 'test/libretro_simulator/skin_resource_legacy.m'),
               '-framework','UIKit','-framework','Foundation','-framework','CoreGraphics',
               '-framework','ImageIO','-framework','QuartzCore','-o',str(app/'Probe')]
    probe.run(command)
    with (app / 'Info.plist').open('wb') as output:
        plistlib.dump({'CFBundleIdentifier':probe.BUNDLE_ID,'CFBundleExecutable':'Probe',
                      'CFBundleName':'Skin Resource Regression','CFBundlePackageType':'APPL',
                      'CFBundleVersion':'1','CFBundleShortVersionString':'1.0',
                      'LSRequiresIPhoneOS':True,'MinimumOSVersion':'17.4',
                      'UIDeviceFamily':[1,2],'UILaunchScreen':{},
                      'CFBundleSupportedPlatforms':['iPhoneSimulator']},output)
    probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
    evidence.mkdir(parents=True,exist_ok=True)
    outcome = probe.run_in_simulator(app,evidence,90)
    report = json.loads((evidence/'probe.json').read_text())
    result = report['results'][0]
    assert outcome['finished'] and result['valid'] is False
    assert all(c['passed'] for c in result['checks']), result
    print('Reproduced on exact Build 463: original DualShocked parsed, both orientations present, resource validation refuses it.',flush=True)
    return {'outcome':outcome,'result':result}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('cores','inputs','evidence','label','legacy-sources'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    args.sources=None;args.only=[];args.lot1=False;args.lot2=False;args.official_shaders=False
    probe.REAL_CORES=()
    probe.SCENARIOS=[
        {'name':'skin-upgrade-existing-install','console':'psx','core':'neotest',
         'content':'content/Shader Pattern.ntc','skinLoading':'upgrade','expect':'run'},
        {'name':'skin-relaunch-saved-selection','console':'psx','core':'neotest',
         'content':'content/Shader Pattern.ntc','skinLoading':'relaunch','expect':'run'},
    ]
    evidence=Path(args.evidence);evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='skin-loading-') as temporary:
        work=Path(temporary)
        fixture=skins.dualshocked_fixture(work/'fixtures')
        legacy=legacy_validation(Path(args.legacy_sources),fixture,work,evidence/'build463')
        app,scenarios=probe.assemble(args,probe.BRIDGE,work/'candidate')
        shutil.copytree(fixture,app/'SkinFixtures'/skins.DUALSHOCKED_ID)
        skins.REFERENCES=tuple(f for f in skins.REFERENCES if f[0]=='press-psx')
        skins.fixtures(app)
        # Byte-for-byte old-format preferences; written before the first session
        # opens the store. No import/reinstallation or selection action is used.
        (app/'skin-loading-seed.json').write_text(json.dumps({'version':1,'console':{
            'skin.portrait':skins.DUALSHOCKED_ID,'skin.landscape':skins.DUALSHOCKED_ID,
            'controls.pressureIntensity':'pronounced','future.setting':'keep-me'},'games':{
            'unrelated-game':{'skin.portrait':'default','future.setting':'unrelated'}}},indent=2))
        probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
        candidate=evidence/'candidate';candidate.mkdir()
        outcome=probe.run_in_simulator(app,candidate,240)
        report=json.loads((candidate/'probe.json').read_text()) if (candidate/'probe.json').exists() else {'results':[]}
        problems=probe.evaluate(report,scenarios)
        if not outcome['finished']: problems.append('candidate probe did not finish')
        # The journal must describe the exact missing resource and affected
        # orientation, and must not contain a refusal of the original skin.
        journals='\n'.join(r.get('journal','') for r in report.get('results',[]))
        if 'actually-missing.png' not in journals: problems.append('missing detailed resource diagnosis')
        for result in report.get('results',[]):
            checks=result.get('skinLoadingChecks',[])
            print(json.dumps({'name':result['name'],'checks':len(checks),
                              'failures':[c for c in checks if not c['passed']]}),flush=True)
        verdict={'source':args.label,'legacySource':'73b0aabc81ffec7e14873b1e466c294980ea28fc',
                 'originalArchiveSHA256':skins.DUALSHOCKED_SHA256,'legacy':legacy,
                 'candidateOutcome':outcome,'problems':problems,'physicalDeviceValidated':False,
                 'commercialAzureDreamsTested':False}
        (evidence/'verdict.json').write_text(json.dumps(verdict,indent=2))
        if problems: raise SystemExit('\n'.join(problems))
    print('Existing-install, actual in-game selection, per-orientation fallback and new-session persistence passed on Simulator.')

if __name__=='__main__':main()
