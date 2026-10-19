import 'dart:math' as math;
import 'dart:ui' show Color;

/// How a game's retail box is built and how it opens.
///
/// The family decides the thickness, where the hinge is and what the inside
/// looks like when the box opens (docs/game-box-3d.md § 2).
enum GameBoxCaseKind {
  /// DVD/Blu-ray style plastic case: the front panel turns around the spine.
  keepCase,

  /// CD jewel case: a thin lid turns around its left edge.
  jewelCase,

  /// Plastic clamshell for cartridges (Mega Drive, Master System, PC Engine):
  /// opens like a book and holds the cartridge.
  clamshell,

  /// Cardboard box: the top flap opens and the cartridge comes out of it.
  cardboard,

  /// No physical box is known (arcade boards, digital stores): a thin card,
  /// no opening.
  flat,
}

/// The physical medium held in the box.
enum GameBoxSupportKind {
  disc,
  miniDisc,
  umd,
  cartridge,
  card,
  hucard,
  floppy,
  cassette,
  none,
}

/// Shape of a cartridge or card, in millimetres (approximate retail sizes).
class GameBoxCartridgeStyle {
  const GameBoxCartridgeStyle({
    required this.id,
    required this.width,
    required this.height,
    required this.thickness,
    required this.bodyColor,
    this.labelRect = const (0.12, 0.08, 0.76, 0.56),
    this.cornerRadius = 4,
    this.cutCorner = false,
    this.gripLines = 0,
  });

  final String id;
  final double width;
  final double height;
  final double thickness;
  final Color bodyColor;

  /// Label area as fractions of the cartridge face: left, top, width, height.
  final (double, double, double, double) labelRect;
  final double cornerRadius;

  /// Bottom-right corner cut (Game Boy style).
  final bool cutCorner;

  /// Number of horizontal grip ridges drawn under the label.
  final int gripLines;
}

/// Size of a disc support in millimetres.
class GameBoxDiscStyle {
  const GameBoxDiscStyle({
    required this.id,
    required this.diameter,
    this.hole = 15,
    this.shell = false,
  });

  final String id;
  final double diameter;
  final double hole;

  /// UMD: the disc sits in a plastic shell.
  final bool shell;
}

/// Everything the 3D box needs to know about one platform's packaging.
class GameBoxProfile {
  const GameBoxProfile({
    required this.id,
    required this.caseKind,
    required this.width,
    required this.height,
    required this.depth,
    required this.support,
    required this.caseColor,
    this.interiorColor,
    this.cartridge,
    this.disc,
    this.lidThickness = 1.6,
    this.cornerRadius = 0,
  });

  final String id;
  final GameBoxCaseKind caseKind;

  /// Outer size in millimetres (width × height × depth/thickness).
  final double width;
  final double height;
  final double depth;
  final GameBoxSupportKind support;
  final Color caseColor;
  final Color? interiorColor;
  final GameBoxCartridgeStyle? cartridge;
  final GameBoxDiscStyle? disc;

  /// Thickness of the opening panel (front panel, jewel lid or flap).
  final double lidThickness;

  /// Rounded corners of the front outline (mm): keep cases are rounded,
  /// jewel cases and cardboard boxes are square.
  final double cornerRadius;

  bool get opens => caseKind != GameBoxCaseKind.flat;

  Color get resolvedInteriorColor => interiorColor ?? caseColor;

