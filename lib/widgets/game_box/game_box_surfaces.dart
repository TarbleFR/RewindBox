import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'package:neostation/services/game_box/game_box_profile.dart';

/// Neutral surfaces of the 3D box: what is drawn when a scan is missing.
///
/// None of them imitates a scan. A missing back is a plain surface with a
/// discreet notice, a missing spine shows the known title in plain type, a
/// missing support label leaves a blank, neutral label (docs/game-box-3d.md
/// § 5).
class GameBoxNeutralFace extends StatelessWidget {
  const GameBoxNeutralFace({
    super.key,
    required this.color,
    this.notice,
    this.icon,
  });

  final Color color;
  final String? notice;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final onColor = _onColor(color);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: onColor.withValues(alpha: 0.10), width: 1),
      ),
      child: notice == null
          ? const SizedBox.expand()
          : LayoutBuilder(builder: (context, c) {
              final size = (c.maxWidth * 0.07).clamp(7.0, 15.0);
              return Center(
                child: Padding(
                  padding: EdgeInsets.all(c.maxWidth * 0.08),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (icon != null)
                        Icon(icon, size: size * 2.2, color: onColor.withValues(alpha: 0.35)),
                      SizedBox(height: size * 0.5),
                      Text(
                        notice!,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: size,
                          color: onColor.withValues(alpha: 0.55),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
    );
  }
}

/// A spine without scan: case colour and the title, reading top to bottom.
class GameBoxTitleSpine extends StatelessWidget {
  const GameBoxTitleSpine({super.key, required this.color, required this.title});

  final Color color;
  final String title;

  @override
  Widget build(BuildContext context) {
    final onColor = _onColor(color);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: onColor.withValues(alpha: 0.10), width: 1),
      ),
      child: LayoutBuilder(builder: (context, c) {
        final size = (c.maxWidth * 0.42).clamp(5.0, 18.0);
        return RotatedBox(
          quarterTurns: 1,
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: c.maxHeight * 0.06),
            child: Center(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: size,
                  color: onColor.withValues(alpha: 0.85),
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.3,
                ),
              ),
            ),
          ),
        );
      }),
    );
  }
}

/// Inside of the box once open: the tray of a plastic case (hub with its
/// gripping teeth, card slot) or the inside of a cardboard box.
class GameBoxInteriorPainter extends CustomPainter {
  GameBoxInteriorPainter({
    required this.kind,
    required this.color,
    this.hub = true,
    this.teeth = true,
    this.cardSlot = false,
  });

