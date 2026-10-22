import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/widgets/console_bubble_transition.dart';
import 'package:neostation/widgets/neo_glass_bubble.dart';

class _Visit {
  int created = 0;
  int disposed = 0;
  int returned = 0;
  bool playlistInput = false;
  final scroll = ScrollController();
}

class _Playlist extends StatefulWidget {
  const _Playlist(this.visit);
  final _Visit visit;
  @override
  State<_Playlist> createState() => _PlaylistState();
}

class _PlaylistState extends State<_Playlist> {
  @override
  void initState() {
    super.initState();
    widget.visit.created++;
    GamepadNavigationManager.pushLayer('bubble-test-playlist',
      onActivate: () => widget.visit.playlistInput = true,
      onDeactivate: () => widget.visit.playlistInput = false);
  }
  @override
  void dispose() {
    widget.visit.disposed++;
    GamepadNavigationManager.popLayer('bubble-test-playlist');
    super.dispose();
  }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Sega 32X')),
    body: ListView.builder(controller: widget.visit.scroll, itemCount: 80,
      itemBuilder: (_, i) => ListTile(title: Text('Game $i'))),
  );
}

class _Systems extends StatefulWidget {
  const _Systems({super.key, required this.visit});
  final _Visit visit;
  @override
  State<_Systems> createState() => _SystemsState();
}

class _SystemsState extends State<_Systems> {
  final pages = PageController(initialPage: 2);
  late BuildContext source;
  int selected = 2;

  Future<void> open() async {
    await ConsoleBubbleScope.open<void>(source, identity: '$selected',
      builder: (_) => _Playlist(widget.visit));
    widget.visit.returned++;
  }

  @override
  void dispose() {
    pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ConsoleBubbleScope(builder: (context) {
    source = context;
    return Scaffold(body: PageView.builder(controller: pages, itemCount: 5,
      onPageChanged: (i) => setState(() => selected = i),
      itemBuilder: (_, i) => Center(child: ConsoleBubbleAnchor(
        identity: '$i', selected: selected == i,
        child: SizedBox(width: 180, height: 230,
          child: GestureDetector(key: ValueKey('console-$i'), onTap: open,
            child: NeoGlassBubble(radius: 30,
              child: Center(child: Text('Console $i'))))),
      )),
    ));
  });
}

void main() {
  Future<({GlobalKey<_SystemsState> systems, GlobalKey<NavigatorState> nav, _Visit visit})> mount(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final systems = GlobalKey<_SystemsState>();
    final nav = GlobalKey<NavigatorState>();
    final visit = _Visit();
    addTearDown(visit.scroll.dispose);
    await tester.pumpWidget(MaterialApp(navigatorKey: nav,
      theme: ThemeData.dark(), home: _Systems(key: systems, visit: visit)));
    await tester.pump();
    return (systems: systems, nav: nav, visit: visit);
  }

  Future<void> start(WidgetTester tester, _SystemsState state) async {
    unawaited(state.open());
    await tester.pump();
    await tester.pump();
  }

  testWidgets('artwork morphs; playlist mounts once and reverse retains carousel state', (tester) async {
    final h = await mount(tester);
    final source = tester.getRect(find.byKey(const ValueKey('console-2')));
    await start(tester, h.systems.currentState!);
    await tester.pump(const Duration(milliseconds: 210));
    final flight = tester.getRect(find.byKey(const ValueKey('console-bubble-flight')));
    expect(flight.width, greaterThan(source.width));
    expect(flight.width, lessThan(844));
    expect(find.byType(RawImage), findsOneWidget);
    expect(h.visit.created, 1);
    expect(h.visit.playlistInput, isFalse);
    final page = tester.state(find.byType(_Playlist));
    await tester.pumpAndSettle();
    expect(h.visit.playlistInput, isTrue);
    expect(identical(page, tester.state(find.byType(_Playlist))), isTrue);
    h.visit.scroll.jumpTo(160);
    await tester.pump();
    await tester.binding.setSurfaceSize(const Size(900, 600));
    await tester.pump();
    expect(h.visit.scroll.offset, 160);
    expect(h.visit.created, 1);
    h.nav.currentState!.pop();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 170));
    expect(h.visit.playlistInput, isFalse);
    expect(h.visit.returned, 0);
    final closing = tester.getRect(find.byKey(const ValueKey('console-bubble-flight')));
    expect(closing.width, lessThan(900));
    await tester.pumpAndSettle();
    expect(h.visit.returned, 1);
    expect(h.visit.disposed, 1);
    expect(h.systems.currentState!.selected, 2);
    expect(h.systems.currentState!.pages.page, 2);
    expect(find.byKey(const ValueKey('console-2')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('rapid activations share the lifetime lock through the reverse flight', (tester) async {
    final h = await mount(tester);
    await start(tester, h.systems.currentState!);
    unawaited(h.systems.currentState!.open());
    await tester.pumpAndSettle();
    expect(h.visit.created, 1);
    expect(h.visit.returned, 0);
    h.nav.currentState!.pop();
    await tester.pump();
    unawaited(h.systems.currentState!.open());
    await tester.pump(const Duration(milliseconds: 150));
    expect(h.visit.created, 1);
    expect(h.visit.returned, 0);
    await tester.pumpAndSettle();
    expect(h.visit.returned, 3);
    await start(tester, h.systems.currentState!);
    await tester.pumpAndSettle();
    expect(h.visit.created, 2);
    h.nav.currentState!.pop();
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('touch activation and programmatic controller activation take the same route', (tester) async {
    final h = await mount(tester);
    await tester.tap(find.byKey(const ValueKey('console-2')));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 210));
    final touch = tester.getRect(find.byKey(const ValueKey('console-bubble-flight')));
    h.nav.currentState!.pop(); // Interrupt the opening, before completion.
    await tester.pumpAndSettle();
    expect(h.visit.disposed, 1);
    await start(tester, h.systems.currentState!);
    await tester.pump(const Duration(milliseconds: 210));
    expect(tester.getRect(find.byKey(const ValueKey('console-bubble-flight'))), touch);
    h.nav.currentState!.pop();
    await tester.pumpAndSettle();
    expect(h.visit.returned, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('iOS Reduce Motion avoids snapshots and spatial expansion', (tester) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(reduceMotion: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    final h = await mount(tester);
    await start(tester, h.systems.currentState!);
    await tester.pump(const Duration(milliseconds: 40));
    expect(find.byType(RawImage), findsNothing);
    expect(tester.getSize(find.byKey(const ValueKey('console-bubble-flight'))), const Size(844, 390));
    await tester.pumpAndSettle();
    h.nav.currentState!.pop();
    await tester.pumpAndSettle();
    expect(h.visit.returned, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('removing the scope during a flight releases route and input ownership', (tester) async {
    final h = await mount(tester);
    await start(tester, h.systems.currentState!);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();
    expect(h.visit.disposed, 1);
    expect(tester.takeException(), isNull);
  });
}
