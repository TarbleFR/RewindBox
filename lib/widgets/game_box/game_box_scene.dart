import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';

/// Images and texts shown on a box.
///
/// Providers are owned by the caller (sizes for browsing or inspection, cache
/// eviction). A null provider means the scan is not available: the scene then
/// draws a neutral surface instead, never another face's scan.
class GameBoxArt {
  const GameBoxArt({
    required this.title,
    this.front,
    this.back,
    this.spine,
    this.support,
    this.spineLandscape = false,
    this.backAspect,
    this.edgeColor,
    this.frontFallback,
    this.backUnavailable = '',
    this.gloss = true,
  });

  final String title;
  final ImageProvider? front;
  final ImageProvider? back;
  final ImageProvider? spine;
  final ImageProvider? support;

  /// The spine scan is stored lying down (text left to right): it is turned a
  /// quarter clockwise to run along the spine.
  final bool spineLandscape;

  /// Width / height of the back scan. A jewel-case back inlay scanned with
  /// its two folding spines is wider (≈ 151 × 118 mm) than the visible back
  /// (≈ 138 × 118 mm): the spines are then shown on the sides of the case.
  final double? backAspect;

  /// Colour of the top, bottom and edges of a cardboard box, sampled from the
  /// front scan's border when known.
  final Color? edgeColor;

  /// Shown on the front when there is no front scan (NeoStation's usual
  /// replacement card).
  final Widget? frontFallback;

  /// Discreet notice on a neutral back ("Back not available").
  final String backUnavailable;

  /// Faint reflection of the clear plastic sleeve. The inspector turns it
  /// off while the back is read or zoomed, so that it never covers print.
  final bool gloss;

  /// Fraction of a jewel back inlay taken by each folding spine.
  static const jewelSpineFraction = 6.5 / 151;

  bool get backHasJewelSpines => (backAspect ?? 0) >= 1.22;

  GameBoxArt copyWith({bool? gloss}) => GameBoxArt(
        title: title,
        front: front,
        back: back,
        spine: spine,
        support: support,
        spineLandscape: spineLandscape,
        backAspect: backAspect,
        edgeColor: edgeColor,
        frontFallback: frontFallback,
        backUnavailable: backUnavailable,
        gloss: gloss ?? this.gloss,
      );
}

/// Paints a [GameBoxModel] at a [BoxPose], optionally open.
class GameBoxScene extends StatelessWidget {
  const GameBoxScene({
    super.key,
    required this.model,
    required this.art,
    this.pose = BoxPose.rest,
    this.opening = BoxOpening.closed,
    this.rotationSafeFit = true,
    this.fitPadding = 0.86,
    this.outlineBlend = 0,
    this.groundShadow = false,
  });

  final GameBoxModel model;
  final GameBoxArt art;
  final BoxPose pose;
  final BoxOpening opening;
  final bool rotationSafeFit;
  final double fitPadding;

  /// See [BoxProjector.outlineBlend].
  final double outlineBlend;

