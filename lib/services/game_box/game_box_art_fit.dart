import 'dart:math' as math;
import 'dart:ui' show Rect, Size;

import 'package:neostation/services/game_box/game_box_profile.dart';

/// What an image used for a face of the box really is
/// (docs/game-box-3d.md § 13).
///
/// Only a flat scan of the matching face is drawn as the print of a case. A
/// full cover sheet is cut along its verified layout; a 3D render, a logo,
/// an icon or key art is never stretched onto a case as if it were its print.
enum GameBoxArtNature {
  /// A flat scan (or flat template) of this face.
  scan,

  /// The whole cover sheet laid flat: back, spine and front side by side.
  wrap,

  /// A scan that still shows the plastic frame of the case around the print.
  framedCase,

  /// A box already drawn in perspective (ScreenScraper `box-3D`, GameTDB
  /// `box`): it has its own geometry and cannot be a flat texture.
  render3d,

  /// Catalogue art: a logo, a store or console icon (PS3 ICON0.PNG, Switch
  /// title icon), key art. Shown small on a neutral cover, never as a print.
  promo,
}

/// The part of an image shown on a printed area, and where it lands.
///
/// [source] is the window of the image (fractions); [target] the rectangle
/// of the printed area it fills (fractions). Between the two, the image is
/// scaled by at most [GameBoxArtFit.maxStretch] more on one axis than on the
/// other, so titles, logos, faces and age ratings keep their proportions.
class GameBoxArtLayout {
  const GameBoxArtLayout({this.source = full, this.target = full, this.stretch = 1});

  static const Rect full = Rect.fromLTWH(0, 0, 1, 1);
  static const GameBoxArtLayout fill = GameBoxArtLayout();

  final Rect source;
  final Rect target;

  /// Horizontal scale over vertical scale of the drawn image (1 = exact).
  final double stretch;

  bool get isFull => source == full && target == full;

  /// Share of the printed area left uncovered (neutral bands).
  double get uncovered => 1 - target.width * target.height;

  @override
  String toString() => 'GameBoxArtLayout(source: $source, target: $target, stretch: ${stretch.toStringAsFixed(4)})';
}

/// Fits an image into a printed area without distorting its print.
class GameBoxArtFit {
  GameBoxArtFit._();

  /// Largest anisotropic scale accepted (3 %): below what the eye notices on
  /// type and within the cut tolerance of printed cover sheets.
  static const double maxStretch = 0.03;

  /// Largest share of the image cut away on one axis (3 %, split between the
  /// two sides): the bleed and scanner margins of a scan.
  static const double maxCrop = 0.03;

  /// Layout of an image of [imageAspect] (width / height) on an area of
  /// [areaAspect]. Close ratios fill the area; then up to [maxCrop] of the
  /// image's margins is cut; what remains is centred with neutral bands.
  static GameBoxArtLayout fit(
    double imageAspect,
    double areaAspect, {
    double stretch = maxStretch,
    double crop = maxCrop,
  }) {
    if (!imageAspect.isFinite || imageAspect <= 0 || !areaAspect.isFinite || areaAspect <= 0) {
      return GameBoxArtLayout.fill;
    }
    final r = imageAspect / areaAspect;
    final tolerance = 1 + stretch;
    if (r <= tolerance && r >= 1 / tolerance) {
      return GameBoxArtLayout(stretch: 1 / r);
    }
    if (r > 1) {
      // Wider than the area: cut the side margins, then bands top and bottom.
      final keep = math.max(1 - crop, tolerance / r);
      final shown = r * keep; // aspect ratio of the kept part over the area's
      final height = math.min(1.0, tolerance / shown);
      final drawn = shown * height; // over the area's aspect, in the target
      return GameBoxArtLayout(
        source: Rect.fromLTWH((1 - keep) / 2, 0, keep, 1),
        target: Rect.fromLTWH(0, (1 - height) / 2, 1, height),
        stretch: 1 / drawn,
      );
    }
    // Taller than the area: cut the top and bottom margins, then side bands.
    final keep = math.max(1 - crop, r * tolerance);
    final shown = r / keep;
    final width = math.min(1.0, shown * tolerance);
    final drawn = shown / width;
    return GameBoxArtLayout(
      source: Rect.fromLTWH(0, (1 - keep) / 2, 1, keep),
      target: Rect.fromLTWH((1 - width) / 2, 0, width, 1),
      stretch: 1 / drawn,
    );
  }
}

