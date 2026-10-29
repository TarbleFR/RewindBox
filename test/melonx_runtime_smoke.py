#!/usr/bin/env python3
"""Load the actual NativeAOT runtime and private frameworks in an ARM64 iOS app.

Exercises an original non-graphical homebrew in Simulator only.
No physical-device signing, helper, personal content or gameplay proof is inferred.
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
def run(*args): return subprocess.check_output(list(map(str,args)),text=True,stderr=subprocess.STDOUT,timeout=300).strip()
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
     var observedRuntime:MeloNXRuntimeAPI?
     do {
       let frameworks=Bundle.main.privateFrameworksURL!
       let root=documents.appendingPathComponent("MeloNX")
       let runtime=try MeloNXRuntimeAPI(library:frameworks.appendingPathComponent("MeloNXCore.framework/MeloNXCore"),frameworks:frameworks,root:root)
       observedRuntime=runtime
       NSLog("SMOKE boundary 54")
       let content=try runtime.content(operation:3)
       guard content["success"] as? Bool == true, content["root"] as? String == root.path else {throw NSError(domain:"actual-bootstrap",code:1)}
       let journal=documents.appendingPathComponent("app.log")
       NSLog("SMOKE boundary 57")
       MeloNXLaunchJournal.configure(path:journal.path)
       NSLog("SMOKE boundary 58")
       let journalSetup=try runtime.content(path:journal.path,operation:9)
       guard journalSetup["success"] as? Bool == true else {throw NSError(domain:"actual-launch-journal-configuration",code:23)}
       NSLog("SMOKE boundary 60")
       let storage=try runtime.content(operation:6)
       guard storage["success"] as? Bool == true, storage["profiles"] is [[String:Any]] else {throw NSError(domain:"actual-save-profiles",code:4)}
       NSLog("SMOKE boundary 62")
       let badSave=try runtime.content(path:"{\"titleId\":\"invalid\",\"profileId\":\"invalid\"}",operation:7)
       guard badSave["success"] as? Bool == false else {throw NSError(domain:"actual-save-validation",code:5)}
       report["storageProfilesRecognized"]=true;report["invalidSaveAssociationRejected"]=true
       NSLog("SMOKE boundary 65")
       try runtime.session.initialize(root:root)
       NSLog("SMOKE boundary 66")
       let invalid=try runtime.content(path:root.appendingPathComponent("missing.nsp").path,operation:0)
       guard invalid["success"] as? Bool == false, runtime.session.state == 0 else {throw NSError(domain:"actual-content",code:2)}
       NSLog("SMOKE boundary 68")
       try runtime.prepareGraphics(["resolution":0.5,"shaderCache":false,"asyncShaders":true,"vsync":true,"filter":"bilinear"],universalJit:false)
       let rejected=runtime.session.prepare(game:root.appendingPathComponent("missing.nro"),locale:"fr-FR",width:1280,height:720)
       guard rejected == -2, runtime.session.state == 0 else {throw NSError(domain:"actual-prepare",code:3)}
       // A synthetic PFS0 header contains no proprietary content. The actual
       // engine must report missing personal keys before allocating a guest.
       let package=root.appendingPathComponent("empty.nsp")
       try Data([0x50,0x46,0x53,0x30]+Array(repeating:UInt8(0),count:12)).write(to:package)
       NSLog("SMOKE boundary 75")
       let missingKeys=try runtime.content(path:package.path,operation:8)
       guard missingKeys["success"] as? Bool == false, missingKeys["errorCode"] as? String == "keysMissing", missingKeys["nativeStatus"] is NSNumber, runtime.session.state == 0 else {throw NSError(domain:"actual-key-preflight",code:6)}
       let persisted=try String(contentsOf:journal,encoding:.utf8)
       let persistedEvents=persisted.components(separatedBy:.newlines).compactMap { line -> [String:Any]? in
         let prefix="[MeloNX:core] "
         guard line.hasPrefix(prefix), let data=String(line.dropFirst(prefix.count)).data(using:.utf8) else {return nil}
         return (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
       }
       guard persistedEvents.contains(where:{$0["stage"] as? String == "keys" && $0["status"] as? String == "failed" && $0["nativeStatus"] as? Int == 1}) else {throw NSError(domain:"actual-launch-journal-persistence",code:24)}
       report["actualNativeLaunchJournalWritten"]=true
       // Exercise the actual new NativeAOT key import ABI using synthetic bytes.
       // Keep unsupported entries beside a supported one, exactly as an export.
       let staged=root.appendingPathComponent("key-preview",isDirectory:true)
       try FileManager.default.createDirectory(at:staged,withIntermediateDirectories:true)
       let candidate=staged.appendingPathComponent("prod.keys")
       let fixture="header_key = "+String(repeating:"a",count:64)+"\nfuture_console_key = "+String(repeating:"b",count:32)+"\nmariko_master_kek_source_05 = "+String(repeating:"c",count:34)
       try fixture.write(to:candidate,atomically:true,encoding:.utf8)
       NSLog("SMOKE boundary 87")
       let keyPreview=try runtime.content(path:candidate.path,operation:2)
       guard keyPreview["success"] as? Bool == true,
             (keyPreview["recognizedKeys"] as? NSNumber)?.intValue == 1,
             (keyPreview["ignoredKeys"] as? NSNumber)?.intValue == 1,
             (keyPreview["invalidSizeKeys"] as? NSNumber)?.intValue == 1 else {throw NSError(domain:"actual-key-import-preview",code:16)}
       let installed=root.appendingPathComponent("system/prod.keys")
       guard !FileManager.default.fileExists(atPath:installed.path) else {throw NSError(domain:"preview-mutated-installed-keys",code:17)}
       try fixture.write(to:installed,atomically:true,encoding:.utf8)
       NSLog("SMOKE boundary 95")
       let reloaded=try runtime.content(operation:2)
       guard reloaded["success"] as? Bool == true else {throw NSError(domain:"actual-key-reload",code:18)}
       try "header_key = aa".write(to:candidate,atomically:true,encoding:.utf8)
       NSLog("SMOKE boundary 98")
       let badKey=try runtime.content(path:candidate.path,operation:2)
       guard badKey["success"] as? Bool == false, badKey["errorCode"] as? String == "keySize",
             try String(contentsOf:installed,encoding:.utf8) == fixture else {throw NSError(domain:"actual-key-refusal",code:19)}
       try FileManager.default.removeItem(at:installed)
       try FileManager.default.removeItem(at:staged)
       report["actualKeyImportABIValidated"]=true;report["keyUnknownEntryAccepted"]=true
       report["mixedInvalidKeySizeAccepted"]=true
       report["keyRefusalCodePreserved"]=true;report["personalKeysUsed"]=false
       do {
         NSLog("SMOKE boundary 107")
         try runtime.prepareGraphics(["resolution":9],universalJit:false)
         throw NSError(domain:"invalid-graphics-accepted",code:13)
       } catch MeloNXHostError.operation(let stage,let status,let detail) {
         guard stage == "graphics", status == 1, !detail.isEmpty else {throw NSError(domain:"graphics-error-propagation",code:14)}
         report["invalidGraphicsCodePreserved"]=true
       }
       // Resolve and exercise the new entry point in the actual NativeAOT image.
       for ratio in 0...5 {
         NSLog("SMOKE boundary 115")
         try runtime.prepareGraphics(["aspectRatio":ratio,"hostMemoryBudget":true,"textureRecompression":true,"showRamGraph":true],universalJit:false)
       }
       guard !runtime.setAspectRatio(5,generation:12345) else {throw NSError(domain:"stale-display-generation",code:20)}
       // The RAM overlay's game FPS export: resolved in the actual image and
       // refused for a generation that is not live.
       guard runtime.providesPerformanceSnapshot,runtime.performanceSnapshot(generation:12345).isEmpty else {throw NSError(domain:"performance-snapshot-export",code:24)}
       NSLog("SMOKE boundary 118")
       try runtime.prepareGraphics(["aspectRatio":1],universalJit:false)
       report["displayAndMemoryConfigurationAccepted"]=true
       // Simulator-only executable mapping proof with the real ARM64 engine.
       // It does not exercise iPhone signing, its helper or Universal JIT.
       NSLog("SMOKE boundary 122")
       try runtime.prepareJit();try runtime.prepareJit()
       typealias SignalQuery = @convention(c) (Int32,UnsafePointer<Darwin.sigaction>?,UnsafeMutablePointer<Darwin.sigaction>?) -> Int32
       let inspectSignal=unsafeBitCast(dlsym(dlopen(nil,RTLD_NOW)!,"sigaction")!,to:SignalQuery.self)
       var segv=Darwin.sigaction(),bus=Darwin.sigaction()
       guard inspectSignal(SIGSEGV,nil,&segv)==0, inspectSignal(SIGBUS,nil,&bus)==0,
             segv.sa_flags & SA_SIGINFO != 0, bus.sa_flags & SA_SIGINFO != 0 else {throw NSError(domain:"actual-Darwin-signal-ABI",code:15)}
       report["actualDarwinThreeArgumentHandlersVerified"]=true
       let diagnostics=runtime.diagnostics()
       let events=diagnostics["events"] as? [[String:Any]] ?? []
       guard events.contains(where:{$0["stage"] as? String == "jitArena" && $0["status"] as? String == "passed"}) else {throw NSError(domain:"actual-jit-arena",code:7)}
       report["actualSimulatorCodeArenaVerified"]=true;report["missingKeysRejectedBeforeGuest"]=true
       // Original, unencrypted ARM64 homebrew: branch over its NRO header,
       // call a function whose return lands on a frame-opening STP (the JIT
       // ends that unit after the call and translates the continuation when
       // the call returns), tail-jump past another frame opening, jump past 67
       // undefined words (that unit ends at the jump, as a switch case does),
       // then issue SVC ExitProcess. This is CPU/session proof, not a graphical game.
       let homebrew=root.appendingPathComponent("RewindBox-owned-exit.nro")
       var nro=Data(repeating:0,count:0x3000)
       func word(_ offset:Int,_ value:UInt32) {var little=value.littleEndian;withUnsafeBytes(of:&little){nro.replaceSubrange(offset..<offset+4,with:$0)}}
       word(0,0x14000020);word(0x10,0x304f524e);word(0x18,0x3000)
       word(0x20,0);word(0x24,0x1000);word(0x28,0x1000);word(0x2c,0x1000);word(0x30,0x2000);word(0x34,0x1000);word(0x38,0x1000)
       word(0x80,0x94000020);word(0x84,0xa9bf7bfd);word(0x88,0xa8c17bfd);word(0x8c,0x14000021);word(0x90,0xa9bf7bfd)
       word(0x100,0xd65f03c0)
       word(0x110,0x14000044)
       word(0x220,0xd2800000);word(0x224,0xd40000e1);word(0x228,0x14000000)
       try nro.write(to:homebrew)
       NSLog("SMOKE boundary 142")
       let hb=try runtime.content(path:homebrew.path,operation:8)
       guard hb["success"] as? Bool == true else {throw NSError(domain:"homebrew-preflight",code:8)}
       var sessions=0
       let donationBytes=4*1024*1024*1024
       guard let donation=mmap(nil,donationBytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0), donation != MAP_FAILED else {throw NSError(domain:"donation-fixture-map",code:21)}
       // Local test backing proves the actual Core's allocation/retirement path;
       // it is explicitly NOT a donor process or reduced iPhone footprint proof.
       defer { if runtime.withdrawMemory() { munmap(donation,donationBytes) } }
       var donatedSessions=0
       var livePerformanceSessions=0
       var guestSvcSessions:[[String:Any]]=[]
       for sessionIndex in 1...2 {
         // The diagnostic ring retains earlier sessions and may evict them.
         // Bind this proof to events produced after this session's start.
         let beforeEvents=runtime.diagnostics()["events"] as? [[String:Any]] ?? []
         let beforeSequence=beforeEvents.compactMap { ($0["sequence"] as? NSNumber)?.int64Value }.max() ?? 0
         let guestDeadline=DispatchTime.now()+30
         let sessionDeadline=DispatchTime.now()+45
         guard runtime.offerMemory(donation,bytes:UInt64(donationBytes)) else {throw NSError(domain:"actual-memory-offer",code:22)}
         var borrowedWhileRunning=false
         var liveWithdrawalRefused=false
         var liveGeneration:Int64=0
         var livePerformance:[String:Any]=[:]
         let ended=DispatchSemaphore(value:0)
         var outcome:Result<Void,MeloNXHostError>?
         var owner:MeloNXSessionHost?
         var surface:ProbeView?
         var guestSvcSequence:Int64?
         var sessionEnded=false
         DispatchQueue.main.sync {
           let view=ProbeView(frame:self.window!.rootViewController!.view.bounds)
           let layer=view.layer as! CAMetalLayer
           layer.device=MTLCreateSystemDefaultDevice();layer.pixelFormat = .bgra8Unorm
           layer.drawableSize=CGSize(width:1280,height:720)
           self.window!.rootViewController!.view.addSubview(view);surface=view
           let host=MeloNXSessionHost(api:runtime.session);owner=host
           do {
             try host.start(game:homebrew,locale:"en",width:1280,height:720,surface:layer,pointer:Unmanaged.passUnretained(layer).toOpaque(),prepared:{liveGeneration=$0},beforeRun:{true}) {result in outcome=result;ended.signal()}
           } catch {outcome = .failure(error as? MeloNXHostError ?? .load(String(describing:error)));ended.signal()}
         }
         // Prepared/Running precede GPU readiness. A fixed-delay stop can
         // correctly cancel a cold startup before any guest CPU instruction.
         // Wait off the main queue for this session's actual SVC instead.
         while DispatchTime.now() < guestDeadline {
           let execution=runtime.diagnostics()["events"] as? [[String:Any]] ?? []
           if let event=execution.first(where: {
             $0["stage"] as? String == "guestExecution" && $0["status"] as? String == "passed" &&
             (($0["sequence"] as? NSNumber)?.int64Value ?? 0) > beforeSequence
           }) {
             guestSvcSequence=(event["sequence"] as? NSNumber)?.int64Value
             break
           }
           if ended.wait(timeout:.now()+0.05) == .success {sessionEnded=true;break}
         }
         DispatchQueue.main.sync {
           if guestSvcSequence != nil {
             livePerformance=runtime.performanceSnapshot(generation:liveGeneration)
             let memory=runtime.memorySnapshot()
             borrowedWhileRunning=((memory["donorUsedBytes"] as? NSNumber)?.uint64Value ?? 0)>0
             liveWithdrawalRefused = !runtime.withdrawMemory()
           }
           // Also stop on a missing-SVC deadline so the failure can drain. No
           // delayed callback survives this session or can stop the next one.
           owner?.requestStop()
         }
         if !sessionEnded {
           guard ended.wait(timeout:sessionDeadline) == .success else {throw NSError(domain:"homebrew-session-timeout",code:9)}
         }
         guard let completedOutcome=outcome else {throw NSError(domain:"homebrew-result",code:12)}
         if case .failure(let error)=completedOutcome {throw error}
         guard let svcSequence=guestSvcSequence else {throw NSError(domain:"homebrew-guest-svc-unconfirmed",code:11,userInfo:["session":sessionIndex,"generation":liveGeneration,"afterSequence":beforeSequence])}
         guestSvcSessions.append(["session":sessionIndex,"generation":liveGeneration,"afterSequence":beforeSequence,"svcSequence":svcSequence])
         guard runtime.session.state == 0, owner?.isSessionActive == false else {throw NSError(domain:"homebrew-session-cleanup",code:10)}
         DispatchQueue.main.sync {surface?.removeFromSuperview()}
         // Homebrew presents no frames, so a live snapshot (when the window is
         // already initialized) is well-formed zeros; it proves the gated path,
         // not a game frame rate. The ended generation must be refused.
         if !livePerformance.isEmpty {
           guard ["gameFps","gameFrameTimeMs","fifoPercent"].allSatisfy({ key in (livePerformance[key] as? Double).map { $0.isFinite && $0 >= 0 } ?? false }) else {throw NSError(domain:"live-performance-snapshot",code:25)}
           livePerformanceSessions += 1
         }
         guard liveGeneration > 0,runtime.performanceSnapshot(generation:liveGeneration).isEmpty else {throw NSError(domain:"ended-performance-generation",code:26)}
         guard borrowedWhileRunning,liveWithdrawalRefused,
               (runtime.memorySnapshot()["donorUsedBytes"] as? NSNumber)?.uint64Value == 0,
               runtime.withdrawMemory() else {throw NSError(domain:"actual-donation-lifetime",code:23)}
         donatedSessions += 1
         sessions += 1
       }
       guard guestSvcSessions.count == 2,
             Set(guestSvcSessions.compactMap { $0["svcSequence"] as? Int64 }).count == 2 else {throw NSError(domain:"homebrew-guest-svc-unconfirmed",code:11)}
       report["homebrewGuestSvcSessions"]=guestSvcSessions
       report["actualCoreDonatedBackingSessions"]=donatedSessions
       report["performanceSnapshotStaleAndEndedRefused"]=true
       report["livePerformanceSnapshotSessions"]=livePerformanceSessions
       report["donorProcessUsedInSmoke"]=false
       report["originalHomebrewGuestSvcConfirmed"]=true;report["homebrewSimulatorSessions"]=sessions
       report["homebrewProducesVideo"]=false;report["iphoneGuestExecutionTested"]=false
       report["result"]="passed";report["initializationAndIdempotency"]=true;report["invalidContentRejected"]=true;report["graphicsAccepted"]=true;report["invalidGuestRejected"]=true
     } catch {report["result"]="failed";report["diagnostic"]=String(describing:error);report["nativeDiagnostics"]=observedRuntime?.diagnostics();report["nativeSessionState"]=observedRuntime?.session.state}
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
  launched=run('xcrun','simctl','launch',device,bundle)
  pid=launched.rsplit(':',1)[-1].strip();assert pid.isdigit(),launched
  container=Path(run('xcrun','simctl','get_app_container',device,bundle,'data'));result=container/'Documents/smoke.json'
  deadline=time.monotonic()+120
  while not result.exists() and time.monotonic()<deadline:time.sleep(1)
  native_log=container/'Documents/native-runtime.log'
  if native_log.exists():
   text=native_log.read_text(errors='replace');(OUT/'native-runtime.log').write_text(text[-1000000:]);print(text[-20000:],flush=True)
  if not result.exists() or json.loads(result.read_text()).get('result') != 'passed':
   sampled=subprocess.run(['sample',pid,'1','1','-file',str(OUT/'native-stacks.txt')],capture_output=True,text=True,timeout=20)
   print('Native process stack sampling:',sampled.returncode,flush=True)
   if (OUT/'native-stacks.txt').exists():print((OUT/'native-stacks.txt').read_text(errors='replace')[:70000],flush=True)
  if not result.exists():
   (OUT/'simulator.log').write_text(run('xcrun','simctl','spawn',device,'log','show','--last','3m','--predicate','process == "MeloNXSmoke"'))
   raise RuntimeError('Actual NativeAOT bootstrap did not report completion')
  report=json.loads(result.read_text());report['runtime']=runtime;report['coreSha256']=sha(core)
  report['inputs']={str(p.relative_to(ROOT)):sha(p) for p in [*sources,Path(__file__)]}
  (OUT/'actual-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report,indent=2));assert report['result']=='passed',report
 finally:
  subprocess.run(['xcrun','simctl','shutdown',device],check=False);subprocess.run(['xcrun','simctl','delete',device],check=False)