  /// The same profile with the front proportions of an actual box image.
  ///
  /// The family keeps its thickness and its width class; the height follows
  /// the image so that a landscape SNES box or a tall PAL Dreamcast box is not
  /// stretched into the family's default. Ratios far outside the family
  /// (corrupt or cropped images) are clamped.
  GameBoxProfile withFrontAspect(double? aspect) {
    if (aspect == null || !aspect.isFinite || aspect <= 0) return this;
    // A jewel case has one size whatever its insert: the square front
    // booklet sits beside the hinge. Only tall inserts (long Saturn boxes,
    // tall PAL Dreamcast cases) change the case.
    if (caseKind == GameBoxCaseKind.jewelCase && aspect >= 0.8) return this;
    final clamped = aspect.clamp(0.45, 1.9);
    // Keep the area of the family's default front, so that a landscape box of
    // the same family does not become huge.
    final area = width * height;
    final newWidth = math.sqrt(area * clamped);
    final newHeight = newWidth / clamped;
    return GameBoxProfile(
      id: id,
      caseKind: caseKind,
      width: newWidth,
      height: newHeight,
      depth: depth,
      support: support,
      caseColor: caseColor,
      interiorColor: interiorColor,
      cartridge: cartridge,
      disc: disc,
      lidThickness: lidThickness,
      cornerRadius: cornerRadius,
    );
  }

  /// Front booklet area of a jewel case lid (mm, in the lid's front face):
  /// right of the hinge band, with the clear plastic margins of the real case.
  static const jewelHinge = 8.0;

  /// Profile for a NeoStation system id (`assets/systems/<id>.json`), with
  /// the system's declared media types as a fallback for systems that have no
  /// dedicated entry.
  static GameBoxProfile forSystem(String? systemId, {List<String> media = const []}) {
    final id = (systemId ?? '').toLowerCase().replaceAll('-hacks', '');
    final direct = _bySystem[id];
    if (direct != null) return direct;
    for (final m in media) {
      switch (m) {
        case 'blu_ray':
          return _bluRay(id, const Color(0xFF1C3C78));
        case 'dvd':
        case 'optical_disc':
          return _dvd(id, const Color(0xFF151515));
        case 'umd':
          return _umd(id);
        case 'cd_rom':
        case 'gd_rom':
          return _jewel(id);
        case 'cartridge':
          return _cardboard(id, _cartGeneric);
        case 'hucard':
        case 'card':
          return _clamshell(id, const Color(0xFF1A1A1A), _hucard,
              support: GameBoxSupportKind.hucard);
        case 'floppy':
          return _computer(id, GameBoxSupportKind.floppy);
        case 'cassette':
          return _computer(id, GameBoxSupportKind.cassette);
      }
    }
    return _flat(id);
  }

  // Cartridges ----------------------------------------------------------------