/// How a sheet's spine strip is laid on the case's spine (§ 24).
enum GameBoxSpineFit {
  /// Its own proportions, its height on the case's height; the little the
  /// strip is wider than the spine is the fold of the sheet onto the edges
  /// and is left out (Switch, DS, Wii, GameCube, Wii U: at most 6 % a side).
  trimFold,

  /// Whole, with its own proportions, between margins (a template made
  /// for a thicker case than this one: 3DS).
  whole,

  /// Stretched over the spine (a template whose spine is much wider than
  /// the case's flat spine: PS3), as drawn before.
  stretch,
}

/// A verified layout of a full cover sheet: back | spine | front, as GameTDB
/// publishes them (`coverfull`, `coverfullHQ`) and as ScreenScraper's
/// `box-texture` is accepted only when its proportions match.
class GameBoxWrapLayout {
  const GameBoxWrapLayout({
    required this.panel,
    required this.spine,
    required this.height,
    this.spineFit = GameBoxSpineFit.trimFold,
  });

  /// Template sizes in pixels: one panel, the spine, the sheet height.
  final double panel;
  final double spine;
  final double height;

  /// How the template's spine strip sits on the case's spine (§ 24).
  final GameBoxSpineFit spineFit;

  double get aspect => (2 * panel + spine) / height;

  /// Verified templates (GameTDB HQ full covers, downloaded and measured):
  /// - Switch 2454 × 1888 = 1166 + 122 + 1166; PS3 2000 × 1080 = 928 + 144
  ///   + 928 (1 Nov 2026);
  /// - DS and 3DS 1616 × 680 = 768 + 80 + 768 (Mario Kart DS AMCP,
  ///   Majora's Mask 3D AJRP);
  /// - Wii and GameCube 1024 × 680 = 484 + 56 + 484 (Brawl RSBP01, Mario
  ///   Kart Wii RMCP01, Melee GALP01, Double Dash!! GM4P01); Wii U 1632 ×
  ///   1080 = 776 + 80 + 776 (Mario Kart 8 AMKP01, New Super Mario Bros. U
  ///   ARPP01) (2 Nov 2026).
  static GameBoxWrapLayout? forProfile(GameBoxProfile profile) => switch (profile.id) {
        // A Switch 2 case has the Switch case's size, so a full Switch 2 sheet uses the Switch template.
        'switch' || 'switch2' => const GameBoxWrapLayout(panel: 1166, spine: 122, height: 1888),
        // The PS3 template's spine (20 mm at the panels' scale) is wider than
        // the case's flat spine: it is drawn on it whole, as before.
        'ps3' => const GameBoxWrapLayout(panel: 928, spine: 144, height: 1080, spineFit: GameBoxSpineFit.stretch),
        'ds' => const GameBoxWrapLayout(panel: 768, spine: 80, height: 680),
        // The 3DS reuses the DS template (a 14 mm spine) on its thinner case.
        '3ds' => const GameBoxWrapLayout(panel: 768, spine: 80, height: 680, spineFit: GameBoxSpineFit.whole),
        'wii' || 'gc' || 'triforce' => const GameBoxWrapLayout(panel: 484, spine: 56, height: 680),
        'wiiu' => const GameBoxWrapLayout(panel: 776, spine: 80, height: 1080),
        _ => null,
      };

  /// Relative tolerance on the sheet's proportions.
  static const double tolerance = 0.025;

  bool matches(Size size) {
    if (size.width <= 0 || size.height <= 0) return false;
    final a = size.width / size.height;
    return (a / aspect - 1).abs() <= tolerance;
  }

