import UIKit
import Metal
import QuartzCore
import SwiftUI

private final class MeloNXObservedMetalLayer: CAMetalLayer {
    private let observationLock = NSLock()
    private var presentedFrames: UInt64 = 0
    var firstPresentation: (() -> Void)?
    var frameCount: UInt64 { observationLock.lock(); defer { observationLock.unlock() }; return presentedFrames }
    override func nextDrawable() -> CAMetalDrawable? {
        guard let drawable = super.nextDrawable() else { return nil }
        drawable.addPresentedHandler { [weak self] value in
            guard let self, value.presentedTime > 0 else { return }
            self.observationLock.lock()
            self.presentedFrames += 1
            let first = self.presentedFrames == 1
            self.observationLock.unlock()
            if first { DispatchQueue.main.async { [weak self] in self?.firstPresentation?() } }
        }
        return drawable
    }
}

private final class MeloNXMetalSurface: UIView {
    override class var layerClass: AnyClass { MeloNXObservedMetalLayer.self }
    var metalLayer: MeloNXObservedMetalLayer { layer as! MeloNXObservedMetalLayer }
    override func layoutSubviews() {
        super.layoutSubviews()
        let scale = window?.screen.scale ?? traitCollection.displayScale
        metalLayer.contentsScale = scale
        metalLayer.drawableSize = CGSize(width: bounds.width * scale, height: bounds.height * scale)
    }
}

private struct MeloNXTouchOverlay: View {
    @ObservedObject var router: MeloNXInputRouter
    var body: some View {
        if !router.hideWithController || router.controllerCount == 0 {
            ControllerView(controller:router,isEditing:false,gameId:router.gameID,gameName:router.gameName)
        }
    }
}

private final class MeloNXEditorHost: UIHostingController<AnyView> {
    var closed: (() -> Void)?
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if presentingViewController == nil { let callback = closed; closed = nil; callback?() }
    }
}

final class MeloNXMetalSessionViewController: UIViewController {
    private let host: MeloNXSessionHost
    private let runtime: MeloNXRuntimeAPI?
    private let titleID: String?
    private let game: URL
    private let locale: String
    private let beforeRun: (() -> Bool)?
    private let firstFrame: () -> Void
    private let finished: (Result<Void, MeloNXHostError>) -> Void
    private var settings: [String:Any]
    private let saveSettings: ([String:Any], @escaping (Bool)->Void)->Void
    private var generation: Int64?
    private var saving = false
    private var memoryGraph: MeloNXMemoryGraph?
    private var visible = false
    private var started = false
    private var ready = false
    private var closing = false
    private var pauseReasons = Set<String>()
    private var observers: [NSObjectProtocol] = []
    private let surface = MeloNXMetalSurface()
    private let spinner = UIActivityIndicatorView(style:.large)
    private let menuButton = UIButton(type:.system)
    private var router: MeloNXInputRouter?
    private var controls: UIHostingController<AnyView>?
    var presentedFrameCount: UInt64 { surface.metalLayer.frameCount }

    init(host: MeloNXSessionHost, game: URL, locale: String,
         runtime: MeloNXRuntimeAPI? = nil, titleID: String? = nil,
         settings: [String:Any] = [:],
         saveSettings: @escaping ([String:Any], @escaping (Bool)->Void)->Void = { _, done in done(false) },
         beforeRun: (() -> Bool)? = nil,
         firstFrame: @escaping () -> Void = {},
         finished: @escaping (Result<Void, MeloNXHostError>) -> Void) {
        self.host = host; self.game = game; self.locale = locale; self.titleID = titleID
        self.runtime = runtime; self.beforeRun = beforeRun
        self.settings = settings; self.saveSettings = saveSettings
        self.firstFrame = firstFrame; self.finished = finished
        super.init(nibName:nil,bundle:nil)
        modalPresentationStyle = .fullScreen; isModalInPresentation = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }

