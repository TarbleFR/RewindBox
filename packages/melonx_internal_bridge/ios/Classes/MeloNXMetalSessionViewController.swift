import UIKit
import Metal
import QuartzCore

private final class MeloNXMetalSurface: UIView {
    override class var layerClass: AnyClass { CAMetalLayer.self }
    var metalLayer: CAMetalLayer { layer as! CAMetalLayer }

    override func layoutSubviews() {
        super.layoutSubviews()
        let scale = window?.screen.scale ?? traitCollection.displayScale
        metalLayer.contentsScale = scale
        metalLayer.drawableSize = CGSize(width: bounds.width * scale, height: bounds.height * scale)
    }
}

// Internal presentation primitive. The eventual Flutter launcher must supply
// successful JIT/dependency/control preflight before constructing this view.
// No engine availability flag or external application fallback is provided.
final class MeloNXMetalSessionViewController: UIViewController {
    private let host: MeloNXSessionHost
    private let game: URL
    private let locale: String
    private let finished: (Result<Void, MeloNXHostError>) -> Void
    private var started = false
    private let surface = MeloNXMetalSurface()

    init(host: MeloNXSessionHost, game: URL, locale: String,
         finished: @escaping (Result<Void, MeloNXHostError>) -> Void) {
        self.host = host
        self.game = game
        self.locale = locale
        self.finished = finished
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .fullScreen
        isModalInPresentation = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }

    override func loadView() {
        surface.backgroundColor = .black
        surface.metalLayer.device = MTLCreateSystemDefaultDevice()
        surface.metalLayer.pixelFormat = .bgra8Unorm
        surface.metalLayer.framebufferOnly = false
        surface.metalLayer.isOpaque = true
        view = surface
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !started else { return }
        started = true
        surface.layoutIfNeeded()
        let size = surface.metalLayer.drawableSize
        do {
            try host.start(game: game, locale: locale,
                width: Int32(max(1, min(16384, size.width))),
                height: Int32(max(1, min(16384, size.height))),
                surface: surface.metalLayer,
                pointer: Unmanaged.passUnretained(surface.metalLayer).toOpaque()) { [weak self, finished] result in
                    if let self, self.presentingViewController != nil {
                        self.dismiss(animated: true) { finished(result) }
                    } else { finished(result) }
                }
        } catch let error as MeloNXHostError {
            dismiss(animated: true) { [finished] in finished(.failure(error)) }
        } catch {
            dismiss(animated: true) { [finished] in finished(.failure(.load(String(describing: error)))) }
        }
    }

    // Closing waits for the same completion path as natural game termination.
    // A stalled native owner keeps the session occupied and its layer retained.
    func requestClose() { host.requestStop() }
    func setPaused(_ paused: Bool) { host.setPaused(paused) }
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed || presentingViewController == nil { host.requestStop() }
    }
    deinit { host.requestStop() }
    override var prefersStatusBarHidden: Bool { true }
}
