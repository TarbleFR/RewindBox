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
    this.clear = false,
    this.pxPerMm = 1,
  });

  final Color color;
  final bool ridged;
  final bool seam;
  final bool cardboard;

  /// Clear plastic seen edge-on: lighter along both long borders, where
  /// light runs through the plastic.
  final bool clear;
  final double pxPerMm;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..color = color);
    if (clear) {
      final band = math.max(0.6, math.min(size.width, size.height) * 0.18);
      final horizontal = size.width >= size.height;
      final glow = Paint()..color = _lift(color, 0.35).withValues(alpha: 0.85);
      if (horizontal) {
        canvas.drawRect(Rect.fromLTWH(0, 0, size.width, band), glow);
        canvas.drawRect(Rect.fromLTWH(0, size.height - band, size.width, band), glow);
      } else {
        canvas.drawRect(Rect.fromLTWH(0, 0, band, size.height), glow);
        canvas.drawRect(Rect.fromLTWH(size.width - band, 0, band, size.height), glow);
      }
    }
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
      old.cardboard != cardboard || old.clear != clear || old.pxPerMm != pxPerMm;
}

/// A cover that is not a scan of this case: catalogue art (an XMB or
/// console icon, a logo, a 3D render) shown whole and small on a plain
/// sheet, with the known title in plain type (docs/game-box-3d.md § 13). It
/// keeps the art recognisable in the library without presenting it as the
/// print of the box.
class GameBoxNeutralCover extends StatelessWidget {
  const GameBoxNeutralCover({
    super.key,
    required this.art,
    required this.title,
    required this.color,
    this.artAspect,
    this.compact = false,
  });

  final Widget art;
  final String title;
  final Color color;

  /// Width / height of the art (null: square).
  final double? artAspect;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final onColor = _onColor(color);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: onColor.withValues(alpha: 0.10), width: 1),
      ),
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth, h = c.maxHeight;
        final aspect = (artAspect ?? 1).clamp(0.3, 3.0).toDouble();
        var artW = w * 0.72;
        var artH = artW / aspect;
        if (artH > h * 0.46) {
          artH = h * 0.46;
          artW = artH * aspect;
        }
        final size = (w * 0.075).clamp(6.0, 16.0).toDouble();
        return Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(width: artW, height: artH, child: art),
            if (!compact) ...[
              SizedBox(height: size),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: w * 0.08),
                child: Text(
                  title,
                  maxLines: 3,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: size,
                    color: onColor.withValues(alpha: 0.82),
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ],
        );
      }),
    );
  }
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

/// Light on one face of the box (docs/game-box-3d.md § 20), painted over
/// what the face shows.
///
/// [darken] is the shade of the face's orientation (black). [sheen] is the
/// light a glossy or dark material reflects at grazing angles (white), so a
/// black case keeps its volume against a dark background. [rim] is the light
/// caught by the face's borders: the rounded edges of a plastic case, the
/// folds of a cardboard box. Only the borders named are lit, so the narrow
/// facets of a rounded corner do not show stripes.
class GameBoxFaceLight extends CustomPainter {
  const GameBoxFaceLight({
    this.darken = 0,
    this.sheen = 0,
    this.rim = 0,
    this.rimWidth = 1,
    this.rimVertical = true,
    this.rimHorizontal = true,
    this.radius = 0,
  });

  final double darken;
  final double sheen;
  final double rim;
  final double rimWidth;

  /// Borders at x = 0 and x = width.
  final bool rimVertical;

  /// Borders at y = 0 and y = height.
  final bool rimHorizontal;

  /// Corner radius of the face's outline (logical pixels).
  final double radius;

