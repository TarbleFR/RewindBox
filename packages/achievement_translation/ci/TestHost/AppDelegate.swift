import UIKit

/// A real application/scene lifecycle for the UIKit presentation tests.
@main
@MainActor
final class TestAppDelegate: UIResponder, UIApplicationDelegate {}

@MainActor
final class TestSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
               options connectionOptions: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: scene)
        window.rootViewController = UIViewController()
        window.makeKeyAndVisible()
        self.window = window
    }
}