  static const _cartGeneric = GameBoxCartridgeStyle(
    id: 'generic', width: 100, height: 80, thickness: 18,
    bodyColor: Color(0xFF3A3A3E), gripLines: 3,
  );
  static const _cartNes = GameBoxCartridgeStyle(
    id: 'nes', width: 120, height: 133, thickness: 18,
    bodyColor: Color(0xFF8E8E8E), labelRect: (0.10, 0.07, 0.80, 0.52),
    cornerRadius: 3, gripLines: 5,
  );
  static const _cartFc = GameBoxCartridgeStyle(
    id: 'fc', width: 70, height: 108, thickness: 15,
    bodyColor: Color(0xFFB7322C), labelRect: (0.10, 0.10, 0.80, 0.62),
    cornerRadius: 5,
  );
  static const _cartSnes = GameBoxCartridgeStyle(
    id: 'snes', width: 128, height: 92, thickness: 20,
    bodyColor: Color(0xFF9C9CA3), labelRect: (0.14, 0.10, 0.72, 0.58),
    cornerRadius: 10, gripLines: 2,
  );
  static const _cartN64 = GameBoxCartridgeStyle(
    id: 'n64', width: 116, height: 75, thickness: 20,
    bodyColor: Color(0xFF4A4A50), labelRect: (0.11, 0.08, 0.78, 0.66),
    cornerRadius: 9,
  );
  static const _cartGb = GameBoxCartridgeStyle(
    id: 'gb', width: 57, height: 65, thickness: 8,
    bodyColor: Color(0xFFA7A6A1), labelRect: (0.13, 0.17, 0.74, 0.55),
    cornerRadius: 3, cutCorner: true,
  );
  static const _cartGba = GameBoxCartridgeStyle(
    id: 'gba', width: 57, height: 35, thickness: 8,
    bodyColor: Color(0xFF6F6F78), labelRect: (0.10, 0.14, 0.80, 0.62),
    cornerRadius: 4,
  );
  static const _cartMd = GameBoxCartridgeStyle(
    id: 'md', width: 118, height: 83, thickness: 20,
    bodyColor: Color(0xFF151515), labelRect: (0.12, 0.10, 0.76, 0.62),
    cornerRadius: 4, gripLines: 3,
  );
  static const _cartSms = GameBoxCartridgeStyle(
    id: 'sms', width: 92, height: 68, thickness: 18,
    bodyColor: Color(0xFF1A1A1A), labelRect: (0.10, 0.10, 0.80, 0.62),
    cornerRadius: 3,
  );
  static const _cartGg = GameBoxCartridgeStyle(
    id: 'gg', width: 70, height: 50, thickness: 10,
    bodyColor: Color(0xFF1A1A1A), labelRect: (0.12, 0.12, 0.76, 0.62),
    cornerRadius: 3,
  );
  static const _cart2600 = GameBoxCartridgeStyle(
    id: '2600', width: 80, height: 104, thickness: 22,
    bodyColor: Color(0xFF1B1B1B), labelRect: (0.08, 0.06, 0.84, 0.52),
    cornerRadius: 4, gripLines: 6,
  );
  static const _cardDs = GameBoxCartridgeStyle(
    id: 'ds', width: 33, height: 35, thickness: 3.8,
    bodyColor: Color(0xFF2F2F33), labelRect: (0.08, 0.20, 0.84, 0.74),
    cornerRadius: 1.5,
  );
  static const _card3ds = GameBoxCartridgeStyle(
    id: '3ds', width: 33, height: 35, thickness: 3.8,
    bodyColor: Color(0xFFE9E9EA), labelRect: (0.08, 0.20, 0.84, 0.74),
    cornerRadius: 1.5,
  );
  static const _cardSwitch = GameBoxCartridgeStyle(
    id: 'switch', width: 21, height: 31, thickness: 3.3,
    bodyColor: Color(0xFF2B2B2E), labelRect: (0.10, 0.08, 0.80, 0.72),
    cornerRadius: 1.5,
  );
  static const _cardVita = GameBoxCartridgeStyle(
    id: 'vita', width: 22, height: 30, thickness: 2.0,
    bodyColor: Color(0xFF26262A), labelRect: (0.10, 0.10, 0.80, 0.70),
    cornerRadius: 1.5,
  );
  static const _hucard = GameBoxCartridgeStyle(
    id: 'hucard', width: 54, height: 85, thickness: 1.6,
    bodyColor: Color(0xFFDADAD6), labelRect: (0.10, 0.08, 0.80, 0.64),
    cornerRadius: 3,
  );
  static const _cartLynx = GameBoxCartridgeStyle(
    id: 'lynx', width: 52, height: 34, thickness: 4,
    bodyColor: Color(0xFF2A2A2A), labelRect: (0.10, 0.12, 0.80, 0.70),
    cornerRadius: 3,
  );

  // Families ------------------------------------------------------------------

