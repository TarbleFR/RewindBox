import Foundation
import CoreFoundation

/// Resolve on the library worker after native preflight, before session creation.
/// The core independently checks the actual launched title again.
enum MeloNXHogwartsGraphics {
    static let titleID = "0100F7E00C70E000"

    static func boolean(_ value: Any?, default fallback: Bool) -> Bool {
        guard let value else { return fallback }
        guard let number = value as? NSNumber,
              CFGetTypeID(number) == CFBooleanGetTypeID() else { return false }
        return number.boolValue
    }

    static func resolve(_ requested: [String: Any], title: String?) -> [String: Any] {
        var result = requested
        result.removeValue(forKey: "occlusionQuerySync")
        result.removeValue(forKey: "relaxQueryFlushing")
        guard title?.uppercased() == titleID else { return result }
        let sync = boolean(requested["occlusionQuerySync"], default: true)
        result["occlusionQuerySync"] = sync
        result["relaxQueryFlushing"] = sync && boolean(requested["relaxQueryFlushing"], default: true)
        return result
    }

    static func diagnostic(_ effective: [String: Any], title: String?) -> String {
        let applies = title?.uppercased() == titleID
        return "Hogwarts GPU policy: titleMatched=\(applies); occlusionQuerySync=\(effective["occlusionQuerySync"] as? Bool ?? false); relaxQueryFlushing=\(effective["relaxQueryFlushing"] as? Bool ?? false); applies before session creation"
    }

    /// Short identifiers survive the existing journal's secret scrubber.
    /// This is packaged provenance, not an independently hashed loaded image.
    static func provenance(info: [String: Any], identity: [String: Any]) -> String {
        let source = identity["sourceCoreIdentity"] as? [String: Any] ?? [:]
        let commit = (source["host"] as? String).map { String($0.prefix(12)) } ?? "unavailable"
        let core = (source["sha256"] as? String).map { String($0.prefix(12)) } ?? "unavailable"
        return "Application \(info["CFBundleShortVersionString"] as? String ?? "?") (\(info["CFBundleVersion"] as? String ?? "?")); MeloNX source \(commit); original core SHA256 prefix \(core); packaged receipt, not a runtime benchmark"
    }
}