  final GameBoxCaseKind kind;
  final Color color;
  final bool hub;
  final bool teeth;
  final bool cardSlot;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    if (kind == GameBoxCaseKind.cardboard) {
      // Looking into the box through its top: dark cardboard.
      canvas.drawRect(
        rect,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [_shade(color, 0.42), _shade(color, 0.26)],
          ).createShader(rect),
      );
      return;
    }
    canvas.drawRect(rect, Paint()..color = _shade(color, 0.86));
    final unit = size.shortestSide;
    // Moulded tray border.
    final inset = unit * 0.035;
    final tray = RRect.fromRectAndRadius(rect.deflate(inset), Radius.circular(inset));
    canvas.drawRRect(
      tray,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = math.max(1, inset * 0.3)
        ..color = _lift(color, 0.10),
    );
    if (cardSlot) {
      // Cartridge clip in the upper right (DS, 3DS, Switch, Vita cases).
      final slot = Rect.fromCenter(
        center: Offset(size.width * 0.68, size.height * 0.38),
        width: size.width * 0.34,
        height: size.height * 0.30,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(slot, Radius.circular(unit * 0.02)),
        Paint()..color = _shade(color, 0.70),
      );
    }
    if (!hub) return;
    final c = rect.center;
    final r = unit * 0.085;
    canvas.drawCircle(c, r * 2.1, Paint()..color = _shade(color, 0.74));
    canvas.drawCircle(
      c,
      r * 2.1,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = math.max(0.8, unit * 0.004)
        ..color = _lift(color, 0.12),
    );
    canvas.drawCircle(c, r, Paint()..color = _lift(color, 0.06));
    if (teeth) {
      // The flexible teeth of the hub that hold the disc.
      final paint = Paint()
        ..strokeWidth = math.max(0.8, unit * 0.006)
        ..color = _shade(color, 0.55);
      for (var i = 0; i < 12; i++) {
        final a = i * math.pi / 6;
        canvas.drawLine(
          c + Offset(math.cos(a), math.sin(a)) * (r * 0.35),
          c + Offset(math.cos(a), math.sin(a)) * r,
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(GameBoxInteriorPainter old) =>
      old.kind != kind || old.color != color || old.hub != hub ||
      old.teeth != teeth || old.cardSlot != cardSlot;
}

/// Inside of the opening panel: the booklet clips of a keep case, the clear
/// lid of a jewel case, the flap of a cardboard box.
class GameBoxLidInnerPainter extends CustomPainter {
  GameBoxLidInnerPainter({required this.kind, required this.color});
  final GameBoxCaseKind kind;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    switch (kind) {
      case GameBoxCaseKind.cardboard:
        canvas.drawRect(rect, Paint()..color = _shade(color, 0.92));
        return;
      case GameBoxCaseKind.jewelCase:
        canvas.drawRect(rect, Paint()..color = Color.lerp(color, const Color(0xFF9097A0), 0.18)!);
        // The four tabs that hold the booklet.
        final tab = Paint()..color = _lift(color, 0.20);
        final w = size.width * 0.05, h = size.height * 0.035;
        for (final o in [
          Offset(size.width * 0.12, size.height * 0.04),
          Offset(size.width * 0.12, size.height * 0.925),
          Offset(size.width * 0.83, size.height * 0.04),
          Offset(size.width * 0.83, size.height * 0.925),
        ]) {
          canvas.drawRect(o & Size(w, h), tab);
        }
        return;
      default:
        canvas.drawRect(rect, Paint()..color = _shade(color, 0.90));
        // Two clips for the manual.
        final clip = Paint()..color = _lift(color, 0.14);
        final w = size.width * 0.18, h = size.height * 0.02;
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.41, size.height * 0.06, w, h),
            Radius.circular(h / 2),
          ),
          clip,
        );
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.41, size.height * 0.92, w, h),
            Radius.circular(h / 2),
          ),
          clip,
        );
    }
  }

  @override
  bool shouldRepaint(GameBoxLidInnerPainter old) => old.kind != kind || old.color != color;
}

/// Hinge band of a jewel case lid, on the left of the booklet.
class GameBoxJewelHingePainter extends CustomPainter {
  const GameBoxJewelHingePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = const Color(0x5C000000));
    final line = Paint()
      ..strokeWidth = math.max(0.6, size.width * 0.06)
      ..color = const Color(0x33FFFFFF);
    canvas.drawLine(Offset(size.width * 0.35, 0), Offset(size.width * 0.35, size.height), line);
    canvas.drawLine(Offset(size.width * 0.92, 0), Offset(size.width * 0.92, size.height), line);
  }

  @override
  bool shouldRepaint(GameBoxJewelHingePainter old) => false;
}

/// The two hinge knuckles at the ends of a jewel case's hinge side.
class GameBoxJewelKnucklePainter extends CustomPainter {
  const GameBoxJewelKnucklePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = const Color(0x8C0E0E10);
    final h = size.height * 0.085;
    final w = size.width * 0.42;
    canvas.drawRect(Rect.fromLTWH(size.width - w, 0, w, h), paint);
    canvas.drawRect(Rect.fromLTWH(size.width - w, size.height - h, w, h), paint);
    final hi = Paint()
      ..strokeWidth = 0.8
      ..color = const Color(0x40FFFFFF);
    canvas.drawLine(Offset(size.width - w, h), Offset(size.width, h), hi);
    canvas.drawLine(Offset(size.width - w, size.height - h), Offset(size.width, size.height - h), hi);
  }

  @override
  bool shouldRepaint(GameBoxJewelKnucklePainter old) => false;
}

