#!/usr/bin/env python3
"""Load the actual NativeAOT runtime and private frameworks in an ARM64 iOS app.

No JIT, firmware, keys, game execution, rendering or audio proof is inferred.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/melonx-smoke';OUT.mkdir(parents=True,exist_ok=True)
def run(*args): return subprocess.check_output(list(map(str,args)),text=True,stderr=subprocess.STDOUT).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
core=ROOT/'dist/melonx/iossimulator-arm64/Ryujinx.Library.dylib'
identity=json.loads(core.with_name('identity.json').read_text());assert sha(core)==identity['sha256']
deps=ROOT/'dist/melonx-native';native=json.loads((deps/'identity.json').read_text())
for entry in native['binaries']:assert sha(deps/entry['path'])==entry['sha256']
with tempfile.TemporaryDirectory(prefix='melonx-runtime-') as temporary:
 work=Path(temporary);app=work/'MeloNXSmoke.app';frameworks=app/'Frameworks';frameworks.mkdir(parents=True)
 for source in (deps/'iossimulator').glob('*.framework'):shutil.copytree(source,frameworks/source.name)
 directory=frameworks/'MeloNXCore.framework';directory.mkdir();shutil.copy2(core,directory/'MeloNXCore')
 run('install_name_tool','-id','@rpath/MeloNXCore.framework/MeloNXCore',directory/'MeloNXCore')
 (directory/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'MeloNXCore','CFBundleIdentifier':'com.neogamelab.neostation.smoke.core','CFBundlePackageType':'FMWK','CFBundleVersion':'1'}))
 bundle='com.neogamelab.neostation.melonxsmoke'
 (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'MeloNXSmoke','CFBundleIdentifier':bundle,'CFBundleName':'MeloNXSmoke','CFBundlePackageType':'APPL','CFBundleVersion':'1','CFBundleShortVersionString':'1','MinimumOSVersion':'18.0','LSRequiresIPhoneOS':True,'UIDeviceFamily':[1,2],'UILaunchScreen':{}}))
 swift=work/'App.swift';swift.write_text(r'''import UIKit
import Darwin
@main final class Smoke: UIResponder, UIApplicationDelegate {
 var window: UIWindow?
 func application(_ app: UIApplication,didFinishLaunchingWithOptions options:[UIApplication.LaunchOptionsKey:Any]? = nil)->Bool {
   window=UIWindow(frame:UIScreen.main.bounds);window?.rootViewController=UIViewController();window?.makeKeyAndVisible()
   DispatchQueue.global(qos:.userInitiated).async {
     let documents=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
     let log=documents.appendingPathComponent("native-runtime.log")
     log.path.withCString { _ = freopen($0,"w",stderr) }
     var report:[String:Any]=["actualNativeAOT":true,"gameplayTested":false,"jitTested":false]
     do {
       let frameworks=Bundle.main.privateFrameworksURL!
       let root=documents.appendingPathComponent("MeloNX")
       let runtime=try MeloNXRuntimeAPI(library:frameworks.appendingPathComponent("MeloNXCore.framework/MeloNXCore"),frameworks:frameworks,root:root)
       let content=try runtime.content(operation:3)
       guard content["success"] as? Bool == true, content["root"] as? String == root.path else {throw NSError(domain:"actual-bootstrap",code:1)}
       try runtime.session.initialize(root:root)
       let invalid=try runtime.content(path:root.appendingPathComponent("missing.nsp").path,operation:0)
       guard invalid["success"] as? Bool == false, runtime.session.state == 0 else {throw NSError(domain:"actual-content",code:2)}
       try runtime.prepareGraphics(["resolution":0.5,"shaderCache":false,"asyncShaders":true,"vsync":true,"filter":"bilinear"],universalJit:false)
       let rejected=runtime.session.prepare(game:root.appendingPathComponent("missing.nro"),locale:"fr-FR",width:1280,height:720)
       guard rejected == -2, runtime.session.state == 0 else {throw NSError(domain:"actual-prepare",code:3)}
       report["result"]="passed";report["initializationAndIdempotency"]=true;report["invalidContentRejected"]=true;report["graphicsAccepted"]=true;report["invalidGuestRejected"]=true
     } catch {report["result"]="failed";report["diagnostic"]=String(describing:error)}
     try? JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:documents.appendingPathComponent("smoke.json"),options:.atomic)
   };return true
 }
}''')
 sdk=run('xcrun','--sdk','iphonesimulator','--show-sdk-path')
 sources=[ROOT/'packages/melonx_internal_bridge/ios/Classes'/name for name in ['MeloNXSessionHost.swift','MeloNXRuntimeAPI.swift']]
 run('xcrun','swiftc','-swift-version','5','-target','arm64-apple-ios18.0-simulator','-sdk',sdk,'-framework','UIKit','-Xlinker','-rpath','-Xlinker','@executable_path/Frameworks',*sources,swift,'-o',app/'MeloNXSmoke')
 for framework in frameworks.glob('*.framework'):run('codesign','--force','--sign','-',framework)
 run('codesign','--force','--sign','-',app)
 runtimes=json.loads(run('xcrun','simctl','list','runtimes','-j'))['runtimes']
 runtime=next(r['identifier'] for r in reversed(runtimes) if r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-'))
 device=run('xcrun','simctl','create','MeloNX smoke '+uuid.uuid4().hex[:8],'com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro',runtime)
 try:
  run('xcrun','simctl','boot',device);run('xcrun','simctl','bootstatus',device,'-b');run('xcrun','simctl','install',device,app)
  run('xcrun','simctl','launch',device,bundle)
  container=Path(run('xcrun','simctl','get_app_container',device,bundle,'data'));result=container/'Documents/smoke.json'
  deadline=time.monotonic()+120
  while not result.exists() and time.monotonic()<deadline:time.sleep(1)
  if not result.exists():
   (OUT/'simulator.log').write_text(run('xcrun','simctl','spawn',device,'log','show','--last','3m','--predicate','process == "MeloNXSmoke"'))
   raise RuntimeError('Actual NativeAOT bootstrap did not report completion')
  native_log=container/'Documents/native-runtime.log'
  if native_log.exists():
   text=native_log.read_text(errors='replace');(OUT/'native-runtime.log').write_text(text[-1000000:]);print(text[-20000:],flush=True)
  report=json.loads(result.read_text());report['runtime']=runtime;report['coreSha256']=sha(core)
  report['inputs']={str(p.relative_to(ROOT)):sha(p) for p in [*sources,Path(__file__)]}
  (OUT/'actual-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report,indent=2));assert report['result']=='passed',report
 finally:
  subprocess.run(['xcrun','simctl','shutdown',device],check=False);subprocess.run(['xcrun','simctl','delete',device],check=False)
