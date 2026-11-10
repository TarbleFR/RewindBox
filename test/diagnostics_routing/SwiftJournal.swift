import Foundation
import Darwin

let root = URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
let directory = root.appendingPathComponent("Diagnostics/Switch",isDirectory:true)
let legacy = root.appendingPathComponent("app.log")
try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
try Data("legacy sentinel\n".utf8).write(to:legacy)
var checks = 0
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else { fatalError(message) }; checks += 1
}
func contents(_ url: URL) -> String { (try? String(contentsOf:url,encoding:.utf8)) ?? "" }
func waitFor(_ message:String,_ condition:()->Bool) {
    for _ in 0..<150 { if condition() { checks += 1; return }; usleep(20_000) }
    fatalError(message)
}
MeloNXLaunchJournal.configure(path:legacy.path)
MeloNXStdioCapture.configure(path:legacy.path)
try MeloNXLaunchJournal.configureDiagnostics(directory:directory)
try MeloNXStdioCapture.configureDiagnostics(directory:directory)
check(MeloNXStdioCapture.coreJournalPath == directory.appendingPathComponent("MeloNX-core.log").path,"core route")
check(MeloNXStdioCapture.journalPath == directory.appendingPathComponent("MeloNX-performance.log").path,"performance route")
let launch = directory.appendingPathComponent("MeloNX-launch.log")
try Data(repeating:0x78,count:5 * 1024 * 1024).write(to:launch)
MeloNXLaunchJournal.record("fixture","passed",detail:"new launch")
check(contents(launch).contains("new launch"),"launch current")
check(contents(URL(fileURLWithPath:launch.path + ".previous")).utf8.count == 5 * 1024 * 1024,"launch rotation")

let coreHash = String(repeating:"a",count:64)
MeloNXStdioCapture.prepareSession(titleID:"0100AAAA00000000",info:["CFBundleVersion":"606","CFBundleShortVersionString":"0.0.8"],
    identity:["sourceCoreIdentity":["host":"core606-source","sha256":coreHash]])
let first = MeloNXStdioCapture.sessionContext
MeloNXStdioCapture.bindGeneration(7,context:first)
let performance = directory.appendingPathComponent("MeloNX-performance.log")
for index in 0..<12 {
    let row = MeloNXStdioCapture.contextualLine("[MeloNX:perf] sample \(index) é",context:MeloNXStdioCapture.context(generation:7))
    check(MeloNXStdioCapture.appendLine(row,to:performance.path,limit:1024),"performance append")
}
for url in [performance,URL(fileURLWithPath:performance.path + ".previous")] {
    let data = try Data(contentsOf:url)
    check(data.count <= 1024,"performance cap")
    check(String(data:data,encoding:.utf8) != nil,"complete UTF8")
    for row in contents(url).split(separator:"\n") {
        let json = String(row).components(separatedBy:" context=").last!
        let context = try JSONSerialization.jsonObject(with:Data(json.utf8)) as! [String:String]
        check(context["titleId"] == "0100AAAA00000000" && context["generation"] == "7","generation provenance")
        check(context["coreSHA256"] == coreHash && context["coreSource"] == "core606-source","Core provenance")
        check(context["build"] == "606" && context["pid"] == String(getpid()) && context["timestamp"]?.hasSuffix("Z") == true,"build/process/time provenance")
    }
}
check(!MeloNXStdioCapture.appendLine(String(repeating:"é",count:1024),to:performance.path,limit:1024),"oversized row refused")

// Hold the actual shared writer before capture starts. The pump blocks in its
// initial append; a >pipe-capacity stdio write then blocks while holding FILE's
// lock. end() owns capture's lock and waits in fflush. Releasing appendLock
// must allow pump -> writer -> end to finish; append taking capture's lock
// creates the former deadlock. The outer runner also enforces a timeout.
MeloNXStdioCapture.fixtureHoldAppend()
MeloNXStdioCapture.begin()
let writerStarted = DispatchSemaphore(value:0), writerDone = DispatchSemaphore(value:0), endDone = DispatchSemaphore(value:0)
DispatchQueue.global().async {
    writerStarted.signal()
    fputs(String(repeating:"pipe pressure line\n",count:20_000),stderr)
    writerDone.signal()
}
check(writerStarted.wait(timeout:.now()+2) == .success,"writer started")
usleep(100_000)
DispatchQueue.global().async { MeloNXStdioCapture.end(); endDone.signal() }
usleep(100_000)
MeloNXStdioCapture.prepareSession(titleID:"0100BBBB00000000",info:["CFBundleVersion":"607"],identity:[:])
MeloNXStdioCapture.bindGeneration(8,context:MeloNXStdioCapture.sessionContext)
MeloNXStdioCapture.fixtureReleaseAppend()
check(writerDone.wait(timeout:.now()+5) == .success,"full-pipe writer drained")
check(endDone.wait(timeout:.now()+5) == .success,"concurrent end completed")
let stderrLog = directory.appendingPathComponent("MeloNX-stderr.log")
waitFor("capture drained") { contents(stderrLog).contains("capture end") }
check(!contents(stderrLog).contains("0100BBBB00000000"),"old pump retains immutable context")
check(contents(stderrLog).contains("0100AAAA00000000"),"old pump has original context")
check(MeloNXStdioCapture.context(generation:7)["titleId"] == first["titleId"],"old generation retained")
check(MeloNXStdioCapture.context(generation:123)["context"] == "unavailable","unknown generation never borrows new context")

try FileManager.default.removeItem(at:stderrLog)
MeloNXStdioCapture.begin()
for _ in 0..<1000 { fputs("[mvk-warn] identical warning\n",stderr) }
fputs("[mvk-error] VK_ERROR_DEVICE_LOST late unique\n",stderr)
MeloNXStdioCapture.end()
waitFor("driver capture drained") { contents(stderrLog).contains("capture end") }
let driverLog = contents(stderrLog)
check(driverLog.contains("driver repeated total 999"),"driver repeat count")
check(driverLog.contains("VK_ERROR_DEVICE_LOST late unique"),"late unique error preserved")
check(driverLog.split(separator:"\n").count < 20,"driver flood bounded")
check(driverLog.contains("0100BBBB00000000") && !driverLog.contains("0100AAAA00000000"),"new capture context")
check(contents(legacy) == "legacy sentinel\n","legacy remains byte-for-byte")

RunLoop.main.run(until:Date().addingTimeInterval(0.05))
var relayed = [[String:Any]]()
MeloNXLaunchJournal.sink = { relayed.append($0) }
for (stage,status) in [("engine","info"),("performance","sample"),("memory","retained"),("gpu","failed")] {
    MeloNXLaunchJournal.relayCore(["stage":stage,"status":status])
}
RunLoop.main.run(until:Date().addingTimeInterval(0.1))
check(relayed.count == 2 && relayed.allSatisfy { ["retained","failed"].contains($0["status"] as? String ?? "") },"only critical native relays")
print(String(data:try JSONSerialization.data(withJSONObject:["result":"passed","checks":checks,
    "actualProductionSwift":true,"fullPipeConcurrentEnd":true,"immutableContext":true],options:[.sortedKeys]),encoding:.utf8)!)