  /// Soft shadow under the box (inspector), drawn behind it.
  final bool groundShadow;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final size = constraints.biggest;
      if (!size.isFinite || size.isEmpty) return const SizedBox.shrink();
      final projector = BoxProjector(
        model: model,
        viewport: size,
        pose: pose,
        opening: opening,
        rotationSafeFit: rotationSafeFit,
        fitPadding: fitPadding,
        outlineBlend: outlineBlend,
      );
      final faces = projector.project();
      return SizedBox.fromSize(
        size: size,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            if (groundShadow) _shadow(projector, size),
            for (final f in faces)
              Positioned(
                left: 0,
                top: 0,
                child: Transform(
                  key: ValueKey(f.face.id),
                  transform: f.matrix,
                  child: SizedBox(
                    width: f.width,
                    height: f.height,
                    child: _shaded(_surface(f), f.shade),
                  ),
                ),
              ),
          ],
        ),
      );
    });
  }

  Widget _shadow(BoxProjector projector, Size size) {
    final s = projector.scale * pose.zoom;
    final w = model.width * s * 1.15;
    final cx = size.width / 2 + pose.panX + projector.offsetX;
    final cy = size.height / 2 + pose.panY + projector.offsetY + model.height * s * 0.5;
    return Positioned(
      left: cx - w / 2,
      top: cy - w * 0.06,
      width: w,
      height: w * 0.16,
      child: const IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              colors: [Color(0x55000000), Color(0x00000000)],
            ),
          ),
        ),
      ),
    );
  }

  Widget _shaded(Widget child, double shade) {
    if (shade >= 0.995) return child;
    return Stack(fit: StackFit.expand, children: [
      child,
      IgnorePointer(
        child: ColoredBox(color: Colors.black.withValues(alpha: (1 - shade).clamp(0.0, 0.5))),
      ),
    ]);
  }

  GameBoxProfile get _profile => model.profile;
  bool get _jewel => _profile.caseKind == GameBoxCaseKind.jewelCase;
  bool get _cardboard => _profile.caseKind == GameBoxCaseKind.cardboard;
  bool get _plasticCase =>
      _profile.caseKind == GameBoxCaseKind.keepCase || _profile.caseKind == GameBoxCaseKind.clamshell;

  Color get _edge => _cardboard ? (art.edgeColor ?? _profile.caseColor) : _profile.caseColor;

  /// Tray seen through a jewel case's clear plastic.
  Color get _tray => _profile.resolvedInteriorColor;

  Widget _surface(ProjectedFace f) {
    final mm = f.pxPerMm;
    switch (f.face.surface) {
      case BoxSurface.front:
        return _rounded(f, _front(f, mm));
      case BoxSurface.back:
        return _rounded(f, _back(f, mm));
      case BoxSurface.spine:
        return _spineLeft(f, mm);
      case BoxSurface.spineRight:
        return _spineRight(f, mm);
      case BoxSurface.top:
      case BoxSurface.bottom:
        if (_jewel) return _clearEdge(mm);
        return _plasticEdge(seam: _plasticCase, mm: mm);
      case BoxSurface.edge:
        if (_jewel) return _clearEdge(mm);
        final ridged = _plasticCase && f.face.id.endsWith('.right') && f.face.width > 6;
        return _plasticEdge(ridged: ridged, mm: mm);
      case BoxSurface.interior:
        return CustomPaint(
          painter: GameBoxInteriorPainter(
            kind: _profile.caseKind,
            color: _profile.resolvedInteriorColor,
            hub: _profile.disc != null,
            teeth: _profile.disc != null && !(_profile.disc!.shell),
            cardSlot: _profile.support == GameBoxSupportKind.card,
          ),
        );
      case BoxSurface.lidInner:
        return _rounded(
          f,
          CustomPaint(
            painter: GameBoxLidInnerPainter(
              kind: _profile.caseKind,
              color: _profile.resolvedInteriorColor,
            ),
          ),
        );
      case BoxSurface.supportFront:
        return _supportFront();
      case BoxSurface.supportBack:
      case BoxSurface.supportEdge:
        if (_profile.disc != null) {
          // The data side of a disc (PlayStation discs are black).
          return ColoredBox(color: _profile.id == 'ps1' ? const Color(0xFF101012) : const Color(0xFFB8BDC4));
        }
        return ColoredBox(color: _profile.cartridge?.bodyColor ?? const Color(0xFF3A3A3E));
    }
  }

  Widget _rounded(ProjectedFace f, Widget child) {
    final r = f.face.cornerRadius * f.pxPerMm;
    if (r <= 0.5) return child;
    return ClipRRect(borderRadius: BorderRadius.circular(r), child: child);
  }

  // Front ---------------------------------------------------------------------

  Widget _front(ProjectedFace f, double mm) {
    final front = art.front;
    if (_jewel) {
      return _jewelFront(f, mm, front);
    }
    final Widget picture = front == null
        ? (art.frontFallback ?? GameBoxNeutralFace(color: _profile.caseColor, notice: art.title))
        : _image(front, BoxFit.fill);
    if (_cardboard) return picture;
    // Keep case: the cover sits under a clear sleeve, inside a thin rim of the
    // case's plastic.
    final rim = 1.4 * mm;
    return Stack(fit: StackFit.expand, children: [
      ColoredBox(color: _profile.caseColor),
      Padding(padding: EdgeInsets.all(rim), child: picture),
      if (art.gloss) const _SleeveGloss(),
    ]);
  }

  /// The lid of a jewel case: clear plastic over the black tray, the hinge
  /// band on the left, the square booklet on the right of it.
  Widget _jewelFront(ProjectedFace f, double mm, ImageProvider? front) {
    final hinge = GameBoxProfile.jewelHinge * mm;
    return Stack(fit: StackFit.expand, children: [
      ColoredBox(color: _tray),
      Positioned(
        left: hinge + 1.5 * mm,
        right: 2.5 * mm,
        top: 2.5 * mm,
        bottom: 2.5 * mm,
        child: front == null
            ? (art.frontFallback ?? GameBoxNeutralFace(color: _profile.caseColor, notice: art.title))
            : _image(front, BoxFit.contain),
      ),
      Positioned(
        left: 0,
        top: 0,
        bottom: 0,
        width: hinge,
        child: const CustomPaint(painter: GameBoxJewelHingePainter()),
      ),
      if (art.gloss) const _SleeveGloss(strength: 1.25),
      const _ClearRim(),
    ]);
  }

  // Back ----------------------------------------------------------------------

  Widget _back(ProjectedFace f, double mm) {
    final back = art.back;
    if (back == null) {
      return GameBoxNeutralFace(
        color: _jewel ? _tray : _edge,
        notice: art.backUnavailable.isEmpty ? null : art.backUnavailable,
        icon: Icons.image_not_supported_outlined,
      );
    }
    if (_jewel) {
      // The back inlay, seen through the clear bottom of the tray. A scan
      // that includes the folding spines shows only its middle here.
      final strip = art.backHasJewelSpines ? GameBoxArt.jewelSpineFraction : 0.0;
      return Stack(fit: StackFit.expand, children: [
        ColoredBox(color: _tray),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 2 * mm, vertical: 3.5 * mm),
          child: _crop(back, Rect.fromLTRB(strip, 0, 1 - strip, 1)),
        ),
        const _ClearRim(),
      ]);
    }
    if (_cardboard) return _image(back, BoxFit.fill);
    return Stack(fit: StackFit.expand, children: [
      ColoredBox(color: _profile.caseColor),
      Padding(padding: EdgeInsets.all(1.4 * mm), child: _image(back, BoxFit.fill)),
    ]);
  }

  // Spines --------------------------------------------------------------------

  /// The spine image laid out at the face's full (uncut) size, then windowed.
  Widget _spineLeft(ProjectedFace f, double mm) {
    final spine = art.spine;
    if (_jewel) {
      // Hinge side: the spine of the back inlay behind clear plastic, with the
      // lid's hinge knuckles at both ends.
      Widget? strip;
      if (spine != null) {
        strip = _spineImage(spine);
      } else if (art.back != null && art.backHasJewelSpines) {
        // Right-hand strip of the inlay, as scanned flat, folds onto the hinge
        // side unchanged.
        strip = _crop(art.back!, const Rect.fromLTRB(1 - GameBoxArt.jewelSpineFraction, 0, 1, 1));
      }
      return _jewelSide(mm, strip ?? GameBoxTitleSpine(color: _profile.caseColor, title: art.title), hinge: true);
    }
    final Widget full = spine == null
        ? GameBoxTitleSpine(color: _edge, title: art.title)
        : _spineImage(spine);
    final Widget printed = _plasticCase
        ? Stack(fit: StackFit.expand, children: [
            ColoredBox(color: _profile.caseColor),
            // The spine of the cover, under the sleeve, between the plastic of
            // the front and back panels.
            Padding(padding: EdgeInsets.symmetric(horizontal: 0.9 * mm), child: full),
          ])
        : full;
    return _window(printed, f.face.source, f.width, f.height);
  }

  Widget _spineRight(ProjectedFace f, double mm) {
    Widget? strip;
    if (art.back != null && art.backHasJewelSpines) {
      strip = _crop(art.back!, const Rect.fromLTRB(0, 0, GameBoxArt.jewelSpineFraction, 1));
    }
    if (strip == null) return _clearEdge(mm);
    return _jewelSide(mm, strip, hinge: false);
  }

  Widget _jewelSide(double mm, Widget strip, {required bool hinge}) {
    return Stack(fit: StackFit.expand, children: [
      ColoredBox(color: _tray),
      Padding(
        padding: EdgeInsets.symmetric(horizontal: 1.6 * mm, vertical: 3.5 * mm),
        child: strip,
      ),
      if (hinge) const CustomPaint(painter: GameBoxJewelKnucklePainter()),
      const _ClearRim(),
    ]);
  }

  Widget _spineImage(ImageProvider spine) => art.spineLandscape
      ? RotatedBox(quarterTurns: 1, child: _image(spine, BoxFit.fill))
      : _image(spine, BoxFit.fill);

  // Edges ---------------------------------------------------------------------

  Widget _plasticEdge({bool ridged = false, bool seam = false, required double mm}) {
    return CustomPaint(
      painter: GameBoxEdgePainter(
        color: _edge,
        ridged: ridged,
        seam: seam,
        cardboard: _cardboard,
        pxPerMm: mm,
      ),
    );
  }

  Widget _clearEdge(double mm) => Stack(fit: StackFit.expand, children: [
        ColoredBox(color: Color.lerp(_tray, const Color(0xFF8A8F96), 0.22)!),
        const _ClearRim(),
      ]);

  // Support -------------------------------------------------------------------

  Widget _supportFront() {
    switch (_profile.support) {
      case GameBoxSupportKind.disc:
      case GameBoxSupportKind.miniDisc:
      case GameBoxSupportKind.umd:
        return GameBoxDiscFace(
          style: _profile.disc ?? const GameBoxDiscStyle(id: 'cd', diameter: 120),
          art: art.support,
        );
      case GameBoxSupportKind.cartridge:
      case GameBoxSupportKind.card:
      case GameBoxSupportKind.hucard:
        final style = _profile.cartridge;
        if (style == null) return GameBoxMediaFace(kind: _profile.support, title: art.title);
        return GameBoxCartridgeFace(style: style, title: art.title, art: art.support);
      case GameBoxSupportKind.floppy:
      case GameBoxSupportKind.cassette:
        return GameBoxMediaFace(kind: _profile.support, title: art.title);
      case GameBoxSupportKind.none:
        return const SizedBox.shrink();
    }
  }

  // Images --------------------------------------------------------------------

  static Widget _image(ImageProvider provider, BoxFit fit) => Image(
        image: provider,
        fit: fit,
        gaplessPlayback: true,
        filterQuality: FilterQuality.medium,
        excludeFromSemantics: true,
        errorBuilder: (_, _, _) => const ColoredBox(color: Color(0xFF2A2A2E)),
      );

  /// Shows the [source] region (fractions) of an image, stretched to the box.
  static Widget _crop(ImageProvider provider, Rect source) => LayoutBuilder(
        builder: (context, c) => _window(
          _image(provider, BoxFit.fill),
          source,
          c.maxWidth,
          c.maxHeight,
        ),
      );

  /// Shows only [source] (fractions) of a surface laid out at full size.
  static Widget _window(Widget full, Rect source, double w, double h) {
    if (source == const Rect.fromLTWH(0, 0, 1, 1)) return full;
    final fullW = source.width <= 0 ? w : w / source.width;
    final fullH = source.height <= 0 ? h : h / source.height;
    if (!fullW.isFinite || !fullH.isFinite) return full;
    return ClipRect(
      child: OverflowBox(
        alignment: Alignment.topLeft,
        minWidth: fullW,
        maxWidth: fullW,
        minHeight: fullH,
        maxHeight: fullH,
        child: Transform.translate(
          offset: Offset(-source.left * fullW, -source.top * fullH),
          child: SizedBox(width: fullW, height: fullH, child: full),
        ),
      ),
    );
  }
}

/// Faint diagonal reflection of a clear sleeve or lid. It stays under 8 %
/// white and fades out before the middle of the face.
class _SleeveGloss extends StatelessWidget {
  const _SleeveGloss({this.strength = 1});
  final double strength;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            stops: const [0.0, 0.22, 0.42],
            colors: [
              Colors.white.withValues(alpha: math.min(0.08, 0.06 * strength)),
              Colors.white.withValues(alpha: math.min(0.04, 0.025 * strength)),
              Colors.white.withValues(alpha: 0),
            ],
          ),
        ),
      ),
    );
  }
}

/// Bright edges of clear polystyrene.
class _ClearRim extends StatelessWidget {
  const _ClearRim();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(color: Colors.white.withValues(alpha: 0.16), width: 0.8),
        ),
      ),
    );
  }
}
