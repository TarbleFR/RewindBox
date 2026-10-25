import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/liquid_motion_locale.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/widgets/liquid_battery.dart';
import 'package:neostation/widgets/liquid_motion_clock.dart';
import 'package:neostation/widgets/liquid_progress.dart';
import 'package:neostation/widgets/mau_ali_tab_motion.dart';
import 'package:neostation/widgets/native_carousel.dart';

void main() {
  Widget frame(Widget child, {bool reduced = false, bool visible = true}) =>
      MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: reduced),
          child: TickerMode(
            enabled: visible,
            child: Scaffold(
              body: Center(
                child: SizedBox(width: 400, height: 200, child: child),
              ),
            ),
          ),
        ),
      );
  LiquidProgressPainter progress(WidgetTester tester) => tester
      .widgetList<CustomPaint>(find.byType(CustomPaint))
      .map((e) => e.painter)
      .whereType<LiquidProgressPainter>()
      .single;
  LiquidBatteryPainter battery(WidgetTester tester) => tester
      .widgetList<CustomPaint>(find.byType(CustomPaint))
      .map((e) => e.painter)
      .whereType<LiquidBatteryPainter>()
      .single;

  tearDown(() {
    LiquidMotionClock.instance.lowPower = false;
  });

  test('author motion matches the inspected PnW profile and stays bounded', () {
    final profile = jsonDecode(
      File('assets/data/mau-ali-tab-motion.json').readAsStringSync(),
    );
    expect(profile['creator'], 'Mau Ali');
    expect(profile['segments'], hasLength(21));
    expect(
      MauAliTabMotion.position.transform(.5),
      closeTo(const Cubic(.358, .965, .56, 1).transform(.5), .00001),
    );
    expect(MauAliTabMotion.scale(0), (1, 1));
    expect(MauAliTabMotion.scale(1), (1, 1));
    for (var i = 0; i <= 100; i++) {
      final scale = MauAliTabMotion.scale(i / 100);
      expect(scale.$1, inInclusiveRange(.90, 1.30));
      expect(scale.$2, inInclusiveRange(.90, 1.30));
    }
    expect(LiquidMotionLocale.battery.keys.toSet(), {
      'en',
      'fr',
      'es',
      'pt',
      'ru',
      'zh',
      'zh_Hant',
      'de',
      'it',
      'id',
      'ja',
      'ko',
    });
  });

  testWidgets(
    'measured amount never advances on animation frames, pause or error',
    (tester) async {
      for (final state in LiquidProgressState.values) {
        await tester.pumpWidget(
          frame(LiquidProgressIndicator(value: .37, state: state)),
        );
        await tester.pump(const Duration(milliseconds: 800));
        expect(progress(tester).value, .37);
        expect(progress(tester).status, state);
        expect(
          LiquidMotionClock.instance.running,
          state == LiquidProgressState.running,
        );
      }
      await tester.pumpWidget(frame(const LiquidProgressIndicator(value: .12)));
      expect(
        progress(tester).value,
        .12,
        reason: 'A restarted phase must not retain a previous amount.',
      );
      await tester.pumpWidget(const SizedBox());
      expect(LiquidMotionClock.instance.running, isFalse);
    },
  );

  testWidgets('unknown duration has no invented accessibility percentage', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    for (final value in [null, double.nan, double.infinity]) {
      await tester.pumpWidget(frame(LiquidProgressIndicator(value: value)));
      expect(progress(tester).value, isNull);
      expect(find.bySemanticsLabel(RegExp(r'\d+%')), findsNothing);
    }
    await tester.pumpWidget(frame(const LiquidProgressIndicator(value: .63)));
    expect(progress(tester).value, .63);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'one clock serves multiple views and suspends on all frontend barriers',
    (tester) async {
      final owner = Object();
      final surfaces = Column(
        children: const [
          LiquidProgressIndicator(value: .2),
          LiquidProgressIndicator(value: .7),
          LiquidBattery(percent: 41, charging: true),
        ],
      );
      await tester.pumpWidget(frame(surfaces));
      final painters = tester
          .widgetList<CustomPaint>(find.byType(CustomPaint))
          .map((e) => e.painter)
          .whereType<LiquidProgressPainter>()
          .toList();
      expect(identical(painters[0].clock, painters[1].clock), isTrue);
      expect(identical(painters[0].clock, battery(tester).clock), isTrue);
      expect(LiquidMotionClock.instance.running, isTrue);
      LiquidMotionClock.instance.lowPower = true;
      expect(LiquidMotionClock.instance.running, isFalse);
      LiquidMotionClock.instance.lowPower = false;
      expect(LiquidMotionClock.instance.running, isTrue);
      FrontendMediaGate.instance.hold(owner);
      await tester.pump();
      expect(LiquidMotionClock.instance.running, isFalse);
      FrontendMediaGate.instance.release(owner);
      expect(LiquidMotionClock.instance.running, isTrue);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      expect(LiquidMotionClock.instance.running, isFalse);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      expect(LiquidMotionClock.instance.running, isTrue);
      await tester.pumpWidget(frame(surfaces, visible: false));
      expect(LiquidMotionClock.instance.running, isFalse);
      await tester.pumpWidget(frame(surfaces, reduced: true));
      expect(LiquidMotionClock.instance.running, isFalse);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('battery keeps real percentages, charging and critical palette', (
    tester,
  ) async {
    for (final level in [0, 5, 20, 64, 100]) {
      await tester.pumpWidget(
        frame(LiquidBattery(percent: level, charging: false)),
      );
      expect(battery(tester).percent, level);
      expect(battery(tester).charging, isFalse);
      expect(LiquidMotionClock.instance.running, isFalse);
    }
    expect(LiquidBattery.tint(5), isNot(LiquidBattery.tint(64)));
    await tester.pumpWidget(
      frame(const LiquidBattery(percent: 28, charging: true)),
    );
    await tester.pump(const Duration(seconds: 2));
    expect(battery(tester).percent, 28);
    expect(LiquidMotionClock.instance.running, isTrue);
    await tester.pumpWidget(
      frame(const LiquidBattery(percent: 28, charging: true), reduced: true),
    );
    expect(LiquidMotionClock.instance.running, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  for (final size in [const Size(844, 390), const Size(390, 844)]) {
    testWidgets(
      'console perspective retains selection through rapid input, touch, rotation and playlist return: $size',
      (tester) async {
        await tester.binding.setSurfaceSize(size);
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final key = GlobalKey<NativeCarouselState>();
        final navigator = GlobalKey<NavigatorState>();
        var builds = 0;
        await tester.pumpWidget(
          MaterialApp(
            navigatorKey: navigator,
            home: Scaffold(
              body: Center(
                child: SizedBox(
                  height: 230,
                  child: NativeCarousel(
                    key: key,
                    itemCount: 8,
                    perspective: true,
                    itemBuilder: (_, i) {
                      builds++;
                      return ColoredBox(
                        color: Colors.blueGrey,
                        child: Text('Console $i'),
                      );
                    },
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final before = builds;
        key.currentState!.nextPage();
        key.currentState!.nextPage();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 90));
        expect(
          builds,
          lessThanOrEqualTo(before + 3),
          reason: 'Artwork must not rebuild every animation frame.',
        );
        await tester.pumpAndSettle();
        expect(key.currentState!.currentIndex, 2);
        final flow = tester.widget<Flow>(find.byType(Flow));
        final matrix = (flow.delegate as ConsoleCoverFlowDelegate).transformFor(
          1,
          tester.getSize(find.byType(Flow)),
        );
        expect(matrix.entry(3, 2), isNot(0));
        await tester.fling(
          find.byType(Scrollable).first,
          const Offset(-100, 0),
          800,
        );
        await tester.pumpAndSettle();
        final selected = key.currentState!.currentIndex;
        expect(selected, greaterThanOrEqualTo(2));
        if (selected < 7) {
          key.currentState!.nextPage();
          await tester.pumpAndSettle();
          expect(
            key.currentState!.currentIndex,
            selected + 1,
            reason:
                'A controller move after a touch fling starts from the actual centred console.',
          );
          key.currentState!.previousPage();
          await tester.pumpAndSettle();
          expect(key.currentState!.currentIndex, selected);
        }
        navigator.currentState!.push(
          MaterialPageRoute<void>(
            builder: (_) => const Scaffold(body: Text('Playlist')),
          ),
        );
        await tester.pumpAndSettle();
        navigator.currentState!.pop();
        await tester.pumpAndSettle();
        expect(key.currentState!.currentIndex, selected);
        await tester.binding.setSurfaceSize(Size(size.height, size.width));
        await tester.pumpAndSettle();
        expect(key.currentState!.currentIndex, selected);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  testWidgets(
    'console perspective interruption preserves the app focus during rotation',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(844, 390));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final key = GlobalKey<NativeCarouselState>();
      final focus = ValueNotifier<int>(0);
      addTearDown(focus.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                height: 230,
                child: ValueListenableBuilder<int>(
                  valueListenable: focus,
                  builder: (_, selected, _) => NativeCarousel(
                    key: key,
                    itemCount: 8,
                    initialIndex: selected,
                    footerHeight: 60,
                    perspective: true,
                    onPageChanged: (index, _) => focus.value = index,
                    itemBuilder: (_, index) => Text('Console $index'),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      key.currentState!.animateToPage(4);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 90));
      final retained = focus.value;
      await tester.binding.setSurfaceSize(const Size(390, 844));
      await tester.pumpAndSettle();
      expect(
        focus.value,
        key.currentState!.currentIndex,
        reason:
            'The controller must open the visually centred console after interruption.',
      );
      expect(focus.value, retained);
      key.currentState!.nextPage();
      await tester.pumpAndSettle();
      expect(focus.value, retained + 1);
      expect(focus.value, key.currentState!.currentIndex);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'reduced motion uses a static carousel and immediate controller selection',
    (tester) async {
      final key = GlobalKey<NativeCarouselState>();
      await tester.pumpWidget(
        frame(
          NativeCarousel(
            key: key,
            perspective: true,
            itemCount: 4,
            itemBuilder: (_, i) => Text('$i'),
          ),
          reduced: true,
        ),
      );
      key.currentState!.nextPage();
      await tester.pumpAndSettle();
      expect(key.currentState!.currentIndex, 1);
      expect(
        (tester.widget<Flow>(find.byType(Flow)).delegate
                as ConsoleCoverFlowDelegate)
            .reduced,
        isTrue,
      );
      expect(tester.hasRunningAnimations, isFalse);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
