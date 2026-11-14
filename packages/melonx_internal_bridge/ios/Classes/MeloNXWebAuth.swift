import AuthenticationServices
import Flutter
import UIKit

/// The system sign-in sheet for an OAuth authorization (ASWebAuthenticationSession), as Nextendo's developer
/// documentation asks of an iOS application: the player signs in on the service's own page, and the application only
/// receives the redirect that ends the sheet. RewindBox never sees a password.
///
/// Channel `neostation/web_auth`, method `authenticate` {url, callbackScheme} -> the redirect address. Errors:
/// `cancelled` (the player closed the sheet), `busy`, `invalidRequest`, `unavailable`, `failed`.
final class MeloNXWebAuthPlugin: NSObject, FlutterPlugin, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession? // main thread only
    // Kept like the bridge plugin's: the view controller is resolved when the sheet opens, not at registration.
    private var registrar: FlutterPluginRegistrar?

    static func register(with registrar: FlutterPluginRegistrar) {
        let instance = MeloNXWebAuthPlugin()
        instance.registrar = registrar
        let channel = FlutterMethodChannel(name:"neostation/web_auth",binaryMessenger:registrar.messenger())
        registrar.addMethodCallDelegate(instance,channel:channel)
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard call.method == "authenticate" else { result(FlutterMethodNotImplemented); return }
        let arguments = call.arguments as? [String:Any] ?? [:]
        // Only an https page is opened: the sheet shows its address to the player.
        guard let text = arguments["url"] as? String, let url = URL(string:text), url.scheme == "https", url.host != nil,
              let scheme = arguments["callbackScheme"] as? String, !scheme.isEmpty else {
            result(FlutterError(code:"invalidRequest",message:"An https authorization address and a callback scheme are required.",details:nil)); return
        }
        guard session == nil else { result(FlutterError(code:"busy",message:"A sign-in is already open.",details:nil)); return }
        let created = ASWebAuthenticationSession(url:url,callbackURLScheme:scheme) { [weak self] callback, error in
            DispatchQueue.main.async {
                self?.session = nil
                if let callback { result(callback.absoluteString); return }
                if let failure = error as? ASWebAuthenticationSessionError, failure.code == .canceledLogin {
                    result(FlutterError(code:"cancelled",message:"Sign-in cancelled.",details:nil))
                } else {
                    result(FlutterError(code:"failed",message:error.map { String(describing:$0) } ?? "No redirect was received.",details:nil))
                }
            }
        }
        created.presentationContextProvider = self
        // The player's Safari session is shared: already signed in on nextendo.network means one tap to approve.
        created.prefersEphemeralWebBrowserSession = false
        session = created
        if !created.start() {
            session = nil
            result(FlutterError(code:"unavailable",message:"The system sign-in sheet could not be presented.",details:nil))
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        if let window = registrar?.viewController?.view.window { return window }
        for scene in UIApplication.shared.connectedScenes {
            if let windowScene = scene as? UIWindowScene, let window = windowScene.windows.first(where: { $0.isKeyWindow }) { return window }
        }
        return ASPresentationAnchor()
    }
}
