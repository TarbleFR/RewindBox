#!/usr/bin/env python3
"""Run the real registered Swift plugin in UIKit with explicit guest/JIT doubles."""
import hashlib,json,os,plistlib,shutil,subprocess,tempfile,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/melonx-host';OUT.mkdir(parents=True,exist_ok=True)
CLASSES=ROOT/'packages/melonx_internal_bridge/ios/Classes'
FIXTURES=ROOT/'test/melonx_presentation'
def run(*args):
    return subprocess.check_output(list(map(str,args)),stderr=subprocess.STDOUT,text=True,timeout=300).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
flutter=Path(os.environ['FLUTTER_ROOT'])/'bin/cache/artifacts/engine/ios/Flutter.xcframework'
framework=next(flutter.glob('*simulator*/Flutter.framework'))
sdk=run('xcrun','--sdk','iphonesimulator','--show-sdk-path')
runtimes=json.loads(run('xcrun','simctl','list','runtimes','-j'))['runtimes']
runtime=next(r['identifier'] for r in reversed(runtimes) if r.get('isAvailable') and '.iOS-' in r['identifier'])
device=run('xcrun','simctl','create','MeloNX presentation '+uuid.uuid4().hex[:8],'com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro',runtime)
reports=[]
try:
    run('xcrun','simctl','boot',device);run('xcrun','simctl','bootstatus',device,'-b')
    with tempfile.TemporaryDirectory(prefix='melonx-presentation-') as temporary:
        work=Path(temporary)
        for old in [True,False]:
            name='Old' if old else 'New'
            app=work/(name+'.app');(app/'Frameworks').mkdir(parents=True)
            shutil.copytree(framework,app/'Frameworks/Flutter.framework')
            bundle='com.neogamelab.neostation.presentation'+name.lower()
            (app/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable=name,CFBundleIdentifier=bundle,
                CFBundleName=name,CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1',
                MinimumOSVersion='18.0',LSRequiresIPhoneOS=True,UIDeviceFamily=[1,2],UILaunchScreen={},OldControl=old,
                UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes':False,'UISceneConfigurations':{}})))
            source=CLASSES/'MeloNXInternalBridgePlugin.swift'
            if old:
                source=work/'OldPlugin.swift'
                source.write_text(run('git','-C',ROOT,'show','fa6d056e668e55fb7b96959b20cc15064e52e68a:packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift')+'\n')
            obj=work/(name+'.o')
            try:
                run('xcrun','clang','-c','-fobjc-arc','-target','arm64-apple-ios18.0-simulator','-isysroot',sdk,
                    '-F',framework.parent,FIXTURES/'Registrar.m','-o',obj)
                run('xcrun','swiftc','-swift-version','5','-target','arm64-apple-ios18.0-simulator','-sdk',sdk,
                    '-F',framework.parent,'-framework','Flutter','-framework','UIKit','-framework','AVFoundation',
                    '-import-objc-header',FIXTURES/'Registrar.h','-Xlinker','-rpath','-Xlinker','@executable_path/Frameworks',
                    source,CLASSES/'MeloNXPresentation.swift',FIXTURES/'Doubles.swift',FIXTURES/'App.swift',obj,'-o',app/name)
                run('codesign','--force','--sign','-',app/'Frameworks/Flutter.framework')
                run('codesign','--force','--sign','-',app)
                run('xcrun','simctl','install',device,app)
                run('xcrun','simctl','launch',device,bundle)
                container=Path(run('xcrun','simctl','get_app_container',device,bundle,'data'))
                result=container/'Documents/presentation.json'
                deadline=time.monotonic()+45
                while not result.exists() and time.monotonic()<deadline:time.sleep(.5)
                if not result.exists():
                    print(run('xcrun','simctl','spawn',device,'log','show','--last','2m','--predicate',f'process == "{name}"')[-16000:])
                    raise AssertionError('UIKit probe did not report: '+name)
                report=json.loads(result.read_text());reports.append(report)
                print(json.dumps(report,indent=2),flush=True)
                assert report['result']=='passed' and report['oldControl']==old
                run('xcrun','simctl','terminate',device,bundle)
            except subprocess.CalledProcessError as e:
                print(e.output,flush=True);raise
finally:
    subprocess.run(['xcrun','simctl','shutdown',device],check=False,capture_output=True)
    subprocess.run(['xcrun','simctl','delete',device],check=False,capture_output=True)
inputs=[CLASSES/'MeloNXInternalBridgePlugin.swift',CLASSES/'MeloNXPresentation.swift',Path(__file__),*sorted(FIXTURES.glob('*'))]
receipt=dict(result='passed',source=run('git','-C',ROOT,'rev-parse','HEAD'),runtime=runtime,
    oldControlSource='fa6d056e668e55fb7b96959b20cc15064e52e68a',reports=reports,
    inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},physicalDeviceTested=False,gameplayTested=False)
(OUT/'presentation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS actual UIKit registration/presentation/retry; engine, JIT and guest frames are explicit doubles.')