  bool get isEmpty => darken < 0.004 && sheen < 0.004 && rim < 0.01;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    if (darken >= 0.004) {
      canvas.drawRect(rect, Paint()..color = Color.fromRGBO(0, 0, 0, darken.clamp(0.0, 0.6)));
    }
    if (sheen >= 0.004) {
      // Stronger toward the top left, where the light comes from.
      canvas.drawRect(
        rect,
        Paint()
          ..shader = ui.Gradient.linear(
            rect.topLeft,
            rect.bottomRight,
            [
              Color.fromRGBO(255, 255, 255, (sheen * 1.25).clamp(0.0, 0.5)),
              Color.fromRGBO(255, 255, 255, (sheen * 0.75).clamp(0.0, 0.5)),
            ],
          ),
      );
    }
    if (rim < 0.01 || size.width <= 0 || size.height <= 0) return;
    final w = rimWidth.clamp(0.5, math.max(0.5, math.min(size.width, size.height) * 0.25)).toDouble();
    final soft = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 2.4
      ..color = Color.fromRGBO(255, 255, 255, (rim * 0.3).clamp(0.0, 1.0));
    final sharp = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = w
      ..color = Color.fromRGBO(255, 255, 255, rim.clamp(0.0, 1.0));
    if (rimVertical && rimHorizontal) {
      final r = RRect.fromRectAndRadius(rect.deflate(w / 2), Radius.circular(math.max(0, radius - w / 2)));
      canvas.drawRRect(r, soft);
      canvas.drawRRect(r, sharp);
      return;
    }
    for (final paint in [soft, sharp]) {
      final i = paint.strokeWidth / 2;
      if (rimVertical) {
        canvas.drawLine(Offset(i, 0), Offset(i, size.height), paint);
        canvas.drawLine(Offset(size.width - i, 0), Offset(size.width - i, size.height), paint);
      }
      if (rimHorizontal) {
        canvas.drawLine(Offset(0, i), Offset(size.width, i), paint);
        canvas.drawLine(Offset(0, size.height - i), Offset(size.width, size.height - i), paint);
      }
    }
  }

  @override
  bool shouldRepaint(GameBoxFaceLight old) =>
      old.darken != darken || old.sheen != sheen || old.rim != rim || old.rimWidth != rimWidth ||
      old.rimVertical != rimVertical || old.rimHorizontal != rimHorizontal || old.radius != radius;
}

/// Top, bottom or opening side of a cardboard box (docs/game-box-3d.md
/// § 20). Real boxes print these panels in the colours of the cover, with
/// the title; without a scan of them they take the average colour of the
/// cover's border and the known title in plain type, never stretched pixels
/// of the cover.
class GameBoxCardboardPanel extends StatelessWidget {
  const GameBoxCardboardPanel({
    super.key,
    required this.color,
    required this.title,
    this.standing = false,
  });

  final Color color;
  final String title;

  /// A side panel: the title reads from top to bottom, like the spine.
  final bool standing;

  @override
  Widget build(BuildContext context) {
    final onColor = _onColor(color);
    return ColoredBox(
      color: color,
      child: LayoutBuilder(builder: (context, c) {
        final across = standing ? c.maxWidth : c.maxHeight;
        final along = standing ? c.maxHeight : c.maxWidth;
        if (title.isEmpty || across < 4 || along < 16) return const SizedBox.expand();
        final size = (across * 0.36).clamp(4.0, 15.0).toDouble();
        final text = Padding(
          padding: EdgeInsets.symmetric(horizontal: along * 0.08),
          child: Center(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: size,
                color: onColor.withValues(alpha: 0.82),
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
              ),
            ),
          ),
        );
        return standing ? RotatedBox(quarterTurns: 1, child: text) : text;
      }),
    );
  }
}

/// Verified details of a game that a reconstructed back may show.
@immutable
class GameBoxBackDetails {
  const GameBoxBackDetails({
    required this.title,
    this.platform = '',
    this.year = '',
    this.developer = '',
    this.publisher = '',
    this.genre = '',
    this.players = '',
    this.summary = '',
    this.screenshot,
    this.screenshotAspect,
  });

  final String title;
  final String platform;
  final String year;
  final String developer;
  final String publisher;
  final String genre;
  final String players;
  final String summary;
  final ImageProvider? screenshot;

  /// Width / height of [screenshot], when known.
  final double? screenshotAspect;

  /// Year, studio, publisher and genre, without repeats or empty values.
  String get facts {
    final seen = <String>{};
    final parts = <String>[];
    for (final v in [year, developer, publisher, genre]) {
      final t = v.trim();
      if (t.isEmpty || t == '0' || !seen.add(t.toLowerCase())) continue;
      parts.add(t);
    }
    return parts.join(' · ');
  }

  @override
  bool operator ==(Object other) =>
      other is GameBoxBackDetails &&
      other.title == title &&
      other.platform == platform &&
      other.year == year &&
      other.developer == developer &&
      other.publisher == publisher &&
      other.genre == genre &&
      other.players == players &&
      other.summary == summary &&
      other.screenshot == screenshot &&
      other.screenshotAspect == screenshotAspect;

  @override
  int get hashCode => Object.hash(
      title, platform, year, developer, publisher, genre, players, summary, screenshot, screenshotAspect);
}

/// A back composed from the game's verified details when no authentic back
/// exists (docs/game-box-3d.md § 21): plain colours taken from the cover,
/// the title, a screenshot and the summary when the library has them, the
/// facts of the game, and a label that says it is a reconstruction. It
/// imitates no print and invents nothing.
class GameBoxComposedBack extends StatelessWidget {
  const GameBoxComposedBack({
    super.key,
    required this.color,
    required this.details,
    required this.label,
    this.compact = false,
  });

