#!/usr/bin/env python3
"""Compile relocated public headers, reproducing the old CocoaPods failure."""
import hashlib,json,os,shutil,subprocess,tempfile
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
    report=dict(result='passed',source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        oldSource=OLD,oldRelocatedHeaderFailed=True,currentRelocatedHeaderPassed=True,
        actualIPhoneSDK=True,gameplayTested=False,
        inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HEADER,Path(__file__)]})
    out=ROOT/'build/delivery/melonx-header-module.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: old relocated public header fails; corrected framework module compiles with the iPhone SDK.')
