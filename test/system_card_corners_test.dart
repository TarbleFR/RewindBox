// A grid system card rounds the four corners of its art alike. Reported on the main menu: with an art pack whose
// tiles fill the card (Wii, PlayStation 2…), the top corners read as straight bevels while the bottom ones were round.
// The card's clip (27.r) and its system bubble (30.r) were far rounder than the art (the Corners setting, 10.r in M)
// plus its 4.r inset, and cut across the art's top corners with a wide, nearly straight arc; the bottom corners sit
// above the logo, out of their reach. The clip and the bubble now follow the art's radius plus its inset.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/system_card.dart';
import 'package:neostation/themes/corner_radii.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';

const _art = Color(0xFF00FF00);
const _background = Color(0xFF14121C);

void main() {
  late Directory dir;
  late String artPath;

  setUpAll(() async {
    dir = Directory.systemTemp.createTempSync('system_card_corners');
    // A synthetic opaque tile, square like an art pack's.
    final recorder = ui.PictureRecorder();
    Canvas(recorder).drawRect(const Rect.fromLTWH(0, 0, 256, 256), Paint()..color = _art);
    final image = await recorder.endRecording().toImage(256, 256);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    artPath = '${dir.path}/wii.png';
    File(artPath).writeAsBytesSync(bytes!.buffer.asUint8List());
  });
  tearDownAll(() => dir.deleteSync(recursive: true));

  for (final bubbles in [false, true]) {
    testWidgets('the art keeps four alike corners in a small grid card (bubbles: $bubbles)', (tester) async {
      // An iPhone in landscape and a card of a dense grid, as reported.
      const screen = Size(932, 430);
      await tester.binding.setSurfaceSize(screen);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final assets = NeoAssetsProvider();
      addTearDown(assets.dispose);
      final capture = GlobalKey();
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      final imageContext = tester.element(find.byType(SizedBox).last);
      await tester.runAsync(() => precacheImage(ResizeImage(FileImage(File(artPath)), width: 512), imageContext));
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, child) => ChangeNotifierProvider.value(
            value: assets,
            child: MaterialApp(
              theme: ThemeData.dark().copyWith(
                extensions: [
                  CornerRadii.m(),
                  LiquidGlassTheme(settings: InterfaceStyleSettings(showSystemBubbles: bubbles)),
                ],
              ),
              home: MediaQuery(
                data: const MediaQueryData(size: screen, disableAnimations: true),
                child: Scaffold(
                  backgroundColor: _background,
                  body: Center(
                    child: RepaintBoundary(
                      key: capture,
                      child: ColoredBox(
                        color: _background,
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: SizedBox(
                            width: 75,
                            height: 75 / 0.8,
                            child: SystemCard(
                              info: SystemInfo(folderName: 'wii', title: 'Wii', customBackgroundPath: artPath),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      // Every clip around the art is at most as round as the art plus the space between them, so none of them cuts
      // into it. The art's own clip is the nearest one.
      final artImage = find.byKey(ValueKey('${artPath}_0'));
      expect(artImage, findsOneWidget);
      final clips = find.ancestor(of: artImage, matching: find.byType(ClipRRect));
      final artClip = clips.first;
      final artRect = tester.getRect(artClip);
      final artRadius = tester.widget<ClipRRect>(artClip).borderRadius.resolve(TextDirection.ltr).topLeft.x;
      expect(artRadius, greaterThan(0));
      var outerClips = 0;
      for (final element in clips.evaluate().skip(1)) {
        final clip = element.widget as ClipRRect;
        final rect = tester.getRect(find.byElementPredicate((e) => identical(e, element)));
        final radius = clip.borderRadius.resolve(TextDirection.ltr).topLeft.x;
        final inset = (artRect.left - rect.left).clamp(0.0, artRect.top - rect.top);
        expect(radius, lessThanOrEqualTo(artRadius + inset + 0.01), reason: 'clip $rect around the art $artRect');
        outerClips++;
      }
      expect(outerClips, bubbles ? 2 : 1, reason: 'the card clip, and the bubble when it is shown');

      // Drawn: the corners at the top of the art are as round as those at the bottom.
      final pixels = await tester.runAsync(() async {
        final boundary = capture.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await boundary.toImage(pixelRatio: 4);
        final data = await image.toByteData();
        final size = Size(image.width.toDouble(), image.height.toDouble());
        image.dispose();
        return (data!, size);
      });
      final (data, size) = pixels!;
      final width = size.width.toInt(), height = size.height.toInt();
      bool isArt(int x, int y) {
        final i = (y * width + x) * 4;
        return data.getUint8(i + 1) > 200 && data.getUint8(i) < 120 && data.getUint8(i + 2) < 120;
      }

      var top = height, bottom = -1, left = width, right = -1;
      for (var y = 0; y < height; y++) {
        for (var x = 0; x < width; x++) {
          if (!isArt(x, y)) continue;
          if (y < top) top = y;
          if (y > bottom) bottom = y;
          if (x < left) left = x;
          if (x > right) right = x;
        }
      }
      final side = right - left;
      expect(side, greaterThan(150));
      // How far the corner's round reaches into a column near the left and right edges, from the top and the bottom.
      for (final fraction in [0.02, 0.04, 0.06, 0.08]) {
        for (final x in [left + (side * fraction).round(), right - (side * fraction).round()]) {
          var fromTop = 0, fromBottom = 0;
          while (fromTop < side ~/ 2 && !isArt(x, top + fromTop)) {
            fromTop++;
          }
          while (fromBottom < side ~/ 2 && !isArt(x, bottom - fromBottom)) {
            fromBottom++;
          }
          expect(
            (fromTop - fromBottom).abs(),
            lessThanOrEqualTo(2),
            reason: 'column $x: $fromTop px rounded at the top, $fromBottom px at the bottom',
          );
        }
      }
      await tester.pumpWidget(const SizedBox());
    });
  }
}
