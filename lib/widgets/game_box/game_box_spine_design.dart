import 'package:flutter/material.dart';

import 'package:neostation/services/game_box/game_box_profile.dart';

/// What the sides of a real box look like when no scan shows them
/// (docs/game-box-3d.md § 27).
///
/// The spine of a game case is a template of its platform: a Wii spine is
/// white with the grey Wii mark at its top and the title in dark type, a
/// GameCube spine black with the NINTENDO GAMECUBE mark and the title in
/// white capitals, a Wii U spine blue with a white head holding the Wii U
/// mark… A cardboard box prints its spine on both long sides and its title
/// on the top flap, in the colours of its own print. The marks are the
/// platform logos the app already shows (assets/images/logos, used to
/// identify the platform, see TRADEMARKS.md there).
@immutable
class GameBoxSpineDesign {
  const GameBoxSpineDesign({
    required this.background,
    required this.ink,
    this.logo,
    this.logoInk,
    this.head,
    this.headMm = 30,
    this.uppercase = false,
    this.gameLogo = false,
  });

  /// Colour of the spine.
  final Color background;

  /// Colour of the title.
  final Color ink;

  /// Platform logo (`assets/images/logos/<logo>.webp`), at the top.
  final String? logo;
  final Color? logoInk;

  /// Colour of a band behind the logo (null: the spine's colour).
  final Color? head;

  /// Length of the logo's place at the top of the spine, in millimetres.
  final double headMm;

  /// Title in capitals (GameCube, PlayStation 2).
  final bool uppercase;

  /// The game's own logo (scraped "wheel") stands for the title when there
  /// is one, as on cartridge boxes; game cases print the title as type.
  final bool gameLogo;

  /// Platform logos shipped in assets/images/logos.
  static const Set<String> logos = {
    '2600', '32x', '3do', '3ds', '5200', '7800', 'a2', 'amiga', 'cdi', 'dc', 'ds', 'fc', 'fds', 'gb', 'gba',
    'gbc', 'gc', 'genesis', 'gg', 'jag', 'jagcd', 'lynx', 'mcd', 'md', 'n64', 'neogeo', 'nes', 'ngcd', 'ngp',
    'ngpc', 'pccd', 'pce', 'pcfx', 'ps1', 'ps2', 'ps3', 'psp', 'sat', 'satellaview', 'scd', 'sfc', 'sms',
    'snes', 'switch', 'switch2', 'tg16', 'tgcd', 'vb', 'vita', 'wii', 'wiiu', 'ws', 'wsc', 'xbox', 'xbox360',
  };

  static const Color _white = Color(0xFFFFFFFF);
  static const Color _black = Color(0xFF0D0D10);
  static const Color _darkInk = Color(0xFF262628);

  /// The spine of [profile]'s platform. [print] is the colour of the
  /// cover's own border (cardboard boxes, cartridge cases), used where the
  /// spine follows the print rather than a platform template.
  static GameBoxSpineDesign of(GameBoxProfile profile, {Color? print}) {
    switch (profile.id) {
      case 'wii':
        return const GameBoxSpineDesign(
            background: _white, ink: Color(0xFF3A3A3C), logo: 'wii', logoInk: Color(0xFF9C9C9E), headMm: 28);
      case 'gc':
      case 'triforce':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'gc', logoInk: _white, headMm: 44, uppercase: true);
      case 'wiiu':
        return const GameBoxSpineDesign(
            background: Color(0xFF0098C8), ink: _white, logo: 'wiiu', logoInk: Color(0xFF0098C8),
            head: _white, headMm: 30, uppercase: true);
      case 'ps2':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'ps2', logoInk: _white, headMm: 34, uppercase: true, gameLogo: true);
      case 'ps3':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'ps3', logoInk: _white, head: Color(0xFF000000), headMm: 30,
            gameLogo: true);
      case 'psp':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'psp', logoInk: _white, headMm: 26, gameLogo: true);
      case 'vita':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: 'vita', logoInk: _white, head: _black, headMm: 22);
      case 'xbox':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'xbox', logoInk: _white, head: Color(0xFF3E8E2C), headMm: 34,
            gameLogo: true);
      case 'xbox360':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: 'xbox360', logoInk: _white, head: Color(0xFF5DAE2E),
            headMm: 34, gameLogo: true);
      case 'ds':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: 'ds', logoInk: Color(0xFF808082), headMm: 26);
      case '3ds':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: '3ds', logoInk: _white, head: Color(0xFFD7001D), headMm: 24);
      case 'ps1':
        return const GameBoxSpineDesign(
            background: _black, ink: _white, logo: 'ps1', logoInk: _white, headMm: 24, gameLogo: true);
      case 'switch':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: 'switch', logoInk: _white, head: Color(0xFFE60012), headMm: 26);
      // The Switch spine with the Switch 2 logo.
      case 'switch2':
        return const GameBoxSpineDesign(
            background: _white, ink: _darkInk, logo: 'switch2', logoInk: _white, head: Color(0xFFE60012), headMm: 26);
    }
    // Other platforms: the cover's own colour (a black NES border, a grey
    // SNES frame…), the platform's mark at the top, the game's logo.
    final background = print ??
        (profile.caseKind == GameBoxCaseKind.jewelCase ? _black : profile.resolvedInsertColor);
    final ink = _contrast(background);
    return GameBoxSpineDesign(
      background: background,
      ink: ink,
      logo: logos.contains(profile.id) ? profile.id : null,
      logoInk: ink.withValues(alpha: 0.9),
      headMm: profile.caseKind == GameBoxCaseKind.cardboard ? 34 : 28,
      gameLogo: true,
    );
  }

  static Color _contrast(Color c) => c.computeLuminance() > 0.45 ? const Color(0xFF1E1E20) : _white;

  String? get logoAsset => logo == null ? null : 'assets/images/logos/$logo.webp';
}