/// Edges of plastic cases (grip ridges on the opening side, sleeve seam on
/// top and bottom) and folded cardboard.
class GameBoxEdgePainter extends CustomPainter {
  GameBoxEdgePainter({
    required this.color,
    this.ridged = false,
    this.seam = false,
    this.cardboard = false,
    this.pxPerMm = 1,
  });

  final Color color;
  final bool ridged;
  final bool seam;
  final bool cardboard;
  final double pxPerMm;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = color);
    final dark = Paint()
      ..strokeWidth = math.max(0.6, pxPerMm * 0.25)
      ..color = _shade(color, 0.72);
    final light = Paint()
      ..strokeWidth = math.max(0.6, pxPerMm * 0.2)
      ..color = _lift(color, 0.12);
    if (cardboard) {
      // Folded edges of the cardboard.
      canvas.drawLine(rect.topLeft, rect.topRight, light);
      canvas.drawLine(rect.bottomLeft, rect.bottomRight, dark);
      return;
    }
    if (ridged) {
      // Vertical grip ridges along the middle of the opening side.
      final step = math.max(2.0, pxPerMm * 1.4);
      final top = size.height * 0.3, bottom = size.height * 0.7;
      for (var y = top; y < bottom; y += step) {
        canvas.drawLine(Offset(size.width * 0.2, y), Offset(size.width * 0.8, y), dark);
      }
    }
    if (seam) {
      // Where the clear sleeve meets the case.
      canvas.drawLine(
        Offset(size.width * 0.5, 0),
        Offset(size.width * 0.5, size.height),
        dark,
      );
    }
    canvas.drawLine(rect.topLeft, rect.bottomLeft, light);
  }

  @override
  bool shouldRepaint(GameBoxEdgePainter old) =>
      old.color != color || old.ridged != ridged || old.seam != seam ||
      old.cardboard != cardboard || old.pxPerMm != pxPerMm;
}

/// A disc, with its original art when one is known.
///
/// The art (a `support-2D` scan, round with a transparent outside) is clipped
/// to the disc; without art the disc is plain silver with a blank label, never
/// presented as the original print.
class GameBoxDiscFace extends StatelessWidget {
  const GameBoxDiscFace({super.key, required this.style, this.art});

  final GameBoxDiscStyle style;
  final ImageProvider? art;

  @override
  Widget build(BuildContext context) {
    final holeFraction = style.hole / style.diameter;
    Widget disc = CustomPaint(
      painter: _DiscPainter(holeFraction: holeFraction, plain: art == null),
      child: art == null
          ? null
          : ClipPath(
              clipper: _RingClipper(holeFraction),
              child: Image(
                image: art!,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                filterQuality: FilterQuality.medium,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
    );
    if (style.shell) {
      disc = CustomPaint(
        painter: _UmdShellPainter(),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 5, 4, 9),
          child: disc,
        ),
      );
    }
    return disc;
  }
}

class _RingClipper extends CustomClipper<Path> {
  _RingClipper(this.hole);
  final double hole;

  @override
  Path getClip(Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    return Path()
      ..fillType = PathFillType.evenOdd
      ..addOval(Rect.fromCircle(center: c, radius: r))
      ..addOval(Rect.fromCircle(center: c, radius: r * hole));
  }

  @override
  bool shouldReclip(_RingClipper old) => old.hole != hole;
}

