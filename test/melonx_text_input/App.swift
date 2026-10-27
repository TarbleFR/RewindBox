import UIKit

@main final class ProbeApp: UIResponder, UIApplicationDelegate {
    func application(_ app: UIApplication, configurationForConnecting session: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Probe", sessionRole: session.role)
        configuration.delegateClass = ProbeScene.self; return configuration
    }
}

enum ProbeFailure: Error { case check(String), timeout(String) }

final class ProbeScene: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    var started = false
    var checks = 0

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        window = UIWindow(windowScene: scene)
        window?.rootViewController = UIViewController()
        window?.rootViewController?.view.backgroundColor = .black
        window?.makeKeyAndVisible()
    }
    func sceneDidBecomeActive(_ scene: UIScene) {
        guard !started else { return }; started = true
        Task { @MainActor in
            var report: [String: Any]
            do { report = try await self.run(); report["result"] = "passed" }
            catch { report = ["result": "failed", "error": String(describing: error)] }
            report["checks"] = self.checks
            report["journal"] = MeloNXLaunchJournal.events
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let data = try! JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            try! data.write(to: documents.appendingPathComponent("textinput.json"), options: .atomic)
        }
    }

    @MainActor func check(_ value: Bool, _ message: String) throws {
        guard value else { throw ProbeFailure.check(message) }; checks += 1
    }
    @MainActor func until(_ what: String, timeout: Double = 10, _ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            if Date() > deadline { throw ProbeFailure.timeout(what) }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
    }
    /// The alert this probe expects on top of the session view.
    @MainActor func alert(on root: UIViewController) -> UIAlertController? {
        guard let alert = root.presentedViewController as? UIAlertController, !alert.isBeingDismissed,
              alert.viewIfLoaded?.window != nil else { return nil }
        return alert
    }
    /// What UIKit does for a tap: the alert is dismissed, then the handler runs.
    @MainActor func tap(_ alert: UIAlertController, _ title: String) {
        typealias Handler = @convention(block) (UIAlertAction) -> Void
        let action = alert.actions.first { $0.title == title }!
        let handler = unsafeBitCast(action.value(forKey: "handler") as AnyObject, to: Handler.self)
        alert.dismiss(animated: false) { handler(action) }
    }

    @MainActor func run() async throws -> [String: Any] {
        let root = window!.rootViewController!
        let input = MeloNXTextInput.shared
        var unblocked: [String: Bool] = [:]
        func ask(_ id: String, title: String = "", message: String = "", placeholder: String = "", raw: Data? = nil) {
            Engine.ask(id, title: title, message: message, placeholder: placeholder, raw: raw) { unblocked[id] = $0 }
        }

        // No registry: nothing registered, nothing shown.
        input.attach(register: nil, invoke: nil, presenter: root)
        try check(Engine.registrations.isEmpty, "registered without the engine exports")
        input.attach(register: Engine.register, invoke: Engine.invoke, presenter: root)
        input.attach(register: Engine.register, invoke: Engine.invoke, presenter: root)
        try check(Engine.registrations == ["show_text_input"] && Engine.callback != nil, "one process-wide registration")

        // 1. The keyboard applet's request, answered with multi-byte text.
        ask("a1", title: "Name", message: "Enter your name", placeholder: "Harry")
        try await until("first keyboard") { alert(on: root) != nil }
        var shown = alert(on: root)!
        try check(shown.title == "Name" && shown.message == "Enter your name", "header and subtitle")
        try check(shown.textFields?.count == 1 && shown.textFields?.first?.placeholder == "Harry", "guide text as placeholder")
        try check(shown.actions.map { $0.title ?? "" } == ["Cancel", "OK"] && shown.preferredAction?.title == "OK", "actions")
        try check(unblocked["a1"] == nil, "engine released before an answer")
        shown.textFields?.first?.text = "Hermione Été 東京"
        tap(shown, "OK")
        try await until("first answer") { unblocked["a1"] != nil }
        try check(unblocked["a1"] == true && Engine.answer("a1")?.text == "Hermione Été 東京", "text delivered as UTF-8")

        // 2. Untitled request; Cancel answers empty (the game keeps its initial text).
        ask("a2")
        try await until("untitled keyboard") { alert(on: root) != nil }
        shown = alert(on: root)!
        try check(shown.title == "Text input" && shown.message == nil, "fallback title")
        tap(shown, "Cancel")
        try await until("cancel answer") { unblocked["a2"] != nil }
        try check(unblocked["a2"] == true && Engine.answer("a2") != nil && Engine.answer("a2")!.text == nil, "cancel is an empty answer")

        // 3. Two requests at once are shown one after the other, in order.
        ask("q1", title: "First"); try await until("q1 queued") { alert(on: root)?.title == "First" }
        ask("q2", title: "Second")
        try await Task.sleep(nanoseconds: 300_000_000)
        try check(alert(on: root)?.title == "First", "second request stacked on the first")
        shown = alert(on: root)!; shown.textFields?.first?.text = "1"; tap(shown, "OK")
        try await until("q2 shown after q1") { alert(on: root)?.title == "Second" }
        shown = alert(on: root)!; shown.textFields?.first?.text = "2"; tap(shown, "OK")
        try await until("queue answered") { unblocked["q1"] != nil && unblocked["q2"] != nil }
        try check(Engine.answer("q1")?.text == "1" && Engine.answer("q2")?.text == "2", "queue answers")

        // 4. The in-game menu is open: the keyboard waits for it to close.
        let menu = UIViewController()
        root.present(menu, animated: false)
        ask("m1", title: "After menu")
        try await Task.sleep(nanoseconds: 700_000_000)
        try check(root.presentedViewController === menu && unblocked["m1"] == nil, "keyboard stacked on the menu")
        menu.dismiss(animated: false)
        try await until("keyboard after the menu") { alert(on: root)?.title == "After menu" }

        // 5. Another session's teardown leaves this keyboard alone.
        input.detach(UIViewController())
        try await Task.sleep(nanoseconds: 200_000_000)
        try check(alert(on: root)?.title == "After menu" && unblocked["m1"] == nil, "foreign detach cancelled the keyboard")

        // 6. This session closes with the keyboard open: answered empty, removed.
        input.detach(root)
        try await until("close answer") { unblocked["m1"] != nil }
        try check(unblocked["m1"] == true && Engine.answer("m1")!.text == nil, "close answers empty")
        try await until("keyboard removed") { root.presentedViewController == nil }

        // 7. A request after the session: answered at once, nothing shown.
        ask("late", title: "Late")
        try await until("late answer") { unblocked["late"] != nil }
        try check(unblocked["late"] == true && Engine.answer("late")!.text == nil && root.presentedViewController == nil, "late request")

        // 8. Unreadable requests are ignored without a crash (no answer possible).
        input.attach(register: Engine.register, invoke: Engine.invoke, presenter: root)
        ask("bad", raw: Data("not json".utf8))
        ask("empty", raw: Data())
        try await until("unreadable requests") { unblocked["bad"] != nil && unblocked["empty"] != nil }
        try check(unblocked["bad"] == false && unblocked["empty"] == false && root.presentedViewController == nil, "unreadable request")
        try check(MeloNXLaunchJournal.events.contains { $0["status"] as? String == "invalidRequest" }, "invalid request journaled")
        try check(!MeloNXLaunchJournal.events.contains { ($0["detail"] as? String ?? "").contains("Hermione") }, "entered text journaled")
        input.detach(root)
        try check(Engine.registrations.count == 1, "registered again")
        return ["answers": Engine.answers.map { ["name": $0.name, "text": $0.text.map { $0 as Any } ?? NSNull()] as [String: Any] }]
    }
}