  /// Average colour of the cover's border (or the case's print colour).
  final Color color;
  final GameBoxBackDetails details;

  /// « Verso reconstitué » in the player's language.
  final String label;
  final bool compact;

  /// The sheet's colour: the cover's own tone, quietened for reading.
  static Color sheetOf(Color cover) => cover.computeLuminance() > 0.42
      ? Color.lerp(cover, const Color(0xFFF2F1EE), 0.62)!
      : Color.lerp(cover, const Color(0xFF101114), 0.5)!;

  @override
  Widget build(BuildContext context) {
    final sheet = sheetOf(color);
    final ink = _onColor(sheet);
    return ColoredBox(
      color: sheet,
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth, h = c.maxHeight;
        if (!w.isFinite || !h.isFinite || w < 24 || h < 24) return const SizedBox.expand();
        final unit = math.min(w, h);
        final pad = unit * 0.07;
        final titleSize = (unit * 0.075).clamp(6.0, 22.0).toDouble();
        final bodySize = (unit * 0.04).clamp(4.5, 13.0).toDouble();
        final labelSize = (unit * 0.034).clamp(4.0, 11.0).toDouble();
        final wide = w > h * 1.15;
        final shot = details.screenshot;
        final aspect = (details.screenshotAspect ?? 4 / 3).clamp(0.5, 2.4).toDouble();
        Widget? picture;
        if (shot != null && !compact) {
          picture = AspectRatio(
            aspectRatio: aspect,
            child: DecoratedBox(
              position: DecorationPosition.foreground,
              decoration: BoxDecoration(border: Border.all(color: ink.withValues(alpha: 0.25), width: 1)),
              child: Image(
                image: shot,
                fit: BoxFit.contain,
                filterQuality: FilterQuality.medium,
                excludeFromSemantics: true,
                gaplessPlayback: true,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
          );
        }
        final title = Text(
          details.title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontSize: titleSize, fontWeight: FontWeight.w800, color: ink, height: 1.1),
        );
        final facts = details.facts;
        final summary = details.summary.trim();
        final text = <Widget>[
          if (summary.isNotEmpty && !compact)
            Expanded(
              child: Text(
                summary,
                overflow: TextOverflow.fade,
                style: TextStyle(fontSize: bodySize, color: ink.withValues(alpha: 0.86), height: 1.3),
              ),
            )
          else
            const Spacer(),
          if (facts.isNotEmpty) ...[
            SizedBox(height: pad * 0.4),
            Text(
              facts,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: bodySize * 0.92, color: ink.withValues(alpha: 0.72)),
            ),
          ],
          if (details.players.trim().isNotEmpty && details.players.trim() != '0') ...[
            SizedBox(height: pad * 0.25),
            Row(children: [
              Icon(Icons.person_outline, size: bodySize * 1.2, color: ink.withValues(alpha: 0.72)),
              SizedBox(width: bodySize * 0.3),
              Text(details.players.trim(),
                  style: TextStyle(fontSize: bodySize * 0.92, color: ink.withValues(alpha: 0.72))),
            ]),
          ],
        ];
        final footer = Row(children: [
          if (details.platform.isNotEmpty)
            Expanded(
              child: Text(
                details.platform,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: labelSize, color: ink.withValues(alpha: 0.6), fontWeight: FontWeight.w600),
              ),
            )
          else
            const Spacer(),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: ink.withValues(alpha: 0.45), width: 1),
              borderRadius: BorderRadius.circular(labelSize),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: labelSize * 0.7, vertical: labelSize * 0.25),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.info_outline, size: labelSize * 1.15, color: ink.withValues(alpha: 0.75)),
                SizedBox(width: labelSize * 0.35),
                Text(label, style: TextStyle(fontSize: labelSize, color: ink.withValues(alpha: 0.85))),
              ]),
            ),
          ),
        ]);
        final Widget body;
        if (wide && picture != null) {
          body = Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: (w - 2 * pad) * 0.42, child: picture),
            SizedBox(width: pad),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                title,
                SizedBox(height: pad * 0.5),
                ...text,
              ]),
            ),
          ]);
        } else {
          body = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            title,
            if (picture != null) ...[
              SizedBox(height: pad * 0.6),
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: h * 0.34),
                child: Center(child: picture),
              ),
            ],
            SizedBox(height: pad * 0.6),
            ...text,
          ]);
        }
        return Padding(
          padding: EdgeInsets.all(pad),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(child: body),
            SizedBox(height: pad * 0.5),
            footer,
          ]),
        );
      }),
    );
  }
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