/// A spine drawn from its platform's template (§ 27): standing, top at the
/// top, its type running from top to bottom like a printed spine.
class GameBoxDesignedSpine extends StatelessWidget {
  const GameBoxDesignedSpine({
    super.key,
    required this.design,
    required this.title,
    this.gameLogo,
    this.heightMm,
    this.compact = false,
  });

  final GameBoxSpineDesign design;
  final String title;

  /// The game's own logo, drawn instead of the title when the design takes it.
  final ImageProvider? gameLogo;

  /// Real length of the spine (null: the head takes a sixth of it).
  final double? heightMm;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: design.background,
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth, h = c.maxHeight;
        if (w < 1 || h < 1) return const SizedBox.expand();
        final mm = heightMm != null && heightMm! > 0 ? h / heightMm! : h / 180;
        final head = (design.logo == null ? 0.0 : design.headMm * mm).clamp(0.0, h * 0.4).toDouble();
        final gap = w * 0.35;
        final titleTop = head + gap;
        final titleLength = h - titleTop - gap;
        final logoAsset = design.logoAsset;
        return Stack(children: [
          if (head > 0 && design.head != null)
            Positioned(left: 0, top: 0, width: w, height: head, child: ColoredBox(color: design.head!)),
          if (head > 0 && logoAsset != null)
            Positioned(
              left: w * 0.14,
              top: head * 0.1,
              width: w * 0.72,
              height: head * 0.8,
              child: _Turned(
                child: Image.asset(
                  logoAsset,
                  color: design.logoInk ?? design.ink,
                  fit: BoxFit.contain,
                  filterQuality: FilterQuality.medium,
                  errorBuilder: (_, _, _) => const SizedBox.shrink(),
                ),
              ),
            ),
          if (!compact && titleLength > 4)
            Positioned(
              left: w * 0.12,
              top: titleTop,
              width: w * 0.76,
              height: titleLength,
              child: _Turned(child: _title(context)),
            ),
        ]);
      }),
    );
  }

  Widget _title(BuildContext context) {
    final text = design.uppercase ? title.toUpperCase() : title;
    final type = LayoutBuilder(builder: (context, c) {
      final size = (c.maxHeight * 0.62).clamp(3.0, 40.0).toDouble();
      // A long title is set smaller, never cut, as printers do.
      return FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.centerLeft,
        child: Text(
          text,
          maxLines: 1,
          softWrap: false,
          style: TextStyle(
            fontSize: size,
            height: 1,
            color: design.ink,
            fontWeight: design.uppercase ? FontWeight.w800 : FontWeight.w600,
            letterSpacing: design.uppercase ? 0.4 : 0.1,
          ),
        ),
      );
    });
    final logo = gameLogo;
    if (!design.gameLogo || logo == null) return type;
    return Image(
      image: logo,
      fit: BoxFit.contain,
      alignment: Alignment.center,
      filterQuality: FilterQuality.medium,
      gaplessPlayback: true,
      excludeFromSemantics: true,
      errorBuilder: (_, _, _) => type,
    );
  }
}

/// A child laid out lying (its width along the spine), then turned a quarter
/// clockwise to read from top to bottom.
class _Turned extends StatelessWidget {
  const _Turned({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => RotatedBox(quarterTurns: 1, child: child);
}

/// The top or bottom flap of a cardboard box (§ 27). The top flap shows the
/// spine laid along it (the spine scan when there is one, else its
/// template), as the title flap of a real box; the bottom flap keeps the
/// colour of the print and the platform's mark.
class GameBoxCardboardFlap extends StatelessWidget {
  const GameBoxCardboardFlap({
    super.key,
    required this.design,
    required this.spine,
    required this.spineAspect,
    this.top = true,
    this.compact = false,
  });

  final GameBoxSpineDesign design;

  /// The standing spine (scan or template).
  final Widget spine;

  /// Width / height of the standing spine (depth / height of the box).
  final double spineAspect;
  final bool top;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: design.background,
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth, h = c.maxHeight;
        if (w < 1 || h < 1 || compact) return const SizedBox.expand();
        if (top) {
          // The spine lying along the flap, its top on the left, whole.
          final aspect = spineAspect.isFinite && spineAspect > 0 ? spineAspect : 0.15;
          return Center(
            child: FittedBox(
              fit: BoxFit.contain,
              child: SizedBox(
                width: 1000,
                height: 1000 * aspect,
                child: RotatedBox(quarterTurns: 3, child: spine),
              ),
            ),
          );
        }
        final logoAsset = design.logoAsset;
        if (logoAsset == null) return const SizedBox.expand();
        return Align(
          alignment: const Alignment(-0.8, 0),
          child: SizedBox(
            width: h * 1.6,
            height: h * 0.6,
            child: Opacity(
              opacity: 0.85,
              child: Image.asset(
                logoAsset,
                color: design.logoInk ?? design.ink,
                fit: BoxFit.contain,
                filterQuality: FilterQuality.medium,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
          ),
        );
      }),
    );
  }
}
