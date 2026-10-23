"""Execute the actual Swift donor owner with deterministic Core/IPC fault doubles."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'packages/melonx_internal_bridge/ios/Classes/MeloNXMemoryLease.swift'
with tempfile.TemporaryDirectory(prefix='melonx-lease-') as d:
 w=Path(d)
 (w/'Doubles.swift').write_text('''import Foundation
class MeloNXRuntimeAPI {
 var offer=true, withdraw=true, offers=0, withdrawals=0
 func offerMemory(_ p:UnsafeMutableRawPointer,bytes:UInt64)->Bool {offers += 1;return offer}
 func withdrawMemory()->Bool {withdrawals += 1;return withdraw}
}
enum MeloNXHostError:Error {case load(String)}
enum MeloNXLaunchJournal {static func record(_ a:String,_ b:String,detail:String){}}
class MLXRamDonor {
 static let shared=MLXRamDonor()
 var maxDonors=0,killDonorsAfterMapping=true,hasOutstandingRegions=false
 var shouldContinue:(()->Bool)?
 var release=true,available=true,supply=true,leak=false,acquisitions=0,releases=0,shutdowns=0
 func releaseRegionChecked(_ p:UnsafeMutableRawPointer)->Bool {
  releases += 1;if release {hasOutstandingRegions=false};return release
 }
}
func mlx_ram_donor_is_available()->Bool {MLXRamDonor.shared.available}
func mlx_ram_donor_acquire_up_to(_ size:UInt64,_ minimum:UInt64,_ actual:inout UInt64)->UnsafeMutableRawPointer? {
 let d=MLXRamDonor.shared;d.acquisitions += 1
 if !d.supply {d.hasOutstandingRegions=d.leak;return nil}
 actual=minimum;d.hasOutstandingRegions=true
 return UnsafeMutableRawPointer(bitPattern:0x100000)
}
func mlx_ram_donor_shutdown(){MLXRamDonor.shared.shutdowns += 1}
''')
 (w/'main.swift').write_text('''import Foundation
var cases=0
func check(_ condition:Bool){precondition(condition,"lease assertion \\(cases)");cases += 1}
let d=MLXRamDonor.shared, core=MeloNXRuntimeAPI(), lease=MeloNXMemoryLease()
func state()->String {lease.snapshot()["donorState"] as! String}
try lease.prepare(runtime:core,enabled:false,isCurrent:{true});check(state()=="off" && d.acquisitions==0)
try lease.prepare(runtime:core,enabled:true,isCurrent:{false});check(state()=="cancelled" && core.offers==0)
d.available=false
try lease.prepare(runtime:core,enabled:true,isCurrent:{true});check(state()=="unavailable" && core.offers==0)
d.available=true;d.supply=false
try lease.prepare(runtime:core,enabled:true,isCurrent:{true});check(state()=="fallback" && core.offers==0)
d.supply=true;core.offer=false
try lease.prepare(runtime:core,enabled:true,isCurrent:{true});check(state()=="fallback" && d.releases==1 && !d.hasOutstandingRegions)
core.offer=true
try lease.prepare(runtime:core,enabled:true,isCurrent:{true})
check(state()=="offered" && !d.killDonorsAfterMapping && d.maxDonors==4)
check(lease.snapshot()["donorMappedBytes"] as! UInt64 == 256*1024*1024)
core.withdraw=false
let released=d.releases, acquired=d.acquisitions
check(!lease.retire(runtime:core) && state()=="retained" && d.releases==released)
do {try lease.prepare(runtime:core,enabled:true,isCurrent:{true});fatalError("replaced live loan")} catch {cases += 1}
check(d.acquisitions==acquired)
core.withdraw=true;d.release=false
check(!lease.retire(runtime:core) && state()=="retained" && d.hasOutstandingRegions)
d.release=true
check(lease.retire(runtime:core) && state()=="released" && !d.hasOutstandingRegions)
var calls=0
try lease.prepare(runtime:core,enabled:true,isCurrent:{calls += 1;return calls==1})
check(state()=="released" && !d.hasOutstandingRegions)
try lease.prepare(runtime:core,enabled:true,isCurrent:{true});check(state()=="offered")
check(lease.retire(runtime:core))
d.supply=false;d.leak=true
do {try lease.prepare(runtime:core,enabled:true,isCurrent:{true});fatalError("lost reservation")} catch {cases += 1}
check(state()=="retained" && !lease.retire(runtime:core))
print("PASS \\(cases) production lease cases; Core and donor IPC doubles, no physical loan claim.")
''')
 subprocess.run(['xcrun','swiftc','-swift-version','5',str(source),str(w/'Doubles.swift'),str(w/'main.swift'),'-o',str(w/'lease')],check=True)
 result=subprocess.check_output([str(w/'lease')],text=True);print(result)
 out=ROOT/'dist/melonx-host/lease.json';out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(dict(result='passed',summary=result,inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,Path(__file__)]},actualDonorTested=False),indent=2)+'\n')
