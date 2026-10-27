// Only the engine's callback registry, the journal and the string catalogue are
// doubled. UIKit, UIAlertController and MeloNXTextInput.swift are real.
import UIKit

enum MeloNXLaunchJournal {
    static var events: [[String: Any]] = []
    static func record(_ stage: String, _ status: String, code: Int64 = 0, detail: String = "") {
        let event: [String: Any] = ["stage": stage, "status": status, "code": code, "detail": detail]
        if Thread.isMainThread { events.append(event) } else { DispatchQueue.main.async { events.append(event) } }
    }
}
func MeloNXText(_ key: String) -> String { key }

/// Ryujinx.Common.Callbacks.CallbackRegistry as MeloNX's AlertHelper uses it:
/// the native callback is invoked on an engine thread, which then blocks until
/// "show_text_input_result_<id>" is invoked.
enum Engine {
    static let lock = NSLock()
    static var registrations: [String] = []
    static var callback: MeloNXTextInput.Callback?
    static var answers: [(name: String, text: String?)] = []
    static var waiting: [String: DispatchSemaphore] = [:]

    static let register: MeloNXTextInput.Register = { name, callback, _ in
        Engine.lock.lock(); defer { Engine.lock.unlock() }
        Engine.registrations.append(name.map { String(cString: $0) } ?? "")
        Engine.callback = callback.map { unsafeBitCast($0, to: MeloNXTextInput.Callback.self) }
    }
    static let invoke: MeloNXTextInput.Invoke = { name, data, length in
        let label = name.map { String(cString: $0) } ?? ""
        var text: String?
        if let data, length > 0 { text = String(decoding: UnsafeRawBufferPointer(start: data, count: Int(length)), as: UTF8.self) }
        Engine.lock.lock()
        Engine.answers.append((name: label, text: text))
        let semaphore = Engine.waiting.removeValue(forKey: label)
        Engine.lock.unlock()
        semaphore?.signal()
        return semaphore == nil ? 0 : 1
    }

    /// One request from a background thread, like the HLE applet thread.
    static func ask(_ id: String, title: String = "", message: String = "", placeholder: String = "",
                    raw: Data? = nil, unblocked: @escaping (Bool) -> Void = { _ in }) {
        DispatchQueue.global(qos: .userInitiated).async {
            let semaphore = DispatchSemaphore(value: 0)
            lock.lock(); waiting["show_text_input_result_" + id] = semaphore; let callback = Engine.callback; lock.unlock()
            let json = raw ?? (try! JSONSerialization.data(withJSONObject: ["Title": title, "Message": message,
                                                                             "Placeholder": placeholder, "CallbackId": id]))
            json.withUnsafeBytes { buffer in
                var data = MeloNXTextInput.CallbackData(pointer: UnsafeMutableRawPointer(mutating: buffer.baseAddress),
                                                        length: Int32(buffer.count))
                withUnsafeMutableBytes(of: &data) { callback?($0.baseAddress, nil) }
            }
            let answered = semaphore.wait(timeout: .now() + (raw == nil ? 30 : 1)) == .success
            if !answered { lock.lock(); waiting.removeValue(forKey: "show_text_input_result_" + id); lock.unlock() }
            DispatchQueue.main.async { unblocked(answered) }
        }
    }
    static func answer(_ id: String) -> (name: String, text: String?)? {
        lock.lock(); defer { lock.unlock() }
        return answers.last { $0.name == "show_text_input_result_" + id }
    }
}
