import Flutter
import UIKit

@main final class ProbeApp:UIResponder,UIApplicationDelegate {
    func application(_ app:UIApplication,configurationForConnecting session:UISceneSession,
                     options:UIScene.ConnectionOptions)->UISceneConfiguration {
        let configuration=UISceneConfiguration(name:"Probe",sessionRole:session.role)
        configuration.delegateClass=ProbeScene.self;return configuration
    }
}
final class ProbeScene:UIResponder,UIWindowSceneDelegate {
    var window:UIWindow?
    let registrar=PresentationRegistrar()
    var plugin:MeloNXInternalBridgePlugin!
    var checks=0
    var started=false
    let old=Bundle.main.object(forInfoDictionaryKey:"OldControl") as? Bool == true
    var game=""
    func scene(_ scene:UIScene,willConnectTo session:UISceneSession,options:UIScene.ConnectionOptions) {
        guard let scene=scene as? UIWindowScene else { return }
        // The exact registration ordering that the previous code mishandled.
        assert(registrar.viewController == nil)
        MeloNXInternalBridgePlugin.register(with:registrar)
        plugin=registrar.plugin as? MeloNXInternalBridgePlugin
        window=UIWindow(windowScene:scene);window?.rootViewController=UIViewController()
        let docs=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        game=docs.appendingPathComponent("original-probe.nro").path
        try! Data([1,2,3,4]).write(to:URL(fileURLWithPath:game))
    }
    func sceneDidBecomeActive(_ scene:UIScene) {
        guard !started else { return };started=true
        if old {
            window?.makeKeyAndVisible()
            registrar.viewController=window?.rootViewController
        }
        DispatchQueue.main.asyncAfter(deadline:.now()+0.1) { self.noWindow() }
    }
    func check(_ value:Bool,_ message:String) {
        guard value else { finish(false,message);return };checks += 1
    }
    func call(_ method:String,_ arguments:[String:Any]=[:],_ completion:@escaping([String:Any])->Void) {
        plugin.handle(FlutterMethodCall(methodName:method,arguments:arguments)) { value in
            completion(value as? [String:Any] ?? [:])
        }
    }
    func launch(_ completion:@escaping([String:Any])->Void) {
        call("launch",["gamePath":game,"jitBackend":"builtin","locale":"fr"],completion)
    }
    func noWindow() {
        launch { result in
            self.check(result["error"] as? String == "presentationUnavailable","no-window refusal")
            self.check(Probe.detachCalls == 1 && Probe.starts == 0,"prepared without guest")
            self.call("diagnostics") { status in
                self.check(status["jitArenaReady"] as? Bool == !self.old,"arena retained independently of presentation")
                self.window?.makeKeyAndVisible()
                self.registrar.viewController=self.window?.rootViewController
                DispatchQueue.main.asyncAfter(deadline:.now()+0.2) { self.attachedAfterRegistration() }
            }
        }
    }
    func attachedAfterRegistration() {
        launch { result in
            if self.old {
                self.check(result["success"] as? Bool == false && Probe.detachCalls == 2,"old retry repeats completed handshake")
                self.finish(true,"old registration/retry failure reproduced");return
            }
            self.check(result["success"] as? Bool == true,"late registrar attachment launches")
            self.check(Probe.detachCalls == 1 && Probe.handshakes == 1,"no second one-time handshake")
            self.check(self.window?.rootViewController?.presentedViewController?.viewIfLoaded?.window === self.window,"actual UIKit presentation")
            self.close { self.fallback() }
        }
    }
    func close(_ next:@escaping()->Void) {
        call("stop") { _ in
            DispatchQueue.main.asyncAfter(deadline:.now()+0.2,execute:next)
        }
    }
    func fallback() {
        registrar.viewController=nil
        window?.rootViewController=UINavigationController(rootViewController:UIViewController())
        DispatchQueue.main.asyncAfter(deadline:.now()+0.2) {
            self.launch { result in
                self.check(result["success"] as? Bool == true,"nil registrar uses live application window")
                self.check(Probe.detachCalls == 1 && Probe.starts == 2,"relaunch preserves arena")
                self.close { self.modal() }
            }
        }
    }
    func modal() {
        let sheet=UIViewController();sheet.modalPresentationStyle = .overFullScreen
        window?.rootViewController?.present(sheet,animated:false) {
            self.launch { result in
                self.check(result["success"] as? Bool == true,"existing UIKit modal traversed")
                self.check(sheet.presentedViewController is MeloNXMetalSessionViewController,"presented above current modal")
                self.close { sheet.dismiss(animated:false) { self.cancelWhileWaiting() } }
            }
        }
    }
    func cancelWhileWaiting() {
        window?.isHidden=true
        let starts=Probe.starts
        launch { result in
            self.check(result["error"] as? String == "launchCancelled","pending presentation cancellation")
            self.window?.makeKeyAndVisible()
            DispatchQueue.main.asyncAfter(deadline:.now()+0.3) {
                self.check(Probe.starts == starts,"cancelled launch cannot present later")
                MeloNXMemoryLease.shared.retained = true
                self.launch { failed in
                    self.check(failed["requiresRestart"] as? Bool == true,"retained donor blocks restart")
                    self.check(Probe.detachCalls == 1 && Probe.starts == starts,"memory refusal preserves prepared JIT and starts no guest")
                    self.finish(true,"presentation, retry and donor quarantine passed")
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline:.now()+0.15) { self.call("stop") { _ in } }
    }
    func finish(_ success:Bool,_ detail:String) {
        let result:[String:Any]=["result":success ? "passed":"failed","oldControl":old,
            "checks":checks,"detail":detail,"actualUIKit":true,"actualFlutterFramework":true,
            "registrarBoundaryDouble":true,"engineAndJitDouble":true,"guestFrameDouble":true,
            "physicalDeviceTested":false,"gameplayTested":false,"detachCalls":Probe.detachCalls,"presentedSessions":Probe.starts]
        let docs=FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
        try! JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:docs.appendingPathComponent("presentation.json"),options:.atomic)
        if !success { fatalError(detail) }
    }
}
