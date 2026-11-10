// SPDX-License-Identifier: GPL-3.0-or-later
import UIKit
import Combine

/// The controller skin the player chose for the Nintendo Switch, over a MeloNX
/// session (MeloNXSkinOverlay, docs/dolphin-skins.md). Created only when a skin is
/// selected for the console or the game (Documents/Libretro/Config/Frontend/
/// switch.json); without one nothing here exists and the session is unchanged.
///
/// While its layout is shown for the current orientation:
/// - it replaces the Melo-Controller (hidden) and sends the Core's button indices
///   and both sticks through MeloNXInputRouter (the same pad and "touch" source);
/// - the game goes into the skin's screen, the renderer keeping its own aspect
///   ratio inside it (the surface sets its drawable from its bounds, as on rotation);
/// - the session's floating menu button is hidden over a skin with its own Menu,
///   which opens the same RewindBox session menu;
/// - HOME and Capture, which the embedded Core cannot receive, show a notice and
///   send nothing to the game.
/// It follows the Melo-Controller's visibility rule (hidden when a controller is
/// connected and "Hide touch controls when a controller is connected" is on), and
/// lets go of every input whenever the session pauses (menu, editor, background),
/// the layout changes (rotation) or the session closes.
final class MeloNXSkinSession {
    let overlay: MeloNXSkinOverlay
    private weak var host: UIView?
    private weak var surface: UIView?
    private weak var menuButton: UIView?
    private let surfaceFill: [NSLayoutConstraint]
    private let router: MeloNXInputRouter
    private var observers = Set<AnyCancellable>()
    /// The Melo-Controller's view, rebuilt by the session (refreshControls).
    var controlsView: () -> UIView? = { nil }
    /// No menu or editor is presented, the session is not paused or closing.
    var interactive: () -> Bool = { true }
    private var noticeLabel: UILabel?
    private(set) var shown = false

    /// nil when no skin is chosen for the Switch (the session is then unchanged).
    init?(game: URL, router: MeloNXInputRouter, host: UIView, surface: UIView,
          surfaceFill: [NSLayoutConstraint], menuButton: UIView, menu: @escaping () -> Void) {
        let overlay = MeloNXSkinOverlay(gameKey: game.lastPathComponent)
        guard overlay.hasSkin else { return nil }
        self.overlay = overlay; self.router = router; self.host = host; self.surface = surface
        self.surfaceFill = surfaceFill; self.menuButton = menuButton
        overlay.frame = host.bounds
        overlay.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        overlay.buttonChanged = { [weak router] button, pressed in router?.skinButton(Int32(button), pressed: pressed) }
        overlay.sticksChanged = { [weak router] lx, ly, rx, ry in router?.skinSticks(leftX: lx, leftY: ly, rightX: rx, rightY: ry) }
        overlay.menuHandler = menu
        overlay.systemButtonHandler = { [weak self] name in
            self?.showNotice(MeloNXText(name == "capture" ? "Capture is not available with this Switch engine"
                                                          : "HOME is not available with this Switch engine"))
        }
        overlay.layoutChanged = { [weak self] in self?.sync() }
        // Above the game, below the session's buttons and graph (added after it).
        host.insertSubview(overlay, aboveSubview: surface)
        router.$controllerCount.combineLatest(router.$hideWithController)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in self?.sync() }
            .store(in: &observers)
    }

    /// Shown, interactive, the Melo-Controller and the floating menu, the game's place.
    func sync() {
        guard let host else { return }
        let hiddenByController = router.hideWithController && router.controllerCount > 0
        shown = overlay.layoutActive && !hiddenByController
        let interactive = shown && self.interactive()
        if !interactive { overlay.releaseAllInputs() }
        overlay.isHidden = !shown
        overlay.isUserInteractionEnabled = interactive
        controlsView()?.isHidden = shown
        menuButton?.isHidden = shown && overlay.hasMenuControl
        placeSurface(in: host)
    }

    /// The layout pass of the session view: the overlay fills it, the game goes
    /// into the skin's screen.
    func layout() {
        guard let host else { return }
        overlay.frame = host.bounds
        overlay.layoutIfNeeded()
        placeSurface(in: host)
    }

    private func placeSurface(in host: UIView) {
        guard let surface else { return }
        let screen = overlay.screenFrame
        if shown, !screen.isNull, screen.width >= 1, screen.height >= 1 {
            NSLayoutConstraint.deactivate(surfaceFill)
            surface.translatesAutoresizingMaskIntoConstraints = true
            let frame = overlay.convert(screen, to: host).integral
            if surface.frame != frame { surface.frame = frame }
        } else if surface.translatesAutoresizingMaskIntoConstraints {
            surface.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate(surfaceFill)
        }
    }

    /// A short message over the game for about two seconds (one at a time).
    private func showNotice(_ text: String) {
        guard let host else { return }
        noticeLabel?.removeFromSuperview()
        let label = UILabel()
        label.text = text; label.textColor = .white; label.textAlignment = .center; label.numberOfLines = 2
        label.font = .preferredFont(forTextStyle: .footnote); label.adjustsFontForContentSizeCategory = true
        label.backgroundColor = UIColor.black.withAlphaComponent(0.72)
        label.layer.cornerRadius = 10; label.layer.masksToBounds = true
        label.accessibilityTraits = .staticText
        let screen = shown && !overlay.screenFrame.isNull ? overlay.convert(overlay.screenFrame, to: host) : host.bounds
        let size = label.sizeThatFits(CGSize(width: min(screen.width - 24, 320), height: 80))
        label.frame = CGRect(x: screen.midX - (size.width + 24) / 2, y: screen.minY + 12, width: size.width + 24, height: size.height + 14)
        host.addSubview(label)
        noticeLabel = label
        UIAccessibility.post(notification: .announcement, argument: text)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) { [weak self, weak label] in
            guard let label, self?.noticeLabel === label else { return }
            UIView.animate(withDuration: 0.25, animations: { label.alpha = 0 }) { _ in label.removeFromSuperview() }
        }
    }

    func close() {
        noticeLabel?.removeFromSuperview()
        overlay.releaseAllInputs()
        observers.removeAll()
        overlay.removeFromSuperview()
    }
}