class _DiscPainter extends CustomPainter {
  _DiscPainter({required this.holeFraction, required this.plain});
  final double holeFraction;
  final bool plain;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final rect = Rect.fromCircle(center: c, radius: r);
    canvas.drawCircle(
      c,
      r,
      Paint()
        ..shader = const SweepGradient(
          colors: [
            Color(0xFFCFD3D8), Color(0xFFF2F4F6), Color(0xFFB9BEC6),
            Color(0xFFE6E9ED), Color(0xFFC3C8CF), Color(0xFFCFD3D8),
          ],
        ).createShader(rect),
    );
    if (plain) {
      // Blank label: neutral, so that it cannot pass for the original print.
      canvas.drawCircle(c, r * 0.94, Paint()..color = const Color(0xFFE9EAEC));
      canvas.drawCircle(
        c,
        r * 0.94,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = math.max(0.6, r * 0.01)
          ..color = const Color(0xFFB3B8BF),
      );
    }
    // Clamping ring and hole.
    canvas.drawCircle(c, r * holeFraction * 2.2, Paint()..color = const Color(0x33FFFFFF));
    canvas.drawCircle(c, r * holeFraction, Paint()..color = const Color(0xFF2A2A2E));
  }

  @override
  bool shouldRepaint(_DiscPainter old) =>
      old.holeFraction != holeFraction || old.plain != plain;
}

class _UmdShellPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final path = Path()
      ..moveTo(rect.left, rect.top + size.height * 0.12)
      ..quadraticBezierTo(rect.left, rect.top, rect.left + size.width * 0.12, rect.top)
      ..lineTo(rect.right - size.width * 0.12, rect.top)
      ..quadraticBezierTo(rect.right, rect.top, rect.right, rect.top + size.height * 0.12)
      ..lineTo(rect.right, rect.bottom - size.height * 0.08)
      ..quadraticBezierTo(rect.right, rect.bottom, rect.right - size.width * 0.08, rect.bottom)
      ..lineTo(rect.left + size.width * 0.08, rect.bottom)
      ..quadraticBezierTo(rect.left, rect.bottom, rect.left, rect.bottom - size.height * 0.08)
      ..close();
    canvas.drawPath(path, Paint()..color = const Color(0xCC1E1E22));
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = const Color(0x66FFFFFF),
    );
  }

  @override
  bool shouldRepaint(_UmdShellPainter old) => false;
}

/// The face of a cartridge or card.
///
/// With a `support-2D` scan (a photo of the actual cartridge) the scan is the
/// face. Without it, the console's cartridge shape is drawn with a blank
/// label carrying the known title in plain type.
class GameBoxCartridgeFace extends StatelessWidget {
  const GameBoxCartridgeFace({
    super.key,
    required this.style,
    required this.title,
    this.art,
  });

  final GameBoxCartridgeStyle style;
  final String title;
  final ImageProvider? art;

  @override
  Widget build(BuildContext context) {
    if (art != null) {
      return Image(
        image: art!,
        fit: BoxFit.contain,
        gaplessPlayback: true,
        filterQuality: FilterQuality.medium,
        errorBuilder: (_, _, _) => _blank(),
      );
    }
    return _blank();
  }

