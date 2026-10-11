// LibraryReadingStore notifications and the widget tree lifecycle: readers
// save their last position in State.dispose, while the framework finalizes
// the tree. Listeners below the reader (title page, Local view, Favourites)
// call setState from the store notification.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_test_support.dart';

/// Shows the saved location of [progressKey] and rebuilds on every store
/// notification, like the screens below a reader.
class _ProgressLabel extends StatefulWidget {
  const _ProgressLabel({required this.store, required this.progressKey});

  final LibraryReadingStore store;
  final String progressKey;

  @override
  State<_ProgressLabel> createState() => _ProgressLabelState();
}

class _ProgressLabelState extends State<_ProgressLabel> {
  int builds = 0;

  @override
  void initState() {
    super.initState();
    widget.store.addListener(_changed);
  }

  @override
  void dispose() {
    widget.store.removeListener(_changed);
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    builds++;
    final location = widget.store.progressFor(widget.progressKey)?.location;
    return Text('saved ${location ?? 'none'}');
  }
}

/// Saves a position from its State.dispose, as the readers do.
class _SavesOnDispose extends StatefulWidget {
  const _SavesOnDispose({required this.store, required this.progressKey});

  final LibraryReadingStore store;
  final String progressKey;

  @override
  State<_SavesOnDispose> createState() => _SavesOnDisposeState();
}

class _SavesOnDisposeState extends State<_SavesOnDispose> {
  @override
  void dispose() {
    widget.store.saveProgress(
      LibraryReadingProgress(
        key: widget.progressKey,
        location: 'page:7',
        fraction: 0.7,
      ),
    );
    widget.store.saveProgress(
      LibraryReadingProgress(
        key: widget.progressKey,
        location: 'page:8',
        fraction: 0.8,
      ),
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const Text('reader');
}

void main() {
  setUpReaderEnvironment();

  Future<GlobalKey<NavigatorState>> pumpHome(
    WidgetTester tester,
    LibraryReadingStore store,
    String progressKey,
  ) async {
    final navigator = GlobalKey<NavigatorState>();
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigator,
        locale: const Locale('en'),
        supportedLocales: const <Locale>[Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(
          body: _ProgressLabel(store: store, progressKey: progressKey),
        ),
      ),
    );
    return navigator;
  }

  testWidgets(
    'closing a page reader within its save delay redraws the screen below',
    (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      const key = 'local:listened';
      final navigator = await pumpHome(tester, store, key);
      unawaited(
        navigator.currentState!.push<void>(
          MaterialPageRoute<void>(
            builder: (_) => LibraryPageReaderScreen(
              content: FakePageContent(progressKey: key),
              store: store,
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await settle(tester, rounds: 3);
      // The opening position is saved after the reader's 700 ms delay.
      await tester.pump(const Duration(milliseconds: 800));
      expect(store.progressFor(key)?.location, 'page:0');
      expect(find.text('saved page:0', skipOffstage: false), findsOneWidget);

      // Turn a page and close at once (B), before the turn animation has
      // reached page 1.
      final reader = tester.state<LibraryPageReaderScreenState>(
        find.byType(LibraryPageReaderScreen),
      );
      reader.gamepadBindings.right!();
      await tester.pump();
      reader.gamepadBindings.back!();
      final readerFinder = find.byType(
        LibraryPageReaderScreen,
        skipOffstage: false,
      );
      for (var i = 0; i < 20 && readerFinder.evaluate().isNotEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(readerFinder, findsNothing);
      expect(tester.takeException(), isNull);
      // The turn requested just before B is the position saved, even though
      // its animation had not reached the new page yet.
      expect(store.progressFor(key)?.location, 'page:1');
      // The reader saves before it is popped, so the screen below redraws
      // with the new position (a save from State.dispose, while the tree is
      // locked, is covered by the next test).
      await tester.pump();
      expect(find.text('saved page:1'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await flushStore(tester, store);
    },
  );

  testWidgets(
    'changes saved while the tree is locked reach listeners once, in order',
    (tester) async {
      final (store, _) = await createStore(tester);
      const key = 'local:disposed';
      final navigator = await pumpHome(tester, store, key);
      final label = tester.state<_ProgressLabelState>(
        find.byType(_ProgressLabel),
      );
      unawaited(
        navigator.currentState!.push<void>(
          MaterialPageRoute<void>(
            builder: (_) => _SavesOnDispose(store: store, progressKey: key),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final buildsBefore = label.builds;
      var notifications = 0;
      store.addListener(() => notifications++);

      navigator.currentState!.pop();
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // Both saves are delivered by one notification after the frame.
      expect(notifications, 1);
      expect(find.text('saved page:8'), findsOneWidget);
      expect(label.builds, greaterThan(buildsBefore));

      // Outside a frame every change still notifies synchronously.
      store.saveProgress(
        LibraryReadingProgress(key: key, location: 'page:9', fraction: 0.9),
      );
      expect(notifications, 2);
      await tester.pump();
      expect(find.text('saved page:9'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await flushStore(tester, store);
    },
  );
}
