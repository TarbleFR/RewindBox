// Only engine/JIT/guest boundaries are doubled. UIKit and Flutter's Objective-C
// framework, the production registrar code and presentation resolver are real.
import Flutter
import UIKit

enum Probe {
    static var detachCalls=0; static var handshakes=0; static var starts=0
    private static let lock=NSLock()
    private static var report:[String:Any] = ["events":[]]
    private static var polls=0
    private static var journal=""
    static func setReport(_ value:[String:Any]) { lock.lock(); report=value; lock.unlock() }
    static func snapshot()->[String:Any] { lock.lock(); defer {lock.unlock()}; polls += 1; return report }
    static var pollCount:Int { lock.lock(); defer {lock.unlock()}; return polls }
    static func setJournal(_ path:String) { lock.lock(); journal=path; lock.unlock() }
    static var journalPath:String { lock.lock(); defer {lock.unlock()}; return journal }
    static func finalPerformance() {
        lock.lock(); defer {lock.unlock()}
        guard let previous=report["performance"] as? [String:Any],previous["status"] as? String == "sample" else {return}
        var final=previous;final["sequence"]=102;final["status"]="final"
        report["precedingPerformance"]=previous;report["performance"]=final
    }
}
func MeloNXMemoryEntitlements() -> [String:Any] { ["allowed":true] }
func MeloNXJitHasActiveCoreHandshake() -> Bool { true }
func MeloNXJitConfirmCoreLoadHandoff() -> Bool { Probe.handshakes += 1; return true }
func MeloNXJitExecutableMappingProbe() -> [String:Any] { ["success":true] }
func MeloNXJitWaitForDetach(_ timeout: Double, _ message: inout NSString?) -> Bool {
    Probe.detachCalls += 1
    // A second helper cannot observe a one-time arena initialization again.
    return Probe.detachCalls == 1
}
func MeloNXJitAbortTransaction() {}
enum MeloNXJitBridgePlugin { static func register(with registrar: FlutterPluginRegistrar) {} }
enum MeloNXStrings { static var locale="en" }
enum MeloNXLaunchJournal {
    static var sink: (([String:Any])->Void)?
    static func configure(path:String) {}
    static func configureDiagnostics(directory:URL) throws {}
    static func relayCore(_ event:[String:Any]) {}
    static func record(_ stage:String,_ status:String,code:Int64=0,detail:String="") {}
}
enum MeloNXHostError: Error {
    case load(String), prepare(Int64,String), run(Int32,String), operation(String,Int64,String)
    var description:String { String(describing:self) }
}
final class SessionAPI {}
final class MeloNXRuntimeAPI {
    let session=SessionAPI()
    init(library:URL,frameworks:URL,root:URL,moltenVk:Int32=0) throws {}
    func content(path:String="",operation:Int32) throws -> [String:Any] {
        if operation == 9 { Probe.setJournal(path) }
        return operation == 8 ? ["success":true,"titleId":"0100AAAA00000000"] : ["success":true]
    }
    func diagnostics() -> [String:Any] { Probe.snapshot() }
    func contentProgress() -> Int32 { 0 }
    func cancelContent() {}
    func prepareGraphics(_ settings:[String:Any],universalJit:Bool) throws {}
    func prepareJit() throws {}
}
final class MeloNXSessionHost {
    var isSessionActive=false
    init(api:SessionAPI) {}
}
final class MeloNXMetalSessionViewController:UIViewController {
    let host:MeloNXSessionHost
    let beforeRun:()->Bool
    let firstFrame:()->Void
    let finished:(Result<Void,MeloNXHostError>)->Void
    init(host:MeloNXSessionHost,game:URL,locale:String,runtime:MeloNXRuntimeAPI,titleID:String?,settings:[String:Any] = [:],
         saveSettings:@escaping([String:Any],@escaping(Bool)->Void)->Void = {_,done in done(false)},
         beforeRun:@escaping()->Bool,firstFrame:@escaping()->Void,
         finished:@escaping(Result<Void,MeloNXHostError>)->Void) {
        self.host=host;self.beforeRun=beforeRun;self.firstFrame=firstFrame;self.finished=finished
        super.init(nibName:nil,bundle:nil);modalPresentationStyle = .fullScreen
    }
    required init?(coder:NSCoder) { fatalError() }
    override func viewDidAppear(_ animated:Bool) {
        super.viewDidAppear(animated)
        guard beforeRun() else { return }
        Probe.starts += 1;host.isSessionActive=true
        // The real controller binds in SessionHost.prepared before native run.
        // This explicit session double exposes the same generation boundary.
        MeloNXStdioCapture.bindGeneration(Int64(Probe.starts),context:MeloNXStdioCapture.sessionContext)
        // Explicit guest-frame double, not a graphics/gameplay claim.
        firstFrame()
    }
    func requestClose() {
        Probe.finalPerformance()
        host.isSessionActive=false
        dismiss(animated:false) { self.finished(.success(())) }
    }
}

final class MeloNXMemoryLease {
    static let shared=MeloNXMemoryLease()
    var retained=false
    func snapshot()->[String:Any] { ["donorState":retained ? "retained":"off"] }
    func prepare(runtime:MeloNXRuntimeAPI,enabled:Bool,isCurrent:@escaping()->Bool) throws {
        if retained {throw MeloNXHostError.load("Retained donor reservation fixture")}
    }
    func retire(runtime:MeloNXRuntimeAPI)->Bool {true}
}
