import Foundation
import Darwin

/// A process-rooted owner. All acquire/retire calls use the plugin library queue.
/// No destructor unmaps guest memory; a failed native teardown retains the lease.
final class MeloNXMemoryLease {
    static let shared = MeloNXMemoryLease()
    private var region: UnsafeMutableRawPointer?
    private let lock = NSLock()
    private var mappedBytes: UInt64 = 0
    private var state = "off"
    private func update(_ state:String, bytes:UInt64? = nil, why:String = "") {
        lock.lock(); self.state = state
        if let bytes { mappedBytes = bytes }
        let mapped = mappedBytes
        lock.unlock()
        MeloNXLaunchJournal.record("memory",state,detail:"MeloNX donor lease state changed. Mapped bytes: \(mapped)." + (why.isEmpty ? "" : " " + why))
    }
    var isRetained: Bool { lock.lock(); defer { lock.unlock() }; return state == "retained" }
    func snapshot() -> [String:Any] {
        lock.lock(); defer { lock.unlock() }
        return ["donorState":state,"donorMappedBytes":mappedBytes]
    }
    func prepare(runtime:MeloNXRuntimeAPI, enabled:Bool, isCurrent:@escaping()->Bool) throws {
        guard retire(runtime:runtime) else { throw MeloNXHostError.load("Donated guest memory is still owned; restart RewindBox before another session.") }
        guard enabled else { update("off"); return }
        // NeoSwap's donors are RPCS3-session scoped. Never start this manager
        // while that owner is active (including a retained/quarantined session).
        typealias Active = @convention(c)(UInt32)->Int32
        if let handle = dlopen(nil,RTLD_NOW) {
            defer { dlclose(handle) }
            if let symbol = dlsym(handle,"NeoSwap_OwnerSessionActive"),
               unsafeBitCast(symbol,to:Active.self)(0) != 0 { update("busy"); return }
        }
        guard isCurrent() else { update("cancelled"); return }
        guard mlx_ram_donor_is_available() else { update("unavailable"); return }
        update("preparing")
        let donor = MLXRamDonor.shared
        donor.maxDonors = 4
        // Preserve the original donor processes while their memory is borrowed.
        // No claim that terminating a donor removes Apple's accounting limits.
        donor.killDonorsAfterMapping = false
        donor.shouldContinue = isCurrent
        var granted: UInt64 = 0
        let address = mlx_ram_donor_acquire_up_to(4 * 1024 * 1024 * 1024,256 * 1024 * 1024,&granted)
        donor.shouldContinue = nil
        guard let address, granted > 0 else {
            MeloNXLaunchJournal.record("memory","refused",detail:donor.lastError ?? "No mapped donor region returned.")
            if donor.hasOutstandingRegions {
                update("retained")
                throw MeloNXHostError.load("The donor retained an unmapped reservation; restart RewindBox before retrying.")
            }
            mlx_ram_donor_shutdown(); update(isCurrent() ? "fallback" : "cancelled"); return
        }
        region = address; update("mapped",bytes:granted)
        guard isCurrent() else { _ = retire(runtime:runtime); return }
        guard runtime.offerMemory(address,bytes:granted) else {
            guard retire(runtime:runtime) else { throw MeloNXHostError.load("Cannot safely retire rejected donor memory; restart RewindBox.") }
            update("fallback"); return
        }
        update("offered")
    }
    // `reason` names the call in the journal ("retry before a launch"); a refusal says which proof was missing: the
    // engine's state and its donated allocations still live (neostation_melonx_memory_snapshot), or the donor's own
    // bookkeeping.
    @discardableResult func retire(runtime:MeloNXRuntimeAPI, reason:String = "") -> Bool {
        let prefix = reason.isEmpty ? "" : reason + ": "
        guard let region else {
            if MLXRamDonor.shared.hasOutstandingRegions { update("retained",why:prefix + "the donor still holds an unmapped reservation."); return false }
            // A reservation the donor has since given back: nothing of this lease is retained any more.
            if isRetained { update("released",bytes:0,why:prefix + "the donor's reservation was given back.") }
            return true
        }
        guard runtime.withdrawMemory() else {
            let engine = runtime.memorySnapshot()
            update("retained",why:prefix + "the engine refused to withdraw (donated bytes used \(engine["donorUsedBytes"] ?? "-"), live allocations \(engine["donorAllocations"] ?? "-")).")
            return false
        }
        guard MLXRamDonor.shared.releaseRegionChecked(region) else { update("retained",why:prefix + "the donor refused to release the region."); return false }
        self.region = nil
        mlx_ram_donor_shutdown()
        update("released",bytes:0,why:reason.isEmpty ? "" : reason + ".")
        return true
    }
}