  /// Windows (fractions of the sheet) of its three parts, or null when the
  /// image does not have this layout's proportions.
  ({Rect back, Rect spine, Rect front})? split(Size size) {
    if (!matches(size)) return null;
    final total = 2 * panel + spine;
    final p = panel / total, s = spine / total;
    return (
      back: Rect.fromLTWH(0, 0, p, 1),
      spine: Rect.fromLTWH(p, 0, s, 1),
      front: Rect.fromLTWH(p + s, 0, p, 1),
    );
  }
}

/// Recognises what an image is, from where it came from when that is known,
/// else from its size and transparency (docs/game-box-3d.md § 13).
class GameBoxArtClassifier {
  GameBoxArtClassifier._();

  /// PS3 XMB icon (ICON0.PNG), the size Sony's format fixes.
  static const Size ps3Icon = Size(320, 176);

  /// Provenance types (see [GameBoxFaceRecord.type]) and what they hold.
  static GameBoxArtNature? ofProvenance(String? type) {
    if (type == null || type.isEmpty) return null;
    final t = type.toLowerCase();
    if (t.contains('icon') || t.contains('wheel') || t.contains('marquee') || t.contains('fanart') ||
        t.contains('logo') || t.contains('promo')) {
      return GameBoxArtNature.promo;
    }
    if (t.contains('box-3d') || t.endsWith(':box') || t.contains(':box/') || t.contains('render')) {
      return GameBoxArtNature.render3d;
    }
    if (t.contains('coverfull') || t.contains('box-texture') || t.contains('wrap')) {
      return GameBoxArtNature.wrap;
    }
    if (t.contains('framed')) return GameBoxArtNature.framedCase;
    return GameBoxArtNature.scan;
  }

  /// Nature of a front (or back) image of [size] on [profile].
  ///
  /// [opaqueShare] is the share of opaque pixels when the image has been
  /// decoded (a render or a logo leaves its background transparent).
  static GameBoxArtNature classify({
    required GameBoxProfile profile,
    required Size? size,
    String? provenance,
    double? opaqueShare,
    bool front = true,
  }) {
    final known = ofProvenance(provenance);
    if (known != null) return known;
    if (size == null || size.width <= 0 || size.height <= 0) return GameBoxArtNature.scan;
    // A box already drawn in perspective, or a logo on transparency.
    if (opaqueShare != null && opaqueShare < 0.9 && !profile.adaptsToArt) {
      return GameBoxArtNature.render3d;
    }
    if (profile.id == 'ps3' && size == ps3Icon) return GameBoxArtNature.promo;
    // Cardboard boxes take the proportions of their art; a jewel booklet is
    // drawn contained in its square window.
    if (profile.adaptsToArt || profile.caseKind == GameBoxCaseKind.jewelCase) {
      return GameBoxArtNature.scan;
    }
    final aspect = size.width / size.height;
    final wrap = GameBoxWrapLayout.forProfile(profile);
    if (wrap != null && wrap.matches(size) && size.width >= 600) return GameBoxArtNature.wrap;
    final printed = profile.printedAspect;
    final square = (aspect - 1).abs() < 0.04;
    final side = math.max(size.width, size.height);
    // A square picture is a store or console icon when it is small (title
    // icons are 256 px, HOME menu icons 48 px), or on a portrait case whose
    // print is never square (Switch, PS3, DVD family). A large square scan
    // of a near-square case (3DS, DS) stays a scan. On a case whose print
    // is square (HuCard), a square picture is its cover; only a tiny one is
    // an icon (§ 24).
    if ((printed - 1).abs() < 0.04) {
      if (square && side <= 128) return GameBoxArtNature.promo;
    } else if (square && (side <= 512 || printed < 0.8)) {
      return GameBoxArtNature.promo;
    }
    // Far from the printed area's proportions (a landscape logo on a portrait
    // case): catalogue art, not this case's print.
    if ((math.log(aspect / printed)).abs() > math.log(1.25)) return GameBoxArtNature.promo;
    return GameBoxArtNature.scan;
  }
}
