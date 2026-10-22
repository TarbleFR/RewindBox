import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';
import 'package:neostation/widgets/neo_glass_bubble.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final gate = FrontendMediaGate.instance;
  Widget scene({
    bool selected = true,
    bool enabled = true,
    bool reduced = false,
  }) => MaterialApp(
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.purple,
        brightness: Brightness.dark,
      ),
    ),
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: reduced),
      child: TickerMode(
        enabled: enabled,
        child: Center(
          child: SizedBox(
            width: 180,
            height: 230,
            child: NeoBubbleMotion(
              selected: selected,
              float: true,
              child: const NeoGlassBubble(
                radius: 30,
                child: Center(child: Text('Sega 32X')),
              ),
            ),
          ),
        ),
      ),
    ),
  );

  testWidgets(
    'dense console glass has neutral reflections and no per-card blur',
    (tester) async {
      await tester.pumpWidget(scene(selected: false));
      expect(find.byType(BackdropFilter), findsNothing);
      final bubbles = find.descendant(
        of: find.byType(NeoGlassBubble),
        matching: find.byType(DecoratedBox),
      );
      for (final decorated in tester.widgetList<DecoratedBox>(bubbles)) {
        final d = decorated.decoration as BoxDecoration;
        final colors = [
          if (d.color != null) d.color!,
          ...?d.gradient?.colors,
          if (d.border is Border) (d.border! as Border).top.color,
          for (final shadow in d.boxShadow ?? <BoxShadow>[]) shadow.color,
        ];
        for (final color in colors) {
          expect(color.r, color.g);
          expect(color.g, color.b);
        }
      }
    },
  );

  testWidgets('press compresses and cancel restores the selected bubble', (
    tester,
  ) async {
    await tester.pumpWidget(scene());
    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(NeoGlassBubble)),
    );
    await tester.pump();
    expect(
      tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale,
      lessThan(1),
    );
    await tester.pump(const Duration(milliseconds: 180));
    final pressure = tester
        .widget<Transform>(find.byKey(const ValueKey('neo-bubble-pressure')))
        .transform;
    expect(pressure.storage[0], greaterThan(1));
    expect(pressure.storage[5], lessThan(1));
    await gesture.cancel();
    await tester.pump();
    expect(
      tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale,
      greaterThan(1),
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'idle motion stops for hidden tabs, reduced motion and emulation',
    (tester) async {
      await tester.pumpWidget(scene());
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.binding.transientCallbackCount, greaterThan(0));
      final owner = Object();
      addTearDown(() => FrontendMediaGate.instance.release(owner));
      final producer = Object();
      final cleanup = Completer<void>();
      gate.register(producer, () => cleanup.future);
      addTearDown(() => gate.unregister(producer));
      // UI motion must stop synchronously, before an unrelated AVFoundation
      // producer finishes its asynchronous shutdown. Its barrier is tested
      // independently by frontend_media_gate_test.dart.
      unawaited(gate.hold(owner));
      await tester.pump();
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale, 1);
      cleanup.complete();
      gate.unregister(producer);
      FrontendMediaGate.instance.release(owner);
      await tester.pump();
      expect(tester.binding.transientCallbackCount, greaterThan(0));
      await tester.pumpWidget(scene(enabled: false));
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.binding.transientCallbackCount, 0);
      await tester.pumpWidget(scene(reduced: true));
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale, 1);
      await tester.pumpWidget(scene(selected: false));
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'iOS Reduce Motion is respected even without MediaQuery.disableAnimations',
    (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(reduceMotion: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await tester.pumpWidget(scene());
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.binding.transientCallbackCount, 0);
      expect(tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale, 1);
    },
  );

  testWidgets(
    'rapid focus changes retarget the moving lens without a position jump',
    (tester) async {
      final selection = ValueNotifier(NavTab.systems);
      addTearDown(selection.dispose);
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, child) => MaterialApp(
            home: Scaffold(
              body: Center(
                child: ValueListenableBuilder<NavTab>(
                  valueListenable: selection,
                  builder: (_, selected, child) => MainMenuTabStrip(
                    tabs: NavTab.values,
                    selected: selected,

                    tabBuilder: (tab) => TextButton(
                      onPressed: () => selection.value = tab,
                      child: Text(tab.name),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      final lens = find.byKey(const ValueKey('main-menu-tab-indicator'));
      final initial = tester.getRect(lens).left;
      selection.value = NavTab.settings;
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      final moving = tester.getRect(lens).left;
      expect(moving, greaterThan(initial));
      final stretch = tester
          .widget<Transform>(
            find.byKey(const ValueKey('main-menu-liquid-stretch')),
          )
          .transform;
      expect(stretch.storage[0], greaterThan(1));
      expect(stretch.storage[5], lessThan(1));
      selection.value = NavTab.consoles;
      await tester.pump();
      expect(tester.getRect(lens).left, closeTo(moving, 0.01));
      await tester.pumpAndSettle();
      expect(
        tester.getRect(lens).left,
        tester
            .getRect(find.byKey(const ValueKey('main-menu-cell-consoles')))
            .left,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('lens depth stays on the edge and keeps the image center clear', (
    tester,
  ) async {
    await tester.runAsync(() async {
      final recorder = ui.PictureRecorder();
      NeoGlassLensPainter(
        selected: true,
        radius: 30,
      ).paint(Canvas(recorder), const Size(180, 230));
      final picture = recorder.endRecording();
      final bitmap = await picture.toImage(180, 230);
      try {
        final pixels = await bitmap.toByteData(
          format: ui.ImageByteFormat.rawRgba,
        );
        int alpha(int x, int y) => pixels!.getUint8((y * 180 + x) * 4 + 3);
        expect(
          alpha(90, 150),
          0,
          reason: 'the clear center cannot haze labels or art',
        );
        expect(
          alpha(90, 1),
          greaterThan(0),
          reason: 'the thick polished rim is visible',
        );
        expect(
          alpha(90, 228),
          greaterThan(0),
          reason: 'the lower meniscus closes the lens',
        );
      } finally {
        bitmap.dispose();
        picture.dispose();
      }
    });
  });
}
