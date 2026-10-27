// Settings › Themes › User interface › "Show system bubbles": the main menu's
// System Art Packs with and without their Liquid Glass bubble. The production
// SystemCard is rendered with the real artwork; only the setting changes.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/my_systems_grid.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/system_card.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:neostation/widgets/neo_glass_bubble.dart';

void main() {
  for (final bubbles in [true, false]) {
    testWidgets('system art packs with bubbles=$bubbles', (tester) async {
      const size = Size(844, 390);
      // A tap plays a sound through a native library the test host lacks.
      SfxService().setEnabled(false);
      addTearDown(() => SfxService().setEnabled(true));
      await tester.binding.setSurfaceSize(size);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final assets = NeoAssetsProvider();
      addTearDown(assets.dispose);
      final capture = GlobalKey();
      final art = File('assets/images/logos/32x.webp').absolute.path;
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      final imageContext = tester.element(find.byType(SizedBox).last);
      await tester.runAsync(() async {
        await precacheImage(
          ResizeImage(FileImage(File(art)), width: 512),
          imageContext,
        );
        await precacheImage(
          const ResizeImage(
            AssetImage('assets/images/logos/32x.webp'),
            width: 256,
          ),
          imageContext,
        );
      });
      final taps = <String>[];
      Widget card(String title, {required bool selected}) => SizedBox(
        width: 150,
        height: 190,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned.fill(
              child: SystemCard(
                info: SystemInfo(
                  folderName: '32x',
                  title: title,
                  customBackgroundPath: art,
                ),
                isSelected: selected,
                onTap: () => taps.add(title),
              ),
            ),
            // The grid's sliding focus indicator, as it chooses it.
            if (selected)
              Positioned.fill(
                child: IgnorePointer(
                  child: bubbles
                      ? const NeoGlassBubble(child: SizedBox.expand())
                      : const SystemSelectionMarker(),
                ),
              ),
          ],
        ),
      );
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, child) => ChangeNotifierProvider.value(
            value: assets,
            child: MaterialApp(
              theme: ThemeData.dark().copyWith(
                extensions: [
                  LiquidGlassTheme(
                    settings: InterfaceStyleSettings(
                      showSystemBubbles: bubbles,
                    ),
                  ),
                ],
              ),
              home: MediaQuery(
                data: const MediaQueryData(size: size, disableAnimations: true),
                child: RepaintBoundary(
                  key: capture,
                  child: Scaffold(
                    body: DecoratedBox(
                      decoration: const BoxDecoration(
                        gradient: LinearGradient(
                          colors: [Color(0xFF283B46), Color(0xFF0F161F)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                      ),
                      child: Center(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            card('Sega 32X', selected: false),
                            const SizedBox(width: 24),
                            card('Sega 32X CD', selected: true),
                          ],
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

      // The original artwork, unchanged, and the console names stay.
      final image = tester.widget<Image>(
        find.byKey(ValueKey('${art}_0')).first,
      );
      expect(image.fit, BoxFit.cover);
      expect(find.text('Sega 32X'), findsOneWidget);
      expect(find.text('Sega 32X CD'), findsOneWidget);

      final cardBubbles = find.descendant(
        of: find.byType(SystemCard),
        matching: find.byType(NeoGlassBubble),
      );
      if (bubbles) {
        expect(cardBubbles, findsNWidgets(2));
        expect(find.byType(SystemSelectionMarker), findsNothing);
      } else {
        expect(cardBubbles, findsNothing);
        expect(find.byType(NeoGlassBubble), findsNothing);
        // The discreet marker sits under the focused card, off the artwork
        // and off the console name.
        final marker = tester.getRect(
          find.byKey(const ValueKey('system-selection-marker')),
        );
        final focused = tester.getRect(find.byType(SystemCard).last);
        expect(marker.top, greaterThanOrEqualTo(focused.bottom));
        expect(marker.center.dx, closeTo(focused.center.dx, 0.5));
        expect(
          marker.overlaps(tester.getRect(find.text('Sega 32X CD'))),
          isFalse,
        );
      }

      // Touch selection works the same in both modes.
      await tester.tap(find.text('Sega 32X'));
      await tester.tap(find.text('Sega 32X CD'));
      expect(taps, ['Sega 32X', 'Sega 32X CD']);
      expect(tester.takeException(), isNull);
      await tester.pumpAndSettle();

      await tester.runAsync(() async {
        final boundary =
            capture.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        final bitmap = await boundary.toImage(pixelRatio: 1.5);
        try {
          final data = await bitmap.toByteData(format: ui.ImageByteFormat.png);
          final target = File(
            'build/bubble-review/system-bubbles-${bubbles ? 'on' : 'off'}.png',
          );
          await target.parent.create(recursive: true);
          await target.writeAsBytes(data!.buffer.asUint8List());
        } finally {
          bitmap.dispose();
        }
      });
      await tester.pumpWidget(const SizedBox());
    });
  }
}