  Widget _blank() {
    return CustomPaint(
      painter: _CartridgePainter(style),
      child: LayoutBuilder(builder: (context, c) {
        final (l, t, w, h) = style.labelRect;
        final size = (c.maxWidth * 0.075).clamp(5.0, 16.0);
        return Stack(children: [
          Positioned(
            left: c.maxWidth * l,
            top: c.maxHeight * t,
            width: c.maxWidth * w,
            height: c.maxHeight * h,
            child: Padding(
              padding: EdgeInsets.all(size * 0.6),
              child: Center(
                child: Text(
                  title,
                  textAlign: TextAlign.center,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: size,
                    color: const Color(0xFF3C3C40),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ),
        ]);
      }),
    );
  }
}

class _CartridgePainter extends CustomPainter {
  _CartridgePainter(this.style);
  final GameBoxCartridgeStyle style;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final radius = Radius.circular(size.width * style.cornerRadius / style.width);
    final body = Path();
    if (style.cutCorner) {
      final cut = size.width * 0.12;
      body
        ..moveTo(rect.left + radius.x, rect.top)
        ..lineTo(rect.right - radius.x, rect.top)
        ..quadraticBezierTo(rect.right, rect.top, rect.right, rect.top + radius.y)
        ..lineTo(rect.right, rect.bottom - cut)
        ..quadraticBezierTo(rect.right, rect.bottom, rect.right - cut, rect.bottom)
        ..lineTo(rect.left + radius.x, rect.bottom)
        ..quadraticBezierTo(rect.left, rect.bottom, rect.left, rect.bottom - radius.y)
        ..lineTo(rect.left, rect.top + radius.y)
        ..quadraticBezierTo(rect.left, rect.top, rect.left + radius.x, rect.top)
        ..close();
    } else {
      body.addRRect(RRect.fromRectAndRadius(rect, radius));
    }
    canvas.drawPath(body, Paint()..color = style.bodyColor);
    canvas.drawPath(
      body,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = math.max(0.8, size.width * 0.008)
        ..color = _shade(style.bodyColor, 0.7),
    );
    final (l, t, w, h) = style.labelRect;
    final label = Rect.fromLTWH(
      size.width * l, size.height * t, size.width * w, size.height * h,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(label, Radius.circular(size.width * 0.012)),
      Paint()..color = const Color(0xFFEDEBE6),
    );
    if (style.gripLines > 0) {
      final top = label.bottom + size.height * 0.05;
      final bottom = size.height * 0.95;
      final step = (bottom - top) / (style.gripLines + 1);
      final paint = Paint()
        ..strokeWidth = math.max(0.8, size.height * 0.012)
        ..color = _shade(style.bodyColor, 0.78);
      for (var i = 1; i <= style.gripLines; i++) {
        final y = top + step * i;
        canvas.drawLine(
          Offset(size.width * 0.2, y),
          Offset(size.width * 0.8, y),
          paint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_CartridgePainter old) => old.style != style;
}

/// Floppy disk or cassette, always neutral (no label scan is fetched).
class GameBoxMediaFace extends StatelessWidget {
  const GameBoxMediaFace({super.key, required this.kind, required this.title});

  final GameBoxSupportKind kind;
  final String title;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _MediaPainter(kind),
      child: LayoutBuilder(builder: (context, c) {
        final size = (c.maxWidth * 0.07).clamp(5.0, 14.0);
        final top = kind == GameBoxSupportKind.floppy ? 0.42 : 0.14;
        return Padding(
          padding: EdgeInsets.fromLTRB(
            c.maxWidth * 0.16, c.maxHeight * top, c.maxWidth * 0.16, c.maxHeight * 0.1,
          ),
          child: Align(
            alignment: Alignment.topCenter,
            child: Text(
              title,
              maxLines: 2,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: size, color: const Color(0xFF3C3C40)),
            ),
          ),
        );
      }),
    );
  }
}

class _MediaPainter extends CustomPainter {
  _MediaPainter(this.kind);
  final GameBoxSupportKind kind;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    if (kind == GameBoxSupportKind.floppy) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, Radius.circular(size.width * 0.03)),
        Paint()..color = const Color(0xFF2B2D33),
      );
      canvas.drawRect(
        Rect.fromLTWH(size.width * 0.28, 0, size.width * 0.46, size.height * 0.30),
        Paint()..color = const Color(0xFFA9ADB4),
      );
      canvas.drawRect(
        Rect.fromLTWH(size.width * 0.12, size.height * 0.40, size.width * 0.76, size.height * 0.56),
        Paint()..color = const Color(0xFFEDEBE6),
      );
    } else {
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, Radius.circular(size.width * 0.04)),
        Paint()..color = const Color(0xFF26272B),
      );
      canvas.drawRect(
        Rect.fromLTWH(size.width * 0.1, size.height * 0.1, size.width * 0.8, size.height * 0.5),
        Paint()..color = const Color(0xFFEDEBE6),
      );
      final p = Paint()..color = const Color(0xFF111114);
      canvas.drawCircle(Offset(size.width * 0.33, size.height * 0.42), size.height * 0.08, p);
      canvas.drawCircle(Offset(size.width * 0.67, size.height * 0.42), size.height * 0.08, p);
    }
  }

  @override
  bool shouldRepaint(_MediaPainter old) => old.kind != kind;
}

/// The cover of the game's manual.
///
/// It is the first page of the local PDF, drawn once the box is opened. Until
/// then (or when the page cannot be drawn) the booklet is plain paper with
/// the known title: a stand-in for the real document that exists on the
/// device, never an invented cover.
class GameBoxBookletCover extends StatelessWidget {
  const GameBoxBookletCover({super.key, required this.title, this.page});

