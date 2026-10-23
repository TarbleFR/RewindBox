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
import Metal
import QuartzCore
import Darwin
final class ProbeView:UIView {override class var layerClass:AnyClass { CAMetalLayer.self }}
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
       let storage=try runtime.content(operation:6)
       guard storage["success"] as? Bool == true, storage["profiles"] is [[String:Any]] else {throw NSError(domain:"actual-save-profiles",code:4)}
       let badSave=try runtime.content(path:"{\"titleId\":\"invalid\",\"profileId\":\"invalid\"}",operation:7)
       guard badSave["success"] as? Bool == false else {throw NSError(domain:"actual-save-validation",code:5)}
       report["storageProfilesRecognized"]=true;report["invalidSaveAssociationRejected"]=true
       try runtime.session.initialize(root:root)
       let invalid=try runtime.content(path:root.appendingPathComponent("missing.nsp").path,operation:0)
       guard invalid["success"] as? Bool == false, runtime.session.state == 0 else {throw NSError(domain:"actual-content",code:2)}
       try runtime.prepareGraphics(["resolution":0.5,"shaderCache":false,"asyncShaders":true,"vsync":true,"filter":"bilinear"],universalJit:false)
       let rejected=runtime.session.prepare(game:root.appendingPathComponent("missing.nro"),locale:"fr-FR",width:1280,height:720)
       guard rejected == -2, runtime.session.state == 0 else {throw NSError(domain:"actual-prepare",code:3)}
       // A synthetic PFS0 header contains no proprietary content. The actual
       // engine must report missing personal keys before allocating a guest.
       let package=root.appendingPathComponent("empty.nsp")
       try Data([0x50,0x46,0x53,0x30]+Array(repeating:UInt8(0),count:12)).write(to:package)
       let missingKeys=try runtime.content(path:package.path,operation:8)
       guard missingKeys["success"] as? Bool == false, missingKeys["errorCode"] as? String == "keysMissing", runtime.session.state == 0 else {throw NSError(domain:"actual-key-preflight",code:6)}
       // Simulator-only executable mapping proof with the real ARM64 engine.
       // It does not exercise iPhone signing, its helper or Universal JIT.
       try runtime.prepareJit();try runtime.prepareJit()
       let diagnostics=runtime.diagnostics()
       let events=diagnostics["events"] as? [[String:Any]] ?? []
       guard events.contains(where:{$0["stage"] as? String == "jitArena" && $0["status"] as? String == "passed"}) else {throw NSError(domain:"actual-jit-arena",code:7)}
       report["actualSimulatorCodeArenaVerified"]=true;report["missingKeysRejectedBeforeGuest"]=true
       // Original, unencrypted ARM64 homebrew: branch over its NRO header and
       // issue SVC ExitProcess. This is CPU/session proof, not a graphical game.
       let homebrew=root.appendingPathComponent("RewindBox-owned-exit.nro")
       var nro=Data(repeating:0,count:0x3000)
       func word(_ offset:Int,_ value:UInt32) {var little=value.littleEndian;withUnsafeBytes(of:&little){nro.replaceSubrange(offset..<offset+4,with:$0)}}
       word(0,0x14000020);word(0x10,0x304f524e);word(0x18,0x3000)
       word(0x20,0);word(0x24,0x1000);word(0x28,0x1000);word(0x2c,0x1000);word(0x30,0x2000);word(0x34,0x1000);word(0x38,0x1000)
       word(0x80,0xd2800000);word(0x84,0xd40000e1);word(0x88,0x14000000)
       try nro.write(to:homebrew)
       let hb=try runtime.content(path:homebrew.path,operation:8)
       guard hb["success"] as? Bool == true else {throw NSError(domain:"homebrew-preflight",code:8)}
       var sessions=0
       for _ in 0..<2 {
         let ended=DispatchSemaphore(value:0)
         var outcome:Result<Void,MeloNXHostError>?
         var owner:MeloNXSessionHost?
         var surface:ProbeView?
         DispatchQueue.main.sync {
           let view=ProbeView(frame:self.window!.rootViewController!.view.bounds)
           let layer=view.layer as! CAMetalLayer
           layer.device=MTLCreateSystemDefaultDevice();layer.pixelFormat = .bgra8Unorm
           layer.drawableSize=CGSize(width:1280,height:720)
           self.window!.rootViewController!.view.addSubview(view);surface=view
           let host=MeloNXSessionHost(api:runtime.session);owner=host
           do {
             try host.start(game:homebrew,locale:"en",width:1280,height:720,surface:layer,pointer:Unmanaged.passUnretained(layer).toOpaque(),beforeRun:{true}) {result in outcome=result;ended.signal()}
             DispatchQueue.main.asyncAfter(deadline:.now()+2) {host.requestStop()}
           } catch {outcome = .failure(error as? MeloNXHostError ?? .load(String(describing:error)));ended.signal()}
         }
         guard ended.wait(timeout:.now()+45) == .success else {throw NSError(domain:"homebrew-session-timeout",code:9)}
         guard let completedOutcome=outcome else {throw NSError(domain:"homebrew-result",code:12)}
         if case .failure(let error)=completedOutcome {throw error}
         guard runtime.session.state == 0, owner?.isSessionActive == false else {throw NSError(domain:"homebrew-session-cleanup",code:10)}
         DispatchQueue.main.sync {surface?.removeFromSuperview()}
         sessions += 1
       }
       let execution=runtime.diagnostics()["events"] as? [[String:Any]] ?? []
       guard execution.filter({$0["stage"] as? String == "guestExecution" && $0["status"] as? String == "passed"}).count >= 2 else {throw NSError(domain:"homebrew-guest-svc-unconfirmed",code:11)}
       report["originalHomebrewGuestSvcConfirmed"]=true;report["homebrewSimulatorSessions"]=sessions
       report["homebrewProducesVideo"]=false;report["iphoneGuestExecutionTested"]=false
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
