"""Run the production performance bar (RPCS3's minimal bar: FPS, CPU, RAM, RamDonor) and its samplers in UIKit."""
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
 // The production samplers: the footprint (MeloNXJitBridgePlugin.mm) and the process's CPU time.
 let actual=MeloNXMemoryGraph.processSample();check((actual["footprintBytes"] as? NSNumber)?.uint64Value ?? 0 > 0)
 let cpu0=(actual["processCpuSeconds"] as? NSNumber)?.doubleValue ?? -1
 var spin=0.0;for i in 0..<3_000_000 {spin += Double(i).squareRoot()};check(spin>0)
 let cpu1=MeloNXProcessCPUSeconds() ?? -1;check(cpu0>0 && cpu1>cpu0)
 // RPCS3's minimal bar: 256 x 44, four columns, the value above its caption.
 check(MeloNXMemoryGraph.barSize==CGSize(width:256,height:44))
 let graph=MeloNXMemoryGraph(frame:CGRect(origin:CGPoint(x:20,y:80),size:MeloNXMemoryGraph.barSize))
 graph.numberLocale=Locale(identifier:"en_US_POSIX");graph.processorCount=4
 check(graph.intrinsicContentSize==MeloNXMemoryGraph.barSize && !graph.isUserInteractionEnabled)
 check(graph.captionTexts==["FPS","CPU","RAM","RamDonor"])
 check(graph.accessibilityLabel=="RSwitch Performance" && graph.accessibilityIdentifier=="melonx.performance.overlay")
 // Before the first sample nothing is invented.
 check([graph.fpsText,graph.cpuText,graph.ramText,graph.donorText]==["—","—","—","—"])
 check(graph.accessibilityValue=="FPS —. CPU —. App RAM: —. RamDonor lent: —")
 var samples=0
 var fps:Any?=59.94 // MeloNXRuntimeAPI.performanceSnapshot reports a Swift Double
 var donor:Any?=UInt64(3072)*1048576 // MeloNXRuntimeAPI.memorySnapshot reports a Swift UInt64
 var cpuTotal=100.0,cpuStep=1.0,cpuMissing=false
 graph.now = { Double(samples)/2 }
 graph.sample = {samples += 1;cpuTotal += cpuStep;var values:[String:Any]=["footprintBytes":NSNumber(value:UInt64(512+samples*2)*1048576),"availableBytes":NSNumber(value:UInt64(768)*1048576),"donorMappedBytes":NSNumber(value:UInt64(4096)*1048576),"donorState":"offered"];values["gameFps"]=fps;values["donorUsedBytes"]=donor;if !cpuMissing {values["processCpuSeconds"]=cpuTotal};return values}
 view.view.addSubview(graph);graph.setSampling(true);check(graph.isSampling && samples==1)
 // One sample: no CPU interval yet. 514 MiB footprint and 3072 MiB lent, decimal GB.
 check(graph.fpsText=="59.9" && graph.cpuText=="—" && graph.ramText=="0.54 GB" && graph.donorText=="3.22 GB")
 graph.setSampling(true);check(samples==1)
 for _ in 0..<120 {graph.observe()};check(samples==121)
 // 1 s of CPU time per 0.5 s on 4 cores: 50 %.
 check(graph.fpsText=="59.9" && graph.cpuText=="50%" && graph.ramText=="0.79 GB" && graph.donorText=="3.22 GB")
 check(graph.accessibilityValue=="FPS 59.9. CPU 50%. App RAM: 0.79 GB. RamDonor lent: 3.22 GB")
 cpuStep=5;graph.observe();check(graph.cpuText=="100%")
 // A CPU time that goes back or is missing is no interval; the next valid pair is.
 cpuStep=(-10);graph.observe();check(graph.cpuText=="—")
 cpuStep=0.5;graph.observe();check(graph.cpuText=="25%")
 cpuMissing=true;graph.observe();check(graph.cpuText=="—")
 cpuMissing=false;graph.observe();check(graph.cpuText=="—")
 graph.observe();check(graph.cpuText=="25%" && samples==127)
 // No live session (or an older engine): "—", never a stale value. Zero is a stalled-frame sample.
 fps=nil;graph.observe();check(graph.fpsText=="—" && graph.accessibilityValue?.hasPrefix("FPS —. CPU 25%.")==true)
 fps=29.97;graph.observe();check(graph.fpsText=="30.0")
 fps=0.0;graph.observe();check(graph.fpsText=="0.0")
 fps=Double.nan;graph.observe();check(graph.fpsText=="—")
 fps=(-1.0);graph.observe();check(graph.fpsText=="—")
 // The session's language sets the decimal separator (MeloNXStrings.locale in the controller).
 graph.numberLocale=Locale(identifier:"fr");fps=59.94;graph.observe()
 check(graph.fpsText=="59,9" && graph.ramText=="0,82 GB")
 donor=nil;graph.observe();check(graph.donorText=="—" && graph.ramText=="0,82 GB")
 graph.numberLocale=Locale(identifier:"en_US_POSIX");donor=UInt64(3072)*1048576;graph.observe()
 check(graph.donorText=="3.22 GB" && graph.ramText=="0.82 GB" && samples==135)
 graph.setSampling(false);check(!graph.isSampling)
 // Sampling again starts a new CPU interval: a pause is never averaged in.
 graph.setSampling(true);check(graph.isSampling && samples==136 && graph.cpuText=="—" && graph.fpsText=="59.9")
 graph.setSampling(false);check(!graph.isSampling)
 graph.layoutIfNeeded()
 for label in graph.subviews {label.layer.displayIfNeeded()}
 let format=UIGraphicsImageRendererFormat();format.scale=3;format.preferredRange = .standard
 let image=UIGraphicsImageRenderer(bounds:graph.bounds,format:format).image {graph.layer.render(in:$0.cgContext)}
 let root=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
 try! image.pngData()!.write(to:root.appendingPathComponent("memory.png"))
 // The RAM caption is orange and the RamDonor caption green, in their own columns of the caption row
 // (rows 26-38 pt; read the other way up they would be the white value row).
 let flat=image.cgImage!
 let width=flat.width
 let height=flat.height
 check(width==768 && height==132)
 var pixels=[UInt8](repeating:0,count:width*height*4)
 pixels.withUnsafeMutableBytes { raw in
  let context=CGContext(data:raw.baseAddress,width:width,height:height,bitsPerComponent:8,bytesPerRow:width*4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
  context.draw(flat,in:CGRect(x:0,y:0,width:width,height:height))
 }
 func colored(_ columns:Range<Int>,_ match:(Int,Int,Int)->Bool)->Int {
  var found=0
  for y in 78..<114 {for x in columns {let i=(y*width+x)*4;if match(Int(pixels[i]),Int(pixels[i+1]),Int(pixels[i+2])) {found += 1}}}
  return found
 }
 let orange={(r:Int,g:Int,b:Int) in r>180 && g>90 && g<190 && b<80 && r-g>50}
 let green={(r:Int,g:Int,b:Int) in g>140 && r<120 && b<150 && g-r>60}
 // Columns at 3x: FPS 24-168, CPU 168-312, RAM 312-528, RamDonor 528-744.
 let ramOrange=colored(312..<528,orange),donorGreen=colored(528..<744,green)
 check(ramOrange>=10 && donorGreen>=10 && colored(24..<312,orange)==0 && colored(24..<312,green)==0)
 weak var released:MeloNXMemoryGraph?
 autoreleasepool {let temporary=MeloNXMemoryGraph();temporary.setSampling(true);released=temporary}
 check(released==nil)
 DispatchQueue.main.asyncAfter(deadline:.now()+0.7){
  check(samples==136)
  let report:[String:Any] = ["result":"passed","cases":count,"actualFootprintBytes":actual["footprintBytes"]!,"captionOrangePixels":ramOrange,"captionGreenPixels":donorGreen,"gameplayTested":false]
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
  report['cpuLabelTested']=True
  report['runtime']=runtime
  (OUT/'memory.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'memory.png').write_bytes((container/'memory.png').read_bytes())
finally:
 subprocess.run(['xcrun','simctl','shutdown',device],capture_output=True)
 subprocess.run(['xcrun','simctl','delete',device],capture_output=True)