  final String title;

  /// First page of the PDF, owned by the caller ([RawImage] keeps a clone).
  final ui.Image? page;

  @override
  Widget build(BuildContext context) {
    final image = page;
    if (image != null) {
      return Stack(fit: StackFit.expand, children: [
        const ColoredBox(color: Color(0xFFF3F0E8)),
        RawImage(image: image, fit: BoxFit.fill, filterQuality: FilterQuality.medium),
        const CustomPaint(painter: _BookletSheenPainter()),
      ]);
    }
    return DecoratedBox(
      decoration: const BoxDecoration(color: Color(0xFFF1EEE6)),
      child: LayoutBuilder(builder: (context, c) {
        final size = (c.maxWidth * 0.085).clamp(5.0, 16.0);
        return Padding(
          padding: EdgeInsets.all(c.maxWidth * 0.1),
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.menu_book_outlined, size: size * 2.4, color: const Color(0x66302C26)),
              SizedBox(height: size * 0.6),
              Text(
                title,
                textAlign: TextAlign.center,
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: size, color: const Color(0xB3302C26), fontWeight: FontWeight.w600),
              ),
            ]),
          ),
        );
      }),
    );
  }
}

/// Faint light across a printed cover, so the paper reads as paper.
class _BookletSheenPainter extends CustomPainter {
  const _BookletSheenPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0x14FFFFFF), Color(0x00FFFFFF), Color(0x0A000000)],
          stops: [0.0, 0.5, 1.0],
        ).createShader(rect),
    );
    // The fold of the stapled spine.
    canvas.drawRect(
      Rect.fromLTWH(0, 0, math.max(1.0, size.width * 0.018), size.height),
      Paint()..color = const Color(0x22000000),
    );
  }

  @override
  bool shouldRepaint(_BookletSheenPainter old) => false;
}

/// Edges and back of the manual: stacked pages, or the stapled spine.
class GameBoxBookletPaperPainter extends CustomPainter {
  const GameBoxBookletPaperPainter({this.spine = false, this.pages = false});

  /// The folded spine with its two staples.
  final bool spine;

  /// The edges of the stacked pages.
  final bool pages;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = spine ? const Color(0xFFE4DFD3) : const Color(0xFFF0ECE3));
    if (pages) {
      final line = Paint()
        ..color = const Color(0x22000000)
        ..strokeWidth = 0.5;
      final horizontal = size.width >= size.height;
      final across = horizontal ? size.height : size.width;
      final n = (across / 1.4).floor().clamp(1, 8);
      for (var i = 1; i < n; i++) {
        final t = across * i / n;
        if (horizontal) {
          canvas.drawLine(Offset(0, t), Offset(size.width, t), line);
        } else {
          canvas.drawLine(Offset(t, 0), Offset(t, size.height), line);
        }
      }
    }
    if (spine && size.height > size.width * 4) {
      final staple = Paint()..color = const Color(0xFF9EA2A8);
      final w = math.max(0.8, size.width * 0.4);
      for (final y in [size.height * 0.24, size.height * 0.76]) {
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset(size.width / 2, y), width: w, height: size.height * 0.08),
            Radius.circular(w / 2),
          ),
          staple,
        );
      }
    }
  }

  @override
  bool shouldRepaint(GameBoxBookletPaperPainter old) => old.spine != spine || old.pages != pages;
}

Color _onColor(Color c) =>
    c.computeLuminance() > 0.45 ? const Color(0xFF1E1E22) : const Color(0xFFF4F4F6);

Color _lift(Color c, double k) => Color.lerp(c, const Color(0xFFFFFFFF), k)!;

Color _shade(Color c, double k) => Color.from(
      alpha: c.a,
      red: (c.r * k).clamp(0.0, 1.0),
      green: (c.g * k).clamp(0.0, 1.0),
      blue: (c.b * k).clamp(0.0, 1.0),
    );