    override func loadView() {
        view = UIView(); view.backgroundColor = .black
        surface.backgroundColor = .black
        surface.metalLayer.device = MTLCreateSystemDefaultDevice()
        surface.metalLayer.pixelFormat = .bgra8Unorm
        surface.metalLayer.framebufferOnly = false
        surface.metalLayer.isOpaque = true
        surface.metalLayer.firstPresentation = { [weak self] in
            guard let self, !self.closing else { return }
            self.ready = true; self.spinner.stopAnimating()
            self.applyPause(); self.firstFrame()
        }
        surface.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(surface)
        NSLayoutConstraint.activate([surface.leadingAnchor.constraint(equalTo:view.leadingAnchor),surface.trailingAnchor.constraint(equalTo:view.trailingAnchor),surface.topAnchor.constraint(equalTo:view.topAnchor),surface.bottomAnchor.constraint(equalTo:view.bottomAnchor)])
        spinner.color = .white; spinner.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(spinner)
        NSLayoutConstraint.activate([spinner.centerXAnchor.constraint(equalTo:view.centerXAnchor),spinner.centerYAnchor.constraint(equalTo:view.centerYAnchor)])
        spinner.startAnimating()
        menuButton.setImage(UIImage(systemName:"ellipsis.circle.fill"),for:.normal)
        menuButton.tintColor = .white; menuButton.backgroundColor = UIColor.black.withAlphaComponent(0.35)
        menuButton.layer.cornerRadius = 22; menuButton.accessibilityLabel = MeloNXText("Menu")
        menuButton.translatesAutoresizingMaskIntoConstraints = false
        menuButton.addTarget(self,action:#selector(showMenu),for:.touchUpInside)
        view.addSubview(menuButton)
        NSLayoutConstraint.activate([menuButton.widthAnchor.constraint(equalToConstant:44),menuButton.heightAnchor.constraint(equalToConstant:44),menuButton.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:8),menuButton.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor,constant:-8)])
        let graph = MeloNXMemoryGraph()
        graph.sample = { [weak self] in
            var values = MeloNXMemorySnapshot() as? [String:Any] ?? [:]
            for (key,value) in MeloNXMemoryLease.shared.snapshot() { values[key] = value }
            for (key,value) in self?.runtime?.memorySnapshot() ?? [:] { values[key] = value }
            return values
        }
        graph.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(graph); memoryGraph = graph
        NSLayoutConstraint.activate([
            graph.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor,constant:8),
            graph.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:8),
            graph.widthAnchor.constraint(equalToConstant:240),graph.heightAnchor.constraint(equalToConstant:152)
        ])
        updateMemoryGraph()
        for (name, pause) in [(UIApplication.willResignActiveNotification,true),(UIApplication.didBecomeActiveNotification,false)] {
            observers.append(NotificationCenter.default.addObserver(forName:name,object:nil,queue:.main) { [weak self] _ in self?.setPause("application",enabled:pause); self?.updateMemoryGraph() })
        }
    }

    private func installControls(generation: Int64) {
        self.generation = generation
        guard let runtime else { return }
        let router = MeloNXInputRouter(runtime:runtime,generation:generation,game:game,titleID:titleID)
        self.router = router
        router.onMenu = { [weak self] in self?.showMenu() }
        refreshControls()
        if UIApplication.shared.applicationState != .active { pauseReasons.insert("application") }
        applyPause()
    }
    private func refreshControls() {
        guard let router else { return }
        if let controls {
            controls.willMove(toParent:nil); controls.view.removeFromSuperview(); controls.removeFromParent()
        }
        let child = UIHostingController(rootView:AnyView(MeloNXTouchOverlay(router:router)))
        child.view.backgroundColor = .clear; child.view.translatesAutoresizingMaskIntoConstraints = false
        addChild(child); view.insertSubview(child.view,belowSubview:menuButton)
        NSLayoutConstraint.activate([child.view.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor),child.view.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor),child.view.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor),child.view.bottomAnchor.constraint(equalTo:view.safeAreaLayoutGuide.bottomAnchor)])
        child.didMove(toParent:self); controls = child
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        visible = true; updateMemoryGraph()
        guard !started else { return }; started = true
        if closing {
            dismiss(animated:true) { [finished] in finished(.success(())) }
            return
        }
        surface.layoutIfNeeded()
        let size = surface.metalLayer.drawableSize
        do {
            try host.start(game:game,locale:locale,
                width:Int32(max(1,min(16384,size.width))),height:Int32(max(1,min(16384,size.height))),
                surface:surface.metalLayer,pointer:Unmanaged.passUnretained(surface.metalLayer).toOpaque(),
                prepared:{ [weak self] id in self?.installControls(generation:id) },beforeRun:beforeRun) { [weak self, finished] result in
                    self?.router?.close(); self?.closing = true; self?.updateMemoryGraph()
                    if let self, self.presentingViewController != nil {
                        self.dismiss(animated:true) { finished(result) }
                    } else { finished(result) }
                }
        } catch {
            let failure = error as? MeloNXHostError ?? .load(String(describing:error))
            dismiss(animated:true) { [finished] in finished(.failure(failure)) }
        }
    }

    private func setPause(_ reason: String, enabled: Bool) {
        if enabled { pauseReasons.insert(reason) } else { pauseReasons.remove(reason) }
        applyPause()
    }
    private func applyPause() {
        router?.suspend(!pauseReasons.isEmpty)
        host.setPaused(!pauseReasons.isEmpty)
    }
    @objc private func showMenu() {
        guard presentedViewController == nil, !closing, !saving else { return }
        setPause("menu",enabled:true)
        let menu = UIAlertController(title:game.deletingPathExtension().lastPathComponent,message:nil,preferredStyle:.actionSheet)
        menu.addAction(UIAlertAction(title:MeloNXText("Resume"),style:.cancel) { [weak self] _ in self?.setPause("menu",enabled:false) })
        menu.addAction(UIAlertAction(title:MeloNXText("RAM graph") + ": " + MeloNXText((settings["showRamGraph"] as? Bool ?? true) ? "On" : "Off"),style:.default) { [weak self] _ in
            guard let self else { return }
            self.saveOption("showRamGraph",value:!(self.settings["showRamGraph"] as? Bool ?? true))
        })
        menu.addAction(UIAlertAction(title:MeloNXText("Memory status"),style:.default) { [weak self] _ in self?.showMemoryStatus() })
        if ready {
            menu.addAction(UIAlertAction(title:MeloNXText("Screen format"),style:.default) { [weak self] _ in self?.showFormats() })
        }
        if ready, let router {
            menu.addAction(UIAlertAction(title:MeloNXText("Edit touch controls"),style:.default) { [weak self] _ in self?.editLayout() })
            menu.addAction(UIAlertAction(title:MeloNXText("Controller mapping"),style:.default) { [weak self] _ in self?.editMapping() })
            let title = MeloNXText("Hide touch controls when a controller is connected") + ": " + MeloNXText(router.hideWithController ? "On" : "Off")
            menu.addAction(UIAlertAction(title:title,style:.default) { [weak self] _ in router.hideWithController.toggle(); self?.setPause("menu",enabled:false) })
        }
        menu.addAction(UIAlertAction(title:MeloNXText("Close game"),style:.destructive) { [weak self] _ in self?.requestClose() })
        menu.popoverPresentationController?.sourceView = menuButton
        menu.popoverPresentationController?.sourceRect = menuButton.bounds
        present(menu,animated:true)
    }
    private func updateMemoryGraph() {
        let enabled = settings["showRamGraph"] as? Bool ?? true
        memoryGraph?.isHidden = !enabled
        memoryGraph?.setSampling(enabled && visible && !closing && UIApplication.shared.applicationState == .active)
    }
    private func showFormats() {
        guard !closing else { return }
        let menu = UIAlertController(title:MeloNXText("Screen format"),message:nil,preferredStyle:.actionSheet)
        let current = (settings["aspectRatio"] as? NSNumber)?.intValue ?? 1
        for (value,key) in [(1,"Original (16:9)"),(0,"4:3"),(2,"16:10"),(3,"21:9"),(4,"32:9"),(5,"Stretch")] {
            menu.addAction(UIAlertAction(title:(value == current ? "✓ " : "") + MeloNXText(key),style:.default) { [weak self] _ in self?.saveOption("aspectRatio",value:value) })
        }
        menu.addAction(UIAlertAction(title:MeloNXText("Cancel"),style:.cancel) { [weak self] _ in self?.setPause("menu",enabled:false) })
        menu.popoverPresentationController?.sourceView = menuButton
        menu.popoverPresentationController?.sourceRect = menuButton.bounds
        present(menu,animated:true)
    }
    private func saveOption(_ key:String, value:Any) {
        guard !closing, !saving else { return }
        var updated = settings; updated[key] = value
        let oldAspect = (settings["aspectRatio"] as? NSNumber)?.int32Value ?? 1
        if key == "aspectRatio" {
            guard let generation,let aspect = value as? Int,
                  runtime?.setAspectRatio(Int32(aspect),generation:generation) == true else { settingsFailed(); return }
        }
        saving = true
        saveSettings(updated) { [weak self] success in
            guard let self else { return }
            self.saving = false
            guard !self.closing else { return }
            if success { self.settings = updated; self.updateMemoryGraph(); self.setPause("menu",enabled:false) }
            else {
                if key == "aspectRatio", let generation = self.generation { _ = self.runtime?.setAspectRatio(oldAspect,generation:generation) }
                self.settingsFailed()
            }
        }
    }
    private func settingsFailed() {
        let alert = UIAlertController(title:MeloNXText("Settings could not be saved."),message:nil,preferredStyle:.alert)
        alert.addAction(UIAlertAction(title:MeloNXText("Done"),style:.default) { [weak self] _ in self?.setPause("menu",enabled:false) })
        present(alert,animated:true)
    }
    private func showMemoryStatus() {
        let access = MeloNXMemoryEntitlements()
        let state = MeloNXText(access["increasedMemoryLimit"] as? Bool == true ? "Granted" : "Unavailable")
        let donorState = MeloNXMemoryLease.shared.snapshot()["donorState"] as? String ?? "unavailable"
        let message = MeloNXText("Extended memory") + ": " + state + "\nRamDonor: " + MeloNXText("Donor " + donorState) + "\n\n" + MeloNXText("RamDonor lends memory through the bundled extension. If unavailable, MeloNX uses normal memory.")
        let alert = UIAlertController(title:MeloNXText("Memory status"),message:message,preferredStyle:.alert)
        alert.addAction(UIAlertAction(title:MeloNXText("Done"),style:.default) { [weak self] _ in self?.setPause("menu",enabled:false) })
        present(alert,animated:true)
    }
    private func editLayout() {
        guard let router else { setPause("menu",enabled:false); return }
        let editor = MeloNXEditorHost(rootView:AnyView(ControllerView(controller:router,isEditing:true,gameId:router.gameID,gameName:router.gameName)))
        editor.modalPresentationStyle = .overFullScreen; editor.isModalInPresentation = true
        editor.view.backgroundColor = UIColor.black.withAlphaComponent(0.45)
        editor.closed = { [weak self] in self?.refreshControls(); self?.setPause("menu",enabled:false) }
        present(editor,animated:true)
    }
    private func editMapping() {
        guard let router else { setPause("menu",enabled:false); return }
        let editor = MeloNXEditorHost(rootView:AnyView(MeloNXMappingView(router:router)))
        editor.modalPresentationStyle = .fullScreen
        editor.closed = { [weak self] in self?.setPause("menu",enabled:false) }
        present(editor,animated:true)
    }
    func requestClose() {
        guard !closing else { return }; closing = true
        router?.close(); host.requestStop(); updateMemoryGraph()
        spinner.startAnimating(); menuButton.isEnabled = false
    }
    func setPaused(_ paused: Bool) { setPause("host",enabled:paused) }
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        visible = false; updateMemoryGraph()
        if isBeingDismissed || presentingViewController == nil { router?.close(); host.requestStop() }
    }
    deinit {
        memoryGraph?.setSampling(false)
        observers.forEach { NotificationCenter.default.removeObserver($0) }
        router?.close(); host.requestStop()
    }
    override var prefersStatusBarHidden: Bool { true }
}
