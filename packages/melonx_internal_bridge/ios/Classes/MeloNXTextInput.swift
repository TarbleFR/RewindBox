import UIKit

/// Text the guest asks the player for: the Switch software keyboard applet,
/// its inline variant and an amiibo's name. MeloNX's managed AlertHelper
/// (Ryujinx.Library) sends a "show_text_input" request through the engine's
/// callback registry, then blocks the requesting HLE thread until
/// "show_text_input_result_<CallbackId>" is invoked. The standalone app
/// registers that callback (AlertHandlers.swift); RewindBox did not, so the
/// request was never answered and the game waited on its keyboard forever.
///
/// Every request is answered exactly once: with the text, or empty (Cancel,
/// no session to show it on, or the session closing). The engine replaces an
/// empty answer with the applet's initial text, as in the standalone app.
/// Entered text is never written to the journal. Main thread only, except the
/// C callback, which copies the request and hands it to the main queue.
final class MeloNXTextInput {
    typealias Register = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, UnsafeMutableRawPointer?) -> Void
    typealias Invoke = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, Int32) -> UInt8
    typealias Callback = @convention(c) (UnsafeMutableRawPointer?, UnsafeMutableRawPointer?) -> Void
    /// What the callback's first argument points to: Ryujinx.Common.Callbacks.
    /// CallbackData { nint Ptr; int Len }, passed by reference.
    struct CallbackData { var pointer: UnsafeMutableRawPointer?; var length: Int32 }
    /// AlertHelper.TextInputRequest, serialized with its property names.
    struct Request: Decodable {
        let title: String, message: String, placeholder: String, callbackId: String
        enum CodingKeys: String, CodingKey {
            case title = "Title", message = "Message", placeholder = "Placeholder", callbackId = "CallbackId"
        }
    }
    static let requestName = "show_text_input"
    static let shared = MeloNXTextInput()

    private var invoke: Invoke?
    private var registered = false
    private weak var presenter: UIViewController?
    private var queue: [Request] = []
    private var shown: Request?
    private weak var alert: UIAlertController?
    private var retryScheduled = false

    /// Called by the engine on its own thread; the request bytes are only valid
    /// during the call.
    static let callback: Callback = { data, _ in
        guard let data else { return }
        let value = data.load(as: CallbackData.self)
        guard let pointer = value.pointer, value.length > 0 else { return }
        let bytes = Data(bytes: pointer, count: Int(value.length))
        guard let request = try? JSONDecoder().decode(Request.self, from: bytes), !request.callbackId.isEmpty else {
            MeloNXLaunchJournal.record("textInput", "invalidRequest", detail: "Unreadable keyboard request; the guest keeps waiting.")
            return
        }
        DispatchQueue.main.async { MeloNXTextInput.shared.enqueue(request) }
    }

    /// Registers the callback once per process (the registry is process-wide)
    /// and shows the requests of this session over `presenter`.
    func attach(register: Register?, invoke: Invoke?, presenter: UIViewController) {
        guard let register, let invoke else {
            MeloNXLaunchJournal.record("textInput", "unavailable", detail: "This engine has no callback registry; games cannot ask for text.")
            return
        }
        self.invoke = invoke
        self.presenter = presenter
        if !registered {
            Self.requestName.withCString { register($0, unsafeBitCast(Self.callback, to: UnsafeRawPointer.self), nil) }
            registered = true
        }
        showNext()
    }

    /// The session ends: answer everything still waiting so no guest thread
    /// stays blocked, and remove the keyboard. Another session's presenter is
    /// left alone.
    func detach(_ owner: UIViewController?) {
        // An identity, not a reference: the owner may be in its deinit.
        release(owner.map { ObjectIdentifier($0) })
    }
    private func release(_ owner: ObjectIdentifier?) {
        if !Thread.isMainThread { DispatchQueue.main.async { self.release(owner) }; return }
        if let presenter, ObjectIdentifier(presenter) != owner { return }
        presenter = nil
        let waiting = queue
        queue.removeAll(); shown = nil
        alert?.dismiss(animated: false)
        alert = nil
        for request in waiting { answer(request, text: nil, status: "cancelled") }
    }

    private func enqueue(_ request: Request) {
        MeloNXLaunchJournal.record("textInput", "requested", detail: "The game asks for text.")
        guard presenter != nil else { answer(request, text: nil, status: "noSession"); return }
        queue.append(request)
        showNext()
    }

    private func showNext() {
        guard shown == nil, let request = queue.first else { return }
        guard let presenter else { release(nil); return }
        guard presenter.viewIfLoaded?.window != nil else { retryLater(); return }
        // Wait for the in-game menu or an editor to close; never stack on them.
        if presenter.presentedViewController != nil { retryLater(); return }
        let alert = UIAlertController(title: request.title.isEmpty ? MeloNXText("Text input") : request.title,
                                      message: request.message.isEmpty ? nil : request.message, preferredStyle: .alert)
        alert.addTextField { field in
            field.placeholder = request.placeholder
            field.autocorrectionType = .no
            field.returnKeyType = .done
        }
        alert.addAction(UIAlertAction(title: MeloNXText("Cancel"), style: .cancel) { [weak self] _ in
            self?.finish(request.callbackId, text: nil)
        })
        let ok = UIAlertAction(title: MeloNXText("OK"), style: .default) { [weak self, weak alert] _ in
            self?.finish(request.callbackId, text: alert?.textFields?.first?.text ?? "")
        }
        alert.addAction(ok)
        alert.preferredAction = ok
        shown = request
        self.alert = alert
        presenter.present(alert, animated: true)
    }

    private func retryLater() {
        guard !retryScheduled else { return }
        retryScheduled = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            self?.retryScheduled = false
            self?.showNext()
        }
    }

    private func finish(_ callbackId: String, text: String?) {
        guard let request = shown, request.callbackId == callbackId else { return }
        shown = nil; alert = nil
        queue.removeAll { $0.callbackId == callbackId }
        answer(request, text: text, status: text == nil ? "cancelled" : "answered")
        showNext()
    }

    private func answer(_ request: Request, text: String?, status: String) {
        guard let invoke else { return }
        let name = Self.requestName + "_result_" + request.callbackId
        let bytes = Array((text ?? "").utf8)
        let delivered = name.withCString { label in
            bytes.withUnsafeBytes { buffer in invoke(label, bytes.isEmpty ? nil : buffer.baseAddress, Int32(bytes.count)) }
        }
        let detail = text.map { "Text entered (\($0.count) characters)." } ?? "Empty answer: the game keeps its initial text."
        MeloNXLaunchJournal.record("textInput", status, code: Int64(delivered), detail: detail)
    }
}
