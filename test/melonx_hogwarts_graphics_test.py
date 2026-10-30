#!/usr/bin/env python3
"""Execute the actual Swift host policy on Apple; no GPU benchmark is claimed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--require-native',action='store_true');args=p.parse_args()
source=ROOT/'packages/melonx_internal_bridge/ios/Classes/MeloNXHogwartsGraphics.swift'
plugin=ROOT/'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift'
launch=plugin.read_text().split('private func launch(',1)[1]
assert launch.index('let preflight = try runtime.content') < launch.index('MeloNXHogwartsGraphics.resolve') < launch.index('try runtime.prepareGraphics(settings') < launch.index('try runtime.prepareJit(')
assert 'title:titleID' in launch and 'settings:settings' in launch
assert 'MeloNX-native-identity' in launch and '"provenance","packaged"' in launch
locale=(ROOT/'lib/l10n/melonx_library_locale.dart').read_text()
for label in ['Synchronize occlusion results','Group GPU query submissions','Hogwarts GPU options apply on the next launch. Disable them here to compare.']:
    assert locale.count(json.dumps(label)+':')==11,label
checks=None
if shutil.which('xcrun'):
    with tempfile.TemporaryDirectory(prefix='hogwarts-policy-') as d:
        work=Path(d)
        (work/'main.swift').write_text(r'''import Foundation
import CoreFoundation
var checks=0
func check(_ condition: @autoclosure () -> Bool) { checks += 1; precondition(condition(), "check \(checks)") }
let title=MeloNXHogwartsGraphics.titleID
let values: [Any?] = [nil, true, false, NSNumber(value:0), NSNumber(value:1), "true", NSNull(), ["x":true]]
func expected(_ v: Any?) -> Bool {
 guard let v else { return true }
 guard let n=v as? NSNumber, CFGetTypeID(n)==CFBooleanGetTypeID() else { return false }
 return n.boolValue
}
let titles: [String?] = [title, title.lowercased(), "01006A800016E000", nil, "", "Hogwarts Legacy", title + "0"]
for id in titles { for sync in values { for batch in values {
 var requested: [String:Any] = ["resolution":0.75,"asyncShaders":false,"donateMemory":true,"shaderCache":true]
 if let sync { requested["occlusionQuerySync"]=sync }
 if let batch { requested["relaxQueryFlushing"]=batch }
 let effective=MeloNXHogwartsGraphics.resolve(requested,title:id)
 if id?.uppercased()==title {
  check(effective["occlusionQuerySync"] as? Bool == expected(sync))
  check(effective["relaxQueryFlushing"] as? Bool == (expected(sync) && expected(batch)))
 } else {
  check(effective["occlusionQuerySync"]==nil)
  check(effective["relaxQueryFlushing"]==nil)
 }
 check(effective["resolution"] as? Double == 0.75)
 check(effective["asyncShaders"] as? Bool == false)
 check(effective["donateMemory"] as? Bool == true)
 check(effective["shaderCache"] as? Bool == true)
 check(requested["resolution"] as? Double == 0.75)
}}}
let decoded=try! JSONSerialization.jsonObject(with:Data("{\"occlusionQuerySync\":false,\"relaxQueryFlushing\":true}".utf8)) as! [String:Any]
let disabled=MeloNXHogwartsGraphics.resolve(decoded,title:title)
check(disabled["occlusionQuerySync"] as? Bool == false)
check(disabled["relaxQueryFlushing"] as? Bool == false)
for _ in 0..<100 {
 check(MeloNXHogwartsGraphics.resolve([:],title:title)["relaxQueryFlushing"] as? Bool == true)
 check(MeloNXHogwartsGraphics.resolve([:],title:nil)["relaxQueryFlushing"]==nil)
}
let detail=MeloNXHogwartsGraphics.provenance(info:["CFBundleShortVersionString":"0.0.8","CFBundleVersion":"599"],identity:["sourceCoreIdentity":["host":"e7143e566462bf6e3d9c143ce24532c1ad7aeb10","sha256":"b0bb4cd7da18337fd66eedec218df4a783efeff38f7c412cef2a00be813f41e6"]])
check(detail.contains("0.0.8 (599)") && detail.contains("e7143e566462") && detail.contains("b0bb4cd7da18"))
let safe=detail.replacingOccurrences(of:"(?i)\\b[0-9a-f]{32,}\\b",with:"[redacted]",options:.regularExpression)
 .replacingOccurrences(of:"(?im)^\\s*[a-z0-9_]+\\s*=\\s*[^\\r\\n]+",with:"[redacted key entry]",options:.regularExpression)
check(safe==detail)
check(MeloNXHogwartsGraphics.provenance(info:[:],identity:[:]).contains("unavailable"))
let config=MeloNXHogwartsGraphics.diagnostic(disabled,title:title)
check(config.contains("titleMatched=true") && config.contains("occlusionQuerySync=false") && config.contains("relaxQueryFlushing=false"))
print(checks)
''')
        subprocess.run(['xcrun','swiftc','-swift-version','5',str(source),str(work/'main.swift'),'-o',str(work/'probe')],check=True)
        checks=int(subprocess.check_output([str(work/'probe')],text=True).strip())
elif args.require_native:
    raise RuntimeError('Apple Swift execution required')
report=dict(result='passed',swiftExecuted=checks is not None,swiftChecks=checks,sourceScopeOnly=checks is None,gameplayMeasured=False,coreRebuilt=False,
            inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [source,plugin,Path(__file__)]})
out=ROOT/'build/delivery/hogwarts599-policy-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