  static GameBoxProfile _dvd(String id, Color color,
          {GameBoxDiscStyle disc = _dvdDisc, double width = 135, double height = 190}) =>
      GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.keepCase,
        width: width, height: height, depth: 14,
        support: disc.diameter < 100 ? GameBoxSupportKind.miniDisc : GameBoxSupportKind.disc,
        caseColor: color, disc: disc, lidThickness: 2, cornerRadius: 4.5,
      );

  static GameBoxProfile _bluRay(String id, Color color) => GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.keepCase,
        width: 135, height: 170, depth: 12,
        support: GameBoxSupportKind.disc, caseColor: color,
        disc: const GameBoxDiscStyle(id: 'bd', diameter: 120), lidThickness: 2,
        cornerRadius: 4,
      );

  static GameBoxProfile _jewel(String id, {Color color = const Color(0xFF202024)}) =>
      GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.jewelCase,
        width: 142, height: 125, depth: 10,
        support: GameBoxSupportKind.disc, caseColor: color,
        interiorColor: const Color(0xFF16161A),
        disc: const GameBoxDiscStyle(id: 'cd', diameter: 120), lidThickness: 2.4,
      );

  static GameBoxProfile _umd(String id) => GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.keepCase,
        width: 104, height: 180, depth: 13,
        support: GameBoxSupportKind.umd, caseColor: const Color(0xFF1D1D21),
        disc: const GameBoxDiscStyle(id: 'umd', diameter: 60, hole: 11, shell: true),
        lidThickness: 2, cornerRadius: 6,
      );

  static GameBoxProfile _handheld(String id, Color color, GameBoxCartridgeStyle card,
          {double width = 125, double height = 137, double depth = 14, double radius = 7}) =>
      GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.keepCase,
        width: width, height: height, depth: depth,
        support: GameBoxSupportKind.card, caseColor: color, cartridge: card,
        lidThickness: 1.8, cornerRadius: radius,
      );

  static GameBoxProfile _cardboard(String id, GameBoxCartridgeStyle cart,
          {double width = 150, double height = 200, double depth = 36}) =>
      GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.cardboard,
        width: width, height: height, depth: depth,
        support: GameBoxSupportKind.cartridge,
        caseColor: const Color(0xFFD9D2C3),
        interiorColor: const Color(0xFFBDB29C),
        cartridge: cart, lidThickness: 0.6,
      );

  static GameBoxProfile _clamshell(String id, Color color, GameBoxCartridgeStyle cart,
          {GameBoxSupportKind support = GameBoxSupportKind.cartridge,
          double width = 135, double height = 190, double depth = 27}) =>
      GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.clamshell,
        width: width, height: height, depth: depth,
        support: support, caseColor: color, cartridge: cart, lidThickness: 2.2,
        cornerRadius: width > 138 ? 0 : 3,
      );

  static GameBoxProfile _computer(String id, GameBoxSupportKind support) => GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.cardboard,
        width: 150, height: 210, depth: 32, support: support,
        caseColor: const Color(0xFFD9D2C3), interiorColor: const Color(0xFFBDB29C),
        lidThickness: 0.6,
      );

  static GameBoxProfile _flat(String id) => GameBoxProfile(
        id: id, caseKind: GameBoxCaseKind.flat,
        width: 135, height: 190, depth: 3,
        support: GameBoxSupportKind.none, caseColor: const Color(0xFF26262B),
        cornerRadius: 2,
      );

  static const _dvdDisc = GameBoxDiscStyle(id: 'dvd', diameter: 120);

  static final Map<String, GameBoxProfile> _bySystem = {
    // Discs in DVD/Blu-ray cases.
    'ps2': _dvd('ps2', const Color(0xFF141416)),
    'ps3': _bluRay('ps3', const Color(0xFF1E3F7A)),
    'xbox': _dvd('xbox', const Color(0xFF173A17)),
    'xbox360': _dvd('xbox360', const Color(0xFF2E7D32)),
    'wii': _dvd('wii', const Color(0xFFEDEDED)),
    'wiiu': _dvd('wiiu', const Color(0xFF1E5AA8)),
    'gc': _dvd('gc', const Color(0xFF141416),
        disc: const GameBoxDiscStyle(id: 'gc', diameter: 80, hole: 15),
        width: 130, height: 184),
    'triforce': _dvd('triforce', const Color(0xFF141416),
        disc: const GameBoxDiscStyle(id: 'gc', diameter: 80, hole: 15),
        width: 130, height: 184),
    'psp': _umd('psp'),
    // CD jewel cases.
    'ps1': _jewel('ps1'),
    'sat': _jewel('sat'),
    'dc': _jewel('dc'),
    'mcd': _jewel('mcd'),
    'scd': _jewel('scd'),
    '3do': _jewel('3do'),
    'cdi': _jewel('cdi'),
    'pccd': _jewel('pccd'),
    'tgcd': _jewel('tgcd'),
    'ngcd': _jewel('ngcd'),
    'pcfx': _jewel('pcfx'),
    'jagcd': _jewel('jagcd'),
    'naomigd': _jewel('naomigd'),
    // Handheld card cases.
    'ds': _handheld('ds', const Color(0xFFEEEEEE), _cardDs),
    '3ds': _handheld('3ds', const Color(0xFFEDEDED), _card3ds, depth: 11),
    'switch': _handheld('switch', const Color(0xFFD7262E), _cardSwitch,
        width: 105, height: 170, depth: 11, radius: 4),
    'vita': _handheld('vita', const Color(0xFF2A4E9B), _cardVita,
        width: 105, height: 135, depth: 12, radius: 5),
    // Cartridges in plastic clamshells.
    'md': _clamshell('md', const Color(0xFF111111), _cartMd),
    'genesis': _clamshell('genesis', const Color(0xFF111111), _cartMd),
    '32x': _clamshell('32x', const Color(0xFF111111), _cartMd),
    'sms': _clamshell('sms', const Color(0xFF111111), _cartSms),
    'mark3': _clamshell('mark3', const Color(0xFF111111), _cartSms),
    'pico': _clamshell('pico', const Color(0xFF111111), _cartMd),
    'pce': _clamshell('pce', const Color(0xFF1A1A1A), _hucard,
        support: GameBoxSupportKind.hucard, width: 142, height: 125, depth: 10),
    'tg16': _clamshell('tg16', const Color(0xFF1A1A1A), _hucard,
        support: GameBoxSupportKind.hucard),
    // Cartridges in cardboard boxes.
    'nes': _cardboard('nes', _cartNes, width: 127, height: 178, depth: 30),
    'fc': _cardboard('fc', _cartFc, width: 120, height: 170, depth: 25),
    'fds': _computer('fds', GameBoxSupportKind.floppy),
    'snes': _cardboard('snes', _cartSnes, width: 180, height: 128, depth: 35),
    'sfc': _cardboard('sfc', _cartSnes, width: 180, height: 128, depth: 35),
    'satellaview': _cardboard('satellaview', _cartSnes, width: 180, height: 128, depth: 35),
    'n64': _cardboard('n64', _cartN64, width: 225, height: 160, depth: 40),
    'gb': _cardboard('gb', _cartGb, width: 105, height: 105, depth: 25),
    'gbc': _cardboard('gbc', _cartGb, width: 105, height: 105, depth: 25),
    'gba': _cardboard('gba', _cartGba, width: 118, height: 118, depth: 25),
    'vb': _cardboard('vb', _cartGb, width: 150, height: 150, depth: 30),
    'gg': _cardboard('gg', _cartGg, width: 115, height: 150, depth: 25),
    'lynx': _cardboard('lynx', _cartLynx, width: 135, height: 175, depth: 25),
    'ngp': _cardboard('ngp', _cartGba, width: 110, height: 140, depth: 22),
    'ngpc': _cardboard('ngpc', _cartGba, width: 110, height: 140, depth: 22),
    'ws': _cardboard('ws', _cartGba, width: 110, height: 140, depth: 22),
    'wsc': _cardboard('wsc', _cartGba, width: 110, height: 140, depth: 22),
    '2600': _cardboard('2600', _cart2600, width: 145, height: 200, depth: 40),
    '5200': _cardboard('5200', _cart2600, width: 145, height: 200, depth: 40),
    '7800': _cardboard('7800', _cart2600, width: 145, height: 200, depth: 40),
    'jag': _cardboard('jag', _cartGeneric, width: 150, height: 210, depth: 40),
    'neogeo': _cardboard('neogeo', _cartGeneric, width: 230, height: 300, depth: 70),
  };
}
