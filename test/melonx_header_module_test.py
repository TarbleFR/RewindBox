#!/usr/bin/env python3
"""Compile relocated public headers, reproducing the old CocoaPods failure."""
import hashlib,json,os,shlex,shutil,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POD=ROOT/'packages/melonx_internal_bridge/ios'
HEADER=POD/'Classes/MeloNXJitBridgePlugin.h'
OLD='5445f9bb3bd1b04ba88e4e4f03852e6dfbd4763e'
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
flutter=Path(os.environ['FLUTTER_ROOT'])/'bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
assert (flutter/'Flutter.framework/Flutter').is_file()
with tempfile.TemporaryDirectory(prefix='melonx-module-') as temporary:
    work=Path(temporary)
    framework=work/'melonx_internal_bridge.framework'
    headers=framework/'Headers';headers.mkdir(parents=True)
    modules=framework/'Modules';modules.mkdir()
    for source in (POD/'Memory').glob('*.h'):
        shutil.copy2(source,headers/source.name)
    public=headers/HEADER.name
    (headers/'melonx_internal_bridge.h').write_text('#import "MeloNXJitBridgePlugin.h"\n#import "MLXRamDonor.h"\n#import "MLXRamDonorProtocol.h"\n')
    (modules/'module.modulemap').write_text('framework module melonx_internal_bridge {\n umbrella header "melonx_internal_bridge.h"\n export *\n module * { export * }\n}\n')
    client=work/'client.m'
    client.write_text('@import melonx_internal_bridge;\nvoid check(void) { MLXRamDonor *donor = MLXRamDonor.shared; (void)donor.hasOutstandingRegions; (void)mlx_ram_donor_is_available(); (void)MeloNXMemorySnapshot(); }\n')
    command=['xcrun','clang','-fsyntax-only','-fobjc-arc','-fmodules','-target','arm64-apple-ios18.0','-isysroot',sdk,'-F',str(flutter),'-F',str(work),'-Werror=non-modular-include-in-framework-module',str(client)]
    public.write_bytes(subprocess.check_output(['git','show',OLD+':'+str(HEADER.relative_to(ROOT))],cwd=ROOT))
    old=subprocess.run([*command,'-fmodules-cache-path='+str(work/'old-cache')],capture_output=True,text=True)
    assert old.returncode!=0 and "'../Memory/MLXRamDonor.h' file not found" in old.stderr,old.stderr
    public.write_bytes(HEADER.read_bytes())
    current=subprocess.run([*command,'-fmodules-cache-path='+str(work/'new-cache')],capture_output=True,text=True)
    assert current.returncode==0,current.stderr
    # No search path points at the source Memory directory: only copied headers
    # can satisfy the framework import, as in the failing release compilation.
    assert not (framework/'Memory').exists()
    # Read the production CocoaPods build flags, not a separate test-only set.
    # The module import above exercises Swift's relocated C interface; the .mm
    # consumer below also requires Clang's explicit C++ module opt-in.
    podspec=POD/'melonx_internal_bridge.podspec'
    environment={k:v for k,v in os.environ.items() if k not in {'BUNDLE_GEMFILE','BUNDLE_PATH'}}
    spec=json.loads(subprocess.check_output(['pod','ipc','spec',str(podspec)],env=environment,text=True))
    settings=spec['pod_target_xcconfig']
    assert settings['CLANG_ENABLE_MODULES']=='YES'
    flags=shlex.split(settings['OTHER_CPLUSPLUSFLAGS'].replace('$(inherited)',''))
    cpp=work/'client.mm'
    cpp.write_text('#import "'+str(HEADER)+'"\nvoid check() { (void)MeloNXMemorySnapshot(); (void)mlx_ram_donor_is_available(); }\n')
    cpp_command=['xcrun','clang++','-fsyntax-only','-fobjc-arc','-std=c++20','-target','arm64-apple-ios18.0','-isysroot',sdk,'-F',str(flutter),str(cpp)]
    old_cpp=subprocess.run([*cpp_command,'-fmodules','-fno-cxx-modules','-fmodules-cache-path='+str(work/'old-cpp-cache')],capture_output=True,text=True)
    assert old_cpp.returncode!=0 and "C++ modules are disabled" in old_cpp.stderr,old_cpp.stderr
    current_cpp=subprocess.run([*cpp_command,*flags,'-fmodules-cache-path='+str(work/'new-cpp-cache')],capture_output=True,text=True)
    assert current_cpp.returncode==0,current_cpp.stderr
    report=dict(result='passed',source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        oldSource=OLD,oldRelocatedHeaderFailed=True,currentRelocatedHeaderPassed=True,
        oldObjectiveCxxModulesFailed=True,currentObjectiveCxxModulesPassed=True,podConfigurationActual=True,
        actualIPhoneSDK=True,gameplayTested=False,
        inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HEADER,podspec,Path(__file__)]})
    out=ROOT/'build/delivery/melonx-header-module.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: old relocated header and Objective-C++ flags fail; corrected framework and actual Pod flags compile with the iPhone SDK.')
