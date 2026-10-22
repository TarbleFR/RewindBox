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
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';

void main() {
  for (final size in [const Size(844, 390), const Size(390, 844)]) {
    testWidgets(
      'production console bubbles retain artwork and readable names: $size',
      (tester) async {
        await tester.binding.setSurfaceSize(size);
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final assets = NeoAssetsProvider();
        addTearDown(assets.dispose);
        final capture = GlobalKey();
        final art = File('assets/images/logos/32x.webp').absolute.path;
        await tester.pumpWidget(const MaterialApp(home: SizedBox()));
        final imageContext = tester.element(find.byType(SizedBox).last);
        // Finish real I/O before the production widgets subscribe from the
        // test's fake clock. Their existing cache keys are then reused.
        await tester.runAsync(() async {
          await precacheImage(ResizeImage(FileImage(File(art)), width: 512), imageContext);
          await precacheImage(const ResizeImage(AssetImage('assets/images/logos/32x.webp'), width: 256), imageContext);
        });
        await tester.pumpWidget(
          ScreenUtilInit(
            designSize: const Size(640, 480),
            builder: (_, child) => ChangeNotifierProvider.value(
              value: assets,
              child: MaterialApp(
                theme: ThemeData.dark(),
                home: MediaQuery(
                  data: MediaQueryData(size: size, disableAnimations: true),
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
                        child: Column(
                          children: [
                            Expanded(
                              child: Center(
                                child: SizedBox(
                                  width: size.width < 500 ? 200 : 230,
                                  height: size.width < 500 ? 260 : 290,
                                  child: SystemCard(
                                    info: SystemInfo(
                                      folderName: '32x',
                                      title: 'Sega 32X',
                                      customBackgroundPath: art,
                                    ),
                                    isSelected: true,
                                  ),
                                ),
                              ),
                            ),
                            Padding(
                              padding: const EdgeInsets.all(12),
                              child: MainMenuTabStrip(
                                tabs: NavTab.values,
                                selected: NavTab.systems,
                                showAirPlay: false,
                                tabBuilder: (tab) => Padding(
                                  padding: EdgeInsets.all(8.r),
                                  child: NavTabIcon(
                                    spec: navTabSpec(tab),
                                    tint: Colors.white,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
        // Decode the existing cached-image provider, not a replacement artwork.
        final image = tester.widget<Image>(find.byKey(ValueKey('${art}_0')));
        expect(image.fit, BoxFit.cover);
        await tester.pumpAndSettle();
        expect(find.text('Sega 32X'), findsOneWidget);
        expect(tester.getRect(find.text('Sega 32X')).height, greaterThan(0));
        expect(tester.takeException(), isNull);
        if (size.width > size.height) {
          await tester.runAsync(() async {
            final boundary =
                capture.currentContext!.findRenderObject()!
                    as RenderRepaintBoundary;
            final bitmap = await boundary.toImage(pixelRatio: 1.5);
            try {
              final data = await bitmap.toByteData(
                format: ui.ImageByteFormat.png,
              );
              final target = File(
                'build/bubble-review/console-and-navigation.png',
              );
              await target.parent.create(recursive: true);
              await target.writeAsBytes(data!.buffer.asUint8List());
            } finally {
              bitmap.dispose();
            }
          });
        }
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
}
