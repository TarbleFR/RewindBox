import Foundation
import JavaScriptCore

let source = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
let fixture = try String(contentsOfFile: CommandLine.arguments[2], encoding: .utf8)
let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[3]))) as! [[String: Any]]
var results = [[String: Any]]()
for options in cases {
    let context = JSContext()!
    var failure: String? = nil
    context.exceptionHandler = { _, value in failure = value?.toString() ?? "JavaScript exception" }
    context.evaluateScript("var neostationProbeNonce = 41;\n" + fixture)
    context.objectForKeyedSubscript("helperTestBegin")!.call(withArguments: [options])
    context.evaluateScript(source)
    let json = context.evaluateScript("JSON.stringify(helperTestState, function(key,value) { return typeof value === 'bigint' ? String(value) : value; })")!.toString()!
    let state = try JSONSerialization.jsonObject(with: Data(json.utf8))
    results.append(["state": state, "error": failure as Any? ?? NSNull()])
}
let encoded = try JSONSerialization.data(withJSONObject: results, options: [.sortedKeys])
print(String(data: encoded, encoding: .utf8)!)
