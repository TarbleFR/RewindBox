"""Run the production bounded memory graph, FPS label and OS footprint sampler in UIKit."""
import hashlib,json,plistlib,subprocess,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CLASSES=ROOT/'packages/melonx_internal_bridge/ios/Classes'
OUT=ROOT/'dist/melonx-host';OUT.mkdir(parents=True,exist_ok=True)
def run(*a):
 try:return subprocess.check_output(list(map(str,a)),stderr=subprocess.STDOUT,text=True,timeout=300).strip()
 except subprocess.CalledProcessError as e:print(e.output,flush=True);raise
sdk=run('xcrun','--sdk','iphonesimulator','--show-sdk-path')
runtime=next(r['identifier'] for r in reversed(json.loads(run('xcrun','simctl','list','runtimes','-j'))['runtimes']) if r.get('isAvailable') and '.iOS-' in r['identifier'])
device=run('xcrun','simctl','create','MeloNX memory '+uuid.uuid4().hex[:8],'com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro',runtime)
try:
 run('xcrun','simctl','boot',device);run('xcrun','simctl','bootstatus',device,'-b')
 with tempfile.TemporaryDirectory(prefix='melonx-memory-') as d:
  w=Path(d);app=w/'Memory.app';app.mkdir();bundle='com.neogamelab.neostation.memoryprobe'
  (app/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable='Memory',CFBundleIdentifier=bundle,CFBundleName='Memory',CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1',MinimumOSVersion='18.0',LSRequiresIPhoneOS=True,UIDeviceFamily=[1],UILaunchScreen={})))
  # Exact production function; full ObjC++ plugin is separately iPhone-SDK checked.
  native=(CLASSES/'MeloNXJitBridgePlugin.mm').read_text().split('NSDictionary* MeloNXMemorySnapshot(void) {',1)[1]
  (w/'Memory.h').write_text('#import <Foundation/Foundation.h>\nNSDictionary* _Nonnull MeloNXMemorySnapshot(void);\n')
  (w/'Memory.m').write_text('#import "Memory.h"\n#import <mach/mach.h>\n#import <os/proc.h>\n#import <TargetConditionals.h>\nNSDictionary* MeloNXMemorySnapshot(void) {'+native)
  (w/'App.swift').write_text(r'''import UIKit
func MeloNXText(_ key:String)->String { key }
@main class App:UIResponder,UIApplicationDelegate {
var window:UIWindow?
func application(_ app:UIApplication,didFinishLaunchingWithOptions options:[UIApplication.LaunchOptionsKey:Any]?)->Bool {
 let window=UIWindow(frame:UIScreen.main.bounds);self.window=window
 let view=UIViewController();view.view.backgroundColor = .darkGray;window.rootViewController=view;window.makeKeyAndVisible()
 DispatchQueue.main.asyncAfter(deadline:.now()+0.2){self.check(view)};return true
}
func check(_ view:UIViewController) {
 var count=0
 func check(_ value:Bool) { precondition(value,"memory assertion \(count)");count += 1 }
 var history=MeloNXMemoryHistory();check(history.peak==nil)
 history.append(time:0,bytes:nil);check(history.points.count==1 && history.peak==nil)
 for i in 0..<400 {history.append(time:Double(i)/2,bytes:UInt64(i)*1048576)}
 check(history.points.count==120 && history.peak==399*1048576)
 history.append(time:300,bytes:nil);check(history.points.count==1 && history.points[0].bytes==nil && history.peak==399*1048576)
 let actual=MeloNXMemorySnapshot();check((actual["footprintBytes"] as? NSNumber)?.uint64Value ?? 0 > 0)
 let graph=MeloNXMemoryGraph(frame:CGRect(x:20,y:80,width:240,height:152))
 var samples=0
 var fps:Any?=59.94 // MeloNXRuntimeAPI.performanceSnapshot reports a Swift Double
 graph.now = { Double(samples)/2 }
 graph.sample = {samples += 1;var values:[String:Any]=["footprintBytes":NSNumber(value:UInt64(512+samples*2)*1048576),"availableBytes":NSNumber(value:UInt64(768)*1048576),"donorMappedBytes":NSNumber(value:UInt64(4096)*1048576),"donorUsedBytes":NSNumber(value:UInt64(3072)*1048576),"donorState":"offered"];values["gameFps"]=fps;return values}
 view.view.addSubview(graph);graph.setSampling(true);check(graph.isSampling && samples==1)
 graph.setSampling(true);check(samples==1)
 for _ in 0..<120 {graph.observe()};check(graph.history.points.count==120)
 check(graph.fpsText=="60 FPS" && graph.accessibilityLabel?.contains("60 FPS")==true)
 // No live session (or an older engine): the title row shows no counter.
 fps=nil;graph.observe();check(graph.fpsText.isEmpty && graph.accessibilityLabel?.contains("FPS")==false)
 fps=29.97;graph.observe();check(graph.fpsText=="30 FPS" && graph.history.points.count==120)
 graph.setSampling(false);check(!graph.isSampling)
 graph.layoutIfNeeded()
 let renderer=UIGraphicsImageRenderer(bounds:graph.bounds)
 let image=renderer.image {graph.layer.render(in:$0.cgContext)}
 let root=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
 try! image.pngData()!.write(to:root.appendingPathComponent("memory.png"))
 weak var released:MeloNXMemoryGraph?
 autoreleasepool {let temporary=MeloNXMemoryGraph();temporary.setSampling(true);released=temporary}
 check(released==nil)
 DispatchQueue.main.asyncAfter(deadline:.now()+0.7){
  check(samples==123)
  let report:[String:Any] = ["result":"passed","cases":count,"actualFootprintBytes":actual["footprintBytes"]!,"gameplayTested":false]
  try! JSONSerialization.data(withJSONObject:report,options:.prettyPrinted).write(to:root.appendingPathComponent("memory.json"))
 }
}
}''')
  run('xcrun','clang','-c','-fobjc-arc','-target','arm64-apple-ios18.0-simulator','-isysroot',sdk,w/'Memory.m','-o',w/'Memory.o')
  run('xcrun','swiftc','-swift-version','5','-target','arm64-apple-ios18.0-simulator','-sdk',sdk,'-framework','UIKit','-import-objc-header',w/'Memory.h',CLASSES/'MeloNXMemoryGraph.swift',w/'App.swift',w/'Memory.o','-o',app/'Memory')
  run('codesign','--force','--sign','-',app);run('xcrun','simctl','install',device,app);run('xcrun','simctl','launch',device,bundle)
  container=Path(run('xcrun','simctl','get_app_container',device,bundle,'data'))/'Documents'
  deadline=time.monotonic()+30
  while not (container/'memory.json').exists() and time.monotonic()<deadline:time.sleep(.5)
  if not (container/'memory.json').exists():
   print(run('xcrun','simctl','spawn',device,'log','show','--last','2m','--predicate','process == "Memory"')[-12000:]);raise AssertionError('No memory report')
  report=json.loads((container/'memory.json').read_text());assert report['result']=='passed';print(json.dumps(report),flush=True)
  report['inputs']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [CLASSES/'MeloNXMemoryGraph.swift',CLASSES/'MeloNXJitBridgePlugin.mm',Path(__file__)]}
  report['fpsLabelTested']=True
  report['runtime']=runtime
  (OUT/'memory.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'memory.png').write_bytes((container/'memory.png').read_bytes())
finally:
 subprocess.run(['xcrun','simctl','shutdown',device],capture_output=True)
 subprocess.run(['xcrun','simctl','delete',device],capture_output=True)
