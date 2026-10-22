import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/widgets/rewind_startup.dart';

void main() {
  Future<RewindStartupController> start(WidgetTester tester) async {
    final controller = RewindStartupController();
    await tester.pumpWidget(RewindStartupRoot(controller: controller));
    return controller;
  }

  final intro = find.byKey(const ValueKey('rewind-motion-intro'));
  Widget destination({bool ready = true}) {
    const page = MaterialApp(home: Scaffold(body: Text('Library ready')));
    return ready ? const RewindStartupReady(child: page) : page;
  }

  testWidgets(
    'cold start mounts real app before revealing and has no repeated name',
    (tester) async {
      final controller = await start(tester);
      controller.attach(destination(ready: false));
      await tester.pump();
      expect(find.text('Library ready'), findsOneWidget);
      expect(intro, findsOneWidget);
      expect(find.text('RewindBox'), findsNothing);
      await tester.pump(const Duration(seconds: 4));
      expect(intro, findsOneWidget);
      controller.contentReady();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 241));
      expect(intro, findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    },
  );

  testWidgets(
    'fast ready skips remaining intro rather than adding a minimum wait',
    (tester) async {
      final controller = await start(tester);
      controller.attach(destination());
      await tester.pump(); // actual content's first painted frame
      await tester.pump(); // schedule opening
      await tester.pump(const Duration(milliseconds: 241));
      expect(intro, findsNothing);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    },
  );

  testWidgets('setup first frame can finish intro without a library scan', (
    tester,
  ) async {
    final controller = await start(tester);
    controller.attach(
      const RewindStartupReady(child: MaterialApp(home: Text('Setup'))),
    );
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 241));
    expect(intro, findsNothing);
    expect(find.text('Setup'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets(
    'storage issue stays interactive, retry keeps one root, warm resume never replays',
    (tester) async {
      final controller = await start(tester);
      var retries = 0;
      controller.showIssue(
        MaterialApp(
          home: TextButton(
            onPressed: () {
              retries++;
              controller.showIssue(null);
            },
            child: const Text('Retry'),
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Retry'));
      await tester.pump();
      expect(retries, 1);
      controller.attach(destination());
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 241));
      expect(intro, findsNothing);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(const Duration(seconds: 2));
      expect(intro, findsNothing);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    },
  );

  testWidgets(
    'actual platform Reduce Motion disables fragments and idle pulse',
    (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          FakeAccessibilityFeatures(reduceMotion: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      final controller = await start(tester);
      final painted = tester
          .widgetList<CustomPaint>(find.byType(CustomPaint))
          .map((w) => w.painter)
          .whereType<RewindMarkPainter>()
          .single;
      expect(painted.reduced, isTrue);
      controller.attach(destination());
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 101));
      expect(intro, findsNothing);
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
    },
  );

  testWidgets(
    'interruption pauses motion, rotation retains native scale, dispose cancels timers',
    (tester) async {
      final controller = await start(tester);
      tester.view.physicalSize = const Size(852, 393);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await tester.pump(const Duration(seconds: 2));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(const Duration(milliseconds: 100));
      final mark = find.byWidgetPredicate(
        (w) => w is CustomPaint && w.painter is RewindMarkPainter,
      );
      expect(tester.getSize(mark), const Size(227.94, 227.94));
      await tester.pumpWidget(const SizedBox());
      controller.dispose();
      await tester.pump(const Duration(seconds: 3));
      expect(tester.takeException(), isNull);
    },
  );
}
